"""Select external attachments and extract the fields they supply."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .classify import LlmClassifier
from .convert import Converter
from .extract import FieldResult, extract
from .groups import Group
from .llm_types import JsonLlm
from .processing import Options, SourceScope
from .schema import REPEATED_DTYPES, DocumentClass, SchemaField, find_class
from .source import build_source
from .sources import MIN_SCORE, SOURCES_FILE, Candidate, is_uncertain, rank_candidates
from .store_records import SourceReference
from .values import is_empty


def resolve_external_field(
    result: dict[str, Any],
    group: Group,
    document_class: DocumentClass,
    schema_field: SchemaField,
    reference: dict[str, Any] | None,
    *,
    scope: SourceScope,
    converter: Converter,
    classifier: LlmClassifier | None,
    llm: JsonLlm,
    options: Options,
    used_sources: dict[str, SourceReference],
) -> None:
    """Take a field's values from a separate file when the schema allows it."""
    name = schema_field.name
    spec = schema_field.external
    document_value = result["data"].get(name)
    entry = result["fields"].setdefault(name, {"value": document_value, "evidence": []})
    if reference:
        entry["attachment_reference"] = reference

    overrides = options.overrides.get(group.name, {})
    runner_up = None
    if name in overrides:
        files = overrides[name]
        if files is None:
            entry["source"] = {"file": None, "set_in": SOURCES_FILE}
            if schema_field.required and is_empty(document_value):
                _flag(result, f"missing_required:{name}")
            return
        chosen = files
        source: dict[str, Any] = {
            "files": [scope.rel(path) for path in files],
            "set_in": SOURCES_FILE,
        }
    else:
        needed = (
            spec.when == "always"
            or is_empty(document_value)
            or (spec.when == "auto" and reference is not None)
        )
        if not needed:
            return
        ranked = _rank_attachments(
            result,
            group,
            document_class,
            schema_field,
            reference,
            scope,
            converter,
            classifier,
            options,
        )
        top = [_candidate_info(candidate, scope) for candidate in ranked[:3]]
        if not ranked or ranked[0].score < MIN_SCORE:
            entry["source"] = {"file": None, "candidates": top}
            _flag(result, f"external_source_not_found:{name}")
            if schema_field.required and is_empty(document_value):
                _flag(result, f"missing_required:{name}")
            return
        chosen = [ranked[0].path]
        source = _candidate_info(ranked[0], scope)
        source["files"] = [source.pop("file")]
        runner_up = top[1] if len(top) > 1 else None
        if is_uncertain(ranked):
            _flag(result, f"external_source_uncertain:{name}")

    extracted = _extract_selected_files(
        result,
        group,
        document_class,
        schema_field,
        reference,
        chosen,
        scope=scope,
        converter=converter,
        llm=llm,
        options=options,
        used_sources=used_sources,
    )
    if runner_up:
        source["runner_up"] = runner_up
    result["data"][name] = extracted.value
    new_entry = extracted.as_dict()
    new_entry["source"] = source
    if reference:
        new_entry["attachment_reference"] = reference
    if not is_empty(document_value):
        new_entry["document_value"] = document_value
    result["fields"][name] = new_entry
    if schema_field.required and is_empty(extracted.value):
        _flag(result, f"missing_required:{name}")


def _candidate_info(candidate: Candidate, scope: SourceScope) -> dict[str, Any]:
    return {
        "file": scope.rel(candidate.path),
        "score": candidate.score,
        "reasons": candidate.reasons,
    }


def _flag(result: dict, reason: str) -> None:
    reasons = result["review_reasons"]
    if reason not in reasons:
        reasons.append(reason)


def _rank_attachments(
    result: dict,
    group: Group,
    document_class: DocumentClass,
    schema_field: SchemaField,
    reference: dict | None,
    scope: SourceScope,
    converter: Converter,
    classifier: LlmClassifier | None,
    options: Options,
) -> list[Candidate]:
    texts, classes_of = {}, {}
    spec = schema_field.external
    assert spec is not None
    allowed = {find_class(options.classes, c).name for c in spec.classes}
    for path in scope.neighbours(group):
        converted = converter.convert(path, scope.rel(path))
        if not converted.has_text:
            continue
        candidate_class = None
        if classifier is not None:
            label = classifier.classify([converted], options.classes).name
            candidate_class = find_class(options.classes, label) if label else None
        label = candidate_class.name if candidate_class else None
        if label == document_class.name or (allowed and label not in allowed):
            continue
        texts[path], classes_of[path] = converted.text, candidate_class
    main_text = "\n\n".join(
        converter.convert(path, scope.rel(path)).text for path in group.files
    )
    return rank_candidates(
        scope.root,
        group.files[0],
        main_text,
        result["data"],
        schema_field.name,
        (reference or {}).get("quote"),
        texts,
        classes_of,
    )


def _attachment_context(
    result: dict,
    group: Group,
    document_class: DocumentClass,
    schema_field: SchemaField,
    reference: dict | None,
    scope: SourceScope,
) -> str:
    name = schema_field.name
    main_rel = scope.rel(group.files[0])
    known = {k: v for k, v in result["data"].items() if k != name and not is_empty(v)}
    # Tell the model plainly that this file belongs to the document: a table with
    # unrelated captions otherwise tends to yield nothing.
    context = (
        f"This file is the attachment of the document '{main_rel}' "
        f"({document_class.name}) that lists the values of '{name}'."
    )
    if reference:
        context += f' The document itself says: "{reference["quote"]}".'
    context += (
        " Every entry in this file that fits the field is part of that document; "
        "extract all of them, even if tables or sections have other captions. "
        "Leave child values null when this file does not contain them. "
        "Values already extracted from the document: "
        + json.dumps(known, ensure_ascii=False, default=str)[:2000]
    )
    return context


def _extract_selected_files(
    result: dict,
    group: Group,
    document_class: DocumentClass,
    schema_field: SchemaField,
    reference: dict | None,
    chosen: list[Path],
    *,
    scope: SourceScope,
    converter: Converter,
    llm: JsonLlm,
    options: Options,
    used_sources: dict[str, SourceReference],
) -> FieldResult:
    name = schema_field.name
    repeated = schema_field.dtype in REPEATED_DTYPES
    value: Any = [] if repeated else None
    evidence: list[dict[str, Any]] = []
    item_evidence: list[list[dict[str, Any]]] = []
    errors: list[str] = []
    context = _attachment_context(
        result, group, document_class, schema_field, reference, scope
    )
    single_field = document_class.model_copy(update={"fields": [schema_field]})
    for path in chosen:
        converted = converter.convert(path, scope.rel(path))
        captured = converted.source_reference
        earlier = used_sources.get(converted.name)
        if earlier is not None and earlier != captured:
            _flag(result, f"conversion_failed:{converted.name}")
            result["warnings"].append(
                f"{converted.name}: source changed during extraction"
            )
            continue
        used_sources[converted.name] = captured
        result["warnings"].extend(
            f"{converted.name}: {note}" for note in converted.notes
        )
        if converted.error:
            result["warnings"].append(f"{converted.name}: {converted.error}")
            _flag(result, f"conversion_failed:{converted.name}")
            continue
        sub = extract(
            llm,
            single_field,
            # Each call fits its own selected pages into --max-chars.
            build_source([converted], max_chars=None),
            max_retries=options.retries,
            context=context,
            find_references=False,
            label=f"source {group.name} ← {scope.rel(path)}",
            max_chars=options.max_chars,
        )
        result["warnings"].extend(sub.warnings)
        field_result = sub.fields[name]
        if repeated:
            value.extend(field_result.value or [])
            item_evidence.extend(field_result.item_evidence)
        elif is_empty(value):
            value = field_result.value
        evidence.extend(field_result.evidence)
        errors.extend(e for e in field_result.validation_errors if e not in errors)
        for reason in sub.review_reasons:
            if not reason.startswith("missing_required:"):
                _flag(result, reason)

    return FieldResult(value, evidence[:3], item_evidence, errors)
