"""Assign a group of files to one configured document class."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .convert import ConvertedFile
from .llm_types import JsonLlm, generation_settings
from .schema import DocumentClass, find_class
from .store import WorkspaceStore

NO_MATCH = "No matching document class"
_EXCERPT_CHARS_PER_FILE = 3_000
_EXCERPT_CHARS_TOTAL = 12_000


@dataclass
class Classification:
    name: str | None
    source: str
    reason: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "reason": self.reason,
            "error": self.error,
        }


def group_excerpt(files: list[ConvertedFile]) -> str:
    """The beginning of each file, so every file in a group gets a say."""
    usable = [file for file in files if file.error is None and file.text.strip()]
    if not usable:
        return ""
    per_file = min(_EXCERPT_CHARS_PER_FILE, _EXCERPT_CHARS_TOTAL // len(usable))
    return "\n\n".join(
        f"=== FILE: {file.name} ===\n{file.text[:per_file]}" for file in usable
    )


def _class_lines(classes: list[DocumentClass]) -> str:
    lines = []
    for document_class in classes:
        line = f"- {document_class.name}"
        if document_class.description:
            line += f": {document_class.description}"
        if document_class.aliases:
            line += f" (also known as: {', '.join(document_class.aliases)})"
        lines.append(line)
    lines.append(f"- {NO_MATCH}: none of the classes above clearly fits")
    return "\n".join(lines)


class LlmClassifier:
    """Classifies with the LLM; results are cached in the workspace when configured.

    The cache key covers the text the model sees, the class names, descriptions and
    aliases, the model, endpoint, generation settings, and classification/client
    code, so changes to any of those ask the model again. Changes to a class's
    fields do not.
    """

    def __init__(self, llm: JsonLlm, store: WorkspaceStore | None = None):
        self.llm = llm
        self.store = store

    def cache_key(self, excerpt: str, classes: list[DocumentClass]) -> str:
        payload = json.dumps(
            {
                "excerpt": excerpt,
                # Only what the prompt shows: editing fields keeps the cache valid.
                "classes": [[c.name, c.description, c.aliases] for c in classes],
                "model": self.llm.model,
                "base_url": getattr(self.llm, "base_url", "").rstrip("/"),
                "generation": generation_settings(self.llm),
                "code": hashlib.sha256(
                    b"".join(
                        Path(__file__).with_name(f"{module}.py").read_bytes()
                        for module in ("classify", "llm", "llm_types", "llm_endpoints")
                    )
                ).hexdigest(),
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def classify(
        self, files: list[ConvertedFile], classes: list[DocumentClass]
    ) -> Classification:
        excerpt = group_excerpt(files)
        key = self.cache_key(excerpt, classes)
        cached = (
            self.store.cache.classification(key) if self.store and excerpt else None
        )
        if cached is not None:
            return Classification(**cached)
        result = self._classify(excerpt, classes)
        if self.store and excerpt and result.error is None:
            self.store.cache.save_classification(key, result.as_dict())
        return result

    def _classify(self, excerpt: str, classes: list[DocumentClass]) -> Classification:
        if not excerpt:
            return Classification(None, "llm", error="no text to classify")
        labels = [document_class.name for document_class in classes] + [NO_MATCH]
        system = (
            "You classify documents. The input is one or more files that belong "
            "together (for example a letter and its attachments). Pick the single "
            "class that describes the group as a whole, usually the main document."
        )
        user = "\n".join(
            [
                "CLASSES:",
                _class_lines(classes),
                "",
                "FILES:",
                excerpt,
                "",
                'Respond with JSON: {"class": <one class name>, "reason": <one short '
                "sentence>}.",
            ]
        )
        schema = {
            "type": "object",
            "properties": {
                "class": {"type": "string", "enum": labels},
                "reason": {"type": "string"},
            },
            "required": ["class", "reason"],
            "additionalProperties": False,
        }
        files = [
            line.removeprefix("=== FILE: ").removesuffix(" ===")
            for line in excerpt.splitlines()
            if line.startswith("=== FILE: ")
        ]
        label = "classify " + (files[0] if files else "?")
        if len(files) > 1:
            label += f" (+{len(files) - 1})"
        reply = self.llm.complete_json(
            system=system, user=user, name="document_class", schema=schema, label=label
        )
        if reply.data is None:
            return Classification(None, "llm", error="model returned invalid JSON")
        raw_label = str(reply.data.get("class") or "").strip()
        reason = reply.data.get("reason")
        reason = reason.strip() if isinstance(reason, str) else None
        if not raw_label or raw_label.casefold() == NO_MATCH.casefold():
            return Classification(None, "llm", reason=reason)
        document_class = find_class(classes, raw_label)
        if document_class is None:
            return Classification(
                None, "llm", reason=reason, error=f"unknown class '{raw_label}'"
            )
        return Classification(document_class.name, "llm", reason=reason)
