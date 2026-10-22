"""Operational reads for clinic admins. No patient data."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from supabase import Client

from app.core.security import require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.services.ai_availability_service import AiAvailabilityService

router = APIRouter()
_clinician_dep = require_role("clinician")


@router.get(
    "/ai-availability",
    summary="Model availability by workload and model",
    description=(
        "Requires a clinic admin. Counts of success, timeout, 429, 5xx, circuit-open and "
        "fallback attempts with p50/p95/p99 latency over a rolling window (default 24 h, "
        "at most 336 h). Aggregated counters only: no patient data or message text."
    ),
)
async def ai_availability(
    hours: int = Query(default=24, ge=1, le=336),
    user: CurrentUser = Depends(_clinician_dep),
    db: Client = Depends(get_db),
) -> Any:
    service = AiAvailabilityService(db)
    await service.require_admin(user)
    return await service.window(hours)
