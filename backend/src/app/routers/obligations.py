"""Obligation routes — CRUD for clinician-assigned patient tasks."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from supabase import Client

from app.core.security import get_current_user
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.obligation import ObligationCreate, ObligationRead, ObligationUpdate
from app.services.obligation_service import ObligationService

router = APIRouter()


def _get_service(db: Client = Depends(get_db)) -> ObligationService:
    return ObligationService(db)


@router.get(
    "/",
    response_model=list[ObligationRead],
    summary="List my obligations",
)
async def list_obligations(
    active_only: bool = True,
    user: CurrentUser = Depends(get_current_user),
    service: ObligationService = Depends(_get_service),
) -> list:
    return await service.list_obligations(user.id, active_only)


@router.post(
    "/",
    response_model=ObligationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an obligation",
)
async def create_obligation(
    data: ObligationCreate,
    user: CurrentUser = Depends(get_current_user),
    service: ObligationService = Depends(_get_service),
) -> dict:
    payload = data.model_dump(exclude_unset=True)
    if "obligation_type" in payload:
        payload["obligation_type"] = (
            payload["obligation_type"].value
            if hasattr(payload["obligation_type"], "value")
            else payload["obligation_type"]
        )
    if "set_by_care_team_id" in payload and payload["set_by_care_team_id"]:
        payload["set_by_care_team_id"] = str(payload["set_by_care_team_id"])
    return await service.create_obligation(user.id, payload)


@router.put(
    "/{obligation_id}",
    response_model=ObligationRead,
    summary="Update an obligation",
)
async def update_obligation(
    obligation_id: UUID,
    data: ObligationUpdate,
    user: CurrentUser = Depends(get_current_user),
    service: ObligationService = Depends(_get_service),
) -> dict:
    return await service.update_obligation(
        obligation_id, user.id, data.model_dump(exclude_unset=True)
    )
