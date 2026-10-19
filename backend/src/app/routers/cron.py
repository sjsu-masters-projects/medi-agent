"""Internal cron endpoints for Cloud Scheduler."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from supabase import Client

from app.core.security import require_cron_auth_token
from app.db.connection import get_db
from app.models.cron import CronJobRunResponse, EmailDispatchRequest, ReminderDispatchRequest
from app.services.chat_turn_queue import TurnDispatcher
from app.services.cron_service import CronService

router = APIRouter(dependencies=[Depends(require_cron_auth_token)])


def _get_service(db: Client = Depends(get_db)) -> CronService:
    return CronService(db)


@router.post(
    "/emails/dispatch",
    response_model=CronJobRunResponse,
    summary="Dispatch verified opt-in email delivery",
    description=(
        "Internal-only. Sends due queued email, reconciles provider status and records "
        "an `email_dispatch` run. A dry run only counts due work."
    ),
)
async def dispatch_emails(
    body: EmailDispatchRequest | None = None,
    service: CronService = Depends(_get_service),
) -> CronJobRunResponse:
    request = body or EmailDispatchRequest()
    return CronJobRunResponse(**await service.dispatch_emails(dry_run=request.dry_run))


@router.post(
    "/reminders/dispatch",
    response_model=CronJobRunResponse,
    summary="Dispatch due reminders",
    description=(
        "Internal-only endpoint used by Cloud Scheduler to create due reminder "
        "notifications for appointments. A real run then dispatches queued email as a "
        "separate `email_dispatch` run whose failure never fails the reminder response."
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
        await service.dispatch_emails_isolated()
    return CronJobRunResponse(**result)


@router.post(
    "/chat-turns/dispatch",
    summary="Re-enqueue queued Nora turns whose task was never created",
    description=(
        "Internal-only. The transactional-outbox sweep for CHAT_TURNS_VIA_WORKER: a bounded pass "
        "over queued turns with no accepted task, safe to repeat (tasks are named from the turn "
        "id and attempt). Intended for Cloud Scheduler about once a minute."
    ),
)
async def dispatch_chat_turns(db: Client = Depends(get_db)) -> dict[str, int]:
    return await TurnDispatcher(db).sweep()
