"""Folder-specific model settings without changing the process environment."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import dotenv_values

if TYPE_CHECKING:
    from .verification import VerifierSettings

DEFAULT_BASE_URL = "http://localhost:11434/v1"
OCR_ENGINES = ("auto", "tesseract")
TABLE_MODES = ("ruled", "docling", "predicted")
DEFAULT_DOCUMENT_TIMEOUT = 180.0
_SWITCHES = {
    **dict.fromkeys(("1", "true", "yes", "on"), True),
    **dict.fromkeys(("0", "false", "no", "off"), False),
}


class ConfigError(ValueError):
    """Raised when a settings file cannot be read."""


@dataclass(frozen=True)
class LlmSettings:
    base_url: str
    model: str | None
    api_key: str | None = field(repr=False)
    env_file: Path | None


def load_llm_settings(
    input_dir: Path,
    *,
    env_file: Path | None = None,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    default_base_url: str = DEFAULT_BASE_URL,
    default_model: str | None = None,
) -> LlmSettings:
    """Resolve CLI flags > process environment > nearest .env > defaults.

    Automatic discovery starts at the input folder and walks its parents. An
    explicit env_file is relative to the working directory and replaces discovery.
    Only one file is loaded; values are not interpolated or exported to os.environ.
    """
    path, value = _settings_source(input_dir, env_file)
    return LlmSettings(
        base_url=value("OPENAI_BASE_URL", base_url) or default_base_url,
        model=value("INTEXTUM_MODEL", model) or default_model,
        api_key=value("OPENAI_API_KEY", api_key),
        env_file=path,
    )


@dataclass(frozen=True)
class RecognitionSettings:
    ocr_engine: str
    ocr_languages: list[str]
    table_mode: str
    detect_marks: bool = False
    document_timeout: float = DEFAULT_DOCUMENT_TIMEOUT


def load_recognition_settings(
    input_dir: Path,
    *,
    env_file: Path | None = None,
    ocr_engine: str | None = None,
    ocr_languages: list[str] | None = None,
    table_mode: str | None = None,
    detect_marks: bool | None = None,
    document_timeout: float | None = None,
) -> RecognitionSettings:
    """Resolve OCR and table settings with the same precedence as model settings.

    INTEXTUM_OCR_LANGUAGES lists codes separated by commas, e.g. ``deu,eng``.
    """
    _, value = _settings_source(input_dir, env_file)
    engine = value("INTEXTUM_OCR_ENGINE", ocr_engine) or "auto"
    if engine not in OCR_ENGINES:
        raise ConfigError(
            f"INTEXTUM_OCR_ENGINE must be one of {', '.join(OCR_ENGINES)}: {engine}"
        )
    mode = value("INTEXTUM_TABLE_MODE", table_mode) or "ruled"
    if mode not in TABLE_MODES:
        raise ConfigError(
            f"INTEXTUM_TABLE_MODE must be one of {', '.join(TABLE_MODES)}: {mode}"
        )
    if ocr_languages:
        languages = list(ocr_languages)
    else:
        raw = value("INTEXTUM_OCR_LANGUAGES", None) or ""
        languages = [code.strip() for code in raw.split(",") if code.strip()]
    raw_marks = value(
        "INTEXTUM_DETECT_MARKS",
        None if detect_marks is None else str(detect_marks),
    )
    switch = (raw_marks or "false").strip().casefold()
    if switch not in _SWITCHES:
        raise ConfigError(f"INTEXTUM_DETECT_MARKS must be true or false: {raw_marks}")
    raw_timeout = value(
        "INTEXTUM_DOCUMENT_TIMEOUT",
        None if document_timeout is None else str(document_timeout),
    )
    try:
        timeout = float(raw_timeout) if raw_timeout else DEFAULT_DOCUMENT_TIMEOUT
    except ValueError:
        timeout = math.nan
    if not (math.isfinite(timeout) and timeout > 0):
        raise ConfigError(
            f"INTEXTUM_DOCUMENT_TIMEOUT must be a positive number: {raw_timeout}"
        )
    return RecognitionSettings(
        ocr_engine=engine,
        ocr_languages=languages,
        table_mode=mode,
        detect_marks=_SWITCHES[switch],
        document_timeout=timeout,
    )


def load_verifier_settings(
    input_dir: Path,
    *,
    env_file: Path | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    threshold: float | None = None,
    max_chars: int | None = None,
) -> VerifierSettings | None:
    """Decision-model settings, or None when no verifier model is configured.

    The endpoint defaults to the extraction endpoint (OPENAI_BASE_URL), whose
    API key is reused only when the verifier talks to that same endpoint.
    """
    from .verification import DEFAULT_MAX_CHARS, DEFAULT_THRESHOLD, VerifierSettings

    _, value = _settings_source(input_dir, env_file)
    name = value("INTEXTUM_VERIFIER_MODEL", model)
    if not name:
        return None
    extraction_url = value("OPENAI_BASE_URL", None) or DEFAULT_BASE_URL
    url = value("INTEXTUM_VERIFIER_BASE_URL", base_url) or extraction_url
    key = value("INTEXTUM_VERIFIER_API_KEY", api_key)
    if key is None and url == extraction_url:
        key = value("OPENAI_API_KEY", None)
    raw = value(
        "INTEXTUM_VERIFIER_THRESHOLD",
        None if threshold is None else str(threshold),
    )
    try:
        limit = float(raw) if raw is not None else DEFAULT_THRESHOLD
    except ValueError:
        raise ConfigError(
            f"INTEXTUM_VERIFIER_THRESHOLD is not a number: {raw}"
        ) from None
    if not 0 < limit < 1:
        raise ConfigError("INTEXTUM_VERIFIER_THRESHOLD must be between 0 and 1")
    return VerifierSettings(
        model=name,
        base_url=url,
        api_key=key,
        threshold=limit,
        max_chars=max_chars or DEFAULT_MAX_CHARS,
    )


def _settings_source(input_dir: Path, env_file: Path | None):
    """The settings file in use and a lookup: override > environment > file."""
    if env_file is not None:
        path = env_file.expanduser().resolve()
        if not path.is_file():
            raise ConfigError(f"settings file not found: {path}")
    else:
        root = input_dir.resolve()
        path = next(
            (p / ".env" for p in (root, *root.parents) if (p / ".env").is_file()),
            None,
        )

    values: dict[str, str | None] = {}
    if path is not None:
        try:
            with path.open(encoding="utf-8-sig") as stream:
                values = dotenv_values(stream=stream, interpolate=False)
        except (OSError, UnicodeError) as exc:
            raise ConfigError(f"cannot read settings file {path}: {exc}") from exc

    def value(name: str, override: str | None) -> str | None:
        if override is not None:
            return override
        return os.environ.get(name) or values.get(name) or None

    return path, value
