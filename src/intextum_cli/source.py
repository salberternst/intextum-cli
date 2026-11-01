"""Combined source text for a group of files, and locating evidence in it."""

from __future__ import annotations

import re
from bisect import bisect_left
from dataclasses import dataclass, field, replace
from itertools import pairwise

from .conversion_marks import MARK_TAGS
from .convert import ConvertedFile

FILE_HEADER = "=== FILE: {name} ==="
PAGE_HEADER = "=== PAGE: {number} ==="
_SNIPPET_CHARS = 240
_MAX_ANCHOR_WORDS = 10
_MARKUP_CHARS = frozenset("*`\\")
_MARK_TAGS = tuple(MARK_TAGS.values())


@dataclass
class Segment:
    start: int
    end: int
    file: str
    page: int | None
    source_start: int = 0
    document_key: str | None = None
    elements: list[dict] = field(default_factory=list)


@dataclass
class SourceText:
    text: str
    segments: list[Segment]
    truncated_files: list[str]
    _loose: tuple[str, list[int]] | None = field(default=None, init=False, repr=False)
    _columns: list[tuple[str, list[int]]] | None = field(
        default=None, init=False, repr=False
    )

    def loose_text(self) -> tuple[str, list[int]]:
        """Loosely normalized text plus each character's offset in ``text``."""
        if self._loose is None:
            self._loose = _loosen(self.text)
        return self._loose

    def table_columns(self) -> list[tuple[str, list[int]]]:
        """Each Markdown table column as loose text plus offsets in ``text``."""
        if self._columns is None:
            self._columns = list(_table_columns(self))
        return self._columns


def _fair_budgets(lengths: list[int], budget: int) -> list[int]:
    """Split ``budget`` so short files are kept whole and long ones share the rest."""
    allocation = [0] * len(lengths)
    remaining = budget
    order = sorted(range(len(lengths)), key=lengths.__getitem__)
    for position, index in enumerate(order):
        share = remaining // (len(order) - position)
        allocation[index] = min(lengths[index], share)
        remaining -= allocation[index]
    return allocation


def build_source(files: list[ConvertedFile], *, max_chars: int | None) -> SourceText:
    """Concatenate files under ``=== FILE: name ===`` headers, within ``max_chars``.

    Without ``max_chars`` every page is kept; ``fit_source`` can shorten the text
    later, e.g. after selecting the pages one extraction call needs.
    """
    usable = [file for file in files if file.error is None and file.text.strip()]
    lengths = [sum(len(page) for page in file.pages) for file in usable]
    budgets = lengths if max_chars is None else _fair_budgets(lengths, max_chars)

    parts: list[str] = []
    segments: list[Segment] = []
    truncated: list[str] = []
    offset = 0

    def append(text: str) -> int:
        nonlocal offset
        start = offset
        parts.append(text)
        offset += len(text)
        return start

    for file, budget in zip(usable, budgets, strict=True):
        if parts:
            append("\n\n")
        append(FILE_HEADER.format(name=file.name) + "\n")
        remaining = budget
        for page_index, page in enumerate(file.pages):
            if remaining <= 0:
                break
            if not page.strip():
                continue
            text = page[:remaining]
            remaining -= len(text)
            if page_index and segments and segments[-1].file == file.name:
                append("\n\n")
            if file.paged:
                append(PAGE_HEADER.format(number=page_index + 1) + "\n")
            start = append(text)
            segments.append(
                Segment(
                    start=start,
                    end=start + len(text),
                    file=file.name,
                    page=page_index + 1 if file.paged else None,
                    document_key=file.document_key,
                    elements=[
                        entry
                        for entry in file.elements
                        if entry["page_index"] == page_index
                    ],
                )
            )
        if budget < sum(len(page) for page in file.pages):
            truncated.append(file.name)
    return SourceText(text="".join(parts), segments=segments, truncated_files=truncated)


def _reassemble(
    pieces: list[tuple[Segment, str]], truncated_files: list[str]
) -> SourceText:
    """Join page contents under their headers, keeping each segment's references."""
    parts: list[str] = []
    segments: list[Segment] = []
    offset = 0
    previous_file = None
    for segment, content in pieces:
        header = "\n\n" if parts else ""
        if segment.file != previous_file:
            header += FILE_HEADER.format(name=segment.file) + "\n"
        if segment.page is not None:
            header += PAGE_HEADER.format(number=segment.page) + "\n"
        parts.extend((header, content))
        start = offset + len(header)
        offset = start + len(content)
        segments.append(replace(segment, start=start, end=offset))
        previous_file = segment.file
    return SourceText(
        text="".join(parts), segments=segments, truncated_files=truncated_files
    )


def select_source_pages(source: SourceText, pattern: str | None) -> SourceText:
    """Select matching pages while preserving source offsets and element references."""
    if pattern is None:
        return source
    compiled = re.compile(pattern)
    pieces = [
        (segment, content)
        for segment in source.segments
        if compiled.search(content := source.text[segment.start : segment.end])
    ]
    return _reassemble(pieces, list(source.truncated_files))


def fit_source(source: SourceText, max_chars: int) -> SourceText:
    """Shorten the text to ``max_chars``: short files stay whole, long ones share."""
    files = list(dict.fromkeys(segment.file for segment in source.segments))
    lengths = [
        sum(s.end - s.start for s in source.segments if s.file == name)
        for name in files
    ]
    if sum(lengths) <= max_chars:
        return source
    budgets = dict(zip(files, _fair_budgets(lengths, max_chars), strict=True))
    truncated = list(source.truncated_files)
    for name, length in zip(files, lengths, strict=True):
        if budgets[name] < length and name not in truncated:
            truncated.append(name)
    pieces = []
    for segment in source.segments:
        content = source.text[segment.start : segment.end][: budgets[segment.file]]
        budgets[segment.file] -= len(content)
        if content.strip():
            pieces.append((segment, content))
    return _reassemble(pieces, truncated)


def short_anchor(value: str) -> str:
    words = value.split()
    return " ".join(words[:_MAX_ANCHOR_WORDS]).strip()


def _loosen(text: str) -> tuple[str, list[int]]:
    """Lowercase, collapse whitespace, table pipes and dash runs, drop Markdown markup.

    Docling's Markdown adds ``**bold**``, backticks and ``\\_`` escapes that a
    model usually leaves out of its quotes, as it does the mark tags in wrapped text.
    """
    chars: list[str] = []
    offsets: list[int] = []
    separator = True
    divided = False
    resume = 0
    for index, char in enumerate(text):
        if index < resume or char in _MARKUP_CHARS:
            continue
        if char == "[":
            tag = next((tag for tag in _MARK_TAGS if text.startswith(tag, index)), None)
            if tag is not None:
                resume = index + len(tag)
                continue
        if char.isspace() or char == "|":
            if not separator and not divided:
                chars.append(" ")
                offsets.append(index)
                separator = True
            continue
        following = text[index + 1 : index + 2]
        if char == "-" and (not following or following.isspace() or following == "|"):
            # A hyphen before a line or cell break usually divides a word, which
            # quotes leave out: "Eigentums-\nwechsel" matches "Eigentumswechsel".
            divided = True
            continue
        divided = False
        if char == "-" and chars and chars[-1] == "-":
            # Table rules differ only in length: "|---|" matches "|------|".
            continue
        for lowered in char.lower():
            chars.append(lowered)
            offsets.append(index)
        separator = False
    return "".join(chars), offsets


def _loose_pattern(anchor: str) -> re.Pattern[str] | None:
    loose, _ = _loosen(anchor)
    loose = loose.strip()
    if not loose:
        return None
    # Control characters come from garbled escapes; let each match any character.
    parts = ["." if ord(char) < 32 else re.escape(char) for char in loose]
    return re.compile("".join(parts))


def _find(anchor: str, pattern: re.Pattern[str] | None, source: SourceText, start: int):
    position = source.text.find(anchor, start)
    if position >= 0 or pattern is None:
        return position
    loose, offsets = source.loose_text()
    match = pattern.search(loose, bisect_left(offsets, start))
    return offsets[match.start()] if match else -1


def _evidence(position: int, source: SourceText) -> dict | None:
    segment = next(
        (seg for seg in source.segments if seg.start <= position < seg.end), None
    )
    if segment is None:
        return None
    end = min(segment.end, position + _SNIPPET_CHARS)
    evidence = {
        "file": segment.file,
        "page": segment.page,
        "snippet": source.text[position:end].strip(),
    }
    relative = position - segment.start + segment.source_start
    references = list(
        dict.fromkeys(
            entry["ref"]
            for entry in segment.elements
            if entry["start"] <= relative < entry["end"]
        )
    )
    if segment.document_key and references:
        evidence.update(document_key=segment.document_key, element_refs=references)
    return evidence


def _column_views(rows: list[list[tuple[str, int]]]):
    for column in zip(*rows, strict=True):
        parts: list[str] = []
        positions: list[int] = []
        for cell, start in column:
            parts.append(cell + "\n")
            positions.extend(range(start, start + len(cell) + 1))
        loose, offsets = _loosen("".join(parts))
        yield loose, [positions[index] for index in offsets]


def _table_columns(source: SourceText):
    """Read each Markdown table column without joining separate tables or pages."""
    for segment in source.segments:
        rows: list[list[tuple[str, int]]] = []
        position = segment.start
        for line in source.text[segment.start : segment.end].splitlines(keepends=True):
            boundaries = [match.start() for match in re.finditer(r"(?<!\\)\|", line)]
            cells = (
                [
                    (line[left + 1 : right], position + left + 1)
                    for left, right in pairwise(boundaries)
                ]
                if line.strip().startswith("|") and line.strip().endswith("|")
                else []
            )
            if rows and (not cells or len(cells) != len(rows[0])):
                yield from _column_views(rows)
                rows = []
            if cells and not all(
                re.fullmatch(r"\s*:?-+:?\s*", cell) for cell, _ in cells
            ):
                rows.append(cells)
            position += len(line)
        if rows:
            yield from _column_views(rows)


def locate_quotes(anchor: str, source: SourceText) -> list[tuple[int, dict]]:
    """Every occurrence of a verbatim quote, in order, also down one table column."""
    pattern = _loose_pattern(anchor)
    if pattern is None:
        return []
    positions = sorted(
        {
            offsets[match.start()]
            for text, offsets in (source.loose_text(), *source.table_columns())
            for match in pattern.finditer(text)
        }
    )
    found = ((position, _evidence(position, source)) for position in positions)
    return [(position, evidence) for position, evidence in found if evidence]


def locate(
    anchor: str | None, source: SourceText, start: int = 0
) -> tuple[int, dict] | None:
    """Locate an anchor inside file content and return ``(offset, evidence)``.

    Tries an exact match first, then ignores case, whitespace and table pipes.
    Matches inside ``=== FILE ===`` header lines are skipped. Searching begins at
    ``start`` (keeps repeated items in document order) and falls back to the
    beginning of the text.
    """
    if not anchor or not anchor.strip():
        return None
    anchor = anchor.strip()
    pattern = _loose_pattern(anchor)
    for begin in dict.fromkeys((start, 0)):
        cursor = begin
        while (position := _find(anchor, pattern, source, cursor)) >= 0:
            evidence = _evidence(position, source)
            if evidence is not None:
                return position, evidence
            cursor = position + 1
    return None
