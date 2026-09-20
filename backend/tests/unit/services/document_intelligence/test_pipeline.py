"""Pipeline behaviour with a fake OCR engine: no Tesseract binary is required here."""

from __future__ import annotations

import io
from collections.abc import Sequence
from typing import Any

import pymupdf
import pytest
from PIL import Image

from app.services.document_intelligence import (
    DocumentClass,
    DocumentIntelligencePolicy,
    DocumentIntelligenceService,
    ExtractionMethod,
    ExtractionRoute,
    FailureKind,
    PageClass,
    PageQuality,
)
from app.services.document_intelligence.ocr import OcrResult, OcrWord


class FakeOcrEngine:
    """Returns scripted words; confidence depends on whether the raster is upright."""

    name = "fake"
    version = "0.1"

    def __init__(
        self,
        words: Sequence[str] = ("Metformin", "500", "mg"),
        *,
        confidence: float = 0.95,
        osd: int | None = None,
        upright_portrait: bool = True,
        fail: bool = False,
    ) -> None:
        self.words = list(words)
        self.confidence = confidence
        self.osd = osd
        self.upright_portrait = upright_portrait
        self.fail = fail
        self.calls = 0

    def available_languages(self) -> frozenset[str]:
        return frozenset({"eng"})

    def orientation_degrees(self, image: Any) -> int | None:
        return self.osd

    def recognize(self, image: Any, *, languages: Sequence[str], timeout_seconds: int) -> OcrResult:
        self.calls += 1
        if self.fail:
            raise TimeoutError("tesseract timed out")
        upright = image.height >= image.width if self.upright_portrait else True
        confidence = self.confidence if upright else 0.2
        words = [
            OcrWord(
                text=text if upright else "xq",
                left=40 + index * 200,
                top=100,
                width=180,
                height=40,
                confidence=confidence,
                block=1,
                paragraph=1,
                line=1,
            )
            for index, text in enumerate(self.words)
        ]
        return OcrResult(words=words, languages=list(languages))


def _text_pdf(lines: Sequence[str], *, pages: int = 1) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page(width=612, height=792)
        y = 72.0
        for line in lines:
            page.insert_text((48, y), line, fontsize=11, fontname="helv")
            y += 16
    data = doc.tobytes()
    doc.close()
    return bytes(data)


def _image_pdf(image: Image.Image, *, landscape: bool = False) -> bytes:
    doc = pymupdf.open()
    width, height = (792, 612) if landscape else (612, 792)
    page = doc.new_page(width=width, height=height)
    page.insert_image(page.rect, stream=_png(image))
    data = doc.tobytes()
    doc.close()
    return bytes(data)


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _scan_image(width: int = 1275, height: int = 1650) -> Image.Image:
    """A page-shaped raster with one band of "ink".

    The band is placed proportionally rather than at fixed pixel offsets so the helper
    works for small rasters too: at the default size it starts at x=100, and the
    upscaling test relies on that ratio holding when the image is 400px wide.
    """
    image = Image.new("L", (width, height), 255)
    x_start = max(1, round(width * 100 / 1275))
    x_end = max(x_start + 1, round(width * 900 / 1275))
    y_start = max(1, round(height * 200 / 1650))
    y_end = max(y_start + 1, round(height * 240 / 1650))
    for x in range(x_start, min(x_end, width)):
        for y in range(y_start, min(y_end, height)):
            image.putpixel((x, y), 0)
    return image


def _service(engine: Any = None, **policy: Any) -> DocumentIntelligenceService:
    return DocumentIntelligenceService(
        ocr_engine=engine, policy=DocumentIntelligencePolicy(**policy)
    )


# ── Born-digital PDFs ────────────────────────────────────


def test_born_digital_pdf_uses_embedded_text_with_coordinates() -> None:
    extraction = _service(FakeOcrEngine()).extract(
        _text_pdf(["Lisinopril 10 mg once daily", "Metformin 500 mg twice daily"]),
        mime_type="application/pdf",
        file_name="meds.pdf",
    )

    assert extraction.document_class is DocumentClass.BORN_DIGITAL_TEXT
    assert extraction.route is ExtractionRoute.AUTOMATED_CANDIDATES
    page = extraction.pages[0]
    assert page.method is ExtractionMethod.EMBEDDED_TEXT
    assert page.quality is PageQuality.USABLE
    assert page.confidence == 1.0
    assert page.text.splitlines() == ["Lisinopril 10 mg once daily", "Metformin 500 mg twice daily"]
    assert page.coordinate_unit == "pt"
    assert page.words[0].bbox.x0 == pytest.approx(48, abs=1)
    assert extraction.text_for_model().startswith("[[page 1]]")
    assert "pymupdf" in extraction.engine_versions
    assert extraction.extractor_version.startswith("document-intelligence/1;")


def test_empty_pdf_pages_are_blank_and_the_document_is_rejected() -> None:
    doc = pymupdf.open()
    doc.new_page()
    doc.new_page()
    extraction = _service(FakeOcrEngine()).extract(
        bytes(doc.tobytes()), mime_type="application/pdf"
    )

    assert [page.page_class for page in extraction.pages] == [PageClass.BLANK, PageClass.BLANK]
    assert extraction.document_class is DocumentClass.BLANK
    assert extraction.route is ExtractionRoute.REJECTED
    assert extraction.route_reason == "blank_document"
    assert extraction.failure_kind is FailureKind.PERMANENT


def test_encrypted_pdf_is_rejected_permanently_without_reading_pages() -> None:
    doc = pymupdf.open()
    doc.new_page().insert_text((48, 72), "Warfarin 5 mg", fontname="helv")
    data = bytes(
        doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    )

    extraction = _service(FakeOcrEngine()).extract(data, mime_type="application/pdf")

    assert extraction.document_class is DocumentClass.ENCRYPTED
    assert extraction.route is ExtractionRoute.REJECTED
    assert extraction.failure_kind is FailureKind.PERMANENT
    assert extraction.pages == []


def test_bytes_that_do_not_match_the_declared_type_are_unreadable() -> None:
    extraction = _service(FakeOcrEngine()).extract(
        b"\x00\x01not a pdf", mime_type="application/pdf"
    )

    assert extraction.document_class is DocumentClass.UNREADABLE
    assert extraction.route is ExtractionRoute.REJECTED


def test_unknown_container_is_unsupported() -> None:
    extraction = _service(FakeOcrEngine()).extract(b"PK\x03\x04", mime_type="application/zip")

    assert extraction.document_class is DocumentClass.UNSUPPORTED
    assert extraction.route is ExtractionRoute.REJECTED
    assert extraction.failure_kind is FailureKind.PERMANENT


def test_truncated_pdf_is_never_treated_as_complete() -> None:
    """A cut-off PDF must not yield automated candidates, however it is classified.

    Whether MuPDF can repair a truncation depends on where the cut lands, so this does
    not demand a repair. The corpus documents the same contract: `build_truncated_pdf`
    expects `UNREADABLE` with `REJECTED` or `REVIEW_WITH_CAUTION`, and merely permits a
    repaired born-digital result. The guarantee under test is the one that matters
    clinically — a partial document never reaches the automated path.
    """
    complete = _text_pdf(["Metoprolol 50 mg twice daily"], pages=2)
    truncated = complete[: int(len(complete) * 0.6)]

    extraction = _service(FakeOcrEngine()).extract(truncated, mime_type="application/pdf")

    assert extraction.route is not ExtractionRoute.AUTOMATED_CANDIDATES

    if extraction.repaired:
        assert extraction.route is ExtractionRoute.REVIEW_WITH_CAUTION
        assert extraction.route_reason == "pdf_repaired"
        assert any("repaired" in warning for warning in extraction.warnings)
    else:
        assert extraction.document_class is DocumentClass.UNREADABLE
        assert extraction.failure_kind is FailureKind.PERMANENT


def test_page_limit_processes_a_prefix_and_warns() -> None:
    extraction = _service(FakeOcrEngine(), max_pages=2).extract(
        _text_pdf(["Aspirin 81 mg"], pages=3), mime_type="application/pdf"
    )

    assert extraction.page_count == 2
    assert any("first 2 of 3 pages" in warning for warning in extraction.warnings)


# ── Scanned PDFs and OCR ─────────────────────────────────


def test_scanned_pdf_runs_ocr_and_converts_pixels_to_points() -> None:
    engine = FakeOcrEngine(confidence=0.96)
    extraction = _service(engine, render_dpi=150).extract(
        _image_pdf(_scan_image()), mime_type="application/pdf"
    )

    page = extraction.pages[0]
    assert extraction.document_class is DocumentClass.SCANNED_IMAGE
    assert page.page_class is PageClass.SCANNED_IMAGE
    assert page.method is ExtractionMethod.OCR
    assert page.render_dpi == 150
    assert page.text == "Metformin 500 mg"
    assert page.quality is PageQuality.USABLE
    assert page.confidence == pytest.approx(0.96)
    # 40 px at 150 dpi is 19.2 pt
    assert page.words[0].bbox.x0 == pytest.approx(19.2, abs=0.01)
    assert extraction.route is ExtractionRoute.AUTOMATED_CANDIDATES
    assert engine.calls == 1


def test_low_confidence_ocr_page_routes_to_review_with_caution() -> None:
    extraction = _service(FakeOcrEngine(confidence=0.6), render_dpi=100).extract(
        _image_pdf(_scan_image()), mime_type="application/pdf"
    )

    assert extraction.pages[0].quality is PageQuality.LOW
    assert extraction.route is ExtractionRoute.REVIEW_WITH_CAUTION
    assert extraction.route_reason == "low_quality_pages_present"
    assert extraction.model_input_pages()


def test_unusable_ocr_page_is_excluded_from_model_input_and_routed_to_clinician() -> None:
    extraction = _service(FakeOcrEngine(confidence=0.3), render_dpi=100).extract(
        _image_pdf(_scan_image()), mime_type="application/pdf"
    )

    assert extraction.pages[0].quality is PageQuality.UNUSABLE
    assert extraction.route is ExtractionRoute.CLINICIAN_ONLY
    assert extraction.text_for_model() == ""


def test_osd_suggestion_is_verified_before_it_is_applied() -> None:
    engine = FakeOcrEngine(osd=90, upright_portrait=True)
    landscape = _scan_image(1650, 1275)

    extraction = _service(engine, render_dpi=100).extract(
        _image_pdf(landscape, landscape=True), mime_type="application/pdf"
    )

    page = extraction.pages[0]
    assert page.rotation_applied == 90
    assert page.text == "Metformin 500 mg"
    assert (page.width, page.height) == (612, 792)
    assert any("OSD" in warning for warning in page.warnings)
    assert engine.calls == 2


def test_rotation_is_found_by_search_when_osd_is_silent() -> None:
    engine = FakeOcrEngine(osd=None, upright_portrait=True)
    landscape = _scan_image(1650, 1275)

    extraction = _service(engine, render_dpi=100).extract(
        _image_pdf(landscape, landscape=True), mime_type="application/pdf"
    )

    page = extraction.pages[0]
    assert page.rotation_applied in (90, 270)
    assert page.text == "Metformin 500 mg"
    assert any("confidence search" in warning for warning in page.warnings)


def test_wrong_osd_suggestion_on_an_upright_page_is_rejected() -> None:
    engine = FakeOcrEngine(osd=90, upright_portrait=True)

    extraction = _service(engine, render_dpi=100).extract(
        _image_pdf(_scan_image()), mime_type="application/pdf"
    )

    assert extraction.pages[0].rotation_applied == 0
    assert extraction.pages[0].text == "Metformin 500 mg"


def test_image_page_without_ink_is_blank_and_skips_ocr() -> None:
    engine = FakeOcrEngine()
    blank = Image.new("L", (1275, 1650), 255)

    extraction = _service(engine, render_dpi=100).extract(
        _image_pdf(blank), mime_type="application/pdf"
    )

    assert extraction.pages[0].page_class is PageClass.BLANK
    assert engine.calls == 0
    assert extraction.route is ExtractionRoute.REJECTED


def test_ocr_engine_failure_is_a_page_warning_not_a_crash() -> None:
    extraction = _service(FakeOcrEngine(fail=True), render_dpi=100).extract(
        _image_pdf(_scan_image()), mime_type="application/pdf"
    )

    page = extraction.pages[0]
    assert page.words == []
    assert any(warning.startswith("OCR failed") for warning in page.warnings)
    assert extraction.route is ExtractionRoute.CLINICIAN_ONLY


def test_ocr_disabled_by_policy_matches_current_production_behaviour() -> None:
    extraction = _service(None, ocr_enabled=False, render_dpi=100).extract(
        _image_pdf(_scan_image()), mime_type="application/pdf"
    )

    page = extraction.pages[0]
    assert page.quality is PageQuality.UNUSABLE
    assert "disabled by policy" in page.warnings[-1]
    assert extraction.route is ExtractionRoute.CLINICIAN_ONLY
    assert extraction.failure_kind is FailureKind.NONE


def test_missing_ocr_engine_is_a_transient_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.document_intelligence import pipeline
    from app.services.document_intelligence.ocr import OcrEngineUnavailableError

    def _unavailable() -> None:
        raise OcrEngineUnavailableError("no tesseract")

    monkeypatch.setattr(pipeline, "TesseractOcrEngine", _unavailable)
    extraction = _service(None, render_dpi=100).extract(
        _image_pdf(_scan_image()), mime_type="application/pdf"
    )

    assert extraction.route is ExtractionRoute.CLINICIAN_ONLY
    assert extraction.failure_kind is FailureKind.TRANSIENT
    assert "unavailable" in extraction.pages[0].warnings[-1]


def test_garbage_text_layer_over_a_scan_is_ignored_in_favour_of_ocr() -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_image(page.rect, stream=_png(_scan_image()))
    page.insert_text(
        (48, 72), "qzxwvk bkrtpl xvzqwn ptkrmz wqzxvb rtplkq zvkxwq mkptrz", fontname="helv"
    )
    data = bytes(doc.tobytes())

    extraction = _service(FakeOcrEngine(), render_dpi=100).extract(
        data, mime_type="application/pdf"
    )

    page_extraction = extraction.pages[0]
    assert page_extraction.page_class is PageClass.SCANNED_IMAGE
    assert page_extraction.text == "Metformin 500 mg"
    assert any("sanity" in warning for warning in page_extraction.warnings)


def test_mixed_page_keeps_embedded_words_and_ocrs_only_the_image_region() -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    # The header has to clear `min_text_chars` (20), or the page classifies as a plain
    # scan and the mixed-page branch under test never runs.
    page.insert_text((48, 72), "REFERRAL NOTE - CARDIOLOGY CLINIC", fontsize=12, fontname="helv")
    # Portrait, or FakeOcrEngine treats the region as sideways and returns its "xq"
    # low-confidence sentinel instead of the scripted words.
    page.insert_image(pymupdf.Rect(48, 300, 564, 700), stream=_png(_scan_image(800, 1032)))
    data = bytes(doc.tobytes())
    engine = FakeOcrEngine(("Furosemide", "40", "mg"))

    extraction = _service(engine, render_dpi=100).extract(data, mime_type="application/pdf")

    page_extraction = extraction.pages[0]
    assert extraction.document_class is DocumentClass.MIXED
    assert page_extraction.page_class is PageClass.MIXED
    assert page_extraction.text.splitlines() == [
        "REFERRAL NOTE - CARDIOLOGY CLINIC",
        "Furosemide 40 mg",
    ]
    assert page_extraction.rotation_applied == 0
    ocr_word = page_extraction.words[-1]
    assert ocr_word.method is ExtractionMethod.OCR
    assert ocr_word.bbox.y0 >= 300  # offset into page coordinates
    assert engine.calls == 1


# ── Raster uploads ───────────────────────────────────────


def test_png_upload_is_a_single_scanned_page_in_pixel_units() -> None:
    extraction = _service(FakeOcrEngine()).extract(_png(_scan_image()), mime_type="image/png")

    page = extraction.pages[0]
    assert extraction.document_class is DocumentClass.SCANNED_IMAGE
    assert page.coordinate_unit == "px"
    assert page.words[0].bbox.x0 == 40
    assert extraction.route is ExtractionRoute.AUTOMATED_CANDIDATES


def test_small_raster_is_upscaled_and_coordinates_are_mapped_back() -> None:
    small = _scan_image(400, 500)
    extraction = _service(FakeOcrEngine()).extract(_png(small), mime_type="image/png")

    page = extraction.pages[0]
    assert any("upscaled" in warning for warning in page.warnings)
    assert page.words[0].bbox.x0 == pytest.approx(40 / 3, abs=0.01)


def test_multi_frame_tiff_becomes_multiple_pages() -> None:
    first, second = _scan_image(), _scan_image()
    buffer = io.BytesIO()
    first.save(buffer, format="TIFF", save_all=True, append_images=[second])

    extraction = _service(FakeOcrEngine()).extract(buffer.getvalue(), mime_type="image/tiff")

    assert extraction.page_count == 2
    assert [page.page_number for page in extraction.pages] == [1, 2]


def test_undecodable_image_bytes_are_unreadable() -> None:
    extraction = _service(FakeOcrEngine()).extract(
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, mime_type="image/png"
    )

    assert extraction.document_class is DocumentClass.UNREADABLE
    assert extraction.route is ExtractionRoute.REJECTED


def test_blank_image_upload_is_rejected() -> None:
    extraction = _service(FakeOcrEngine()).extract(
        _png(Image.new("L", (800, 600), 255)), mime_type="image/png"
    )

    assert extraction.pages[0].page_class is PageClass.BLANK
    assert extraction.route is ExtractionRoute.REJECTED
