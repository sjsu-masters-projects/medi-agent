from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.core.exceptions import ValidationError
from app.models.reconciliation import ReconciliationDecision, ReconciliationDecisionRequest
from app.services.clinical_reconciliation_service import ClinicalReconciliationService


def _service() -> ClinicalReconciliationService:
    return ClinicalReconciliationService(MagicMock())


def test_medication_matching_prefers_rxnorm_then_normalized_names() -> None:
    service = _service()

    assert (
        service._match_reason(
            fact_type="medication",
            candidate={"rxcui": "860975", "name": "Metformin"},
            record={"rxcui": "860975", "name": "Different name"},
        )
        == "Exact RxNorm concept"
    )
    assert (
        service._match_reason(
            fact_type="medication",
            candidate={"name": "  metformin   hydrochloride "},
            record={"name": "Metformin hydrochloride"},
        )
        == "Normalized medication name"
    )


def test_condition_and_allergy_matching_are_conservative() -> None:
    service = _service()

    assert (
        service._match_reason(
            fact_type="condition",
            candidate={"icd10_code": "E11.9", "name": "Diabetes"},
            record={"icd10_code": "E11.9", "name": "Other"},
        )
        == "Exact ICD-10 code"
    )
    assert (
        service._match_reason(
            fact_type="allergy",
            candidate={"allergen": "Penicillin", "reaction": "rash"},
            record={"allergen": "penicillin", "reaction": "anaphylaxis"},
        )
        == "Normalized allergen; reaction differs (review conflict)"
    )


def test_candidate_fields_exclude_missing_values_and_never_map_criticality_to_severity() -> None:
    service = _service()

    candidate = service._candidate_fields(
        {
            "fact_type": "allergy",
            "value": {"allergen": "Amoxicillin", "criticality": "high"},
        }
    )

    assert candidate == {"allergen": "Amoxicillin"}


def test_evidence_only_resource_has_no_projectable_fields() -> None:
    assert _service()._candidate_fields(
        {"fact_type": "care_plan", "value": {"title": "Exercise"}}
    ) == {}


def test_reconciliation_request_requires_explicit_safe_shape() -> None:
    with pytest.raises(ValueError, match="update requires a local target"):
        ReconciliationDecisionRequest.model_validate(
            {
                "decision": ReconciliationDecision.UPDATE,
                "selected_fields": ["name"],
                "idempotency_key": "00000000-0000-0000-0000-000000000001",
            }
        )


def test_withdrawn_or_applied_candidate_cannot_be_reconciled_again() -> None:
    db = MagicMock()
    service = ClinicalReconciliationService(db)
    service._fact = MagicMock(  # type: ignore[method-assign]
        return_value={
            "id": "00000000-0000-0000-0000-000000000001",
            "fact_type": "medication",
            "review_state": "pending_review",
            "reconciliation_state": "source_withdrawn",
        }
    )
    request = ReconciliationDecisionRequest.model_validate(
        {
            "decision": "add",
            "idempotency_key": "00000000-0000-0000-0000-000000000002",
        }
    )

    with pytest.raises(ValidationError, match="immutable evidence"):
        service.decide(
            fact_id=UUID("00000000-0000-0000-0000-000000000001"),
            patient_id=UUID("00000000-0000-0000-0000-000000000003"),
            actor_id=UUID("00000000-0000-0000-0000-000000000004"),
            request=request,
        )
    db.rpc.assert_not_called()
    with pytest.raises(ValueError, match="note is required"):
        ReconciliationDecisionRequest.model_validate(
            {
                "decision": ReconciliationDecision.REJECT,
                "idempotency_key": "00000000-0000-0000-0000-000000000001",
            }
        )
