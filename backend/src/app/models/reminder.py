"""Reminder scheduling schemas."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import AdherenceTargetType

DayOfWeek = Literal[
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


class ReminderScheduleRead(BaseModel):
    """Patient-configured reminder schedule for a medication or obligation."""

    id: UUID
    patient_id: UUID
    target_type: AdherenceTargetType
    target_id: UUID
    timezone: str
    times_of_day: list[str] = Field(default_factory=list, description="24h local times")
    days_of_week: list[DayOfWeek] = Field(default_factory=list)
    is_enabled: bool = True
    created_at: str
    updated_at: str | None = None


class ReminderScheduleUpsert(BaseModel):
    """Upsert payload for a patient-owned reminder schedule."""

    timezone: str
    times_of_day: list[str] = Field(default_factory=list, min_length=1)
    days_of_week: list[DayOfWeek] = Field(default_factory=list)
    is_enabled: bool = True


class ReminderGuidanceRead(BaseModel):
    """Backend guidance derived from the regimen's human-readable frequency."""

    supports_automatic_reminders: bool
    recommended_times_per_day: int | None = None
    recommended_days_per_week: int | None = None
    guidance_text: str | None = None


class ReminderTargetRead(BaseModel):
    """Reminder-eligible regimen item shown in the patient portal."""

    target_type: AdherenceTargetType
    target_id: UUID
    name: str
    description: str | None = None
    frequency: str
    provider_name: str | None = None
    reminder_schedule: ReminderScheduleRead | None = None
    guidance: ReminderGuidanceRead
