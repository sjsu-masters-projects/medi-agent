"""Medication schemas."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import MedicationRoute


class MedicationCreate(BaseModel):
    """From document parsing or manual entry."""

    name: str = Field(..., min_length=1, max_length=200)
    generic_name: str | None = None
    rxcui: str | None = None  # RxNorm concept ID
    dosage: str = Field(..., examples=["500mg", "10mg/5ml"])
    frequency: str = Field(..., examples=["twice daily", "every 8 hours", "as needed"])
    route: MedicationRoute = MedicationRoute.ORAL
    prescribed_by_care_team_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    instructions: str | None = Field(default=None, examples=["Take with food"])
    source_document_id: UUID | None = None  # traceability to parsed doc


class MedicationUpdate(BaseModel):
    dosage: str | None = None
    frequency: str | None = None
    route: MedicationRoute | None = None
    end_date: date | None = None
    instructions: str | None = None
    is_active: bool | None = None


class MedicationRead(BaseModel):
    id: UUID
    patient_id: UUID
    name: str
    generic_name: str | None = None
    rxcui: str | None = None
    dosage: str
    frequency: str
    route: MedicationRoute
    prescribed_by_care_team_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    instructions: str | None = None
    source_document_id: UUID | None = None
    is_active: bool = True
    created_at: str
