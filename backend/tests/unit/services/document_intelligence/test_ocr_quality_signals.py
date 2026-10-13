"""OCR quality reaches the extraction model, and sideways reads are not trusted.

No OCR binary is needed: pages are built directly or read by a scripted engine.
"""

from __future__ import annotations

import io
import math
import re
from collections.abc import Sequence
from typing import Any

import pytest
from PIL import Image, ImageDraw

from app.services.document_intelligence import (
    DocumentIntelligencePolicy,
    DocumentIntelligenceService,
)
from app.services.document_intelligence.models import (
    BoundingBox,
    DocumentExtraction,
    ExtractionMethod,
    ExtractionRoute,
    PageClass,
    PageExtraction,
    PageQuality,
    TextLine,
    WordBox,
)
from app.services.document_intelligence.ocr import OcrResult, OcrWord
from tests.unit.services.document_intelligence.phone_photo_fixtures import (
    lab_report_image,
    png_bytes,
    rotate,
)

PAGE_MARKER = re.compile(r"^\[\[page (\d+)(?: — ([^\]]+))?\]\]$", re.MULTILINE)


def _page(number: int, method: ExtractionMethod, quality: PageQuality) -> PageExtraction:
    bbox = BoundingBox(x0=10, y0=10, x1=200, y1=30)
    return PageExtraction(
        page_number=number,
        page_class=(
            PageClass.BORN_DIGITAL_TEXT
            if method is ExtractionMethod.EMBEDDED_TEXT
            else PageClass.SCANNED_IMAGE
        ),
        method=method,
        width=612,
        height=792,
        words=[WordBox(text="Sodium", bbox=bbox, confidence=0.9, line_id=0, method=method)],
        lines=[TextLine(line_id=0, text="Sodium 139 mmol/L", bbox=bbox, confidence=0.9)],
        text="Sodium 139 mmol/L",
        quality=quality,
    )


def _document(*pages: PageExtraction) -> DocumentExtraction:
    return DocumentExtraction(
        document_class="mixed",
        mime_type="application/pdf",
        source_sha256="0" * 64,
        page_count=len(pages),
        pages=list(pages),
        route=ExtractionRoute.REVIEW_WITH_CAUTION,
        route_reason="low_quality_pages_present",
        extractor_version="test",
    )


def test_page_headers_say_how_each_page_was_read() -> None:
    text = _document(
        _page(1, ExtractionMethod.EMBEDDED_TEXT, PageQuality.USABLE),
        _page(2, ExtractionMethod.OCR, PageQuality.USABLE),
        _page(3, ExtractionMethod.OCR, PageQuality.LOW),
        _page(4, ExtractionMethod.OCR, PageQuality.UNUSABLE),
    ).text_for_model()

    assert PAGE_MARKER.findall(text) == [
        ("1", ""),
        ("2", "OCR"),
        ("3", "OCR, low confidence: verify numbers"),
    ]
    assert text.startswith("[[page 1]]\nSodium 139 mmol/L\n\n[[page 2 — OCR]]\n")
    assert "[[page 3 — OCR, low confidence: verify numbers]]\nSodium 139 mmol/L" in text


# ── Orientation with a scripted engine ───────────────────


class AspectScriptedEngine:
    """Reads tall (sideways) words on one raster aspect and wide words on the other."""

    name = "scripted"
    version = "0.1"

    def __init__(self, *, sideways_when_portrait: bool, osd: int | None) -> None:
        self.sideways_when_portrait = sideways_when_portrait
        self.osd = osd
        self.calls = 0

    def available_languages(self) -> frozenset[str]:
        return frozenset({"eng"})

    def orientation_degrees(self, image: Any) -> int | None:
        return self.osd

    def recognize(self, image: Any, *, languages: Sequence[str], timeout_seconds: int) -> OcrResult:
        self.calls += 1
        portrait = image.height >= image.width
        sideways = portrait == self.sideways_when_portrait
        # The sideways read is the more confident one and has more characters, which is
        # exactly what a confidence-only orientation check would prefer.
        texts = ["Hemoglobin", "Metformin", "twice", "daily", "Sodium"]
        if sideways:
            texts.append("Potassium")
        return OcrResult(
            words=[
                OcrWord(
                    text=text,
                    left=40 + index * 60,
                    top=100,
                    width=30 if sideways else 180,
                    height=180 if sideways else 30,
                    confidence=0.97 if sideways else 0.9,
                    block=1,
                    paragraph=1,
                    line=index + 1 if sideways else 1,
                )
                for index, text in enumerate(texts)
            ],
            languages=list(languages),
        )


def _band_png(width: int, height: int) -> bytes:
    image = Image.new("L", (width, height), 255)
    ImageDraw.Draw(image).rectangle((width // 10, height // 8, width // 2, height // 8 + 40), 0)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _extract(engine: AspectScriptedEngine, png: bytes) -> PageExtraction:
    service = DocumentIntelligenceService(ocr_engine=engine, policy=DocumentIntelligencePolicy())
    return service.extract(png, mime_type="image/png").pages[0]


def test_confident_sideways_read_yields_to_the_osd_rotation() -> None:
    engine = AspectScriptedEngine(sideways_when_portrait=True, osd=90)

    page = _extract(engine, _band_png(1275, 1650))

    assert page.rotation_applied == 90
    assert "Potassium" not in page.text
    assert any("OSD" in warning for warning in page.warnings)


def test_sideways_read_triggers_the_rotation_search_without_osd() -> None:
    engine = AspectScriptedEngine(sideways_when_portrait=True, osd=None)

    page = _extract(engine, _band_png(1275, 1650))

    assert page.rotation_applied in (90, 270)
    assert any("confidence search" in warning for warning in page.warnings)
    assert engine.calls == 4


def test_osd_suggestion_that_reads_sideways_is_rejected() -> None:
    engine = AspectScriptedEngine(sideways_when_portrait=True, osd=90)

    page = _extract(engine, _band_png(1650, 1275))

    assert page.rotation_applied == 0
    assert page.text == "Hemoglobin Metformin twice daily Sodium"
    assert engine.calls == 2


def test_low_confidence_scan_is_flagged_in_the_model_input() -> None:
    class LowConfidenceEngine(AspectScriptedEngine):
        def recognize(self, image: Any, **kwargs: Any) -> OcrResult:
            result = super().recognize(image, **kwargs)
            return result.model_copy(
                update={"words": [w.model_copy(update={"confidence": 0.6}) for w in result.words]}
            )

    service = DocumentIntelligenceService(
        ocr_engine=LowConfidenceEngine(sideways_when_portrait=False, osd=None),
        policy=DocumentIntelligencePolicy(),
    )
    extraction = service.extract(_band_png(1275, 1650), mime_type="image/png")

    assert extraction.pages[0].quality is PageQuality.LOW
    assert extraction.text_for_model().startswith(
        "[[page 1 — OCR, low confidence: verify numbers]]\n"
    )


def test_straightened_page_reports_the_straightened_frame() -> None:
    tilted = rotate(lab_report_image(), -6)
    engine = AspectScriptedEngine(sideways_when_portrait=False, osd=None)

    page = _extract(engine, png_bytes(tilted))

    radians = math.radians(page.deskew_degrees)
    expected_width = tilted.width * math.cos(radians) + tilted.height * math.sin(radians)
    assert page.deskew_degrees == pytest.approx(6.0, abs=0.3)
    assert page.width == pytest.approx(expected_width)
    assert page.coordinate_unit == "px"
