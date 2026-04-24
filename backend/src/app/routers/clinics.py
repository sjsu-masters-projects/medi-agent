"""Clinic routes — clinic-code resolution for auth flows."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from supabase import Client

from app.db.connection import get_db
from app.models.clinic import (
    ClinicCodeResolveRequest,
    ClinicCodeResolveResponse,
)
from app.services.clinic_service import ClinicService

router = APIRouter()


def _get_service(db: Client = Depends(get_db)) -> ClinicService:
    return ClinicService(db)


@router.post(
    "/resolve-code",
    response_model=ClinicCodeResolveResponse,
    summary="Resolve clinic code",
    description="Resolves a clinician-provided clinic code before signup/login.",
)
async def resolve_clinic_code(
    body: ClinicCodeResolveRequest,
    service: ClinicService = Depends(_get_service),
) -> ClinicCodeResolveResponse:
    result = await service.resolve_clinic_code(body.clinic_code)
    return ClinicCodeResolveResponse(**result)
