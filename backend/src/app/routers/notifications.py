"""Notification routes."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter

from app.models import NotificationRead

router = APIRouter()


@router.get("/", response_model=list[NotificationRead])
async def list_notifications() -> Any:
    raise NotImplementedError


@router.put("/{notification_id}/read")
async def mark_as_read(notification_id: UUID) -> Any:
    raise NotImplementedError
