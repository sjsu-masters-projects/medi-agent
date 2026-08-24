"""Generic, review-gated clinical action contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ClinicalActionState(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalDecisionType(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ClinicalRecommendationCreate(BaseModel):
    patient_id: UUID
    action_type: str = Field(min_length=1, max_length=100)
    proposed_payload: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(min_length=1)
    rationale: str = Field(min_length=1, max_length=5000)
    proposer_type: str = Field(default="system", min_length=1, max_length=100)
    proposer_reference: str | None = Field(default=None, max_length=500)


class ClinicalRecommendationRead(BaseModel):
    id: UUID
    patient_id: UUID
    action_type: str
    proposed_payload: dict[str, Any]
    evidence: list[dict[str, Any]]
    rationale: str
    proposer_type: str
    proposer_reference: str | None = None
    state: ClinicalActionState
    created_at: datetime
    updated_at: datetime


class ApprovalDecisionCreate(BaseModel):
    decision: ApprovalDecisionType
    note: str = Field(min_length=1, max_length=5000)
    edited_payload: dict[str, Any] | None = None


class ActionEnvelopeCreate(BaseModel):
    idempotency_key: str = Field(min_length=16, max_length=255)


class ActionEnvelopeRead(BaseModel):
    id: UUID
    recommendation_id: UUID
    idempotency_key: str
    state: ClinicalActionState
    outcome: dict[str, Any] = Field(default_factory=dict)
    executed_by: UUID | None = None
    executed_at: datetime | None = None
    created_at: datetime


class AuditRecord(BaseModel):
    id: UUID
    recommendation_id: UUID
    actor_id: UUID | None = None
    event_type: str
    event_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
