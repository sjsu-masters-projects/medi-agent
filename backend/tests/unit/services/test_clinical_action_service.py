"""Approval, assignment, and idempotency tests for the clinical action gate."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import AuthorizationError, ValidationError
from app.models.clinical_action import (
    ActionEnvelopeCreate,
    ApprovalDecisionCreate,
    ClinicalRecommendationCreate,
)
from app.services.clinical_action_service import ClinicalActionService

PATIENT = UUID("00000000-0000-0000-0000-000000000111")
PROPOSER = UUID("00000000-0000-0000-0000-000000000222")
REVIEWER = UUID("00000000-0000-0000-0000-000000000333")


class Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class Table:
    def __init__(self, name: str, store: dict[str, list[dict[str, Any]]]) -> None:
        self.name, self.store = name, store
        self.filters: list[tuple[str, str]] = []
        self.payload: dict[str, Any] | None = None
        self.single_result = False

    def select(self, *_: str) -> Table:
        return self

    def eq(self, key: str, value: Any) -> Table:
        self.filters.append((key, str(value)))
        return self

    def single(self) -> Table:
        self.single_result = True
        return self

    def insert(self, payload: dict[str, Any]) -> Table:
        self.payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> Table:
        self.payload = payload
        return self
    def execute(self) -> Result:
        rows = self.store.setdefault(self.name, [])
        matched = [row for row in rows if all(str(row.get(k)) == v for k, v in self.filters)]
        if self.payload is not None:
            if self.name == "care_teams":
                raise AssertionError("unexpected care team write")
            if self.name in {"clinical_recommendations", "action_envelopes"} and matched:
                for row in matched:
                    row.update(self.payload)
                return Result(matched)
            if self.name not in {"clinical_recommendations", "action_envelopes"} or not self.filters:
                row = {
                    "id": str(uuid4()),
                    "created_at": "2026-08-20T00:00:00Z",
                    "updated_at": "2026-08-20T00:00:00Z",
                    **self.payload,
                }
                rows.append(row)
                return Result([row])
        return Result((matched[0] if matched else None) if self.single_result else matched)


class Database:
    def __init__(self) -> None:
        self.store: dict[str, list[dict[str, Any]]] = {"care_teams": [
            {"id": "care-proposer", "clinician_id": str(PROPOSER), "patient_id": str(PATIENT), "status": "active"},
            {"id": "care-reviewer", "clinician_id": str(REVIEWER), "patient_id": str(PATIENT), "status": "active"},
        ]}
    def table(self, name: str) -> Table:
        return Table(name, self.store)


def recommendation() -> ClinicalRecommendationCreate:
    return ClinicalRecommendationCreate(patient_id=PATIENT, action_type="routine_message", proposed_payload={"body": "Check in"}, evidence=[{"source": "fact-1"}], rationale="Follow-up is due.")


def test_requires_independent_assigned_review_and_deduplicates_execution() -> None:
    db = Database()
    service = ClinicalActionService(db)  # type: ignore[arg-type]
    proposed = service.propose(recommendation(), actor_id=PROPOSER)
    recommendation_id = UUID(proposed["id"])

    with pytest.raises(AuthorizationError, match="own"):
        service.decide(recommendation_id, reviewer_id=PROPOSER, decision=ApprovalDecisionCreate(decision="approve", note="ok"))
    approved = service.decide(recommendation_id, reviewer_id=REVIEWER, decision=ApprovalDecisionCreate(decision="approve", note="Reviewed"))
    assert approved["state"] == "approved"
    key = "request-00000001"
    first = service.get_or_create_envelope(recommendation_id, clinician_id=REVIEWER, envelope=ActionEnvelopeCreate(idempotency_key=key))
    second = service.get_or_create_envelope(recommendation_id, clinician_id=REVIEWER, envelope=ActionEnvelopeCreate(idempotency_key=key))
    assert first["id"] == second["id"]


def test_unassigned_clinician_and_unapproved_execution_are_rejected() -> None:
    db = Database()
    service = ClinicalActionService(db)  # type: ignore[arg-type]
    proposed = service.propose(recommendation(), actor_id=PROPOSER)
    with pytest.raises(AuthorizationError, match="not assigned"):
        service.decide(UUID(proposed["id"]), reviewer_id=uuid4(), decision=ApprovalDecisionCreate(decision="approve", note="No access"))
    with pytest.raises(ValidationError, match="approved"):
        service.get_or_create_envelope(UUID(proposed["id"]), clinician_id=REVIEWER, envelope=ActionEnvelopeCreate(idempotency_key="request-00000002"))


def unclassified_recommendation() -> ClinicalRecommendationCreate:
    """An action type nobody has assigned a tier, which fails closed to the top tier."""
    return ClinicalRecommendationCreate(patient_id=PATIENT, action_type="adjust_anticoagulant_dose", proposed_payload={"dose": "5mg"}, evidence=[{"source": "fact-2"}], rationale="INR is out of range.")


def test_a_model_may_not_propose_an_unclassified_action() -> None:
    """No actor means no clinician originated it; review must not launder that."""
    service = ClinicalActionService(Database())  # type: ignore[arg-type]

    with pytest.raises(AuthorizationError, match="proposed by a clinician"):
        service.propose(unclassified_recommendation(), actor_id=None)


def test_a_clinician_may_propose_the_same_action() -> None:
    service = ClinicalActionService(Database())  # type: ignore[arg-type]

    proposed = service.propose(unclassified_recommendation(), actor_id=PROPOSER)

    assert proposed["state"] == "pending_approval"


def test_a_model_may_still_propose_a_classified_ordinary_action() -> None:
    """The restriction is targeted, not a blanket ban on model proposals."""
    service = ClinicalActionService(Database())  # type: ignore[arg-type]

    proposed = service.propose(recommendation(), actor_id=None)

    assert proposed["state"] == "pending_approval"


def test_the_applied_tier_is_recorded_on_the_audit_trail() -> None:
    """Which authority a decision required must survive later registry changes."""
    db = Database()
    service = ClinicalActionService(db)  # type: ignore[arg-type]

    service.propose(recommendation(), actor_id=PROPOSER)

    audits = db.store["clinical_action_audit_records"]
    assert audits[0]["event_data"]["action_tier"] == "clinician_review"


def test_a_refused_proposal_is_not_persisted() -> None:
    db = Database()
    service = ClinicalActionService(db)  # type: ignore[arg-type]

    with pytest.raises(AuthorizationError):
        service.propose(unclassified_recommendation(), actor_id=None)

    assert db.store.get("clinical_recommendations", []) == []
