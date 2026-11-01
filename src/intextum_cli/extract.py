"""Schema-driven extraction with evidence anchors, across one or more files."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .conversion_marks import has_mark_tag
from .extraction_prompt import (
    REFERENCES_KEY,
    SYSTEM_PROMPT,
    attachment_fields,
    build_prompt,
    call_label,
    field_batches,
    response_name,
    response_schema,
)
from .llm_types import JsonLlm
from .schema import REPEATED_DTYPES, DocumentClass, SchemaField
from .source import (
    SourceText,
    fit_source,
    locate,
    locate_quotes,
    select_source_pages,
    short_anchor,
)
from .values import ambiguous_number, coerce, is_empty, validation_errors

logger = logging.getLogger(__name__)


@dataclass
class FieldResult:
    value: Any
    evidence: list[dict[str, Any]] = field(default_factory=list)
    item_evidence: list[list[dict[str, Any]]] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"value": self.value, "evidence": self.evidence}
        if self.item_evidence:
            data["item_evidence"] = self.item_evidence
        if self.validation_errors:
            data["validation_errors"] = self.validation_errors
        return data


@dataclass
class ExtractionResult:
    data: dict[str, Any]
    fields: dict[str, FieldResult]
    review_reasons: list[str]
    warnings: list[str]
    llm_calls: int
    # For fields with ``external``: the sentence saying the values are elsewhere.
    references: dict[str, dict[str, Any]] = field(default_factory=dict)


def _drop_empty_values(value: Any, empty_values: list[str]) -> Any:
    """Treat configured placeholder values (e.g. ``0``) as missing."""
    if value is None or not empty_values:
        return value
    placeholders = {item.strip().casefold() for item in empty_values}
    return None if str(value).strip().casefold() in placeholders else value


def records_from_reply(schema_field: SchemaField, raw: Any) -> list[dict[str, Any]]:
    """Turn one field of the model reply into ``[{value, anchor}]`` records."""
    if schema_field.dtype in REPEATED_DTYPES:
        items = raw if isinstance(raw, list) else [raw]
    else:
        items = [raw]
    records: list[dict[str, Any]] = []
    for item in items:
        if schema_field.dtype == "list":
            value = item.get("value") if isinstance(item, dict) else item
            nested = value if isinstance(value, list) else [value]
            for entry in nested:
                entry = _drop_empty_values(entry, schema_field.empty_values)
                if is_empty(entry):
                    continue
                text = str(entry).strip()
                records.append(
                    {"value": text, "anchor": short_anchor(text), "value_errors": []}
                )
            continue
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        anchor = item.get("evidence_anchor")
        anchor = short_anchor(anchor) if isinstance(anchor, str) else None
        if schema_field.dtype == "object_list":
            if not isinstance(value, dict):
                continue
            cleaned = {}
            value_errors = []
            for child in schema_field.fields:
                child_value = _drop_empty_values(
                    coerce(value.get(child.name), child.dtype), child.empty_values
                )
                if not is_empty(child_value):
                    cleaned[child.name] = child_value
                    if child.dtype == "float" and ambiguous_number(
                        value.get(child.name)
                    ):
                        value_errors.append(f"{child.name}:ambiguous_number")
            if cleaned:
                records.append(
                    {"value": cleaned, "anchor": anchor, "value_errors": value_errors}
                )
            continue
        cleaned_value = _drop_empty_values(
            coerce(value, schema_field.dtype), schema_field.empty_values
        )
        if not is_empty(cleaned_value):
            ambiguous = schema_field.dtype == "float" and ambiguous_number(value)
            records.append(
                {
                    "value": cleaned_value,
                    "anchor": anchor,
                    "value_errors": ["ambiguous_number"] if ambiguous else [],
                }
            )
    return records


def _ground(
    schema_field: SchemaField, records: list[dict[str, Any]], source: SourceText
):
    cursor = 0
    for record in records:
        found = locate(record["anchor"], source, start=cursor)
        record["grounded"] = found is not None
        record["evidence"] = [found[1]] if found else []
        if found and schema_field.dtype in REPEATED_DTYPES:
            cursor = found[0] + 1
        record["quote_errors"] = []
        if schema_field.dtype == "object_list":
            for child in schema_field.fields:
                quote = record["value"].get(child.name)
                if not child.verbatim or is_empty(quote):
                    continue
                matches = locate_quotes(quote, source)
                if not matches:
                    record["quote_errors"].append(f"{child.name}:not_in_source")
                    continue
                # Status notes repeat; prefer the occurrences after this item's anchor.
                if found:
                    matches.sort(key=lambda match: match[0] < found[0])
                if child.quote_for:
                    dtypes = {f.name: f.dtype for f in schema_field.fields}
                    related = [
                        match
                        for match in matches
                        if _related_quote(
                            child.quote_for,
                            dtypes,
                            record["value"],
                            quote,
                            match[0],
                            source,
                        )
                    ]
                    if not related:
                        record["quote_errors"].append(f"{child.name}:unrelated_quote")
                    matches = related or matches
                if matches[0][1] not in record["evidence"]:
                    record["evidence"].append(matches[0][1])
            # Without a located row, no_evidence already asks for review.
            if found:
                record["quote_errors"].extend(
                    _source_conflicts(schema_field, record["value"], found[0], source)
                )


def _source_conflicts(
    schema_field: SchemaField, value: dict[str, Any], position: int, source: SourceText
) -> list[str]:
    """Compare ``implied_by`` values with the entry's source row and quotes."""
    start, end = _line_bounds(position, source)
    row = source.text[start:end]
    quotes = [
        str(value[child.name])
        for child in schema_field.fields
        if child.verbatim and not is_empty(value.get(child.name))
    ]
    errors = []
    for child in schema_field.fields:
        actual = value.get(child.name)
        if is_empty(actual):
            continue
        for expected, signal in child.implied_by.items():
            signalled = has_mark_tag("\n".join([row, *quotes]), signal.marks) or (
                signal.quote is not None
                and any(re.search(signal.quote, quote) for quote in quotes)
            )
            if signalled != (str(actual).casefold() == expected):
                errors.append(f"{child.name}:conflicts_with_source")
                break
    return errors


def _line_bounds(position: int, source: SourceText) -> tuple[int, int]:
    segment = next(s for s in source.segments if s.start <= position < s.end)
    start = max(source.text.rfind("\n", segment.start, position) + 1, segment.start)
    end = source.text.find("\n", position, segment.end)
    return start, segment.end if end < 0 else end


def _shared_note_numbers(
    quote: str, position: int, line_start: int, end: int, source: SourceText
) -> str:
    """Numbers beside a table note that wraps over rows numbered one by one.

    Such a note is one deletion for all of them, also for numbered rows right below
    it where its column is empty. A note wrapping over unnumbered rows belongs to
    its first row alone.
    """

    def compact(text: str) -> str:
        return re.sub(r"[\W_]+", "", re.sub(r"\[[^\]]*\]", "", text).casefold())

    lines = source.text[line_start:end].split("\n")
    rows = [
        line.split("|")
        for line in lines[
            : next(
                (i for i, line in enumerate(lines) if not line.startswith("|")),
                len(lines),
            )
        ]
    ]
    column = source.text.count("|", line_start, position)
    if not rows or column >= len(rows[0]):
        return ""
    needle = compact(quote)
    seen = compact(source.text[position:].split("|", 1)[0].split("\n", 1)[0])
    span = 1
    while len(seen) < len(needle) and needle.startswith(seen) and span < len(rows):
        if column >= len(rows[span]):
            return ""
        seen += compact(rows[span][column])
        span += 1
    if span < 2 or seen != needle:
        return ""

    def number(cells: list[str], index: int) -> str:
        cell = cells[index] if index < len(cells) else ""
        return re.sub(r"\[[^\]]*\]", "", cell).strip()

    for index in range(len(rows[0])):
        if index != column and all(number(r, index).isdigit() for r in rows[:span]):
            numbers = [number(row, index) for row in rows[:span]]
            for row in rows[span:]:
                if number(row, column) or not number(row, index).isdigit():
                    break
                numbers.append(number(row, index))
            return " ".join(numbers)
    return ""


def _whole_token(pattern: str) -> str:
    """Match a token, but not a part of ``3.000``, ``3,000`` or ``12.07.2007``.

    A comma before fewer than three digits separates a list of numbers: ``2,3``.
    """
    return r"(?<!\w)(?<!\d\.)" + pattern + r"(?!\.\d)(?!,\d{3}(?!\d))(?!\w)"


def _identifier_pattern(text: str, dtype: str) -> str | None:
    """A pattern for a coerced identifier as source text writes it, if it is a token."""
    if dtype == "date":
        try:
            day = date.fromisoformat(text)
        except ValueError:
            pass
        else:
            return _whole_token(
                f"(?:{text}|0?{day.day}[./-]0?{day.month}[./-]"
                f"(?:{day.year}|{day.year % 100:02}))"
            )
    if text.isdigit():
        return _whole_token("0*" + (text.lstrip("0") or "0"))
    if re.fullmatch(r"[\w-]+", text):
        return _whole_token(re.escape(text))
    return None


def _related_quote(
    names: list[str],
    dtypes: dict[str, str],
    value: dict[str, Any],
    quote: str,
    position: int,
    source: SourceText,
) -> bool:
    """Require an item identifier in a quote or its immediate source-row context."""
    segment = next(s for s in source.segments if s.start <= position < s.end)
    line_start, line_end = _line_bounds(position, source)
    context = source.text[line_start:line_end]
    # A wrapped plain-text note may put its entry number on the preceding line.
    # In a Markdown table, keep the context strictly inside the matching row.
    if "|" not in context and line_start > segment.start:
        previous = source.text.rfind("\n", segment.start, line_start - 1) + 1
        context = source.text[max(previous, segment.start) : line_end]
    context = (
        quote
        + "\n"
        + context
        + "\n"
        + _shared_note_numbers(quote, position, line_start, segment.end, source)
    )
    compact = re.sub(r"[\W_]+", "", context.casefold())
    for name in names:
        identifier = value.get(name)
        if is_empty(identifier):
            continue
        text = str(identifier)
        pattern = _identifier_pattern(text, dtypes[name])
        if pattern is not None:
            if re.search(pattern, context, re.I):
                return True
        else:
            needle = re.sub(r"[\W_]+", "", text.casefold())
            if needle and needle in compact:
                return True
    return False


def _item_errors(schema_field: SchemaField, value: Any) -> list[str]:
    if schema_field.dtype == "object_list":
        errors: list[str] = []
        for child in schema_field.fields:
            child_value = value.get(child.name)
            for error in validation_errors(child_value, child.dtype, child.enum):
                errors.append(f"{child.name}:{error}")
            if child.required and is_empty(child_value):
                errors.append(f"{child.name}:missing_required")
        return errors
    dtype = "str" if schema_field.dtype == "list" else schema_field.dtype
    return validation_errors(value, dtype, schema_field.enum)


def _duplicate_errors(
    schema_field: SchemaField, records: list[dict[str, Any]]
) -> set[str]:
    errors = set()
    for child in schema_field.fields:
        if child.unique:
            values = [
                str(record["value"].get(child.name))
                for record in records
                if not is_empty(record["value"].get(child.name))
            ]
            if len(values) != len(set(values)):
                errors.add(f"{child.name}:duplicate")
    return errors


# --- orchestration ------------------------------------------------------------


def extract(
    llm: JsonLlm,
    document_class: DocumentClass,
    source: SourceText,
    *,
    max_retries: int = 1,
    context: str | None = None,
    find_references: bool = True,
    label: str = "",
    max_chars: int | None = None,
) -> ExtractionResult:
    """Extract all fields of ``document_class`` from ``source``.

    With ``max_chars``, each call's text is shortened after selecting its pages,
    so fields limited to one section can read all of that section.

    With ``find_references``, fields that have ``external`` are resolved later by
    the caller: they do not trigger retries or ``missing_required``, and the model
    reports any sentence pointing to an attachment for them.
    """
    schema_fields = document_class.fields
    deferred = (
        {f.name for f in schema_fields if f.external} if find_references else set()
    )
    references: dict[str, dict[str, Any]] = {}
    records: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    review: list[str] = []
    calls = 0
    batches = field_batches(schema_fields)
    retry_hint = None

    for attempt in range(max_retries + 1):
        for batch in batches:
            batch_source = select_source_pages(source, batch[0].source_pages_matching)
            if batch[0].source_pages_matching is not None and not batch_source.segments:
                for schema_field in batch:
                    reason = f"no_matching_source_pages:{schema_field.name}"
                    if reason not in review:
                        review.append(reason)
                continue
            if max_chars is not None:
                batch_source = fit_source(batch_source, max_chars)
            for name in batch_source.truncated_files:
                if f"source_truncated:{name}" not in review:
                    warnings.append(
                        f"{name}: text truncated to fit --max-chars {max_chars}"
                    )
                    review.append(f"source_truncated:{name}")
            calls += 1
            reference_fields = attachment_fields(batch, find_references)
            reply = llm.complete_json(
                system=SYSTEM_PROMPT,
                user=build_prompt(
                    document_class,
                    batch,
                    batch_source,
                    retry_hint,
                    context=context,
                    find_references=find_references,
                ),
                name=response_name(document_class, batch),
                schema=response_schema(batch, reference_fields),
                label=call_label(label, batch, attempt),
            )
            batch_names = ", ".join(f.name for f in batch)
            if reply.data is None:
                warnings.append(f"invalid JSON from model for fields: {batch_names}")
                if "llm_invalid_json" not in review:
                    review.append("llm_invalid_json")
                continue
            if reply.finish_reason == "length":
                warnings.append(f"model reply truncated for fields: {batch_names}")
            raw_references = reply.data.get(REFERENCES_KEY)
            for name in reference_fields:
                quote = (
                    raw_references.get(name)
                    if isinstance(raw_references, dict)
                    else None
                )
                if isinstance(quote, str) and quote.strip() and name not in references:
                    found = locate(quote.strip(), batch_source)
                    references[name] = {
                        "quote": quote.strip(),
                        "evidence": [found[1]] if found else [],
                    }
            for schema_field in batch:
                parsed = records_from_reply(
                    schema_field, reply.data.get(schema_field.name)
                )
                if parsed:
                    _ground(schema_field, parsed, batch_source)
                    records[schema_field.name] = parsed

        missing = [
            f.name
            for f in schema_fields
            if f.required and not records.get(f.name) and f.name not in deferred
        ]
        if not missing or attempt == max_retries:
            break
        logger.info("retrying for missing required fields: %s", ", ".join(missing))
        retry_hint = (
            "On the previous attempt these required fields were missing: "
            f"{', '.join(missing)}. Look again carefully; the values are likely "
            "present in the SOURCE TEXT, possibly in another file."
        )
        batches = [
            batch for batch in field_batches(schema_fields)
            if any(f.name in missing for f in batch)
        ]  # fmt: skip

    data: dict[str, Any] = {}
    results: dict[str, FieldResult] = {}
    for schema_field in schema_fields:
        field_records = records.get(schema_field.name, [])
        repeated = schema_field.dtype in REPEATED_DTYPES
        if not field_records:
            value: Any = [] if repeated else None
            data[schema_field.name] = value
            results[schema_field.name] = FieldResult(value=value)
            if schema_field.required and schema_field.name not in deferred:
                review.append(f"missing_required:{schema_field.name}")
            continue

        if repeated:
            value = [record["value"] for record in field_records]
            errors = sorted(
                {
                    e
                    for record in field_records
                    for e in (
                        _item_errors(schema_field, record["value"])
                        + record["quote_errors"]
                        + record["value_errors"]
                    )
                }
                | _duplicate_errors(schema_field, field_records)
            )
            item_evidence = [record["evidence"] for record in field_records]
            evidence = [ev for record in field_records for ev in record["evidence"]][:3]
            ungrounded = sum(1 for record in field_records if not record["grounded"])
        else:
            value = field_records[0]["value"]
            errors = (
                _item_errors(schema_field, value) + field_records[0]["value_errors"]
            )
            item_evidence = []
            evidence = field_records[0]["evidence"]
            ungrounded = 0 if field_records[0]["grounded"] else 1

        if errors:
            review.append(f"invalid:{schema_field.name}")
        if ungrounded:
            review.append(f"no_evidence:{schema_field.name}")
        data[schema_field.name] = value
        results[schema_field.name] = FieldResult(
            value=value,
            evidence=evidence,
            item_evidence=item_evidence,
            validation_errors=errors,
        )

    return ExtractionResult(
        data=data,
        fields=results,
        review_reasons=review,
        warnings=warnings,
        llm_calls=calls,
        references=references,
    )
