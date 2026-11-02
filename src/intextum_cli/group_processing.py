"""Convert, classify, and extract a single document group."""

from __future__ import annotations

from typing import Any

from .classify import Classification, LlmClassifier
from .convert import Converter
from .external_fields import resolve_external_field
from .extract import extract
from .groups import Group
from .llm_types import JsonLlm, LlmError
from .processing import Options, SourceScope
from .schema import find_class
from .source import build_source
from .store_records import SourceReference


def process_group(
    group: Group,
    *,
    converter: Converter,
    classifier: LlmClassifier | None,
    llm: JsonLlm | None,
    options: Options,
    scope: SourceScope,
    used_sources: dict[str, SourceReference],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "group": group.name,
        "mode": "classify" if options.classify_only else "extract",
        "files": group.relative_files,
        "status": "completed",
        "needs_review": False,
        "review_reasons": [],
        "class": None,
        "data": {},
        "fields": {},
        "warnings": [],
        "error": None,
    }
    reasons: list[str] = result["review_reasons"]
    warnings: list[str] = result["warnings"]

    converted = [converter.convert(path, group.relative(path)) for path in group.files]
    used_sources.update({file.name: file.source_reference for file in converted})
    for file in converted:
        warnings.extend(f"{file.name}: {note}" for note in file.notes)
        if file.error:
            warnings.append(f"{file.name}: {file.error}")
            reasons.append(f"conversion_failed:{file.name}")
    if not any(file.has_text for file in converted):
        errors = list(dict.fromkeys(file.error for file in converted if file.error))
        if len(errors) == len(converted) == 1:
            error = errors[0]
        elif errors and all(file.error for file in converted):
            error = f"no file could be converted: {'; '.join(errors)}"
        else:
            error = "no text could be extracted (a scan without OCR text?)"
        return finish_result(result, status="failed", error=error)

    requested = group.document_class or options.forced_class
    if group.no_matching_class:
        classification = Classification(None, "viewer", "Confirmed no matching class")
        document_class = None
    elif requested:
        document_class = find_class(options.classes, requested)
        if document_class is None:
            return finish_result(
                result, status="failed", error=f"unknown class '{requested}'"
            )
        source = group.classification_source if group.document_class else "--class"
        classification = Classification(document_class.name, source)
    elif classifier is None:
        return finish_result(result, status="failed", error="no classifier configured")
    else:
        try:
            classification = classifier.classify(converted, options.classes)
        except LlmError as exc:
            return finish_result(
                result, status="failed", error=f"classification failed: {exc}"
            )
        document_class = (
            find_class(options.classes, classification.name)
            if classification.name
            else None
        )
    result["class"] = classification.as_dict()
    if document_class is None:
        if classification.error:
            warnings.append(f"classification: {classification.error}")
        reasons.append("unclassified")
        return finish_result(result, status="unclassified")

    if options.classify_only or not document_class.fields:
        return finish_result(result)
    if llm is None:
        return finish_result(
            result, status="failed", error="no LLM configured for extraction"
        )

    # Each call fits its own selected pages into --max-chars.
    source_text = build_source(converted, max_chars=None)
    try:
        extraction = extract(
            llm,
            document_class,
            source_text,
            max_retries=options.retries,
            label=f"extract {group.name}",
            max_chars=options.max_chars,
            source_paths={group.relative(path): path for path in group.files},
        )
    except LlmError as exc:
        return finish_result(result, status="failed", error=f"extraction failed: {exc}")
    result["data"] = extraction.data
    result["fields"] = {name: fr.as_dict() for name, fr in extraction.fields.items()}
    reasons.extend(extraction.review_reasons)
    warnings.extend(extraction.warnings)
    try:
        for schema_field in document_class.fields:
            if schema_field.external:
                resolve_external_field(
                    result,
                    group,
                    document_class,
                    schema_field,
                    extraction.references.get(schema_field.name),
                    scope=scope,
                    used_sources=used_sources,
                    converter=converter,
                    classifier=classifier,
                    llm=llm,
                    options=options,
                )
    except LlmError as exc:
        return finish_result(result, status="failed", error=f"extraction failed: {exc}")
    return finish_result(result)


def finish_result(
    result: dict[str, Any], *, status: str | None = None, error: str | None = None
):
    if status:
        result["status"] = status
    if error:
        result["error"] = error
    result["needs_review"] = result["status"] not in {"completed", "duplicate"} or bool(
        result["review_reasons"]
    )
    return result
