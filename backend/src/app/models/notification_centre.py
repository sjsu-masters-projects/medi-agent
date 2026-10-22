"""Role-scoped notification presentation; reading never performs clinical actions."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

NotificationCategory = Literal[
    "messages", "documents", "care_plans", "appointments", "reminders", "follow_up", "safety"
]
NotificationLocale = Literal["en-US", "es-MX"]


class CentreItem(BaseModel):
    id: UUID
    event_type: str
    category: NotificationCategory
    title: str
    body: str
    created_at: datetime
    is_read: bool
    action_url: str | None
    action_label: str
    actionable: bool
    can_acknowledge: bool = False
    patient_name: str | None = None
    clinic_name: str | None = None
    clinic_id: UUID | None = None
    source_label: str | None = None
    state_checked_at: datetime | None = None


class CentrePage(BaseModel):
    items: list[CentreItem]
    next_cursor: str | None = None
    read_through: str | None = None


class CentreSummary(BaseModel):
    unread_count: int = Field(ge=0)
    action_item_count: int = Field(ge=0)


class CentreReadThrough(BaseModel):
    model_config = ConfigDict(extra="forbid")
    read_through: str = Field(min_length=1, max_length=65536)


class CentreReadThroughResult(BaseModel):
    """Receipts marked read now, and snapshot receipts left alone because they are no
    longer the caller's to see. Already-read receipts count as neither."""

    updated_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)


class CentreAcknowledgment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=1000)
