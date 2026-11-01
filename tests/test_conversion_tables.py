from types import SimpleNamespace

from docling_core.types.doc import (
    BoundingBox,
    CoordOrigin,
    DoclingDocument,
    ImageRef,
    ProvenanceItem,
    Size,
)
from docling_core.types.doc.page import BoundingRectangle, TextCell
from PIL import Image, ImageDraw

from intextum_cli.conversion_recovery import restore_recognized_text
from intextum_cli.conversion_tables import restore_ruled_tables, split_native_columns


def bbox(left, top, width=20, height=10):
    return BoundingBox(
        l=left, t=top, r=left + width, b=top + height, coord_origin=CoordOrigin.TOPLEFT
    )


def text(value, left, top, width=20):
    return TextCell(
        index=0,
        text=value,
        orig=value,
        from_ocr=True,
        rect=BoundingRectangle.from_bounding_box(bbox(left, top, width)),
    )


def ruled_form(columns, cells, rules=(50, 95, 140, 750)):
    image = Image.new("RGB", (600, 800), "white")
    draw = ImageDraw.Draw(image)
    for x in columns:
        draw.line((x, 50, x, 750), fill="black")
    for y in rules:
        draw.line((columns[0], y, columns[-1], y), fill="black")
    # Red cancellations must not be mistaken for additional table rules.
    draw.line((columns[0], 210, columns[-1], 210), fill="red", width=2)
    draw.line((columns[0], 210, columns[-1], 240), fill="red", width=2)
    document = DoclingDocument(name="Fictional scanned register")
    document.add_page(
        page_no=1,
        size=Size(width=600, height=800),
        image=ImageRef.from_pil(image, dpi=72),
    )
    document.add_picture(
        prov=ProvenanceItem(
            page_no=1,
            bbox=bbox(columns[0], 50, columns[-1] - columns[0], 700),
            charspan=(0, 0),
        )
    )
    return SimpleNamespace(
        document=document,
        pages=[
            SimpleNamespace(page_no=1, size=Size(width=600, height=800), cells=cells)
        ],
    )


def test_ruled_form_keeps_predecessor_batch_and_historical_rows_separate():
    columns = [30, 70, 110, 150, 250, 440, 485, 530, 570]
    result = ruled_form(
        columns,
        [
            text("Lfd. Nr.", 35, 110, 30),
            text("Bisherige", 75, 110, 30),
            text("Los", 115, 110, 30),
            text("Artikelcode", 155, 110, 80),
            text("Typ und Beschreibung", 255, 110, 170),
            text("Pal.", 450, 110),
            text("Box", 495, 110),
            text("Stk.", 540, 110),
            text("1", 40, 200),
            text("3", 120, 200),
            text("197/55", 160, 200, 70),
            text("Testbauteil", 260, 200, 120),
            text("18", 495, 215),
            text("82", 540, 215),
            text("4", 40, 300),
            text("1", 80, 300),
            text("3", 120, 300),
            text("55/7", 160, 300, 70),
            text("Testmodul", 260, 300, 120),
            text("18", 495, 300),
            text("82", 540, 300),
        ],
    )
    assert restore_ruled_tables(result) == 1
    assert restore_recognized_text(result) == 0
    [table] = result.document.tables
    assert table.data.num_cols == 8
    rows = table.data.grid
    historical = next(row for row in rows if row[0].text == "1")
    replacement = next(row for row in rows if row[0].text == "4")
    assert [c.text for c in historical[:5]] == [
        "1",
        "",
        "3",
        "197/55",
        "Testbauteil",
    ]
    assert [c.text for c in replacement[:5]] == ["4", "1", "3", "55/7", "Testmodul"]
    assert rows[0][2].column_header and rows[0][2].text == "Los"
    assert table.prov[0].page_no == 1
    assert not result.document.pictures
    assert result.document.pages[1].image.pil_image.size == (600, 800)


def test_custodian_and_reviewer_signature_stay_in_different_columns():
    result = ruled_form(
        [30, 70, 280, 340, 570],
        [
            text("Lfd. Nr.", 35, 110, 30),
            text("Betreuer", 80, 110, 100),
            text("Ref.", 285, 110, 40),
            text("Grundlage der Zuordnung", 350, 110, 200),
            text("1b", 40, 200),
            text("Alex Beispiel", 80, 200, 110),
            text("und", 80, 215),
            text("Bea Muster", 80, 230, 110),
            text("Unterschrift Beispielprüfer", 350, 215, 200),
        ],
    )
    assert restore_ruled_tables(result) == 1
    custodian = " ".join(row[1].text for row in result.document.tables[0].data.grid)
    basis = " ".join(row[3].text for row in result.document.tables[0].data.grid)
    assert "Bea Muster" in custodian and "Beispielprüfer" not in custodian
    assert "Beispielprüfer" in basis


def test_native_line_crossing_rule_is_split_using_pdf_character_positions(tmp_path):
    from reportlab.pdfgen.canvas import Canvas

    path = tmp_path / "columns.pdf"
    canvas = Canvas(str(path), pagesize=(600, 800))
    canvas.setFont("Courier", 10)
    canvas.drawString(40, 590, "4")
    canvas.drawString(80, 590, "1")
    canvas.drawString(120, 590, "3")
    canvas.save()
    line = SimpleNamespace(box=bbox(40, 200, 90, 12), text="4 1 3", from_ocr=False)
    split = split_native_columns(
        [line], [30, 70, 110, 150], path, 1, Size(width=600, height=800)
    )
    assert [c.text for c in split] == ["4", "1", "3"]


def test_non_ruled_page_keeps_original_content():
    result = ruled_form([30, 570], [text("Ordinary text", 40, 200, 100)])
    original = result.document.model_dump()
    assert restore_ruled_tables(result) == 0
    assert result.document.model_dump() == original


def test_rule_below_an_early_entry_does_not_extend_the_header():
    columns = [30, 100, 250, 570]
    # A black line under the first entry lies in the top 30% of the form but
    # after a wide gap, so it separates entries rather than ending the header.
    result = ruled_form(
        columns,
        [
            text("No.", 40, 110),
            text("Code", 110, 110, 40),
            text("Use", 260, 110, 40),
            text("1", 40, 200),
            text("10/1", 110, 200, 40),
            text("Widget", 260, 200, 60),
            text("2", 40, 300),
            text("10/2", 110, 300, 40),
            text("Module", 260, 300, 60),
        ],
        rules=(50, 95, 140, 230, 750),
    )
    assert restore_ruled_tables(result) == 1
    [table] = result.document.tables
    headers = {cell.text for cell in table.data.table_cells if cell.column_header}
    assert headers == {"No.", "Code", "Use"}
    rows = table.export_to_dataframe(result.document).values.tolist()
    assert ["1", "10/1", "Widget"] in rows
