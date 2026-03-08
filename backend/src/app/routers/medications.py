"""Medication routes."""

from uuid import UUID

from fastapi import APIRouter

from app.models import MedicationCreate, MedicationRead, MedicationUpdate

router = APIRouter()


@router.get("/", response_model=list[MedicationRead])
async def list_medications(active_only: bool = True) -> list:
    raise NotImplementedError


@router.post("/", response_model=MedicationRead, status_code=201)
async def create_medication(data: MedicationCreate) -> dict:
    raise NotImplementedError


@router.put("/{medication_id}", response_model=MedicationRead)
async def update_medication(medication_id: UUID, data: MedicationUpdate) -> dict:
    raise NotImplementedError
