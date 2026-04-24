"""Patient service — profile management and care team operations.

Handles:
    - Get/update own patient profile
    - List care team (clinicians assigned to this patient)
    - Join a clinic via invite code
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import NotFoundError, ValidationError
from app.services.reminder_schedule_service import validate_timezone_name

logger = logging.getLogger(__name__)


class PatientService:
    """Patient-scoped operations. All methods require the patient's user ID."""

    def __init__(self, db: Client) -> None:
        self.db = db

    # ── Profile ─────────────────────────────────────────

    async def get_profile(self, patient_id: UUID) -> Any:
        """Fetch the patient's own profile by auth user ID."""
        result = self.db.table("patients").select("*").eq("id", str(patient_id)).single().execute()
        if not result.data:
            raise NotFoundError("Patient", str(patient_id))
        return result.data

    async def update_profile(self, patient_id: UUID, updates: dict[str, Any]) -> Any:
        """Partial update — only non-None fields are sent."""
        # Filter out None values so we don't overwrite with nulls
        clean = {k: v for k, v in updates.items() if v is not None}
        if not clean:
            return await self.get_profile(patient_id)

        if "timezone" in clean:
            clean["timezone"] = validate_timezone_name(str(clean["timezone"]))

        result = self.db.table("patients").update(clean).eq("id", str(patient_id)).execute()
        if not result.data:
            raise NotFoundError("Patient", str(patient_id))
        return result.data[0]

    # ── Care Team ───────────────────────────────────────

    async def get_care_team(self, patient_id: UUID) -> Any:
        """List all clinicians assigned to this patient, with their names."""
        result = (
            self.db.table("care_teams")
            .select("*, clinicians(first_name, last_name, specialty, clinic_name)")
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
            .execute()
        )
        # Flatten the joined clinician data for the response
        teams = []
        for row in cast(list[dict[str, Any]], result.data or []):
            clinician = cast(dict[str, Any], row.pop("clinicians", {}) or {})
            row["clinician_first_name"] = clinician.get("first_name", "")
            row["clinician_last_name"] = clinician.get("last_name", "")
            row["specialty_context"] = clinician.get("specialty", "")
            row["clinic_name"] = clinician.get("clinic_name", "")
            teams.append(row)
        return teams

    async def join_care_team(self, patient_id: UUID, invite_code: str) -> Any:
        """Join a clinician's care team using an invite code.

        Invite codes are stored in the care_teams table as pending rows
        with a code column. The patient "claims" the row.
        """
        normalized_code = invite_code.strip().upper()

        # Look up invite regardless of status so errors can be precise.
        result = (
            self.db.table("care_teams")
            .select("*")
            .eq("invite_code", normalized_code)
            .single()
            .execute()
        )
        if not result.data:
            raise ValidationError("Invite code is invalid")

        raw_invite = result.data
        if isinstance(raw_invite, list):
            if not raw_invite:
                raise ValidationError("Invite code is invalid")
            invite = cast(dict[str, Any], raw_invite[0])
        else:
            invite = cast(dict[str, Any], raw_invite)

        expires_at = invite.get("invite_expires_at")
        if isinstance(expires_at, str):
            try:
                if datetime.fromisoformat(expires_at.replace("Z", "+00:00")) <= datetime.now(UTC):
                    self.db.table("care_teams").update({"status": "inactive"}).eq(
                        "id", invite["id"]
                    ).execute()
                    raise ValidationError(
                        "Invite code has expired. Request a new active invite code"
                    )
            except ValueError:
                logger.warning(
                    "Invalid invite_expires_at value on care_teams row %s", invite.get("id")
                )

        if invite.get("status") != "pending":
            if invite.get("status") == "active":
                raise ValidationError("Invite code is already active and cannot be reused")
            raise ValidationError("Invite code is no longer active. Request a new code")

        if invite.get("patient_id"):
            raise ValidationError("Invite code has already been claimed")

        existing_link = (
            self.db.table("care_teams")
            .select("id")
            .eq("patient_id", str(patient_id))
            .eq("clinician_id", str(invite["clinician_id"]))
            .eq("status", "active")
            .execute()
        )
        if existing_link.data:
            raise ValidationError("You are already linked to this care team")

        care_team_id = invite["id"]

        # Claim the invite
        updated = (
            self.db.table("care_teams")
            .update(
                {
                    "invite_claimed_at": datetime.now(UTC).isoformat(),
                    "patient_id": str(patient_id),
                    "status": "active",
                }
            )
            .eq("id", care_team_id)
            .execute()
        )
        if not updated.data:
            raise ValidationError("Failed to join care team")

        joined = (
            self.db.table("care_teams")
            .select("*, clinicians(first_name, last_name, specialty, clinic_name)")
            .eq("id", care_team_id)
            .single()
            .execute()
        )
        if not joined.data:
            raise ValidationError("Failed to load care team after joining")

        row = cast(dict[str, Any], joined.data)
        clinician = cast(dict[str, Any], row.pop("clinicians", {}) or {})
        row["clinician_first_name"] = clinician.get("first_name", "")
        row["clinician_last_name"] = clinician.get("last_name", "")
        row["specialty_context"] = clinician.get("specialty", "")
        row["clinic_name"] = clinician.get("clinic_name", "")
        return row
