"""Staff management service — list, invite, update roles, remove clinic team members.

Staff are clinicians who share the same clinic_name. An admin-role clinician
can manage roles for other members in their clinic.
"""

from __future__ import annotations

import logging
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)


class StaffService:
    """Clinic staff management operations."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def _get_clinic_name(self, clinician_id: UUID) -> str:
        """Look up the clinic_name for a clinician."""
        result = (
            self.db.table("clinicians")
            .select("clinic_name")
            .eq("id", str(clinician_id))
            .single()
            .execute()
        )
        if not result.data:
            raise NotFoundError("Clinician", str(clinician_id))
        return cast("str", result.data["clinic_name"])

    async def _require_admin(self, clinician_id: UUID) -> str:
        """Verify the clinician has admin role. Returns their clinic_name."""
        result = (
            self.db.table("clinicians")
            .select("clinic_name, role")
            .eq("id", str(clinician_id))
            .single()
            .execute()
        )
        if not result.data:
            raise NotFoundError("Clinician", str(clinician_id))
        if result.data["role"] != "admin":
            raise AuthorizationError("Only clinic admins can manage staff")
        return cast("str", result.data["clinic_name"])

    async def list_staff(self, clinician_id: UUID) -> dict[str, Any]:
        """List all clinicians in the same clinic."""
        clinic_name = await self._get_clinic_name(clinician_id)
        result = (
            self.db.table("clinicians")
            .select("id, email, first_name, last_name, role, specialty, created_at")
            .eq("clinic_name", clinic_name)
            .order("created_at")
            .execute()
        )
        return {
            "staff": result.data or [],
            "clinic_name": clinic_name,
        }

    async def update_role(self, admin_id: UUID, target_id: UUID, new_role: str) -> dict[str, Any]:
        """Update a team member's role. Requires admin role."""
        clinic_name = await self._require_admin(admin_id)

        if str(admin_id) == str(target_id):
            raise ValidationError("Cannot change your own role")

        target = (
            self.db.table("clinicians")
            .select("id, clinic_name")
            .eq("id", str(target_id))
            .single()
            .execute()
        )
        if not target.data or target.data["clinic_name"] != clinic_name:
            raise NotFoundError("Staff member", str(target_id))

        self.db.table("clinicians").update({"role": new_role}).eq("id", str(target_id)).execute()

        return {"id": str(target_id), "role": new_role}

    async def remove_member(self, admin_id: UUID, target_id: UUID) -> dict[str, str]:
        """Remove a staff member from the clinic. Requires admin role."""
        clinic_name = await self._require_admin(admin_id)

        if str(admin_id) == str(target_id):
            raise ValidationError("Cannot remove yourself from the clinic")

        target = (
            self.db.table("clinicians")
            .select("id, clinic_name")
            .eq("id", str(target_id))
            .single()
            .execute()
        )
        if not target.data or target.data["clinic_name"] != clinic_name:
            raise NotFoundError("Staff member", str(target_id))

        self.db.table("clinicians").update({"clinic_name": f"_removed_{clinic_name}"}).eq(
            "id", str(target_id)
        ).execute()

        return {"status": "removed", "id": str(target_id)}

    async def invite_member(self, admin_id: UUID, email: str, role: str) -> dict[str, Any]:
        """Invite a new clinician to the clinic by email.

        If the email matches an existing clinician, updates their clinic_name.
        Otherwise creates a pending invitation record.
        """
        clinic_name = await self._require_admin(admin_id)

        existing = (
            self.db.table("clinicians").select("id, clinic_name").eq("email", email).execute()
        )

        if existing.data:
            target = existing.data[0]
            if target["clinic_name"] == clinic_name:
                raise ValidationError("This person is already in your clinic")

            self.db.table("clinicians").update({"clinic_name": clinic_name, "role": role}).eq(
                "id", target["id"]
            ).execute()

            return {"status": "added", "email": email, "role": role}

        return {"status": "pending", "email": email, "role": role}
