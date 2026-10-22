"""Reviewed care-handoff summary routes (CON-001)."""

from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from supabase import Client

from app.core.security import require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.handoff import (
    HandoffCreateRequest,
    HandoffDetail,
    HandoffExportRequest,
    HandoffExportResponse,
    HandoffHeader,
    HandoffSaveRequest,
    HandoffVersionRequest,
)
from app.services.care_team_access import CareTeamAccessService
from app.services.handoff_summary_service import HandoffSummaryService

router = APIRouter()
_clinician_dep = require_role("clinician")


def _service(db: Client = Depends(get_db)) -> HandoffSummaryService:
    async def authorize(clinician_id: UUID, patient_id: UUID) -> None:
        # Active link required; the denial is audited by the shared error handler.
        await asyncio.to_thread(CareTeamAccessService(db).for_patient, clinician_id, patient_id)

    return HandoffSummaryService(db, authorize)


_BASE = "/clinician/patients/{patient_id}/handoff-summaries"


@router.post(_BASE, response_model=HandoffHeader, status_code=status.HTTP_201_CREATED)
async def create_handoff_summary(
    patient_id: UUID,
    body: HandoffCreateRequest,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: HandoffSummaryService = Depends(_service),
) -> HandoffHeader:
    response.headers["Cache-Control"] = "no-store"
    header = await service.create(user.id, patient_id, body)
    if header.replayed:
        response.status_code = status.HTTP_200_OK
    return header


@router.get(_BASE, response_model=list[HandoffHeader])
async def list_handoff_summaries(
    patient_id: UUID,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: HandoffSummaryService = Depends(_service),
) -> list[HandoffHeader]:
    response.headers["Cache-Control"] = "no-store"
    return await service.list(user.id, patient_id)


@router.get(_BASE + "/{summary_id}", response_model=HandoffDetail)
async def get_handoff_summary(
    patient_id: UUID,
    summary_id: UUID,
    response: Response,
    version: int | None = None,
    user: CurrentUser = Depends(_clinician_dep),
    service: HandoffSummaryService = Depends(_service),
) -> HandoffDetail:
    response.headers["Cache-Control"] = "no-store"
    return await service.get(user.id, patient_id, summary_id, version)


@router.put(_BASE + "/{summary_id}", response_model=HandoffDetail)
async def save_handoff_summary(
    patient_id: UUID,
    summary_id: UUID,
    body: HandoffSaveRequest,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: HandoffSummaryService = Depends(_service),
) -> HandoffDetail:
    response.headers["Cache-Control"] = "no-store"
    return await service.save(user.id, patient_id, summary_id, body)


@router.post(_BASE + "/{summary_id}/approve", response_model=HandoffDetail)
async def approve_handoff_summary(
    patient_id: UUID,
    summary_id: UUID,
    body: HandoffVersionRequest,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: HandoffSummaryService = Depends(_service),
) -> HandoffDetail:
    response.headers["Cache-Control"] = "no-store"
    return await service.approve(user.id, patient_id, summary_id, body.version)


@router.post(_BASE + "/{summary_id}/export", response_model=HandoffExportResponse)
async def export_handoff_summary(
    patient_id: UUID,
    summary_id: UUID,
    body: HandoffExportRequest,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: HandoffSummaryService = Depends(_service),
) -> HandoffExportResponse:
    response.headers["Cache-Control"] = "no-store"
    return await service.export(user.id, patient_id, summary_id, body.version, body.format)
