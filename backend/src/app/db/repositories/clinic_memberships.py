"""Clinic-membership repository methods (CLN-003)."""

from __future__ import annotations

from typing import Any, cast

from app.db.supabase_execute import HasSupabaseClient, execute_async

MEMBERSHIP_FIELDS = "clinician_id, clinic_id, role, status"


class ClinicMembershipRepository:
    """Encapsulate clinic_memberships table access patterns."""

    def __init__(self, owner: HasSupabaseClient) -> None:
        self.owner = owner

    @staticmethod
    def _as_rows(data: Any) -> list[dict[str, Any]]:
        return [row for row in cast("list[dict[str, Any]]", data or []) if isinstance(row, dict)]

    async def list_active_for_clinician(self, clinician_id: str) -> list[dict[str, Any]]:
        """List a clinician's active memberships."""
        result = await execute_async(
            self.owner,
            lambda db: db.table("clinic_memberships")
            .select(MEMBERSHIP_FIELDS)
            .eq("clinician_id", clinician_id)
            .eq("status", "active"),
            operation="clinic membership lookup",
            retry_transient=True,
        )
        return self._as_rows(result.data)

    async def list_active_clinician_ids(self, clinic_id: str, *, limit: int = 200) -> list[str]:
        """List the clinicians with an active membership at a clinic."""
        result = await execute_async(
            self.owner,
            lambda db: db.table("clinic_memberships")
            .select("clinician_id")
            .eq("clinic_id", clinic_id)
            .eq("status", "active")
            .limit(limit),
            operation="clinic member lookup",
            retry_transient=True,
        )
        return [
            str(row["clinician_id"])
            for row in self._as_rows(result.data)
            if row.get("clinician_id")
        ]
