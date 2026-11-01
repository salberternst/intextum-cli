"""File and correction endpoints for the optional NiceGUI application."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from .document_render import render_document
from .review_state import ReviewConflict
from .store import StorageError
from .view import Library

INLINE_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".txt", ".csv"}


class EditRequest(BaseModel):
    field: str = Field(min_length=1)
    value: Any = None
    note: str = ""
    revision: str | None = None


class DocumentBuildRequest(BaseModel):
    file: str
    group: str = ""


class ReviewRequest(BaseModel):
    action: str
    revision: str = Field(min_length=1)
    class_name: str | None = None
    note: str = ""


class ExtractRequest(BaseModel):
    revision: str = Field(min_length=1)


def create_api(library: Library) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None)

    @app.get("/review.css", include_in_schema=False)
    def stylesheet():
        return FileResponse(Path(__file__).parent / "static" / "review.css")

    static = Path(__file__).parent / "static"

    @app.get("/document-viewer")
    def document_viewer():
        return FileResponse(
            static / "document-viewer.html",
            headers={
                "Content-Security-Policy": (
                    "default-src 'none'; script-src 'self'; "
                    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                    "connect-src 'self'; frame-src 'self'; "
                    "frame-ancestors 'self'; base-uri 'none'"
                ),
            },
        )

    @app.get("/document-viewer.js")
    def document_script():
        return FileResponse(static / "document-viewer.js", media_type="text/javascript")

    @app.get("/document.css")
    def document_css():
        return FileResponse(static / "document.css", media_type="text/css")

    @app.get("/vendor/docling-components.js")
    def document_components():
        return FileResponse(
            static / "vendor" / "docling-components.js", media_type="text/javascript"
        )

    @app.get("/api/document")
    def document_status(file: str, group: str):
        return library.document_status(file, group)

    @app.post("/api/document/build")
    def build_document(payload: DocumentBuildRequest):
        return library.build_document(payload.file, payload.group)

    @app.get("/api/document/json")
    def document_json(file: str, key: str, group: str):
        document = library.document_json(file, key, group)
        if document is None:
            raise HTTPException(404, "Document view not found")
        return document

    @app.get("/api/document/html")
    def document_html(file: str, key: str, group: str):
        document = library.document_json(file, key, group)
        if document is None:
            raise HTTPException(404, "Document view not found")
        return HTMLResponse(
            render_document(document),
            headers={
                "Content-Security-Policy": (
                    "default-src 'none'; img-src 'self'; style-src 'self'; "
                    "script-src 'none'; frame-ancestors 'self'; base-uri 'none'"
                ),
            },
        )

    @app.get("/api/document/assets/{key}/{filename}")
    def document_asset(key: str, filename: str):
        asset = library.documents.asset(key, filename)
        if asset is None:
            raise HTTPException(404, "Image not found")
        return Response(
            asset,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=31536000, immutable",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/api/index")
    def index():
        return {
            "input": str(library.input_dir) if library.input_dir else None,
            "database": str(library.database),
            "groups": library.index(),
        }

    @app.get("/api/group/{slug}")
    def group(slug: str):
        result = library.result(slug)
        if result is None:
            raise HTTPException(404, "Group not found")
        return result

    @app.get("/api/export/{slug}")
    def export(slug: str):
        result = library.result(slug)
        if result is None:
            raise HTTPException(404, "Group not found")
        return Response(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    "attachment; filename*=UTF-8''" + quote(slug + ".json")
                )
            },
        )

    @app.get("/api/text")
    def text(file: str, group: str):
        return library.text(file, group)

    @app.get("/api/raw")
    def raw(file: str, download: bool = False):
        path = library.file(file)
        if path is None:
            raise HTTPException(404, "File not found")
        disposition = (
            "inline"
            if not download and path.suffix.lower() in INLINE_SUFFIXES
            else "attachment"
        )
        return FileResponse(
            path,
            media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            filename=path.name,
            content_disposition_type=disposition,
        )

    @app.post("/api/edit/{slug}")
    def edit(slug: str, payload: EditRequest):
        try:
            return library.edit(
                slug, payload.field, payload.value, payload.note, payload.revision
            )
        except KeyError as exc:
            raise HTTPException(404, "Group or field not found") from exc
        except ReviewConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except (OSError, StorageError) as exc:
            raise HTTPException(500, "Could not save this correction") from exc

    @app.post("/api/review/{slug}")
    def review(slug: str, payload: ReviewRequest):
        try:
            return library.review_action(
                slug, payload.action, payload.revision, payload.class_name, payload.note
            )
        except KeyError as exc:
            raise HTTPException(404, "Group not found") from exc
        except ReviewConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except (OSError, StorageError) as exc:
            raise HTTPException(500, "Could not save this review decision") from exc

    @app.post("/api/reextract/{slug}")
    def reextract(slug: str, payload: ExtractRequest):
        try:
            return library.reextract(slug, payload.revision)
        except KeyError as exc:
            raise HTTPException(404, "Group not found") from exc
        except ReviewConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except (OSError, StorageError) as exc:
            raise HTTPException(500, "Could not re-extract this group") from exc

    return app
