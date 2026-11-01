"""Shared model reply, telemetry, and generation-setting types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

# Rough token estimate when the server reports no usage (German text, JSON).
CHARS_PER_TOKEN = 3.5


class LlmError(RuntimeError):
    """Raised when the model endpoint fails."""


@dataclass
class CallStats:
    """Measurements of one model request."""

    label: str
    prompt_chars: int
    output_chars: int
    prompt_tokens: int | None
    completion_tokens: int | None
    reasoning_tokens: int | None
    first_token_s: float | None
    total_s: float
    finish_reason: str | None
    max_tokens: int
    context_length: int | None
    response_format: str

    @property
    def estimated(self) -> bool:
        return self.prompt_tokens is None or self.completion_tokens is None

    @property
    def input_tokens(self) -> int:
        if self.prompt_tokens is not None:
            return self.prompt_tokens
        return round(self.prompt_chars / CHARS_PER_TOKEN)

    @property
    def output_tokens(self) -> int:
        if self.completion_tokens is not None:
            return self.completion_tokens
        return round(self.output_chars / CHARS_PER_TOKEN)

    @property
    def tokens_per_second(self) -> float | None:
        generating = self.total_s - (self.first_token_s or 0.0)
        return self.output_tokens / generating if generating > 0.05 else None


@dataclass
class CallProgress:
    """Snapshot of a reply that is still streaming."""

    label: str
    tokens: int
    thinking_tokens: int
    elapsed_s: float
    max_tokens: int
    attempt: int


@dataclass
class JsonReply:
    data: dict[str, Any] | None
    content: str
    finish_reason: str | None
    attempts: list[dict[str, Any]] = field(default_factory=list)


class JsonLlm(Protocol):
    model: str

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        name: str,
        schema: dict[str, Any],
        label: str = "",
    ) -> JsonReply: ...


def generation_settings(settings: object) -> dict[str, Any]:
    """Requested generation settings shared by result and classification keys.

    Minimal JsonLlm implementations may omit these optional client attributes.
    Runtime compatibility fallbacks are deliberately excluded from the identity.
    """
    return {
        "thinking": getattr(settings, "thinking", False),
        "context_length": getattr(settings, "context_length", None),
        "max_output_tokens": getattr(settings, "max_output_tokens", 4096),
    }
