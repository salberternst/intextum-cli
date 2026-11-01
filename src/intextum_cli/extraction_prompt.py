"""Extraction prompts, field batches, and structured response schemas."""

from __future__ import annotations

import json
import re
from typing import Any

from .schema import REPEATED_DTYPES, DocumentClass, SchemaField
from .source import SourceText, short_anchor
from .values import is_empty

_NAME_RE = re.compile(r"[^A-Za-z0-9_-]+")
REFERENCES_KEY = "__attachment_references"
# Without this, a model tends to return nothing when the source looks different from
# the examples (e.g. items in a table instead of running text).
EXAMPLES_NOTE = (
    "The examples show the output format only. The SOURCE TEXT may present values "
    "differently, for example as a table or list, and may lack some child values. "
    "Extract every entry that matches the field description and leave child values "
    "null when the source does not contain them."
)

SYSTEM_PROMPT = (
    "You are a structured-extraction assistant. You read source documents and "
    "return JSON with every value asked for, plus a short verbatim anchor from the "
    "source that locates the value. You never invent values. Anchors are short (at "
    "most ten words) and copied character-for-character from the source."
)


def field_batches(fields: list[SchemaField]) -> list[list[SchemaField]]:
    """Scalars share one call; each repeated field gets its own output budget."""
    scalars: dict[str | None, list[SchemaField]] = {}
    for schema_field in fields:
        if schema_field.dtype not in REPEATED_DTYPES:
            scalars.setdefault(schema_field.source_pages_matching, []).append(
                schema_field
            )
    repeated = [[f] for f in fields if f.dtype in REPEATED_DTYPES]
    return list(scalars.values()) + repeated


def _render_field(schema_field: SchemaField) -> str:
    lines = [
        f'- field_name: "{schema_field.name}"',
        f"  type: {schema_field.dtype}",
        f"  required: {str(schema_field.required).lower()}",
        f"  description: {schema_field.description}",
    ]
    if schema_field.enum:
        lines.append(f"  allowed_values: {', '.join(schema_field.enum)}")
    if schema_field.external:
        lines.append("  may_be_in_separate_file: true")
    if schema_field.dtype == "object_list":
        lines.append("  child_fields:")
        for child in schema_field.fields:
            line = f"    - {child.name} ({child.dtype}): {child.description}"
            if child.enum:
                line += f" [allowed_values: {', '.join(child.enum)}]"
            if child.required:
                line += " [required]"
            if child.verbatim:
                line += (
                    " [verbatim source quote; never paraphrase; null if unavailable]"
                )
            if child.quote_for:
                line += (
                    f" [quote must refer to this item's {' or '.join(child.quote_for)}]"
                )
            lines.append(line)
    return "\n".join(lines)


def _render_examples(document_class: DocumentClass, batch: list[SchemaField]) -> str:
    """Per-field examples plus scenes, limited to the fields in this call."""
    blocks = []
    for schema_field in batch:
        for example in schema_field.examples:
            if is_empty(example.value):
                continue
            anchor_source = example.extraction_text or (
                "" if isinstance(example.value, dict) else str(example.value)
            )
            entry = {
                "field": schema_field.name,
                "value": example.value,
                "evidence_anchor": short_anchor(anchor_source),
                "source_excerpt": example.text,
            }
            blocks.append(json.dumps(entry, ensure_ascii=False, indent=2))
    batch_names = {schema_field.name for schema_field in batch}
    for scene in document_class.scenes:
        extractions = [
            {
                "field": extraction.field,
                "value": extraction.value,
                "evidence_anchor": short_anchor(extraction.extraction_text),
            }
            for extraction in scene.extractions
            if extraction.field in batch_names and not is_empty(extraction.value)
        ]
        if extractions:
            entry = {"source_excerpt": scene.text, "extractions": extractions}
            blocks.append(json.dumps(entry, ensure_ascii=False, indent=2))
    return "\n\n---\n\n".join(blocks)


def attachment_fields(batch: list[SchemaField], find_references: bool) -> list[str]:
    return [f.name for f in batch if f.external] if find_references else []


def _expected_shape(batch: list[SchemaField], reference_fields: list[str]) -> str:
    parts = []
    for schema_field in batch:
        if schema_field.dtype == "object_list":
            children = ", ".join(
                f'"{child.name}": <{child.dtype} or null>'
                for child in schema_field.fields
            )
            parts.append(
                f'  "{schema_field.name}": [ {{"value": {{{children}}}, '
                '"evidence_anchor": "<short verbatim prefix>"}, ... ]'
            )
        elif schema_field.dtype == "list":
            parts.append(
                f'  "{schema_field.name}": [ "<one verbatim list item>", ... ]'
            )
        else:
            parts.append(
                f'  "{schema_field.name}": {{"value": <{schema_field.dtype} or null>, '
                '"evidence_anchor": "<short verbatim prefix or null>"}'
            )
    if reference_fields:
        inner = ", ".join(
            f'"{name}": "<sentence or null>"' for name in reference_fields
        )
        parts.append(f'  "{REFERENCES_KEY}": {{{inner}}}')
    return "{\n" + ",\n".join(parts) + "\n}"


def build_prompt(
    document_class: DocumentClass,
    batch: list[SchemaField],
    source: SourceText,
    retry_hint: str | None = None,
    *,
    context: str | None = None,
    find_references: bool = True,
) -> str:
    reference_fields = attachment_fields(batch, find_references)
    file_names = list(dict.fromkeys(segment.file for segment in source.segments))
    parts = [
        f"DOCUMENT CLASS: {document_class.name}",
    ]
    if document_class.description:
        parts.append(f"CLASS DESCRIPTION: {document_class.description}")
    parts += [
        f"FILES: {', '.join(file_names)}",
        "",
        "FIELDS:",
        "\n\n".join(_render_field(schema_field) for schema_field in batch),
    ]
    examples = _render_examples(document_class, batch)
    if examples:
        parts += ["", "EXAMPLES:", examples, "", EXAMPLES_NOTE]
    parts += [
        "",
        "INSTRUCTIONS:",
        "1. The SOURCE TEXT contains one or more files that belong together. Each "
        "file starts with a line '=== FILE: <name> ==='. Use information from all "
        "files; a value may come from any of them. PDF pages are labelled "
        "'=== PAGE: <number> ==='. These labels are not source evidence.",
        '2. For each scalar field return {"value": ..., "evidence_anchor": "..."}. '
        'If absent return {"value": null, "evidence_anchor": null}.',
        "3. For each object_list field return an array of "
        '{"value": {...}, "evidence_anchor": "..."}, one per item, in source order. '
        "Include every child key; use null for missing child values. If absent "
        "return [].",
        "4. For each plain list field return an array of strings, each one complete "
        "verbatim list item. If absent return [].",
        "5. evidence_anchor MUST be a verbatim substring of the file content (never "
        "the '=== FILE' line), at most ten words: the shortest unique prefix of the "
        "text the value comes from. Do not paraphrase. For a table row, use the "
        "text of its most distinctive cell. Identify the item itself, not a later "
        "change or status note; quoted child fields have their own source checks.",
        '6. Dates as YYYY-MM-DD. Currency as {"amount": number, "currency": '
        "ISO code or null}. Numbers without thousands separators.",
        "7. Do not invent placeholders such as N/A or unknown; use null.",
        "8. Only extract values that match the field description. For list fields "
        "take entries only from the matching section or table.",
        "9. Write every character as it appears in the source, including umlauts "
        "and accents (ä, ö, ü, ß, é). Never use \\u escape sequences.",
        "10. Return compact JSON only, no explanations or markdown.",
    ]
    if reference_fields:
        parts.append(
            f"11. Fields marked may_be_in_separate_file can be listed in an attachment "
            f"instead of the document itself. In {REFERENCES_KEY}, give for each such "
            "field the verbatim sentence (at most 25 words) saying its values are in "
            "an attachment, annex, table or separate list, e.g. 'siehe Tabelle im "
            "Anhang (Anlage 1)'. Use null if the document says nothing like that."
        )
    parts += [
        "",
        "EXPECTED JSON SHAPE:",
        _expected_shape(batch, reference_fields),
    ]
    if document_class.instructions:
        parts += ["", "CLASS INSTRUCTIONS:", document_class.instructions]
    if context:
        parts += ["", "CONTEXT:", context]
    if retry_hint:
        parts += ["", "RETRY NOTE:", retry_hint]
    parts += ["", "SOURCE TEXT:", source.text, "", "Respond with a single JSON object."]
    return "\n".join(parts)


def _strict_object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _value_schema(dtype: str, enum: list[str]) -> dict[str, Any]:
    if dtype in {"str", "date"}:
        schema: dict[str, Any] = {"type": ["string", "null"]}
        if enum:
            schema["enum"] = [*enum, None]
        return schema
    if dtype == "list":
        items: dict[str, Any] = {"type": "string"}
        if enum:
            items["enum"] = list(enum)
        return {"type": ["array", "null"], "items": items}
    if dtype == "currency":
        currency = _strict_object(
            {
                "amount": {"type": ["number", "null"]},
                "currency": {"type": ["string", "null"]},
            }
        )
        return {**currency, "type": ["object", "null"]}
    json_type = {"int": "integer", "float": "number", "bool": "boolean"}[dtype]
    return {"type": [json_type, "null"]}


def _field_schema(schema_field: SchemaField) -> dict[str, Any]:
    anchor = {"type": ["string", "null"]}
    if schema_field.dtype == "list":
        items: dict[str, Any] = {"type": "string"}
        if schema_field.enum:
            items["enum"] = list(schema_field.enum)
        return {"type": "array", "items": items}
    if schema_field.dtype == "object_list":
        children = {
            child.name: _value_schema(child.dtype, child.enum)
            for child in schema_field.fields
        }
        return {
            "type": "array",
            "items": _strict_object(
                {"value": _strict_object(children), "evidence_anchor": anchor}
            ),
        }
    return _strict_object(
        {
            "value": _value_schema(schema_field.dtype, schema_field.enum),
            "evidence_anchor": anchor,
        }
    )


def response_schema(
    batch: list[SchemaField], reference_fields: list[str] | None = None
) -> dict[str, Any]:
    properties = {f.name: _field_schema(f) for f in batch}
    if reference_fields:
        properties[REFERENCES_KEY] = _strict_object(
            {name: {"type": ["string", "null"]} for name in reference_fields}
        )
    return _strict_object(properties)


def call_label(label: str, batch: list[SchemaField], attempt: int) -> str:
    names = [f.name for f in batch]
    shown = names[0] if len(names) == 1 else f"{names[0]} +{len(names) - 1} fields"
    retry = f" retry {attempt}" if attempt else ""
    return f"{label or 'extract'} [{shown}]{retry}"


def response_name(document_class: DocumentClass, batch: list[SchemaField]) -> str:
    raw = "_".join([document_class.name, *(f.name for f in batch)])
    return (_NAME_RE.sub("_", raw).strip("_") or "extraction")[:60]
