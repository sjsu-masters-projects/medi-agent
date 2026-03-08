"""Symptom report schemas."""

from uuid import UUID

from pydantic import BaseModel, Field


class SymptomReportCreate(BaseModel):
    """Can come from chat, voice, or manual entry."""

    symptom: str = Field(..., min_length=1, max_length=300)
    severity: int = Field(..., ge=1, le=10, description="1=mild, 10=worst")
    onset: str | None = Field(default=None, examples=["2 days ago", "since yesterday morning"])
    duration: str | None = Field(default=None, examples=["on and off", "constant"])
    related_medication_id: UUID | None = None
    body_area: str | None = Field(default=None, examples=["head", "chest", "stomach"])
    notes: str | None = None


class SymptomReportRead(BaseModel):
    id: UUID
    patient_id: UUID
    symptom: str
    severity: int
    onset: str | None = None
    duration: str | None = None
    related_medication_id: UUID | None = None
    related_medication_name: str | None = None  # denormalized for display
    body_area: str | None = None
    ai_assessment: str | None = None  # Symptom Agent output
    flagged_for_adr: bool = False  # sent to Pharmacovigilance Agent?
    notes: str | None = None
    created_at: str
