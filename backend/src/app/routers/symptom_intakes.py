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
    IntakeReply,
    IntakeStart,
)
from app.models.symptom_report_history import SymptomReportDetail, SymptomReportList
from app.services.symptom_intake_service import SymptomIntakeService
from app.services.symptom_report_history_service import SymptomReportHistoryService

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


@router.post("/symptom-intakes/{intake_id}/reply")
async def reply(
    intake_id: UUID, data: IntakeReply, service: SymptomIntakeService = Depends(intake_service)
) -> Any:
    return await service.reply(intake_id, data)


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


async def history_service(
    response: Response,
    user: CurrentUser = Depends(require_role("patient")),
    db: Client = Depends(get_db),
) -> tuple[SymptomReportHistoryService, CurrentUser]:
    response.headers["Cache-Control"] = "private, no-store"
    return SymptomReportHistoryService(db), user


@router.get("/symptom-history", response_model=SymptomReportList)
async def symptom_history(
    limit: int = Query(default=50, ge=1, le=100),
    context: tuple[SymptomReportHistoryService, CurrentUser] = Depends(history_service),
) -> Any:
    """The patient's own confirmed symptom reports, newest first."""
    service, user = context
    return await service.list_for_patient(user.id, limit)


@router.get("/symptom-history/{report_id}", response_model=SymptomReportDetail)
async def symptom_history_detail(
    report_id: UUID,
    context: tuple[SymptomReportHistoryService, CurrentUser] = Depends(history_service),
) -> Any:
    service, user = context
    return await service.detail_for_patient(user.id, report_id)
