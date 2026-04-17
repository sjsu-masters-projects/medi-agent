"""Clinic-focused repository methods."""

from __future__ import annotations

from typing import Any, cast

from app.db.supabase_execute import HasSupabaseClient, execute_async, execute_sync


class ClinicRepository:
    """Encapsulate clinic table access patterns."""

    def __init__(self, owner: HasSupabaseClient) -> None:
        self.owner = owner

    @staticmethod
    def _filter_matching_code(rows: list[dict[str, Any]], normalized_code: str) -> list[dict[str, Any]]:
        return [
            row
            for row in rows
            if str(row.get("code", "")).strip().upper() == normalized_code
        ]

    @staticmethod
    def _as_rows(data: Any) -> list[dict[str, Any]]:
        return [row for row in cast("list[dict[str, Any]]", data or []) if isinstance(row, dict)]

    def find_matching_by_code(self, clinic_code: str) -> list[dict[str, Any]]:
        """Find clinics by exact code with a whitespace-tolerant fallback."""
        normalized_code = clinic_code.strip().upper()
        exact_result = execute_sync(
            self.owner,
            lambda db: db.table("clinics")
            .select("id, code, display_name, status")
            .eq("code", normalized_code),
            operation="clinic lookup",
            retry_transient=True,
        )
        exact_rows = self._as_rows(exact_result.data)
        if exact_rows:
            return exact_rows

        fallback_result = execute_sync(
            self.owner,
            lambda db: db.table("clinics")
            .select("id, code, display_name, status")
            .ilike("code", f"%{normalized_code}%"),
            operation="clinic lookup",
            retry_transient=True,
        )
        return self._filter_matching_code(self._as_rows(fallback_result.data), normalized_code)

    async def find_matching_by_code_async(self, clinic_code: str) -> list[dict[str, Any]]:
        """Async variant for services running on the event loop."""
        normalized_code = clinic_code.strip().upper()
        exact_result = await execute_async(
            self.owner,
            lambda db: db.table("clinics")
            .select("id, code, display_name, status")
            .eq("code", normalized_code),
            operation="clinic lookup",
            retry_transient=True,
        )
        exact_rows = self._as_rows(exact_result.data)
        if exact_rows:
            return exact_rows

        fallback_result = await execute_async(
            self.owner,
            lambda db: db.table("clinics")
            .select("id, code, display_name, status")
            .ilike("code", f"%{normalized_code}%"),
            operation="clinic lookup",
            retry_transient=True,
        )
        return self._filter_matching_code(self._as_rows(fallback_result.data), normalized_code)

    def get_code_by_id(self, clinic_id: str) -> str | None:
        """Return clinic code for a clinic UUID."""
        result = execute_sync(
            self.owner,
            lambda db: db.table("clinics").select("code").eq("id", clinic_id).single(),
            operation=f"clinic code lookup by clinic_id={clinic_id}",
            retry_transient=True,
        )
        clinic_data = cast("dict[str, Any]", result.data or {})
        code = clinic_data.get("code")
        return code if isinstance(code, str) and code else None

    def list_codes_by_canonical_name(self, canonical_name: str) -> list[dict[str, Any]]:
        """List clinic code rows by canonical name."""
        result = execute_sync(
            self.owner,
            lambda db: db.table("clinics")
            .select("code")
            .eq("canonical_name", canonical_name)
            .limit(1),
            operation=f"clinic code lookup by canonical_name={canonical_name}",
            retry_transient=True,
        )
        return self._as_rows(result.data)

    def list_codes_by_display_name(self, display_name: str) -> list[dict[str, Any]]:
        """List clinic code rows by display name."""
        result = execute_sync(
            self.owner,
            lambda db: db.table("clinics")
            .select("code")
            .eq("display_name", display_name)
            .limit(1),
            operation=f"clinic code lookup by display_name={display_name}",
            retry_transient=True,
        )
        return self._as_rows(result.data)

    async def find_existing_by_canonical_name(self, canonical_name: str) -> list[dict[str, Any]]:
        """Find clinics by canonical name for pre-provision duplicate checks."""
        result = await execute_async(
            self.owner,
            lambda db: db.table("clinics").select("id").eq("canonical_name", canonical_name),
            operation="clinic existing lookup",
            retry_transient=False,
        )
        return self._as_rows(result.data)

    async def insert_clinic(self, payload: dict[str, Any]) -> Any:
        """Insert a clinic row."""
        return await execute_async(
            self.owner,
            lambda db: db.table("clinics").insert(payload),
            operation="clinic insert",
            retry_transient=False,
        )

    async def find_provisioned_by_canonical_name(self, canonical_name: str) -> list[dict[str, Any]]:
        """Fetch the provisioned clinic row when insert payload is empty."""
        result = await execute_async(
            self.owner,
            lambda db: db.table("clinics")
            .select("id, code, display_name, canonical_name, type2_npi, status, created_at")
            .eq("canonical_name", canonical_name),
            operation="clinic fetch after provision",
            retry_transient=False,
        )
        return self._as_rows(result.data)
