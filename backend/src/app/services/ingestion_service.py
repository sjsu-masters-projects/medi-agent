"""Durable, candidate-only document ingestion.

The request path only records a pending document. A worker claims that row and
uses deterministic document intelligence before a model sees any text. Clinical
candidates are created only through the grounding service, which requires page
text and coordinates for the extracted value.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from supabase import Client

from app.agents.ingestion.prompts import (
    EXTRACT_CONTENT_SYSTEM,
    EXTRACT_CONTENT_USER,
    GENERATE_SUMMARY_SYSTEM,
    GENERATE_SUMMARY_USER,
)
from app.clients.model_router import TaskType, get_router
from app.core.exceptions import DocumentParseError
from app.models.document_extraction import DocumentExtractionResult
from app.services.document_intelligence.grounding import (
    DocumentEvidenceCandidateService,
    items_from_extraction_result,
)
from app.services.document_intelligence.models import (
    DocumentExtraction,
    ExtractionMethod,
    ExtractionRoute,
)
from app.services.document_intelligence.pipeline import DocumentIntelligenceService
from app.services.document_preview_service import DocumentPreviewService
from app.services.explanation_service import normalize_patient_summary

logger = logging.getLogger(__name__)

MAX_PARSE_ATTEMPTS = 3


class IngestionService:
    """Process one claimed document outside the API request lifecycle."""

    def __init__(
        self,
        db: Client,
        *,
        intelligence: DocumentIntelligenceService | None = None,
    ) -> None:
        self.db = db
        self._intelligence = intelligence or DocumentIntelligenceService()

    async def ingest_document(
        self,
        document_id: UUID,
        patient_id: UUID,
        file_path: str | None = None,
        document_type: str | None = None,
        *,
        actor_id: UUID | None = None,
        is_retry: bool = False,
        claim: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Claim (when needed), process, and record one terminal ingestion result."""
        claim = claim or self._claim(document_id, patient_id, actor_id=actor_id, is_retry=is_retry)
        run_id = str(claim["run_id"])
        attempt = int(claim["attempt"])
        file_path = str(claim.get("file_path") or file_path or "")
        mime_type = str(claim.get("mime_type") or "application/octet-stream")
        source_hash = claim.get("content_hash")

        if source_hash and self._has_completed_source_hash(
            patient_id=patient_id, source_hash=str(source_hash)
        ):
            self._finish(run_id, status="duplicate")
            self._set_document(document_id, parse_status="completed", parsed=True)
            return self._outcome("duplicate")

        try:
            content = self.db.storage.from_("documents").download(file_path)
            self._ensure_source_preview(
                document_id=document_id,
                patient_id=patient_id,
                content=content,
                mime_type=mime_type,
                source_hash=str(source_hash) if source_hash else None,
            )
            extraction = self._intelligence.extract(
                content, mime_type=mime_type, file_name=str(claim.get("file_name") or "")
            )
        except Exception as exc:  # noqa: BLE001 - details stay server-side
            logger.exception("Could not read document %s", document_id)
            return self._finish_failed(
                document_id,
                run_id,
                attempt,
                detail=str(exc),
                warnings=[],
                page_count=0,
                text_chars=0,
                extraction_method=None,
            )

        warnings = self._warnings(extraction)
        page_count = extraction.page_count
        model_text = extraction.text_for_model()
        text_chars = len(model_text)
        method = self._extraction_method(extraction)

        terminal_status = self._route_terminal_status(extraction)
        if terminal_status is not None:
            failure_code = "needs_ocr" if terminal_status == "needs_ocr" else "source_unreadable"
            if terminal_status == "needs_evidence_review":
                failure_code = "evidence_not_grounded"
            self._set_document(
                document_id,
                parse_status=terminal_status,
                parse_failure_code=failure_code,
                parsed=False,
            )
            self._finish(
                run_id,
                status=terminal_status,
                failure_code=failure_code,
                warnings=warnings,
                page_count=page_count,
                text_chars=text_chars,
                extraction_method=method,
            )
            return self._outcome(terminal_status, error_code=failure_code)

        try:
            extraction_result, model_version = await self._extract_structured(model_text)
        except (PydanticValidationError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Document model output needs review for %s: %s", document_id, exc)
            return self._finish_unvalidated_model_output(
                document_id,
                run_id,
                warnings=warnings,
                page_count=page_count,
                text_chars=text_chars,
                extraction_method=method,
            )
        except Exception as exc:  # noqa: BLE001 - classified before becoming client-visible
            logger.exception("Document model extraction failed for %s", document_id)
            return self._finish_failed(
                document_id,
                run_id,
                attempt,
                detail=str(exc),
                warnings=warnings,
                page_count=page_count,
                text_chars=text_chars,
                extraction_method=method,
            )

        items = items_from_extraction_result(extraction_result)
        try:
            registered = DocumentEvidenceCandidateService(self.db).register(
                patient_id=patient_id,
                actor_id=self._document_actor(document_id, patient_id),
                document_id=document_id,
                extraction=extraction,
                items=items,
                model_version=model_version,
            )
        except Exception as exc:  # noqa: BLE001 - do not strand a claimed row in processing
            logger.exception("Could not register document candidates for %s", document_id)
            return self._finish_failed(
                document_id,
                run_id,
                attempt,
                detail=str(exc),
                warnings=warnings,
                page_count=page_count,
                text_chars=text_chars,
                extraction_method=method,
            )
        if items and not registered.created:
            warnings.append("No proposed value had a verifiable source anchor.")
            self._set_document(
                document_id,
                parse_status="needs_evidence_review",
                parse_failure_code="evidence_not_grounded",
                parsed=False,
            )
            self._finish(
                run_id,
                status="needs_evidence_review",
                failure_code="evidence_not_grounded",
                warnings=warnings,
                page_count=page_count,
                text_chars=text_chars,
                extraction_method=method,
            )
            return self._outcome("needs_evidence_review", error_code="evidence_not_grounded")

        summary = await self._optional_summary(extraction_result)
        if summary is None:
            warnings.append("Optional patient summary was unavailable.")
        self._set_document(
            document_id,
            parse_status="completed",
            parsed=True,
            ai_summary=summary,
        )
        self._finish(
            run_id,
            status="completed",
            candidate_fact_count=registered.created,
            warnings=warnings,
            page_count=page_count,
            text_chars=text_chars,
            extraction_method=method,
        )
        return self._outcome(
            "completed",
            candidate_count=registered.created,
            summary_length=len(summary or ""),
        )

    async def _extract_structured(
        self, model_text: str
    ) -> tuple[DocumentExtractionResult, str | None]:
        response, telemetry = await get_router().generate_text_with_telemetry(
            TaskType.DOCUMENT_PARSING,
            prompt=EXTRACT_CONTENT_USER.format(raw_content=model_text),
            system_instruction=EXTRACT_CONTENT_SYSTEM,
            temperature=0.1,
            max_tokens=2048,
        )
        return DocumentExtractionResult.model_validate(self._parse_json(response)), telemetry.model

    def _finish_unvalidated_model_output(
        self,
        document_id: UUID,
        run_id: str,
        *,
        warnings: list[str],
        page_count: int,
        text_chars: int,
        extraction_method: str | None,
    ) -> dict[str, Any]:
        """Stop unsafe model output without spending another retry on the same source."""
        warning = "Model output could not be safely normalized; clinician review is required."
        self._set_document(
            document_id,
            parse_status="needs_evidence_review",
            parse_failure_code="invalid_model_response",
            parsed=False,
        )
        self._finish(
            run_id,
            status="needs_evidence_review",
            failure_code="invalid_model_response",
            warnings=[*warnings, warning],
            page_count=page_count,
            text_chars=text_chars,
            extraction_method=extraction_method,
        )
        return self._outcome("needs_evidence_review", error_code="invalid_model_response")

    async def _optional_summary(self, extraction: DocumentExtractionResult) -> str | None:
        try:
            summary = await get_router().generate_text(
                TaskType.PATIENT_EXPLANATION,
                prompt=GENERATE_SUMMARY_USER.format(
                    medications=json.dumps(
                        [item.model_dump(exclude={"evidence"}) for item in extraction.medications]
                    ),
                    conditions=json.dumps(
                        [item.model_dump(exclude={"evidence"}) for item in extraction.conditions]
                    ),
                    follow_up_instructions=json.dumps(
                        [item.model_dump(exclude={"evidence"}) for item in extraction.obligations]
                    ),
                ),
                system_instruction=GENERATE_SUMMARY_SYSTEM,
                temperature=0.2,
                # Gemini's reasoning tokens share this ceiling. 1024 avoids a second
                # request for the intentionally short (<180 word) patient explanation.
                max_tokens=1024,
            )
            return normalize_patient_summary(summary) or None
        except Exception as exc:  # noqa: BLE001 - summary is never a safety boundary
            logger.warning("Optional document summary failed: %s", type(exc).__name__)
            return None

    def _claim(
        self, document_id: UUID, patient_id: UUID, *, actor_id: UUID | None, is_retry: bool
    ) -> dict[str, Any]:
        result = self.db.rpc(
            "claim_document_ingestion",
            {
                "p_document_id": str(document_id),
                "p_patient_id": str(patient_id),
                "p_actor_id": str(actor_id) if actor_id else None,
                "p_is_retry": is_retry,
            },
        ).execute()
        data = cast(dict[str, Any], result.data or {})
        if not data.get("run_id"):
            raise DocumentParseError(str(document_id), "Could not claim document ingestion")
        return data

    def _document_actor(self, document_id: UUID, patient_id: UUID) -> UUID:
        result = (
            self.db.table("documents")
            .select("uploaded_by")
            .eq("id", str(document_id))
            .single()
            .execute()
        )
        row = cast(dict[str, Any], result.data or {})
        return UUID(str(row.get("uploaded_by") or patient_id))

    def _set_document(
        self,
        document_id: UUID,
        *,
        parse_status: str,
        parse_failure_code: str | None = None,
        parsed: bool,
        ai_summary: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "parse_status": parse_status,
            "parse_error": None,
            "parse_failure_code": parse_failure_code,
            "parsed": parsed,
        }
        if ai_summary is not None:
            payload["ai_summary"] = ai_summary
        self.db.table("documents").update(payload).eq("id", str(document_id)).execute()

    def _ensure_source_preview(
        self,
        *,
        document_id: UUID,
        patient_id: UUID,
        content: bytes,
        mime_type: str,
        source_hash: str | None,
    ) -> None:
        """Create a derived TIFF preview without making preview failure clinical failure."""
        if mime_type != "image/tiff":
            return
        try:
            preview = DocumentPreviewService().create_tiff_pdf_preview(content)
            # The content hash identifies the immutable source. Computing it directly
            # avoids running a second OCR pass merely to name a derived preview.
            version = source_hash or hashlib.sha256(content).hexdigest()
            preview_path = f"{patient_id}/previews/{document_id}/{version}.pdf"
            self.db.storage.from_("documents").upload(
                path=preview_path,
                file=preview.content,
                file_options={
                    "cache-control": "3600",
                    "content-type": preview.mime_type,
                    "upsert": "true",
                },
            )
            self.db.table("documents").update(
                {
                    "preview_path": preview_path,
                    "preview_mime_type": preview.mime_type,
                    "preview_status": "ready",
                    "preview_failure_code": None,
                }
            ).eq("id", str(document_id)).execute()
        except Exception as exc:  # noqa: BLE001 - original source and OCR can still be reviewed
            logger.warning(
                "Could not generate TIFF preview for %s: %s", document_id, type(exc).__name__
            )
            self.db.table("documents").update(
                {
                    "preview_path": None,
                    "preview_mime_type": None,
                    "preview_status": "failed",
                    "preview_failure_code": "preview_unavailable",
                }
            ).eq("id", str(document_id)).execute()

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

    def _finish(
        self,
        run_id: str,
        *,
        status: str,
        candidate_fact_count: int = 0,
        failure_code: str | None = None,
        error: str | None = None,
        warnings: list[str] | None = None,
        page_count: int = 0,
        text_chars: int = 0,
        extraction_method: str | None = None,
    ) -> None:
        self.db.table("document_ingestion_runs").update(
            {
                "status": status,
                "candidate_fact_count": candidate_fact_count,
                "failure_code": failure_code,
                "error_message": error,
                "warnings": warnings or [],
                "page_count": page_count,
                "extracted_text_char_count": text_chars,
                "extraction_method": extraction_method,
                "completed_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", run_id).execute()

    def _finish_failed(
        self,
        document_id: UUID,
        run_id: str,
        attempt: int,
        *,
        detail: str,
        warnings: list[str],
        page_count: int,
        text_chars: int,
        extraction_method: str | None,
    ) -> dict[str, Any]:
        code = self._failure_code(detail, attempt)
        self._set_document(
            document_id, parse_status="failed", parse_failure_code=code, parsed=False
        )
        self._finish(
            run_id,
            status="failed",
            failure_code=code,
            error=detail,
            warnings=warnings,
            page_count=page_count,
            text_chars=text_chars,
            extraction_method=extraction_method,
        )
        return self._outcome("failed", error_code=code)

    @staticmethod
    def _parse_json(response: str) -> dict[str, Any]:
        candidate = response.strip()
        if candidate.startswith("```"):
            candidate = candidate.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        payload = json.loads(candidate)
        if not isinstance(payload, dict):
            raise ValueError("Document extractor response must be a JSON object")
        return payload

    @staticmethod
    def _warnings(extraction: DocumentExtraction) -> list[str]:
        return [
            *extraction.warnings,
            *(warning for page in extraction.pages for warning in page.warnings),
        ]

    @staticmethod
    def _extraction_method(extraction: DocumentExtraction) -> str | None:
        methods = {
            page.method for page in extraction.pages if page.method is not ExtractionMethod.NONE
        }
        if not methods:
            return None
        if len(methods) == 1:
            return next(iter(methods)).value
        return "mixed"

    @staticmethod
    def _route_terminal_status(extraction: DocumentExtraction) -> str | None:
        if (
            extraction.route
            in (
                ExtractionRoute.AUTOMATED_CANDIDATES,
                ExtractionRoute.REVIEW_WITH_CAUTION,
            )
            and extraction.text_for_model()
        ):
            return None
        if extraction.route is ExtractionRoute.CLINICIAN_ONLY:
            return "needs_ocr"
        if extraction.route is ExtractionRoute.REJECTED:
            return "failed"
        return "needs_evidence_review"

    @staticmethod
    def _failure_code(detail: str, attempt: int) -> str:
        if attempt >= MAX_PARSE_ATTEMPTS:
            return "attempt_limit_reached"
        if isinstance(detail, PydanticValidationError) or "json" in detail.lower():
            return "invalid_model_response"
        if any(word in detail.lower() for word in ("pdf", "decode", "read", "source")):
            return "source_unreadable"
        return "provider_unavailable"

    @staticmethod
    def _outcome(
        status: str,
        *,
        candidate_count: int = 0,
        summary_length: int = 0,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "candidate_facts_created": candidate_count,
            "medications_created": 0,
            "conditions_created": 0,
            "allergies_created": 0,
            "obligations_created": 0,
            "summary_length": summary_length,
            "error_code": error_code,
        }
