"""Clinic service — resolve clinic codes and provision clinics for auth flows."""

from __future__ import annotations

from typing import Any, cast

from supabase import Client

from app.core.exceptions import ValidationError
from app.db.repositories import ClinicRepository
from app.db.supabase_execute import execute_async


class ClinicService:
    """Clinic identity operations used by auth and internal tooling."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self.clinic_repo = ClinicRepository(self)

    async def resolve_clinic_code(self, clinic_code: str) -> dict[str, Any]:
        """Resolve a clinic code for clinician auth gating."""
        rows = await self.clinic_repo.find_matching_by_code_async(clinic_code)
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

        existing_rows = await self.clinic_repo.find_existing_by_canonical_name(canonical_name)
        if existing_rows:
            raise ValidationError("Clinic already exists")

        payload: dict[str, Any] = {
            "display_name": clean_name,
            "canonical_name": canonical_name,
            "type2_npi": type2_npi,
            "status": "active",
        }

        try:
            created = await self.clinic_repo.insert_clinic(payload)
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
            rows = await self.clinic_repo.find_provisioned_by_canonical_name(canonical_name)

        if not rows:
            raise ValidationError("Clinic provisioning failed")

        return rows[0]

    async def _execute(self, query: Any) -> Any:
        """Run blocking Supabase execute() off the event loop."""
        return await execute_async(
            self,
            lambda _db: query,
            operation="Supabase query",
            retry_transient=False,
        )
