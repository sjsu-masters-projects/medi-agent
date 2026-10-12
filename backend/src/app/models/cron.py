"""Cron job request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ReminderDispatchRequest(BaseModel):
    """Manual override inputs for the reminder dispatcher."""

    dry_run: bool = False
    window_minutes: int = Field(default=15, ge=1, le=120)


class EmailDispatchRequest(BaseModel):
    """Manual override inputs for the email dispatcher."""

    dry_run: bool = False


class CronJobRunResponse(BaseModel):
    """Standard response for internal cron job runs."""

    run_id: UUID
    job_name: str
    status: str
    dry_run: bool
    started_at: datetime
    finished_at: datetime | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
