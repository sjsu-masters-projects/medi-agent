"""Clinic routes — clinic-code resolution and internal provisioning."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from supabase import Client

from app.core.security import require_internal_admin_token
from app.db.connection import get_db
from app.models.clinic import (
    ClinicCodeResolveRequest,
    ClinicCodeResolveResponse,
    ClinicRead,
    InternalClinicProvisionRequest,
)
from app.services.clinic_service import ClinicService

router = APIRouter()

_internal_admin_dep = require_internal_admin_token


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


@router.post(
    "/internal/provision",
    response_model=ClinicRead,
    status_code=status.HTTP_201_CREATED,
    summary="Provision clinic internally",
    description="Internal-only endpoint to provision a clinic and return its code.",
)
async def provision_clinic(
    body: InternalClinicProvisionRequest,
    _: None = Depends(_internal_admin_dep),
    service: ClinicService = Depends(_get_service),
) -> ClinicRead:
    created = await service.provision_clinic(
        clinic_name=body.clinic_name,
        type2_npi=body.type2_npi,
    )
    return ClinicRead(**created)
