"""Obligation schemas."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ObligationType


class ObligationCreate(BaseModel):
    obligation_type: ObligationType
    description: str = Field(..., min_length=1, max_length=500)
    frequency: str = Field(..., examples=["daily", "3x per week", "after meals"])
    set_by_care_team_id: UUID | None = None


class ObligationUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=500)
    frequency: str | None = None
    is_active: bool | None = None


class ObligationRead(BaseModel):
    id: UUID
    patient_id: UUID
    obligation_type: ObligationType
    description: str
    frequency: str
    set_by_care_team_id: UUID | None = None
    is_active: bool = True
    created_at: str
