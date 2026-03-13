"""Clinician service — profile, patient list, invite codes.

Handles:
    - Get own clinician profile
    - List assigned patients (via care_teams junction)
    - Get full detail for a specific patient
    - Generate invite codes for patients to join
"""

from __future__ import annotations

import logging
import secrets
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import AuthorizationError, NotFoundError

logger = logging.getLogger(__name__)


class ClinicianService:
    """Clinician-scoped operations. All methods require the clinician's user ID."""

    def __init__(self, db: Client) -> None:
        self.db = db

    # ── Profile ─────────────────────────────────────────

    async def get_profile(self, clinician_id: UUID) -> Any:
        """Fetch the clinician's own profile."""
        result = (
            self.db.table("clinicians").select("*").eq("id", str(clinician_id)).single().execute()
        )
        if not result.data:
            raise NotFoundError("Clinician", str(clinician_id))
        return result.data

    # ── Patient List ────────────────────────────────────

    async def get_patients(self, clinician_id: UUID) -> Any:
        """List all patients assigned to this clinician via active care teams."""
        result = (
            self.db.table("care_teams")
            .select("*, patients(id, email, first_name, last_name, date_of_birth, avatar_url)")
            .eq("clinician_id", str(clinician_id))
            .eq("status", "active")
            .execute()
        )
        # Flatten — pull patient data up to top level
        patients = []
        for row in cast(list[dict[str, Any]], result.data or []):
            patient = cast(dict[str, Any], row.pop("patients", {}) or {})
            if patient:
                patient["care_team_id"] = row["id"]
                patient["role"] = row.get("role", "")
                patients.append(patient)
        return patients

    async def get_patient_detail(self, clinician_id: UUID, patient_id: UUID) -> Any:
        """Get full patient profile — only if clinician is assigned.

        Security: checks the care_teams junction table to ensure
        the clinician has an active relationship with this patient.
        """
        # Verify assignment
        assignment = (
            self.db.table("care_teams")
            .select("id")
            .eq("clinician_id", str(clinician_id))
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
            .execute()
        )
        if not assignment.data:
            raise AuthorizationError("You are not assigned to this patient")

        # Fetch full patient profile
        result = self.db.table("patients").select("*").eq("id", str(patient_id)).single().execute()
        if not result.data:
            raise NotFoundError("Patient", str(patient_id))
        return result.data

    # ── Invite Codes ────────────────────────────────────

    async def generate_invite_code(self, clinician_id: UUID) -> Any:
        """Create a pending care_team row with a unique invite code.

        The patient uses this code via POST /patients/me/care-team/join.
        Codes are 8-char uppercase alphanumeric for easy sharing.
        """
        code = secrets.token_hex(4).upper()  # e.g. "A1B2C3D4"

        result = (
            self.db.table("care_teams")
            .insert(
                {
                    "clinician_id": str(clinician_id),
                    "invite_code": code,
                    "status": "pending",
                    "role": "provider",
                }
            )
            .execute()
        )
        if not result.data:
            raise Exception("Failed to generate invite code")

        return {
            "invite_code": code,
            "care_team_id": cast(list[dict[str, Any]], result.data)[0]["id"],
        }
