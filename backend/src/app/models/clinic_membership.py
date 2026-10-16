"""Clinic membership schemas: a clinician's role and status at one clinic (CLN-003)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ClinicianRole, ClinicMembershipStatus, ClinicStatus


class ClinicMembership(BaseModel):
    """One clinic a clinician belongs to, with the role they hold there."""

    clinician_id: UUID
    clinic_id: UUID
    role: ClinicianRole
    status: ClinicMembershipStatus


class ClinicMembershipRead(BaseModel):
    """A clinic the signed-in clinician can act in, for clinic pickers."""

    clinic_id: UUID
    clinic_code: str
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
