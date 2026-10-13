"""Patient-only authoritative intake reads and explicit mutations."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from supabase import Client

from app.core.security import require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.symptom_intake import (
    IntakeAnswer,
    IntakeConfirm,
    IntakeMutation,
    IntakePreview,
    IntakeStart,
)
from app.services.symptom_intake_service import SymptomIntakeService

router = APIRouter()


async def intake_service(
    response: Response,
    user: CurrentUser = Depends(require_role("patient")),
    db: Client = Depends(get_db),
) -> SymptomIntakeService:
    response.headers["Cache-Control"] = "private, no-store"
    return SymptomIntakeService(db, user)


@router.get("/symptom-intakes/active")
async def active(
    session_id: str = Query(default="default", min_length=1, max_length=128),
    service: SymptomIntakeService = Depends(intake_service),
) -> Any:
    return await service.active(session_id)


@router.post("/symptom-intakes")
async def start(data: IntakeStart, service: SymptomIntakeService = Depends(intake_service)) -> Any:
    return await service.start(data)


@router.get("/symptom-intakes/{intake_id}")
async def read(intake_id: UUID, service: SymptomIntakeService = Depends(intake_service)) -> Any:
    return await service.read(intake_id)


@router.post("/symptom-intakes/{intake_id}/answers")
async def answer(
    intake_id: UUID, data: IntakeAnswer, service: SymptomIntakeService = Depends(intake_service)
) -> Any:
    return await service.answer(intake_id, data)


@router.post("/symptom-intakes/{intake_id}/cancel")
async def cancel(
    intake_id: UUID, data: IntakeMutation, service: SymptomIntakeService = Depends(intake_service)
) -> Any:
    return await service.cancel(intake_id, data)


@router.get("/symptom-reports/{report_id}")
async def report(report_id: UUID, service: SymptomIntakeService = Depends(intake_service)) -> Any:
    return await service.report(report_id)


@router.post("/symptom-intakes/{intake_id}/preview")
async def preview(
    intake_id: UUID, data: IntakePreview, service: SymptomIntakeService = Depends(intake_service)
) -> Any:
    return await service.preview(intake_id, data.expected_revision)


@router.post("/symptom-intakes/{intake_id}/confirm")
async def confirm(
    intake_id: UUID, data: IntakeConfirm, service: SymptomIntakeService = Depends(intake_service)
) -> Any:
    return await service.confirm(intake_id, data)
