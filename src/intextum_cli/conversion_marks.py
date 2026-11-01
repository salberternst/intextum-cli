"""Tag text in ruled forms that cancellation lines underline, strike or cross."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .conversion_tables import (
    PositionedText,
    recognized_text,
    ruled_grid,
    split_native_columns,
)

if TYPE_CHECKING:
    from docling.datamodel.document import ConversionResult
    from docling_core.types.doc import BoundingBox, DoclingDocument, Size
    from PIL.Image import Image

# Neutral descriptions of what is drawn; schemas decide what a mark means.
MARK_TAGS = {
    "underline": "[underlined]",
    "strike": "[struck through]",
    "cross": "[crossed out]",
}


def has_mark_tag(text: str, marks: list[str]) -> bool:
    return any(MARK_TAGS[mark] in text for mark in marks)


@dataclass(frozen=True)
class Line:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def slope(self) -> float | None:
        width = abs(self.x1 - self.x0)
        return abs(self.y1 - self.y0) / width if width else None


def _is_horizontal(line: Line) -> bool:
    return line.slope is not None and line.slope <= 0.07


def _is_diagonal(line: Line) -> bool:
    # About 4° to 78°: flat cancellation strokes count, near-vertical rules do not.
    return line.slope is not None and 0.07 < line.slope < 4.7


def _image_lines(image: Image, scale: float) -> list[Line]:
    """Long strokes in the page image, independent of their colour."""
    import cv2
    import numpy as np

    ink = (np.asarray(image.convert("L")) < 170).astype(np.uint8)
    length = max(20, int(30 * scale))
    horizontal = cv2.morphologyEx(
        ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (length, 1))
    )
    vertical = cv2.morphologyEx(
        ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, length))
    )
    lines = []
    _, _, stats, _ = cv2.connectedComponentsWithStats(horizontal)
    for x, y, width, height, _ in stats[1:]:
        if width >= length:
            middle = (y + height / 2) / scale
            lines.append(Line(x / scale, middle, (x + width) / scale, middle))
    rest = ink.copy()
    rest[(horizontal > 0) | (vertical > 0)] = 0
    found = cv2.HoughLinesP(
        rest * 255,
        1,
        np.pi / 360,
        threshold=60,
        minLineLength=int(75 * scale),
        maxLineGap=6,
    )
    for x0, y0, x1, y1 in [] if found is None else found.reshape(-1, 4):
        line = Line(x0 / scale, y0 / scale, x1 / scale, y1 / scale)
        if _is_diagonal(line):
            lines.append(line)
    return lines


def _vector_lines(path: Path | None, page_no: int, size: Size) -> list[Line]:
    """Straight segments of drawn PDF paths, in top-left page coordinates."""
    if path is None or path.suffix.lower() != ".pdf":
        return []
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
    from docling.utils.locks import pypdfium2_lock

    def matrix(handle) -> tuple[float, ...]:
        value = raw.FS_MATRIX()
        raw.FPDFPageObj_GetMatrix(handle, value)
        return (value.a, value.b, value.c, value.d, value.e, value.f)

    def combine(inner, outer) -> tuple[float, ...]:
        a, b, c, d, e, f = inner
        A, B, C, D, E, F = outer
        return (
            a * A + b * C,
            a * B + b * D,
            c * A + d * C,
            c * B + d * D,
            e * A + f * C + E,
            e * B + f * D + F,
        )

    lines: list[Line] = []

    def visit(handle, outer) -> None:
        kind = raw.FPDFPageObj_GetType(handle)
        transform = combine(matrix(handle), outer)
        if kind == raw.FPDF_PAGEOBJ_FORM:
            for index in range(raw.FPDFFormObj_CountObjects(handle)):
                visit(raw.FPDFFormObj_GetObject(handle, index), transform)
            return
        if kind != raw.FPDF_PAGEOBJ_PATH:
            return
        a, b, c, d, e, f = transform
        previous = None
        for index in range(raw.FPDFPath_CountSegments(handle)):
            segment = raw.FPDFPath_GetPathSegment(handle, index)
            x, y = raw.FS_FLOAT(), raw.FS_FLOAT()
            raw.FPDFPathSegment_GetPoint(segment, x, y)
            point = (
                a * x.value + c * y.value + e,
                size.height - (b * x.value + d * y.value + f),
            )
            if (
                previous is not None
                and raw.FPDFPathSegment_GetType(segment) == raw.FPDF_SEGMENT_LINETO
            ):
                line = Line(*previous, *point)
                if abs(line.x1 - line.x0) >= 30:
                    lines.append(line)
            previous = point

    with pypdfium2_lock, pdfium.PdfDocument(path) as pdf:
        with closing(pdf[page_no - 1]) as page:
            # As for native column splitting, leave rotated or offset pages alone.
            if page.get_rotation() or page.get_bbox()[:2] != (0, 0):
                return []
            identity = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
            for index in range(raw.FPDFPage_CountObjects(page.raw)):
                visit(raw.FPDFPage_GetObject(page.raw, index), identity)
    return lines


def _without_rules(
    lines: list[Line], rules: list[float], tolerance: float
) -> list[Line]:
    """Printed row rules are not marks, even with text sitting just above them."""
    return [
        line
        for line in lines
        if not _is_horizontal(line)
        or all(abs((line.y0 + line.y1) / 2 - rule) > tolerance for rule in rules)
    ]


def _crosses(line: Line, box: BoundingBox) -> bool:
    """Whether a segment passes through a box (Liang-Barsky clipping)."""
    dx, dy = line.x1 - line.x0, line.y1 - line.y0
    start, end = 0.0, 1.0
    for p, q in (
        (-dx, line.x0 - box.l),
        (dx, box.r - line.x0),
        (-dy, line.y0 - box.t),
        (dy, box.b - line.y0),
    ):
        if p == 0:
            if q < 0:
                return False
            continue
        ratio = q / p
        if p < 0:
            start = max(start, ratio)
        else:
            end = min(end, ratio)
        if start > end:
            return False
    return True


def _kinds(box: BoundingBox, lines: list[Line]) -> set[str]:
    height = box.b - box.t
    kinds: set[str] = set()
    for line in lines:
        if _is_horizontal(line):
            left, right = sorted((line.x0, line.x1))
            if min(right, box.r) - max(left, box.l) < 0.6 * (box.r - box.l):
                continue
            y = (line.y0 + line.y1) / 2
            if box.t + 0.3 * height <= y <= box.b - 0.3 * height:
                kinds.add("strike")
            elif box.b - 0.3 * height < y <= box.b + 0.7 * height:
                kinds.add("underline")
        elif _is_diagonal(line) and _crosses(line, box):
            kinds.add("cross")
    return kinds


def _tags(box: BoundingBox, marks: list[tuple[BoundingBox, set[str]]]) -> str:
    """Tag an element only when most of its recognized lines carry a mark."""
    inside = [kinds for cell, kinds in marks if cell.intersection_over_self(box) >= 0.5]
    marked = [kinds for kinds in inside if kinds]
    if not marked or 2 * len(marked) <= len(inside):
        return ""
    found = set().union(*marked)
    return " ".join(tag for kind, tag in MARK_TAGS.items() if kind in found)


def _tag_document(
    document: DoclingDocument,
    page_no: int,
    height: float,
    marks: list[tuple[BoundingBox, set[str]]],
) -> int:
    from docling_core.types.doc import ContentLayer, TableItem, TextItem

    tagged = 0
    for item, _ in document.iterate_items(
        traverse_pictures=True, included_content_layers=set(ContentLayer)
    ):
        if not any(prov.page_no == page_no for prov in item.prov):
            continue
        if isinstance(item, TableItem):
            for cell in item.data.table_cells:
                if cell.text and cell.bbox is not None:
                    tags = _tags(cell.bbox.to_top_left_origin(height), marks)
                    if tags:
                        cell.text = f"{cell.text} {tags}"
                        tagged += 1
        elif isinstance(item, TextItem) and item.text:
            boxes = [p.bbox for p in item.prov if p.page_no == page_no]
            tags = _tags(boxes[0].to_top_left_origin(height), marks)
            if tags:
                item.text = f"{item.text} {tags}"
                tagged += 1
    return tagged


def _page_marks(
    cells: list[PositionedText], scanned: list[Line], drawn: list[Line]
) -> list[tuple[BoundingBox, set[str]]]:
    # Lines in the page image date from the scan; native text placed over it was
    # added later. Drawn PDF paths lie above both and apply to all text.
    return [
        (
            cell.box,
            _kinds(cell.box, drawn)
            | (_kinds(cell.box, scanned) if cell.from_ocr else set()),
        )
        for cell in cells
    ]


def mark_cancellations(conversion: ConversionResult, path: Path | None = None) -> int:
    """Append neutral mark tags to elements inside large ruled forms."""
    document = conversion.document
    tagged = 0
    for page in getattr(conversion, "pages", []):
        saved_page = document.pages.get(page.page_no)
        if page.size is None or saved_page is None or saved_page.image is None:
            continue
        image = saved_page.image.pil_image
        grid = ruled_grid(image)
        if grid is None:
            continue
        columns, _, bottom, header, rules = grid
        scale_x = image.width / page.size.width
        scale_y = image.height / page.size.height
        # Printed headings and page furniture are often underlined by design.
        cells = [
            cell
            for cell in recognized_text(page)
            if cell.box.t >= header / scale_y
            and cell.box.b <= bottom / scale_y
            and cell.box.l >= columns[0] / scale_x - 2
            and cell.box.r <= columns[-1] / scale_x + 2
        ]
        if not cells:
            continue
        # Measure marks on the cells a ruled table is built from, not on wide lines.
        cells = split_native_columns(
            cells,
            [x / scale_x for x in columns],
            path,
            page.page_no,
            page.size,
        )
        heights = [y / scale_y for y in rules]
        tolerance = 3 / scale_y
        marks = _page_marks(
            cells,
            _without_rules(_image_lines(image, scale_x), heights, tolerance),
            _without_rules(
                _vector_lines(path, page.page_no, page.size), heights, tolerance
            ),
        )
        if any(kinds for _, kinds in marks):
            tagged += _tag_document(document, page.page_no, page.size.height, marks)
    return tagged
