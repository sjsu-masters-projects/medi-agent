"""Medication routes — CRUD for patient medications."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from supabase import Client

from app.core.security import get_current_user
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.medication import MedicationCreate, MedicationRead, MedicationUpdate
from app.services.medication_service import MedicationService

router = APIRouter()


def _get_service(db: Client = Depends(get_db)) -> MedicationService:
    return MedicationService(db)


@router.get(
    "/",
    response_model=list[MedicationRead],
    summary="List my medications",
)
async def list_medications(
    active_only: bool = True,
    user: CurrentUser = Depends(get_current_user),
    service: MedicationService = Depends(_get_service),
) -> Any:
    return await service.list_medications(user.id, active_only)


@router.post(
    "/",
    response_model=MedicationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a medication",
)
async def create_medication(
    data: MedicationCreate,
    user: CurrentUser = Depends(get_current_user),
    service: MedicationService = Depends(_get_service),
) -> Any:
    payload = data.model_dump(exclude_unset=True)
    # Convert enums and UUIDs to strings for Supabase
    if "route" in payload:
        payload["route"] = (
            payload["route"].value if hasattr(payload["route"], "value") else payload["route"]
        )
    if "prescribed_by_care_team_id" in payload and payload["prescribed_by_care_team_id"]:
        payload["prescribed_by_care_team_id"] = str(payload["prescribed_by_care_team_id"])
    if "source_document_id" in payload and payload["source_document_id"]:
        payload["source_document_id"] = str(payload["source_document_id"])
    if "start_date" in payload and payload["start_date"]:
        payload["start_date"] = str(payload["start_date"])
    if "end_date" in payload and payload["end_date"]:
        payload["end_date"] = str(payload["end_date"])
    return await service.create_medication(user.id, payload)


@router.put(
    "/{medication_id}",
    response_model=MedicationRead,
    summary="Update a medication",
)
async def update_medication(
    medication_id: UUID,
    data: MedicationUpdate,
    user: CurrentUser = Depends(get_current_user),
    service: MedicationService = Depends(_get_service),
) -> Any:
    payload = data.model_dump(exclude_unset=True)
    if "route" in payload and payload["route"]:
        payload["route"] = (
            payload["route"].value if hasattr(payload["route"], "value") else payload["route"]
        )
    if "end_date" in payload and payload["end_date"]:
        payload["end_date"] = str(payload["end_date"])
    return await service.update_medication(medication_id, user.id, payload)
