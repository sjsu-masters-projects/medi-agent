"""Patient routes — profile and care team management.

All endpoints require authentication as a patient.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from supabase import Client

from app.core.security import require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.care_team import CareTeamRead
from app.models.patient import PatientRead, PatientUpdate
from app.services.patient_service import PatientService

router = APIRouter()

# All patient routes require the "patient" role
_patient_dep = require_role("patient")


def _get_service(db: Client = Depends(get_db)) -> PatientService:
    return PatientService(db)


@router.get("/me", response_model=PatientRead, summary="Get my patient profile")
async def get_my_profile(
    user: CurrentUser = Depends(_patient_dep),
    service: PatientService = Depends(_get_service),
) -> Any:
    return await service.get_profile(user.id)


@router.put("/me", response_model=PatientRead, summary="Update my patient profile")
async def update_my_profile(
    data: PatientUpdate,
    user: CurrentUser = Depends(_patient_dep),
    service: PatientService = Depends(_get_service),
) -> Any:
    return await service.update_profile(user.id, data.model_dump(exclude_unset=True))


@router.get(
    "/me/care-team",
    response_model=list[CareTeamRead],
    summary="List my clinicians",
)
async def get_my_care_team(
    user: CurrentUser = Depends(_patient_dep),
    service: PatientService = Depends(_get_service),
) -> Any:
    return await service.get_care_team(user.id)


@router.post(
    "/me/care-team/join",
    response_model=CareTeamRead,
    summary="Join a clinic via invite code",
)
async def join_clinic(
    invite_code: str,
    user: CurrentUser = Depends(_patient_dep),
    service: PatientService = Depends(_get_service),
) -> Any:
    return await service.join_care_team(user.id, invite_code)
