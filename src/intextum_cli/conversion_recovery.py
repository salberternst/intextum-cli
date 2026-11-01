"""Retain recognized text omitted by Docling's layout and table assembly."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docling.datamodel.document import ConversionResult
    from docling_core.types.doc import BoundingBox, DoclingDocument


def _normalized(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


def _coverage(
    document: DoclingDocument, page_no: int, height: float
) -> list[tuple[BoundingBox, str]]:
    covered: list[tuple[BoundingBox, str]] = []
    for item in document.texts:
        for prov in item.prov:
            if prov.page_no == page_no:
                start, end = prov.charspan
                covered.append(
                    (
                        prov.bbox.to_top_left_origin(height),
                        _normalized(item.text[start:end]),
                    )
                )
    for table in document.tables:
        for prov in table.prov:
            if prov.page_no != page_no:
                continue
            rows: dict[int, list] = {}
            for cell in table.data.table_cells:
                rows.setdefault(cell.start_row_offset_idx, []).append(cell)
                covered.append(
                    (
                        (cell.bbox or prov.bbox).to_top_left_origin(height),
                        _normalized(cell.text),
                    )
                )
            for cells in rows.values():
                nonempty = sorted(
                    (cell for cell in cells if cell.text),
                    key=lambda cell: cell.start_col_offset_idx,
                )
                if not nonempty:
                    continue
                boxes = [
                    (cell.bbox or prov.bbox).to_top_left_origin(height)
                    for cell in nonempty
                ]
                covered.append(
                    (
                        boxes[0].model_copy(
                            update={
                                "l": min(box.l for box in boxes),
                                "r": max(box.r for box in boxes),
                                "t": min(box.t for box in boxes),
                                "b": max(box.b for box in boxes),
                            }
                        ),
                        _normalized(" ".join(cell.text for cell in nonempty)),
                    )
                )
    return covered


def _lines(cells: list[tuple[BoundingBox, str]]) -> list[str]:
    """Join OCR words on the same line without merging neighboring rows."""
    rows: list[list[tuple[BoundingBox, str]]] = []
    for box, text in sorted(cells, key=lambda cell: (cell[0].t, cell[0].l)):
        if rows:
            previous = rows[-1][0][0]
            overlap = min(box.b, previous.b) - max(box.t, previous.t)
            if overlap >= min(box.height, previous.height) / 2:
                rows[-1].append((box, text))
                continue
        rows.append([(box, text)])
    return [
        " ".join(text for _, text in sorted(row, key=lambda cell: cell[0].l))
        for row in rows
    ]


def restore_recognized_text(conversion: ConversionResult) -> int:
    """Restore unrepresented text cells, keeping their page and bounding box.

    Scanned forms can be classified as pictures, or a table may use only the
    native PDF words even after OCR recognized its scanned entries. Match both
    text and location before treating an OCR cell as already represented.
    """
    from docling_core.types.doc import (
        BoundingBox,
        CoordOrigin,
        DocItemLabel,
        ProvenanceItem,
    )

    document = conversion.document
    restored = 0
    for page in getattr(conversion, "pages", []):
        if page.size is None:
            continue
        covered = _coverage(document, page.page_no, page.size.height)
        missing: list[tuple[BoundingBox, str]] = []
        # The pipeline can release parsed_page during cleanup. Layout clusters
        # retain their assigned OCR cells after assembly.
        cells = list(page.cells)
        layout = getattr(getattr(page, "predictions", None), "layout", None)
        clusters = list(layout.clusters) if layout is not None else []
        while clusters:
            cluster = clusters.pop(0)
            cells.extend(cluster.cells)
            clusters.extend(cluster.children)
        for cell in cells:
            text = cell.text.strip()
            if not any(char.isalnum() for char in text):
                continue
            box = cell.rect.to_bounding_box().to_top_left_origin(page.size.height)
            if box.area() <= 0:
                continue
            needle = _normalized(text)
            if any(
                needle in existing and box.intersection_over_self(region) >= 0.5
                for region, existing in covered
            ):
                continue
            missing.append((box, text))
            covered.append((box, needle))
        if not missing:
            continue
        text = "\n".join(_lines(missing))
        bbox = BoundingBox(
            l=min(box.l for box, _ in missing),
            t=min(box.t for box, _ in missing),
            r=max(box.r for box, _ in missing),
            b=max(box.b for box, _ in missing),
            coord_origin=CoordOrigin.TOPLEFT,
        ).to_bottom_left_origin(page.size.height)
        prov = ProvenanceItem(page_no=page.page_no, bbox=bbox, charspan=(0, len(text)))
        # Insert next to this page's existing content so Markdown page breaks
        # and the source-to-element index keep referring to the original page.
        items = [item for item, _ in document.iterate_items() if item.prov]
        same_page = [
            item for item in items if any(p.page_no == page.page_no for p in item.prov)
        ]
        later = [
            item for item in items if min(p.page_no for p in item.prov) > page.page_no
        ]
        if same_page or later:
            document.insert_text(
                sibling=same_page[-1] if same_page else later[0],
                after=bool(same_page),
                label=DocItemLabel.TEXT,
                text=text,
                prov=prov,
            )
        else:
            document.add_text(label=DocItemLabel.TEXT, text=text, prov=prov)
        restored += len(missing)
    return restored
