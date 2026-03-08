"""Care team schemas — patient ↔ clinician junction."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import CareTeamStatus


class CareTeamCreate(BaseModel):
    """Links a patient to a clinician (usually via invite code)."""

    clinician_id: UUID
    role: str = Field(..., examples=["primary_care", "cardiologist", "endocrinologist"])
    specialty_context: str | None = None
    clinic_name: str | None = None


class CareTeamRead(BaseModel):
    id: UUID
    patient_id: UUID
    clinician_id: UUID
    clinician_first_name: str
    clinician_last_name: str
    role: str
    specialty_context: str | None = None
    clinic_name: str | None = None
    status: CareTeamStatus = CareTeamStatus.ACTIVE
    created_at: str
