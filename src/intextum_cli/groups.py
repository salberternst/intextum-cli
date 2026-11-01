"""Decide which files in the input folder are processed together.

Rules, in order:

1. Groups listed in ``groups.yaml`` at the input root (files or folders, globs ok).
2. With ``group_by="folder"`` (default), every remaining top-level subfolder is one
   group (all files below it) and every remaining file in the input root is its
   own group. With ``group_by="file"``, every remaining file is its own group.

Hidden files/folders (leading ``.``), Office lock files (``~$...``), file types
that cannot be converted to text and files matching an exclude pattern are skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from .convert import is_supported

GROUPS_FILE = "groups.yaml"
_IGNORED_NAMES = frozenset({GROUPS_FILE, "sources.yaml", "Thumbs.db", "desktop.ini"})


class GroupsError(ValueError):
    """Raised when ``groups.yaml`` is invalid or inconsistent."""


@dataclass
class Group:
    name: str
    root: Path
    files: list[Path]
    document_class: str | None = None
    classification_source: str = "groups.yaml"
    no_matching_class: bool = False

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    @property
    def relative_files(self) -> list[str]:
        return [self.relative(path) for path in self.files]


def scope_resolver(root: Path, files: list[Path]):
    """Return a function mapping a file to its scope (the folder of one customer/case).

    If the input root itself contains files, the whole input is one scope (for
    example a single customer folder). Otherwise each top-level subfolder is one.
    """
    single = any(len(path.relative_to(root).parts) == 1 for path in files)

    def scope(path: Path) -> str:
        parts = path.relative_to(root).parts
        return "" if single or len(parts) == 1 else parts[0]

    return scope


def _is_skipped(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    if any(part.startswith(".") for part in parts):
        return True
    return path.name in _IGNORED_NAMES or path.name.startswith("~$")


def _candidate_files(
    root: Path,
    exclude: list[Path],
    unsupported: list[Path] | None,
    patterns: list[re.Pattern[str]],
    matched: list[Path] | None,
) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        if not path.is_file() or _is_skipped(path, root):
            continue
        if any(path.is_relative_to(excluded) for excluded in exclude):
            continue
        relative = path.relative_to(root).as_posix()
        if any(pattern.search(relative) for pattern in patterns):
            if matched is not None:
                matched.append(path)
            continue
        if not is_supported(path):
            if unsupported is not None:
                unsupported.append(path)
            continue
        files.append(path)
    return sorted(files)


def _load_group_specs(root: Path) -> list[dict]:
    groups_file = root / GROUPS_FILE
    if not groups_file.is_file():
        return []
    try:
        data = yaml.safe_load(groups_file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise GroupsError(f"{groups_file}: invalid YAML: {exc}") from exc
    specs = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(specs, list):
        raise GroupsError(f"{groups_file}: expected a top-level 'groups:' list")
    for index, spec in enumerate(specs, start=1):
        if not isinstance(spec, dict):
            raise GroupsError(f"{groups_file}: group #{index} must be a mapping")
        if not str(spec.get("name") or "").strip():
            raise GroupsError(f"{groups_file}: group #{index} needs a 'name'")
        files = spec.get("files")
        if not isinstance(files, list) or not files:
            raise GroupsError(
                f"{groups_file}: group '{spec['name']}' needs a non-empty 'files' list"
            )
    return specs


def _match_pattern(root: Path, pattern: str, candidates: set[Path]) -> list[Path]:
    matched: set[Path] = set()
    try:
        hits = list(root.glob(pattern))
    except (NotImplementedError, ValueError) as exc:
        raise GroupsError(f"{GROUPS_FILE}: invalid pattern '{pattern}': {exc}") from exc
    for hit in hits:
        if hit.is_dir():
            matched.update(path for path in candidates if path.is_relative_to(hit))
        elif hit in candidates:
            matched.add(hit)
    return sorted(matched)


def discover_groups(
    root: Path,
    *,
    exclude: list[Path] | None = None,
    group_by: Literal["folder", "file"] = "folder",
    unsupported: list[Path] | None = None,
    exclude_patterns: list[str] | None = None,
    excluded_files: list[Path] | None = None,
) -> list[Group]:
    """Return the processing groups for ``root`` in a stable order.

    Files of unsupported types are left out and appended to ``unsupported``.
    Files whose path relative to ``root`` matches one of ``exclude_patterns``
    (case-insensitive regular expressions) are left out everywhere and appended to
    ``excluded_files``.
    """
    root = root.resolve()
    if not root.is_dir():
        raise GroupsError(f"input folder not found: {root}")
    excluded = [path.resolve() for path in exclude or []]
    patterns = []
    for pattern in exclude_patterns or []:
        try:
            patterns.append(re.compile(pattern, re.IGNORECASE))
        except re.error as exc:
            raise GroupsError(f"invalid exclude pattern '{pattern}': {exc}") from exc
    candidates = _candidate_files(root, excluded, unsupported, patterns, excluded_files)
    candidate_set = set(candidates)

    groups: list[Group] = []
    owner: dict[Path, str] = {}
    names: set[str] = set()
    for spec in _load_group_specs(root):
        name = str(spec["name"]).strip()
        if name in names:
            raise GroupsError(f"{GROUPS_FILE}: duplicate group name '{name}'")
        names.add(name)
        files: list[Path] = []
        for pattern in spec["files"]:
            matched = _match_pattern(root, str(pattern), candidate_set)
            if not matched:
                raise GroupsError(
                    f"{GROUPS_FILE}: group '{name}': '{pattern}' matches no files"
                    + (" (excluded files are ignored)" if patterns else "")
                )
            for path in matched:
                if path in owner and owner[path] != name:
                    raise GroupsError(
                        f"{GROUPS_FILE}: {path.relative_to(root)} is in both "
                        f"'{owner[path]}' and '{name}'"
                    )
                if path not in owner:
                    owner[path] = name
                    files.append(path)
        document_class = spec.get("class")
        groups.append(
            Group(
                name=name,
                root=root,
                files=files,
                document_class=str(document_class).strip() if document_class else None,
            )
        )

    by_folder: dict[str, list[Path]] = {}
    singles: list[Path] = []
    for path in candidates:
        if path in owner:
            continue
        parts = path.relative_to(root).parts
        if len(parts) == 1 or group_by == "file":
            singles.append(path)
        else:
            by_folder.setdefault(parts[0], []).append(path)

    implicit = [
        Group(name=folder, root=root, files=files)
        for folder, files in by_folder.items()
    ]
    implicit += [
        Group(name=path.relative_to(root).as_posix(), root=root, files=[path])
        for path in singles
    ]
    for group in sorted(implicit, key=lambda group: group.name):
        if group.name in names:
            raise GroupsError(
                f"{GROUPS_FILE}: group name '{group.name}' clashes with a folder "
                "or file of the same name"
            )
        names.add(group.name)
        groups.append(group)
    return groups
