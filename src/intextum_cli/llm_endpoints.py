"""Endpoint detection and optional model context-window discovery."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


def _get_json(url: str, timeout: float) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _root(base_url: str) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def is_ollama(base_url: str, timeout: float = 3.0) -> bool:
    """Whether the endpoint is Ollama, which answers ``GET /api/version``."""
    try:
        info = _get_json(f"{_root(base_url)}/api/version", timeout)
    except Exception:  # noqa: BLE001 - any other server
        return False
    return isinstance(info, dict) and isinstance(info.get("version"), str)


def fetch_context_length(base_url: str, model: str, timeout: float = 3.0) -> int | None:
    """Ask the server for the model's context window, if it says.

    Supports LM Studio (``/api/v0/models/<model>``, loaded context), Ollama
    (``/api/ps``, context of the loaded model) and vLLM (``max_model_len`` in
    ``/v1/models``); other servers return None.
    """
    root = _root(base_url)
    try:
        info = _get_json(
            f"{root}/api/v0/models/{urllib.parse.quote(model, safe='/')}", timeout
        )
        for key in ("loaded_context_length", "max_context_length"):
            value = info.get(key) if isinstance(info, dict) else None
            if isinstance(value, int) and value > 0:
                return value
    except Exception:  # noqa: BLE001 - not LM Studio, try the next
        pass
    try:
        running = _get_json(f"{root}/api/ps", timeout)
        for entry in running.get("models", []) if isinstance(running, dict) else []:
            names = {entry.get("name"), entry.get("model")}
            value = entry.get("context_length")
            if names & {model, f"{model}:latest"} and isinstance(value, int):
                return value
    except Exception:  # noqa: BLE001 - not Ollama, try the next
        pass
    try:
        listing = _get_json(f"{base_url.rstrip('/')}/models", timeout)
    except Exception:  # noqa: BLE001 - optional information
        return None
    for entry in listing.get("data", []) if isinstance(listing, dict) else []:
        if isinstance(entry, dict) and entry.get("id") == model:
            value = entry.get("max_model_len") or entry.get("context_length")
            if isinstance(value, int) and value > 0:
                return value
    return None
