"""Results, vital signs and medication actions are grounded on their own printed row."""

from __future__ import annotations

import pymupdf
import pytest

from app.models.clinical_fact import ConfidenceBand
from app.models.document_extraction import parse_model_extraction
from app.services.document_intelligence.grounding import (
    flag_meaning,
    ground_item,
    items_from_extraction_result,
    medication_action,
    range_status,
    result_interpretation,
)
from app.services.document_intelligence.pipeline import DocumentIntelligenceService

EVIDENCE = [{"page": 1, "excerpt": "row", "confidence": 0.9}]
# A synthetic report laid out like a real one: each cell is its own text span.
ROWS = [
    ("Hemoglobin A1c", "7.8", "H", "%", "4.0 - 5.6"),
    ("Sodium", "139", "", "mmol/L", "136 - 145"),
    ("Urea nitrogen (BUN)", "14", "", "mg/dL", "7 - 20"),
    ("HDL cholesterol", "44", "L", "mg/dL", ">= 50"),
    ("Potassium", "6.9", "HH", "mmol/L", "3.5 - 5.1"),
    ("Albumin/creatinine ratio", "14", "", "mg/g", "< 30"),
]
COLUMNS = (40, 260, 330, 370, 450)


def _lab_report() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((40, 60), "SYNTHETIC TEST DOCUMENT - LABORATORY REPORT", fontsize=11)
    page.insert_text((40, 80), "Collected 10/12/2026 07:45 PT", fontsize=9)
    for index, row in enumerate(ROWS):
        y = 120 + index * 16
        for x, cell in zip(COLUMNS, row, strict=True):
            if cell:
                page.insert_text((x, y), cell, fontsize=9)
    page.insert_text((40, 260), "Blood pressure 128/82 mmHg   Pulse 72 bpm", fontsize=9)
    page.insert_text((40, 280), "Metformin 500 mg twice daily - Continue", fontsize=9)
    page.insert_text((40, 296), "Glipizide 5 mg daily - STOP", fontsize=9)
    content = doc.tobytes()
    doc.close()
    return content


@pytest.fixture(scope="module")
def extraction():
    return DocumentIntelligenceService().extract(_lab_report(), mime_type="application/pdf")


def _result(**value: str) -> dict[str, object]:
    return {**value, "evidence": EVIDENCE}


def test_model_input_keeps_each_result_on_its_printed_row(extraction) -> None:
    text = extraction.text_for_model()
    assert "Hemoglobin A1c | 7.8 | H | % | 4.0 - 5.6" in text
    assert "Sodium | 139 | mmol/L | 136 - 145" in text
    # Anchoring still uses the unchanged page text.
    assert "Hemoglobin A1c\n" in extraction.pages[0].text


def test_correct_result_is_grounded_with_the_reports_own_flag_and_range(extraction) -> None:
    item = ground_item(
        extraction,
        "lab_result",
        _result(
            test_name="Hemoglobin A1c", value="7.8", unit="%", reference_range="4.0 - 5.6", flag="H"
        ),
    )
    assert item.confidence_band is ConfidenceBand.HIGH
    assert item.value["flag_meaning"] == "high"
    assert item.value["range_status"] == "above"
    assert "consistency" not in item.value
    assert {evidence.field for evidence in item.evidence} >= {"test_name", "value", "flag"}


def test_flag_from_another_row_is_dropped_not_attached(extraction) -> None:
    item = ground_item(
        extraction,
        "lab_result",
        _result(
            test_name="Sodium", value="139", unit="mmol/L", reference_range="136 - 145", flag="H"
        ),
    )
    assert item.anchored
    assert "flag" not in item.value
    assert item.value["range_status"] == "within"
    assert any("flag" in note and "not found" in note for note in item.uncertainty)


def test_value_printed_on_another_row_or_altered_is_never_a_candidate(extraction) -> None:
    borrowed = ground_item(extraction, "lab_result", _result(test_name="Potassium", value="139"))
    altered = ground_item(
        extraction, "lab_result", _result(test_name="Hemoglobin A1c", value="7.9")
    )
    assert borrowed.confidence_score == 0
    assert altered.confidence_score == 0
    assert "value" not in altered.value


def test_repeated_short_value_anchors_to_its_own_row(extraction) -> None:
    bun = ground_item(
        extraction, "lab_result", _result(test_name="Urea nitrogen (BUN)", value="14")
    )
    ratio = ground_item(
        extraction, "lab_result", _result(test_name="Albumin/creatinine ratio", value="14")
    )
    value_box = {
        name: next(e for e in item.evidence if e.field == "value").location["bbox"]["y0"]
        for name, item in (("bun", bun), ("ratio", ratio))
    }
    assert value_box["bun"] != value_box["ratio"]


def test_critical_flag_is_surfaced_for_review(extraction) -> None:
    item = ground_item(
        extraction,
        "lab_result",
        _result(test_name="Potassium", value="6.9", flag="HH", reference_range="3.5 - 5.1"),
    )
    assert item.value["flag_meaning"] == "critical"
    assert "The report marks this result as critical." in item.uncertainty


def test_flag_that_contradicts_its_range_is_never_confident(extraction) -> None:
    # The OCR error class this guards: "4.0 - 5.6" read as "40-56" drops the decimals.
    page = extraction.pages[0]
    ocr_like = extraction.model_copy(
        update={
            "pages": [
                page.model_copy(
                    update={
                        "words": [
                            word.model_copy(update={"text": "40-56"})
                            if word.text == "4.0"
                            else word
                            for word in page.words
                            if word.text not in {"-", "5.6"} or word.bbox.y0 > 130
                        ]
                    }
                )
            ]
        }
    )
    item = ground_item(
        ocr_like,
        "lab_result",
        _result(test_name="Hemoglobin A1c", value="7.8", reference_range="40-56", flag="H"),
    )
    assert "consistency" in item.value
    assert item.confidence_band is not ConfidenceBand.HIGH
    assert any("does not match" in note for note in item.uncertainty)


def test_vital_signs_need_their_value_on_the_same_line(extraction) -> None:
    pressure = ground_item(
        extraction, "vital_sign", _result(name="Blood pressure", value="128/82", unit="mmHg")
    )
    invented = ground_item(extraction, "vital_sign", _result(name="Pulse", value="88"))
    assert pressure.anchored and pressure.confidence_score > 0
    assert invented.confidence_score == 0


def test_stopped_medication_keeps_its_printed_action(extraction) -> None:
    stopped = ground_item(
        extraction,
        "medication",
        _result(name="Glipizide", dosage="5 mg", frequency="daily", status="STOP"),
    )
    continued = ground_item(
        extraction,
        "medication",
        _result(name="Metformin", dosage="500 mg", frequency="twice daily", status="Continue"),
    )
    assert stopped.value["medication_action"] == "stopped"
    assert any("must not become an active care-plan item" in note for note in stopped.uncertainty)
    assert continued.value["medication_action"] == "continued"


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("STOP", "stopped"),
        ("Discontinue", "stopped"),
        ("D/C", "stopped"),
        ("Suspender", "stopped"),
        ("Do not stop", "stopped"),  # read as a stop: the plan is held for review
        ("Hold until seen", "held"),
        ("No change", "continued"),
        ("sin cambios", "continued"),
        ("Continuar", "continued"),
        ("Increase to 1000 mg", "changed"),
        ("Cambiar a 10 mg", "changed"),
        ("New", "new"),
        ("Iniciar", "new"),
        ("Take with food", "unknown"),
        (None, None),
    ],
)
def test_medication_action_reads_english_and_spanish(printed, expected) -> None:
    assert medication_action(printed) == expected


@pytest.mark.parametrize(
    ("flag", "meaning"),
    [
        ("H", "high"),
        ("Alto", "high"),
        ("L", "low"),
        ("bajo", "low"),
        ("HH", "critical"),
        ("CRITICAL", "critical"),
        ("A", "abnormal"),
        ("(H)", "high"),
        ("Q", "unrecognized"),
        ("+", "unrecognized"),
        (None, None),
    ],
)
def test_printed_flags(flag, meaning) -> None:
    assert flag_meaning(flag) == meaning


@pytest.mark.parametrize(
    ("value", "reference", "status"),
    [
        ("7.8", "4.0 - 5.6", "above"),
        ("44", ">= 50", "below"),
        ("14", "< 30", "within"),
        ("98", ">= 60", "within"),
        ("3,2", "3,5 - 5,1", "below"),
        ("146", "70 a 99", "above"),
        ("<5", "< 10", None),
        ("trace", "negative", None),
        ("12", "10 - 5", None),
    ],
)
def test_range_status_only_for_plain_numbers(value, reference, status) -> None:
    assert range_status(value, reference) == status


def test_missing_flag_on_an_out_of_range_value_is_noted() -> None:
    derived = result_interpretation({"value": "212", "reference_range": "< 200"})
    assert derived["range_status"] == "above"
    assert "no flag was read" in derived["consistency"]


def test_malformed_items_are_dropped_one_by_one() -> None:
    result, dropped = parse_model_extraction(
        {
            "document": {"document_type": "lab_report"},
            "lab_results": [
                {"test_name": "Sodium", "value": 139, "evidence": EVIDENCE},
                {"test_name": "Potassium", "value": "4.3"},  # no evidence
            ],
            "medications": "not a list",
            "immunizations": [{"vaccine": "Influenza", "evidence": EVIDENCE}],
        }
    )
    assert dropped == 2
    assert [item.value for item in result.lab_results] == ["139"]
    assert result.document.document_type == "lab_report"
    types = [fact_type for fact_type, _ in items_from_extraction_result(result)]
    assert types == ["lab_result", "immunization"]


def test_unknown_document_type_is_not_recorded() -> None:
    result, _ = parse_model_extraction({"document": {"document_type": "x-ray film"}})
    assert result.document.document_type is None
    with pytest.raises(ValueError):
        parse_model_extraction(["not", "an", "object"])
