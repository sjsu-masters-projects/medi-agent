"""Shared clinical core and care-team-owned record routes (PLAN-002, CLN-003 slice G)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from supabase import Client

from app.core.security import require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.services.shared_clinical_core_service import SharedClinicalCoreService

router = APIRouter()
_clinician_dep = require_role("clinician")
_patient_dep = require_role("patient")


def _core(db: Client = Depends(get_db)) -> SharedClinicalCoreService:
    return SharedClinicalCoreService(db)


class ConditionSensitivityRequest(BaseModel):
    is_sensitive: bool


@router.get(
    "/clinician/patients/{patient_id}/shared-summary",
    summary="Shared clinical summary: medications, allergies, visible conditions, care teams",
)
async def get_shared_summary(
    patient_id: UUID,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: SharedClinicalCoreService = Depends(_core),
) -> Any:
    response.headers["Cache-Control"] = "no-store"
    return service.summary_for_clinician(user.id, patient_id)


@router.get(
    "/patient/conditions",
    summary="My conditions and which ones I have marked sensitive",
)
async def list_my_conditions(
    response: Response,
    user: CurrentUser = Depends(_patient_dep),
    service: SharedClinicalCoreService = Depends(_core),
) -> Any:
    response.headers["Cache-Control"] = "no-store"
    return {"conditions": service.conditions_for_patient(user.id)}


@router.put(
    "/patient/conditions/{condition_id}/sensitivity",
    summary="Mark or unmark one of my conditions as sensitive (visible only to its recording team)",
)
async def set_condition_sensitivity(
    condition_id: UUID,
    data: ConditionSensitivityRequest,
    user: CurrentUser = Depends(_patient_dep),
    service: SharedClinicalCoreService = Depends(_core),
) -> Any:
    return service.set_sensitivity(user.id, condition_id, data.is_sensitive)
