"""Presentation and value validation shared by the review UI and its API."""

from __future__ import annotations

import html
import json
import math
import re
from pathlib import PurePosixPath
from typing import Any

from .schema import ChildField, SchemaField
from .values import coerce, is_empty, validation_errors

ROW_ID = "__intextum_row"
EVIDENCE_COLUMN = "__intextum_evidence"


def items_without_evidence(entry: dict[str, Any]) -> list[int]:
    """Positions of the extracted list items that have no evidence passage."""
    value = entry.get("value")
    evidence = entry.get("item_evidence")
    # A correction replaces the items the evidence was recorded for.
    if entry.get("edited") or not isinstance(value, list) or not evidence:
        return []
    if len(evidence) != len(value):
        return []
    return [index for index, items in enumerate(evidence) if not items]


def mark_missing_evidence(
    rows: list[dict[str, Any]], columns: list[dict[str, Any]], missing: list[int]
) -> None:
    """Add a sortable leading column saying which table rows lack evidence."""
    for row in rows:
        row[EVIDENCE_COLUMN] = "Missing" if row[ROW_ID] in missing else "Found"
    columns.insert(
        0,
        {
            "name": EVIDENCE_COLUMN,
            "field": EVIDENCE_COLUMN,
            "label": "Evidence",
            "align": "left",
            "sortable": True,
        },
    )


def infer_dtype(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, dict) and "amount" in value and "currency" in value:
        return "currency"
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return "date"
    return "str"


def field_spec(
    name: str, entry: dict[str, Any], schema: SchemaField | None = None
) -> SchemaField:
    """Use the extraction schema when available, otherwise infer from values."""
    if schema is not None:
        return schema
    value = entry.get("value")
    if value is None:
        value = entry.get("extracted_value")
    if isinstance(value, list):
        objects = [item for item in value if isinstance(item, dict)]
        if objects:
            names = dict.fromkeys(key for item in objects for key in item)
            children = []
            for key in names:
                sample = next(
                    (item[key] for item in objects if item.get(key) is not None), None
                )
                dtype = "list" if isinstance(sample, list) else infer_dtype(sample)
                children.append(ChildField(name=key, dtype=dtype))
            return SchemaField(name=name, dtype="object_list", fields=children)
        return SchemaField(name=name, dtype="list")
    return SchemaField(name=name, dtype=infer_dtype(value))


def _normalize(value: Any, dtype: str, enum: list[str], required: bool) -> Any:
    normalized = coerce(value, dtype)
    errors = validation_errors(normalized, dtype, enum)
    if required and is_empty(normalized):
        errors.append("missing_required")
    # JSON cannot represent NaN or infinity, including inside currency values.
    amount = normalized.get("amount") if isinstance(normalized, dict) else normalized
    if isinstance(amount, float) and not math.isfinite(amount):
        errors.append("invalid_number")
    if errors:
        raise ValueError(", ".join(errors).replace("_", " "))
    return normalized


def normalize_edit(value: Any, spec: SchemaField) -> Any:
    """Reject malformed corrections and preserve schema types on disk."""
    if spec.dtype == "object_list":
        if not isinstance(value, list) or any(not isinstance(v, dict) for v in value):
            raise ValueError("Expected a table of objects")
        if spec.required and not value:
            raise ValueError("At least one row is required")
        rows = []
        for index, item in enumerate(value, start=1):
            row = dict(item)
            for child in spec.fields:
                try:
                    row[child.name] = _normalize(
                        item.get(child.name), child.dtype, child.enum, child.required
                    )
                except ValueError as exc:
                    raise ValueError(f"Row {index}, {child.name}: {exc}") from exc
            rows.append(row)
        return rows
    if spec.dtype == "list":
        if not isinstance(value, list):
            raise ValueError("Expected a list of values")
        if spec.required and not value:
            raise ValueError("At least one value is required")
        return [_normalize(item, "str", spec.enum, True) for item in value]
    return _normalize(value, spec.dtype, spec.enum, spec.required)


def display_value(value: Any) -> str:
    if value is None or value == "":
        return "Not provided"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, dict) and isinstance(value.get("amount"), int | float):
        return f"{value['amount']:,.2f} {value.get('currency') or ''}".strip()
    return str(value)


def filtered_groups(
    entries: list[dict[str, Any]], query: str = "", scope: str = "all"
) -> list[dict[str, Any]]:
    query = query.strip().casefold()
    return [
        entry
        for entry in entries
        if (scope != "review" or entry.get("needs_review"))
        and (scope != "edited" or entry.get("edited"))
        and (scope != "failed" or entry.get("status") == "failed")
        and (scope != "reviewed" or entry.get("reviewed"))
        and (
            not query
            or query in f"{entry['group']} {entry.get('class') or ''}".casefold()
            or any(query in name.casefold() for name in entry.get("files", []))
        )
    ]


def document_rows(
    entries: list[dict[str, Any]], query: str = "", scope: str = "all"
) -> list[dict[str, Any]]:
    """List source documents directly while retaining their extraction identity."""
    rows = []
    query = query.strip().casefold()
    for entry in filtered_groups(entries, scope=scope):
        slug = entry["slug"]
        files = list(dict.fromkeys(entry.get("files") or []))
        if entry.get("status") == "failed":
            status, status_label = "failed", "Failed"
        elif entry.get("reviewed"):
            status, status_label = "complete", "Reviewed"
        elif entry.get("needs_review"):
            status, status_label = "needs-review", "Needs review"
        elif entry.get("edited"):
            status, status_label = "edited", "Edited"
        else:
            status, status_label = "complete", "Complete"
        # Failed results can have no source files; keep them reachable for review.
        for name in files or [None]:
            if query and query not in (
                f"{entry['group']} {entry.get('class') or ''} {name or ''}".casefold()
            ):
                continue
            rows.append(
                {
                    "id": json.dumps([slug, name]),
                    "label": PurePosixPath(name).name if name else entry["group"],
                    "slug": slug,
                    "file": name,
                    "group": entry["group"],
                    "classification": entry.get("class") or "Unclassified",
                    "status": status,
                    "status_label": status_label,
                    "needs_review": bool(entry.get("needs_review")),
                    "file_count": len(files),
                }
            )
    return sorted(rows, key=lambda row: (row["label"].casefold(), row["id"]))


def source_html(pages: list[str], page: int, snippet: str = "") -> str:
    """Escape document text before adding the evidence mark."""
    text = pages[page] if pages else ""
    needle = snippet.strip().split("\n", 1)[0].strip()
    position = text.find(needle) if needle else -1
    if position < 0:
        body = html.escape(text)
    else:
        end = position + len(needle)
        body = (
            html.escape(text[:position])
            + '<mark id="evidence-match">'
            + html.escape(text[position:end])
            + "</mark>"
            + html.escape(text[end:])
        )
    return f'<pre class="document-text">{body}</pre>'
