"""Adherence tracking schemas."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import AdherenceStatus, AdherenceTargetType


class AdherenceLog(BaseModel):
    """Single event — med taken, obligation done, or skipped."""

    target_type: AdherenceTargetType
    target_id: UUID
    status: AdherenceStatus
    scheduled_time: str | None = None
    notes: str | None = None


class AdherenceLogRead(BaseModel):
    id: UUID
    patient_id: UUID
    target_type: AdherenceTargetType
    target_id: UUID
    status: AdherenceStatus
    scheduled_time: str | None = None
    notes: str | None = None
    logged_at: str


class AdherenceStats(BaseModel):
    """Computed over `period_days` window."""

    patient_id: UUID
    overall_score: float = Field(..., ge=0.0, le=1.0, examples=[0.85])
    medication_score: float = Field(..., ge=0.0, le=1.0)
    obligation_score: float = Field(..., ge=0.0, le=1.0)
    current_streak_days: int = 0
    period_days: int = 30
    total_expected: int = 0
    total_completed: int = 0
