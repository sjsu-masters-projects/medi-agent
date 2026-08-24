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
