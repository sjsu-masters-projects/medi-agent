"""Staff management service — list, invite, update roles, remove clinic team members.

Staff are clinicians who share the same clinic_name. An admin-role clinician
can manage roles for other members in their clinic.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from supabase import Client

from app.clients.resend import ResendClient
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.db.repositories import ClinicianRepository, ClinicRepository

logger = logging.getLogger(__name__)


class StaffService:
    """Clinic staff management operations."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self.clinic_repo = ClinicRepository(self)
        self.clinician_repo = ClinicianRepository(self)
        self.resend_client = ResendClient()

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

    def _send_clinician_invite_email(
        self,
        email: str,
        context: dict[str, Any],
        role: str,
    ) -> bool:
        """Notify invitee via Resend; isolated for tests and single call site."""
        return self.resend_client.send_clinician_invite(
            to_email=email,
            clinic_name=str(context["clinic_name"]),
            role=role,
            clinic_code=(str(context["clinic_code"]) if context.get("clinic_code") else None),
        )

    def _lookup_code_by_clinic_id(self, clinic_id: str) -> str | None:
        """Lookup clinic code by clinic UUID with best-effort error handling."""
        try:
            return self.clinic_repo.get_code_by_id(clinic_id)
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
                rows = self.clinic_repo.list_codes_by_canonical_name(normalized_name)
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
                rows = self.clinic_repo.list_codes_by_display_name(clinic_name)
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
                for peer_clinic_id in self.clinician_repo.list_peer_clinic_ids_by_name(clinic_name):
                    code = self._lookup_code_by_clinic_id(peer_clinic_id)
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
            data = self.clinician_repo.get_context(str(clinician_id))
        except Exception as exc:
            if self._is_no_rows_error(exc):
                raise NotFoundError("Clinician", str(clinician_id)) from None
            raise

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
            data = self.clinician_repo.get_context(str(clinician_id), include_role=True)
        except Exception as exc:
            if self._is_no_rows_error(exc):
                raise NotFoundError("Clinician", str(clinician_id)) from None
            raise

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

    async def list_staff(self, clinician_id: UUID) -> dict[str, Any]:
        """List all clinicians in the same clinic."""
        context = await self._get_clinic_context(clinician_id)

        staff_rows: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        if context["clinic_id"]:
            for row in self.clinician_repo.list_staff_by_clinic_id(str(context["clinic_id"])):
                row_id = str(row.get("id") or "")
                if row_id and row_id not in seen_ids:
                    seen_ids.add(row_id)
                    staff_rows.append(row)

            # Add same-name peers as a safety net for clinic identity drift.
            for row in self.clinician_repo.list_staff_by_clinic_name(str(context["clinic_name"])):
                row_id = str(row.get("id") or "")
                if row_id and row_id not in seen_ids:
                    seen_ids.add(row_id)
                    staff_rows.append(row)
        else:
            for row in self.clinician_repo.list_staff_by_clinic_name(str(context["clinic_name"])):
                row_id = str(row.get("id") or "")
                if row_id and row_id not in seen_ids:
                    seen_ids.add(row_id)
                    staff_rows.append(row)

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

        target_data = self.clinician_repo.get_target_identity(
            str(target_id),
            operation="staff role target lookup",
        )
        if not target_data or not self._is_same_clinic(
            source_id=(str(context["clinic_id"]) if context["clinic_id"] else None),
            source_name=str(context["clinic_name"]),
            target_id=(str(target_data.get("clinic_id")) if target_data.get("clinic_id") else None),
            target_name=str(target_data.get("clinic_name") or ""),
        ):
            raise NotFoundError("Staff member", str(target_id))

        self.clinician_repo.update_role(str(target_id), new_role)

        return {"id": str(target_id), "role": new_role}

    async def remove_member(self, admin_id: UUID, target_id: UUID) -> dict[str, str]:
        """Remove a staff member from the clinic. Requires admin role."""
        context = await self._require_admin(admin_id)

        if str(admin_id) == str(target_id):
            raise ValidationError("Cannot remove yourself from the clinic")

        target_data = self.clinician_repo.get_target_identity(
            str(target_id),
            operation="staff removal target lookup",
        )
        if not target_data or not self._is_same_clinic(
            source_id=(str(context["clinic_id"]) if context["clinic_id"] else None),
            source_name=str(context["clinic_name"]),
            target_id=(str(target_data.get("clinic_id")) if target_data.get("clinic_id") else None),
            target_name=str(target_data.get("clinic_name") or ""),
        ):
            raise NotFoundError("Staff member", str(target_id))

        self.clinician_repo.detach_from_clinic(
            str(target_id),
            clinic_name=str(context["clinic_name"]),
        )

        return {"status": "removed", "id": str(target_id)}

    async def invite_member(self, admin_id: UUID, email: str, role: str) -> dict[str, Any]:
        """Invite a new clinician to the clinic by email.

        If the email matches an existing clinician, updates their clinic_name.
        Otherwise creates a pending invitation record.
        """
        context = await self._require_admin(admin_id)

        existing = self.clinician_repo.list_by_email(email)

        if existing:
            target = existing[0]
            if self._is_same_clinic(
                source_id=(str(context["clinic_id"]) if context["clinic_id"] else None),
                source_name=str(context["clinic_name"]),
                target_id=(str(target.get("clinic_id")) if target.get("clinic_id") else None),
                target_name=str(target.get("clinic_name") or ""),
            ):
                raise ValidationError("This person is already in your clinic")

            self.clinician_repo.assign_to_clinic(
                str(target.get("id")),
                clinic_id=(str(context["clinic_id"]) if context["clinic_id"] else None),
                clinic_name=str(context["clinic_name"]),
                role=role,
            )

            email_sent = self._send_clinician_invite_email(email, context, role)

            return {"status": "added", "email": email, "role": role, "email_sent": email_sent}

        email_sent = self._send_clinician_invite_email(email, context, role)
        return {"status": "pending", "email": email, "role": role, "email_sent": email_sent}
