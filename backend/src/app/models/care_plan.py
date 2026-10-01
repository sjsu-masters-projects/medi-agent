"""Contracts for the clinician-approved care-plan lifecycle."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class CarePlanStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    GENERATION_FAILED = "generation_failed"


class CarePlanCategory(StrEnum):
    MEDICATION = "medication"
    MOVEMENT = "movement"
    NUTRITION = "nutrition"
    HYDRATION = "hydration"
    MONITORING = "monitoring"
    FOLLOW_UP = "follow_up"
    OTHER = "other"


class CarePlanDraftSelection(BaseModel):
    """A model-selected category for one already-grounded source fact.

    The model may classify a supplied fact, but it cannot author patient-facing
    content. The service copies wording only from the evidence-backed fact.
    """

    source_fact_id: UUID
    category: CarePlanCategory


class CarePlanDraftProposal(BaseModel):
    items: list[CarePlanDraftSelection] = Field(min_length=1, max_length=100)


class CarePlanItemUpdate(BaseModel):
    id: UUID
    title: str = Field(min_length=1, max_length=300)
    instructions: str = Field(min_length=1, max_length=2000)
    frequency: str = Field(min_length=1, max_length=200)
    schedule: dict[str, Any] = Field(default_factory=dict)
    medication: dict[str, Any] = Field(default_factory=dict)
    is_removed: bool = False
    clinician_confirmed: bool = False
    language_verified: bool = False
    verified_locale: Literal["en-US", "es-MX"] | None = None


class CarePlanDraftUpdate(BaseModel):
    items: list[CarePlanItemUpdate] = Field(min_length=1, max_length=100)


class CarePlanApprovalRequest(BaseModel):
    note: str = Field(min_length=1, max_length=5000)


class CarePlanItemRead(BaseModel):
    id: UUID
    source_fact_id: UUID | None = None
    category: CarePlanCategory
    title: str
    instructions: str
    frequency: str
    schedule: dict[str, Any] = Field(default_factory=dict)
    medication: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float | None = None
    uncertainty: list[str] = Field(default_factory=list)
    conflict: dict[str, Any] = Field(default_factory=dict)
    blocker_reason: str | None = None
    reviewed_locale: str | None = None
    is_removed: bool = False
    projection_type: str | None = None
    projection_id: UUID | None = None
    source: dict[str, Any] | None = None


class CarePlanVersionRead(BaseModel):
    id: UUID
    patient_id: UUID
    version_number: int
    status: CarePlanStatus
    source_watermark: datetime
    generated_at: datetime | None = None
    generation_error_code: str | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    items: list[CarePlanItemRead] = Field(default_factory=list)


class CarePlanGenerationRead(BaseModel):
    id: UUID
    patient_id: UUID
    source_watermark: datetime
    status: str
    attempts: int
    requested_at: datetime
    next_attempt_at: datetime | None = None
    completed_at: datetime | None = None
    failure_code: str | None = None
    plan_version_id: UUID | None = None


class PatientCarePlanRead(BaseModel):
    id: UUID
    version_number: int
    approved_at: datetime
    items: list[CarePlanItemRead]


class BarrierCode(StrEnum):
    SIDE_EFFECTS = "side_effects"
    COST = "cost"
    ACCESS = "access"
    SCHEDULE = "schedule"
    CONFUSION = "confusion"
    OTHER = "other"


class CarePlanAdherenceCreate(BaseModel):
    target_type: str = Field(pattern="^(medication|obligation)$")
    target_id: UUID
    scheduled_time: datetime | None = None
    barrier_code: BarrierCode | None = None
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def other_requires_note(self) -> CarePlanAdherenceCreate:
        if self.barrier_code is BarrierCode.OTHER and not (self.note or "").strip():
            raise ValueError("A note is required when the barrier is other")
        return self
