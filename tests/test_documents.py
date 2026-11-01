from concurrent.futures import ThreadPoolExecutor

import pytest

from intextum_cli.convert import Converter, file_digest
from intextum_cli.document_cache import DocumentStore
from intextum_cli.document_model import resolve_evidence
from intextum_cli.document_render import render_document
from intextum_cli.source import build_source, locate
from intextum_cli.view import Library


@pytest.fixture
def document():
    from docling_core.types.doc import (
        DocItemLabel,
        DoclingDocument,
        ImageRef,
        TableCell,
        TableData,
    )
    from PIL import Image

    doc = DoclingDocument(name="Review document")
    doc.add_text(label=DocItemLabel.SECTION_HEADER, text="Invoice 4711")
    doc.add_text(
        label=DocItemLabel.TEXT, text='Total: 12.50 EUR <script>alert("x")</script>'
    )
    doc.add_table(
        data=TableData(
            num_rows=2,
            num_cols=2,
            table_cells=[
                TableCell(
                    text="Items",
                    col_span=2,
                    column_header=True,
                    start_row_offset_idx=0,
                    end_row_offset_idx=1,
                    start_col_offset_idx=0,
                    end_col_offset_idx=2,
                ),
                TableCell(
                    text="Widget",
                    start_row_offset_idx=1,
                    end_row_offset_idx=2,
                    start_col_offset_idx=0,
                    end_col_offset_idx=1,
                ),
                TableCell(
                    text="12.50",
                    start_row_offset_idx=1,
                    end_row_offset_idx=2,
                    start_col_offset_idx=1,
                    end_col_offset_idx=2,
                ),
            ],
        )
    )
    doc.add_picture(image=ImageRef.from_pil(Image.new("RGB", (8, 8), "red"), dpi=72))
    return doc


def mock_converter(monkeypatch, document, calls=None):
    def convert(self, path, force_ocr=None):
        if calls is not None:
            calls.append(str(path))
        self._converted_document = document
        return [
            document.export_to_markdown(escape_html=False, escape_underscores=False)
        ], False

    monkeypatch.setattr(Converter, "_convert_with_docling", convert)


def make_library(tmp_path):
    from intextum_cli.store import WorkspaceStore

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    path = inbox / "invoice.docx"
    path.write_bytes(b"docx")
    store = WorkspaceStore(tmp_path / "results.sqlite", create=True)
    store.set_workspace(inbox)
    key = DocumentStore.key(file_digest(path), path.suffix)
    store.cache.save_conversion(
        key, file_digest(path), path.suffix, ["Original cached source text"], False, []
    )
    store.results.save(
        {
            "group": "invoice",
            "files": ["invoice.docx"],
            "status": "completed",
            "fields": {"total": {"value": 12.5}},
            "review_reasons": [],
            "needs_review": False,
        },
        [],
        [{"path": "invoice.docx", "digest": file_digest(path), "key": key}],
    )
    lib = Library(store.path)
    lib.edit("invoice", "total", 13.5)
    return lib


def workspace(tmp_path):
    from intextum_cli.store import WorkspaceStore

    return WorkspaceStore(tmp_path / "workspace.sqlite", create=True)


def test_full_document_roundtrip_assets_and_source_refs(
    tmp_path, monkeypatch, document
):
    mock_converter(monkeypatch, document)
    path = tmp_path / "invoice.docx"
    path.write_bytes(b"docx")
    store = workspace(tmp_path)
    converter = Converter(store)
    converted = converter.convert(path)
    manifest, cached = converter.documents.read(converted.document_key)
    assert cached["tables"][0]["data"]["table_cells"][0]["col_span"] == 2
    assert len(manifest["assets"]) == 1
    filename = manifest["assets"][0]
    assert converter.documents.asset(converted.document_key, filename).startswith(
        b"\x89PNG"
    )
    assert cached["pictures"][0]["image"]["uri"] == f"assets/{filename}"
    public = converter.documents.public_document(converted.document_key)
    assert public["pictures"][0]["image"]["uri"].startswith("/api/document/assets/")
    evidence = locate("Widget", build_source([converted], max_chars=10000))[1]
    assert evidence["document_key"] == converted.document_key
    assert evidence["element_refs"] == ["#/tables/0"]
    again = Converter(store).convert(path)
    assert again.text == converted.text and again.elements == converted.elements


def test_build_preserves_extraction_text_results_and_edits(
    tmp_path, monkeypatch, document
):
    calls = []
    mock_converter(monkeypatch, document, calls)
    lib = make_library(tmp_path)
    before_text = lib.text("invoice.docx", "invoice")
    before_result = lib.result("invoice")
    assert lib.document_status("invoice.docx", "invoice")["status"] == "missing"
    assert calls == []
    assert lib.build_document("invoice.docx", "invoice")["status"] == "ready"
    assert len(calls) == 1
    assert lib.text("invoice.docx", "invoice") == before_text
    assert lib.result("invoice") == before_result
    lib.build_document("invoice.docx", "invoice")
    assert len(calls) == 1


def test_build_requests_for_same_file_are_coalesced(tmp_path, monkeypatch, document):
    calls = []
    mock_converter(monkeypatch, document, calls)
    lib = make_library(tmp_path)
    other = Library(lib.database)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda library: library.build_document("invoice.docx", "invoice"),
                [lib, other],
            )
        )
    assert all(result["status"] == "ready" for result in results)
    assert len(calls) == 1


def test_build_retains_recorded_ocr_settings(tmp_path, monkeypatch, document):
    import json

    lib = make_library(tmp_path)
    source = lib.store.results.source("invoice", "invoice.docx")
    settings = {
        "ocr": "force",
        "ocr_engine": "tesseract",
        "ocr_languages": ["deu"],
        "table_mode": "predicted",
        "detect_marks": True,
    }
    with lib.store.connection() as db:
        db.execute(
            "UPDATE conversions SET settings=? WHERE key=?",
            (json.dumps(settings), source["conversion_key"]),
        )
    seen = []

    def recognize(self, path, force_ocr=None):
        seen.append(
            (
                self.force_ocr,
                self.ocr_engine,
                self.ocr_languages,
                self.table_mode,
                self.detect_marks,
            )
        )
        self._converted_document = document
        return ["Rebuilt document text"], False

    monkeypatch.setattr(Converter, "_convert_with_docling", recognize)
    assert lib.build_document("invoice.docx", "invoice")["status"] == "ready"
    assert seen == [(True, "tesseract", ("deu",), "predicted", True)]


def test_corrupt_view_and_missing_images_can_be_rebuilt(
    tmp_path, monkeypatch, document
):
    calls = []
    mock_converter(monkeypatch, document, calls)
    lib = make_library(tmp_path)
    key = lib.build_document("invoice.docx", "invoice")["key"]
    store = lib.documents
    asset = store.read(key)[0]["assets"][0]
    with lib.store.connection() as db:
        db.execute("DELETE FROM document_assets WHERE conversion_key=?", (key,))
    assert lib.document_status("invoice.docx", "invoice")["needs_rebuild"]
    assert lib.build_document("invoice.docx", "invoice")["status"] == "ready"
    assert store.asset(key, asset) is not None
    with lib.store.connection() as db:
        db.execute("UPDATE conversions SET document='{' WHERE key=?", (key,))
    assert lib.document_status("invoice.docx", "invoice")["status"] == "missing"
    assert lib.text("invoice.docx", "invoice")["pages"] == [
        "Original cached source text"
    ]
    assert lib.build_document("invoice.docx", "invoice")["status"] == "ready"
    assert len(calls) == 3


def test_changed_original_does_not_replace_pinned_document(
    tmp_path, monkeypatch, document
):
    mock_converter(monkeypatch, document)
    lib = make_library(tmp_path)
    key = lib.build_document("invoice.docx", "invoice")["key"]
    (lib.input_dir / "invoice.docx").write_bytes(b"changed")
    assert lib.document_status("invoice.docx", "invoice")["key"] == key
    assert lib.document_json("other.docx", key, "invoice") is None
    assert lib.document_json("../outside.docx", key, "invoice") is None
    assert (
        "changed since extraction"
        in lib.build_document("invoice.docx", "invoice")["error"]
    )
    assert lib.document_status("invoice.docx", "invoice")["key"] == key


def test_document_key_tracks_versions_ocr_extension_and_options(tmp_path, monkeypatch):
    from intextum_cli import document_cache

    key = DocumentStore.key("file", ".docx")
    assert key != DocumentStore.key("file", ".txt")
    assert key != DocumentStore.key("file", ".docx", True)
    monkeypatch.setattr(document_cache, "package_version", lambda name: "new-version")
    assert key != DocumentStore.key("file", ".docx")
    monkeypatch.setattr(document_cache, "DOCUMENT_FORMAT", 2)
    assert key != DocumentStore.key("file", ".docx")


def test_evidence_requires_unique_match_when_refs_are_unavailable(
    tmp_path, monkeypatch, document
):
    mock_converter(monkeypatch, document)
    lib = make_library(tmp_path)
    key = lib.build_document("invoice.docx", "invoice")["key"]
    manifest = lib.document_record("invoice.docx", "invoice")[0]
    assert resolve_evidence(manifest, {"snippet": "Widget"}) == (["#/tables/0"], None)
    refs, warning = resolve_evidence(manifest, {"snippet": "12.50"})
    assert refs == [] and "uniquely" in warning
    assert resolve_evidence(
        manifest, {"document_key": key, "element_refs": ["#/tables/0"]}
    ) == (["#/tables/0"], None)
    assert (
        resolve_evidence(
            manifest,
            {
                "document_key": "stale",
                "element_refs": ["#/tables/0"],
                "snippet": "absent",
            },
        )[0]
        == []
    )


def test_cached_html_is_readable_and_untrusted_content_cannot_execute(
    tmp_path, monkeypatch, document
):
    pytest.importorskip("nh3")
    mock_converter(monkeypatch, document)
    lib = make_library(tmp_path)
    key = lib.build_document("invoice.docx", "invoice")["key"]
    rendered = render_document(lib.document_json("invoice.docx", key, "invoice"))
    assert 'data-doc-ref="#/tables/0"' in rendered
    assert 'colspan="2"' in rendered
    assert "&lt;script&gt;" in rendered and "<script>" not in rendered
    assert "/api/document/assets/" in rendered
    data = lib.document_json("invoice.docx", key, "invoice")
    data["pictures"][0]["image"]["uri"] = "https://example.invalid/tracker.png"
    assert "tracker.png" not in render_document(data)
    assert lib.documents.asset(key, "../secret.png") is None
    assert lib.documents.asset("not-a-key", "secret.png") is None


def test_document_api_reads_without_conversion_and_build_is_explicit(
    tmp_path, monkeypatch, document
):
    pytest.importorskip("nicegui")
    from fastapi.testclient import TestClient

    from intextum_cli.view_api import create_api

    calls = []
    mock_converter(monkeypatch, document, calls)
    lib = make_library(tmp_path)
    params = {"file": "invoice.docx", "group": "invoice"}
    with TestClient(create_api(lib)) as client:
        assert client.get("/api/document", params=params).json()["status"] == "missing"
        assert calls == []
        state = client.post("/api/document/build", json=params).json()
        key = state["key"]
        assert len(calls) == 1
        query = {**params, "key": key}
        assert (
            client.get("/api/document/json", params=query).json()["schema_name"]
            == "DoclingDocument"
        )
        response = client.get("/api/document/html", params=query)
        assert (
            response.status_code == 200
            and "script-src 'none'" in response.headers["content-security-policy"]
        )
        filename = lib.document_record("invoice.docx", "invoice")[0]["assets"][0]
        assert client.get(f"/api/document/assets/{key}/{filename}").content.startswith(
            b"\x89PNG"
        )
        assert client.get(f"/api/document/assets/{key}/secrets.png").status_code == 404
        assert (
            client.get(
                "/api/document/json", params={**query, "file": "../secret"}
            ).status_code
            == 404
        )
        assert client.get("/vendor/docling-components.js").status_code == 200
        assert client.get("/document-viewer").status_code == 200
        assert len(calls) == 1


def test_plain_reader_has_document_structure_without_docling_conversion(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        Converter,
        "_document_converter",
        lambda *args: pytest.fail("plain text loaded recognition"),
    )
    path = tmp_path / "notes.txt"
    path.write_text(
        "First paragraph with some text.\n\nSecond paragraph with more text."
    )
    converted = Converter(workspace(tmp_path)).convert(path)
    assert converted.document_key and len(converted.elements) == 2


def test_partial_recognition_is_not_cached_as_complete(tmp_path, monkeypatch, document):
    from types import SimpleNamespace

    result = SimpleNamespace(
        document=document,
        status=SimpleNamespace(value="partial_success"),
        errors=[SimpleNamespace(error_message="Recognition timed out")],
    )
    monkeypatch.setattr(
        Converter,
        "_document_converter",
        lambda *args: SimpleNamespace(convert=lambda path: result),
    )
    path = tmp_path / "slow.docx"
    path.write_bytes(b"docx")
    store = workspace(tmp_path)
    converted = Converter(store).convert(path)
    assert "incomplete" in converted.error and "timed out" in converted.error
    assert not converted.document_key
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM conversions").fetchone()[0] == 0


def test_view_preparation_failure_keeps_usable_text(tmp_path, monkeypatch, document):
    mock_converter(monkeypatch, document)
    monkeypatch.setattr(
        DocumentStore,
        "prepare",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad view")),
    )
    path = tmp_path / "invoice.docx"
    path.write_bytes(b"docx")
    store = workspace(tmp_path)
    converted = Converter(store).convert(path)
    assert converted.error is None and "Invoice 4711" in converted.text
    assert converted.conversion_key and not converted.document_key
    assert "Document view could not be cached" in converted.notes[0]
    assert Converter(store).convert(path).text == converted.text


def test_reading_damaged_text_never_starts_conversion(tmp_path, monkeypatch):
    lib = make_library(tmp_path)
    monkeypatch.setattr(
        Converter, "convert", lambda *args: pytest.fail("read started conversion")
    )
    with lib.store.connection() as db:
        db.execute("UPDATE conversions SET pages='{' ")
    assert lib.text("invoice.docx", "invoice") == {
        "cached": False,
        "pages": [],
        "notes": [],
    }


def test_slow_previous_file_cannot_replace_current_view(tmp_path, monkeypatch):
    pytest.importorskip("nicegui")
    import asyncio

    from nicegui import run, ui
    from nicegui.testing import user_simulation
    from nicegui.testing.general import nicegui_reset_globals

    from intextum_cli.view_document import DocumentPane

    lib = make_library(tmp_path)
    monkeypatch.setattr(
        lib, "text", lambda name, convert=False: {"cached": True, "pages": [name]}
    )
    monkeypatch.setattr(lib, "document_status", lambda *args: {"status": "missing"})

    async def scenario():
        gates = {name: asyncio.Event() for name in ("first.txt", "second.txt")}
        started = {name: asyncio.Event() for name in gates}

        async def delayed(function, *args):
            value = function(*args)
            name = value[0]["pages"][0]
            started[name].set()
            await gates[name].wait()
            return value

        monkeypatch.setattr(run, "io_bound", delayed)

        async def page():
            pane = DocumentPane(lib)
            pane.build()
            pane.picker.options = ["first.txt", "second.txt"]
            first = asyncio.create_task(pane.select_file("first.txt"))
            await started["first.txt"].wait()
            second = asyncio.create_task(pane.select_file("second.txt"))
            await started["second.txt"].wait()
            gates["second.txt"].set()
            await second
            gates["first.txt"].set()
            await first
            assert pane.file == "second.txt"
            assert pane.data["pages"] == ["second.txt"]
            ui.label("Latest file retained")

        async with user_simulation(page) as user:
            await user.open("/")
            await user.should_see("Latest file retained")

    try:
        asyncio.run(scenario())
    finally:
        # NiceGUI's simulation resets routes on entry; reset once more before
        # later run_with/TestClient tests build another application.
        with nicegui_reset_globals():
            pass


def test_compact_tables_drop_padding_but_keep_cells_and_alignment():
    from intextum_cli.document_model import compact_tables

    padded = (
        "Note | not a table\n"
        "|   No. | Code   | A \\| B   |\n"
        "|------:|:-------|----------|\n"
        "|     1 | 26/1   |          |"
    )
    assert compact_tables(padded) == (
        "Note | not a table\n"
        "| No. | Code | A \\| B |\n"
        "| ---: | :--- | --- |\n"
        "| 1 | 26/1 |  |"
    )


def test_compact_table_text_maps_to_the_table_element(tmp_path, monkeypatch, document):
    from intextum_cli.document_model import compact_tables

    def convert(self, path, force_ocr=None):
        self._converted_document = document
        markdown = document.export_to_markdown(
            escape_html=False, escape_underscores=False
        )
        return [compact_tables(markdown)], False

    monkeypatch.setattr(Converter, "_convert_with_docling", convert)
    path = tmp_path / "invoice.docx"
    path.write_bytes(b"docx")
    converted = Converter(workspace(tmp_path)).convert(path)
    assert "| Widget | 12.50 |" in converted.text
    evidence = locate("Widget", build_source([converted], max_chars=10000))[1]
    assert evidence["element_refs"] == ["#/tables/0"]
