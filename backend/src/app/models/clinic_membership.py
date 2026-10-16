"""Clinic membership schema: a clinician's role and status at one clinic (CLN-003)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ClinicianRole, ClinicMembershipStatus


class ClinicMembership(BaseModel):
    """One clinic a clinician belongs to, with the role they hold there."""

    clinician_id: UUID
    clinic_id: UUID
    role: ClinicianRole
    status: ClinicMembershipStatus
