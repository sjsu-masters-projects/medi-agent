"""Medication service — CRUD for patient medications.

Medications can be created by:
    - AI ingestion agent (from parsed documents)
    - Clinicians (manual entry)
    - Patients (self-reported)

All operations are scoped to a patient_id.
"""

from __future__ import annotations

import logging
from uuid import UUID

from supabase import Client

from app.core.exceptions import NotFoundError

logger = logging.getLogger(__name__)


class MedicationService:
    """Patient-scoped medication operations."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def list_medications(self, patient_id: UUID, active_only: bool = True) -> list[dict]:
        """List medications for a patient, optionally filtered to active only."""
        query = (
            self.db.table("medications")
            .select("*")
            .eq("patient_id", str(patient_id))
            .order("created_at", desc=True)
        )
        if active_only:
            query = query.eq("is_active", True)
        result = query.execute()
        return result.data or []

    async def create_medication(self, patient_id: UUID, data: dict) -> dict:
        """Create a new medication for a patient."""
        row = {"patient_id": str(patient_id), **data}
        result = self.db.table("medications").insert(row).execute()
        if not result.data:
            raise Exception("Failed to create medication")
        return result.data[0]

    async def update_medication(self, medication_id: UUID, patient_id: UUID, updates: dict) -> dict:
        """Update a medication — only non-None fields are applied."""
        clean = {k: v for k, v in updates.items() if v is not None}
        if not clean:
            return await self._get(medication_id, patient_id)

        result = (
            self.db.table("medications")
            .update(clean)
            .eq("id", str(medication_id))
            .eq("patient_id", str(patient_id))
            .execute()
        )
        if not result.data:
            raise NotFoundError("Medication", str(medication_id))
        return result.data[0]

    async def _get(self, medication_id: UUID, patient_id: UUID) -> dict:
        """Internal — fetch a single medication."""
        result = (
            self.db.table("medications")
            .select("*")
            .eq("id", str(medication_id))
            .eq("patient_id", str(patient_id))
            .single()
            .execute()
        )
        if not result.data:
            raise NotFoundError("Medication", str(medication_id))
        return result.data
