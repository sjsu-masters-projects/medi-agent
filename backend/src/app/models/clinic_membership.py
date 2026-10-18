"""Clinic membership schemas: a clinician's role and status at one clinic (CLN-003)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ClinicianRole, ClinicMembershipStatus, ClinicStatus


class ClinicTag(BaseModel):
    """The clinic of the clinician's care-team link, on a list item (CLN-003 slice C)."""

    clinic_id: UUID | None = None
    clinic_name: str | None = None


class ClinicMembership(BaseModel):
    """One clinic a clinician belongs to, with the role they hold there."""

    clinician_id: UUID
    clinic_id: UUID
    role: ClinicianRole
    status: ClinicMembershipStatus


class ClinicMembershipRead(BaseModel):
    """A clinic the signed-in clinician can act in, for clinic pickers."""

    clinic_id: UUID
    # Only an admin at the clinic receives the open join code.
    clinic_code: str | None = None
    clinic_name: str
    status: ClinicStatus
    role: ClinicianRole


class ClinicMembershipsResponse(BaseModel):
    """The signed-in clinician's active memberships and default clinic."""

    default_clinic_id: UUID | None = None
    clinics: list[ClinicMembershipRead] = Field(default_factory=list)


class JoinClinicRequest(BaseModel):
    """Add a clinic to the signed-in account with an open clinic code.

    An open code grants provider or nurse access, as signup with a code does; admin access
    comes only from an addressed invitation.
    """

    clinic_code: str = Field(..., min_length=6, max_length=20)
    role: Literal["provider", "nurse"] = "provider"


class JoinClinicResponse(BaseModel):
    """The membership after a join: newly added, or already held (unchanged)."""

    status: Literal["joined", "already_member"]
    clinic_id: UUID
    clinic_code: str
    clinic_name: str
    clinic_status: ClinicStatus
    role: ClinicianRole


class ClinicScopedRequest(BaseModel):
    """An action that belongs to one clinic; optional only for a single membership."""

    clinic_id: UUID | None = None


class SetDefaultClinicRequest(BaseModel):
    """Choose which of the caller's clinics is preselected."""

    clinic_id: UUID


class DefaultClinicResponse(BaseModel):
    default_clinic_id: UUID
    clinic_id: UUID
    role: ClinicianRole


class LeaveClinicResponse(BaseModel):
    """The membership ended; ``links_ended`` patient links at that clinic ended with it."""

    status: Literal["left"]
    clinic_id: UUID
    links_ended: int = Field(ge=0)
    default_clinic_id: UUID | None = None


class ClinicRenameRequest(BaseModel):
    """An admin edits the display name of their clinic."""

    display_name: str = Field(..., min_length=2, max_length=120)


class ClinicRenameResponse(BaseModel):
    clinic_id: UUID
    clinic_name: str
