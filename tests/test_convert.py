from types import SimpleNamespace

import pytest

from intextum_cli import convert
from intextum_cli.conversion_readers import read_csv_text
from intextum_cli.convert import ConvertedFile, Converter
from intextum_cli.store import WorkspaceStore


def test_unsupported_and_plain_text(tmp_path):
    (tmp_path / "a.xyz").write_text("?")
    (tmp_path / "b.txt").write_text("hello\n\n\n\nworld   \n")
    converter = Converter(WorkspaceStore(tmp_path / "workspace.sqlite", create=True))
    assert converter.convert(tmp_path / "a.xyz").error == "unsupported file type '.xyz'"
    converted = converter.convert(tmp_path / "b.txt")
    assert converted.pages == ["hello\n\nworld"] and not converted.paged
    with converter.store.connection() as db:
        assert db.execute("SELECT count(*) FROM conversions").fetchone()[0] == 1


def test_legacy_spreadsheet_without_libreoffice_explains_what_to_install(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(convert, "has_libreoffice", lambda: False)
    (tmp_path / "old.xls").write_bytes(b"\xd0\xcf\x11\xe0")
    result = Converter().convert(tmp_path / "old.xls")
    assert "require LibreOffice" in result.error


def test_cache_key_includes_docling_version_and_ocr_mode(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("hello")
    store = WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    normal = Converter(store)
    ocr = Converter(store, force_ocr=True)
    normal.convert(tmp_path / "a.txt")
    ocr.convert(tmp_path / "a.txt")
    assert normal.cache_key(tmp_path / "a.txt") != ocr.cache_key(tmp_path / "a.txt")
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM conversions").fetchone()[0] == 2


def test_ocr_engine_and_languages_have_separate_persistent_caches(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("Readable source text without OCR models")
    store = WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    converters = [
        Converter(store),
        Converter(store, ocr_engine="tesseract", ocr_languages=["deu"]),
        Converter(store, ocr_engine="tesseract", ocr_languages=["eng"]),
        Converter(store, table_mode="docling"),
        Converter(store, table_mode="predicted"),
        Converter(store, detect_marks=True),
    ]
    results = [converter.convert(path) for converter in converters]
    assert len({result.conversion_key for result in results}) == 6
    record = store.cache.conversion(results[1].conversion_key)
    assert record.settings["ocr_engine"] == "tesseract"
    assert record.settings["ocr_languages"] == ["deu"]
    assert record.settings["table_mode"] == "ruled"
    record = store.cache.conversion(results[4].conversion_key)
    assert record.settings["table_mode"] == "predicted"


def test_ocrmac_engine_reaches_docling_and_changes_the_cache_key(tmp_path):
    from docling.datamodel.base_models import InputFormat

    converter = Converter(ocr_engine="ocrmac", ocr_languages=["de-DE"])
    docling = converter._build_docling(force_ocr=False)
    options = docling.format_to_options[InputFormat.PDF].pipeline_options
    assert options.ocr_options.kind == "ocrmac"
    assert options.ocr_options.lang == ["de-DE"]
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"x")
    assert converter.cache_key(path) != Converter().cache_key(path)


def test_document_timeout_reaches_docling_without_changing_the_cache_key(tmp_path):
    from docling.datamodel.base_models import InputFormat

    docling = Converter(document_timeout=600)._build_docling(force_ocr=False)
    options = docling.format_to_options[InputFormat.PDF].pipeline_options
    assert options.document_timeout == 600
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"x")
    assert Converter(document_timeout=600).cache_key(path) == Converter().cache_key(
        path
    )


@pytest.mark.parametrize(
    "mode,matching", [("ruled", True), ("docling", True), ("predicted", False)]
)
def test_table_mode_selects_docling_cell_matching(mode, matching):
    from docling.datamodel.base_models import InputFormat

    docling = Converter(table_mode=mode)._build_docling(force_ocr=False)
    options = docling.format_to_options[InputFormat.PDF].pipeline_options
    assert options.table_structure_options.do_cell_matching is matching


@pytest.mark.parametrize("mode,reconstructed", [("ruled", 1), ("predicted", 0)])
def test_only_ruled_table_mode_reconstructs_ruled_forms(
    tmp_path, monkeypatch, mode, reconstructed
):
    from docling_core.types.doc import DoclingDocument

    document = DoclingDocument(name="form")
    document.add_text(label="text", text="Readable form text")
    conversion = SimpleNamespace(status=None, document=document, pages=[])
    calls = []
    monkeypatch.setattr(
        convert, "restore_ruled_tables", lambda *args: calls.append(args) or 0
    )
    converter = Converter(table_mode=mode)
    monkeypatch.setattr(
        converter,
        "_document_converter",
        lambda force_ocr=None: SimpleNamespace(convert=lambda path: conversion),
    )
    pages, _ = converter._convert_with_docling(tmp_path / "form.pdf")
    assert "Readable form text" in pages[0]
    assert len(calls) == reconstructed


@pytest.mark.parametrize("detect_marks,calls", [(False, 0), (True, 1)])
def test_marks_are_detected_only_when_switched_on(
    tmp_path, monkeypatch, detect_marks, calls
):
    from docling_core.types.doc import DoclingDocument

    document = DoclingDocument(name="form")
    document.add_text(label="text", text="Readable form text")
    conversion = SimpleNamespace(status=None, document=document, pages=[])
    seen = []
    monkeypatch.setattr(
        convert, "mark_cancellations", lambda *args: seen.append(args) or 0
    )
    converter = Converter(detect_marks=detect_marks)
    monkeypatch.setattr(
        converter,
        "_document_converter",
        lambda force_ocr=None: SimpleNamespace(convert=lambda path: conversion),
    )
    converter._convert_with_docling(tmp_path / "form.pdf")
    assert len(seen) == calls


def test_docling_tables_reach_the_text_without_alignment_padding(tmp_path, monkeypatch):
    from docling_core.types.doc import DoclingDocument, TableCell, TableData

    document = DoclingDocument(name="register")
    document.add_table(
        data=TableData(
            num_rows=2,
            num_cols=2,
            table_cells=[
                TableCell(
                    text=text,
                    start_row_offset_idx=row,
                    end_row_offset_idx=row + 1,
                    start_col_offset_idx=column,
                    end_col_offset_idx=column + 1,
                )
                for row, column, text in [
                    (0, 0, "Lfd. Nr. der Artikel"),
                    (0, 1, "Los"),
                    (1, 0, "1"),
                    (1, 1, "26"),
                ]
            ],
        )
    )
    conversion = SimpleNamespace(status=None, document=document, pages=[])
    converter = Converter()
    monkeypatch.setattr(
        converter,
        "_document_converter",
        lambda force_ocr=None: SimpleNamespace(convert=lambda path: conversion),
    )
    pages, _ = converter._convert_with_docling(tmp_path / "register.pdf")
    assert "| 1 | 26 |" in pages[0]
    assert "  " not in pages[0].replace("|  |", "")


def test_unknown_table_mode_is_rejected():
    with pytest.raises(ValueError, match="unknown table mode"):
        Converter(table_mode="guess")


def test_convert_command_passes_ocr_settings(tmp_path, monkeypatch, capsys):
    from intextum_cli.cli import main

    path = tmp_path / "notes.txt"
    path.write_text("Readable source text")
    settings = {}

    def document_converter(self, path, name=None):
        settings.update(
            force=self.force_ocr,
            engine=self.ocr_engine,
            languages=self.ocr_languages,
            tables=self.table_mode,
            marks=self.detect_marks,
        )
        return ConvertedFile(path.name, ["Readable source text"])

    monkeypatch.setattr(Converter, "convert", document_converter)
    assert (
        main(
            [
                "convert",
                str(path),
                "--force-ocr",
                "--ocr-engine",
                "tesseract",
                "--ocr-language",
                "deu",
                "--ocr-language",
                "eng",
                "--table-mode",
                "predicted",
                "--detect-marks",
            ]
        )
        == 0
    )
    assert settings == {
        "force": True,
        "engine": "tesseract",
        "languages": ("deu", "eng"),
        "tables": "predicted",
        "marks": True,
    }
    assert "Readable source text" in capsys.readouterr().out


def test_gis_sidecar_files_are_not_supported(tmp_path):
    assert not convert.is_supported(tmp_path / "sites.shp.xml")
    assert not convert.is_supported(tmp_path / "aerial.tif.aux.xml")
    assert convert.is_supported(tmp_path / "export.xml")


def test_has_text_ignores_image_placeholders():
    assert not ConvertedFile("scan.pdf", ["<!-- image -->"]).has_text
    assert not ConvertedFile("map.pdf", ["Maßstab 1 : 15000"]).has_text
    assert not ConvertedFile("x.pdf", error="conversion failed").has_text
    assert not ConvertedFile(
        "broken.pdf", ["106228104114108105991043211910199104115"]
    ).has_text
    assert ConvertedFile(
        "letter.pdf", ["Sehr geehrte Damen und Herren, anbei der Vertrag."]
    ).has_text


def test_empty_file_is_reported_as_empty(tmp_path):
    (tmp_path / "leer.xlsx").write_bytes(b"")
    assert Converter().convert(tmp_path / "leer.xlsx").error == "empty file (0 bytes)"


def test_read_csv_text_handles_windows_encoding_and_semicolons(tmp_path):
    path = tmp_path / "items.csv"
    path.write_bytes(
        "Straße;Code;Menge;Größe\r\nHafenstraße;5;46;0\r\nMühlweg;3;190;2|x\r\n".encode(
            "cp1252"
        )
    )
    [page], note = read_csv_text(path)
    assert page.splitlines() == [
        "| Straße | Code | Menge | Größe |",
        "|---|---|---|---|",
        "| Hafenstraße | 5 | 46 | 0 |",
        "| Mühlweg | 3 | 190 | 2/x |",
    ]
    assert note == "CSV read without Docling (cp1252, delimiter ;)"


def test_csv_fallback_only_when_docling_fails(tmp_path, monkeypatch):
    path = tmp_path / "liste.csv"
    path.write_bytes("a;b\r\nMüller;1\r\n".encode("cp1252"))

    def docling_fails(self, path, force_ocr=None):
        raise RuntimeError("CsvDocumentBackend could not load document")

    monkeypatch.setattr(Converter, "_convert_with_docling", docling_fails)
    converted = Converter(
        WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    ).convert(path)
    assert converted.error is None and "| Müller | 1 |" in converted.text
    assert converted.notes == ["CSV read without Docling (cp1252, delimiter ;)"]
    # Notes survive the cache.
    again = Converter(
        WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    ).convert(path)
    assert again.notes == converted.notes

    monkeypatch.setattr(
        Converter,
        "_convert_with_docling",
        lambda self, p, force_ocr=None: (["| a | b |"], False),
    )
    (tmp_path / "ok.csv").write_text("a,b\n1,2\n")
    assert Converter().convert(tmp_path / "ok.csv").notes == []


def test_msg_fallback_when_docling_fails(tmp_path, monkeypatch):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    import oxmsg

    message = SimpleNamespace(
        subject="Order confirmation", sender="Sales <sales@example.org>", recipients=[SimpleNamespace(name="Alex Example", email_address="alex@example.org")],
        sent_date=datetime(2026, 10, 1, 9, 0, tzinfo=UTC), body="Hello Alex,\r\nplease find the order confirmation attached.",
        html_body=None, attachments=[SimpleNamespace(file_name="order.pdf")],
    )  # fmt: skip
    monkeypatch.setattr(oxmsg.Message, "load", staticmethod(lambda path: message))
    monkeypatch.setattr(
        Converter,
        "_convert_with_docling",
        lambda self, p, force_ocr=None: (_ for _ in ()).throw(
            RuntimeError("soffice failed")
        ),
    )
    (tmp_path / "mail.msg").write_bytes(b"\xd0\xcf\x11\xe0")
    converted = Converter().convert(tmp_path / "mail.msg")
    assert converted.text.splitlines()[:5] == [
        "# Order confirmation",
        "",
        "From: Sales <sales@example.org>",
        "To: Alex Example <alex@example.org>",
        "Date: 2026-10-01T09:00:00+00:00",
    ]
    assert "Attachments (content not included): order.pdf" in converted.text
    assert "please find the order confirmation attached." in converted.text
    assert converted.notes == [
        "Outlook message read without Docling; 1 attachment(s) not converted"
    ]


def test_ocr_fallback_for_pdfs_without_text(tmp_path, monkeypatch):
    calls = []

    def fake_docling(self, path, force_ocr=None):
        calls.append(force_ocr)
        if force_ocr:
            return ["Service contract between Acme Ltd and Globex Inc"], True
        return ["<!-- image -->"], True

    monkeypatch.setattr(Converter, "_convert_with_docling", fake_docling)
    (tmp_path / "scan.pdf").write_bytes(b"%PDF-1.4")
    converted = Converter().convert(tmp_path / "scan.pdf")
    assert calls == [None, True]
    assert converted.has_text and converted.notes == [
        "text from full-page OCR (fallback)"
    ]

    # No second attempt when --force-ocr is already on, or for non-scan formats.
    calls.clear()
    Converter(force_ocr=True).convert(tmp_path / "scan.pdf")
    assert calls == [None]


def test_legacy_files_are_not_read(tmp_path, monkeypatch):
    path = tmp_path / "a.txt"
    path.write_text("Current source text")
    legacy = tmp_path / ".intextum" / "cache"
    legacy.mkdir(parents=True)
    (legacy / "old.json").write_text('{"pages":["Stale text"]}')
    store = WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    assert Converter(store).convert(path).text == "Current source text"


def test_identifier_labels_count_as_text():
    assert ConvertedFile("map.pdf", ["12_3_456\n12_3_457/2\nMaßstab 1 : 2500"]).has_text
    assert ConvertedFile("map.pdf", ["205/1 | 206/1"]).has_text
    # One label, a scale, a date or a long number are not enough.
    assert not ConvertedFile("map.pdf", ["99_1_12/3 | Maßstab 1:2500"]).has_text
    assert not ConvertedFile("scan.pdf", ["01.10.2027 1:3500 203091"]).has_text
    assert not ConvertedFile(
        "broken.pdf", ["106228104114108105991043211910199104115"]
    ).has_text


def test_conversions_carry_independent_source_references(tmp_path):
    path = tmp_path / "notes.txt"
    store = WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    converter = Converter(store)
    path.write_text("The first version of the document")
    first = converter.convert(path, "notes.txt")
    path.write_text("The revised version of the document")
    second = converter.convert(path, "renamed.txt")
    assert first.source_reference["path"] == "notes.txt"
    assert second.source_reference["path"] == "renamed.txt"
    assert first.source_reference["digest"] != second.source_reference["digest"]
    assert first.conversion_key != second.conversion_key
    assert store.cache.conversion(first.conversion_key).pages == first.pages


def test_recognized_text_is_restored_before_marks_are_tagged(tmp_path, monkeypatch):
    from docling_core.types.doc import DoclingDocument

    conversion = SimpleNamespace(
        status=None, document=DoclingDocument(name="form"), pages=[]
    )
    order = []
    monkeypatch.setattr(
        convert, "restore_recognized_text", lambda *_: order.append("restore") or 0
    )
    monkeypatch.setattr(
        convert, "mark_cancellations", lambda *_: order.append("mark") or 0
    )
    converter = Converter(detect_marks=True, table_mode="docling")
    monkeypatch.setattr(
        converter,
        "_document_converter",
        lambda force_ocr=None: SimpleNamespace(convert=lambda path: conversion),
    )
    converter._convert_with_docling(tmp_path / "form.pdf")
    assert order == ["restore", "mark"]


def layered_document(body=None):
    from docling_core.types.doc import ContentLayer, DoclingDocument

    document = DoclingDocument(name="scan")
    if body:
        document.add_text(label="text", text=body)
    document.add_text(
        label="page_footer",
        text="Running footer of the inventory register office",
        content_layer=ContentLayer.FURNITURE,
    )
    document.add_text(
        label="text",
        text="Hidden speaker notes",
        content_layer=ContentLayer.INVISIBLE,
    )
    return document


def test_extraction_text_keeps_furniture_but_not_other_layers(tmp_path, monkeypatch):
    conversion = SimpleNamespace(
        status=None, document=layered_document("Readable body text"), pages=[]
    )
    converter = Converter()
    monkeypatch.setattr(
        converter,
        "_document_converter",
        lambda force_ocr=None: SimpleNamespace(convert=lambda path: conversion),
    )
    pages, _ = converter._convert_with_docling(tmp_path / "scan.pdf")
    assert "Readable body text" in pages[0]
    assert "Running footer" in pages[0]
    assert "Hidden" not in pages[0]


def test_ocr_fallback_runs_when_only_a_footer_has_text(tmp_path, monkeypatch):
    calls = []

    def build(force_ocr=None):
        calls.append(force_ocr)
        body = "Service contract between Acme Ltd and Globex Inc" if force_ocr else None
        return SimpleNamespace(
            convert=lambda path: SimpleNamespace(
                status=None, document=layered_document(body), pages=[]
            )
        )

    converter = Converter()
    monkeypatch.setattr(converter, "_document_converter", build)
    (tmp_path / "scan.pdf").write_bytes(b"%PDF-1.4")
    converted = converter.convert(tmp_path / "scan.pdf")
    assert calls == [None, True]
    assert "Service contract" in converted.text
    assert converted.notes == ["text from full-page OCR (fallback)"]
