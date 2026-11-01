"""Transactional, portable storage for an intextum workspace."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock

from .cache_store import CacheStore
from .result_store import ResultStore

APPLICATION_ID = 0x4954584D  # ITXM
FORMAT_VERSION = 3


class StorageError(RuntimeError):
    """A workspace cannot be opened, read, or saved."""


class WorkspaceStore:
    def __init__(self, path: Path, *, create: bool = False):
        self.path = path.resolve()
        self._locks: dict[str, FileLock] = {}
        self.results = ResultStore(self)
        self.cache = CacheStore(self)
        if create:
            with self.lock("initialize"):
                if not self.path.exists():
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        with self.connection(create=True) as db:
                            db.executescript(_SCHEMA)
                            db.execute(f"PRAGMA application_id={APPLICATION_ID}")
                            db.execute(f"PRAGMA user_version={FORMAT_VERSION}")
                    except Exception:
                        self.path.unlink(missing_ok=True)
                        raise
        try:
            with self.connection(readonly=True) as db:
                if db.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
                    raise StorageError(f"not an intextum database: {self.path}")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version != FORMAT_VERSION:
                    raise StorageError(
                        f"unsupported database version {version}; "
                        "recreate it with intextum extract"
                    )
                tables = {
                    r[0]
                    for r in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                required = {
                    "metadata",
                    "schemas",
                    "results",
                    "corrections",
                    "conversions",
                    "result_sources",
                    "assets",
                    "document_assets",
                    "classifications",
                    "previews",
                    "review_events",
                    "verifications",
                }
                if not required <= tables:
                    raise StorageError(f"incomplete workspace database: {self.path}")
                if db.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
                    raise StorageError(f"damaged database: {self.path}")
            with self.connection() as db:
                db.execute("PRAGMA journal_mode=WAL")
        except StorageError:
            raise
        except OSError as exc:
            raise StorageError(f"cannot open database {self.path}: {exc}") from exc

    def lock(self, name: str) -> FileLock:
        # One reentrant FileLock per name and store: viewer re-extraction holds
        # "extract" while pipeline.run acquires it again on the same store.
        if name in self._locks:
            return self._locks[name]
        key = hashlib.sha256(f"{self.path}\0{name}".encode()).hexdigest()
        folder = Path(tempfile.gettempdir()) / "intextum-locks"
        folder.mkdir(exist_ok=True, mode=0o700)
        return self._locks.setdefault(name, FileLock(str(folder / f"{key}.lock")))

    @contextmanager
    def connection(
        self, *, readonly: bool = False, create: bool = False
    ) -> Iterator[sqlite3.Connection]:
        db = None
        try:
            mode = "rwc" if create else "ro" if readonly else "rw"
            db = sqlite3.connect(
                self.path.as_uri() + f"?mode={mode}", uri=True, timeout=5
            )
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA synchronous=FULL")
            yield db
            db.commit()
        except sqlite3.Error as exc:
            if db is not None:
                db.rollback()
            raise StorageError(f"database {self.path}: {exc}") from exc
        except Exception:
            if db is not None:
                db.rollback()
            raise
        finally:
            if db is not None:
                db.close()

    def set_workspace(self, input_dir: Path) -> None:
        with self.connection() as db:
            db.executemany(
                "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
                [("input", str(input_dir.resolve())), ("name", input_dir.name)],
            )

    def metadata(self) -> dict[str, str]:
        with self.connection(readonly=True) as db:
            return dict(db.execute("SELECT key, value FROM metadata"))


_SCHEMA = """
CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE schemas(key TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE results(
    group_name TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE COLLATE NOCASE,
    slug_fold TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL, schema_key TEXT NOT NULL REFERENCES schemas(key),
    status TEXT, class_name TEXT, needs_review INTEGER NOT NULL DEFAULT 0,
    review_reasons TEXT NOT NULL DEFAULT '[]', edited INTEGER NOT NULL DEFAULT 0,
    files TEXT NOT NULL DEFAULT '[]', reviewed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX results_review ON results(needs_review);
CREATE INDEX results_status ON results(status);
CREATE INDEX results_class ON results(class_name);
CREATE INDEX results_edited ON results(edited);
CREATE TABLE corrections(
    id INTEGER PRIMARY KEY, group_name TEXT NOT NULL REFERENCES results(group_name),
    payload TEXT NOT NULL
);
CREATE INDEX corrections_group ON corrections(group_name, id);
CREATE TABLE conversions(
    key TEXT PRIMARY KEY, digest TEXT NOT NULL, suffix TEXT NOT NULL,
    pages TEXT NOT NULL, paged INTEGER NOT NULL, notes TEXT NOT NULL,
    manifest TEXT, document TEXT, settings TEXT NOT NULL
);
CREATE TABLE result_sources(
    group_name TEXT NOT NULL REFERENCES results(group_name), path TEXT NOT NULL,
    digest TEXT NOT NULL, conversion_key TEXT REFERENCES conversions(key),
    view_key TEXT REFERENCES conversions(key), PRIMARY KEY(group_name,path)
);
CREATE INDEX result_sources_path ON result_sources(path);
CREATE TABLE assets(key TEXT PRIMARY KEY, mimetype TEXT NOT NULL, data BLOB NOT NULL);
CREATE TABLE document_assets(
    conversion_key TEXT NOT NULL REFERENCES conversions(key), filename TEXT NOT NULL,
    asset_key TEXT NOT NULL REFERENCES assets(key), PRIMARY KEY(conversion_key,filename)
);
CREATE TABLE classifications(key TEXT PRIMARY KEY, payload TEXT NOT NULL);
-- Retained for format 3 compatibility; preview caches are no longer used.
CREATE TABLE previews(
    digest TEXT PRIMARY KEY, asset_key TEXT NOT NULL REFERENCES assets(key)
);
CREATE TABLE review_events(
    id INTEGER PRIMARY KEY, group_name TEXT NOT NULL REFERENCES results(group_name),
    payload TEXT NOT NULL
);
CREATE INDEX review_events_group ON review_events(group_name,id);
CREATE TABLE verifications(
    group_name TEXT PRIMARY KEY REFERENCES results(group_name), payload TEXT NOT NULL
);
"""
