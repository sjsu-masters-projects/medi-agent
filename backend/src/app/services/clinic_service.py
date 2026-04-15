"""Clinic service — resolve clinic codes and internal clinic provisioning."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from supabase import Client

from app.core.exceptions import ValidationError


class ClinicService:
    """Clinic identity operations used by auth and internal tooling."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def resolve_clinic_code(self, clinic_code: str) -> dict[str, Any]:
        """Resolve a clinic code for clinician auth gating."""
        normalized_code = clinic_code.strip().upper()

        result = await self._execute(
            self.db.table("clinics")
            .select("id, code, display_name, status")
            .eq("code", normalized_code)
        )
        rows = cast("list[dict[str, Any]]", result.data or [])
        if not rows:
            raise ValidationError("Clinic code is invalid")

        clinic = rows[0]
        if clinic.get("status") != "active":
            raise ValidationError("Clinic code is inactive")

        return {
            "clinic_id": clinic["id"],
            "clinic_code": clinic["code"],
            "clinic_name": clinic["display_name"],
            "status": clinic["status"],
        }

    async def provision_clinic(
        self, clinic_name: str, type2_npi: str | None = None
    ) -> dict[str, Any]:
        """Create a canonical clinic row via internal provisioning flow."""
        clean_name = " ".join(clinic_name.split()).strip()
        if not clean_name:
            raise ValidationError("Clinic name cannot be empty")

        canonical_name = clean_name.lower()

        existing = await self._execute(
            self.db.table("clinics").select("id").eq("canonical_name", canonical_name)
        )
        existing_rows = cast("list[dict[str, Any]]", existing.data or [])
        if existing_rows:
            raise ValidationError("Clinic already exists")

        payload: dict[str, Any] = {
            "display_name": clean_name,
            "canonical_name": canonical_name,
            "type2_npi": type2_npi,
            "status": "active",
        }

        try:
            created = await self._execute(self.db.table("clinics").insert(payload))
        except Exception as exc:  # pragma: no cover - defensive branch
            detail = str(exc).lower()
            if "duplicate" in detail or "unique" in detail:
                raise ValidationError("Clinic already exists") from None
            if "row-level security" in detail or "violates row-level security policy" in detail:
                raise ValidationError(
                    "Clinic provisioning is blocked by clinics table RLS policy"
                ) from None
            raise

        rows = cast("list[dict[str, Any]]", created.data or [])
        if not rows:
            # Some Supabase client versions return no insert payload by default.
            fetched = await self._execute(
                self.db.table("clinics")
                .select("id, code, display_name, canonical_name, type2_npi, status, created_at")
                .eq("canonical_name", canonical_name)
            )
            rows = cast("list[dict[str, Any]]", fetched.data or [])

        if not rows:
            raise ValidationError("Clinic provisioning failed")

        return rows[0]

    async def _execute(self, query: Any) -> Any:
        """Run blocking Supabase execute() off the event loop."""
        return await asyncio.to_thread(query.execute)
