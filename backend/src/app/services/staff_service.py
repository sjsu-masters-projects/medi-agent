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

    @staticmethod
    def _is_no_rows_error(exc: Exception) -> bool:
        detail = str(exc).lower()
        return "pgrst116" in detail or "contains 0 rows" in detail

    @staticmethod
    def _normalize_clinic_name(clinic_name: str) -> str:
        """Normalize clinic name for canonical_name comparisons."""
        return " ".join(clinic_name.split()).strip().lower()

    @staticmethod
    def _as_dict_rows(value: Any) -> list[dict[str, Any]]:
        """Normalize Supabase JSON payloads to dict-only row lists."""
        if not isinstance(value, list):
            return []

        return [row for row in value if isinstance(row, dict)]

    def _lookup_code_by_clinic_id(self, clinic_id: str) -> str | None:
        """Lookup clinic code by clinic UUID with best-effort error handling."""
        try:
            clinic_result = (
                self.db.table("clinics").select("code").eq("id", clinic_id).single().execute()
            )
            clinic_data = cast("dict[str, Any]", clinic_result.data)
            if clinic_data and clinic_data.get("code"):
                return cast("str", clinic_data["code"])
        except Exception as exc:
            if not self._is_no_rows_error(exc):
                logger.warning(
                    "Failed to resolve clinic code by clinic_id=%s", clinic_id, exc_info=exc
                )

        return None

    def _lookup_clinic_code(self, clinic_id: str | None, clinic_name: str) -> str | None:
        """Best-effort clinic code lookup for admin/settings surfaces."""
        if clinic_id:
            code = self._lookup_code_by_clinic_id(clinic_id)
            if code:
                return code

        normalized_name = self._normalize_clinic_name(clinic_name)
        if normalized_name:
            try:
                clinic_result = (
                    self.db.table("clinics")
                    .select("code")
                    .eq("canonical_name", normalized_name)
                    .limit(1)
                    .execute()
                )
                rows = self._as_dict_rows(clinic_result.data)
                if rows:
                    code = rows[0].get("code")
                    if isinstance(code, str) and code:
                        return code
            except Exception as exc:
                if not self._is_no_rows_error(exc):
                    logger.warning(
                        "Failed to resolve clinic code by canonical_name=%s",
                        normalized_name,
                        exc_info=exc,
                    )

        if clinic_name:
            try:
                clinic_result = (
                    self.db.table("clinics")
                    .select("code")
                    .eq("display_name", clinic_name)
                    .limit(1)
                    .execute()
                )
                rows = self._as_dict_rows(clinic_result.data)
                if rows:
                    code = rows[0].get("code")
                    if isinstance(code, str) and code:
                        return code
            except Exception as exc:
                if not self._is_no_rows_error(exc):
                    logger.warning(
                        "Failed to resolve clinic code by display_name=%s",
                        clinic_name,
                        exc_info=exc,
                    )

        if clinic_name:
            try:
                clinicians_result = (
                    self.db.table("clinicians")
                    .select("clinic_id")
                    .eq("clinic_name", clinic_name)
                    .limit(50)
                    .execute()
                )
                rows = self._as_dict_rows(clinicians_result.data)
                for row in rows:
                    peer_clinic_id = row.get("clinic_id")
                    if not peer_clinic_id:
                        continue
                    code = self._lookup_code_by_clinic_id(str(peer_clinic_id))
                    if code:
                        return code
            except Exception as exc:
                if not self._is_no_rows_error(exc):
                    logger.warning(
                        "Failed to resolve clinic code via peer clinicians for clinic_name=%s",
                        clinic_name,
                        exc_info=exc,
                    )

        return None

    async def _get_clinic_context(self, clinician_id: UUID) -> dict[str, Any]:
        """Look up clinic identity for a clinician.

        Uses clinic_id when available and falls back to legacy clinic_name.
        """
        try:
            result = (
                self.db.table("clinicians")
                .select("clinic_id, clinic_name")
                .eq("id", str(clinician_id))
                .single()
                .execute()
            )
        except Exception as exc:
            if self._is_no_rows_error(exc):
                raise NotFoundError("Clinician", str(clinician_id)) from None
            raise

        data = cast("dict[str, Any]", result.data)
        if not data:
            raise NotFoundError("Clinician", str(clinician_id))

        clinic_id = str(data.get("clinic_id")) if data.get("clinic_id") else None
        clinic_name = data.get("clinic_name") or ""
        return {
            "clinic_id": clinic_id,
            "clinic_name": clinic_name,
            "clinic_code": self._lookup_clinic_code(clinic_id, clinic_name),
        }

    async def _require_admin(self, clinician_id: UUID) -> dict[str, Any]:
        """Verify the clinician has admin role and return clinic context."""
        try:
            result = (
                self.db.table("clinicians")
                .select("clinic_id, clinic_name, role")
                .eq("id", str(clinician_id))
                .single()
                .execute()
            )
        except Exception as exc:
            if self._is_no_rows_error(exc):
                raise NotFoundError("Clinician", str(clinician_id)) from None
            raise

        data = cast("dict[str, Any]", result.data)
        if not data:
            raise NotFoundError("Clinician", str(clinician_id))
        if data["role"] != "admin":
            raise AuthorizationError("Only clinic admins can manage staff")

        clinic_id = str(data.get("clinic_id")) if data.get("clinic_id") else None
        clinic_name = data.get("clinic_name") or ""
        return {
            "clinic_id": clinic_id,
            "clinic_name": clinic_name,
            "clinic_code": self._lookup_clinic_code(clinic_id, clinic_name),
        }

    @staticmethod
    def _is_same_clinic(
        *,
        source_id: str | None,
        source_name: str,
        target_id: str | None,
        target_name: str,
    ) -> bool:
        """Compare clinic identity with clinic_id preferred, clinic_name fallback."""
        if source_id and target_id:
            if source_id == target_id:
                return True
            # Defensive fallback for rare identity drift while UUID data is corrected.
            return bool(source_name and target_name and source_name == target_name)

        # Fallback path when one side is missing clinic_id in runtime data.
        if source_name and target_name:
            return source_name == target_name

        return False

    def _build_staff_list_query(self) -> Any:
        return (
            self.db.table("clinicians")
            .select(
                "id, email, first_name, last_name, role, specialty, created_at, clinic_id, clinic_name"
            )
            .order("created_at")
        )

    async def list_staff(self, clinician_id: UUID) -> dict[str, Any]:
        """List all clinicians in the same clinic."""
        context = await self._get_clinic_context(clinician_id)

        staff_rows: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        if context["clinic_id"]:
            by_id_result = (
                self._build_staff_list_query().eq("clinic_id", str(context["clinic_id"])).execute()
            )
            for row in by_id_result.data or []:
                row_id = str(row.get("id") or "")
                if row_id and row_id not in seen_ids:
                    seen_ids.add(row_id)
                    staff_rows.append(cast("dict[str, Any]", row))

            # Add same-name peers as a safety net for clinic identity drift.
            by_name_result = (
                self._build_staff_list_query().eq("clinic_name", context["clinic_name"]).execute()
            )
            for row in by_name_result.data or []:
                row_id = str(row.get("id") or "")
                if row_id and row_id not in seen_ids:
                    seen_ids.add(row_id)
                    staff_rows.append(cast("dict[str, Any]", row))
        else:
            by_name_result = (
                self._build_staff_list_query().eq("clinic_name", context["clinic_name"]).execute()
            )
            for row in by_name_result.data or []:
                row_id = str(row.get("id") or "")
                if row_id and row_id not in seen_ids:
                    seen_ids.add(row_id)
                    staff_rows.append(cast("dict[str, Any]", row))

        return {
            "staff": staff_rows,
            "clinic_name": context["clinic_name"],
            "clinic_code": context.get("clinic_code"),
        }

    async def update_role(self, admin_id: UUID, target_id: UUID, new_role: str) -> dict[str, Any]:
        """Update a team member's role. Requires admin role."""
        context = await self._require_admin(admin_id)

        if str(admin_id) == str(target_id):
            raise ValidationError("Cannot change your own role")

        target = (
            self.db.table("clinicians")
            .select("id, clinic_id, clinic_name")
            .eq("id", str(target_id))
            .single()
            .execute()
        )
        target_data = cast("dict[str, Any]", target.data)
        if not target_data or not self._is_same_clinic(
            source_id=(str(context["clinic_id"]) if context["clinic_id"] else None),
            source_name=str(context["clinic_name"]),
            target_id=(str(target_data.get("clinic_id")) if target_data.get("clinic_id") else None),
            target_name=str(target_data.get("clinic_name") or ""),
        ):
            raise NotFoundError("Staff member", str(target_id))

        self.db.table("clinicians").update({"role": new_role}).eq("id", str(target_id)).execute()

        return {"id": str(target_id), "role": new_role}

    async def remove_member(self, admin_id: UUID, target_id: UUID) -> dict[str, str]:
        """Remove a staff member from the clinic. Requires admin role."""
        context = await self._require_admin(admin_id)

        if str(admin_id) == str(target_id):
            raise ValidationError("Cannot remove yourself from the clinic")

        target = (
            self.db.table("clinicians")
            .select("id, clinic_id, clinic_name")
            .eq("id", str(target_id))
            .single()
            .execute()
        )
        target_data = cast("dict[str, Any]", target.data)
        if not target_data or not self._is_same_clinic(
            source_id=(str(context["clinic_id"]) if context["clinic_id"] else None),
            source_name=str(context["clinic_name"]),
            target_id=(str(target_data.get("clinic_id")) if target_data.get("clinic_id") else None),
            target_name=str(target_data.get("clinic_name") or ""),
        ):
            raise NotFoundError("Staff member", str(target_id))

        self.db.table("clinicians").update(
            {
                "clinic_id": None,
                "clinic_name": f"_removed_{context['clinic_name']}",
            }
        ).eq("id", str(target_id)).execute()

        return {"status": "removed", "id": str(target_id)}

    async def invite_member(self, admin_id: UUID, email: str, role: str) -> dict[str, Any]:
        """Invite a new clinician to the clinic by email.

        If the email matches an existing clinician, updates their clinic_name.
        Otherwise creates a pending invitation record.
        """
        context = await self._require_admin(admin_id)

        existing = (
            self.db.table("clinicians")
            .select("id, clinic_id, clinic_name")
            .eq("email", email)
            .execute()
        )

        if existing.data:
            target = cast("dict[str, Any]", existing.data[0])
            if self._is_same_clinic(
                source_id=(str(context["clinic_id"]) if context["clinic_id"] else None),
                source_name=str(context["clinic_name"]),
                target_id=(str(target.get("clinic_id")) if target.get("clinic_id") else None),
                target_name=str(target.get("clinic_name") or ""),
            ):
                raise ValidationError("This person is already in your clinic")

            self.db.table("clinicians").update(
                {
                    "clinic_id": context["clinic_id"],
                    "clinic_name": context["clinic_name"],
                    "role": role,
                }
            ).eq("id", str(target.get("id"))).execute()

            return {"status": "added", "email": email, "role": role}

        return {"status": "pending", "email": email, "role": role}
