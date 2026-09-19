"""The document-extraction contract handles model wording without guessing clinical facts."""

from __future__ import annotations

from app.models.document_extraction import DocumentExtractionResult, ExtractedMedication
from app.services.document_intelligence.grounding import items_from_extraction_result


def _medication(route: str) -> ExtractedMedication:
    return ExtractedMedication.model_validate(
        {
            "name": "Metformin",
            "dosage": "500 mg",
            "frequency": "twice daily",
            "route": route,
            "evidence": [{"page": 1, "excerpt": "Metformin 500 mg", "confidence": 0.9}],
        }
    )


def test_route_preserves_source_wording_without_a_closed_vocabulary() -> None:
    for source_route in ("by mouth", "P.O.", "vía oral", "intravenous", "subcut", "sublingual"):
        assert _medication(source_route).route == source_route


def test_source_route_is_retained_in_the_candidate_payload() -> None:
    extraction = DocumentExtractionResult(medications=[_medication("by mouth")])

    fact_type, value = items_from_extraction_result(extraction)[0]

    assert fact_type == "medication"
    assert value["route"] == "by mouth"


def test_unfamiliar_source_severity_and_obligation_type_do_not_break_extraction() -> None:
    extraction = DocumentExtractionResult.model_validate(
        {
            "allergies": [
                {
                    "allergen": "Penicillin",
                    "severity": "anaphylactic",
                    "evidence": [{"page": 1, "excerpt": "Penicillin", "confidence": 0.9}],
                }
            ],
            "obligations": [
                {
                    "description": "Use the spacer with inhaler",
                    "obligation_type": "device technique",
                    "evidence": [{"page": 1, "excerpt": "Use the spacer", "confidence": 0.9}],
                }
            ],
        }
    )

    assert extraction.allergies[0].severity == "anaphylactic"
    assert extraction.obligations[0].obligation_type == "device technique"
