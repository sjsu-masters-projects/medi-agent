"""Document extraction import service.

Persists a project-owned extraction result into the same document, medication,
condition, allergy, and obligation tables that power the Today feed.
"""

from __future__ import annotations

import json
import re
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.models.document_extraction import DocumentExtractionResult
from app.models.enums import DocumentType, MedicationRoute, ObligationType
from app.services.document_service import DocumentService
from app.services.medication_service import MedicationService
from app.services.obligation_service import ObligationService

DEMO_DOCUMENT_EXTRACTION = DocumentExtractionResult.model_validate(
    {
        "document": {
            "title": "Discharge Summary",
            "document_type": DocumentType.DISCHARGE_SUMMARY.value,
            "source_name": "Dr Adam Careful",
            "notes": "Imported from a normalized document extraction demo.",
        },
        "summary": (
            "Discharge Summary extracted from a clinical document. "
            "Author: Dr Adam Careful. Reason for admission: Acute Asthmatic attack. "
            "Was wheezing for days prior to admission. Discharge medications: "
            "Theophylline 200mg, Ventolin Inhaler. Known allergies: Doxycycline (Hives)."
        ),
        "medications": [
            {
                "name": "Theophylline",
                "dosage": "200mg",
                "frequency": "twice daily",
                "route": MedicationRoute.ORAL.value,
                "instructions": "Take with Food",
            },
            {
                "name": "Ventolin Inhaler",
                "dosage": "as directed",
                "frequency": "as directed",
                "route": MedicationRoute.INHALED.value,
                "instructions": "Management of Asthma",
            },
        ],
        "conditions": [
            {
                "name": "Asthma exacerbation",
                "status": "active",
                "notes": "Acute Asthmatic attack. Was wheezing for days prior to admission.",
            }
        ],
        "allergies": [
            {
                "allergen": "Doxycycline",
                "reaction": "Hives",
                "severity": "severe",
            }
        ],
        "obligations": [
            {
                "description": "Review discharge instructions from Discharge Summary",
                "frequency": "today",
                "obligation_type": ObligationType.CUSTOM.value,
            }
        ],
    }
)


class DocumentExtractionImportService:
    """Imports normalized document extraction results into patient-scoped records."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self.document_service = DocumentService(db)
        self.medication_service = MedicationService(db)
        self.obligation_service = ObligationService(db)

    async def import_extraction(
        self,
        *,
        patient_id: UUID,
        uploaded_by: UUID,
        uploaded_by_role: str,
        extraction: DocumentExtractionResult | None = None,
    ) -> dict[str, Any]:
        effective_extraction = extraction or DEMO_DOCUMENT_EXTRACTION
        document_payload = effective_extraction.document
        serialized_extraction = effective_extraction.model_dump(mode="json")
        summary = effective_extraction.summary or self._summary(effective_extraction)

        document = await self.document_service.create_document(
            patient_id=patient_id,
            uploaded_by=uploaded_by,
            uploaded_by_role=uploaded_by_role,
            file_name=self._file_name(document_payload.title),
            file_path="",
            file_size_bytes=len(json.dumps(serialized_extraction).encode("utf-8")),
            mime_type="application/json",
            document_type=document_payload.document_type.value,
            source_clinic=document_payload.source_name or "Document extraction demo",
            notes=document_payload.notes,
            sign_file_url=False,
        )
        document_id = UUID(str(document["id"]))

        medication_ids = await self._create_medications(
            patient_id,
            document_id,
            effective_extraction,
        )
        condition_ids = self._create_conditions(patient_id, effective_extraction)
        allergy_ids = self._create_allergies(patient_id, effective_extraction)
        obligation_ids = await self._create_obligations(patient_id, effective_extraction)

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
            "medications_created": len(medication_ids),
            "conditions_created": len(condition_ids),
            "allergies_created": len(allergy_ids),
            "obligations_created": len(obligation_ids),
            "summary": summary,
        }

    async def _create_medications(
        self,
        patient_id: UUID,
        document_id: UUID,
        extraction: DocumentExtractionResult,
    ) -> list[str]:
        created_ids: list[str] = []
        seen_names: set[str] = set()

        for medication in extraction.medications:
            dedupe_key = medication.name.strip().lower()
            if dedupe_key in seen_names:
                continue
            seen_names.add(dedupe_key)
            payload = {
                "name": medication.name,
                "generic_name": medication.generic_name,
                "rxcui": medication.rxcui,
                "dosage": medication.dosage,
                "frequency": medication.frequency,
                "route": medication.route.value,
                "instructions": medication.instructions,
                "source_document_id": str(document_id),
            }
            created = await self.medication_service.create_medication(patient_id, payload)
            created_ids.append(str(created["id"]))

        return created_ids

    def _create_conditions(
        self,
        patient_id: UUID,
        extraction: DocumentExtractionResult,
    ) -> list[str]:
        created_ids: list[str] = []

        for condition in extraction.conditions:
            result = (
                self.db.table("conditions")
                .insert(
                    {
                        "patient_id": str(patient_id),
                        "name": condition.name,
                        "status": condition.status,
                        "notes": condition.notes,
                    }
                )
                .execute()
            )
            data = cast(list[dict[str, Any]], result.data or [])
            if data:
                created_ids.append(str(data[0]["id"]))

        return created_ids

    def _create_allergies(
        self,
        patient_id: UUID,
        extraction: DocumentExtractionResult,
    ) -> list[str]:
        created_ids: list[str] = []

        for allergy in extraction.allergies:
            result = (
                self.db.table("allergies")
                .insert(
                    {
                        "patient_id": str(patient_id),
                        "allergen": allergy.allergen,
                        "reaction": allergy.reaction,
                        "severity": allergy.severity,
                    }
                )
                .execute()
            )
            data = cast(list[dict[str, Any]], result.data or [])
            if data:
                created_ids.append(str(data[0]["id"]))

        return created_ids

    async def _create_obligations(
        self,
        patient_id: UUID,
        extraction: DocumentExtractionResult,
    ) -> list[str]:
        created_ids: list[str] = []

        for obligation in extraction.obligations:
            payload = {
                "obligation_type": obligation.obligation_type.value,
                "description": obligation.description,
                "frequency": obligation.frequency,
            }
            created = await self.obligation_service.create_obligation(patient_id, payload)
            created_ids.append(str(created["id"]))

        return created_ids

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
