"""Internal cron endpoints for Cloud Scheduler."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from supabase import Client

from app.core.security import require_cron_auth_token
from app.db.connection import get_db
from app.models.cron import (
    CronJobRunResponse,
    NightlyAdrScanRequest,
    ReminderDispatchRequest,
)
from app.services.cron_service import CronService

router = APIRouter(dependencies=[Depends(require_cron_auth_token)])


def _get_service(db: Client = Depends(get_db)) -> CronService:
    return CronService(db)


@router.post(
    "/reminders/dispatch",
    response_model=CronJobRunResponse,
    summary="Dispatch due reminders",
    description=(
        "Internal-only endpoint used by Cloud Scheduler to create due reminder "
        "notifications for appointments."
    ),
)
async def dispatch_reminders(
    body: ReminderDispatchRequest | None = None,
    service: CronService = Depends(_get_service),
) -> CronJobRunResponse:
    request = body or ReminderDispatchRequest()
    result = await service.dispatch_reminders(
        dry_run=request.dry_run,
        window_minutes=request.window_minutes,
    )
    return CronJobRunResponse(**result)


@router.post(
    "/adr/nightly-scan",
    response_model=CronJobRunResponse,
    summary="Run nightly ADR scan",
    description=(
        "Internal-only endpoint used by Cloud Scheduler to flag new symptom reports "
        "for the ADR pipeline."
    ),
)
async def run_nightly_adr_scan(
    body: NightlyAdrScanRequest | None = None,
    service: CronService = Depends(_get_service),
) -> CronJobRunResponse:
    request = body or NightlyAdrScanRequest()
    result = await service.run_nightly_adr_scan(
        dry_run=request.dry_run,
        lookback_hours=request.lookback_hours,
        limit=request.limit,
    )
    return CronJobRunResponse(**result)
