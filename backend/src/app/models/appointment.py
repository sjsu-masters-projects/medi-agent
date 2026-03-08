"""Appointment schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import AppointmentStatus, AppointmentType


class AppointmentCreate(BaseModel):
    care_team_id: UUID
    scheduled_at: datetime
    duration_minutes: int = Field(default=30, ge=5, le=480)
    appointment_type: AppointmentType = AppointmentType.FOLLOW_UP
    location: str | None = Field(default=None, examples=["Room 302", "Telehealth"])
    reason: str | None = None
    notes: str | None = None


class AppointmentUpdate(BaseModel):
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    location: str | None = None
    reason: str | None = None
    notes: str | None = None
    status: AppointmentStatus | None = None


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
    source_document_id: UUID | None = None  # parsed from "return in 2 weeks"
    created_at: str
