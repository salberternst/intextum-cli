"""Shared records at the boundary between processing and SQLite storage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict

from .schema import DocumentClass


class SourceReference(TypedDict):
    path: str
    digest: str
    key: NotRequired[str | None]


@dataclass
class ConversionRecord:
    key: str
    digest: str
    suffix: str
    pages: list[str]
    paged: bool
    notes: list[str]
    settings: dict
    manifest: dict | None = None
    document: dict | None = None


WorkspaceSnapshot = tuple[str, dict, list[DocumentClass]]


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)
