"""Client for decision-model endpoints that score typed questions about a text.

Ollama (0.40.4 or later for Kev) and the llama.cpp server expose
``POST /v1/systemone``; OpenRouter exposes the same request shape at
``POST /api/alpha/decisions``. A request carries the ``state`` text and named
``questions``; yes/no ("noul") answers return the probability of yes.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

_RETRY_STATUS = {429, 500, 502, 503, 524, 529}


class DecisionError(RuntimeError):
    """The decision endpoint failed or returned an unusable answer."""


class Decider(Protocol):
    model: str

    def decide(self, state: str, questions: dict[str, dict]) -> dict[str, dict]: ...


def decisions_url(base_url: str) -> str:
    """OpenRouter's alpha route, otherwise the local /v1/systemone route."""
    parts = urllib.parse.urlsplit(base_url)
    root = f"{parts.scheme}://{parts.netloc}"
    if parts.netloc.endswith("openrouter.ai"):
        return f"{root}/api/alpha/decisions"
    return f"{root}/v1/systemone"


def yes_probability(answer: dict[str, Any]) -> float | None:
    """Normalise a noul answer: ``noul`` or a ``true`` option probability."""
    value = answer.get("noul")
    if value is None:
        value = (answer.get("probabilities") or {}).get("true")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return min(max(float(value), 0.0), 1.0)


@dataclass
class DecisionClient:
    base_url: str
    model: str
    api_key: str | None = field(default=None, repr=False)
    timeout: float = 600.0
    retries: int = 2

    @property
    def url(self) -> str:
        return decisions_url(self.base_url)

    def decide(self, state: str, questions: dict[str, dict]) -> dict[str, dict]:
        body = json.dumps(
            {"model": self.model, "state": state, "questions": questions}
        ).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(self.url, data=body, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    reply = json.load(response)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:300]
                if exc.code in _RETRY_STATUS and attempt < self.retries:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise DecisionError(
                    f"{self.url} returned HTTP {exc.code}: {detail}"
                ) from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt < self.retries:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise DecisionError(f"cannot reach {self.url}: {exc}") from None
            except json.JSONDecodeError as exc:
                raise DecisionError(f"{self.url} returned invalid JSON") from exc
            answers = reply.get("answers") if isinstance(reply, dict) else None
            if not isinstance(answers, dict):
                error = reply.get("error") if isinstance(reply, dict) else None
                raise DecisionError(f"{self.url} returned no answers: {error or reply}")
            return answers
        raise AssertionError("unreachable")
