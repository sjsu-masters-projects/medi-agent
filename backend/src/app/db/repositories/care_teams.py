"""Care-team-focused repository methods."""

from __future__ import annotations

from typing import Any, cast

from app.db.supabase_execute import HasSupabaseClient, execute_async


class CareTeamRepository:
    """Encapsulate care_teams table access patterns."""

    def __init__(self, owner: HasSupabaseClient) -> None:
        self.owner = owner

    @staticmethod
    def _as_rows(data: Any) -> list[dict[str, Any]]:
        return [row for row in cast("list[dict[str, Any]]", data or []) if isinstance(row, dict)]

    async def list_invites_for_clinician_ids(self, clinician_ids: list[str]) -> list[dict[str, Any]]:
        """List invite-code rows for a clinic-scoped set of clinicians."""
        result = await execute_async(
            self.owner,
            lambda db: db.table("care_teams")
            .select(
                "id, invite_code, status, role, patient_id, "
                "created_at, invite_expires_at, invite_claimed_at, "
                "patients(id, first_name, last_name, email), "
                "clinicians(id, first_name, last_name, email)"
            )
            .in_("clinician_id", clinician_ids)
            .order("created_at", desc=True)
            .limit(100),
            operation="invite code list lookup",
            retry_transient=True,
        )
        return self._as_rows(result.data)

    async def find_invite_for_creator(
        self, care_team_id: str, clinician_id: str
    ) -> dict[str, Any] | None:
        """Lookup an invite row scoped to its creator."""
        result = await execute_async(
            self.owner,
            lambda db: db.table("care_teams")
            .select("id, clinician_id, status, patient_id, invite_code")
            .eq("id", care_team_id)
            .eq("clinician_id", clinician_id)
            .single(),
            operation="invite lookup",
            retry_transient=False,
        )
        data = cast("dict[str, Any]", result.data or {})
        return data or None

    async def deactivate_invite(self, care_team_id: str, clinician_id: str | None = None) -> list[dict[str, Any]]:
        """Mark an invite row inactive, optionally scoped to creator."""
        def _build_query(db: Any) -> Any:
            query = db.table("care_teams").update({"status": "inactive"}).eq("id", care_team_id)
            if clinician_id is not None:
                query = query.eq("clinician_id", clinician_id)
            return query

        result = await execute_async(
            self.owner,
            _build_query,
            operation="invite deactivate",
            retry_transient=False,
        )
        return self._as_rows(result.data)

    async def list_pending_invites_for_clinician(self, clinician_id: str) -> list[dict[str, Any]]:
        """List pending invite rows for a clinician ordered newest-first."""
        result = await execute_async(
            self.owner,
            lambda db: db.table("care_teams")
            .select("id, invite_code, created_at, invite_expires_at")
            .eq("clinician_id", clinician_id)
            .eq("status", "pending")
            .order("created_at", desc=True),
            operation="current invite lookup",
            retry_transient=False,
        )
        return self._as_rows(result.data)

    async def find_active_assignment(self, clinician_id: str, patient_id: str) -> list[dict[str, Any]]:
        """Lookup active assignment rows for clinician-patient pairs."""
        result = await execute_async(
            self.owner,
            lambda db: db.table("care_teams")
            .select("id")
            .eq("clinician_id", clinician_id)
            .eq("patient_id", patient_id)
            .eq("status", "active"),
            operation="care team assignment lookup",
            retry_transient=False,
        )
        return self._as_rows(result.data)

    async def list_assigned_patient_ids(self, clinician_id: str) -> list[dict[str, Any]]:
        """List assigned patient IDs for a clinician."""
        result = await execute_async(
            self.owner,
            lambda db: db.table("care_teams")
            .select("patient_id")
            .eq("clinician_id", clinician_id)
            .eq("status", "active"),
            operation="assigned patient lookup",
            retry_transient=False,
        )
        return self._as_rows(result.data)
