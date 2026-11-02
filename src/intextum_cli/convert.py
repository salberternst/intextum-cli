"""File → text conversion with Docling, cached by file content."""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path

from .config import DEFAULT_DOCUMENT_TIMEOUT, OCR_ENGINES, TABLE_MODES
from .conversion_marks import mark_cancellations
from .conversion_readers import read_csv_text, read_msg_text
from .conversion_recovery import restore_recognized_text
from .conversion_tables import restore_ruled_tables
from .document_cache import DocumentStore
from .document_model import compact_tables, extraction_layers, synthetic_document
from .store import WorkspaceStore
from .store_records import SourceReference

logger = logging.getLogger(__name__)

_PAGE_BREAK = "\n<!-- intextum-page-break -->\n"
# A file has text if it has at least this many letters (after dropping image
# placeholders), or at least MIN_ID_LABELS identifier-style numbers such as
# "12_3_456" or "205/1" (drawings and maps often carry nothing else). Plain digit
# runs do not count: a broken font layer can yield long numbers and nothing else.
MIN_CONTENT_CHARS = 20
MIN_ID_LABELS = 2
_ID_LABEL_RE = re.compile(
    r"(?<![\d_/])\d{1,6}(?:_\d{1,6}){0,3}/\d{1,4}(?![\d/])|(?<![\d_/])\d{1,6}(?:_\d{1,6}){2,3}(?![\d_])"
)
_PLACEHOLDER_RE = re.compile(r"<!--.*?-->", re.S)
_WORD_CHARS_RE = re.compile(r"[^\W\d_]")

PLAIN_TEXT_SUFFIXES = frozenset({".txt", ".text", ".log", ".json", ".xml"})
DOCLING_SUFFIXES = frozenset(
    {
        ".pdf",
        ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp",
        ".docx", ".docm", ".dotx", ".dotm", ".xlsx", ".xlsm", ".xltx",
        ".pptx", ".pptm", ".ppsx", ".potx",
        ".odt", ".ott", ".ods", ".ots", ".odp", ".otp",
        ".html", ".htm", ".xhtml", ".mhtml", ".mht",
        ".eml", ".msg", ".epub", ".tex", ".vtt",
        ".md", ".qmd", ".rmd", ".csv", ".adoc", ".asciidoc",
    }
)  # fmt: skip
# Legacy formats Docling supports only with LibreOffice installed.
LEGACY_OFFICE_SUFFIXES = frozenset(
    {".doc", ".dot", ".rtf", ".xls", ".xlt", ".ppt", ".pps", ".pot"}
)
_LIBREOFFICE_APP = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")


# Metadata sidecars written by GIS tools next to .shp or raster files.
_SIDECAR_SUFFIXES = (".shp.xml", ".aux.xml")


def is_supported(path: Path) -> bool:
    """Whether a file type can be turned into text at all."""
    if path.name.lower().endswith(_SIDECAR_SUFFIXES):
        return False
    suffix = path.suffix.lower()
    return suffix in PLAIN_TEXT_SUFFIXES | DOCLING_SUFFIXES | LEGACY_OFFICE_SUFFIXES


def has_libreoffice() -> bool:
    return bool(
        shutil.which("soffice")
        or shutil.which("libreoffice")
        or _LIBREOFFICE_APP.is_file()
    )


@dataclass
class ConvertedFile:
    """Text of one file, split by page when the format has pages."""

    name: str
    pages: list[str] = field(default_factory=list)
    paged: bool = False
    error: str | None = None
    # How the text was obtained when it was not a plain Docling conversion.
    notes: list[str] = field(default_factory=list)
    conversion_key: str | None = None
    document_key: str | None = None
    elements: list[dict] = field(default_factory=list)
    digest: str | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(self.pages)

    @property
    def source_reference(self) -> SourceReference:
        """The source identity captured with this particular conversion."""
        if self.digest is None:
            raise ValueError(
                "source references require a converted file's content hash"
            )
        return {"path": self.name, "digest": self.digest, "key": self.conversion_key}

    @property
    def has_text(self) -> bool:
        """False for files without real content, e.g. scans without OCR text."""
        return self.error is None and _has_content(self.pages)


def _has_content(pages: list[str]) -> bool:
    content = _PLACEHOLDER_RE.sub(" ", "\n\n".join(pages))
    return (
        len(_WORD_CHARS_RE.findall(content)) >= MIN_CONTENT_CHARS
        or len(_ID_LABEL_RE.findall(content)) >= MIN_ID_LABELS
    )


_DIGESTS: dict[tuple[str, int, int], str] = {}


def file_digest(path: Path) -> str:
    """SHA-256 of a file's content, memoised per path, size and modification time."""
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in _DIGESTS:
        _DIGESTS[key] = _hash_file(path)
    return _DIGESTS[key]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def compact_text(text: str) -> str:
    """Strip trailing whitespace and collapse runs of blank lines."""
    lines: list[str] = []
    blank = False
    for line in text.splitlines():
        line = line.rstrip()
        if line:
            lines.append(line)
            blank = False
        elif not blank and lines:
            lines.append("")
            blank = True
    return "\n".join(lines).strip()


_OCR_SUFFIXES = frozenset({".pdf"}) | frozenset(
    {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
)


class Converter:
    """Converts files to text; the Docling pipeline is built on first use.

    Fallbacks when Docling produces nothing usable: CSV files Docling cannot
    read (non-UTF-8) and Outlook ``.msg`` files are read directly, and PDFs or
    images without text are converted again with full-page OCR. Each fallback is
    recorded in ``ConvertedFile.notes``.
    """

    def __init__(
        self,
        store: WorkspaceStore | None = None,
        *,
        force_ocr: bool = False,
        ocr_engine: str = "auto",
        ocr_languages: list[str] | tuple[str, ...] = (),
        table_mode: str = "ruled",
        detect_marks: bool = False,
        document_timeout: float = DEFAULT_DOCUMENT_TIMEOUT,
    ):
        if ocr_engine not in OCR_ENGINES:
            raise ValueError(f"unknown OCR engine: {ocr_engine}")
        if table_mode not in TABLE_MODES:
            raise ValueError(f"unknown table mode: {table_mode}")
        self.store = store
        self.force_ocr = force_ocr
        self.ocr_engine = ocr_engine
        self.ocr_languages = tuple(ocr_languages)
        self.table_mode = table_mode
        self.detect_marks = detect_marks
        self.document_timeout = document_timeout
        self._docling = None
        self._docling_ocr = None
        self._memory: dict[str, ConvertedFile] = {}
        self.documents = DocumentStore(store) if store else None
        self._conversion_lock = threading.RLock()
        self._converted_document = None
        self._body_empty = False

    def _document_converter(self, force_ocr: bool | None = None):
        force_ocr = self.force_ocr if force_ocr is None else force_ocr
        if force_ocr and not self.force_ocr:
            if self._docling_ocr is None:
                self._docling_ocr = self._build_docling(force_ocr=True)
            return self._docling_ocr
        if self._docling is None:
            self._docling = self._build_docling(force_ocr=self.force_ocr)
        return self._docling

    def _build_docling(self, *, force_ocr: bool):
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            TesseractCliOcrOptions,
        )
        from docling.document_converter import (
            DocumentConverter,
            ImageFormatOption,
            PdfFormatOption,
        )

        options = PdfPipelineOptions()
        options.do_ocr = True
        options.do_table_structure = True
        options.generate_page_images = True
        options.generate_picture_images = True
        options.images_scale = 1.0
        options.document_timeout = self.document_timeout
        if self.ocr_engine == "tesseract":
            options.ocr_options = TesseractCliOcrOptions()
        if self.ocr_languages:
            options.ocr_options.lang = list(self.ocr_languages)
        options.ocr_options.force_full_page_ocr = force_ocr
        # Predicted cells keep scanned entries and text spanning several columns
        # apart from the PDF's own text cells.
        options.table_structure_options.do_cell_matching = (
            self.table_mode != "predicted"
        )
        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=options),
                InputFormat.IMAGE: ImageFormatOption(pipeline_options=options),
            }
        )

    def cache_key(self, path: Path) -> str:
        # Document and text share one identity, including extension and Core version.
        return DocumentStore.key(
            file_digest(path),
            path.suffix,
            self.force_ocr,
            ocr_engine=self.ocr_engine,
            ocr_languages=self.ocr_languages,
            table_mode=self.table_mode,
            detect_marks=self.detect_marks,
        )

    def convert(self, path: Path, name: str | None = None) -> ConvertedFile:
        with self._conversion_lock:
            digest = file_digest(path)
            converted = self._convert(path, name)
            return replace(converted, digest=digest)

    def _from_cache(self, key: str, name: str) -> ConvertedFile | None:
        cached = self.store.cache.conversion(key) if self.store else None
        if cached is None:
            return None
        converted = ConvertedFile(
            name=name,
            pages=cached.pages,
            paged=bool(cached.paged),
            notes=cached.notes,
            conversion_key=key,
        )
        document = self.documents.read(key)
        if document and document[0]["pages"] == converted.pages:
            converted.document_key = key
            converted.elements = document[0]["elements"]
        return converted

    def build_document(self, path: Path) -> str:
        """Repair a structured view while preserving cached extraction text."""
        if self.store is None:
            raise RuntimeError("document storage is not configured")
        key = self.cache_key(path)
        with self._conversion_lock, self.store.lock("conversion:" + key):
            if self.documents.complete(key):
                return key
            if not is_supported(path) or path.stat().st_size == 0:
                raise ValueError("This file is empty or its format is unsupported.")
            digest = file_digest(path)
            self._converted_document = None
            pages, paged, notes = self._convert_uncached(path, path.suffix.lower())
            if file_digest(path) != digest:
                raise ValueError("The original changed while building its view.")
            if self._converted_document is None:
                raise RuntimeError("conversion did not return a structured document")
            self.documents.save(
                key,
                self._converted_document,
                digest=file_digest(path),
                pages=[compact_text(page) for page in pages],
                paged=paged,
                notes=notes,
                force_ocr=self.force_ocr,
                suffix=path.suffix.lower(),
                ocr_engine=self.ocr_engine,
                ocr_languages=self.ocr_languages,
                table_mode=self.table_mode,
                detect_marks=self.detect_marks,
            )
        return key

    def _convert(self, path: Path, name: str | None = None) -> ConvertedFile:
        name = name or path.name
        if not is_supported(path):
            return ConvertedFile(
                name=name, error=f"unsupported file type '{path.suffix.lower()}'"
            )
        if path.stat().st_size == 0:
            return ConvertedFile(name=name, error="empty file (0 bytes)")
        key = self.cache_key(path)
        if self.store:
            with self.store.lock("conversion:" + key):
                cached = self._from_cache(key, name)
                if cached is not None:
                    return cached
                return self._recognize(path, name, key)
        if key not in self._memory:
            self._memory[key] = self._recognize(path, name, key)
        return replace(self._memory[key], name=name)

    def _recognize(self, path: Path, name: str, key: str) -> ConvertedFile:
        digest = file_digest(path)
        try:
            self._converted_document = None
            pages, paged, notes = self._convert_uncached(path, path.suffix.lower())
        except Exception as exc:  # noqa: BLE001 - report and keep the group going
            logger.debug("conversion failed for %s", path, exc_info=True)
            return ConvertedFile(name=name, error=f"conversion failed: {exc}")
        if file_digest(path) != digest:
            return ConvertedFile(
                name=name, error="source changed during recognition; retry extraction"
            )
        pages = [compact_text(page) for page in pages]
        converted = ConvertedFile(name=name, pages=pages, paged=paged, notes=notes)
        if self.store:
            manifest, document, assets = None, None, None
            try:
                if self._converted_document is not None:
                    manifest, document, assets = self.documents.prepare(
                        key,
                        self._converted_document,
                        digest=file_digest(path),
                        pages=pages,
                        paged=paged,
                        notes=notes,
                        force_ocr=self.force_ocr,
                    )
            except (OSError, ValueError, TypeError) as exc:
                logger.warning("could not prepare document view for %s: %s", path, exc)
                notes.append(
                    "Document view could not be cached; extracted text is available."
                )
            self.store.cache.save_conversion(
                key,
                file_digest(path),
                path.suffix.lower(),
                pages,
                paged,
                notes,
                manifest,
                document,
                assets,
                settings=DocumentStore.options(
                    digest,
                    path.suffix,
                    self.force_ocr,
                    ocr_engine=self.ocr_engine,
                    ocr_languages=self.ocr_languages,
                    table_mode=self.table_mode,
                    detect_marks=self.detect_marks,
                ),
            )
            converted.conversion_key = key
            if manifest is not None:
                converted.document_key = key
                converted.elements = manifest["elements"]
        return converted

    def _convert_uncached(
        self, path: Path, suffix: str
    ) -> tuple[list[str], bool, list[str]]:
        if suffix in PLAIN_TEXT_SUFFIXES:
            pages = [path.read_text(encoding="utf-8", errors="replace")]
            self._converted_document = synthetic_document(path.name, pages)
            return pages, False, []
        if suffix in LEGACY_OFFICE_SUFFIXES and not has_libreoffice():
            # Docling's own error for this is generic; say what is missing.
            raise RuntimeError(
                f"{suffix} files require LibreOffice "
                "(macOS: brew install --cask libreoffice)"
            )
        try:
            pages, paged = self._convert_with_docling(path)
        except Exception:
            fallback = {".csv": read_csv_text, ".msg": read_msg_text}.get(suffix)
            if fallback is None:
                raise
            logger.info("docling could not read %s; using a fallback reader", path.name)
            pages, note = fallback(path)
            self._converted_document = synthetic_document(
                path.name, pages, tables=suffix == ".csv"
            )
            return pages, False, [note]

        if (
            suffix in _OCR_SUFFIXES
            and not self.force_ocr
            and (self._body_empty or not _has_content(pages))
        ):
            initial_document = self._converted_document
            logger.info("no text in %s; converting again with full-page OCR", path.name)
            try:
                ocr_pages, ocr_paged = self._convert_with_docling(path, force_ocr=True)
            except Exception:  # noqa: BLE001 - keep the first result
                logger.debug("OCR fallback failed for %s", path, exc_info=True)
            else:
                if _has_content(ocr_pages) and not self._body_empty:
                    return ocr_pages, ocr_paged, ["text from full-page OCR (fallback)"]
            self._converted_document = initial_document
        return pages, paged, []

    def _convert_with_docling(
        self, path: Path, *, force_ocr: bool | None = None
    ) -> tuple[list[str], bool]:
        logger.info("docling: converting %s", path.name)
        conversion = self._document_converter(force_ocr).convert(path)
        if (
            getattr(getattr(conversion, "status", None), "value", None)
            == "partial_success"
        ):
            details = "; ".join(error.error_message for error in conversion.errors)
            raise RuntimeError(
                "Document recognition was incomplete (possibly a timeout). "
                + (details or "Retry the conversion or inspect the original.")
            )
        document = conversion.document
        if self.table_mode == "ruled":
            tables = restore_ruled_tables(conversion, path)
            if tables:
                logger.info("restored %d ruled tables from %s", tables, path.name)
        # Restore first: tags in cell text would hide cells from its coverage check.
        restored = restore_recognized_text(conversion)
        if restored:
            logger.info("retained %d omitted text cells from %s", restored, path.name)
        if self.detect_marks:
            marked = mark_cancellations(conversion, path)
            if marked:
                logger.info("tagged %d marked elements in %s", marked, path.name)
        self._converted_document = document
        # A digital running footer alone must not prevent the OCR fallback.
        self._body_empty = not _has_content(
            [document.export_to_markdown(traverse_pictures=True)]
        )
        # Plain characters for the model: no &amp; entities or \\_ escapes.
        markdown = compact_tables(
            document.export_to_markdown(
                page_break_placeholder=_PAGE_BREAK,
                escape_html=False,
                escape_underscores=False,
                traverse_pictures=True,
                included_content_layers=extraction_layers(),
            )
        )
        paged = bool(document.pages)
        pages = markdown.split(_PAGE_BREAK) if paged else [markdown]
        return pages, paged
