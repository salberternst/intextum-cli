"""Explicit JSON and CSV exports from one consistent workspace snapshot."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .naming import slugify
from .schema import REPEATED_DTYPES
from .store import WorkspaceStore
from .store_records import WorkspaceSnapshot

SUMMARY_CSV = "_summary.csv"


REVIEW_STATES = ("all", "reviewed", "open")


def review_state(result: dict[str, Any]) -> str:
    return (result.get("review") or {}).get("state") or "open"


def export_workspace(
    store: WorkspaceStore,
    out_dir: Path,
    output_format: str = "all",
    state: str = "all",
) -> int:
    """Export results in ``state``; returns how many results were exported."""
    if state not in REVIEW_STATES:
        raise ValueError(f"unknown review state '{state}'")
    everything = store.results.snapshot()
    snapshots = [
        snapshot
        for snapshot in everything
        if state == "all" or review_state(snapshot[1]) == state
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    if output_format in {"json", "all"}:
        # Files from an earlier, wider export would contradict the filter.
        exported = {slug for slug, _, _ in snapshots}
        for slug, _, _ in everything:
            if slug not in exported:
                (out_dir / f"{slug}.json").unlink(missing_ok=True)
        for slug, result, _ in snapshots:
            (out_dir / f"{slug}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
                + "\n",
                encoding="utf-8",
            )
    if output_format in {"csv", "all"}:
        write_csvs(snapshots, out_dir)
    return len(snapshots)


def write_csvs(snapshots: list[WorkspaceSnapshot], out_dir: Path) -> None:
    """One summary CSV for all groups plus one CSV per class with its fields."""
    results = [result for _, result, _ in snapshots]
    classes = {}
    dtypes = {}
    for _, result, schemas in snapshots:
        for schema in schemas:
            # A viewer class change can leave a previously exported CSV empty.
            fields = classes.setdefault(schema.name, {})
            if schema.name != (result.get("class") or {}).get("name"):
                continue
            for field in schema.fields:
                fields.setdefault(field.name, field)
                dtypes[result["group"], field.name] = field.dtype
    with (out_dir / SUMMARY_CSV).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "group",
                "status",
                "class",
                "class_source",
                "reason",
                "needs_review",
                "review_state",
                "review_reasons",
                "files",
                "duplicates",
                "sources",
                "error",
            ]
        )
        for result in results:
            classification = result.get("class") or {}
            writer.writerow(
                [
                    result["group"],
                    result["status"],
                    classification.get("name") or "",
                    classification.get("source") or "",
                    classification.get("reason") or "",
                    "yes" if result.get("needs_review") else "no",
                    review_state(result),
                    "; ".join(result.get("review_reasons") or []),
                    "; ".join(result.get("files") or []),
                    "; ".join(
                        f"{name} = {info['primary']}"
                        for name, info in (result.get("duplicates") or {}).items()
                    ),
                    "; ".join(_source_summary(result)),
                    result.get("error") or "",
                ]
            )

    for class_name, field_map in sorted(classes.items()):
        fields = list(field_map.values())
        rows = [
            r for r in results
            if (r.get("class") or {}).get("name") == class_name
            and r.get("status") == "completed"
            and r.get("mode") != "classify"
        ]  # fmt: skip
        csv_path = out_dir / f"{slugify(class_name)}.csv"
        if not rows:
            csv_path.unlink(missing_ok=True)
            continue
        with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                ["group", "needs_review", "review_state", "review_reasons"]
                + [f.name for f in fields]
            )
            for result in rows:
                data = result.get("data") or {}
                writer.writerow(
                    [
                        result["group"],
                        "yes" if result.get("needs_review") else "no",
                        review_state(result),
                        "; ".join(result.get("review_reasons") or []),
                    ]
                    + [
                        _csv_value(
                            data.get(f.name),
                            dtypes.get((result["group"], f.name), f.dtype),
                        )
                        for f in fields
                    ]
                )


def _source_summary(result: dict[str, Any]) -> list[str]:
    parts = []
    for name, entry in (result.get("fields") or {}).items():
        source = entry.get("source") if isinstance(entry, dict) else None
        if not source:
            continue
        files = ", ".join(source.get("files") or []) or "none found"
        detail = source.get("set_in") or (
            f"{source['score']:.2f}" if source.get("score") is not None else ""
        )
        parts.append(f"{name} ← {files}" + (f" ({detail})" if detail else ""))
    return parts


def _csv_value(value: Any, dtype: str) -> str:
    if value is None:
        return ""
    if dtype in REPEATED_DTYPES:
        return json.dumps(value, ensure_ascii=False) if value else ""
    if dtype == "currency" and isinstance(value, dict):
        return " ".join(
            str(part)
            for part in (value.get("amount"), value.get("currency"))
            if part is not None
        )
    return str(value)
