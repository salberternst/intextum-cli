"""Review cached documents and correct results in a portable SQLite workspace.

NiceGUI is optional and loaded only when the browser view is started.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
import threading
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .convert import Converter, file_digest
from .document_cache import DocumentStore
from .document_model import resolve_evidence
from .review import field_spec, normalize_edit
from .schema import DocumentClass, SchemaError, SchemaField, find_class, load_classes
from .store import StorageError, WorkspaceStore


class ViewError(RuntimeError):
    """Raised when a workspace cannot be served."""


@dataclass
class Library:
    """A portable database with an optional directory containing originals."""

    database: Path
    input_dir: Path | None = None
    schemas: Path | None = None

    def __post_init__(self) -> None:
        self.database = self.database.resolve()
        try:
            self.store = WorkspaceStore(self.database)
            metadata = self.store.metadata()
            root = self.input_dir or metadata.get("input")
            self.input_dir = Path(root).resolve() if root else None
            if self.input_dir is not None and not self.input_dir.is_dir():
                self.input_dir = None
            self.name = metadata.get("name", self.database.stem)
            self.classes = load_classes(self.schemas) if self.schemas else None
        except (StorageError, SchemaError) as exc:
            raise ViewError(str(exc)) from exc
        self.documents = DocumentStore(self.store)

    def index(self) -> list[dict[str, Any]]:
        return self.store.results.index()

    def result(self, slug: str) -> dict[str, Any] | None:
        return self.store.results.get(slug)

    def review_action(
        self,
        slug: str,
        action: str,
        revision: str,
        class_name: str | None = None,
        note: str = "",
    ) -> dict:
        return self.store.results.review_action(
            slug,
            action,
            revision,
            class_name=class_name,
            note=note,
            classes=self.classes,
        )

    def reextract(self, slug: str, revision: str) -> dict:
        from .reextraction import reextract

        return reextract(self, slug, revision)

    def reextract_many(self, slugs: list[str], progress=None) -> list[dict]:
        from .reextraction import reextract_many

        return reextract_many(self, slugs, progress)

    def file(self, relative: str) -> Path | None:
        """Resolve only recorded documents within the optional original directory."""
        if self.input_dir is None or not isinstance(relative, str) or not relative:
            return None
        if not self.store.results.contains_path(relative):
            return None
        path = (self.input_dir / relative).resolve()
        if (
            not path.is_file()
            or self.input_dir not in path.parents
            or any(
                part.startswith(".") for part in path.relative_to(self.input_dir).parts
            )
        ):
            return None
        return path

    def text(self, relative: str, group: str) -> dict[str, Any]:
        source = self.store.results.source(group, relative)
        cached = (
            self.store.cache.conversion(source["conversion_key"])
            if source and source["conversion_key"]
            else None
        )
        if cached is None:
            return {"cached": False, "pages": [], "notes": []}
        return {
            "cached": True,
            "pages": cached.pages,
            "paged": bool(cached.paged),
            "notes": cached.notes,
        }

    def document_record(
        self, relative: str, group: str, key: str | None = None
    ) -> tuple[dict, dict] | None:
        source = self.store.results.source(group, relative)
        candidate = source["view_key"] if source else None
        if not candidate or (key is not None and key != candidate):
            return None
        return self.documents.read(candidate)

    def document_status(self, relative: str, group: str) -> dict[str, Any]:
        source = self.store.results.source(group, relative)
        can_build = source is not None and self.file(relative) is not None
        cached = self.document_record(relative, group)
        if cached is None:
            return {"status": "missing", "can_build": can_build}
        manifest, _ = cached
        missing = [
            filename
            for filename in manifest["assets"]
            if self.documents.asset(manifest["key"], filename) is None
        ]
        notes = list(manifest["notes"])
        if missing:
            notes.append(
                "Some cached images are missing. "
                "Rebuild this document view to restore them."
            )
        return {
            "status": "ready",
            "key": manifest["key"],
            "image_pages": manifest["image_pages"],
            "notes": notes,
            "needs_rebuild": bool(missing),
            "can_build": can_build,
        }

    def build_document(self, relative: str, group: str) -> dict[str, Any]:
        source = self.store.results.source(group, relative)
        path = self.file(relative)
        if source is None or path is None:
            return {
                "status": "error",
                "error": (
                    "The original document is unavailable. "
                    "Locate the source folder with --input to rebuild."
                ),
            }
        try:
            if file_digest(path) != source["digest"]:
                raise ValueError(
                    "The original has changed since extraction; "
                    "run extract to process the new version."
                )
            original = (
                self.store.cache.conversion(source["conversion_key"])
                if source["conversion_key"]
                else None
            )
            force_ocr = original is not None and original.settings.get("ocr") == "force"
            settings = original.settings if original else {}
            converter = Converter(
                self.store,
                force_ocr=force_ocr,
                ocr_engine=settings.get("ocr_engine", "auto"),
                ocr_languages=settings.get("ocr_languages", []),
                table_mode=settings.get("table_mode", "ruled"),
                detect_marks=settings.get("detect_marks", False),
            )
            key = converter.build_document(path)
            if file_digest(path) != source["digest"]:
                raise ValueError(
                    "The original changed while building its view; retry extraction."
                )
            self.store.results.bind_view(
                group, relative, key, source["digest"], source["conversion_key"]
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}
        return self.document_status(relative, group)

    def document_json(self, relative: str, key: str, group: str) -> dict | None:
        if self.document_record(relative, group, key) is None:
            return None
        return self.documents.public_document(key)

    def document_evidence(
        self, relative: str, evidence: dict, group: str
    ) -> tuple[list[str], str | None]:
        cached = self.document_record(relative, group)
        if cached is None:
            return [], "Build the document view to navigate its elements."
        if self.text(relative, group).get("pages") != cached[0]["pages"]:
            evidence = {**evidence, "document_key": None}
        return resolve_evidence(cached[0], evidence)

    def schema_fields(
        self, result: dict[str, Any], classes: list[DocumentClass] | None = None
    ) -> dict[str, SchemaField]:
        name = (result.get("class") or {}).get("name")
        if classes is None:
            classes = (
                self.store.results.classes(result["group"])
                if self.classes is None
                else self.classes
            )
        document_class = find_class(classes, name) if name else None
        return (
            {field.name: field for field in document_class.fields}
            if document_class
            else {}
        )

    def edit(
        self,
        slug: str,
        field: str,
        value: Any,
        note: str = "",
        revision: str | None = None,
    ) -> dict[str, Any]:
        def normalize(result, classes, value):
            spec = field_spec(
                field,
                result["fields"][field],
                self.schema_fields(
                    result, classes if self.classes is None else self.classes
                ).get(field),
            )
            return normalize_edit(value, spec)

        return self.store.results.edit(slug, field, value, note, normalize, revision)


def open_in_system(path: Path) -> None:
    """Hand a file to the desktop, for formats no browser renders."""
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif sys.platform.startswith("win"):
        subprocess.run(["cmd", "/c", "start", "", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def build_app(library: Library):
    """Create the NiceGUI workspace and its file API only when requested."""
    try:
        from nicegui import ui

        importlib.import_module("nh3")
    except ModuleNotFoundError as exc:
        if exc.name in {"nicegui", "nh3"}:
            raise ViewError(
                "The review UI needs its optional dependencies. Install them with: "
                'python -m pip install -e ".[ui]"'
            ) from exc
        raise
    from .review_ui import ReviewWorkspace
    from .view_api import create_api

    async def review_page():
        await ReviewWorkspace(library).build()

    app = create_api(library)
    ui.run_with(
        app,
        root=review_page,
        title="intextum · Document review",
        favicon="📄",
        dark=False,
        show_welcome_message=False,
    )
    return app


def serve(
    database: Path,
    *,
    input_dir: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    schemas: Path | None = None,
) -> None:
    library = Library(database, input_dir, schemas)
    app = build_app(library)
    import uvicorn

    url = f"http://{host}:{port}/"
    print(f"{len(library.index())} group(s) from {library.database}", file=sys.stderr)
    print(f"serving {url} (ctrl-c to stop)", file=sys.stderr)
    timer = threading.Timer(1.0, webbrowser.open, args=[url])
    timer.daemon = True
    if open_browser:
        timer.start()
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)
    finally:
        timer.cancel()
