"""Notification routes."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from supabase import Client

from app.core.security import require_role
from app.db.connection import get_db
from app.models import NotificationRead
from app.models.auth import CurrentUser
from app.services.notification_service import NotificationService

router = APIRouter()
_patient_dep = require_role("patient")


@router.get("/", response_model=list[NotificationRead])
async def list_notifications(
    user: CurrentUser = Depends(_patient_dep),
    db: Client = Depends(get_db),
) -> Any:
    return await NotificationService(db).list_for_patient(str(user.id))


@router.put("/{notification_id}/read")
async def mark_as_read(
    notification_id: UUID,
    user: CurrentUser = Depends(_patient_dep),
    db: Client = Depends(get_db),
) -> Any:
    return await NotificationService(db).mark_read(str(user.id), str(notification_id))
