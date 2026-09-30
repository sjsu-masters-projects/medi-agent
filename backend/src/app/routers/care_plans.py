"""Care-plan routes.  Drafting is automatic; clinicians own review and publication."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from supabase import Client

from app.core.security import get_current_user, require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.care_plan import CarePlanApprovalRequest, CarePlanDraftUpdate
from app.services.care_plan_service import CarePlanService

router = APIRouter()
_clinician_dep = require_role("clinician")


def _service(db: Client = Depends(get_db)) -> CarePlanService:
    return CarePlanService(db)


@router.get("/patients/{patient_id}", summary="Get the active approved care plan")
async def get_my_care_plan(
    patient_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    service: CarePlanService = Depends(_service),
) -> Any:
    if user.role != "patient" or user.id != patient_id:
        from app.core.exceptions import AuthorizationError

        raise AuthorizationError("You can only access your own care plan")
    return service.get_for_patient(patient_id)


@router.get(
    "/clinician/patients/{patient_id}", summary="Get a clinician care-plan draft or version"
)
async def get_clinician_care_plan(
    patient_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanService = Depends(_service),
) -> Any:
    return service.get_for_clinician(user.id, patient_id)


@router.get(
    "/clinician/patients/{patient_id}/review-context",
    summary="Compare the latest draft with the current approved care plan",
)
async def get_care_plan_review_context(
    patient_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanService = Depends(_service),
) -> Any:
    return service.get_review_context_for_clinician(user.id, patient_id)


@router.get(
    "/clinician/patients/{patient_id}/generation",
    summary="Get automatic care-plan draft generation state",
)
async def get_care_plan_generation(
    patient_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanService = Depends(_service),
) -> Any:
    return service.generation_for_clinician(user.id, patient_id)


@router.put(
    "/clinician/patients/{patient_id}/{plan_id}",
    summary="Save clinician edits to a care-plan draft",
)
async def update_care_plan_draft(
    patient_id: UUID,
    plan_id: UUID,
    data: CarePlanDraftUpdate,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanService = Depends(_service),
) -> Any:
    return service.update_draft(user.id, patient_id, plan_id, data)


@router.post(
    "/clinician/patients/{patient_id}/{plan_id}/approve",
    summary="Approve and publish the complete care plan",
)
async def approve_care_plan(
    patient_id: UUID,
    plan_id: UUID,
    data: CarePlanApprovalRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanService = Depends(_service),
) -> Any:
    return service.approve(user.id, patient_id, plan_id, data.note)


@router.post(
    "/clinician/patients/{patient_id}/retry-generation",
    summary="Retry a failed automatic care-plan draft",
)
async def retry_care_plan_generation(
    patient_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanService = Depends(_service),
) -> dict[str, str]:
    service.retry_failed_generation(user.id, patient_id)
    return {"status": "pending"}
