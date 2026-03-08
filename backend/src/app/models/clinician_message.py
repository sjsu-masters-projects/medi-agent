"""Clinician → Patient message schemas (in-app + email)."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import MessageChannel


class ClinicianMessageCreate(BaseModel):
    patient_id: UUID
    channel: MessageChannel
    subject: str | None = Field(default=None, max_length=200)  # email only
    body: str = Field(..., min_length=1, max_length=5000)


class ClinicianMessageRead(BaseModel):
    id: UUID
    clinician_id: UUID
    patient_id: UUID
    channel: MessageChannel
    subject: str | None = None
    body: str
    is_read: bool = False
    created_at: str
