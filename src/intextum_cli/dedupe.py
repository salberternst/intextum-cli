"""Find files that are copies or versions of another file, so text is used once.

Two files count as duplicates when they are byte-identical, or when all of these
hold for their texts:

- the smaller text is almost fully contained in the larger one (a signed scan
  may add a signature page),
- the larger one does not add much of its own (a 2023 price list that extends
  the 2021 list is a new version, not a copy),
- they contain the same numeric tokens in the same order, including signs and
  repetitions (dates, reference numbers, amounts), which keeps different
  contracts built from one template apart.
Only files in the same scope are compared: the whole input if it contains files
directly, otherwise each top-level subfolder.

From each set of duplicates one primary is kept: outside archive folders first,
then signed copies, then non-drafts, then the newest file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .convert import file_digest
from .groups import scope_resolver

MIN_TEXT_CHARS = 300
MIN_TEXT_OVERLAP = 0.9
MIN_TEXT_JACCARD = 0.7
MIN_LENGTH_RATIO = 0.5

_WORD_RE = re.compile(r"\w+")
_NUMBER_RE = re.compile(r"[+\-−]?\d+(?:[.,/]\d+)*")
_ARCHIVE_PARTS = frozenset({"archiv", "archive", "alt", "old", "backup"})
_SIGNED_RE = re.compile(
    r"gez|unterschrieben|unterzeichnet|signiert|gegengezeichnet|signed", re.I
)
_DRAFT_RE = re.compile(r"entwurf|draft|überarb", re.I)


@dataclass(frozen=True)
class Duplicate:
    primary: Path
    reason: str  # "identical file" or "same text"
    similarity: float


@dataclass
class _Profile:
    path: Path
    shingles: frozenset[tuple[str, ...]]
    numbers: tuple[str, ...]
    length: int


def _profile(path: Path, text: str) -> _Profile | None:
    words = [word.lower() for word in _WORD_RE.findall(text)]
    if len(text) < MIN_TEXT_CHARS or len(words) < 3:
        return None
    shingles = frozenset(zip(words, words[1:], words[2:], strict=False))
    return _Profile(path, shingles, tuple(_NUMBER_RE.findall(text)), len(text))


def _jaccard(a: frozenset, b: frozenset) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def _containment(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 1.0 if a == b else 0.0
    return len(a & b) / min(len(a), len(b))


def _text_similarity(a: _Profile, b: _Profile) -> float | None:
    if a.numbers != b.numbers:
        return None
    if min(a.length, b.length) / max(a.length, b.length) < MIN_LENGTH_RATIO:
        return None
    text = _containment(a.shingles, b.shingles)
    if text < MIN_TEXT_OVERLAP or _jaccard(a.shingles, b.shingles) < MIN_TEXT_JACCARD:
        return None
    return text


def _primary_rank(path: Path, root: Path) -> tuple:
    parts = {part.casefold() for part in path.relative_to(root).parts[:-1]}
    return (
        bool(parts & _ARCHIVE_PARTS),
        not _SIGNED_RE.search(path.name),
        bool(_DRAFT_RE.search(path.name)),
        -path.stat().st_mtime,
        path.relative_to(root).as_posix(),
    )


def find_duplicates(root: Path, texts: dict[Path, str]) -> dict[Path, Duplicate]:
    """Map every non-primary file to the primary it duplicates."""
    parent = {path: path for path in texts}
    evidence: dict[frozenset[Path], tuple[str, float]] = {}

    def find(path: Path) -> Path:
        while parent[path] != path:
            parent[path] = parent[parent[path]]
            path = parent[path]
        return path

    def join(a: Path, b: Path, reason: str, similarity: float) -> None:
        evidence[frozenset((a, b))] = (reason, similarity)
        parent[find(a)] = find(b)

    scope = scope_resolver(root, list(texts))
    scopes: dict[str, list[Path]] = {}
    for path in sorted(texts):
        scopes.setdefault(scope(path), []).append(path)

    for paths in scopes.values():
        by_digest: dict[str, Path] = {}
        for path in paths:
            digest = file_digest(path)
            if digest in by_digest:
                join(path, by_digest[digest], "identical file", 1.0)
            else:
                by_digest[digest] = path
        profiles = [p for p in (_profile(path, texts[path]) for path in paths) if p]
        for index, a in enumerate(profiles):
            for b in profiles[index + 1 :]:
                if find(a.path) == find(b.path):
                    continue
                similarity = _text_similarity(a, b)
                if similarity is not None:
                    join(a.path, b.path, "same text", round(similarity, 3))

    clusters: dict[Path, list[Path]] = {}
    for path in texts:
        clusters.setdefault(find(path), []).append(path)
    duplicates: dict[Path, Duplicate] = {}
    for members in clusters.values():
        if len(members) < 2:
            continue
        primary = min(members, key=lambda path: _primary_rank(path, root))
        for member in members:
            if member == primary:
                continue
            # Report the strongest match this file has inside its set.
            reason, similarity = max(
                (value for pair, value in evidence.items() if member in pair),
                key=lambda value: value[1],
            )
            duplicates[member] = Duplicate(primary, reason, similarity)
    return duplicates
