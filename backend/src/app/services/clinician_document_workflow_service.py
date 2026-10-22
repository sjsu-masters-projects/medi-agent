"""Document-specific clinician workflows.

Keeps document review, annotation, and deep-dive document enrichment separate
from the broader ClinicianService orchestration layer.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from app.core.exceptions import ValidationError
from app.db.repositories import CareTeamRepository
from app.models.enums import DocumentReviewStatus, UploaderRole
from app.services.care_team_access import PatientAccess
from app.services.clinical_fact_service import ClinicalFactService
from app.services.clinician_record_gate import ClinicianRecordGate
from app.services.document_processing_status import attach_duplicate_status
from app.services.document_summary_service import (
    is_missing_summary_column_error,
    is_missing_summary_schedule_column_error,
)


# Migration 038 is applied by hand after this image deploys. Naming the summary columns
# in a select would make the clinician's document list fail outright during that window,
# so each read degrades to the pre-038 column set and the API schema supplies defaults.
def _is_missing_title_column(error: APIError) -> bool:
    message = str(getattr(error, "message", error))
    return str(getattr(error, "code", "")) in {"PGRST204", "42703"} and "display_title" in message


_SUMMARY_LIFECYCLE_COLUMNS = "summary_status, summary_failure_code, summary_attempts, "
_SUMMARY_COLUMNS = f"{_SUMMARY_LIFECYCLE_COLUMNS}summary_next_attempt_at, "


class ClinicianDocumentWorkflowService:
    """Clinician-scoped document review and annotation workflows."""

    def __init__(
        self,
        *,
        db: Client,
        care_team_repo: CareTeamRepository,
        execute: Callable[..., Awaitable[Any]],
        gate: ClinicianRecordGate | None = None,
    ) -> None:
        self.db = db
        self.care_team_repo = care_team_repo
        self._execute = execute
        self.gate = gate or ClinicianRecordGate(db)

    async def fetch_patient_documents(
        self, patient_id: UUID, *, clinician_id: UUID
    ) -> list[dict[str, Any]]:
        """Return the patient's documents this clinician may see, with reviewer metadata.

        A document routed to another care team is never listed; one the patient left
        unrouted is listed for every team that treats them.
        """
        access = await self._access(clinician_id, patient_id)
        docs = await self._select_documents(
            lambda columns: self.db.table("documents")
            .select(
                "id, file_name, document_type, parse_status, parse_failure_code, parse_attempts, ai_summary, "
                f"{columns}"
                "created_at, uploaded_by_role, clinician_annotation, "
                "review_status, reviewed_by, reviewed_at, review_note, "
                "routing_state, care_team_id"
            )
            .eq("patient_id", str(patient_id))
            .order("created_at", desc=True)
        )
        docs = access.filter_documents(docs)
        await attach_duplicate_status(self.db, docs, self._execute)
        return await self._attach_document_reviewers(docs)

    async def list_document_review_queue(self, clinician_id: UUID) -> list[dict[str, Any]]:
        """Pending patient uploads this clinician may review.

        Routed documents appear only for the owning team's clinicians. Unrouted ones appear
        for every team of the patient, marked ``needs_claim``: they cannot be approved or
        rejected until one clinician claims them.
        """
        links = await asyncio.to_thread(self.gate.access_service.for_clinician, clinician_id)
        patient_id_values = links.patient_ids
        if not patient_id_values:
            return []

        patient_result = await self._execute(
            self.db.table("patients")
            .select("id, first_name, last_name")
            .in_("id", patient_id_values)
        )
        patients_by_id = {
            str(row["id"]): row
            for row in cast(list[dict[str, Any]], patient_result.data or [])
            if row.get("id")
        }

        docs = await self._select_documents(
            lambda columns: self.db.table("documents")
            .select(
                "id, patient_id, file_name, document_type, parse_status, parse_failure_code, parse_attempts, ai_summary, "
                f"{columns}"
                "source_clinic, created_at, uploaded_by_role, review_status, "
                "routing_state, care_team_id"
            )
            .in_("patient_id", patient_id_values)
            .eq("uploaded_by_role", UploaderRole.PATIENT.value)
            .eq("review_status", DocumentReviewStatus.PENDING.value)
            .order("created_at", desc=True)
        )
        docs = links.keep(docs, "document")

        await attach_duplicate_status(self.db, docs, self._execute)
        queue_items: list[dict[str, Any]] = []
        for row in docs:
            patient = patients_by_id.get(str(row.get("patient_id")))
            if not patient:
                continue
            queue_items.append(
                {
                    **row,
                    "patient_first_name": patient.get("first_name", ""),
                    "patient_last_name": patient.get("last_name", ""),
                    "needs_claim": row.get("routing_state") == "unrouted",
                    "claimable_care_team_ids": sorted(
                        links.for_patient(row.get("patient_id")).team_ids
                    ),
                }
            )

        return queue_items

    async def approve_document_review(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        document_id: UUID,
    ) -> dict[str, Any]:
        """Approve a pending patient-uploaded document review."""
        return await self._set_document_review(
            clinician_id=clinician_id,
            patient_id=patient_id,
            document_id=document_id,
            review_status=DocumentReviewStatus.APPROVED,
            review_note=None,
        )

    async def reject_document_review(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        document_id: UUID,
        review_note: str | None = None,
    ) -> dict[str, Any]:
        """Reject a pending patient-uploaded document review."""
        return await self._set_document_review(
            clinician_id=clinician_id,
            patient_id=patient_id,
            document_id=document_id,
            review_status=DocumentReviewStatus.REJECTED,
            review_note=review_note,
        )

    async def save_document_annotation(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        document_id: UUID,
        annotation_text: str,
    ) -> dict[str, Any]:
        """Save clinician annotation on a patient document."""
        await self._gated_document(clinician_id, patient_id, document_id)

        update = (
            self.db.table("documents")
            .update(
                {
                    "clinician_annotation": annotation_text,
                    "annotation_by": str(clinician_id),
                }
            )
            .eq("id", str(document_id))
            .eq("patient_id", str(patient_id))
        )
        await self._execute(update)

        return {"status": "saved", "document_id": str(document_id)}

    async def document_facts(
        self, clinician_id: UUID, patient_id: UUID, document_id: UUID
    ) -> list[dict[str, Any]]:
        """Return evidence-backed candidates for one authorized source document."""
        await self._gated_document(clinician_id, patient_id, document_id)
        access = await self._access(clinician_id, patient_id)
        # A fact may also cite a document routed to another team; it is hidden then.
        facts = await asyncio.to_thread(
            lambda: self.gate.visible_facts(
                access,
                ClinicalFactService(self.db).list_facts_for_document(document_id, patient_id),
            )
        )
        payload: list[dict[str, Any]] = []
        for fact in facts:
            lineage = ClinicalFactService(self.db).get_lineage(UUID(str(fact["id"])), patient_id)
            citations = lineage.get("citations") or []
            payload.append({**fact, "citations": citations})
        return payload

    async def _select_documents(self, build: Callable[[str], Any]) -> list[dict[str, Any]]:
        """Read documents with titles and the summary lifecycle when the database has them."""
        try:
            result = await self._execute(build(f"display_title, {_SUMMARY_COLUMNS}"))
            return cast(list[dict[str, Any]], result.data or [])
        except APIError as exc:
            # The backend can reach Cloud Run before migrations 038, 039 or 050; read
            # without titles and let the summary-lifecycle fallbacks below decide.
            if not (
                _is_missing_title_column(exc)
                or is_missing_summary_column_error(exc)
                or is_missing_summary_schedule_column_error(exc)
            ):
                raise
        try:
            result = await self._execute(build(_SUMMARY_COLUMNS))
        except APIError as exc:
            if is_missing_summary_schedule_column_error(exc):
                result = await self._execute(build(_SUMMARY_LIFECYCLE_COLUMNS))
                return cast(list[dict[str, Any]], result.data or [])
            if not is_missing_summary_column_error(exc):
                raise
            result = await self._execute(build(""))
        return cast(list[dict[str, Any]], result.data or [])

    async def _access(self, clinician_id: UUID, patient_id: UUID) -> PatientAccess:
        """The clinician's active links to this patient; none means not assigned."""
        return await asyncio.to_thread(self.gate.access, clinician_id, patient_id)

    async def _gated_document(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        document_id: UUID,
        *,
        fields: str = (
            "id, patient_id, uploaded_by_role, review_status, reviewed_by, reviewed_at, review_note"
        ),
    ) -> dict[str, Any]:
        """The document row if this clinician may see it, else NotFound (no existence leak)."""
        return await asyncio.to_thread(
            self.gate.document, clinician_id, patient_id, document_id, columns=fields
        )

    async def _set_document_review(
        self,
        *,
        clinician_id: UUID,
        patient_id: UUID,
        document_id: UUID,
        review_status: DocumentReviewStatus,
        review_note: str | None,
    ) -> dict[str, Any]:
        """Persist a shared review decision for a patient-uploaded document."""
        document = await self._gated_document(clinician_id, patient_id, document_id)

        if document.get("routing_state") == "unrouted":
            # Several teams can see this document; none owns it until one claims it.
            raise ValidationError(
                "Claim this document for your care team before reviewing it",
                code="DOCUMENT_CLAIM_REQUIRED",
            )
        if document.get("uploaded_by_role") != UploaderRole.PATIENT.value:
            raise ValidationError("Only patient-uploaded documents can be reviewed")

        current_status = document.get("review_status")
        if current_status != DocumentReviewStatus.PENDING.value:
            raise ValidationError("Document review has already been completed")

        reviewed_at = datetime.now(UTC).isoformat()
        update_payload = {
            "review_status": review_status.value,
            "reviewed_by": str(clinician_id),
            "reviewed_at": reviewed_at,
            "review_note": review_note.strip() if review_note else None,
        }

        result = await self._execute(
            self.db.table("documents")
            .update(update_payload)
            .eq("id", str(document_id))
            .eq("patient_id", str(patient_id))
            .eq("routing_state", "routed")
            .eq("review_status", DocumentReviewStatus.PENDING.value)
        )
        updated_rows = cast(list[dict[str, Any]], result.data or [])
        if not updated_rows:
            raise ValidationError("Document review changed; reload before trying again")
        updated = updated_rows[0]

        return {
            "status": "reviewed",
            "document_id": str(document_id),
            "patient_id": str(patient_id),
            "review_status": updated.get("review_status", review_status.value),
            "reviewed_by": updated.get("reviewed_by", str(clinician_id)),
            "reviewed_at": updated.get("reviewed_at", reviewed_at),
            "review_note": updated.get("review_note"),
        }

    async def _attach_document_reviewers(
        self,
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Hydrate reviewer metadata onto document rows for clinician views."""
        reviewer_ids = sorted(
            {str(document["reviewed_by"]) for document in documents if document.get("reviewed_by")}
        )
        if not reviewer_ids:
            return documents

        reviewers_result = await self._execute(
            self.db.table("clinicians").select("id, first_name, last_name").in_("id", reviewer_ids)
        )
        reviewers_by_id = {
            str(row["id"]): row
            for row in cast(list[dict[str, Any]], reviewers_result.data or [])
            if row.get("id")
        }

        for document in documents:
            reviewer_id = document.get("reviewed_by")
            document["reviewer"] = reviewers_by_id.get(str(reviewer_id)) if reviewer_id else None

        return documents
