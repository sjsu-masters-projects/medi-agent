"""Appointment routes."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from supabase import Client

from app.core.security import get_current_user
from app.db.connection import get_db
from app.models import AppointmentCreate, AppointmentRead, AppointmentUpdate
from app.models.auth import CurrentUser
from app.services.appointment_service import AppointmentService

router = APIRouter()


@router.get("/", response_model=list[AppointmentRead])
async def list_appointments(
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_db),
) -> Any:
    return await AppointmentService(db).list_for_user(
        user_id=current_user.id,
        role=current_user.role,
    )


@router.post("/", response_model=AppointmentRead, status_code=201)
async def create_appointment(
    data: AppointmentCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_db),
) -> Any:
    return await AppointmentService(db).create_for_user(
        user_id=current_user.id,
        role=current_user.role,
        data=data.model_dump(mode="json"),
    )


@router.put("/{appointment_id}", response_model=AppointmentRead)
async def update_appointment(
    appointment_id: UUID,
    data: AppointmentUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_db),
) -> Any:
    return await AppointmentService(db).update_for_user(
        user_id=current_user.id,
        role=current_user.role,
        appointment_id=appointment_id,
        data=data.model_dump(mode="json", exclude_unset=True),
    )
