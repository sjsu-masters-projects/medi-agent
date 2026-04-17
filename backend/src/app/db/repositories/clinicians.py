"""Clinician-focused repository methods."""

from __future__ import annotations

from typing import Any, cast

from supabase import Client

from app.db.supabase_execute import HasSupabaseClient, execute_async, execute_sync


class ClinicianRepository:
    """Encapsulate clinician table access patterns."""

    def __init__(self, owner: HasSupabaseClient) -> None:
        self.owner = owner

    @staticmethod
    def _as_rows(data: Any) -> list[dict[str, Any]]:
        return [row for row in cast("list[dict[str, Any]]", data or []) if isinstance(row, dict)]

    def get_context(
        self, clinician_id: str, *, include_role: bool = False
    ) -> dict[str, Any] | None:
        """Return clinician clinic context and optionally role."""
        fields = "clinic_id, clinic_name, role" if include_role else "clinic_id, clinic_name"
        result = execute_sync(
            self.owner,
            lambda db: db.table("clinicians").select(fields).eq("id", clinician_id).single(),
            operation="clinician context lookup",
            retry_transient=True,
        )
        data = cast("dict[str, Any]", result.data or {})
        return data or None

    async def get_context_async(
        self, clinician_id: str, *, include_role: bool = False
    ) -> dict[str, Any] | None:
        """Async variant for clinician context lookups."""
        fields = "id, clinic_id, clinic_name, role" if include_role else "clinic_id, clinic_name"
        result = await execute_async(
            self.owner,
            lambda db: db.table("clinicians").select(fields).eq("id", clinician_id).single(),
            operation="clinician context lookup",
            retry_transient=True,
        )
        data = cast("dict[str, Any]", result.data or {})
        return data or None

    def list_ids_by_clinic_id(self, clinic_id: str, *, limit: int = 200) -> list[str]:
        """List clinician IDs by clinic UUID."""
        result = execute_sync(
            self.owner,
            lambda db: db.table("clinicians").select("id").eq("clinic_id", clinic_id).limit(limit),
            operation="clinic member lookup",
            retry_transient=True,
        )
        return [str(row["id"]) for row in self._as_rows(result.data) if row.get("id")]

    async def list_ids_by_clinic_id_async(self, clinic_id: str, *, limit: int = 200) -> list[str]:
        """Async variant to list clinician IDs by clinic UUID."""
        result = await execute_async(
            self.owner,
            lambda db: db.table("clinicians").select("id").eq("clinic_id", clinic_id).limit(limit),
            operation="clinic member lookup",
            retry_transient=True,
        )
        return [str(row["id"]) for row in self._as_rows(result.data) if row.get("id")]

    def list_ids_by_clinic_name(self, clinic_name: str, *, limit: int = 200) -> list[str]:
        """List clinician IDs by legacy clinic name."""
        result = execute_sync(
            self.owner,
            lambda db: db.table("clinicians")
            .select("id")
            .eq("clinic_name", clinic_name)
            .limit(limit),
            operation="clinic member lookup",
            retry_transient=True,
        )
        return [str(row["id"]) for row in self._as_rows(result.data) if row.get("id")]

    async def list_ids_by_clinic_name_async(
        self, clinic_name: str, *, limit: int = 200
    ) -> list[str]:
        """Async variant to list clinician IDs by legacy clinic name."""
        result = await execute_async(
            self.owner,
            lambda db: db.table("clinicians")
            .select("id")
            .eq("clinic_name", clinic_name)
            .limit(limit),
            operation="clinic member lookup",
            retry_transient=True,
        )
        return [str(row["id"]) for row in self._as_rows(result.data) if row.get("id")]

    def list_peer_clinic_ids_by_name(self, clinic_name: str, *, limit: int = 50) -> list[str]:
        """List clinic UUIDs from peer clinicians sharing the same clinic name."""
        result = execute_sync(
            self.owner,
            lambda db: db.table("clinicians")
            .select("clinic_id")
            .eq("clinic_name", clinic_name)
            .limit(limit),
            operation=f"peer clinician clinic code lookup by clinic_name={clinic_name}",
            retry_transient=True,
        )
        return [str(row["clinic_id"]) for row in self._as_rows(result.data) if row.get("clinic_id")]

    def build_staff_list_query(self, db: Client) -> Any:
        """Shared staff list base query."""
        return (
            db.table("clinicians")
            .select(
                "id, email, first_name, last_name, role, specialty, created_at, clinic_id, clinic_name"
            )
            .order("created_at")
        )

    def list_staff_by_clinic_id(self, clinic_id: str) -> list[dict[str, Any]]:
        """List staff rows by clinic UUID."""
        result = execute_sync(
            self.owner,
            lambda db: self.build_staff_list_query(db).eq("clinic_id", clinic_id),
            operation="staff list by clinic_id",
            retry_transient=True,
        )
        return self._as_rows(result.data)

    def list_staff_by_clinic_name(self, clinic_name: str) -> list[dict[str, Any]]:
        """List staff rows by legacy clinic name."""
        result = execute_sync(
            self.owner,
            lambda db: self.build_staff_list_query(db).eq("clinic_name", clinic_name),
            operation="staff list by clinic_name",
            retry_transient=True,
        )
        return self._as_rows(result.data)

    def get_target_identity(self, clinician_id: str, *, operation: str) -> dict[str, Any] | None:
        """Lookup a clinician row used by staff mutations."""
        result = execute_sync(
            self.owner,
            lambda db: db.table("clinicians")
            .select("id, clinic_id, clinic_name")
            .eq("id", clinician_id)
            .single(),
            operation=operation,
            retry_transient=True,
        )
        data = cast("dict[str, Any]", result.data or {})
        return data or None

    def list_by_email(self, email: str) -> list[dict[str, Any]]:
        """Lookup clinicians by email address."""
        result = execute_sync(
            self.owner,
            lambda db: db.table("clinicians")
            .select("id, clinic_id, clinic_name")
            .eq("email", email),
            operation="staff invite existing clinician lookup",
            retry_transient=True,
        )
        return self._as_rows(result.data)

    def update_role(self, clinician_id: str, new_role: str) -> None:
        """Persist a clinician role update."""
        self.owner.db.table("clinicians").update({"role": new_role}).eq(
            "id", clinician_id
        ).execute()

    def assign_to_clinic(
        self,
        clinician_id: str,
        *,
        clinic_id: str | None,
        clinic_name: str,
        role: str,
    ) -> None:
        """Assign an existing clinician to a clinic."""
        self.owner.db.table("clinicians").update(
            {
                "clinic_id": clinic_id,
                "clinic_name": clinic_name,
                "role": role,
            }
        ).eq("id", clinician_id).execute()

    def detach_from_clinic(self, clinician_id: str, *, clinic_name: str) -> None:
        """Remove a clinician from a clinic while preserving auditability."""
        self.owner.db.table("clinicians").update(
            {
                "clinic_id": None,
                "clinic_name": f"_removed_{clinic_name}",
            }
        ).eq("id", clinician_id).execute()
