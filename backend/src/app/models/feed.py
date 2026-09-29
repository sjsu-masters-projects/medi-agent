"""Feed API schemas."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TaskProvider(BaseModel):
    """Provider information for a task."""

    id: UUID
    name: str
    specialty: str
    clinic_name: str


class CarePlanTaskProvenance(BaseModel):
    """The approved plan version that made a task patient-visible."""

    version_number: int = Field(..., ge=1)
    category: str
    effective_start_date: str | None = None
    effective_end_date: str | None = None


class FeedTask(BaseModel):
    """Single task in the feed."""

    id: str
    type: Literal["medication", "obligation"]
    target_id: UUID
    care_plan_item_id: UUID | None = None
    care_plan: CarePlanTaskProvenance | None = None
    name: str
    description: str | None = None
    frequency: str
    scheduled_time: str | None = None
    scheduled_at: str | None = None
    status: Literal["pending", "completed", "skipped", "missed"]
    completed_at: str | None = None
    requires_schedule_configuration: bool = False
    provider: TaskProvider | None = None


class FeedSummary(BaseModel):
    """Summary statistics for the feed."""

    total: int = Field(..., ge=0)
    completed: int = Field(..., ge=0)
    pending: int = Field(..., ge=0)
    skipped: int = Field(..., ge=0)
    missed: int = Field(..., ge=0)


class TodayFeedResponse(BaseModel):
    """Today's feed response."""

    date: str = Field(..., examples=["2024-01-15"])
    timezone: str = Field(default="UTC", examples=["UTC", "America/New_York"])
    tasks: list[FeedTask]
    summary: FeedSummary
