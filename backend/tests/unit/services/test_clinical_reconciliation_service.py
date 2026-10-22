from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.core.exceptions import ValidationError
from app.models.reconciliation import ReconciliationDecision, ReconciliationDecisionRequest
from app.services.care_team_access import PatientAccess
from app.services.clinical_reconciliation_service import ClinicalReconciliationService


def _build(db):
    """A service whose ownership gate admits the caller (ownership has its own tests)."""
    service = ClinicalReconciliationService(db)
    service.gate = MagicMock()
    service.gate.fact.return_value = PatientAccess("clinician", "patient", frozenset({"team"}))
    return service


def _service() -> ClinicalReconciliationService:
    return _build(MagicMock())


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


@pytest.mark.parametrize(
    "source,local",
    [
        ("Lisinopril 10 mg tablet", "Lisinopril"),
        ("Metformin 500 mg tablet", "Metformin 1000 mg tablet"),
    ],
)
def test_strength_text_exposes_a_possible_match_without_claiming_equivalence(source, local):
    service = _service()
    reason = service._match_reason(
        fact_type="medication", candidate={"name": source}, record={"name": local}
    )
    assert reason.startswith("Possible name match")
    assert "verify ingredient, dose and formulation" in reason


@pytest.mark.parametrize(
    "source,local",
    [
        ("Metformin 500 mg ER tablet", "Metformin"),
        ("Metformin 500 mg / Sitagliptin 50 mg tablet", "Metformin"),
        ("Lisinopril hydrochlorothiazide 10 mg tablet", "Lisinopril"),
        ("Different drug 10 mg tablet", "Lisinopril"),
        (None, None),
    ],
)
def test_name_matching_preserves_release_salts_combinations_and_missing_identity(source, local):
    assert (
        _service()._match_reason(
            fact_type="medication", candidate={"name": source}, record={"name": local}
        )
        is None
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
    assert (
        _service()._candidate_fields({"fact_type": "care_plan", "value": {"title": "Exercise"}})
        == {}
    )


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
    service = _build(db)
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


def test_add_reconciles_all_present_medication_fields_with_an_audit_key() -> None:
    """An add projects only supplied candidate values through the transaction."""
    db = MagicMock()
    db.rpc.return_value.execute.return_value.data = {
        "fact_id": "00000000-0000-0000-0000-000000000001",
        "decision": "add",
    }
    service = _build(db)
    service._fact = MagicMock(  # type: ignore[method-assign]
        return_value={
            "id": "00000000-0000-0000-0000-000000000001",
            "fact_type": "medication",
            "review_state": "pending_review",
            "reconciliation_state": "not_started",
            "value": {
                "name": "Metformin",
                "dosage": ["500 mg", "with food"],
                "frequency": "twice daily",
                "is_active": True,
            },
        }
    )
    service._require_external_binding_if_fhir = MagicMock()  # type: ignore[method-assign]
    request = ReconciliationDecisionRequest.model_validate(
        {
            "decision": "add",
            "idempotency_key": "00000000-0000-0000-0000-000000000002",
        }
    )

    result = service.decide(
        fact_id=UUID("00000000-0000-0000-0000-000000000001"),
        patient_id=UUID("00000000-0000-0000-0000-000000000003"),
        actor_id=UUID("00000000-0000-0000-0000-000000000004"),
        request=request,
    )

    assert result["decision"] == "add"
    service._require_external_binding_if_fhir.assert_called_once()
    db.rpc.assert_called_once_with(
        "apply_clinical_fact_reconciliation",
        {
            "p_fact_id": "00000000-0000-0000-0000-000000000001",
            "p_actor_id": "00000000-0000-0000-0000-000000000004",
            "p_decision": "add",
            "p_target_id": None,
            "p_patch": {
                "name": "Metformin",
                "dosage": "500 mg; with food",
                "frequency": "twice daily",
                "is_active": True,
            },
            "p_selected_fields": ["dosage", "frequency", "is_active", "name"],
            "p_note": None,
            "p_idempotency_key": "00000000-0000-0000-0000-000000000002",
        },
    )


def test_preview_exposes_candidate_fields_and_match_context() -> None:
    service = _service()
    service._fact = MagicMock(  # type: ignore[method-assign]
        return_value={
            "fact_type": "condition",
            "value": {"name": "Diabetes", "icd10_code": "E11.9"},
        }
    )
    service._matches = MagicMock(  # type: ignore[method-assign]
        return_value=[{"target_id": "local-condition", "match_reason": "Exact ICD-10 code"}]
    )

    preview = service.preview(
        clinician_id=UUID("00000000-0000-0000-0000-000000000004"),
        fact_id=UUID("00000000-0000-0000-0000-000000000001"),
        patient_id=UUID("00000000-0000-0000-0000-000000000003"),
    )

    assert preview == {
        "fact_id": "00000000-0000-0000-0000-000000000001",
        "fact_type": "condition",
        "projectable": True,
        "candidate_fields": {"name": "Diabetes", "icd10_code": "E11.9"},
        "available_fields": ["icd10_code", "name"],
        "matches": [{"target_id": "local-condition", "match_reason": "Exact ICD-10 code"}],
        "review_flags": [],
        "safety_coverage": None,
    }


def test_medication_flags_are_source_differences_not_automatic_clinical_decisions() -> None:
    service = _service()
    service.db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"allergen": "Example medicine"}
    ]
    candidate = {"name": "Example medicine", "dosage": "20 mg", "is_active": False}
    matches = [
        {"record": {"dosage": "10 mg", "is_active": True}},
        {"record": {"dosage": "10 mg", "is_active": True}},
    ]
    flags = service._medication_review_flags(
        {"patient_id": "synthetic-patient"}, candidate, matches
    )
    assert len(flags) == 4
    assert any("Multiple possible" in flag for flag in flags)
    assert any("dosage differs" in flag for flag in flags)
    assert any("active status differs" in flag for flag in flags)
    assert any("not a confirmed allergy assessment" in flag for flag in flags)
    service.db.rpc.assert_not_called()
    service.db.table.assert_called_once_with("allergies")
    service.db.table.return_value.select.return_value.eq.assert_called_once_with(
        "patient_id", "synthetic-patient"
    )


def test_unmatched_medication_never_claims_safety_or_changes_approved_list() -> None:
    service = _service()
    service.db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    flags = service._medication_review_flags(
        {"patient_id": "synthetic-patient"}, {"name": "Synthetic supplement"}, []
    )
    assert len(flags) == 1
    assert "approved list is unchanged" in flags[0]
    service.db.rpc.assert_not_called()
