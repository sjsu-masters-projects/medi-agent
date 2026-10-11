"""In-app notification centre; domain actions remain in their existing routes."""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from supabase import Client

from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.notification_centre import (
    CentreAcknowledgment,
    CentrePage,
    CentreReadThrough,
    CentreReadThroughResult,
    CentreSummary,
    NotificationLocale,
)
from app.routers.care_conversations import conversation_actor
from app.services.notification_centre_service import NotificationCentreService

router = APIRouter()


async def centre_service(
    response: Response,
    actor: CurrentUser = Depends(conversation_actor),
    db: Client = Depends(get_db),
) -> NotificationCentreService:
    response.headers["Cache-Control"] = "private, no-store"
    return NotificationCentreService(db, actor)


@router.get("", response_model=CentrePage)
@router.get("/", response_model=CentrePage, include_in_schema=False)
async def notifications(
    locale: NotificationLocale = "en-US",
    unread: bool = False,
    cursor: str | None = Query(default=None, max_length=4096),
    limit: int = Query(default=50, ge=1, le=100),
    service: NotificationCentreService = Depends(centre_service),
) -> CentrePage:
    return await service.page(
        {"locale": locale, "unread": unread, "cursor": cursor, "limit": limit}
    )


@router.get("/summary", response_model=CentreSummary)
async def summary(service: NotificationCentreService = Depends(centre_service)) -> CentreSummary:
    return await service.summary()


@router.get("/action-items", response_model=CentrePage)
async def action_items(
    category: Literal["documents", "care_plans", "appointments", "follow_up", "safety"]
    | None = None,
    cursor: str | None = Query(default=None, max_length=4096),
    limit: int = Query(default=50, ge=1, le=100),
    service: NotificationCentreService = Depends(centre_service),
) -> CentrePage:
    return await service.action_items({"category": category, "cursor": cursor, "limit": limit})


@router.post("/read-through", response_model=CentreReadThroughResult)
async def read_through(
    data: CentreReadThrough,
    service: NotificationCentreService = Depends(centre_service),
) -> CentreReadThroughResult:
    return await service.read_through(data.read_through)


@router.put("/{item_id}/read")
async def mark_read(
    item_id: UUID,
    service: NotificationCentreService = Depends(centre_service),
) -> Any:
    return await service.mark_read(item_id)


@router.post("/action-items/{item_id}/acknowledge")
async def acknowledge(
    item_id: UUID,
    data: CentreAcknowledgment,
    service: NotificationCentreService = Depends(centre_service),
) -> Any:
    return await service.acknowledge(item_id, data.note)
