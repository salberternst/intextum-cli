"""Docling representations and mappings between source text and elements."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def normalized(text: str) -> tuple[str, list[int]]:
    # Match the same markup/whitespace rules used to ground model evidence.
    from .source import _loosen

    return _loosen(text)


_TABLE_CELL_BREAK = re.compile(r"(?<!\\)\|")
_SEPARATOR_CELL = re.compile(r"\s*(:?)-+(:?)\s*")


def compact_tables(markdown: str) -> str:
    """Drop the alignment padding of Markdown tables; cell text stays unchanged.

    Docling pads every cell to its column width, which can make up most of a
    scanned register's text and of its share of ``--max-chars``.
    """
    lines = []
    for line in markdown.split("\n"):
        stripped = line.strip()
        if len(stripped) > 1 and stripped[0] == "|" and stripped[-1] == "|":
            cells = _TABLE_CELL_BREAK.split(stripped[1:-1])
            separators = [_SEPARATOR_CELL.fullmatch(cell) for cell in cells]
            if all(separators):
                cells = [f"{m.group(1)}---{m.group(2)}" for m in separators]
            else:
                cells = [cell.strip() for cell in cells]
            line = "| " + " | ".join(cells) + " |"
        lines.append(line)
    return "\n".join(lines)


def extraction_layers() -> set:
    """Page text the model reads: the body plus headers and footers."""
    from docling_core.types.doc import ContentLayer

    return {ContentLayer.BODY, ContentLayer.FURNITURE}


def element_index(document, pages: list[str], paged: bool) -> list[dict[str, Any]]:
    """Map serialization parts back to the existing, unchanged source text."""
    from docling_core.transforms.serializer.markdown import (
        MarkdownDocSerializer,
        MarkdownParams,
    )

    serializer = MarkdownDocSerializer(
        doc=document,
        params=MarkdownParams(
            escape_html=False,
            escape_underscores=False,
            traverse_pictures=True,
            layers=extraction_layers(),
        ),
    )
    source = [normalized(page) for page in pages]
    cursors = [0] * len(pages)
    indexed: list[dict[str, Any]] = []
    for part in serializer.get_parts():
        needle, _ = normalized(part.text)
        needle = needle.strip()
        if not needle:
            continue
        items = part.get_unique_doc_items()
        page_numbers = {p.page_no for item in items for p in item.prov}
        candidates = [
            i
            for i in range(len(pages))
            if not paged or not page_numbers or i + 1 in page_numbers
        ]
        for index in candidates:
            haystack, offsets = source[index]
            start = haystack.find(needle, cursors[index])
            if start < 0:
                continue
            end = start + len(needle)
            cursors[index] = end
            for item in items:
                indexed.append(
                    {
                        "ref": item.self_ref,
                        "page": index + 1 if paged else None,
                        "page_index": index,
                        "start": offsets[start],
                        "end": offsets[end - 1] + 1,
                    }
                )
            break
    return indexed


def synthetic_document(name: str, pages: list[str], *, tables: bool = False):
    """Represent direct/fallback readers without loading OCR or conversion models."""
    from docling_core.types.doc import (
        DocItemLabel,
        DoclingDocument,
        TableCell,
        TableData,
    )

    document = DoclingDocument(name=Path(name).stem or "Document")
    for page in pages:
        lines = page.splitlines()
        if tables and len(lines) > 1 and lines[0].startswith("|"):
            rows = [
                [cell.strip() for cell in line.strip().strip("|").split("|")]
                for line in lines
                if line.startswith("|") and not re.fullmatch(r"[|:\- ]+", line)
            ]
            width = max((len(row) for row in rows), default=0)
            cells = [
                TableCell(
                    text=value,
                    column_header=row_index == 0,
                    start_row_offset_idx=row_index,
                    end_row_offset_idx=row_index + 1,
                    start_col_offset_idx=column,
                    end_col_offset_idx=column + 1,
                )
                for row_index, row in enumerate(rows)
                for column, value in enumerate(row + [""] * (width - len(row)))
            ]
            document.add_table(
                data=TableData(num_rows=len(rows), num_cols=width, table_cells=cells)
            )
        else:
            for paragraph in re.split(r"\n\s*\n", page):
                if paragraph.strip():
                    document.add_text(label=DocItemLabel.TEXT, text=paragraph.strip())
    return document


def resolve_evidence(
    manifest: dict[str, Any], evidence: dict[str, Any]
) -> tuple[list[str], str | None]:
    """Only resolve a unique source occurrence; never guess among repeated quotes."""
    elements = manifest.get("elements", [])
    key = manifest["key"]
    references = evidence.get("element_refs") or []
    if evidence.get("document_key") == key and references:
        known = {entry["ref"] for entry in elements}
        found = [ref for ref in references if ref in known]
        if found:
            return list(dict.fromkeys(found)), None
    snippet = evidence.get("snippet", "")
    if not isinstance(snippet, str) or not snippet.strip():
        return [], "This evidence has no source quote."
    page_number = evidence.get("page")
    needles = [snippet.strip(), snippet.strip().split("\n", 1)[0]]
    for needle in dict.fromkeys(needles):
        pattern, _ = normalized(needle)
        pattern = pattern.strip()
        if not pattern:
            continue
        occurrences: list[tuple[int, int]] = []
        for page_index, text in enumerate(manifest.get("pages", [])):
            if page_number and manifest.get("paged") and page_number != page_index + 1:
                continue
            haystack, offsets = normalized(text)
            position = 0
            while (position := haystack.find(pattern, position)) >= 0:
                occurrences.append((page_index, offsets[position]))
                position += len(pattern)
        if len(occurrences) != 1:
            continue
        page_index, offset = occurrences[0]
        matches = [
            entry
            for entry in elements
            if entry["page_index"] == page_index
            and entry["start"] <= offset < entry["end"]
        ]
        if matches:
            return list(dict.fromkeys(entry["ref"] for entry in matches)), None
    return (
        [],
        "The source quote could not be mapped uniquely. "
        "Source text is still available.",
    )
