"""Document extraction candidate registration.

Extraction output is evidence, not clinical truth. This service stores only
pending, provenance-backed candidates; reconciliation owns any later canonical
medication, condition, or allergy change.
"""

from __future__ import annotations

import json
import re
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import ValidationError
from app.models.clinical_fact import ClinicalFactCreate
from app.models.document_extraction import DocumentExtractionResult
from app.services.clinical_fact_service import ClinicalFactService
from app.services.document_service import DocumentService


class DocumentExtractionImportService:
    """Registers normalized document extraction results as patient-scoped candidates."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self.document_service = DocumentService(db)

    async def import_extraction(
        self,
        *,
        patient_id: UUID,
        uploaded_by: UUID,
        uploaded_by_role: str,
        document_id: UUID | None = None,
        extraction: DocumentExtractionResult | None = None,
    ) -> dict[str, Any]:
        if extraction is None:
            raise ValidationError(
                "A verified extraction result is required; demo data is not imported"
            )
        effective_extraction = extraction
        document_payload = effective_extraction.document
        serialized_extraction = effective_extraction.model_dump(mode="json")
        summary = effective_extraction.summary or self._summary(effective_extraction)

        if document_id is None:
            document = await self.document_service.create_document(
                patient_id=patient_id,
                uploaded_by=uploaded_by,
                uploaded_by_role=uploaded_by_role,
                file_name=self._file_name(document_payload.title),
                file_path="",
                file_size_bytes=len(json.dumps(serialized_extraction).encode("utf-8")),
                mime_type="application/json",
                document_type=document_payload.document_type.value,
                source_clinic=document_payload.source_name or "Document extraction import",
                notes=document_payload.notes,
                sign_file_url=False,
            )
            document_id = UUID(str(document["id"]))
        else:
            document = await self.document_service.get_document(document_id, patient_id)

        run_id = self._start_run(document_id=document_id, patient_id=patient_id)
        try:
            clinical_fact_count = self._register_candidate_facts(
                patient_id=patient_id,
                actor_id=uploaded_by,
                document_id=document_id,
                document_title=document_payload.title,
                extraction=effective_extraction,
            )
        except Exception as exc:
            self._finish_run(run_id, status="failed", error=str(exc))
            raise
        self._finish_run(run_id, status="completed", candidate_fact_count=clinical_fact_count)

        self.document_service.update_parse_result(
            document_id=document_id,
            patient_id=patient_id,
            ai_summary=summary,
            parse_status="completed",
            parsed=True,
        )
        document["ai_summary"] = summary
        document["parsed"] = True
        document["parse_status"] = "completed"
        document["parse_error"] = None

        return {
            "document": document,
            "medications_created": 0,
            "conditions_created": 0,
            "allergies_created": 0,
            "obligations_created": 0,
            "clinical_facts_created": clinical_fact_count,
            "summary": summary,
        }

    def _start_run(self, *, document_id: UUID, patient_id: UUID) -> str:
        result = (
            self.db.table("document_ingestion_runs")
            .insert(
                {
                    "document_id": str(document_id),
                    "patient_id": str(patient_id),
                    "status": "processing",
                    "attempt": 1,
                    "extractor_version": "document-extraction-import/1",
                }
            )
            .execute()
        )
        rows = cast(list[dict[str, Any]], result.data or [])
        if not rows or not rows[0].get("id"):
            raise ValidationError("Could not create document ingestion run")
        return str(rows[0]["id"])

    def _finish_run(
        self,
        run_id: str,
        *,
        status: str,
        candidate_fact_count: int = 0,
        error: str | None = None,
    ) -> None:
        self.db.table("document_ingestion_runs").update(
            {
                "status": status,
                "candidate_fact_count": candidate_fact_count,
                "error_message": error,
            }
        ).eq("id", run_id).execute()

    def _register_candidate_facts(
        self,
        *,
        patient_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        document_title: str,
        extraction: DocumentExtractionResult,
    ) -> int:
        """Register extraction output as reviewable candidates, never approved facts."""
        registry = ClinicalFactService(self.db)
        pairs = (
            ("medication", extraction.medications),
            ("condition", extraction.conditions),
            ("allergy", extraction.allergies),
            ("obligation", extraction.obligations),
        )
        created = 0
        for fact_type, extracted_rows in pairs:
            for index, extracted in enumerate(extracted_rows):
                registry.create_candidate(
                    ClinicalFactCreate.model_validate(
                        {
                            "patient_id": str(patient_id),
                            "fact_type": fact_type,
                            "subject_type": fact_type,
                            "value": extracted.model_dump(mode="json"),
                            "external_source_key": f"document/{document_id}/{fact_type}/{index}",
                            "external_source_version": str(document_id),
                            "uncertainty": [
                                "Structured extraction requires clinician review before use as clinical truth."
                            ],
                            "provenance": {
                                "artifact_type": "document",
                                "source_system": "document_extraction",
                                "source_reference": f"document:{document_id}",
                                "document_id": str(document_id),
                                "document_location": {"scope": "document", "title": document_title},
                                "extractor_version": "document-extraction-import/1",
                            },
                            "citations": [
                                {
                                    "excerpt": f"Structured {fact_type} extracted from {document_title}.",
                                    "location": {"scope": "document"},
                                }
                            ],
                        }
                    ),
                    actor_id=actor_id,
                )
                created += 1
        return created

    def _summary(self, extraction: DocumentExtractionResult) -> str:
        title = extraction.document.title
        parts = [f"{title} extracted from a clinical document."]
        if extraction.document.source_name:
            parts.append(f"Source: {extraction.document.source_name}.")
        if extraction.conditions:
            parts.append(
                "Conditions: "
                + ", ".join(condition.name for condition in extraction.conditions)
                + "."
            )
        if extraction.medications:
            parts.append(
                "Medications: "
                + ", ".join(
                    " ".join(
                        part
                        for part in (medication.name, medication.dosage)
                        if part and part != "as directed"
                    )
                    for medication in extraction.medications
                )
                + "."
            )
        if extraction.allergies:
            parts.append(
                "Allergies: "
                + ", ".join(
                    f"{allergy.allergen} ({allergy.reaction})"
                    if allergy.reaction
                    else allergy.allergen
                    for allergy in extraction.allergies
                )
                + "."
            )
        return " ".join(parts)

    def _file_name(self, title: str) -> str:
        safe_title = re.sub(r"[^A-Za-z0-9._ -]+", "", title).strip()
        return f"{safe_title or 'Clinical Document'}.json"
