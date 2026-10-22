"""Patient medication-confirmation contracts (MED-002).

A clinician asks one plain question about one medication discrepancy; the patient's answer is
testimony shown to the clinician as evidence. It never changes a medication, fact or plan.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ConfirmationSubject = Literal["imported", "approved"]
ConfirmationAnswer = Literal["yes", "stopped", "changed", "unsure"]
ConfirmationStatus = Literal["open", "answered", "expired"]


class MedicationConfirmationCreate(BaseModel):
    """Ask the patient about the imported version, or about a matched approved medication."""

    model_config = ConfigDict(extra="forbid")

    subject: ConfirmationSubject = "imported"
    # Required for subject="approved": the patient's approved medication being asked about.
    medication_id: UUID | None = None
    care_team_id: UUID | None = None
    # A retry of the same ask carries the same id and returns the same request.
    client_request_id: UUID | None = None

    @model_validator(mode="after")
    def _shape(self) -> MedicationConfirmationCreate:
        if self.subject == "approved" and self.medication_id is None:
            raise ValueError("an approved medication must be named")
        if self.subject == "imported" and self.medication_id is not None:
            raise ValueError("an imported question does not name a local medication")
        return self


class MedicationConfirmationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: ConfirmationAnswer
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def _changed_needs_a_note(self) -> MedicationConfirmationAnswer:
        if self.answer == "changed" and not self.note:
            raise ValueError("describe what changed")
        return self


class _ConfirmationBase(BaseModel):
    id: UUID
    fact_id: UUID
    care_team_id: UUID
    subject_kind: ConfirmationSubject
    medication_name: str
    dosage: str | None = None
    frequency: str | None = None
    status: ConfirmationStatus
    answer: ConfirmationAnswer | None = None
    answer_note: str | None = None
    created_at: datetime
    expires_at: datetime
    answered_at: datetime | None = None
    clinician_name: str | None = None
    specialty: str | None = None
    clinic_name: str | None = None
    replayed: bool = False


class MedicationConfirmationClinicianRead(_ConfirmationBase):
    """What the asking clinician sees: the patient's answer is testimony, not a record."""

    patient_id: UUID
    requested_by: UUID


class MedicationConfirmationPatientRead(_ConfirmationBase):
    """What the patient sees: the question as asked, with both-language cadence labels."""

    frequency_label_en: str | None = None
    frequency_label_es: str | None = None
