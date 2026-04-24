"""Patient-owned reminder schedule routes."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from supabase import Client

from app.core.security import require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.reminder import ReminderScheduleRead, ReminderScheduleUpsert, ReminderTargetRead
from app.services.reminder_schedule_service import ReminderScheduleService

router = APIRouter()

_patient_dep = require_role("patient")


def _get_service(db: Client = Depends(get_db)) -> ReminderScheduleService:
    return ReminderScheduleService(db)


@router.get(
    "/targets",
    response_model=list[ReminderTargetRead],
    summary="List reminder-eligible medications and obligations",
)
async def list_reminder_targets(
    user: CurrentUser = Depends(_patient_dep),
    service: ReminderScheduleService = Depends(_get_service),
) -> list[ReminderTargetRead]:
    payload = await service.list_targets_for_patient(str(user.id))
    return [ReminderTargetRead.model_validate(item) for item in payload]


@router.put(
    "/{target_type}/{target_id}",
    response_model=ReminderScheduleRead,
    summary="Create or update a reminder schedule",
)
async def upsert_reminder_schedule(
    target_type: Literal["medication", "obligation"],
    target_id: UUID,
    data: ReminderScheduleUpsert,
    user: CurrentUser = Depends(_patient_dep),
    service: ReminderScheduleService = Depends(_get_service),
) -> ReminderScheduleRead:
    payload = await service.upsert_schedule(
        str(user.id),
        target_type,
        str(target_id),
        data.model_dump(exclude_unset=True),
    )
    return ReminderScheduleRead.model_validate(payload)


@router.delete(
    "/{target_type}/{target_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a reminder schedule",
)
async def delete_reminder_schedule(
    target_type: Literal["medication", "obligation"],
    target_id: UUID,
    user: CurrentUser = Depends(_patient_dep),
    service: ReminderScheduleService = Depends(_get_service),
) -> Response:
    await service.delete_schedule(str(user.id), target_type, str(target_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
