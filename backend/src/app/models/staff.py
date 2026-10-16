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
    # The clinic the invitation is for; optional only for an admin of a single clinic.
    clinic_id: UUID | None = None


class StaffUpdateRoleRequest(BaseModel):
    """Update a team member's role at one clinic."""

    role: ClinicianRole
    clinic_id: UUID | None = None


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
    clinic_id: UUID | None = None
    clinic_name: str
    clinic_code: str | None = None
