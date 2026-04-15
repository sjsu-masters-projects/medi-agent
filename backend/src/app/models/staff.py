"""Staff management request/response schemas for clinic team roles."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.models.enums import ClinicianRole


class StaffInviteRequest(BaseModel):
    """Invite a new clinician to the clinic by email."""

    email: EmailStr
    role: ClinicianRole = ClinicianRole.PROVIDER


class StaffUpdateRoleRequest(BaseModel):
    """Update a team member's role."""

    role: ClinicianRole


class StaffMember(BaseModel):
    """Read model for a clinic staff member."""

    id: UUID
    email: str
    first_name: str
    last_name: str
    role: str
    specialty: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class StaffListResponse(BaseModel):
    """List of staff in the clinic."""

    staff: list[StaffMember]
    clinic_name: str
    clinic_code: str | None = None
