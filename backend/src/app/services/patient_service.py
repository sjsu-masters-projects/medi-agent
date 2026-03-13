"""Patient service — profile management and care team operations.

Handles:
    - Get/update own patient profile
    - List care team (clinicians assigned to this patient)
    - Join a clinic via invite code
"""

from __future__ import annotations

import logging
from uuid import UUID

from supabase import Client

from app.core.exceptions import NotFoundError, ValidationError

logger = logging.getLogger(__name__)


class PatientService:
    """Patient-scoped operations. All methods require the patient's user ID."""

    def __init__(self, db: Client) -> None:
        self.db = db

    # ── Profile ─────────────────────────────────────────

    async def get_profile(self, patient_id: UUID) -> dict:
        """Fetch the patient's own profile by auth user ID."""
        result = self.db.table("patients").select("*").eq("id", str(patient_id)).single().execute()
        if not result.data:
            raise NotFoundError("Patient", str(patient_id))
        return result.data

    async def update_profile(self, patient_id: UUID, updates: dict) -> dict:
        """Partial update — only non-None fields are sent."""
        # Filter out None values so we don't overwrite with nulls
        clean = {k: v for k, v in updates.items() if v is not None}
        if not clean:
            return await self.get_profile(patient_id)

        result = self.db.table("patients").update(clean).eq("id", str(patient_id)).execute()
        if not result.data:
            raise NotFoundError("Patient", str(patient_id))
        return result.data[0]

    # ── Care Team ───────────────────────────────────────

    async def get_care_team(self, patient_id: UUID) -> list[dict]:
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
        for row in result.data or []:
            clinician = row.pop("clinicians", {}) or {}
            row["clinician_first_name"] = clinician.get("first_name", "")
            row["clinician_last_name"] = clinician.get("last_name", "")
            row["specialty_context"] = clinician.get("specialty", "")
            row["clinic_name"] = clinician.get("clinic_name", "")
            teams.append(row)
        return teams

    async def join_care_team(self, patient_id: UUID, invite_code: str) -> dict:
        """Join a clinician's care team using an invite code.

        Invite codes are stored in the care_teams table as pending rows
        with a code column. The patient "claims" the row.
        """
        # Look up the pending invite
        result = (
            self.db.table("care_teams")
            .select("*")
            .eq("invite_code", invite_code)
            .eq("status", "pending")
            .is_("patient_id", "null")
            .single()
            .execute()
        )
        if not result.data:
            raise ValidationError(f"Invalid or expired invite code: {invite_code}")

        care_team_id = result.data["id"]

        # Claim the invite
        updated = (
            self.db.table("care_teams")
            .update({"patient_id": str(patient_id), "status": "active"})
            .eq("id", care_team_id)
            .execute()
        )
        if not updated.data:
            raise ValidationError("Failed to join care team")
        return updated.data[0]
