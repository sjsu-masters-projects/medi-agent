"""Document extraction candidate registration.

Extraction output is evidence, not clinical truth. Direct import of client-supplied
extraction JSON is disabled; worker ingestion derives provenance-backed candidates
from the stored document, and reconciliation owns any later canonical medication,
condition, or allergy change.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from supabase import Client

from app.core.exceptions import ValidationError
from app.models.document_extraction import DocumentExtractionResult


class DocumentExtractionImportService:
    """Rejects direct extraction imports so evidence always comes from worker ingestion."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def import_extraction(
        self,
        *,
        patient_id: UUID,
        uploaded_by: UUID,
        uploaded_by_role: str,
        document_id: UUID | None = None,
        extraction: DocumentExtractionResult | None = None,
    ) -> dict[str, Any]:
        # JSON supplied by a client has no independently verified source bytes or
        # page geometry. Keeping this compatibility method writable would let a
        # caller manufacture a clinical candidate with an arbitrary citation.
        # Worker ingestion is the only supported route because it derives evidence
        # from the stored document before model output is considered.
        raise ValidationError(
            "Direct extraction import is disabled; upload the source document for worker ingestion"
        )
