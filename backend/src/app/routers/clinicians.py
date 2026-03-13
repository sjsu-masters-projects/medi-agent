"""Clinician routes — profile, patient list, invite codes.

All endpoints require authentication as a clinician.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from supabase import Client

from app.core.security import require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.clinician import ClinicianRead
from app.models.patient import PatientRead
from app.services.clinician_service import ClinicianService

router = APIRouter()

_clinician_dep = require_role("clinician")


def _get_service(db: Client = Depends(get_db)) -> ClinicianService:
    return ClinicianService(db)


@router.get("/me", response_model=ClinicianRead, summary="Get my clinician profile")
async def get_my_profile(
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.get_profile(user.id)


@router.get(
    "/me/patients",
    summary="List my assigned patients",
    description="Returns all patients with an active care_team relationship.",
)
async def get_my_patients(
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.get_patients(user.id)


@router.get(
    "/me/patients/{patient_id}",
    response_model=PatientRead,
    summary="Get patient detail",
    description="Only accessible if you have an active care team assignment.",
)
async def get_patient_detail(
    patient_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.get_patient_detail(user.id, patient_id)


@router.post(
    "/me/invite-code",
    summary="Generate a patient invite code",
    description="Creates a pending care_team row. Share the code with a patient.",
)
async def generate_invite_code(
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.generate_invite_code(user.id)
