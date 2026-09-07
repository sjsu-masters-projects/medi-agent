"""Ingestion service — orchestrates document ingestion via LangGraph."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.agents.ingestion.graph import IngestionState, create_ingestion_graph
from app.core.exceptions import DocumentParseError
from app.models.clinical_fact import (
    ClinicalFactCreate,
    EvidenceCitationCreate,
    SourceArtifactType,
    SourceProvenanceCreate,
)
from app.services.clinical_fact_service import ClinicalFactService

logger = logging.getLogger(__name__)

MAX_PARSE_ATTEMPTS = 3


class IngestionService:
    """Runs the ingestion pipeline for a document."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self._graph = create_ingestion_graph()

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
        source_hash = self._document_content_hash(document_id)
        if source_hash and self._has_completed_source_hash(
            patient_id=patient_id, source_hash=source_hash
        ):
            run_id = self._start_run(
                document_id=document_id,
                patient_id=patient_id,
                attempt=attempts + 1,
                source_hash=source_hash,
                status="duplicate",
            )
            self._finish_run(run_id, status="duplicate")
            self._update_document_status(
                document_id,
                parse_status="completed",
                parse_error=None,
                parsed=True,
            )
            return {
                "status": "duplicate",
                "medications_created": 0,
                "conditions_created": 0,
                "allergies_created": 0,
                "obligations_created": 0,
                "candidate_facts_created": 0,
                "summary_length": 0,
            }
        ingestion_run_id = self._start_run(
            document_id=document_id,
            patient_id=patient_id,
            attempt=attempts + 1,
            source_hash=source_hash,
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
            self._finish_run(ingestion_run_id, status="failed", error=error)
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

        candidate_count = self._register_candidates(
            document_id=document_id,
            patient_id=patient_id,
            normalized_medications=normalized_medications,
            conditions=validated_data.get("conditions", []),
            allergies=validated_data.get("allergies", []),
            follow_up_instructions=extracted_data.get("follow_up_instructions", []),
        )

        summary = str(final_state.get("patient_summary") or "")
        self._update_document_status(
            document_id,
            parse_status="completed",
            parse_error=None,
            parsed=True,
            ai_summary=summary or None,
        )
        self._finish_run(ingestion_run_id, status="completed", candidate_fact_count=candidate_count)

        return {
            "status": "completed",
            "medications_created": 0,
            "conditions_created": 0,
            "allergies_created": 0,
            "obligations_created": 0,
            "candidate_facts_created": candidate_count,
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

    def _register_candidates(
        self,
        *,
        document_id: UUID,
        patient_id: UUID,
        normalized_medications: list[dict[str, Any]],
        conditions: list[dict[str, Any]],
        allergies: list[dict[str, Any]],
        follow_up_instructions: list[dict[str, Any]],
    ) -> int:
        """Save extraction output only as pending, source-cited candidates."""
        document = cast(
            dict[str, Any],
            self.db.table("documents")
            .select("uploaded_by, file_name")
            .eq("id", str(document_id))
            .single()
            .execute()
            .data
            or {},
        )
        actor_id = UUID(str(document.get("uploaded_by") or patient_id))
        rows = (
            ("medication", normalized_medications),
            ("condition", conditions),
            ("allergy", allergies),
            ("obligation", follow_up_instructions),
        )
        facts = ClinicalFactService(self.db)
        created = 0
        for fact_type, values in rows:
            for index, value in enumerate(values):
                if not isinstance(value, dict) or not value:
                    continue
                facts.create_candidate(
                    ClinicalFactCreate(
                        patient_id=patient_id,
                        fact_type=fact_type,
                        subject_type=fact_type,
                        value=value,
                        uncertainty=[
                            "Document extraction requires clinician review before clinical use."
                        ],
                        external_source_key=f"document/{document_id}/{fact_type}/{index}",
                        external_source_version=str(document_id),
                        provenance=SourceProvenanceCreate(
                            artifact_type=SourceArtifactType.DOCUMENT,
                            source_system="document_ingestion",
                            source_reference=f"document:{document_id}",
                            document_id=document_id,
                            document_location={"scope": "document", "index": index},
                            extractor_version="ingestion-graph/1",
                        ),
                        citations=[
                            EvidenceCitationCreate(
                                excerpt=f"Extracted {fact_type} candidate from "
                                f"{document.get('file_name') or 'clinical document'}.",
                                location={"scope": "document", "index": index},
                            )
                        ],
                    ),
                    actor_id=actor_id,
                )
                created += 1
        return created

    def _document_content_hash(self, document_id: UUID) -> str | None:
        result = (
            self.db.table("documents")
            .select("content_hash")
            .eq("id", str(document_id))
            .single()
            .execute()
        )
        data = cast(dict[str, Any], result.data or {})
        source_hash = data.get("content_hash")
        return source_hash if isinstance(source_hash, str) and source_hash else None

    def _has_completed_source_hash(self, *, patient_id: UUID, source_hash: str) -> bool:
        result = (
            self.db.table("document_ingestion_runs")
            .select("id")
            .eq("patient_id", str(patient_id))
            .eq("source_hash", source_hash)
            .eq("status", "completed")
            .execute()
        )
        return bool(result.data)

    def _start_run(
        self,
        *,
        document_id: UUID,
        patient_id: UUID,
        attempt: int,
        source_hash: str | None = None,
        status: str = "processing",
    ) -> str:
        result = (
            self.db.table("document_ingestion_runs")
            .insert(
                {
                    "document_id": str(document_id),
                    "patient_id": str(patient_id),
                    "status": status,
                    "attempt": attempt,
                    "source_hash": source_hash,
                    "extractor_version": "ingestion-graph/1",
                }
            )
            .execute()
        )
        rows = cast(list[dict[str, Any]], result.data or [])
        if not rows:
            raise DocumentParseError(str(document_id), "Could not create ingestion run")
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
                "completed_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", run_id).execute()
