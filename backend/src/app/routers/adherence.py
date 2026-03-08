"""Adherence routes."""

from fastapi import APIRouter

from app.models import AdherenceLog, AdherenceLogRead, AdherenceStats

router = APIRouter()


@router.post("/", response_model=AdherenceLogRead, status_code=201)
async def log_adherence(data: AdherenceLog) -> dict:
    raise NotImplementedError


@router.get("/stats", response_model=AdherenceStats)
async def get_adherence_stats(period_days: int = 30) -> dict:
    raise NotImplementedError
