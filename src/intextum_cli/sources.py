"""Find the separate file that holds a field's values (e.g. a table of items).

For a field with ``external`` in the schema, every other file in the document's
scope is a candidate (optionally only files of ``external.classes``). Candidates
are ranked by, in order of weight:

- values already extracted from the document that also appear in the file
  (amounts, dates, names; numbers compared across ``753,24`` / ``753.24``),
- shared identifiers in the full texts (reference numbers like ``205/1``, dates),
- how close the files' modification dates are,
- shared words in the file names, ignoring words most files in the scope share,
- whether the kind of file (table, map) matches what the document refers to,
- attachment words in the file name ("Anlage", "Anhang", …) and the same folder,

minus penalties when only one of the two is archived or only one is a draft. The
best candidate is used; ``sources.yaml`` in the input folder can override it.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from .schema import DocumentClass

SOURCES_FILE = "sources.yaml"

WEIGHTS = {
    "values": 0.3,
    "ids": 0.2,
    "date": 0.15,
    "name": 0.15,
    "kind": 0.1,
    "attach_name": 0.05,
    "folder": 0.05,
}
ARCHIVE_PENALTY = 0.2
DRAFT_MISMATCH_PENALTY = 0.1
DATE_WINDOW_DAYS = 365
MIN_SCORE = 0.35  # below: no source is used
# Flag for review when the best score is below this, or the runner-up is close.
CONFIDENT_SCORE = 0.4
MIN_MARGIN = 0.15

_MAP_RE = re.compile(r"luftbild|karte|lageplan|übersichtsplan|\bplan\b|\bmap\b", re.I)
_TABLE_RE = re.compile(
    r"tabelle|liste|aufstellung|verzeichnis|\btable\b|\blist\b|spreadsheet", re.I
)
_ATTACH_NAME_RE = re.compile(r"anlage|anhang|beilage|attachment|annex", re.I)
_DRAFT_RE = re.compile(r"entwurf|draft|überarb", re.I)
_ARCHIVE_PARTS = frozenset({"archiv", "archive", "alt", "old", "backup"})
_TABLE_SUFFIXES = frozenset({".xls", ".xlsx", ".xlsm", ".csv", ".ods"})
_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"})

_REFERENCE_RE = re.compile(r"(?<![\d/.,])\d{1,5}/\d{1,4}(?![\d/])")
_DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_NUMBER_RE = re.compile(r"(?<![\d/])\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?(?![\d/])|\d+")
_NAME_TOKEN_RE = re.compile(r"[a-zäöüß]{3,}|\d{2,}", re.I)
_WORD_RE = re.compile(r"[a-zäöüß]{4,}", re.I)
_NAME_STOPWORDS = frozenset(
    "pdf doc docx xls xlsx vertrag vertrags contract anschreiben letter entwurf draft "
    "anlage anlagen gez unterschrieben und für mit der die das von neu alt kopie "
    "version automatisch gespeichert".split()
)


class SourcesError(ValueError):
    """Raised when ``sources.yaml`` is invalid."""


@dataclass
class Candidate:
    path: Path
    score: float
    reasons: list[str]


# --- normalisation ------------------------------------------------------------


def canonical_number(token: str) -> str | None:
    """Normalise numbers: ``753,24`` and ``753.24`` → ``753.24``, ``60,00`` → ``60``."""
    token = token.strip()
    last_comma, last_dot = token.rfind(","), token.rfind(".")
    if last_comma > last_dot:
        decimals = token[last_comma + 1 :]
        cleaned = token.replace(".", "").replace(",", ".")
        if len(decimals) == 3 and last_dot < 0 and token.count(",") > 1:
            cleaned = token.replace(",", "")
    elif last_dot > last_comma:
        decimals = token[last_dot + 1 :]
        cleaned = token.replace(",", "")
        # 12.554 with one dot and three decimals is ambiguous; treat as thousands
        # only if there are several groups (1.234.567).
        if token.count(".") > 1:
            cleaned = cleaned.replace(".", "")
    else:
        cleaned = token
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return None
    normalized = format(number.normalize(), "f")
    return normalized


def _number_tokens(text: str) -> set[str]:
    numbers = set()
    for match in _NUMBER_RE.finditer(text):
        raw = match.group(0)
        if len(raw.replace(".", "").replace(",", "")) < 2:
            continue
        canonical = canonical_number(raw)
        if canonical and canonical not in {"0", "1"}:
            numbers.add(canonical)
    return numbers


def identifiers(text: str) -> frozenset[str]:
    """Reference numbers (``205/1``), ISO dates, and decimals or 5+ digit numbers."""
    found: set[str] = set(_REFERENCE_RE.findall(text))
    for day, month, year in _DATE_RE.findall(text):
        found.add(f"{year}-{int(month):02d}-{int(day):02d}")
    for year, month, day in _ISO_DATE_RE.findall(text):
        found.add(f"{year}-{month}-{day}")
    for number in _number_tokens(text):
        if "." in number or len(number) >= 5:
            found.add(number)
    return frozenset(found)


def _value_tokens(data: dict[str, Any], skip: set[str]) -> set[str]:
    """Distinctive values extracted from the document, normalised for matching."""
    tokens: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, int | float):
            number = canonical_number(str(value))
            if number and len(number.replace(".", "")) >= 3:
                tokens.add(number)
        elif isinstance(value, date | datetime):
            tokens.add(value.isoformat()[:10])
        elif isinstance(value, str):
            text = value.strip()
            if _ISO_DATE_RE.fullmatch(text):
                tokens.add(text)
            elif re.fullmatch(r"[\d.,]+", text):
                number = canonical_number(text)
                if number and len(number.replace(".", "")) >= 3:
                    tokens.add(number)
            else:
                tokens.update(word.casefold() for word in _WORD_RE.findall(text))
        elif isinstance(value, dict):
            for inner in value.values():
                add(inner)
        elif isinstance(value, list):
            for inner in value:
                add(inner)

    for name, value in data.items():
        if name not in skip:
            add(value)
    return tokens


def _text_tokens(text: str) -> set[str]:
    return (
        {word.casefold() for word in _WORD_RE.findall(text)}
        | identifiers(text)
        | _number_tokens(text)
    )


def _name_tokens(path: Path) -> set[str]:
    stem = path.name.rsplit(".", 1)[0]
    return {
        token.lower()
        for token in _NAME_TOKEN_RE.findall(stem)
        if token.lower() not in _NAME_STOPWORDS
    }


def _kind(path: Path, document_class: DocumentClass | None) -> str | None:
    if document_class is not None:
        text = " ".join(
            [document_class.name, document_class.description, *document_class.aliases]
        )
        if _MAP_RE.search(text):
            return "map"
        if _TABLE_RE.search(text):
            return "table"
    suffix = path.suffix.lower()
    if suffix in _TABLE_SUFFIXES:
        return "table"
    if suffix in _IMAGE_SUFFIXES:
        return "map"
    return None


def _in_archive(path: Path, root: Path) -> bool:
    parts = {part.casefold() for part in path.relative_to(root).parts[:-1]}
    return bool(parts & _ARCHIVE_PARTS)


# --- ranking ------------------------------------------------------------------


def rank_candidates(
    root: Path,
    main_path: Path,
    main_text: str,
    main_data: dict[str, Any],
    field_name: str,
    reference: str | None,
    candidates: dict[Path, str],
    candidate_classes: dict[Path, DocumentClass | None],
) -> list[Candidate]:
    """Score every candidate file as the source of ``field_name``; best first."""
    if not candidates:
        return []
    main_ids = identifiers(main_text)
    wanted_kinds = set()
    for text in filter(None, [reference, main_text if not reference else None]):
        if _MAP_RE.search(text):
            wanted_kinds.add("map")
        if _TABLE_RE.search(text):
            wanted_kinds.add("table")

    candidate_tokens = {path: _text_tokens(text) for path, text in candidates.items()}
    values = _value_tokens(main_data, skip={field_name})
    if len(candidates) > 1:
        # A value found in every candidate says nothing about which one fits.
        values = {
            value
            for value in values
            if not all(value in tokens for tokens in candidate_tokens.values())
        }

    names = {path: _name_tokens(path) for path in [main_path, *candidates]}
    counts = Counter(token for tokens in names.values() for token in tokens)
    common = {t for t, n in counts.items() if len(names) >= 3 and n / len(names) >= 0.5}
    main_names = names[main_path] - common
    main_mtime = main_path.stat().st_mtime
    main_draft = bool(_DRAFT_RE.search(main_path.name))
    main_archived = _in_archive(main_path, root)

    ranked = []
    for path, text in candidates.items():
        reasons: list[str] = []
        tokens = candidate_tokens[path]

        found_values = sorted(values & tokens)
        value_score = min(1.0, len(found_values) / 3)
        if found_values:
            reasons.append(f"contains {', '.join(found_values[:4])}")

        shared_ids = sorted((main_ids & identifiers(text)) - set(found_values))
        id_score = min(1.0, len(shared_ids) / 3)
        if shared_ids:
            reasons.append(f"shares {', '.join(shared_ids[:4])}")

        days = abs(main_mtime - path.stat().st_mtime) / 86_400
        date_score = max(0.0, 1 - days / DATE_WINDOW_DAYS)
        if date_score >= 0.9:
            reasons.append(f"saved {round(days)} days apart")

        shared_names = sorted(main_names & (names[path] - common))
        smaller = min(len(main_names), len(names[path] - common))
        name_score = len(shared_names) / smaller if smaller else 0.0
        if shared_names:
            reasons.append(f"name: {', '.join(shared_names)}")

        kind = _kind(path, candidate_classes.get(path))
        kind_score = 1.0 if kind and kind in wanted_kinds else 0.0
        if kind_score:
            reasons.append(f"document refers to a {kind}")

        attach_score = 1.0 if _ATTACH_NAME_RE.search(path.name) else 0.0
        folder_score = 1.0 if path.parent == main_path.parent else 0.0

        score = (
            WEIGHTS["values"] * value_score
            + WEIGHTS["ids"] * id_score
            + WEIGHTS["date"] * date_score
            + WEIGHTS["name"] * name_score
            + WEIGHTS["kind"] * kind_score
            + WEIGHTS["attach_name"] * attach_score
            + WEIGHTS["folder"] * folder_score
        )
        if bool(_DRAFT_RE.search(path.name)) != main_draft:
            score -= DRAFT_MISMATCH_PENALTY
            reasons.append("draft vs. final")
        if _in_archive(path, root) != main_archived:
            score -= ARCHIVE_PENALTY
            reasons.append("only one is archived")
        ranked.append(Candidate(path, round(max(score, 0.0), 3), reasons))
    ranked.sort(key=lambda candidate: (-candidate.score, candidate.path.as_posix()))
    return ranked


def is_uncertain(ranked: list[Candidate]) -> bool:
    if not ranked:
        return True
    best = ranked[0].score
    runner_up = ranked[1].score if len(ranked) > 1 else 0.0
    return best < CONFIDENT_SCORE or best - runner_up < MIN_MARGIN


# --- overrides ----------------------------------------------------------------


NONE = "none"


def load_overrides(root: Path) -> dict[str, dict[str, list[Path] | None]]:
    """Read ``sources.yaml``: ``{group: {field: [files] | None}}``.

    ``None`` means "do not look outside the document for this field".
    """
    path = root / SOURCES_FILE
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SourcesError(f"{path}: invalid YAML: {exc}") from exc
    entries = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(entries, dict):
        raise SourcesError(f"{path}: expected a top-level 'sources:' mapping")

    overrides: dict[str, dict[str, list[Path] | None]] = {}
    for group, fields in entries.items():
        if not isinstance(fields, dict):
            raise SourcesError(
                f"{SOURCES_FILE}: '{group}' must map field names to files"
            )
        overrides[str(group)] = {}
        for field_name, value in fields.items():
            if value is None or (
                isinstance(value, str) and value.strip().lower() == NONE
            ):
                overrides[str(group)][str(field_name)] = None
                continue
            names = value if isinstance(value, list) else [value]
            files = []
            for name in names:
                file = (root / str(name)).resolve()
                if not file.is_file():
                    raise SourcesError(
                        f"{SOURCES_FILE}: '{group}' / '{field_name}': "
                        f"file not found: {name}"
                    )
                files.append(file)
            overrides[str(group)][str(field_name)] = files
    return overrides
