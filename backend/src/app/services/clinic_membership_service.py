"""Clinic memberships: which clinics a clinician belongs to and in which role (CLN-003).

Until clinician sign-in carries an explicit clinic (CLN-003 slice B), a clinician has at
most one active membership, kept equal to ``clinicians.clinic_id`` and ``clinicians.role``
by migration 065. Callers that need "the" clinic use :meth:`acting_membership`, which
refuses to guess once a clinician has more than one.
"""

from __future__ import annotations

from uuid import UUID

from app.core.exceptions import ValidationError
from app.db.repositories.clinic_memberships import ClinicMembershipRepository
from app.db.supabase_execute import HasSupabaseClient
from app.models.clinic_membership import ClinicMembership


class ClinicMembershipService:
    """Read a clinician's clinic memberships."""

    def __init__(self, owner: HasSupabaseClient) -> None:
        self.repo = ClinicMembershipRepository(owner)

    async def active_memberships(self, clinician_id: UUID | str) -> list[ClinicMembership]:
        """Return the clinician's active memberships, ordered by clinic."""
        rows = await self.repo.list_active_for_clinician(str(clinician_id))
        memberships = [ClinicMembership.model_validate(row) for row in rows]
        return sorted(memberships, key=lambda membership: str(membership.clinic_id))

    async def acting_membership(self, clinician_id: UUID | str) -> ClinicMembership | None:
        """Return the one clinic the clinician acts in, or ``None`` without a clinic.

        Raises:
            ValidationError: the clinician belongs to more than one clinic, so the action
                needs an explicit clinic.
        """
        memberships = await self.active_memberships(clinician_id)
        if len(memberships) > 1:
            raise ValidationError("Choose the clinic for this action")
        return memberships[0] if memberships else None

    async def clinic_member_ids(self, clinic_id: UUID | str) -> list[str]:
        """Return the clinicians with an active membership at the clinic."""
        return await self.repo.list_active_clinician_ids(str(clinic_id))
