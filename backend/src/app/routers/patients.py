"""Patient routes — profile and care team management.

All endpoints require authentication as a patient.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from supabase import Client

from app.core.exceptions import ValidationError
from app.core.security import require_role
from app.db.connection import get_db
from app.models.adr import (
    ADRFollowUpOverviewRead,
    ADRInformationRequestRead,
    ADRInformationResponseRead,
    ADRInformationResponseRequest,
)
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
) -> PatientRead:
    payload = await service.get_profile(user.id)
    return PatientRead.model_validate(payload)


@router.put("/me", response_model=PatientRead, summary="Update my patient profile")
async def update_my_profile(
    data: PatientUpdate,
    user: CurrentUser = Depends(_patient_dep),
    service: PatientService = Depends(_get_service),
) -> PatientRead:
    payload = await service.update_profile(user.id, data.model_dump(exclude_unset=True))
    return PatientRead.model_validate(payload)


@router.get(
    "/me/care-team",
    response_model=list[CareTeamRead],
    summary="List my clinicians",
)
async def get_my_care_team(
    user: CurrentUser = Depends(_patient_dep),
    service: PatientService = Depends(_get_service),
) -> list[CareTeamRead]:
    payload = await service.get_care_team(user.id)
    return [CareTeamRead.model_validate(item) for item in payload]


@router.post(
    "/me/care-team/join",
    response_model=CareTeamRead,
    summary="Join a clinic via invite code",
)
async def join_clinic(
    invite_code: str,
    user: CurrentUser = Depends(_patient_dep),
    service: PatientService = Depends(_get_service),
) -> CareTeamRead:
    payload = await service.join_care_team(user.id, invite_code)
    return CareTeamRead.model_validate(payload)


@router.get(
    "/me/adr-information-requests",
    response_model=list[ADRInformationRequestRead],
    summary="List my pending ADR follow-up questions",
    description=(
        "Returns only patient-answerable questions about events that already happened. "
        "It never asks the patient to change or restart a medication."
    ),
)
async def list_my_adr_information_requests(
    user: CurrentUser = Depends(_patient_dep),
    service: PatientService = Depends(_get_service),
) -> list[ADRInformationRequestRead]:
    payload = await service.list_adr_information_requests(user.id)
    return [ADRInformationRequestRead.model_validate(item) for item in payload]


# Declared before any ``/{request_id}`` path so "overview" is never parsed as an ID.
@router.get(
    "/me/adr-information-requests/overview",
    response_model=ADRFollowUpOverviewRead,
    summary="Get my ADR follow-up overview",
    description=(
        "Returns the selected follow-up request (by request or assessment), every pending "
        "request, and bounded recent history. It carries no score or causality fields."
    ),
)
async def get_my_adr_follow_up_overview(
    request_id: UUID | None = None,
    assessment_id: UUID | None = None,
    user: CurrentUser = Depends(_patient_dep),
    service: PatientService = Depends(_get_service),
) -> ADRFollowUpOverviewRead:
    """Return the patient's own ADR follow-up requests.

    At most one of ``request_id`` and ``assessment_id`` may be given. A missing ID and
    another patient's ID return the same 404.
    """
    if request_id is not None and assessment_id is not None:
        raise ValidationError("Choose a request or an assessment, not both")
    payload = await service.get_adr_follow_up_overview(
        user.id, request_id=request_id, assessment_id=assessment_id
    )
    return ADRFollowUpOverviewRead.model_validate(payload)


@router.post(
    "/me/adr-information-requests/{request_id}/respond",
    response_model=ADRInformationResponseRead,
    summary="Answer a pending ADR follow-up request",
    description=(
        "Atomically stores patient-confirmed evidence, deterministically recalculates "
        "Naranjo decision support, and writes an immutable audit event."
    ),
)
async def respond_to_adr_information_request(
    request_id: UUID,
    response: ADRInformationResponseRequest,
    user: CurrentUser = Depends(_patient_dep),
    service: PatientService = Depends(_get_service),
) -> ADRInformationResponseRead:
    payload = await service.respond_to_adr_information_request(user.id, request_id, response)
    return ADRInformationResponseRead.model_validate(payload)
