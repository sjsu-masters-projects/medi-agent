"""Appointment routes."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter

from app.models import AppointmentCreate, AppointmentRead, AppointmentUpdate

router = APIRouter()


@router.get("/", response_model=list[AppointmentRead])
async def list_appointments() -> Any:
    raise NotImplementedError


@router.post("/", response_model=AppointmentRead, status_code=201)
async def create_appointment(data: AppointmentCreate) -> Any:
    raise NotImplementedError


@router.put("/{appointment_id}", response_model=AppointmentRead)
async def update_appointment(appointment_id: UUID, data: AppointmentUpdate) -> Any:
    raise NotImplementedError
