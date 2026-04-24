"""Document-specific clinician workflows.

Keeps document review, annotation, and deep-dive document enrichment separate
from the broader ClinicianService orchestration layer.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.db.repositories import CareTeamRepository
from app.models.enums import DocumentReviewStatus, UploaderRole


class ClinicianDocumentWorkflowService:
    """Clinician-scoped document review and annotation workflows."""

    def __init__(
        self,
        *,
        db: Client,
        care_team_repo: CareTeamRepository,
        execute: Callable[..., Awaitable[Any]],
    ) -> None:
        self.db = db
        self.care_team_repo = care_team_repo
        self._execute = execute

    async def fetch_patient_documents(self, patient_id: UUID) -> list[dict[str, Any]]:
        """Return patient documents enriched with reviewer metadata."""
        docs = await self._execute(
            self.db.table("documents")
            .select(
                "id, file_name, document_type, parse_status, ai_summary, "
                "created_at, uploaded_by_role, clinician_annotation, "
                "review_status, reviewed_by, reviewed_at, review_note"
            )
            .eq("patient_id", str(patient_id))
            .order("created_at", desc=True)
        )
        return await self._attach_document_reviewers(cast(list[dict[str, Any]], docs.data or []))

    async def list_document_review_queue(self, clinician_id: UUID) -> list[dict[str, Any]]:
        """List pending patient-uploaded documents for assigned patients."""
        patient_rows = await self.care_team_repo.list_assigned_patient_ids(str(clinician_id))
        patient_id_values = [
            str(row["patient_id"]) for row in patient_rows if row.get("patient_id")
        ]
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

        docs = await self._execute(
            self.db.table("documents")
            .select(
                "id, patient_id, file_name, document_type, parse_status, ai_summary, "
                "source_clinic, created_at, uploaded_by_role, review_status"
            )
            .in_("patient_id", patient_id_values)
            .eq("uploaded_by_role", UploaderRole.PATIENT.value)
            .eq("review_status", DocumentReviewStatus.PENDING.value)
            .order("created_at", desc=True)
        )

        queue_items: list[dict[str, Any]] = []
        for row in cast(list[dict[str, Any]], docs.data or []):
            patient = patients_by_id.get(str(row.get("patient_id")))
            if not patient:
                continue
            queue_items.append(
                {
                    **row,
                    "patient_first_name": patient.get("first_name", ""),
                    "patient_last_name": patient.get("last_name", ""),
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
        await self._assert_patient_assignment(clinician_id, patient_id)
        await self._get_document_row(patient_id, document_id)

        await self._execute(
            self.db.table("documents")
            .update(
                {
                    "clinician_annotation": annotation_text,
                    "annotation_by": str(clinician_id),
                }
            )
            .eq("id", str(document_id))
        )

        return {"status": "saved", "document_id": str(document_id)}

    async def _assert_patient_assignment(self, clinician_id: UUID, patient_id: UUID) -> None:
        """Require an active care-team assignment before clinician document access."""
        assignment_rows = await self.care_team_repo.find_active_assignment(
            str(clinician_id),
            str(patient_id),
        )
        if not assignment_rows:
            raise AuthorizationError("You are not assigned to this patient")

    async def _get_document_row(
        self,
        patient_id: UUID,
        document_id: UUID,
        *,
        fields: str = (
            "id, patient_id, uploaded_by_role, review_status, reviewed_by, reviewed_at, review_note"
        ),
    ) -> dict[str, Any]:
        """Fetch a patient-owned document row or raise NotFound."""
        doc_result = await self._execute(
            self.db.table("documents")
            .select(fields)
            .eq("id", str(document_id))
            .eq("patient_id", str(patient_id))
            .single()
        )
        if not doc_result.data:
            raise NotFoundError("Document", str(document_id))
        return cast(dict[str, Any], doc_result.data)

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
        await self._assert_patient_assignment(clinician_id, patient_id)
        document = await self._get_document_row(patient_id, document_id)

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
        )
        updated_rows = cast(list[dict[str, Any]], result.data or [])
        updated = updated_rows[0] if updated_rows else {**document, **update_payload}

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
