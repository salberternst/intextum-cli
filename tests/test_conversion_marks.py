from types import SimpleNamespace

import pypdfium2 as pdfium
import pypdfium2.raw as raw
import pytest
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

from intextum_cli import conversion_marks, conversion_tables
from intextum_cli.conversion_marks import (
    Line,
    _page_marks,
    _vector_lines,
    mark_cancellations,
)
from intextum_cli.conversion_tables import PositionedText, restore_ruled_tables


def bbox(left, top, width=20, height=10):
    return BoundingBox(
        l=left, t=top, r=left + width, b=top + height, coord_origin=CoordOrigin.TOPLEFT
    )


def text(value, left, top, width=20, from_ocr=True):
    return TextCell(
        index=0,
        text=value,
        orig=value,
        from_ocr=from_ocr,
        rect=BoundingRectangle.from_bounding_box(bbox(left, top, width)),
    )


def marked_form(draw_marks, cells):
    """A fictional ruled register; every mark is drawn in black."""
    columns = [30, 100, 250, 450, 570]
    image = Image.new("RGB", (600, 800), "white")
    draw = ImageDraw.Draw(image)
    for x in columns:
        draw.line((x, 50, x, 750), fill="black")
    for y in [50, 95, 140, 750]:
        draw.line((columns[0], y, columns[-1], y), fill="black")
    draw_marks(draw)
    document = DoclingDocument(name="Fictional scanned register")
    document.add_page(
        page_no=1,
        size=Size(width=600, height=800),
        image=ImageRef.from_pil(image, dpi=72),
    )
    document.add_picture(
        prov=ProvenanceItem(page_no=1, bbox=bbox(30, 50, 540, 700), charspan=(0, 0))
    )
    page = SimpleNamespace(page_no=1, size=Size(width=600, height=800), cells=cells)
    return SimpleNamespace(document=document, pages=[page])


def tagged_lines(conversion):
    assert restore_ruled_tables(conversion) == 1
    mark_cancellations(conversion)
    return conversion.document.export_to_markdown()


def test_black_underlines_and_diagonals_tag_only_the_marked_entries():
    def draw_marks(draw):
        draw.line((105, 212, 240, 212), fill="black", width=2)
        draw.line((255, 262, 445, 304), fill="black", width=2)

    markdown = tagged_lines(
        marked_form(
            draw_marks,
            [
                text("No.", 40, 110),
                text("Custodian", 110, 110, 60),
                text("Basis", 260, 110, 60),
                text("1", 40, 200),
                text("Alex Example", 110, 200, 120),
                text("2", 40, 270),
                text("Allocation update", 260, 275, 150),
                text("3", 40, 400),
                text("Chris Sample", 110, 400, 120),
            ],
        )
    )
    assert "Alex Example [underlined]" in markdown
    assert "Allocation update [crossed out]" in markdown
    # The unmarked entry and the underlined-looking header rule stay untagged.
    assert markdown.count("[") == 2


def test_lines_in_the_scan_do_not_mark_native_text_placed_over_it():
    def draw_marks(draw):
        draw.line((105, 212, 240, 212), fill="black", width=2)

    markdown = tagged_lines(
        marked_form(
            draw_marks,
            [
                text("No.", 40, 110),
                text("Custodian", 110, 110, 60),
                text("1", 40, 200),
                text("Alex Example", 110, 200, 120, from_ocr=False),
            ],
        )
    )
    assert "[" not in markdown


def test_drawn_pdf_lines_mark_native_and_scanned_text():
    native = PositionedText(bbox(110, 200, 120), "Alex Example", False)
    scanned = PositionedText(bbox(110, 300, 120), "Chris Sample", True)
    drawn = [Line(105, 212, 240, 212)]
    marks = _page_marks([native, scanned], scanned=[], drawn=drawn)
    assert [kinds for _, kinds in marks] == [{"underline"}, set()]
    scan_only = _page_marks([native, scanned], scanned=drawn, drawn=[])
    assert [kinds for _, kinds in scan_only] == [set(), set()]


def test_unruled_pages_are_left_alone():
    document = DoclingDocument(name="Letter")
    image = Image.new("RGB", (600, 800), "white")
    ImageDraw.Draw(image).line((100, 112, 300, 112), fill="black", width=2)
    document.add_page(
        page_no=1, size=Size(width=600, height=800), image=ImageRef.from_pil(image, 72)
    )
    document.add_text(
        label="text",
        text="Underlined heading",
        prov=ProvenanceItem(page_no=1, bbox=bbox(100, 100, 200), charspan=(0, 18)),
    )
    page = SimpleNamespace(
        page_no=1,
        size=Size(width=600, height=800),
        cells=[text("Underlined heading", 100, 100, 200)],
    )
    conversion = SimpleNamespace(document=document, pages=[page])
    assert mark_cancellations(conversion) == 0
    assert document.texts[0].text == "Underlined heading"


@pytest.fixture
def drawn_pdf(tmp_path):
    """A one-page PDF with a vector diagonal from (50, 700) to (300, 600)."""
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(600, 800)
    path = raw.FPDFPageObj_CreateNewPath(50, 700)
    raw.FPDFPath_LineTo(path, 300, 600)
    raw.FPDFPath_SetDrawMode(path, raw.FPDF_FILLMODE_NONE, True)
    raw.FPDFPage_InsertObject(page.raw, path)
    raw.FPDFPage_GenerateContent(page.raw)
    page.close()
    target = tmp_path / "drawn.pdf"
    pdf.save(target)
    pdf.close()
    return target


def test_vector_lines_use_top_left_page_coordinates(drawn_pdf):
    [line] = _vector_lines(drawn_pdf, 1, Size(width=600, height=800))
    assert (line.x0, line.y0, line.x1, line.y1) == pytest.approx((50, 100, 300, 200))


def test_printed_rule_below_text_is_not_an_underline():
    def draw_marks(draw):
        draw.line((30, 215, 570, 215), fill="black")

    markdown = tagged_lines(
        marked_form(
            draw_marks,
            [
                text("No.", 40, 110),
                text("Custodian", 110, 110, 60),
                text("1", 40, 200),
                text("Alex Example", 110, 200, 120),
            ],
        )
    )
    assert "Alex Example" in markdown
    assert "[" not in markdown


def test_mark_on_one_column_of_a_native_line_tags_only_that_cell(monkeypatch):
    def split(cells, columns, path, page_no, size):
        result = []
        for cell in cells:
            if cell.text == "Alex Example Transfer":
                result += [
                    PositionedText(bbox(110, 200, 120), "Alex Example", False),
                    PositionedText(bbox(260, 200, 120), "Transfer", False),
                ]
            else:
                result.append(cell)
        return result

    monkeypatch.setattr(conversion_tables, "split_native_columns", split)
    monkeypatch.setattr(conversion_marks, "split_native_columns", split)
    monkeypatch.setattr(
        conversion_marks,
        "_vector_lines",
        lambda *_: [Line(105, 205, 240, 205)],
    )
    conversion = marked_form(
        lambda draw: None,
        [
            text("No.", 40, 110),
            text("Custodian", 110, 110, 60),
            text("Alex Example Transfer", 110, 200, 270, from_ocr=False),
        ],
    )
    assert restore_ruled_tables(conversion) == 1
    assert mark_cancellations(conversion) == 1
    markdown = conversion.document.export_to_markdown()
    assert "Alex Example [struck through]" in markdown
    assert "Transfer [" not in markdown
