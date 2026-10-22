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


class PlanOwner(BaseModel):
    """Who owns the care plan an activity came from. Parts only; portals compose the label."""

    care_plan_id: UUID
    care_team_id: UUID | None = None
    ownership_state: Literal["owned", "unowned", "unassigned_legacy"]
    specialty: str | None = None
    clinician_name: str | None = None
    clinic_id: UUID | None = None
    clinic_name: str | None = None
    # True when the prescriber is no longer on the patient's care team.
    unowned_notice: bool = False


class CareTeamFilter(BaseModel):
    """One selectable owner of today's activities. care_team_id null means "unowned"."""

    care_team_id: UUID | None = None
    ownership_state: Literal["owned", "unowned", "unassigned_legacy"]
    specialty: str | None = None
    clinician_name: str | None = None
    clinic_name: str | None = None
    count: int = Field(..., ge=0)


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
    plan_owner: PlanOwner | None = None
    # Every owner of a combined entry (identical activities of several plans); plan_owner is
    # the first. Empty for legacy activities.
    plan_owners: list[PlanOwner] = Field(default_factory=list)
    # Underlying medication/obligation ids this entry stands for; the entry's own id first.
    combined_item_ids: list[UUID] = Field(default_factory=list)
    # Language of name/description when known. Differs from the patient's language only
    # for older single-language records, which the portal labels as shown as written.
    content_locale: Literal["en-US", "es-MX"] | None = None


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
    care_team_filters: list[CareTeamFilter] = Field(default_factory=list)
    # True when the patient has no active care team and an activity has no current owner.
    contact_clinic: bool = False
