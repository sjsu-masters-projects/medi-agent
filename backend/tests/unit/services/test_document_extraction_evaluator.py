"""Offline synthetic document-extraction evaluation tests."""

import json
from pathlib import Path

from app.models.document_extraction import DocumentExtractionResult
from app.services.document_extraction_evaluator import evaluate_recorded_extraction

FIXTURES = Path(__file__).parents[2] / "fixtures" / "document_evaluation"


def test_evaluator_scores_grounded_gold_output() -> None:
    source = (FIXTURES / "born_digital_prescription.txt").read_text()
    expected_payload = json.loads((FIXTURES / "born_digital_expected.json").read_text())
    expected = DocumentExtractionResult.model_validate(expected_payload)

    result = evaluate_recorded_extraction(
        source_pages=[source], expected=expected, output=expected_payload, latency_ms=123
    )

    assert result.schema_valid
    assert result.candidate_precision == 1
    assert result.candidate_recall == 1
    assert result.evidence_valid_rate == 1
    assert result.latency_ms == 123


def test_evaluator_rejects_ungrounded_evidence() -> None:
    source = (FIXTURES / "born_digital_prescription.txt").read_text()
    payload = json.loads((FIXTURES / "born_digital_expected.json").read_text())
    payload["medications"][0]["evidence"][0]["excerpt"] = "Invented medication evidence"
    expected = DocumentExtractionResult.model_validate(
        json.loads((FIXTURES / "born_digital_expected.json").read_text())
    )

    result = evaluate_recorded_extraction(source_pages=[source], expected=expected, output=payload)

    assert result.schema_valid
    assert result.evidence_valid_rate < 1
