"""Real Tesseract over synthetic phone-photo degradations of a synthetic lab report.

These tests exercise the installed OCR engine end to end, so they skip cleanly where
Tesseract or its English model is unavailable (CI installs neither). Readable
degradations must keep each value on its printed row; unreadable ones must send no
text to the extraction model and route the document to clinician review.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.services.document_intelligence import (
    DocumentExtraction,
    DocumentIntelligenceService,
    ExtractionRoute,
    PageQuality,
)
from app.services.document_intelligence.ocr import OcrEngineUnavailableError, TesseractOcrEngine
from tests.unit.services.document_intelligence.phone_photo_fixtures import (
    EXPECTED_PHRASES,
    EXPECTED_ROW_VALUES,
    READABLE_DEGRADATIONS,
    UNREADABLE_DEGRADATIONS,
    lab_report_image,
    png_bytes,
)


@pytest.fixture(scope="module")
def engine() -> TesseractOcrEngine:
    try:
        tesseract = TesseractOcrEngine()
    except OcrEngineUnavailableError as exc:
        pytest.skip(f"Tesseract is not installed: {exc.message}")
    if "eng" not in tesseract.available_languages():
        pytest.skip("Tesseract English language data is not installed")
    return tesseract


@pytest.fixture(scope="module")
def report():
    return lab_report_image()


def _extract(engine: TesseractOcrEngine, image) -> DocumentExtraction:
    return DocumentIntelligenceService(ocr_engine=engine).extract(
        png_bytes(image), mime_type="image/png", file_name="synthetic-photo.png"
    )


@pytest.fixture(scope="module")
def extracted(engine, report) -> Callable[[str], DocumentExtraction]:
    """Each degradation is recognized once per module; OCR dominates the run time."""
    cache: dict[str, DocumentExtraction] = {}
    degradations = {**READABLE_DEGRADATIONS, **UNREADABLE_DEGRADATIONS}

    def get(name: str) -> DocumentExtraction:
        if name not in cache:
            cache[name] = _extract(engine, degradations[name](report))
        return cache[name]

    return get


def _row_tokens(text: str, label: str) -> list[str]:
    """Whole tokens of the printed row, so "78" or "17.8" never pass for "7.8"."""
    row = next((line for line in text.splitlines() if label in line), "")
    return row.replace("|", " ").split()


@pytest.mark.parametrize("name", sorted(READABLE_DEGRADATIONS))
def test_readable_degradation_keeps_values_on_their_rows(extracted, name: str) -> None:
    extraction = extracted(name)

    page = extraction.pages[0]
    text = extraction.text_for_model()
    assert page.quality in (PageQuality.USABLE, PageQuality.LOW), (page.confidence, text)
    assert extraction.route in (
        ExtractionRoute.AUTOMATED_CANDIDATES,
        ExtractionRoute.REVIEW_WITH_CAUTION,
    )
    assert text.startswith("[[page 1 — OCR")
    for label, value in EXPECTED_ROW_VALUES.items():
        assert value in _row_tokens(text, label), f"{name}: {label} row lost {value!r}:\n{text}"
    for phrase in EXPECTED_PHRASES:
        assert phrase in text, f"{name}: {phrase!r} missing:\n{text}"


@pytest.mark.parametrize("name", sorted(UNREADABLE_DEGRADATIONS))
def test_unreadable_photo_reaches_clinician_review_without_model_text(extracted, name: str) -> None:
    extraction = extracted(name)

    assert extraction.route is ExtractionRoute.CLINICIAN_ONLY
    assert extraction.route_reason == "no_usable_page_text"
    assert extraction.text_for_model() == ""
    assert extraction.pages[0].quality in (PageQuality.UNUSABLE, PageQuality.EMPTY)


def test_tilted_photo_is_straightened_and_reported(extracted) -> None:
    page = extracted("tilt_minus_7_degrees").pages[0]

    assert page.deskew_degrees == pytest.approx(7.0, abs=0.5)
    assert any("deskewed" in warning for warning in page.warnings)
    assert all(word.bbox.x1 <= page.width + 1 for word in page.words)


@pytest.mark.parametrize(("name", "rotation"), [("sideways_90", 90), ("sideways_270", 270)])
def test_sideways_photo_is_read_upright(extracted, name: str, rotation: int) -> None:
    page = extracted(name).pages[0]

    assert page.rotation_applied == rotation
    assert page.width < page.height


def test_preparation_is_deterministic(engine, report, extracted) -> None:
    first = extracted("phone_photo_combined")
    second = _extract(engine, READABLE_DEGRADATIONS["phone_photo_combined"](report))

    assert first.text_for_model() == second.text_for_model()
    assert first.pages[0].confidence == second.pages[0].confidence
