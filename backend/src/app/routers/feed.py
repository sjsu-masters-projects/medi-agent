"""Feed routes — aggregated daily tasks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.core.security import get_current_user
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.feed import TodayFeedResponse
from app.services.feed_service import FeedService

router = APIRouter()


def _get_service(db: Client = Depends(get_db)) -> FeedService:
    return FeedService(db)


@router.get(
    "/today",
    response_model=TodayFeedResponse,
    summary="Get today's health tasks",
    description="Aggregated medications and obligations from all providers",
)
async def get_today_feed(
    date: str | None = Query(None, description="Target date (YYYY-MM-DD), defaults to today"),
    timezone: str = Query("UTC", description="IANA timezone"),
    user: CurrentUser = Depends(get_current_user),
    service: FeedService = Depends(_get_service),
) -> Any:
    """Get today's feed for the authenticated patient."""
    # Validate user is a patient
    if user.role != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only patients can access the feed",
        )

    # Parse date if provided
    target_date = None
    if date:
        try:
            target_date = datetime.fromisoformat(date).date()
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use YYYY-MM-DD",
            ) from e

    return await service.get_today(user.id, target_date, timezone)
