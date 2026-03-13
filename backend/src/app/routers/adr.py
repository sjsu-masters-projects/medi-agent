"""ADR / MedWatch routes."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter

from app.models import ADRAssessmentRead, ADRStatus, MedWatchDraft

router = APIRouter()


@router.get("/assessments", response_model=list[ADRAssessmentRead])
async def list_assessments(status: ADRStatus | None = None) -> Any:
    raise NotImplementedError


@router.get("/assessments/{assessment_id}", response_model=ADRAssessmentRead)
async def get_assessment(assessment_id: UUID) -> Any:
    raise NotImplementedError


@router.get("/medwatch", response_model=list[MedWatchDraft])
async def list_medwatch_drafts() -> Any:
    raise NotImplementedError


@router.put("/medwatch/{draft_id}/approve")
async def approve_medwatch(draft_id: UUID) -> Any:
    raise NotImplementedError


@router.put("/medwatch/{draft_id}/dismiss")
async def dismiss_medwatch(draft_id: UUID, reason: str) -> Any:
    raise NotImplementedError
