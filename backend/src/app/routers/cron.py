"""Internal cron endpoints for Cloud Scheduler."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from supabase import Client

from app.core.exceptions import ExternalServiceError
from app.core.security import require_cron_auth_token
from app.db.connection import get_db
from app.models.cron import CronJobRunResponse, ReminderDispatchRequest
from app.services.cron_service import CronService
from app.services.email_service import EmailDeliveryService

router = APIRouter(dependencies=[Depends(require_cron_auth_token)])


@router.post("/emails/dispatch", summary="Dispatch verified opt-in email delivery")
async def dispatch_emails(db: Client = Depends(get_db)) -> dict[str, int]:
    return await EmailDeliveryService(db).dispatch()


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
    if not request.dry_run:
        try:
            await EmailDeliveryService(service.db).dispatch()
        except ExternalServiceError:
            logging.getLogger(__name__).warning(
                "Queued email dispatch unavailable; retained for retry"
            )
    return CronJobRunResponse(**result)
