"""Embedded-text extraction for born-digital PDF pages with PyMuPDF.

Words keep their PDF-point bounding boxes and are grouped into lines and blocks in a
column-aware reading order, so a two-column visit summary is not interleaved line by
line. Ruled tables are recovered with PyMuPDF's table finder when present.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.document_intelligence.models import (
    BoundingBox,
    ExtractionMethod,
    TableCell,
    TableExtraction,
    TextLine,
    WordBox,
)

logger = logging.getLogger(__name__)

EMBEDDED_WORD_CONFIDENCE = 1.0
_COLUMN_TOLERANCE_RATIO = 0.04


class EmbeddedPageText:
    """Reading-ordered words, lines, and tables from one PDF page."""

    def __init__(self, words: list[WordBox], lines: list[TextLine], tables: list[TableExtraction]):
        self.words = words
        self.lines = lines
        self.tables = tables

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


def extract_embedded_page(page: Any) -> EmbeddedPageText:
    """Read the text layer of one PyMuPDF page in reading order."""
    raw_words = page.get_text("words")
    blocks = _group_words_by_block(raw_words)
    ordered_blocks = _order_blocks(blocks, page_width=float(page.rect.width))
    words: list[WordBox] = []
    lines: list[TextLine] = []
    for block in ordered_blocks:
        _append_block_lines(block, words, lines)
    return EmbeddedPageText(words, lines, _find_tables(page))


def _group_words_by_block(raw_words: list[tuple[Any, ...]]) -> list[list[tuple[Any, ...]]]:
    by_block: dict[int, list[tuple[Any, ...]]] = {}
    for raw in raw_words:
        by_block.setdefault(int(raw[5]), []).append(raw)
    return [by_block[key] for key in sorted(by_block)]


def _block_bbox(block: list[tuple[Any, ...]]) -> BoundingBox:
    return BoundingBox(
        x0=min(float(w[0]) for w in block),
        y0=min(float(w[1]) for w in block),
        x1=max(float(w[2]) for w in block),
        y1=max(float(w[3]) for w in block),
    )


def _order_blocks(
    blocks: list[list[tuple[Any, ...]]], *, page_width: float
) -> list[list[tuple[Any, ...]]]:
    """Order blocks top to bottom, reading a left column before a right column.

    Two columns exist only where right-side blocks actually sit; the vertical band they
    span is read column by column, while headings above it, footers below it, and any
    block that straddles the midline are emitted in plain top-to-bottom order.
    """
    if not blocks:
        return []
    midline = page_width / 2
    tolerance = page_width * _COLUMN_TOLERANCE_RATIO
    annotated = sorted(
        ((_block_bbox(block), block) for block in blocks), key=lambda item: item[0].y0
    )
    right_boxes = [bbox for bbox, _ in annotated if bbox.x0 >= midline - tolerance]
    band = (
        (
            min(box.y0 for box in right_boxes) - tolerance,
            max(box.y1 for box in right_boxes) + tolerance,
        )
        if right_boxes
        else None
    )
    ordered: list[list[tuple[Any, ...]]] = []
    left: list[list[tuple[Any, ...]]] = []
    right: list[list[tuple[Any, ...]]] = []
    for bbox, block in annotated:
        in_band = band is not None and bbox.y1 > band[0] and bbox.y0 < band[1]
        if in_band and bbox.x1 <= midline + tolerance:
            left.append(block)
        elif in_band and bbox.x0 >= midline - tolerance:
            right.append(block)
        else:
            ordered.extend(left)
            ordered.extend(right)
            left, right = [], []
            ordered.append(block)
    ordered.extend(left)
    ordered.extend(right)
    return ordered


def _append_block_lines(
    block: list[tuple[Any, ...]], words: list[WordBox], lines: list[TextLine]
) -> None:
    by_line: dict[int, list[tuple[Any, ...]]] = {}
    for raw in block:
        by_line.setdefault(int(raw[6]), []).append(raw)
    for line_key in sorted(by_line):
        line_words = sorted(by_line[line_key], key=lambda w: float(w[0]))
        line_id = len(lines)
        boxes = [
            WordBox(
                text=str(raw[4]),
                bbox=BoundingBox(
                    x0=float(raw[0]), y0=float(raw[1]), x1=float(raw[2]), y1=float(raw[3])
                ),
                confidence=EMBEDDED_WORD_CONFIDENCE,
                line_id=line_id,
                method=ExtractionMethod.EMBEDDED_TEXT,
            )
            for raw in line_words
        ]
        bbox = boxes[0].bbox
        for box in boxes[1:]:
            bbox = bbox.union(box.bbox)
        words.extend(boxes)
        lines.append(
            TextLine(
                line_id=line_id,
                text=" ".join(box.text for box in boxes),
                bbox=bbox,
                confidence=EMBEDDED_WORD_CONFIDENCE,
            )
        )


def _find_tables(page: Any) -> list[TableExtraction]:
    try:
        found = page.find_tables()
    except Exception as exc:  # noqa: BLE001 - table detection is best effort
        logger.info("Table detection unavailable on page %s: %s", page.number, exc)
        return []
    tables: list[TableExtraction] = []
    for table in found.tables:
        cells = _table_cells(table)
        if not cells:
            continue
        rect = table.bbox
        tables.append(
            TableExtraction(
                bbox=BoundingBox(x0=rect[0], y0=rect[1], x1=rect[2], y1=rect[3]),
                row_count=table.row_count,
                col_count=table.col_count,
                cells=cells,
            )
        )
    return tables


def _table_cells(table: Any) -> list[TableCell]:
    cells: list[TableCell] = []
    matrix = table.extract()
    for row_index, row in enumerate(table.rows):
        texts = matrix[row_index] if row_index < len(matrix) else []
        for col_index, cell_rect in enumerate(row.cells):
            if cell_rect is None:
                continue
            text = texts[col_index] if col_index < len(texts) else None
            cells.append(
                TableCell(
                    row=row_index,
                    col=col_index,
                    text=" ".join(str(text or "").split()),
                    bbox=BoundingBox(
                        x0=cell_rect[0], y0=cell_rect[1], x1=cell_rect[2], y1=cell_rect[3]
                    ),
                )
            )
    return cells
