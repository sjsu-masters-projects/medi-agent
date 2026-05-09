"""Ingestion service — orchestrates document ingestion via LangGraph."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.agents.ingestion.graph import IngestionState, create_ingestion_graph
from app.core.exceptions import DocumentParseError
from app.services.medication_service import MedicationService
from app.services.obligation_service import ObligationService

logger = logging.getLogger(__name__)

MAX_PARSE_ATTEMPTS = 3


class IngestionService:
    """Runs the ingestion pipeline for a document."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self._graph = create_ingestion_graph()
        self._med_service = MedicationService(db)
        self._obligation_service = ObligationService(db)

    async def ingest_document(
        self,
        document_id: UUID,
        patient_id: UUID,
        file_path: str,
        document_type: str,
    ) -> dict[str, Any]:
        """Run the full ingestion pipeline for a document."""
        attempts = self._get_parse_attempts(document_id)
        if attempts >= MAX_PARSE_ATTEMPTS:
            message = f"Maximum parse attempts ({MAX_PARSE_ATTEMPTS}) exceeded"
            self._update_document_status(
                document_id,
                parse_status="failed",
                parse_error=message,
                parsed=False,
            )
            raise DocumentParseError(str(document_id), message)

        self._update_document_status(
            document_id,
            parse_status="processing",
            parse_error=None,
            parsed=False,
            parse_attempts=attempts + 1,
        )

        initial_state: IngestionState = {
            "document_id": str(document_id),
            "file_url": file_path,
            "document_type": document_type,
            "patient_id": str(patient_id),
            "raw_content": None,
            "extracted_data": None,
            "validated_data": None,
            "validation_errors": None,
            "normalized_medications": None,
            "saved_ids": None,
            "patient_summary": None,
            "created_tasks": None,
            "error": None,
            "retry_count": attempts,
            "messages": [],
        }

        final_state = cast(IngestionState, await self._graph.ainvoke(initial_state))
        if final_state.get("error"):
            error = str(final_state["error"])
            self._update_document_status(
                document_id,
                parse_status="failed",
                parse_error=error,
                parsed=False,
            )
            latest_attempts = attempts + 1
            if latest_attempts >= MAX_PARSE_ATTEMPTS:
                raise DocumentParseError(str(document_id), error)
            return {
                "status": "failed",
                "medications_created": 0,
                "obligations_created": 0,
                "summary_length": 0,
                "error": error,
            }

        validated_data = final_state.get("validated_data") or {}
        extracted_data = final_state.get("extracted_data") or {}
        normalized_medications = final_state.get("normalized_medications") or []

        medication_ids = await self._save_medications(
            patient_id,
            document_id,
            normalized_medications,
        )
        condition_ids = await self._save_conditions(
            patient_id,
            validated_data.get("conditions", []),
        )
        allergy_ids = await self._save_allergies(
            patient_id,
            validated_data.get("allergies", []),
        )
        obligation_ids = await self._save_obligations(
            patient_id,
            document_id,
            extracted_data.get("follow_up_instructions", []),
        )

        final_state["saved_ids"] = {
            "medications": medication_ids,
            "conditions": condition_ids,
            "allergies": allergy_ids,
            "obligations": obligation_ids,
        }

        summary = str(final_state.get("patient_summary") or "")
        self._update_document_status(
            document_id,
            parse_status="completed",
            parse_error=None,
            parsed=True,
            ai_summary=summary or None,
        )

        return {
            "status": "completed",
            "medications_created": len(medication_ids),
            "conditions_created": len(condition_ids),
            "allergies_created": len(allergy_ids),
            "obligations_created": len(obligation_ids),
            "summary_length": len(summary),
        }

    def _get_parse_attempts(self, document_id: UUID) -> int:
        """Read the current parse attempt count for a document."""
        result = (
            self.db.table("documents")
            .select("parse_attempts")
            .eq("id", str(document_id))
            .single()
            .execute()
        )
        data = cast(dict[str, Any], result.data or {})
        return int(data.get("parse_attempts") or 0)

    def _update_document_status(
        self,
        document_id: UUID,
        *,
        parse_status: str,
        parse_error: str | None = None,
        parsed: bool | None = None,
        ai_summary: str | None = None,
        parse_attempts: int | None = None,
    ) -> None:
        """Update document parsing status in DB."""
        payload: dict[str, Any] = {
            "parse_status": parse_status,
            "parse_error": parse_error,
        }
        if parsed is not None:
            payload["parsed"] = parsed
        if ai_summary is not None:
            payload["ai_summary"] = ai_summary
        if parse_attempts is not None:
            payload["parse_attempts"] = parse_attempts

        self.db.table("documents").update(payload).eq("id", str(document_id)).execute()

    async def _save_medications(
        self,
        patient_id: UUID,
        document_id: UUID,
        normalized_medications: list[dict[str, Any]],
    ) -> list[str]:
        """Save normalized medications to DB via MedicationService."""
        created_ids: list[str] = []
        for medication in normalized_medications:
            payload = {
                "name": medication.get("name")
                or medication.get("generic_name")
                or "Unknown medication",
                "generic_name": medication.get("generic_name"),
                "rxcui": medication.get("rxcui"),
                "dosage": medication.get("dosage")
                or medication.get("parsed_dosage", {}).get("raw")
                or "unspecified",
                "frequency": medication.get("frequency")
                or medication.get("normalized_frequency")
                or "as directed",
                "route": medication.get("route") or "oral",
                "instructions": medication.get("instructions"),
                "source_document_id": str(document_id),
            }
            created = await self._med_service.create_medication(patient_id, payload)
            created_ids.append(str(created["id"]))
        return created_ids

    async def _save_obligations(
        self,
        patient_id: UUID,
        document_id: UUID,
        follow_up_instructions: list[dict[str, Any]],
    ) -> list[str]:
        """Save follow-up instructions as obligations via ObligationService."""
        created_ids: list[str] = []
        for instruction in follow_up_instructions:
            description = str(instruction.get("description") or "").strip()
            if not description:
                continue
            payload = {
                "obligation_type": self._detect_obligation_type(description),
                "description": description,
                "frequency": instruction.get("timing")
                or instruction.get("frequency")
                or "as directed",
                "source_document_id": str(document_id),
            }
            created = await self._obligation_service.create_obligation(patient_id, payload)
            created_ids.append(str(created["id"]))
        return created_ids

    async def _save_conditions(
        self,
        patient_id: UUID,
        conditions: list[dict[str, Any]],
    ) -> list[str]:
        """Persist validated conditions directly to the conditions table."""
        return await asyncio.to_thread(self._insert_conditions, patient_id, conditions)

    def _insert_conditions(
        self,
        patient_id: UUID,
        conditions: list[dict[str, Any]],
    ) -> list[str]:
        """Persist validated conditions directly to the conditions table."""
        created_ids: list[str] = []
        for condition in conditions:
            result = (
                self.db.table("conditions")
                .insert(
                    {
                        "patient_id": str(patient_id),
                        "name": condition.get("name"),
                        "status": condition.get("status") or "active",
                        "notes": condition.get("notes"),
                    }
                )
                .execute()
            )
            data = cast(list[dict[str, Any]], result.data or [])
            if data:
                created_ids.append(str(data[0]["id"]))
        return created_ids

    async def _save_allergies(
        self,
        patient_id: UUID,
        allergies: list[dict[str, Any]],
    ) -> list[str]:
        """Persist validated allergies directly to the allergies table."""
        return await asyncio.to_thread(self._insert_allergies, patient_id, allergies)

    def _insert_allergies(
        self,
        patient_id: UUID,
        allergies: list[dict[str, Any]],
    ) -> list[str]:
        """Persist validated allergies directly to the allergies table."""
        created_ids: list[str] = []
        for allergy in allergies:
            result = (
                self.db.table("allergies")
                .insert(
                    {
                        "patient_id": str(patient_id),
                        "allergen": allergy.get("allergen"),
                        "reaction": allergy.get("reaction"),
                        "severity": allergy.get("severity") or "moderate",
                    }
                )
                .execute()
            )
            data = cast(list[dict[str, Any]], result.data or [])
            if data:
                created_ids.append(str(data[0]["id"]))
        return created_ids

    def _detect_obligation_type(self, description: str) -> str:
        """Infer obligation type from the free-text follow-up instruction."""
        normalized = description.lower()
        if any(token in normalized for token in ("diet", "sodium", "nutrition", "eat", "meal")):
            return "diet"
        if any(
            token in normalized for token in ("walk", "exercise", "activity", "stretch", "physical")
        ):
            return "exercise"
        return "custom"
