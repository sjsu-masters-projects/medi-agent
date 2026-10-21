"""Narrow service regressions supplementing the real PostgreSQL REC contracts."""

from copy import deepcopy
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import ValidationError
from app.models.reconciliation import ReconciliationDecisionRequest
from app.services.clinical_reconciliation_service import ClinicalReconciliationService


@pytest.mark.parametrize(
    "allergen",
    [
        "NKDA",
        " NKA ",
        "No known allergies",
        "No known drug allergies",
        "Sin alergias conocidas",
        "Sin alergias medicamentosas conocidas",
        "  no   known drug ALLERGIES  ",
    ],
)
def test_exact_absence_statement_is_evidence_only_and_is_never_rewritten(allergen):
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    service = ClinicalReconciliationService(db)
    fact = {
        "id": str(uuid4()),
        "patient_id": str(uuid4()),
        "fact_type": "allergy",
        "value": {"allergen": allergen},
        "review_state": "pending_review",
        "reconciliation_state": "not_started",
    }
    saved = deepcopy(fact)
    service._fact = MagicMock(return_value=fact)
    preview = service.preview(fact_id=UUID(fact["id"]), patient_id=UUID(fact["patient_id"]))
    assert preview["projectable"] is False
    assert preview["candidate_fields"] == {}
    assert preview["available_fields"] == []
    assert preview["matches"] == []
    for request in (
        ReconciliationDecisionRequest(decision="add", idempotency_key=uuid4()),
        ReconciliationDecisionRequest(
            decision="update",
            target_id=uuid4(),
            selected_fields=["allergen"],
            idempotency_key=uuid4(),
        ),
    ):
        with pytest.raises(ValidationError, match="evidence-only"):
            service.decide(
                fact_id=UUID(fact["id"]),
                patient_id=UUID(fact["patient_id"]),
                actor_id=uuid4(),
                request=request,
            )
    assert fact == saved
    db.rpc.assert_not_called()


@pytest.mark.parametrize(
    "allergen",
    [
        "Penicillin",
        "Latex",
        "NKDA except penicillin",
        "No known allergies; rash with amoxicillin",
        "Unknown",
        "Allergies not assessed",
        "No known drug allergies to penicillin",
    ],
)
def test_mixed_unknown_or_positive_text_is_not_classified_by_substring(allergen):
    service = ClinicalReconciliationService(MagicMock())
    fact = {"fact_type": "allergy", "value": {"allergen": allergen}}
    assert service._is_projectable(fact) is True
    assert service._candidate_fields(fact) == {"allergen": allergen}


@pytest.mark.parametrize(
    "state,review",
    [
        ("applied", "approved"),
        ("kept_existing", "approved"),
        ("rejected", "rejected"),
        ("deferred", "pending_review"),
        ("source_withdrawn", "approved"),
    ],
)
def test_saved_decision_replay_precedes_terminal_state_without_repeating_rpc(state, review):
    db = MagicMock()
    service = ClinicalReconciliationService(db)
    fact_id, patient_id, actor_id, token = (uuid4() for _ in range(4))
    event = {
        "id": str(uuid4()),
        "fact_id": str(fact_id),
        "patient_id": str(patient_id),
        "actor_id": str(actor_id),
        "decision": "add",
        "note": None,
        "target_id": str(uuid4()),
        "target_type": "medication",
        "target_after": {"name": "Saved synthetic medicine"},
        "target_before": None,
    }
    query = db.table.return_value
    query.select.return_value = query
    query.eq.return_value = query
    query.execute.return_value.data = [event]
    service._fact = MagicMock(return_value={"review_state": review, "reconciliation_state": state})
    result = service.decide(
        fact_id=fact_id,
        patient_id=patient_id,
        actor_id=actor_id,
        request=ReconciliationDecisionRequest(decision="add", idempotency_key=token),
    )
    assert result["replayed"] is True
    assert result["event_id"] == event["id"]
    assert result["target_after"] == event["target_after"]
    db.rpc.assert_not_called()
    assert {call.args for call in query.eq.call_args_list} == {
        ("fact_id", str(fact_id)),
        ("patient_id", str(patient_id)),
        ("actor_id", str(actor_id)),
        ("idempotency_key", str(token)),
        ("clinician_id", str(actor_id)),
        ("status", "active"),
    }


@pytest.mark.parametrize("change", [None, "target", "selected_fields", "note", "decision"])
def test_update_replay_is_bound_to_the_saved_target_fields_and_note(change):
    db = MagicMock()
    query = db.table.return_value
    query.select.return_value = query.eq.return_value = query
    target, token = uuid4(), uuid4()
    event = {
        "id": str(uuid4()),
        "fact_id": str(uuid4()),
        "decision": "update",
        "target_id": str(target),
        "selected_fields": ["dosage"],
        "note": "Reviewed dose",
    }
    query.execute.return_value.data = [event]
    service = ClinicalReconciliationService(db)
    service._fact = MagicMock(return_value={"review_state": "approved"})
    request = ReconciliationDecisionRequest(
        decision="update",
        target_id=uuid4() if change == "target" else target,
        selected_fields=["frequency"] if change == "selected_fields" else ["dosage"],
        note="Other note" if change == "note" else " Reviewed dose ",
        idempotency_key=token,
    )
    if change == "decision":
        request = ReconciliationDecisionRequest(
            decision="reject", note="Reviewed dose", idempotency_key=token
        )
    original_request = request.model_dump(mode="json")
    original_event = deepcopy(event)
    args = {
        "fact_id": UUID(event["fact_id"]),
        "patient_id": uuid4(),
        "actor_id": uuid4(),
        "request": request,
    }
    if change:
        with pytest.raises(ValidationError, match="another reconciliation"):
            service.decide(**args)
    else:
        assert service.decide(**args)["replayed"] is True
    assert request.model_dump(mode="json") == original_request
    assert event == original_event
    db.rpc.assert_not_called()
