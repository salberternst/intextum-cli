"""Coordinate incremental extraction and commit each group independently."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .classify import LlmClassifier
from .convert import Converter
from .dedupe import Duplicate, find_duplicates
from .fingerprints import fingerprint
from .group_processing import finish_result, process_group
from .groups import Group
from .llm_types import JsonLlm
from .processing import Options, SourceScope, Summary
from .store import WorkspaceStore
from .store_records import SourceReference, encode
from .verification import Verifier, verify_workspace


def _detect_duplicates(
    groups: list[Group], converter: Converter, report: Callable[[str], None]
) -> dict[Path, Duplicate]:
    """Convert every file once and find copies and versions across groups."""
    files = sorted({path for group in groups for path in group.files})
    if len(files) < 2:
        return {}
    root = groups[0].root
    texts: dict[Path, str] = {}
    for index, path in enumerate(files, start=1):
        converted = converter.convert(path, path.relative_to(root).as_posix())
        if converted.error is None:
            texts[path] = converted.text
        if index % 50 == 0 or index == len(files):
            report(f"checking for duplicates: {index}/{len(files)} files converted")
    return find_duplicates(root, texts)


def _dropped_files(group: Group, duplicates: dict[Path, Duplicate]) -> dict[str, Any]:
    return {
        group.relative(path): {
            "primary": group.relative(duplicates[path].primary),
            "reason": duplicates[path].reason,
            "similarity": duplicates[path].similarity,
        }
        for path in group.files
        if path in duplicates
    }


def run(
    groups: list[Group],
    *,
    converter: Converter,
    classifier: LlmClassifier | None,
    llm: JsonLlm | None,
    options: Options,
    store: WorkspaceStore,
    report: Callable[[str], None] = print,
    only_groups: set[str] | None = None,
    verifier: Verifier | None = None,
    on_group_finished: Callable[[str], None] | None = None,
) -> Summary:
    """Process groups, then verify their results when a verifier is configured.

    ``on_group_finished`` receives each selected group's name after its result
    is committed or reused. Verification messages go only to ``report``.
    """
    if converter.store is None or converter.store.path != store.path:
        raise ValueError("converter and results must use the same workspace database")
    if classifier is not None and (
        classifier.store is None or classifier.store.path != store.path
    ):
        raise ValueError("classifier and results must use the same workspace database")
    with store.lock("extract"):
        if groups:
            store.set_workspace(groups[0].root)
        if only_groups is None:
            settings = asdict(options)
            settings.pop("classes")
            settings.pop("overrides")
            settings.pop("force")
            plan = {
                "options": settings,
                "groups": [
                    {
                        "name": group.name,
                        "files": group.relative_files,
                        "class": group.document_class,
                    }
                    for group in groups
                ],
            }
            with store.connection() as db:
                db.execute(
                    "INSERT OR REPLACE INTO metadata VALUES('extraction_plan',?)",
                    (encode(plan),),
                )
        return _run(
            groups,
            converter=converter,
            classifier=classifier,
            llm=llm,
            options=options,
            report=report,
            store=store,
            only_groups=only_groups,
            verifier=verifier,
            on_group_finished=on_group_finished,
        )


def _run(
    groups: list[Group],
    *,
    converter: Converter,
    classifier: LlmClassifier | None,
    llm: JsonLlm | None,
    options: Options,
    report: Callable[[str], None],
    store: WorkspaceStore,
    only_groups: set[str] | None = None,
    verifier: Verifier | None = None,
    on_group_finished: Callable[[str], None] | None = None,
) -> Summary:
    summary = Summary()
    results: list[dict[str, Any]] = []

    duplicates = (
        {} if options.keep_duplicates else _detect_duplicates(groups, converter, report)
    )
    all_files = sorted({path for group in groups for path in group.files})
    scope = SourceScope(groups[0].root, all_files, duplicates) if groups else None

    for index, group in enumerate(groups, start=1):
        if only_groups is not None and group.name not in only_groups:
            continue
        choice = store.results.choice(group.name)
        if choice["action"] == "class":
            group = replace(
                group,
                document_class=choice["class_name"],
                classification_source="viewer",
            )
        elif choice["action"] == "no_match":
            group = replace(group, no_matching_class=True)
        prefix = f"[{index}/{len(groups)}] {group.name} ({len(group.files)} file"
        prefix += "s)" if len(group.files) != 1 else ")"
        dropped = _dropped_files(group, duplicates)
        remaining = [file for file in group.files if file not in duplicates]
        effective = replace(group, files=remaining)
        digest = fingerprint(effective, options, dropped, scope)
        stored = store.results.get(group.name, by_group=True)
        previous = None if options.force else stored
        if (
            previous
            and previous.get("fingerprint") == digest
            and previous.get("classification_revision", 0) == choice["id"]
            and previous.get("status") != "failed"
        ):
            summary.unchanged += 1
            results.append(previous)
            report(f"{prefix}: unchanged, skipped")
            if on_group_finished is not None:
                on_group_finished(group.name)
            continue

        used_sources: dict[str, SourceReference] = {}
        if remaining:
            result = process_group(
                effective,
                converter=converter,
                classifier=classifier,
                llm=llm,
                options=options,
                scope=scope,
                used_sources=used_sources,
            )
        else:
            result = finish_result(
                {
                    "group": group.name,
                    "mode": "classify" if options.classify_only else "extract",
                    "files": [],
                    "status": "duplicate",
                    "review_reasons": [],
                    "class": None,
                    "data": {},
                    "fields": {},
                    "warnings": [],
                    "error": None,
                }
            )
        if dropped:
            result["duplicates"] = dropped
            result["warnings"].extend(
                f"{name}: skipped, {info['reason']} as {info['primary']}"
                for name, info in dropped.items()
            )
        result.update(
            {
                "fingerprint": digest,
                "model": options.model,
                "processed_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "tool_version": __version__,
                "classification_revision": choice["id"],
            }
        )
        source_names = list(result.get("files") or [])
        for entry in (result.get("fields") or {}).values():
            for name in (entry.get("source") or {}).get("files") or []:
                if name not in source_names:
                    source_names.append(name)
        sources = []
        for name in source_names:
            reference = used_sources.get(name)
            if reference is not None:
                sources.append(reference)
        result = store.results.save(result, options.classes, sources)
        summary.processed += 1
        results.append(result)
        report(f"{prefix}: {_describe(result)}")
        if on_group_finished is not None:
            on_group_finished(group.name)

    if verifier is not None and results:
        # Send verification requests after extraction. The endpoint server owns
        # model loading and memory management.
        decider, settings = verifier
        summary.verified = verify_workspace(
            store,
            decider,
            settings,
            groups={result["group"] for result in results},
            report=report,
        )
        results = [
            store.results.get(result["group"], by_group=True) or result
            for result in results
        ]

    for result in results:
        summary.needs_review += bool(result.get("needs_review"))
        summary.failed += result.get("status") == "failed"
        summary.duplicates += result.get("status") == "duplicate"
    return summary


def _describe(result: dict[str, Any]) -> str:
    status = result["status"]
    class_name = (result.get("class") or {}).get("name")
    text = class_name or status
    if status == "failed":
        text = f"FAILED: {result.get('error')}"
    elif status == "duplicate":
        primaries = {info["primary"] for info in result["duplicates"].values()}
        text = f"duplicate of {', '.join(sorted(primaries))}"
    elif result.get("review", {}).get("state") == "reviewed":
        text += " · reviewed"
    elif result["review_reasons"]:
        text += f" · needs review ({', '.join(result['review_reasons'])})"
    else:
        text += " · ok"
    return text
