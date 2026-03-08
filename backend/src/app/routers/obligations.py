"""Obligation routes."""

from uuid import UUID

from fastapi import APIRouter

from app.models import ObligationCreate, ObligationRead, ObligationUpdate

router = APIRouter()


@router.get("/", response_model=list[ObligationRead])
async def list_obligations() -> list:
    raise NotImplementedError


@router.post("/", response_model=ObligationRead, status_code=201)
async def create_obligation(data: ObligationCreate) -> dict:
    raise NotImplementedError


@router.put("/{obligation_id}", response_model=ObligationRead)
async def update_obligation(obligation_id: UUID, data: ObligationUpdate) -> dict:
    raise NotImplementedError
