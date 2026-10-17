"""Clinic memberships: which clinics a clinician belongs to and in which role (CLN-003).

A clinician signs in once and sees every patient they are linked to; there is no global
"active clinic". A clinic is chosen only inside an action that belongs to one clinic (patient
invite codes, staff, email invitations, clinic settings). :meth:`acting_membership` resolves
that clinic: the one named by the request, checked against an active membership at an active
clinic, or, without one, the clinician's only membership. Role checks for such an action read
the role held at that clinic, never ``clinicians.role``.

``clinicians.clinic_id`` stays the clinician's default clinic (the first clinic joined) for
legacy readers; joining another clinic does not change it.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError

from app.core import authorization_reasons as reasons
from app.core.exceptions import (
    AuthorizationError,
    ExternalServiceError,
    MediAgentError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from app.db.repositories.care_teams import CareTeamRepository
from app.db.repositories.clinic_memberships import ClinicMembershipRepository
from app.db.supabase_execute import HasSupabaseClient
from app.models.clinic_membership import ClinicMembership
from app.models.enums import ClinicianRole
from app.services.clinic_link_scope import ClinicLinkScope, scope_from_links

logger = logging.getLogger(__name__)

# PostgREST and PostgreSQL codes for a function or table that is not installed yet (066).
_SETUP_PENDING_CODES = {"PGRST202", "PGRST204", "PGRST205", "42883", "42P01"}

NOT_A_MEMBER_MESSAGE = "You are not an active member of that clinic."


def _not_a_member(clinician_id: UUID | str) -> AuthorizationError:
    return AuthorizationError(
        NOT_A_MEMBER_MESSAGE,
        reason_code=reasons.CLINIC_MEMBERSHIP_REQUIRED,
        actor_id=str(clinician_id),
        actor_role="clinician",
        target_type="clinic",
    )


# Stable hints raised by public.clinician_clinic_operation, mapped to public copy.
def _hint_error(hint: str, clinician_id: str) -> MediAgentError | None:
    if hint == "clinic_code_invalid":
        return ValidationError("Clinic code is invalid", code="CLINIC_CODE_INVALID")
    if hint == "clinic_code_inactive":
        return ValidationError("Clinic code is inactive", code="CLINIC_CODE_INACTIVE")
    if hint == "invalid_role":
        return ValidationError(
            "Choose Provider or Nurse / MA. Clinic admin access comes only from an invitation.",
            code="INVALID_ROLE",
        )
    if hint == "membership_inactive":
        ended = AuthorizationError(
            "Your membership at this clinic was ended. Ask that clinic's admin to invite you again.",
            reason_code=reasons.CLINIC_MEMBERSHIP_REQUIRED,
            actor_id=clinician_id,
            actor_role="clinician",
            target_type="clinic",
        )
        # A distinct public code so the portal can say what to do next.
        ended.code = "MEMBERSHIP_INACTIVE"
        return ended
    if hint == "admin_required":
        return AuthorizationError(
            "Only clinic admins can manage staff",
            reason_code=reasons.ADMIN_SCOPE_ONLY,
            actor_id=clinician_id,
            actor_role="clinician",
            target_type="clinic",
        )
    if hint == "clinic_unavailable":
        return _not_a_member(clinician_id)
    if hint == "member_unavailable":
        return NotFoundError("Staff member", "in this clinic")
    if hint == "self_change":
        return ValidationError("You cannot change your own role or remove yourself.")
    if hint == "last_clinic":
        return ValidationError(
            "This is your only clinic, so you cannot leave it.", code="LAST_CLINIC"
        )
    if hint == "sole_admin":
        return ValidationError(
            "You are the only admin here. Make someone else an admin before you leave.",
            code="SOLE_ADMIN",
        )
    if hint == "clinic_name_taken":
        return ValidationError("Another clinic already uses that name.", code="CLINIC_NAME_TAKEN")
    if hint == "invalid_name":
        return ValidationError("Enter a clinic name of 2 to 120 characters.", code="INVALID_NAME")
    if hint == "clinician_required":
        return AuthorizationError(
            "A clinician profile is required.",
            reason_code=reasons.ROLE_LACKS_CLINICAL_SCOPE,
            actor_id=clinician_id,
        )
    return None


class ClinicMembershipService:
    """Read a clinician's clinic memberships and add a clinic by open code."""

    def __init__(self, owner: HasSupabaseClient) -> None:
        self.owner = owner
        self.repo = ClinicMembershipRepository(owner)

    @staticmethod
    def _acting_rows(rows: list[dict[str, Any]]) -> list[ClinicMembership]:
        # A membership at a suspended clinic cannot be acted in. Rows without the embedded
        # clinic (older callers) are kept; the clinic status is then checked elsewhere.
        kept = []
        for row in rows:
            clinic = row.get("clinics")
            if isinstance(clinic, dict) and clinic.get("status") not in (None, "active"):
                continue
            kept.append(ClinicMembership.model_validate(row))
        return sorted(kept, key=lambda membership: str(membership.clinic_id))

    async def active_memberships(self, clinician_id: UUID | str) -> list[ClinicMembership]:
        """Return the clinician's active memberships at active clinics, ordered by clinic."""
        rows = await self.repo.list_active_for_clinician(str(clinician_id))
        return self._acting_rows(rows)

    def active_memberships_sync(self, clinician_id: UUID | str) -> list[ClinicMembership]:
        """Sync variant for the sign-in checks."""
        return self._acting_rows(self.repo.list_active_for_clinician_sync(str(clinician_id)))

    async def acting_membership(
        self,
        clinician_id: UUID | str,
        clinic_id: UUID | str | None = None,
        *,
        require_admin: bool = False,
    ) -> ClinicMembership | None:
        """Resolve the clinic a clinic-scoped action runs in.

        Returns ``None`` only for a clinician with no membership and no clinic named (legacy
        accounts; callers keep their legacy fallback).

        Raises:
            AuthorizationError: the named clinic has no active membership at an active clinic,
                or ``require_admin`` and the role held at that clinic is not admin.
            ValidationError: no clinic was named and the clinician belongs to several.
        """
        memberships = await self.active_memberships(clinician_id)
        if clinic_id is not None:
            wanted = str(clinic_id)
            match = next((m for m in memberships if str(m.clinic_id) == wanted), None)
            if match is None:
                raise _not_a_member(clinician_id)
        elif not memberships:
            return None
        elif len(memberships) == 1:
            match = memberships[0]
        else:
            raise ValidationError("Choose the clinic for this action.", code="CLINIC_REQUIRED")
        if require_admin and match.role is not ClinicianRole.ADMIN:
            raise AuthorizationError(
                "Only clinic admins can manage staff",
                reason_code=reasons.ADMIN_SCOPE_ONLY,
                actor_id=str(clinician_id),
                actor_role="clinician",
                target_type="clinic",
                target_id=str(match.clinic_id),
            )
        return match

    async def link_scope(
        self, clinician_id: UUID | str, clinic_id: UUID | str | None = None
    ) -> ClinicLinkScope:
        """The patients a clinician's list shows, tagged with the clinic of each link.

        Without ``clinic_id``: every active link. With it: the links at that clinic, and only
        when the clinician holds an active membership there; any other clinic yields an empty
        scope, so the answer never reveals whether the clinic exists.
        """
        rows = await CareTeamRepository(self.owner).list_active_links(str(clinician_id))
        allowed: set[str] = set()
        if clinic_id is not None:
            allowed = {str(m.clinic_id) for m in await self.active_memberships(clinician_id)}
        return scope_from_links(rows, str(clinic_id) if clinic_id is not None else None, allowed)

    async def clinic_member_ids(self, clinic_id: UUID | str) -> list[str]:
        """Return the clinicians with an active membership at the clinic."""
        return await self.repo.list_active_clinician_ids(str(clinic_id))

    # ── Clinic pickers and joining by code (066) ──────────────

    async def _operation(
        self, clinician_id: UUID | str, action: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        params = {"p_actor": str(clinician_id), "p_action": action, "p_payload": payload}
        try:
            result = await asyncio.to_thread(
                self.owner.db.rpc("clinician_clinic_operation", params).execute
            )
        except APIError as exc:
            if exc.code in _SETUP_PENDING_CODES:
                raise ServiceUnavailableError(
                    "Clinic memberships are being updated. Try again later.",
                    code="CLINIC_SETUP_PENDING",
                ) from None
            mapped = _hint_error(str(exc.hint or ""), str(clinician_id))
            if mapped is not None:
                raise mapped from None
            logger.warning("Clinic membership operation refused (%s)", exc.code)
            raise ExternalServiceError("Clinic memberships", "Try again later.") from None
        except Exception as exc:
            # Transport errors: keep database text and identifiers out of logs.
            logger.warning("Clinic membership operation unavailable (%s)", type(exc).__name__)
            raise ExternalServiceError("Clinic memberships", "Try again later.") from None
        if not isinstance(result.data, dict):
            raise ExternalServiceError("Clinic memberships", "Try again later.")
        return cast("dict[str, Any]", result.data)

    async def clinics(self, clinician_id: UUID | str) -> dict[str, Any]:
        """List the clinics the clinician can act in, and their default clinic."""
        result = await self._operation(clinician_id, "list", {})
        # The open clinic code lets anyone who has it join, so only an admin at that clinic gets it.
        for entry in result.get("clinics") or []:
            if isinstance(entry, dict) and entry.get("role") != "admin":
                entry["clinic_code"] = None
        return result

    async def join_by_code(
        self, clinician_id: UUID | str, clinic_code: str, role: str
    ) -> dict[str, Any]:
        """Add a clinic to the signed-in account with an open clinic code (audited)."""
        return await self._operation(
            clinician_id,
            "join_code",
            {"clinic_code": clinic_code.strip().upper(), "role": role},
        )

    async def set_member_role(
        self, admin_id: UUID | str, clinic_id: UUID | str, member_id: UUID | str, role: str
    ) -> dict[str, Any]:
        """Change the role a member holds at one clinic (admin there; audited)."""
        return await self._operation(
            admin_id,
            "set_member_role",
            {"clinic_id": str(clinic_id), "member_id": str(member_id), "role": role},
        )

    async def remove_member(
        self, admin_id: UUID | str, clinic_id: UUID | str, member_id: UUID | str
    ) -> dict[str, Any]:
        """End a member's membership at one clinic (admin there; audited)."""
        return await self._operation(
            admin_id, "remove_member", {"clinic_id": str(clinic_id), "member_id": str(member_id)}
        )

    # ── Default clinic, leaving and clinic settings (067) ─────

    async def set_default(self, clinician_id: UUID | str, clinic_id: UUID | str) -> dict[str, Any]:
        """Choose the preselected clinic. Ends no membership (audited)."""
        return await self._operation(clinician_id, "set_default", {"clinic_id": str(clinic_id)})

    async def leave(self, clinician_id: UUID | str, clinic_id: UUID | str) -> dict[str, Any]:
        """Leave one clinic; the caller's links and unused codes there end (audited)."""
        return await self._operation(clinician_id, "leave", {"clinic_id": str(clinic_id)})

    async def rename_clinic(
        self, clinician_id: UUID | str, clinic_id: UUID | str, display_name: str
    ) -> dict[str, Any]:
        """An admin of that clinic edits its display name (audited)."""
        return await self._operation(
            clinician_id,
            "update_clinic",
            {"clinic_id": str(clinic_id), "display_name": display_name},
        )
