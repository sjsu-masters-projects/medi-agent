"""Contracts for explicit clinical-fact reconciliation decisions."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ReconciliationDecision(StrEnum):
    ADD = "add"
    UPDATE = "update"
    KEEP_EXISTING = "keep_existing"
    DEFER = "defer"
    REJECT = "reject"
    MARK_REVIEWED = "mark_reviewed"


class ReconciliationDecisionRequest(BaseModel):
    """One idempotent, clinician-authored reconciliation decision."""

    decision: ReconciliationDecision
    target_id: UUID | None = None
    selected_fields: list[str] = Field(default_factory=list, max_length=20)
    note: str | None = Field(default=None, max_length=2000)
    idempotency_key: UUID

    @model_validator(mode="after")
    def validate_decision_shape(self) -> ReconciliationDecisionRequest:
        if self.decision is ReconciliationDecision.ADD and self.target_id is not None:
            raise ValueError("add must not specify an existing target")
        if self.decision is ReconciliationDecision.UPDATE:
            if self.target_id is None:
                raise ValueError("update requires a local target")
            if not self.selected_fields:
                raise ValueError("update requires one or more selected fields")
        if self.decision in {
            ReconciliationDecision.KEEP_EXISTING,
            ReconciliationDecision.DEFER,
            ReconciliationDecision.REJECT,
            ReconciliationDecision.MARK_REVIEWED,
        } and (self.target_id is not None or self.selected_fields):
            raise ValueError("this decision does not accept a target or selected fields")
        if self.decision in {ReconciliationDecision.DEFER, ReconciliationDecision.REJECT} and not (
            self.note and self.note.strip()
        ):
            raise ValueError("a note is required for defer and reject")
        return self


class ReconciliationMatchRead(BaseModel):
    target_type: str
    target_id: UUID
    match_reason: str
    record: dict[str, Any]


class ReconciliationPreviewRead(BaseModel):
    fact_id: UUID
    fact_type: str
    projectable: bool
    candidate_fields: dict[str, Any]
    available_fields: list[str]
    matches: list[ReconciliationMatchRead] = Field(default_factory=list)


class ReconciliationDecisionRead(BaseModel):
    fact_id: UUID
    event_id: UUID
    decision: ReconciliationDecision
    target_type: str | None = None
    target_id: UUID | None = None
    target_before: dict[str, Any] | None = None
    target_after: dict[str, Any] | None = None
    replayed: bool = False
