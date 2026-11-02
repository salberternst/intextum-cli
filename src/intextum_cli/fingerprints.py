"""Content, configuration, and code identities for incremental extraction."""

from __future__ import annotations

import hashlib
import json
from functools import cache
from pathlib import Path
from typing import Any

from .convert import file_digest
from .document_cache import DocumentStore
from .groups import Group
from .llm_types import generation_settings
from .processing import Options, SourceScope

# Modules that shape results. The CLI, the statistics and the viewer do not,
# and the options they pass are part of the fingerprint payload anyway.
RESULT_MODULES = (
    "classify",
    "convert",
    "document_cache",
    "document_model",
    "dedupe",
    "edits",
    "extract",
    "groups",
    "llm",
    "llm_types",
    "llm_endpoints",
    "processing",
    "group_processing",
    "external_fields",
    "fingerprints",
    "conversion_readers",
    "conversion_marks",
    "conversion_recovery",
    "conversion_tables",
    "extraction_prompt",
    "pipeline",
    "schema",
    "source",
    "sources",
    "values",
)


@cache
def _code_digest() -> str:
    """Hash of the code that shapes results, so logic changes reprocess groups."""
    digest = hashlib.sha256()
    for name in RESULT_MODULES:
        digest.update((Path(__file__).parent / f"{name}.py").read_bytes())
    return digest.hexdigest()


def fingerprint(
    group: Group,
    options: Options,
    duplicates: dict[str, Any] | None = None,
    scope: SourceScope | None = None,
) -> str:
    external = any(f.external for c in options.classes for f in c.fields)
    neighbours = (
        [[scope.rel(path), file_digest(path)] for path in scope.neighbours(group)]
        if external and scope is not None
        else []
    )
    overrides = (
        {
            name: [scope.rel(p) for p in files] if files is not None else None
            for name, files in options.overrides.get(group.name, {}).items()
        }
        if scope is not None
        else {}
    )
    # Only what patterns capture: moving a whole workspace changes no value.
    path_values = {
        f.from_path.pattern: [f.from_path.capture(path) for path in group.files]
        for c in options.classes
        for f in c.fields
        if f.from_path
    }
    payload = {
        "neighbours": neighbours,
        "path_values": path_values,
        "overrides": overrides,
        "duplicates": duplicates or {},
        "code": _code_digest(),
        "conversions": [
            DocumentStore.key(
                file_digest(p),
                p.suffix,
                options.force_ocr,
                ocr_engine=options.ocr_engine,
                ocr_languages=options.ocr_languages,
                table_mode=options.table_mode,
                detect_marks=options.detect_marks,
            )
            for p in group.files
        ],
        "mode": "classify" if options.classify_only else "extract",
        "force_ocr": options.force_ocr,
        "generation": generation_settings(options),
        "files": [[group.relative(path), file_digest(path)] for path in group.files],
        "class": group.document_class or options.forced_class,
        "classification_source": group.classification_source,
        "no_matching_class": group.no_matching_class,
        "classes": [c.model_dump(by_alias=True) for c in options.classes],
        "model": options.model,
        "base_url": options.base_url.rstrip("/"),
        "max_chars": options.max_chars,
        "retries": options.retries,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()
