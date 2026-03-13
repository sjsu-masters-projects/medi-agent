"""Adherence routes — log events and get stats."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from supabase import Client

from app.core.security import get_current_user
from app.db.connection import get_db
from app.models.adherence import AdherenceLog, AdherenceLogRead, AdherenceStats
from app.models.auth import CurrentUser
from app.services.adherence_service import AdherenceService

router = APIRouter()


def _get_service(db: Client = Depends(get_db)) -> AdherenceService:
    return AdherenceService(db)


@router.post(
    "/",
    response_model=AdherenceLogRead,
    status_code=status.HTTP_201_CREATED,
    summary="Log a medication taken or obligation completed",
)
async def log_adherence(
    data: AdherenceLog,
    user: CurrentUser = Depends(get_current_user),
    service: AdherenceService = Depends(_get_service),
) -> Any:
    payload = data.model_dump(exclude_unset=True)
    # Serialize enums and UUIDs for Supabase
    if "target_type" in payload:
        payload["target_type"] = (
            payload["target_type"].value
            if hasattr(payload["target_type"], "value")
            else payload["target_type"]
        )
    if "status" in payload:
        payload["status"] = (
            payload["status"].value if hasattr(payload["status"], "value") else payload["status"]
        )
    if "target_id" in payload:
        payload["target_id"] = str(payload["target_id"])
    return await service.log_adherence(user.id, payload)


@router.get(
    "/stats",
    response_model=AdherenceStats,
    summary="Get adherence score and streak",
    description="Calculates overall, medication, and obligation scores over a time window.",
)
async def get_adherence_stats(
    period_days: int = 30,
    user: CurrentUser = Depends(get_current_user),
    service: AdherenceService = Depends(_get_service),
) -> Any:
    return await service.get_stats(user.id, period_days)
