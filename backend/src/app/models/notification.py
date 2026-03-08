"""Notification schemas."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import NotificationType


class NotificationCreate(BaseModel):
    patient_id: UUID
    notification_type: NotificationType
    title: str = Field(..., max_length=200)
    body: str = Field(..., max_length=1000)
    action_url: str | None = None  # deep link, e.g. /chat or /records/abc


class NotificationRead(BaseModel):
    id: UUID
    patient_id: UUID
    notification_type: NotificationType
    title: str
    body: str
    action_url: str | None = None
    is_read: bool = False
    created_at: str
