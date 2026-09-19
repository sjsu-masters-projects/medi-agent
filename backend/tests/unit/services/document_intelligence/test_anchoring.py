"""Anchoring links an extracted value back to the page words that support it."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

from app.services.document_intelligence.anchoring import (
    anchor_on_page,
    anchor_value,
    normalize_for_match,
)
from app.services.document_intelligence.grounding import (
    DocumentEvidenceCandidateService,
    ground_item,
)
from app.services.document_intelligence.models import (
    BoundingBox,
    DocumentClass,
    DocumentExtraction,
    DocumentIntelligencePolicy,
    ExtractionMethod,
    ExtractionRoute,
    PageClass,
    PageExtraction,
    PageQuality,
    TextLine,
    WordBox,
)

POLICY = DocumentIntelligencePolicy()


def _page(
    lines: list[list[tuple[str, float]]],
    *,
    page_number: int = 1,
    quality: PageQuality = PageQuality.USABLE,
    method: ExtractionMethod = ExtractionMethod.OCR,
) -> PageExtraction:
    words: list[WordBox] = []
    text_lines: list[TextLine] = []
    for line_id, line in enumerate(lines):
        x = 10.0
        boxes = []
        for text, confidence in line:
            box = WordBox(
                text=text,
                bbox=BoundingBox(
                    x0=x, y0=20.0 * line_id, x1=x + 8.0 * len(text), y1=20.0 * line_id + 12
                ),
                confidence=confidence,
                line_id=line_id,
                method=method,
            )
            boxes.append(box)
            x += 8.0 * len(text) + 4
        words.extend(boxes)
        bbox = boxes[0].bbox
        for box in boxes[1:]:
            bbox = bbox.union(box.bbox)
        text_lines.append(
            TextLine(line_id=line_id, text=" ".join(t for t, _ in line), bbox=bbox, confidence=1.0)
        )
    return PageExtraction(
        page_number=page_number,
        page_class=PageClass.SCANNED_IMAGE,
        method=method,
        width=612,
        height=792,
        words=words,
        lines=text_lines,
        text="\n".join(line.text for line in text_lines),
        confidence=0.9,
        quality=quality,
    )


def _extraction(*pages: PageExtraction) -> DocumentExtraction:
    return DocumentExtraction(
        document_class=DocumentClass.SCANNED_IMAGE,
        mime_type="application/pdf",
        source_sha256="a" * 64,
        page_count=len(pages),
        pages=list(pages),
        route=ExtractionRoute.AUTOMATED_CANDIDATES,
        route_reason="all_pages_usable",
        extractor_version="document-intelligence/1",
    )


def test_normalization_folds_case_accents_decimal_commas_and_unit_spacing() -> None:
    assert normalize_for_match("Losartán 50MG") == "losartan 50 mg"
    assert normalize_for_match("Levotiroxina 0,1 mg") == "levotiroxina 0.1 mg"
    assert normalize_for_match("500µg q.d.") == "500 ug qd"
    assert normalize_for_match("Dr. Kim 0.5 mL") == "dr kim 0.5 ml"
    assert normalize_for_match("  c/24 h  ") == "c/24 h"


def test_exact_anchor_returns_page_region_and_quote() -> None:
    page = _page(
        [
            [("DISCHARGE", 0.99), ("MEDICATIONS", 0.99)],
            [("Lisinopril", 0.97), ("10", 0.95), ("mg", 0.96), ("once", 0.98), ("daily", 0.98)],
        ]
    )
    anchor = anchor_value(_extraction(page), "Lisinopril 10 mg", policy=POLICY)

    assert anchor is not None
    assert anchor.page_number == 1
    assert anchor.match_score == 1.0
    assert anchor.quote == "Lisinopril 10 mg once daily"
    assert anchor.matched_text == "Lisinopril 10 mg"
    assert anchor.word_confidence == 0.95
    assert anchor.line_ids == [1]
    assert anchor.bbox.x0 == page.words[2].bbox.x0
    assert anchor.bbox.x1 == page.words[4].bbox.x1
    assert anchor.method is ExtractionMethod.OCR


def test_fuzzy_anchor_tolerates_an_ocr_error_and_reports_the_score() -> None:
    page = _page([[("Metfornin", 0.62), ("500", 0.9), ("mg", 0.9)]])
    anchor = anchor_on_page(page, "Metformin 500 mg", policy=POLICY)

    assert anchor is not None
    assert 0.85 <= anchor.match_score < 1.0
    assert anchor.word_confidence == 0.62


def test_unit_glued_to_number_on_the_page_still_matches() -> None:
    page = _page([[("Atorvastatin", 0.99), ("40mg", 0.93)]])
    anchor = anchor_on_page(page, "40 mg", policy=POLICY)

    assert anchor is not None
    assert anchor.match_score == 1.0


def test_value_absent_from_every_page_is_not_anchored() -> None:
    page = _page([[("Aspirin", 0.99), ("81", 0.99), ("mg", 0.99)]])
    assert anchor_value(_extraction(page), "Warfarin 5 mg", policy=POLICY) is None


def test_unanchored_value_is_excluded_instead_of_receiving_a_placeholder_citation() -> None:
    registry = MagicMock()
    service = DocumentEvidenceCandidateService(MagicMock(), registry=registry)

    summary = service.register(
        patient_id=UUID("00000000-0000-0000-0000-000000000001"),
        actor_id=UUID("00000000-0000-0000-0000-000000000002"),
        document_id=UUID("00000000-0000-0000-0000-000000000003"),
        extraction=_extraction(_page([[("Aspirin", 0.99), ("81", 0.99), ("mg", 0.99)]])),
        items=[("medication", {"name": "Warfarin", "dosage": "5 mg"})],
    )

    assert summary.created == 0
    assert summary.unanchored == 1
    registry.create_candidate.assert_not_called()


def test_source_route_is_retained_only_when_it_is_page_anchored() -> None:
    item = ground_item(
        _extraction(
            _page([[("Nitroglycerin", 0.99), ("0.4", 0.99), ("mg", 0.99), ("sublingual", 0.99)]])
        ),
        "medication",
        {
            "name": "Nitroglycerin",
            "dosage": "0.4 mg",
            "route": "sublingual",
            "evidence": [{"page": 1, "excerpt": "Nitroglycerin 0.4 mg", "confidence": 0.9}],
        },
    )

    assert item.value["route"] == "sublingual"
    assert {evidence.field for evidence in item.evidence} == {"name", "dosage", "route"}


def test_model_only_route_is_omitted_from_the_candidate() -> None:
    item = ground_item(
        _extraction(_page([[("Nitroglycerin", 0.99), ("0.4", 0.99), ("mg", 0.99)]])),
        "medication",
        {"name": "Nitroglycerin", "dosage": "0.4 mg", "route": "sublingual"},
    )

    assert "route" not in item.value
    assert any("route was omitted" in note for note in item.uncertainty)


def test_best_page_wins_and_unusable_pages_are_ignored() -> None:
    fuzzy = _page([[("Metfornin", 0.7)]], page_number=1)
    exact_but_unusable = _page([[("Metformin", 0.99)]], page_number=2, quality=PageQuality.UNUSABLE)
    exact = _page([[("Metformin", 0.99)]], page_number=3)

    anchor = anchor_value(_extraction(fuzzy, exact_but_unusable, exact), "Metformin", policy=POLICY)

    assert anchor is not None
    assert anchor.page_number == 3
    assert anchor.match_score == 1.0
