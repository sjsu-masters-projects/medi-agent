"""Clinician routes."""

from uuid import UUID

from fastapi import APIRouter

from app.models import ClinicianRead

router = APIRouter()


@router.get("/me", response_model=ClinicianRead)
async def get_my_profile() -> dict:
    raise NotImplementedError


@router.get("/me/patients")
async def get_my_patients() -> list:
    raise NotImplementedError


@router.get("/me/patients/{patient_id}")
async def get_patient_detail(patient_id: UUID) -> dict:
    raise NotImplementedError


@router.post("/me/invite-code")
async def generate_invite_code() -> dict:
    raise NotImplementedError
