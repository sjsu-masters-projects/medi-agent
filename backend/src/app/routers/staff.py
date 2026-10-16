"""Staff routes — clinic team management (list, invite, update role, remove).

All endpoints require clinician authentication. Role-modifying operations
additionally require the 'admin' clinician_role.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from supabase import Client

from app.core.security import require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.staff import (
    StaffInviteRequest,
    StaffListResponse,
    StaffMember,
    StaffUpdateRoleRequest,
)
from app.services.staff_service import StaffService

router = APIRouter()

_clinician_dep = require_role("clinician")


def _get_service(db: Client = Depends(get_db)) -> StaffService:
    return StaffService(db)


@router.get(
    "/",
    response_model=StaffListResponse,
    summary="List clinic staff",
    description=(
        "Returns the members of one clinic with the role held there: the clinic named by "
        "clinic_id (an active membership is required) or the clinician's only clinic."
    ),
)
async def list_staff(
    clinic_id: UUID | None = Query(default=None),
    user: CurrentUser = Depends(_clinician_dep),
    service: StaffService = Depends(_get_service),
) -> Any:
    result = await service.list_staff(user.id, clinic_id)
    return StaffListResponse(
        staff=[StaffMember(**s) for s in result["staff"]],
        clinic_id=result.get("clinic_id"),
        clinic_name=result["clinic_name"],
        clinic_code=result.get("clinic_code"),
    )


@router.post(
    "/invite",
    status_code=status.HTTP_201_CREATED,
    summary="Invite a clinician to the clinic",
    description="Requires admin role. Queues an addressed invitation; membership changes only on acceptance.",
)
async def invite_member(
    body: StaffInviteRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: StaffService = Depends(_get_service),
) -> Any:
    return await service.invite_member(user.id, body.email, body.role.value, body.clinic_id)


@router.put(
    "/{member_id}/role",
    summary="Update a staff member's role",
    description="Requires admin role. Cannot change your own role.",
)
async def update_role(
    member_id: UUID,
    body: StaffUpdateRoleRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: StaffService = Depends(_get_service),
) -> Any:
    return await service.update_role(user.id, member_id, body.role.value, body.clinic_id)


@router.delete(
    "/{member_id}",
    summary="Remove a staff member from the clinic",
    description="Requires admin role. Cannot remove yourself.",
)
async def remove_member(
    member_id: UUID,
    clinic_id: UUID | None = Query(default=None),
    user: CurrentUser = Depends(_clinician_dep),
    service: StaffService = Depends(_get_service),
) -> Any:
    return await service.remove_member(user.id, member_id, clinic_id)
