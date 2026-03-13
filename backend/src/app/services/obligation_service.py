"""Obligation service — CRUD for clinician-set obligations.

Obligations are tasks a clinician assigns to a patient:
    - Exercise routines ("walk 30 min daily")
    - Dietary rules ("low sodium diet")
    - Monitoring tasks ("check blood pressure twice daily")

All operations are scoped to a patient_id.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from supabase import Client

from app.core.exceptions import NotFoundError

logger = logging.getLogger(__name__)


class ObligationService:
    """Patient-scoped obligation operations."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def list_obligations(self, patient_id: UUID, active_only: bool = True) -> Any:
        """List obligations for a patient."""
        query = (
            self.db.table("obligations")
            .select("*")
            .eq("patient_id", str(patient_id))
            .order("created_at", desc=True)
        )
        if active_only:
            query = query.eq("is_active", True)
        result = query.execute()
        return result.data or []

    async def create_obligation(self, patient_id: UUID, data: dict[str, Any]) -> Any:
        """Create a new obligation for a patient."""
        row = {"patient_id": str(patient_id), **data}
        result = self.db.table("obligations").insert(row).execute()
        if not result.data:
            raise Exception("Failed to create obligation")
        return result.data[0]

    async def update_obligation(
        self, obligation_id: UUID, patient_id: UUID, updates: dict[str, Any]
    ) -> Any:
        """Update an obligation — partial update."""
        clean = {k: v for k, v in updates.items() if v is not None}
        if not clean:
            return await self._get(obligation_id, patient_id)

        result = (
            self.db.table("obligations")
            .update(clean)
            .eq("id", str(obligation_id))
            .eq("patient_id", str(patient_id))
            .execute()
        )
        if not result.data:
            raise NotFoundError("Obligation", str(obligation_id))
        return result.data[0]

    async def _get(self, obligation_id: UUID, patient_id: UUID) -> Any:
        result = (
            self.db.table("obligations")
            .select("*")
            .eq("id", str(obligation_id))
            .eq("patient_id", str(patient_id))
            .single()
            .execute()
        )
        if not result.data:
            raise NotFoundError("Obligation", str(obligation_id))
        return result.data
