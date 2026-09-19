"""Page classification decides how a page is read before any OCR runs."""

from __future__ import annotations

import pytest

from app.services.document_intelligence.classification import (
    PageSignals,
    classify_page,
    embedded_text_sanity,
    sniff_container,
)
from app.services.document_intelligence.models import DocumentIntelligencePolicy, PageClass

POLICY = DocumentIntelligencePolicy()


@pytest.mark.parametrize(
    ("content", "mime_type", "expected"),
    [
        (b"%PDF-1.7\n...", "application/pdf", "pdf"),
        (b"\x89PNG\r\n\x1a\n....", "image/png", "image"),
        (b"\xff\xd8\xff\xe0....", "image/jpeg", "image"),
        (b"II*\x00....", "image/tiff", "image"),
        (b"MM\x00*....", "image/tiff", "image"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp", "image"),
        (b"%PDF-1.4 renamed", "image/png", "pdf"),
        (b"\x00\x01\x02garbage", "application/pdf", "corrupt"),
        (b"\x00\x01\x02garbage", "image/jpeg", "corrupt"),
        (
            b"PK\x03\x04",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            None,
        ),
        (b"hello", "text/plain", None),
    ],
)
def test_sniff_container_trusts_magic_bytes_over_declared_type(
    content: bytes, mime_type: str, expected: str | None
) -> None:
    assert sniff_container(content, mime_type) == expected


def test_embedded_text_sanity_accepts_clinical_prose_and_abbreviations() -> None:
    text = "Metoprolol succinate 50 mg PO BID; HbA1c 8.2 %; eGFR 55 mL/min; Losartán c/24 h"
    assert embedded_text_sanity(text) == 1.0


def test_embedded_text_sanity_rejects_a_garbage_ocr_layer() -> None:
    assert embedded_text_sanity("qzxwvk bkrtpl xvzqwn ptkrmz wqzxvb rtplkq zvkxwq") < 0.2


def test_embedded_text_sanity_is_neutral_for_numbers_only() -> None:
    assert embedded_text_sanity("187 8.2 1.4 55") == 1.0


def _signals(**overrides: object) -> PageSignals:
    values: dict[str, object] = {
        "text_chars": 0,
        "text_sanity": 1.0,
        "image_coverage": 0.0,
        "ink_ratio": None,
    }
    values.update(overrides)
    return PageSignals.model_validate(values)


def test_text_page_without_large_images_is_born_digital() -> None:
    page_class, warnings = classify_page(_signals(text_chars=400), POLICY)
    assert page_class is PageClass.BORN_DIGITAL_TEXT
    assert warnings == []


def test_text_page_with_a_sizable_image_is_mixed() -> None:
    page_class, _ = classify_page(_signals(text_chars=400, image_coverage=0.15), POLICY)
    assert page_class is PageClass.MIXED


def test_garbage_text_layer_falls_back_to_ocr_with_a_warning() -> None:
    page_class, warnings = classify_page(
        _signals(text_chars=400, text_sanity=0.1, image_coverage=1.0), POLICY
    )
    assert page_class is PageClass.SCANNED_IMAGE
    assert any("sanity" in warning for warning in warnings)


def test_image_only_page_is_scanned() -> None:
    page_class, _ = classify_page(_signals(image_coverage=0.98), POLICY)
    assert page_class is PageClass.SCANNED_IMAGE


def test_page_without_text_images_or_ink_is_blank() -> None:
    page_class, _ = classify_page(_signals(ink_ratio=0.0001), POLICY)
    assert page_class is PageClass.BLANK
    assert classify_page(_signals(), POLICY)[0] is PageClass.BLANK


def test_vector_drawn_page_with_ink_is_sent_to_ocr() -> None:
    page_class, warnings = classify_page(_signals(ink_ratio=0.05), POLICY)
    assert page_class is PageClass.SCANNED_IMAGE
    assert warnings
