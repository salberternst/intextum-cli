"""Options, source scope, and summary shared by extraction stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .dedupe import Duplicate
from .groups import Group, scope_resolver
from .schema import DocumentClass


@dataclass
class Options:
    classes: list[DocumentClass]
    model: str
    base_url: str = ""
    forced_class: str | None = None
    max_chars: int = 60_000
    retries: int = 1
    force: bool = False
    classify_only: bool = False
    force_ocr: bool = False
    ocr_engine: str = "auto"
    ocr_languages: list[str] = field(default_factory=list)
    table_mode: str = "ruled"
    detect_marks: bool = False
    max_output_tokens: int = 4096
    thinking: bool = False
    context_length: int | None = None
    keep_duplicates: bool = False
    # From sources.yaml: {group: {field: [files] | None}}
    overrides: dict[str, dict[str, list[Path] | None]] = field(default_factory=dict)


@dataclass
class SourceScope:
    """Everything a group may look at beyond its own files."""

    root: Path
    files: list[Path]
    duplicates: dict[Path, Duplicate]

    def __post_init__(self) -> None:
        self.scope_of = scope_resolver(self.root, self.files)

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def neighbours(self, group: Group) -> list[Path]:
        """Other files in the same scope(s) as the group, without duplicates."""
        scopes = {self.scope_of(path) for path in group.files}
        members = set(group.files)
        return [
            path
            for path in self.files
            if path not in members
            and path not in self.duplicates
            and self.scope_of(path) in scopes
        ]


@dataclass
class Summary:
    processed: int = 0
    unchanged: int = 0
    needs_review: int = 0
    failed: int = 0
    duplicates: int = 0
    verified: int = 0
