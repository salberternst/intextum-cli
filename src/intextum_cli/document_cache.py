"""Portable Docling documents, local image assets and evidence element indexes."""

from __future__ import annotations

import hashlib
import importlib.metadata
import io
import json
import logging
import re
from collections.abc import Sequence

from .document_model import element_index
from .store import WorkspaceStore

logger = logging.getLogger(__name__)
DOCUMENT_FORMAT = 1
KEY_PATTERN = re.compile(r"[a-f0-9]{64}\Z")
ASSET_PATTERN = re.compile(r"[a-f0-9]{64}\.png\Z")


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


class DocumentStore:
    def __init__(self, store: WorkspaceStore):
        self.store = store

    @staticmethod
    def options(
        digest: str,
        suffix: str,
        force_ocr: bool = False,
        *,
        ocr_engine: str = "auto",
        ocr_languages: Sequence[str] = (),
        table_mode: str = "ruled",
        detect_marks: bool = False,
    ) -> dict:
        return {
            "format": DOCUMENT_FORMAT,
            "text_format": 6,
            "file": digest,
            "suffix": suffix.lower(),
            "docling": package_version("docling"),
            "core": package_version("docling-core"),
            "ocr": "force" if force_ocr else "auto",
            "ocr_engine": ocr_engine,
            "ocr_languages": list(ocr_languages),
            "table_mode": table_mode,
            "detect_marks": detect_marks,
            "page_images": True,
            "picture_images": True,
            "images_scale": 1.0,
        }

    @staticmethod
    def key(
        digest: str,
        suffix: str,
        force_ocr: bool = False,
        *,
        ocr_engine: str = "auto",
        ocr_languages: Sequence[str] = (),
        table_mode: str = "ruled",
        detect_marks: bool = False,
    ) -> str:
        options = DocumentStore.options(
            digest,
            suffix,
            force_ocr,
            ocr_engine=ocr_engine,
            ocr_languages=ocr_languages,
            table_mode=table_mode,
            detect_marks=detect_marks,
        )
        return hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()

    def read(self, key: str) -> tuple[dict, dict] | None:
        if not KEY_PATTERN.fullmatch(key):
            return None
        cached = self.store.cache.conversion(key)
        if cached is None or cached.manifest is None or cached.document is None:
            return None
        try:
            manifest, document = cached.manifest, cached.document
            if (
                manifest.get("format") != DOCUMENT_FORMAT
                or manifest.get("key") != key
                or not isinstance(manifest.get("pages"), list)
                or not all(isinstance(page, str) for page in manifest["pages"])
                or not isinstance(manifest.get("paged"), bool)
                or not isinstance(manifest.get("notes"), list)
                or not all(isinstance(note, str) for note in manifest["notes"])
                or not isinstance(manifest.get("assets"), list)
                or not all(
                    isinstance(name, str) and ASSET_PATTERN.fullmatch(name)
                    for name in manifest["assets"]
                )
                or not isinstance(manifest.get("image_pages"), list)
                or not isinstance(manifest.get("elements"), list)
                or not all(
                    isinstance(entry, dict)
                    and isinstance(entry.get("ref"), str)
                    and isinstance(entry.get("page_index"), int)
                    and isinstance(entry.get("start"), int)
                    and isinstance(entry.get("end"), int)
                    and 0 <= entry["page_index"] < len(manifest["pages"])
                    and 0
                    <= entry["start"]
                    <= entry["end"]
                    <= len(manifest["pages"][entry["page_index"]])
                    for entry in manifest["elements"]
                )
                or document.get("schema_name") != "DoclingDocument"
            ):
                return None
            from docling_core.types.doc import DoclingDocument

            DoclingDocument.model_validate(document)
            return manifest, document
        except (OSError, ValueError, TypeError, AttributeError):
            return None

    def asset(self, key: str, filename: str) -> bytes | None:
        if not KEY_PATTERN.fullmatch(key) or not ASSET_PATTERN.fullmatch(filename):
            return None
        return self.store.cache.asset(key, filename)

    def complete(self, key: str) -> bool:
        cached = self.read(key)
        return cached is not None and all(
            self.asset(key, filename) is not None for filename in cached[0]["assets"]
        )

    def save(
        self,
        key: str,
        document,
        *,
        digest: str,
        pages: list[str],
        paged: bool,
        notes: list[str],
        force_ocr: bool = False,
        suffix: str,
        ocr_engine: str = "auto",
        ocr_languages: Sequence[str] = (),
        table_mode: str = "ruled",
        detect_marks: bool = False,
    ) -> dict:
        manifest, data, assets = self.prepare(
            key,
            document,
            digest=digest,
            pages=pages,
            paged=paged,
            notes=notes,
            force_ocr=force_ocr,
        )
        self.store.cache.save_conversion(
            key,
            digest,
            suffix,
            pages,
            paged,
            notes,
            manifest,
            data,
            assets,
            settings=self.options(
                digest,
                suffix,
                force_ocr,
                ocr_engine=ocr_engine,
                ocr_languages=ocr_languages,
                table_mode=table_mode,
                detect_marks=detect_marks,
            ),
            preserve_text=True,
        )
        return manifest

    def prepare(
        self,
        key: str,
        document,
        *,
        digest: str,
        pages: list[str],
        paged: bool,
        notes: list[str],
        force_ocr: bool = False,
    ) -> tuple[dict, dict, dict[str, bytes]]:
        data = document.export_to_dict()
        filenames: set[str] = set()
        assets: dict[str, bytes] = {}
        warnings = list(notes)

        def keep_image(item, output: dict) -> bool:
            image_ref = getattr(item, "image", None)
            try:
                # Never follow document-supplied remote or filesystem URIs.
                image = None
                if image_ref is not None and (
                    getattr(image_ref, "_pil", None) is not None
                    or str(image_ref.uri).startswith("data:image/")
                ):
                    image = image_ref.pil_image
                if image is None and hasattr(item, "get_image"):
                    provenance = getattr(item, "prov", [])
                    page = (
                        document.pages.get(provenance[0].page_no)
                        if provenance
                        else None
                    )
                    if (
                        page
                        and page.image
                        and (
                            getattr(page.image, "_pil", None) is not None
                            or str(page.image.uri).startswith("data:image/")
                        )
                    ):
                        image = item.get_image(document)
                if image is None:
                    output.pop("image", None)
                    return False
                stream = io.BytesIO()
                image.save(stream, format="PNG")
                raw = stream.getvalue()
                filename = hashlib.sha256(raw).hexdigest() + ".png"
                assets[filename] = raw
                filenames.add(filename)
                output["image"] = {
                    "mimetype": "image/png",
                    "dpi": getattr(image_ref, "dpi", 72),
                    "size": {"width": image.width, "height": image.height},
                    "uri": f"assets/{filename}",
                }
                return True
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                logger.debug("cannot retain document image: %s", exc)
                output.pop("image", None)
                return False

        for index, picture in enumerate(document.pictures):
            if not keep_image(picture, data["pictures"][index]):
                warnings.append(
                    f"Image {index + 1} is unavailable; showing its recognized content."
                )
        image_pages = []
        for number, page in document.pages.items():
            if keep_image(page, data["pages"][str(number)]):
                image_pages.append(number)
        manifest = {
            "format": DOCUMENT_FORMAT,
            "key": key,
            "file_digest": digest,
            "docling": package_version("docling"),
            "core": package_version("docling-core"),
            "force_ocr": force_ocr,
            "pages": pages,
            "paged": paged,
            "notes": list(dict.fromkeys(warnings)),
            "assets": sorted(filenames),
            "image_pages": image_pages,
            "elements": element_index(document, pages, paged),
        }
        return manifest, data, assets

    def public_document(self, key: str) -> dict | None:
        cached = self.read(key)
        if cached is None:
            return None
        manifest, data = cached

        def rewrite(node):
            if isinstance(node, dict):
                if "uri" in node:
                    filename = str(node["uri"]).removeprefix("assets/")
                    node["uri"] = (
                        f"/api/document/assets/{key}/{filename}"
                        if filename in manifest["assets"]
                        else ""
                    )
                for value in node.values():
                    rewrite(value)
            elif isinstance(node, list):
                for value in node:
                    rewrite(value)

        rewrite(data)
        return data
