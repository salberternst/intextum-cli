"""Recover columns of large ruled forms from recognized text and page images."""

from __future__ import annotations

from bisect import bisect_right
from contextlib import closing
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docling.datamodel.base_models import Page
    from docling.datamodel.document import ConversionResult
    from docling_core.types.doc import BoundingBox, Size, TableData
    from PIL.Image import Image


@dataclass
class PositionedText:
    box: BoundingBox
    text: str
    from_ocr: bool


def _groups(positions: list[int], gap: int = 3) -> list[list[int]]:
    groups: list[list[int]] = []
    for position in positions:
        if groups and position - groups[-1][-1] <= gap:
            groups[-1].append(position)
        else:
            groups.append([position])
    return groups


def ruled_grid(image: Image) -> tuple[list[int], int, int, int, list[int]] | None:
    """Only accept a large, clearly ruled grid; leave ordinary layouts alone."""
    import numpy as np

    pixels = np.asarray(image.convert("RGB"))
    # A maximum over RGB excludes red cancellation lines from the black grid.
    dark = pixels.max(axis=2) < 210
    height, width = dark.shape
    wide = dark.copy()
    for shift in (1, 2):
        wide[:, shift:] |= dark[:, :-shift]
        wide[:, :-shift] |= dark[:, shift:]
    candidates = np.flatnonzero(wide.sum(axis=0) > height * 0.55).tolist()
    columns = [
        max(group, key=lambda x: int(dark[:, x].sum())) for group in _groups(candidates)
    ]
    if len(columns) < 3 or columns[-1] - columns[0] < width * 0.4:
        return None
    tall = dark.copy()
    for shift in (1, 2):
        tall[shift:, :] |= dark[:-shift, :]
        tall[:-shift, :] |= dark[shift:, :]
    left, right = columns[0], columns[-1]
    candidates = np.flatnonzero(
        tall[:, left : right + 1].sum(axis=1) > (right - left) * 0.8
    ).tolist()
    rules = [
        max(group, key=lambda y: int(dark[y, left : right + 1].sum()))
        for group in _groups(candidates)
    ]
    if len(rules) < 3 or rules[-1] - rules[0] < height * 0.5:
        return None
    top, bottom = rules[0], rules[-1]
    # Printed header rules lie close together. A rule after a wide gap already
    # separates entries, such as one drawn below the last entry of a section.
    header = None
    for y in rules[1:-1]:
        if (
            y >= top + (bottom - top) * 0.3
            or y - (header or top) > (bottom - top) * 0.1
        ):
            break
        header = y
    if header is None:
        return None
    return columns, top, bottom, header, rules


def recognized_text(page: Page) -> list[PositionedText]:
    cells = list(page.cells)
    layout = getattr(getattr(page, "predictions", None), "layout", None)
    clusters = list(layout.clusters) if layout is not None else []
    while clusters:
        cluster = clusters.pop()
        cells.extend(cluster.cells)
        clusters.extend(cluster.children)
    result: list[PositionedText] = []
    for cell in sorted(cells, key=lambda cell: cell.from_ocr):
        text = cell.text.strip()
        if not text or not any(char.isalnum() for char in text):
            continue
        box = cell.rect.to_bounding_box().to_top_left_origin(page.size.height)
        if box.area() <= 0:
            continue
        if any(
            box.intersection_over_self(previous.box) >= 0.65
            and (
                (cell.from_ocr and not previous.from_ocr)
                or text.casefold() == previous.text.casefold()
            )
            for previous in result
        ):
            continue
        result.append(PositionedText(box, text, cell.from_ocr))
    return result


def _rows(cells: list[PositionedText]) -> list[list[PositionedText]]:
    rows: list[list[PositionedText]] = []
    for cell in sorted(cells, key=lambda cell: (cell.box.t, cell.box.l)):
        if rows:
            previous = rows[-1][0].box
            overlap = min(cell.box.b, previous.b) - max(cell.box.t, previous.t)
            if overlap >= min(cell.box.height, previous.height) * 0.4:
                rows[-1].append(cell)
                continue
        rows.append([cell])
    return rows


def _character_boxes(text_page) -> list[tuple[float, float, float, float]]:
    return [
        text_page.get_charbox(index)
        for index in range(text_page.count_chars())
        if text_page.get_text_range(index, 1).strip()
    ]


def split_native_columns(
    cells: list[PositionedText],
    columns: list[float],
    path: Path | None,
    page_no: int,
    size: Size,
) -> list[PositionedText]:
    """Split native text lines that cross rules, using actual PDF characters."""
    if path is None or path.suffix.lower() != ".pdf":
        return cells
    import pypdfium2 as pdfium
    from docling.utils.locks import pypdfium2_lock

    split: list[PositionedText] = []
    with pypdfium2_lock, pdfium.PdfDocument(path) as pdf:
        with closing(pdf[page_no - 1]) as page:
            # These coordinates are in the rendered page frame. Leave rotated
            # or offset crop boxes to the OCR cells rather than guessing a map.
            if page.get_rotation() or page.get_bbox()[:2] != (0, 0):
                return cells
            x_scale = page.get_width() / size.width
            y_scale = page.get_height() / size.height
            chars = None
            with closing(page.get_textpage()) as text_page:
                for cell in cells:
                    ranges = [
                        (max(left, cell.box.l), min(right, cell.box.r))
                        for left, right in pairwise(columns)
                        if min(right, cell.box.r) - max(left, cell.box.l) > 3
                    ]
                    if len(ranges) < 2:
                        split.append(cell)
                        continue
                    fragments = [
                        (
                            left,
                            right,
                            text_page.get_text_bounded(
                                left=left * x_scale,
                                right=right * x_scale,
                                top=(size.height - cell.box.t + 0.5) * y_scale,
                                bottom=(size.height - cell.box.b - 0.5) * y_scale,
                            )
                            .replace("\x02", "-")
                            .strip(),
                        )
                        for left, right in ranges
                    ]
                    joined = "".join(text for _, _, text in fragments)
                    if (
                        "".join(joined.split()).casefold()
                        != "".join(cell.text.split()).casefold()
                    ):
                        split.append(cell)
                        continue
                    # Fit each box to its characters, not to the column around them,
                    # so that a line under the text covers most of the box.
                    if chars is None:
                        chars = _character_boxes(text_page)
                    for left, right, text in fragments:
                        if text:
                            inside = [
                                (x0 / x_scale, x1 / x_scale)
                                for x0, y0, x1, y1 in chars
                                if left <= (x0 + x1) / 2 / x_scale <= right
                                and cell.box.t
                                <= size.height - (y0 + y1) / 2 / y_scale
                                <= cell.box.b
                            ]
                            update = (
                                {
                                    "l": max(left, min(x0 for x0, _ in inside)),
                                    "r": min(right, max(x1 for _, x1 in inside)),
                                }
                                if inside
                                else {"l": left, "r": right}
                            )
                            split.append(
                                PositionedText(
                                    cell.box.model_copy(update=update), text, False
                                )
                            )
    return split


def _table_data(
    cells: list[PositionedText],
    columns: list[float],
    header_bottom: float,
) -> TableData:
    from docling_core.types.doc import BoundingBox, CoordOrigin, TableCell, TableData

    rows = _rows(cells)
    table_cells = []
    for row_index, row in enumerate(rows):
        grouped: dict[int, list[PositionedText]] = {}
        for cell in sorted(row, key=lambda cell: cell.box.l):
            # Prefer the start of a phrase to its center: headings may span
            # several physical columns, while data normally stays inside one.
            position = cell.box.l + min(3, cell.box.width / 2)
            column = min(max(0, bisect_right(columns, position) - 1), len(columns) - 2)
            grouped.setdefault(column, []).append(cell)
        top = min(cell.box.t for cell in row)
        bottom = max(cell.box.b for cell in row)
        for column in range(len(columns) - 1):
            contents = grouped.get(column, [])
            text = " ".join(cell.text for cell in contents)
            bbox = BoundingBox(
                l=min(cell.box.l for cell in contents) if contents else columns[column],
                r=max(cell.box.r for cell in contents)
                if contents
                else columns[column + 1],
                t=top,
                b=bottom,
                coord_origin=CoordOrigin.TOPLEFT,
            )
            table_cells.append(
                TableCell(
                    text=text,
                    bbox=bbox,
                    column_header=(top + bottom) / 2 < header_bottom,
                    start_row_offset_idx=row_index,
                    end_row_offset_idx=row_index + 1,
                    start_col_offset_idx=column,
                    end_col_offset_idx=column + 1,
                )
            )
    return TableData(
        num_rows=len(rows), num_cols=len(columns) - 1, table_cells=table_cells
    )


def restore_ruled_tables(conversion: ConversionResult, path: Path | None = None) -> int:
    """Restore large ruled forms before recovering any remaining loose text."""
    from docling_core.types.doc import (
        BoundingBox,
        ContentLayer,
        CoordOrigin,
        ProvenanceItem,
    )

    document = conversion.document
    restored = 0
    for page in getattr(conversion, "pages", []):
        saved_page = document.pages.get(page.page_no)
        if page.size is None or saved_page is None or saved_page.image is None:
            continue
        image = saved_page.image.pil_image
        grid = ruled_grid(image)
        if grid is None:
            continue
        pixels, top, bottom, header, _ = grid
        scale_x = page.size.width / image.width
        scale_y = page.size.height / image.height
        columns = [x * scale_x for x in pixels]
        grid_box = BoundingBox(
            l=columns[0],
            r=columns[-1],
            t=top * scale_y,
            b=bottom * scale_y,
            coord_origin=CoordOrigin.TOPLEFT,
        )
        cells = [
            cell
            for cell in recognized_text(page)
            if cell.box.intersection_over_self(grid_box) >= 0.65
        ]
        if not cells:
            continue
        cells = split_native_columns(cells, columns, path, page.page_no, page.size)
        candidates = []
        multiple_pages = False
        for item, _ in document.iterate_items(
            traverse_pictures=True,
            included_content_layers=set(ContentLayer),
        ):
            for prov in item.prov:
                if prov.page_no != page.page_no:
                    continue
                bbox = prov.bbox.to_top_left_origin(page.size.height)
                if bbox.area() > 0 and bbox.intersection_over_self(grid_box) >= 0.65:
                    if len({p.page_no for p in item.prov}) > 1:
                        multiple_pages = True
                    candidates.append(item)
                    break
        if not candidates or multiple_pages:
            continue
        references = {item.self_ref for item in candidates}
        roots = []
        for item in candidates:
            parent = item.parent
            while parent is not None and parent.cref not in references:
                parent = parent.resolve(document).parent
            if parent is None:
                roots.append(item)
        if not roots:
            continue
        data = _table_data(cells, columns, header * scale_y)
        document.insert_table(
            sibling=roots[0],
            after=False,
            data=data,
            prov=ProvenanceItem(
                page_no=page.page_no,
                bbox=grid_box.to_bottom_left_origin(page.size.height),
                charspan=(0, 0),
            ),
        )
        document.delete_items(node_items=roots)
        restored += 1
    return restored
