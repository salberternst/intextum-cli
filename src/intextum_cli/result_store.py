"""Results, schema snapshots, corrections, and pinned source bindings."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from .edits import apply_edits
from .naming import slugify
from .review_state import CLASS_ACTIONS, ReviewConflict, apply_review, class_choice
from .schema import DocumentClass
from .store_records import SourceReference, WorkspaceSnapshot, encode
from .verification import apply_verification

if TYPE_CHECKING:
    from .store import WorkspaceStore


class ResultStore:
    def __init__(self, workspace: WorkspaceStore):
        self.workspace = workspace

    @staticmethod
    def _history(db: sqlite3.Connection, group: str) -> list[dict]:
        return [
            json.loads(row[0])
            for row in db.execute(
                "SELECT payload FROM corrections WHERE group_name=? ORDER BY id",
                (group,),
            )
        ]

    @staticmethod
    def _verification(db: sqlite3.Connection, group: str) -> dict | None:
        row = db.execute(
            "SELECT payload FROM verifications WHERE group_name=?", (group,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def _effective(self, db: sqlite3.Connection, group: str, raw: dict) -> dict:
        """Model output, then verification, corrections, and review decisions."""
        verified = apply_verification(raw, self._verification(db, group))
        return apply_review(
            apply_edits(verified, self._history(db, group)), self._events(db, group)
        )

    def _decode_result(
        self, db: sqlite3.Connection, row: sqlite3.Row | None
    ) -> dict | None:
        if row is None:
            return None
        return self._effective(db, row["group_name"], json.loads(row["payload"]))

    def sources(self, group: str) -> list[dict]:
        with self.workspace.connection(readonly=True) as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM result_sources WHERE group_name=?", (group,)
                )
            ]

    def save_verification(self, group: str, record: dict) -> dict | None:
        """Store a record if it still matches the current extraction."""
        with self.workspace.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM results WHERE group_name=?", (group,)
            ).fetchone()
            if row is None:
                return None
            raw = json.loads(row["payload"])
            # A newer extraction finished meanwhile; its own phase verifies it.
            if raw.get("extraction_id") != record.get("extraction_id"):
                return self._decode_result(db, row)
            db.execute(
                "INSERT INTO verifications VALUES(?,?) ON CONFLICT(group_name) "
                "DO UPDATE SET payload=excluded.payload",
                (group, encode(record)),
            )
            result = self._decode_result(db, row)
            self._update_index(db, group, result)
            return result

    def verification_candidates(
        self, key: str, groups: set[str] | None = None, force: bool = False
    ) -> list[str]:
        """Completed results without a current record for these settings."""
        with self.workspace.connection(readonly=True) as db:
            rows = db.execute(
                "SELECT r.group_name, r.payload, v.payload AS record "
                "FROM results r LEFT JOIN verifications v USING(group_name) "
                "WHERE r.status IN ('completed','unclassified') ORDER BY r.group_name"
            ).fetchall()
        pending = []
        for row in rows:
            if groups is not None and row["group_name"] not in groups:
                continue
            record = json.loads(row["record"]) if row["record"] else {}
            extraction = json.loads(row["payload"]).get("extraction_id")
            if (
                force
                or record.get("key") != key
                or record.get("extraction_id") != extraction
            ):
                pending.append(row["group_name"])
        return pending

    @staticmethod
    def _events(db: sqlite3.Connection, group: str) -> list[dict]:
        return [
            {**json.loads(row["payload"]), "id": row["id"]}
            for row in db.execute(
                "SELECT id,payload FROM review_events WHERE group_name=? ORDER BY id",
                (group,),
            )
        ]

    def choice(self, group: str) -> dict:
        with self.workspace.connection(readonly=True) as db:
            return class_choice(self._events(db, group))

    def review_action(
        self,
        slug: str,
        action: str,
        revision: str,
        *,
        class_name: str | None = None,
        note: str = "",
        classes: list[DocumentClass] | None = None,
    ) -> dict:
        if action not in CLASS_ACTIONS | {"approve", "reopen"}:
            raise ValueError("Unknown review action")
        with self.workspace.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM results WHERE slug=?", (slug,)).fetchone()
            current = self._decode_result(db, row)
            if current is None:
                raise KeyError(slug)
            if revision != current["review"]["revision"]:
                raise ReviewConflict("This result changed. Refresh before saving.")
            if action == "class":
                from .schema import find_class

                available = (
                    classes
                    if classes is not None
                    else self._classes(db, row["schema_key"])
                )
                selected = find_class(available, class_name or "")
                if selected is None:
                    raise ValueError(f"Unknown class '{class_name}'")
                class_name = selected.name
            if action in {"approve", "no_match"}:
                if current.get("status") == "failed":
                    raise ValueError(
                        "Re-extract this failed result before reviewing it."
                    )
                if action == "approve" and current["review"]["pending_extraction"]:
                    raise ValueError(
                        "Re-extract the selected class before reviewing it."
                    )
            event = {
                "action": action,
                "at": datetime.now(UTC).isoformat(),
                "note": note,
                "revision": revision,
                "content_revision": current["review"]["content_revision"],
            }
            if action == "class":
                event["class_name"] = class_name
            cursor = db.execute(
                "INSERT INTO review_events(group_name,payload) VALUES(?,?)",
                (row["group_name"], encode(event)),
            )
            if action == "no_match":
                # Its own class choice is part of the approved revision.
                updated = self._decode_result(db, row)
                event["content_revision"] = updated["review"]["content_revision"]
                db.execute(
                    "UPDATE review_events SET payload=? WHERE id=?",
                    (encode(event), cursor.lastrowid),
                )
            updated = self._decode_result(db, row)
            self._update_index(db, row["group_name"], updated)
            return updated

    def get(self, identifier: str, *, by_group: bool = False) -> dict | None:
        column = "group_name" if by_group else "slug"
        with self.workspace.connection(readonly=True) as db:
            db.execute("BEGIN")
            row = db.execute(
                f"SELECT * FROM results WHERE {column}=?", (identifier,)
            ).fetchone()
            return self._decode_result(db, row)

    @staticmethod
    def _classes(db: sqlite3.Connection, schema_key: str) -> list[DocumentClass]:
        row = db.execute(
            "SELECT payload FROM schemas WHERE key=?", (schema_key,)
        ).fetchone()
        return [DocumentClass.model_validate(c) for c in json.loads(row[0])]

    def classes(self, group: str) -> list[DocumentClass]:
        with self.workspace.connection(readonly=True) as db:
            row = db.execute(
                "SELECT schema_key FROM results WHERE group_name=?", (group,)
            ).fetchone()
            return self._classes(db, row[0]) if row else []

    @staticmethod
    def _index_values(result: dict) -> tuple:
        return (
            result.get("status"),
            (result.get("class") or {}).get("name"),
            bool(result.get("needs_review")),
            encode(result.get("review_reasons") or []),
            bool(result.get("edits")),
            encode(result.get("files") or []),
            (result.get("review") or {}).get("state") == "reviewed",
        )

    def _update_index(self, db: sqlite3.Connection, group: str, result: dict) -> None:
        db.execute(
            "UPDATE results SET status=?, class_name=?, needs_review=?, "
            "review_reasons=?, edited=?, files=?, reviewed=? WHERE group_name=?",
            (*self._index_values(result), group),
        )

    def save(
        self,
        result: dict,
        classes: list[DocumentClass],
        sources: Sequence[SourceReference] = (),
    ) -> dict:
        group = result["group"]
        schema = encode([c.model_dump(by_alias=True) for c in classes])
        schema_key = hashlib.sha256(schema.encode()).hexdigest()
        with self.workspace.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR IGNORE INTO schemas VALUES (?, ?)", (schema_key, schema)
            )
            row = db.execute(
                "SELECT slug FROM results WHERE group_name=?", (group,)
            ).fetchone()
            if row:
                slug = row[0]
            else:
                base = slugify(group)
                slug, counter = base, 2
                while db.execute(
                    "SELECT 1 FROM results WHERE slug_fold=?", (slug.casefold(),)
                ).fetchone():
                    slug, counter = f"{base}_{counter}", counter + 1
            raw = deepcopy(result)
            raw.pop("edits", None)
            raw.pop("review", None)
            raw.pop("verification", None)
            for entry in (raw.get("fields") or {}).values():
                if isinstance(entry, dict):
                    entry.pop("verification", None)
            events = self._events(db, group)
            choice = class_choice(events)
            if raw.get("classification_revision", choice["id"]) != choice["id"]:
                raise ReviewConflict("The class changed during extraction. Retry it.")
            raw.setdefault("classification_revision", choice["id"])
            raw["extraction_id"] = uuid4().hex
            db.execute(
                "INSERT INTO results(group_name,slug,slug_fold,payload,schema_key) "
                "VALUES(?,?,?,?,?) "
                "ON CONFLICT(group_name) DO UPDATE SET "
                "payload=excluded.payload,schema_key=excluded.schema_key",
                (group, slug, slug.casefold(), encode(raw), schema_key),
            )
            effective = self._effective(db, group, deepcopy(raw))
            self._update_index(db, group, effective)
            db.execute("DELETE FROM result_sources WHERE group_name=?", (group,))
            for source in sources:
                db.execute(
                    "INSERT INTO result_sources VALUES(?,?,?,?,?)",
                    (
                        group,
                        source["path"],
                        source["digest"],
                        source.get("key"),
                        source.get("key"),
                    ),
                )
            return effective

    def edit(
        self,
        slug: str,
        field: str,
        value: Any,
        note: str,
        normalize: Callable[[dict, list[DocumentClass], Any], Any],
        revision: str | None = None,
    ) -> dict:
        with self.workspace.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM results WHERE slug=?", (slug,)).fetchone()
            result = self._decode_result(db, row)
            if result is None or field not in (result.get("fields") or {}):
                raise KeyError(field)
            if revision is not None and revision != result["review"]["revision"]:
                raise ReviewConflict("This result changed. Refresh before editing.")
            if result["review"]["pending_extraction"]:
                raise ValueError("Re-extract the selected class before editing fields.")
            value = normalize(result, self._classes(db, row["schema_key"]), value)
            current = result["fields"][field]
            edit = {
                "at": datetime.now(UTC).isoformat(timespec="seconds"),
                "field": field,
                "value": value,
                "previous": current.get("extracted_value", current.get("value")),
                "note": note,
                "class_name": (result.get("class") or {}).get("name"),
                "correction_scope": result.get("classification_revision", 0),
            }
            db.execute(
                "INSERT INTO corrections(group_name,payload) VALUES(?,?)",
                (row["group_name"], encode(edit)),
            )
            result = self._decode_result(db, row)
            self._update_index(db, row["group_name"], result)
            return result

    def index(self) -> list[dict]:
        with self.workspace.connection(readonly=True) as db:
            db.execute("BEGIN")
            return [
                {
                    "slug": r["slug"],
                    "group": r["group_name"],
                    "status": r["status"],
                    "class": r["class_name"],
                    "needs_review": bool(r["needs_review"]),
                    "review_reasons": json.loads(r["review_reasons"]),
                    "edited": bool(r["edited"]),
                    "files": json.loads(r["files"]),
                    "reviewed": bool(r["reviewed"]),
                }
                for r in db.execute(
                    "SELECT slug,group_name,status,class_name,needs_review,"
                    "review_reasons,edited,files,reviewed "
                    "FROM results ORDER BY group_name"
                )
            ]

    def snapshot(self) -> list[WorkspaceSnapshot]:
        with self.workspace.connection(readonly=True) as db:
            db.execute("BEGIN")
            return [
                (
                    r["slug"],
                    self._decode_result(db, r),
                    self._classes(db, r["schema_key"]),
                )
                for r in db.execute("SELECT * FROM results ORDER BY group_name")
            ]

    def source(self, slug: str, relative: str) -> dict | None:
        with self.workspace.connection(readonly=True) as db:
            row = db.execute(
                "SELECT s.* FROM result_sources s JOIN results r USING(group_name) "
                "WHERE r.slug=? AND s.path=?",
                (slug, relative),
            ).fetchone()
            return dict(row) if row else None

    def bind_view(
        self, slug: str, relative: str, key: str, digest: str, expected_key: str | None
    ) -> None:
        with self.workspace.connection() as db:
            db.execute(
                "UPDATE result_sources SET view_key=? WHERE group_name="
                "(SELECT group_name FROM results WHERE slug=?) AND path=? AND digest=? "
                "AND conversion_key IS ?",
                (key, slug, relative, digest, expected_key),
            )

    def contains_path(self, relative: str) -> bool:
        with self.workspace.connection(readonly=True) as db:
            return (
                db.execute(
                    "SELECT 1 FROM result_sources WHERE path=?", (relative,)
                ).fetchone()
                is not None
            )
