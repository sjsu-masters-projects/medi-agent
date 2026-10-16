"""Clinic-membership repository methods (CLN-003)."""

from __future__ import annotations

from typing import Any, cast

from app.db.supabase_execute import HasSupabaseClient, execute_async, execute_sync

MEMBERSHIP_FIELDS = "clinician_id, clinic_id, role, status"
# The clinic's own status decides whether a membership can be acted in.
MEMBERSHIP_WITH_CLINIC_FIELDS = f"{MEMBERSHIP_FIELDS}, clinics(status)"


class ClinicMembershipRepository:
    """Encapsulate clinic_memberships table access patterns."""

    def __init__(self, owner: HasSupabaseClient) -> None:
        self.owner = owner

    @staticmethod
    def _as_rows(data: Any) -> list[dict[str, Any]]:
        return [row for row in cast("list[dict[str, Any]]", data or []) if isinstance(row, dict)]

    async def list_active_for_clinician(self, clinician_id: str) -> list[dict[str, Any]]:
        """List a clinician's active memberships, with each clinic's status."""
        result = await execute_async(
            self.owner,
            lambda db: db.table("clinic_memberships")
            .select(MEMBERSHIP_WITH_CLINIC_FIELDS)
            .eq("clinician_id", clinician_id)
            .eq("status", "active"),
            operation="clinic membership lookup",
            retry_transient=True,
        )
        return self._as_rows(result.data)

    def list_active_for_clinician_sync(self, clinician_id: str) -> list[dict[str, Any]]:
        """Sync variant for the sign-in checks."""
        result = execute_sync(
            self.owner,
            lambda db: db.table("clinic_memberships")
            .select(MEMBERSHIP_WITH_CLINIC_FIELDS)
            .eq("clinician_id", clinician_id)
            .eq("status", "active"),
            operation="clinic membership lookup",
            retry_transient=True,
        )
        return self._as_rows(result.data)

    async def list_active_clinician_ids(self, clinic_id: str, *, limit: int = 200) -> list[str]:
        """List the clinicians with an active membership at a clinic."""
        rows = await self.list_active_for_clinic(clinic_id, limit=limit)
        return [str(row["clinician_id"]) for row in rows if row.get("clinician_id")]

    async def list_active_for_clinic(
        self, clinic_id: str, *, limit: int = 200
    ) -> list[dict[str, Any]]:
        """List the active members of a clinic with the role each holds there."""
        result = await execute_async(
            self.owner,
            lambda db: db.table("clinic_memberships")
            .select("clinician_id, role")
            .eq("clinic_id", clinic_id)
            .eq("status", "active")
            .limit(limit),
            operation="clinic member lookup",
            retry_transient=True,
        )
        return self._as_rows(result.data)

    async def get_active(self, clinician_id: str, clinic_id: str) -> dict[str, Any] | None:
        """Return one clinician's active membership at one clinic, if any."""
        result = await execute_async(
            self.owner,
            lambda db: db.table("clinic_memberships")
            .select(MEMBERSHIP_FIELDS)
            .eq("clinician_id", clinician_id)
            .eq("clinic_id", clinic_id)
            .eq("status", "active")
            .limit(1),
            operation="clinic membership lookup",
            retry_transient=True,
        )
        rows = self._as_rows(result.data)
        return rows[0] if rows else None
