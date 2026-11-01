"""Cached conversions, binary assets, and classifications."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from .store_records import ConversionRecord, encode

if TYPE_CHECKING:
    from .store import WorkspaceStore


def _read_document(raw: str | None) -> dict | None:
    # A damaged view must not make the original extraction text unreadable.
    try:
        value = json.loads(raw) if raw else None
        return value if isinstance(value, dict) else None
    except (ValueError, TypeError):
        return None


class CacheStore:
    def __init__(self, workspace: WorkspaceStore):
        self.workspace = workspace

    def conversion(self, key: str) -> ConversionRecord | None:
        with self.workspace.connection(readonly=True) as db:
            row = db.execute("SELECT * FROM conversions WHERE key=?", (key,)).fetchone()
            if row is None:
                return None
            try:
                pages, notes, settings = (
                    json.loads(row[name]) for name in ("pages", "notes", "settings")
                )
                if not (
                    isinstance(pages, list)
                    and all(isinstance(p, str) for p in pages)
                    and isinstance(notes, list)
                    and all(isinstance(n, str) for n in notes)
                    and isinstance(settings, dict)
                    and row["paged"] in (0, 1)
                ):
                    return None
                return ConversionRecord(
                    key=row["key"],
                    digest=row["digest"],
                    suffix=row["suffix"],
                    pages=pages,
                    paged=bool(row["paged"]),
                    notes=notes,
                    settings=settings,
                    manifest=_read_document(row["manifest"]),
                    document=_read_document(row["document"]),
                )
            except (ValueError, TypeError):
                return None

    def save_conversion(
        self,
        key: str,
        digest: str,
        suffix: str,
        pages: list[str],
        paged: bool,
        notes: list[str],
        manifest: dict | None = None,
        document: dict | None = None,
        assets: dict[str, bytes] | None = None,
        settings: dict | None = None,
        preserve_text: bool = False,
    ) -> None:
        # Serialize everything before acquiring the writer lock.
        values = (
            key,
            digest,
            suffix,
            encode(pages),
            paged,
            encode(notes),
            encode(manifest) if manifest else None,
            encode(document) if document else None,
            encode(settings or {}),
        )
        with self.workspace.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            update_text = (
                ""
                if preserve_text
                else (
                    ",pages=excluded.pages,paged=excluded.paged,notes=excluded.notes,"
                    "settings=excluded.settings"
                )
            )
            db.execute(
                "INSERT INTO conversions VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET "
                "manifest=excluded.manifest,document=excluded.document" + update_text,
                values,
            )
            db.execute("DELETE FROM document_assets WHERE conversion_key=?", (key,))
            for filename, data in (assets or {}).items():
                asset_key = hashlib.sha256(data).hexdigest()
                db.execute(
                    "INSERT OR IGNORE INTO assets VALUES(?,?,?)",
                    (asset_key, "image/png", data),
                )
                db.execute(
                    "INSERT INTO document_assets VALUES(?,?,?)",
                    (key, filename, asset_key),
                )

    def asset(self, key: str, filename: str) -> bytes | None:
        with self.workspace.connection(readonly=True) as db:
            row = db.execute(
                "SELECT a.data FROM assets a JOIN document_assets d "
                "ON a.key=d.asset_key WHERE d.conversion_key=? AND d.filename=?",
                (key, filename),
            ).fetchone()
            return row[0] if row else None

    def classification(self, key: str) -> dict | None:
        with self.workspace.connection(readonly=True) as db:
            row = db.execute(
                "SELECT payload FROM classifications WHERE key=?", (key,)
            ).fetchone()
            return json.loads(row[0]) if row else None

    def save_classification(self, key: str, value: dict) -> None:
        with self.workspace.connection() as db:
            db.execute(
                "INSERT OR REPLACE INTO classifications VALUES(?,?)",
                (key, encode(value)),
            )
