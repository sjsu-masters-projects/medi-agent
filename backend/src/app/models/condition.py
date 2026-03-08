"""Condition and allergy schemas."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import AllergySeverity


class ConditionCreate(BaseModel):
    name: str = Field(..., examples=["Type 2 Diabetes", "Hypertension"])
    icd10_code: str | None = Field(default=None, examples=["E11", "I10"])
    status: str = "active"
    notes: str | None = None


class ConditionRead(BaseModel):
    id: UUID
    patient_id: UUID
    name: str
    icd10_code: str | None = None
    status: str = "active"
    notes: str | None = None
    created_at: str


class AllergyCreate(BaseModel):
    allergen: str = Field(..., examples=["Penicillin", "Peanuts"])
    reaction: str | None = Field(default=None, examples=["Rash", "Anaphylaxis"])
    severity: AllergySeverity = AllergySeverity.MODERATE


class AllergyRead(BaseModel):
    id: UUID
    patient_id: UUID
    allergen: str
    reaction: str | None = None
    severity: AllergySeverity = AllergySeverity.MODERATE
    created_at: str
