"""Appointment schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from app.models.enums import AppointmentResponseAction, AppointmentStatus, AppointmentType


class AppointmentCreate(BaseModel):
    care_team_id: UUID
    scheduled_at: AwareDatetime
    duration_minutes: int = Field(default=30, ge=5, le=480)
    appointment_type: AppointmentType = AppointmentType.FOLLOW_UP
    location: str | None = Field(default=None, examples=["Room 302", "Telehealth"])
    reason: str | None = None
    notes: str | None = None


class AppointmentProposal(BaseModel):
    care_team_id: UUID
    slots: list[AwareDatetime] = Field(min_length=2, max_length=4)
    duration_minutes: int = Field(default=30, ge=5, le=480)
    appointment_type: AppointmentType = AppointmentType.FOLLOW_UP
    location: str | None = None
    reason: str | None = None

    @field_validator("slots")
    @classmethod
    def validate_slots(cls, slots: list[datetime]) -> list[datetime]:
        if len(set(slots)) != len(slots):
            raise ValueError("Offer distinct appointment times")
        return sorted(slots)


class AppointmentUpdate(BaseModel):
    scheduled_at: AwareDatetime | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    location: str | None = None
    reason: str | None = None
    notes: str | None = None
    status: AppointmentStatus | None = None


class AppointmentResponse(BaseModel):
    action: AppointmentResponseAction
    note: str | None = Field(default=None, max_length=1000)


class AppointmentCalendarExport(BaseModel):
    filename: str
    content: str


class AppointmentRead(BaseModel):
    id: UUID
    patient_id: UUID
    care_team_id: UUID
    clinician_name: str | None = None  # denormalized
    scheduled_at: datetime
    duration_minutes: int = 30
    appointment_type: AppointmentType
    location: str | None = None
    reason: str | None = None
    notes: str | None = None
    status: AppointmentStatus = AppointmentStatus.SCHEDULED
    patient_note: str | None = None
    proposal_group_id: UUID | None = None
    proposal_expires_at: datetime | None = None
    source_document_id: UUID | None = None  # parsed from "return in 2 weeks"
    created_at: str
