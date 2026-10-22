"""Care-plan routes.  Drafting is automatic; clinicians own review and publication."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from supabase import Client

from app.core.security import get_current_user, require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.care_plan import (
    AdoptPlanRequest,
    CarePlanApprovalRequest,
    CarePlanDraftUpdate,
    CarePlanTodayPreviewRead,
    CarePlanTranslationRequest,
    CareTeamPlanScopeRead,
    CrossPlanResolutionRequest,
    ResolveConflictReplyRequest,
    RetireItemsRequest,
    ReviewItemReplyRequest,
    TakeRecordRequest,
)
from app.services.care_plan_preview_service import CarePlanPreviewService
from app.services.care_plan_review_service import CarePlanReviewService
from app.services.care_plan_service import CarePlanService
from app.services.care_team_plan_scope import CareTeamPlanScopeService

router = APIRouter()
_clinician_dep = require_role("clinician")


def _service(db: Client = Depends(get_db)) -> CarePlanService:
    return CarePlanService(db)


def _preview_service(db: Client = Depends(get_db)) -> CarePlanPreviewService:
    return CarePlanPreviewService(db)


def _review_service(db: Client = Depends(get_db)) -> CarePlanReviewService:
    return CarePlanReviewService(db)


def _scope_service(db: Client = Depends(get_db)) -> CareTeamPlanScopeService:
    return CareTeamPlanScopeService(db)


@router.get(
    "/clinician/patients/{patient_id}/care-team-options",
    response_model=list[CareTeamPlanScopeRead],
    summary="List the acting clinician's exact active care-team plan scopes",
)
async def get_care_team_plan_options(
    patient_id: UUID,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: CareTeamPlanScopeService = Depends(_scope_service),
) -> Any:
    response.headers["Cache-Control"] = "no-store"
    return service.list_for_clinician(user.id, patient_id)


@router.get(
    "/clinician/patients/{patient_id}/{plan_id}/today-preview",
    summary="Preview the saved proposal in today's patient feed without publishing",
    response_model=CarePlanTodayPreviewRead,
)
async def preview_care_plan_today(
    patient_id: UUID,
    plan_id: UUID,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanPreviewService = Depends(_preview_service),
) -> Any:
    response.headers["Cache-Control"] = "no-store"
    return await service.preview(user.id, patient_id, plan_id)


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
    care_team_id: UUID | None = None,
    care_plan_id: UUID | None = None,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanService = Depends(_service),
) -> Any:
    return service.get_for_clinician(
        user.id, patient_id, care_team_id=care_team_id, care_plan_id=care_plan_id
    )


@router.get(
    "/clinician/patients/{patient_id}/review-context",
    summary="Compare the latest draft with the current approved care plan",
)
async def get_care_plan_review_context(
    patient_id: UUID,
    care_team_id: UUID | None = None,
    care_plan_id: UUID | None = None,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanService = Depends(_service),
) -> Any:
    return service.get_review_context_for_clinician(
        user.id, patient_id, care_team_id=care_team_id, care_plan_id=care_plan_id
    )


@router.get(
    "/clinician/patients/{patient_id}/generation",
    summary="Get automatic care-plan draft generation state",
)
async def get_care_plan_generation(
    patient_id: UUID,
    care_team_id: UUID | None = None,
    care_plan_id: UUID | None = None,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanService = Depends(_service),
) -> Any:
    return service.generation_for_clinician(
        user.id, patient_id, care_team_id=care_team_id, care_plan_id=care_plan_id
    )


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
    "/clinician/patients/{patient_id}/{plan_id}/items/{item_id}/translate",
    summary="Redraft the other language of one draft item for clinician review",
)
async def translate_care_plan_item(
    patient_id: UUID,
    plan_id: UUID,
    item_id: UUID,
    data: CarePlanTranslationRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanService = Depends(_service),
) -> Any:
    return await service.retranslate_item(user.id, patient_id, plan_id, item_id, data.from_locale)


@router.get(
    "/clinician/patients/{patient_id}/{plan_id}/items/{item_id}/back-translate",
    summary="LOC-003: Back-translate Spanish wording to English for clinician verification",
)
async def back_translate_care_plan_item(
    patient_id: UUID,
    plan_id: UUID,
    item_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanService = Depends(_service),
) -> Any:
    return await service.back_translate_item(user.id, patient_id, plan_id, item_id)


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
    return service.approve(
        user.id,
        patient_id,
        plan_id,
        data.note,
        idempotency_key=data.idempotency_key,
        excluded_item_ids=data.excluded_item_ids,
    )


@router.post(
    "/clinician/patients/{patient_id}/retry-generation",
    summary="Retry a failed automatic care-plan draft",
)
async def retry_care_plan_generation(
    patient_id: UUID,
    care_team_id: UUID | None = None,
    care_plan_id: UUID | None = None,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanService = Depends(_service),
) -> dict[str, str]:
    service.retry_failed_generation(
        user.id, patient_id, care_team_id=care_team_id, care_plan_id=care_plan_id
    )
    return {"status": "pending"}


@router.get(
    "/clinician/patients/{patient_id}/plans",
    summary="Every care plan of the patient, as much of each as this clinician may know",
)
async def list_patient_care_plans(
    patient_id: UUID,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanService = Depends(_service),
) -> Any:
    response.headers["Cache-Control"] = "no-store"
    return {"plans": service.plans_for_clinician(user.id, patient_id)}


@router.get(
    "/clinician/patients/{patient_id}/{plan_id}/cross-plan-review",
    summary="Conflicts between this draft and the patient's other plans",
)
async def get_cross_plan_review(
    patient_id: UUID,
    plan_id: UUID,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanService = Depends(_service),
) -> Any:
    response.headers["Cache-Control"] = "no-store"
    return service.cross_plan_review(user.id, patient_id, plan_id)


@router.post(
    "/clinician/patients/{patient_id}/{plan_id}/conflicts/{fingerprint}/resolution",
    summary="Keep both with a written reason, or ask the other care team",
)
async def resolve_cross_plan_conflict(
    patient_id: UUID,
    plan_id: UUID,
    fingerprint: str,
    data: CrossPlanResolutionRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanService = Depends(_service),
) -> Any:
    return service.record_conflict_resolution(
        user.id,
        patient_id,
        plan_id,
        fingerprint=fingerprint,
        resolution=data.resolution,
        reason=data.reason,
    )


@router.get(
    "/clinician/review-items",
    summary="Review items for my care teams (and, without patient detail, clinics I administer)",
)
async def list_review_items(
    status: str = "open",
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanReviewService = Depends(_review_service),
) -> Any:
    if status not in {"open", "resolved", "withdrawn"}:
        status = "open"
    return service.list_for_clinician(user.id, status=status)


@router.post(
    "/clinician/review-items/{item_id}/reply",
    summary="Answer a review item addressed to my care team",
)
async def reply_to_review_item(
    item_id: UUID,
    data: ReviewItemReplyRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanReviewService = Depends(_review_service),
) -> Any:
    return service.reply(user.id, item_id, data.note)


@router.get(
    "/clinician/patients/{patient_id}/plans/{care_plan_id}/activities",
    summary="The approved activities of an unowned plan, to adopt or retire",
)
async def get_unowned_plan_activities(
    patient_id: UUID,
    care_plan_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanService = Depends(_service),
) -> Any:
    return service.unowned_activities(user.id, patient_id, care_plan_id)


@router.post(
    "/clinician/plans/{care_plan_id}/adopt",
    summary="Adopt an unowned plan: its activities become this care team's",
)
async def adopt_care_plan(
    care_plan_id: UUID,
    data: AdoptPlanRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanReviewService = Depends(_review_service),
) -> Any:
    return service.adopt(user.id, care_plan_id, care_team_id=data.care_team_id, note=data.note)


@router.post(
    "/clinician/records/{record}/{record_id}/take",
    summary="Take up a reviewed ADR assessment or MedWatch draft that has no care team",
)
async def take_unowned_record(
    record: Literal["adr_assessment", "medwatch_draft"],
    record_id: UUID,
    data: TakeRecordRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanReviewService = Depends(_review_service),
) -> Any:
    return service.take_record(user.id, record, record_id, care_team_id=data.care_team_id)


@router.post(
    "/clinician/plans/{care_plan_id}/retire-items",
    summary="Retire specific activities of an unowned plan, with a reason",
)
async def retire_care_plan_items(
    care_plan_id: UUID,
    data: RetireItemsRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanReviewService = Depends(_review_service),
) -> Any:
    return service.retire_items(
        user.id,
        care_plan_id,
        care_team_id=data.care_team_id,
        item_ids=data.item_ids,
        reason=data.reason,
    )


@router.post(
    "/clinician/review-items/{item_id}/resolve",
    summary="Resolve the other care team's reply to my conflict question",
)
async def resolve_conflict_reply(
    item_id: UUID,
    data: ResolveConflictReplyRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: CarePlanReviewService = Depends(_review_service),
) -> Any:
    return service.resolve_conflict_reply(user.id, item_id, data.action, data.reason)
