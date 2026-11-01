"""Minimal OpenAI-compatible JSON chat client (Ollama, LM Studio, vLLM, OpenAI)."""

from __future__ import annotations

import json
import logging
import math
import re
import time
from collections.abc import Callable
from typing import Any

from .llm_endpoints import is_ollama
from .llm_types import CallProgress, CallStats, JsonReply, LlmError

logger = logging.getLogger(__name__)

_TOKEN_GROWTH_LIMIT = 4
# Seconds between progress reports while a reply is streaming.
PROGRESS_INTERVAL_S = 1.0
# Cautious estimate for sizing a request before the server has counted the
# prompt, plus room for the chat template, so input + output fit the context.
_SAFE_CHARS_PER_TOKEN = 2.5
_TEMPLATE_TOKENS = 64
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")
_UNSUPPORTED_MARKERS = (
    "unsupported", "not supported", "does not support", "not implemented",
    "unknown parameter", "unrecognized", "invalid value", "must be",
)  # fmt: skip


def parse_json_object(content: str) -> dict[str, Any] | None:
    """Parse a JSON object, tolerating think blocks, code fences and chatter."""
    text = _THINK_RE.sub("", content).strip()
    text = _FENCE_RE.sub("", text).strip()
    for candidate in (text, text[text.find("{") : text.rfind("}") + 1]):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _looks_like_schema_unsupported(message: str) -> bool:
    lowered = message.casefold()
    mentions_format = any(
        marker in lowered for marker in ("json_schema", "response_format", "structured")
    )
    return mentions_format and any(marker in lowered for marker in _UNSUPPORTED_MARKERS)


class OpenAiJsonLlm:
    """Chat-completions client that asks for schema-constrained JSON.

    Falls back to plain JSON mode when the server rejects ``json_schema`` and
    doubles the token budget (up to 4x, never past the context window) when a
    reply is cut off. Thinking is
    switched off (``enable_thinking``) unless ``thinking`` is set; servers that
    reject the switch get requests without it. Ollama ignores that switch and
    gets ``reasoning_effort: none`` instead.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        max_output_tokens: int = 4096,
        timeout: float = 900.0,
        client: Any = None,
        context_length: int | None = None,
        on_call: Callable[[CallStats], None] | None = None,
        on_progress: Callable[[CallProgress], None] | None = None,
        thinking: bool = False,
        ollama: bool | None = None,
    ):
        if ollama is None:
            # Only a real endpoint is probed; injected test clients say so.
            ollama = client is None and is_ollama(base_url)
        self.ollama = ollama
        if client is None:
            from openai import OpenAI

            client = OpenAI(
                base_url=base_url, api_key=api_key or "local", timeout=timeout
            )
        self._client = client
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_output_tokens = max_output_tokens
        # Response formats to try, best first; unsupported ones are dropped.
        self._formats = ["json_schema", "json_object", "text"]
        self._usage_supported = True
        self.context_length = context_length
        self.on_call = on_call
        self.on_progress = on_progress
        self.thinking = thinking
        self._thinking_switch_supported = True
        self._attempt = 1
        self._prompt_tokens: int | None = None

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        name: str,
        schema: dict[str, Any],
        label: str = "",
    ) -> JsonReply:
        attempts: list[dict[str, Any]] = []
        prompt_chars = len(system) + len(user)
        self._prompt_tokens = None
        tokens = self._output_budget(self.max_output_tokens, prompt_chars)
        while True:
            self._attempt = len(attempts) + 1
            content, finish_reason = self._call(
                system, user, name, schema, tokens, label
            )
            attempts.append({"max_tokens": tokens, "finish_reason": finish_reason})
            if (
                finish_reason != "length"
                or tokens >= self.max_output_tokens * _TOKEN_GROWTH_LIMIT
            ):
                break
            more = self._output_budget(tokens * 2, prompt_chars)
            if more <= tokens:
                logger.warning(
                    "reply truncated at %d tokens; the context window allows no more",
                    tokens,
                )
                break
            logger.warning("reply truncated at %d tokens; retrying with more", tokens)
            tokens = more
        return JsonReply(
            data=parse_json_object(content),
            content=content,
            finish_reason=finish_reason,
            attempts=attempts,
        )

    def _output_budget(self, wanted: int, prompt_chars: int) -> int:
        """Output tokens to request, capped so input + output fit the context."""
        if not self.context_length:
            return wanted
        prompt = self._prompt_tokens
        if prompt is None:
            prompt = math.ceil(prompt_chars / _SAFE_CHARS_PER_TOKEN)
        room = self.context_length - prompt - _TEMPLATE_TOKENS
        return max(min(wanted, room), 1)

    def _call(
        self,
        system: str,
        user: str,
        name: str,
        schema: dict[str, Any],
        max_tokens: int,
        label: str = "",
    ) -> tuple[str, str | None]:
        mode = self._formats[0]
        response_format: dict[str, Any] | None = {"type": mode}
        if mode == "json_schema":
            response_format["json_schema"] = {
                "name": name,
                "strict": True,
                "schema": schema,
            }
        elif mode == "text":
            response_format = None
        try:
            return self._stream(system, user, response_format, max_tokens, label, mode)
        except Exception as exc:
            message = str(exc)
            if self._usage_supported and "stream_options" in message:
                logger.warning("server rejected stream_options; token usage estimated")
                self._usage_supported = False
                return self._call(system, user, name, schema, max_tokens, label)
            if self._thinking_switch_supported and "chat_template_kwargs" in message:
                logger.warning("server rejected chat_template_kwargs; thinking not set")
                self._thinking_switch_supported = False
                return self._call(system, user, name, schema, max_tokens, label)
            if len(self._formats) > 1 and _looks_like_schema_unsupported(message):
                logger.warning("server rejected %s response format; trying next", mode)
                self._formats.pop(0)
                return self._call(system, user, name, schema, max_tokens, label)
            raise LlmError(f"{type(exc).__name__}: {exc}") from exc

    def _stream(
        self,
        system: str,
        user: str,
        response_format: dict[str, Any] | None,
        max_tokens: int,
        label: str = "",
        mode: str = "",
    ) -> tuple[str, str | None]:
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0,
            # Streaming keeps long local generations from hitting read timeouts.
            "stream": True,
        }
        if response_format is not None:
            request["response_format"] = response_format
        if self._usage_supported:
            request["stream_options"] = {"include_usage": True}
        if self._thinking_switch_supported:
            request["extra_body"] = {
                "chat_template_kwargs": {"enable_thinking": self.thinking}
            }
        if self.ollama and not self.thinking:
            # Ollama's OpenAI endpoint ignores chat_template_kwargs.
            request["reasoning_effort"] = "none"
        started = time.monotonic()
        stream = self._client.chat.completions.create(**request)
        parts: list[str] = []
        finish_reason = None
        first_token: float | None = None
        usage: Any = None
        # Streamed chunks carry about one token each; used for progress only.
        answer_chunks = thinking_chunks = 0
        reported = started
        for chunk in stream:
            usage = getattr(chunk, "usage", None) or usage
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None)
            extra = getattr(delta, "model_extra", None) or {}
            # Thinking arrives as reasoning_content (LM Studio, older vLLM) or
            # reasoning (newer vLLM); it counts as the first token either way.
            reasoning = (
                getattr(delta, "reasoning_content", None)
                or getattr(delta, "reasoning", None)
                or extra.get("reasoning_content")
                or extra.get("reasoning")
            )
            if first_token is None and (content or reasoning):
                first_token = time.monotonic() - started
            if isinstance(content, str):
                parts.append(content)
            answer_chunks += bool(content)
            thinking_chunks += bool(reasoning)
            finish_reason = getattr(choices[0], "finish_reason", None) or finish_reason
            if self.on_progress is None:
                continue
            now = time.monotonic()
            if now - reported >= PROGRESS_INTERVAL_S:
                reported = now
                self.on_progress(
                    CallProgress(
                        label=label,
                        tokens=answer_chunks + thinking_chunks,
                        thinking_tokens=thinking_chunks,
                        elapsed_s=now - started,
                        max_tokens=max_tokens,
                        attempt=self._attempt,
                    )
                )
        text = "".join(parts)
        self._prompt_tokens = getattr(usage, "prompt_tokens", None)
        if self.on_call is not None:
            details = getattr(usage, "completion_tokens_details", None)
            self.on_call(
                CallStats(
                    label=label,
                    prompt_chars=len(system) + len(user),
                    output_chars=len(text),
                    prompt_tokens=getattr(usage, "prompt_tokens", None),
                    completion_tokens=getattr(usage, "completion_tokens", None),
                    reasoning_tokens=getattr(details, "reasoning_tokens", None),
                    first_token_s=first_token,
                    total_s=time.monotonic() - started,
                    finish_reason=finish_reason,
                    max_tokens=max_tokens,
                    context_length=self.context_length,
                    response_format=mode,
                )
            )
        return text, finish_reason
