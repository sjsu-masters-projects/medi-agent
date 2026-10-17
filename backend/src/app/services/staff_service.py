"""Staff management service — list, invite, update roles, remove clinic team members.

Staff are the clinicians with an active membership at a clinic (CLN-003). Every action runs
in one clinic: the one the request names, or the clinician's only clinic. Rights are the role
held at that clinic, read from the membership, never ``clinicians.role``, and clinics are
compared by id, never by name. An account without an active membership is refused.
Role changes and removals run in ``clinician_clinic_operation``, which rechecks the admin's
membership under lock and writes the audit record in the same transaction.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from supabase import Client

from app.core import authorization_reasons as reasons
from app.core.exceptions import AuthorizationError, ValidationError
from app.db.repositories import ClinicianRepository, ClinicRepository
from app.services.clinic_membership_service import ClinicMembershipService
from app.services.email_invitation_service import EmailInvitationService

logger = logging.getLogger(__name__)


class StaffService:
    """Clinic staff management operations."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self.clinic_repo = ClinicRepository(self)
        self.clinician_repo = ClinicianRepository(self)
        self.memberships = ClinicMembershipService(self)

    async def _clinic_context(
        self, clinician_id: UUID, clinic_id: UUID | None, *, require_admin: bool
    ) -> dict[str, Any]:
        """The clinic a staff action runs in, from the clinician's membership there.

        Raises:
            AuthorizationError: no active membership (``ADMIN_SCOPE_ONLY``), the named clinic is
                not one of the clinician's, or ``require_admin`` and they are not admin there.
            ValidationError: no clinic named and the clinician belongs to several.
        """
        membership = await self.memberships.acting_membership(
            clinician_id, clinic_id, require_admin=require_admin
        )
        if membership is None:
            # Fail closed: no membership means no clinic to manage (no legacy name matching).
            raise AuthorizationError(
                "Only clinic admins can manage staff",
                reason_code=reasons.ADMIN_SCOPE_ONLY,
                actor_id=str(clinician_id),
                actor_role="clinician",
            )
        clinic_key = str(membership.clinic_id)
        clinic = self.clinic_repo.get_identity_by_id(clinic_key) or {}
        return {
            "clinic_id": clinic_key,
            "clinic_name": str(clinic.get("display_name") or ""),
            "clinic_code": clinic.get("code"),
            "role": membership.role.value,
        }

    async def list_staff(self, clinician_id: UUID, clinic_id: UUID | None = None) -> dict[str, Any]:
        """List the members of one clinic, each with the role held there."""
        context = await self._clinic_context(clinician_id, clinic_id, require_admin=False)
        members = await self.memberships.repo.list_active_for_clinic(context["clinic_id"])
        roles = {str(row["clinician_id"]): row.get("role") for row in members}
        staff_rows = [
            {**row, "role": roles[str(row.get("id"))] or row.get("role")}
            for row in self.clinician_repo.list_staff_by_ids(sorted(roles))
            if str(row.get("id")) in roles
        ]
        return {
            "staff": staff_rows,
            "clinic_id": context["clinic_id"],
            "clinic_name": context["clinic_name"],
            "clinic_code": context["clinic_code"],
        }

    async def update_role(
        self,
        admin_id: UUID,
        target_id: UUID,
        new_role: str,
        clinic_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Change the role a member holds at one clinic. Requires admin at that clinic."""
        if str(admin_id) == str(target_id):
            raise ValidationError("Cannot change your own role")
        context = await self._clinic_context(admin_id, clinic_id, require_admin=True)
        await self.memberships.set_member_role(admin_id, context["clinic_id"], target_id, new_role)
        return {"id": str(target_id), "role": new_role}

    async def remove_member(
        self, admin_id: UUID, target_id: UUID, clinic_id: UUID | None = None
    ) -> dict[str, str]:
        """Remove a member from one clinic. Requires admin at that clinic.

        Other memberships are kept. When this clinic was the member's default, their earliest
        remaining clinic becomes the default (with the role held there), or none.
        """
        if str(admin_id) == str(target_id):
            raise ValidationError("Cannot remove yourself from the clinic")
        context = await self._clinic_context(admin_id, clinic_id, require_admin=True)
        await self.memberships.remove_member(admin_id, context["clinic_id"], target_id)
        return {"status": "removed", "id": str(target_id)}

    async def invite_member(
        self, admin_id: UUID, email: str, role: str, clinic_id: UUID | None = None
    ) -> dict[str, Any]:
        """Save an addressed invitation to one clinic without modifying membership.

        An address that already belongs to another clinic can be invited: accepting adds
        this clinic to that account. One that is already a member here cannot.
        """
        context = await self._clinic_context(admin_id, clinic_id, require_admin=True)
        clinic_key = context["clinic_id"]
        for existing in self.clinician_repo.list_by_email(email):
            if existing.get("id") and await self.memberships.repo.get_active(
                str(existing["id"]), clinic_key
            ):
                raise ValidationError("This person is already in your clinic")
        return await EmailInvitationService(self.db).create(
            admin_id, email, role, context["clinic_name"], clinic_id=UUID(clinic_key)
        )
