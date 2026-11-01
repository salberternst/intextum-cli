from types import SimpleNamespace

from docling_core.types.doc import (
    BoundingBox,
    ContentLayer,
    CoordOrigin,
    DocItemLabel,
    DoclingDocument,
    ProvenanceItem,
    Size,
    TableCell,
    TableData,
)
from docling_core.types.doc.page import BoundingRectangle, TextCell

from intextum_cli.conversion_recovery import restore_recognized_text
from intextum_cli.convert import Converter
from intextum_cli.document_cache import DocumentStore
from intextum_cli.document_render import render_document
from intextum_cli.source import build_source, locate
from intextum_cli.store import WorkspaceStore


def box(top=10, left=10, width=100, height=10):
    return BoundingBox(
        l=left,
        t=top,
        r=left + width,
        b=top + height,
        coord_origin=CoordOrigin.TOPLEFT,
    )


def provenance(page=1, text="", bbox=None):
    return ProvenanceItem(page_no=page, bbox=bbox or box(), charspan=(0, len(text)))


def cell(text, *, bbox=None, from_ocr=True):
    return TextCell(
        index=0,
        text=text,
        orig=text,
        from_ocr=from_ocr,
        rect=BoundingRectangle.from_bounding_box(bbox or box()),
    )


def conversion(document, *pages):
    return SimpleNamespace(
        document=document,
        status=SimpleNamespace(value="success"),
        pages=[
            SimpleNamespace(
                page_no=number, size=Size(width=600, height=800), cells=cells
            )
            for number, cells in enumerate(pages, 1)
        ],
    )


def test_omitted_ocr_is_recovered_on_original_page_with_cached_evidence(
    tmp_path, monkeypatch
):
    doc = DoclingDocument(name="Mixed scanned register")
    for number in range(1, 4):
        doc.add_page(page_no=number, size=Size(width=600, height=800))
    doc.add_picture(prov=provenance(1))
    doc.add_text(
        label=DocItemLabel.TEXT,
        text="Next page",
        prov=provenance(3, "Next page"),
    )
    result = conversion(
        doc,
        [cell("Inventarhinweis")],
        [
            cell("Entfernt", bbox=box(left=10, width=35)),
            cell("am 21.05.2020.", bbox=box(left=50)),
        ],
        [cell("Next page")],
    )
    monkeypatch.setattr(
        Converter,
        "_document_converter",
        lambda *args: SimpleNamespace(convert=lambda path: result),
    )
    path = tmp_path / "register.pdf"
    path.write_bytes(b"%PDF-1.4")
    store = WorkspaceStore(tmp_path / "results.sqlite", create=True)
    converted = Converter(store).convert(path)
    assert converted.error is None
    assert len(converted.pages) == 3
    assert "Inventarhinweis" in converted.pages[0]
    assert "Entfernt am 21.05.2020." in converted.pages[1]
    assert converted.pages[2].count("Next page") == 1
    source = build_source([converted], max_chars=60000)
    _, evidence = locate("Entfernt am 21.05.2020.", source)
    assert evidence["page"] == 2
    assert evidence["element_refs"]
    assert DocumentStore(store).read(converted.document_key)
    monkeypatch.setattr(
        Converter,
        "_document_converter",
        lambda *args: (_ for _ in ()).throw(AssertionError("cache miss")),
    )
    assert Converter(store).convert(path).pages == converted.pages


def test_table_ocr_coverage_requires_matching_text_and_location():
    doc = DoclingDocument(name="Custody")
    doc.add_page(page_no=1, size=Size(width=600, height=800))
    doc.add_table(
        prov=provenance(),
        data=TableData(
            num_rows=1,
            num_cols=1,
            table_cells=[
                TableCell(
                    text="Custodian",
                    bbox=box(),
                    start_row_offset_idx=0,
                    end_row_offset_idx=1,
                    start_col_offset_idx=0,
                    end_col_offset_idx=1,
                )
            ],
        ),
    )
    result = conversion(
        doc,
        [
            cell("Custodian"),
            cell("Custodian", bbox=box(top=40)),
            cell("Historical custodian", bbox=box(top=60)),
            cell("Native only", bbox=box(top=80), from_ocr=False),
        ],
    )
    assert restore_recognized_text(result) == 3
    text = doc.export_to_markdown()
    assert text.count("Custodian") == 2
    assert "Historical custodian" in text
    assert "Native only" in text
    assert restore_recognized_text(result) == 0


def test_layout_cells_survive_release_of_parsed_pages():
    doc = DoclingDocument(name="Scanned form")
    doc.add_page(page_no=1, size=Size(width=600, height=800))
    result = conversion(doc, [])
    result.pages[0].predictions = SimpleNamespace(
        layout=SimpleNamespace(
            clusters=[
                SimpleNamespace(cells=[cell("Entfernt am 21.05.2020.")], children=[])
            ]
        )
    )
    assert restore_recognized_text(result) == 1
    assert "Entfernt am 21.05.2020." in doc.export_to_markdown()


def test_picture_text_and_footer_are_in_source_and_evidence(tmp_path, monkeypatch):
    doc = DoclingDocument(name="Register with picture text")
    doc.add_page(page_no=1, size=Size(width=600, height=800))
    picture = doc.add_picture(prov=provenance())
    text = "1 Entfernt am 21.05.2020."
    item = doc.add_text(
        label=DocItemLabel.TEXT, text=text, parent=picture, prov=provenance(1, text)
    )
    footer = "Abdruck vom 08.02.2021"
    doc.add_text(
        label=DocItemLabel.PAGE_FOOTER,
        text=footer,
        content_layer=ContentLayer.FURNITURE,
        prov=provenance(1, footer, box(top=780)),
    )
    result = conversion(doc, [])
    monkeypatch.setattr(
        Converter,
        "_document_converter",
        lambda *args: SimpleNamespace(convert=lambda path: result),
    )
    path = tmp_path / "register.pdf"
    path.write_bytes(b"%PDF-1.4")
    store = WorkspaceStore(tmp_path / "results.sqlite", create=True)
    converted = Converter(store).convert(path)
    assert text in converted.text and footer in converted.text
    _, evidence = locate(text, build_source([converted], max_chars=60000))
    assert evidence["element_refs"] == [item.self_ref]
    assert evidence["page"] == 1
    html = render_document(doc.export_to_dict())
    assert text in html and f'data-doc-ref="{item.self_ref}"' in html
