"""Document service — metadata CRUD and signed URL generation.

Design: Files are uploaded directly to Supabase Storage by the frontend.
This service only handles the *metadata* row in the documents table
and generates time-limited signed URLs for file access.
"""

from __future__ import annotations

import logging
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import DocumentReviewStatus, UploaderRole

logger = logging.getLogger(__name__)

# File validation constants
ALLOWED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "application/json",
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "image/tiff",
        "text/plain",
        "text/csv",
    }
)
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB
SIGNED_URL_EXPIRY_SECONDS = 3600  # 1 hour


class DocumentService:
    """Document metadata operations — the actual files live in Supabase Storage."""

    def __init__(self, db: Client) -> None:
        self.db = db

    # ── Create ──────────────────────────────────────────

    async def create_document(
        self,
        patient_id: UUID,
        uploaded_by: UUID,
        uploaded_by_role: str,
        file_name: str,
        file_path: str,
        file_size_bytes: int,
        mime_type: str,
        document_type: str,
        source_clinic: str | None = None,
        notes: str | None = None,
        sign_file_url: bool = True,
    ) -> Any:
        """Store document metadata after the frontend has uploaded the file.

        Validates file type and size before inserting.
        """
        self._validate_file(mime_type, file_size_bytes)

        # Generate a signed URL for immediate access
        file_url = self._generate_signed_url(file_path) if sign_file_url else ""

        row: dict[str, Any] = {
            "patient_id": str(patient_id),
            "uploaded_by": str(uploaded_by),
            "uploaded_by_role": uploaded_by_role,
            "file_name": file_name,
            "file_url": file_url,
            "file_path": file_path,  # storage path for re-signing
            "file_size_bytes": file_size_bytes,
            "mime_type": mime_type,
            "document_type": document_type,
            "source_clinic": source_clinic,
            "notes": notes,
            "parse_status": "pending",
            "parse_error": None,
            "parse_attempts": 0,
            "review_status": (
                DocumentReviewStatus.PENDING.value
                if uploaded_by_role == UploaderRole.PATIENT.value
                else None
            ),
            "reviewed_by": None,
            "reviewed_at": None,
            "review_note": None,
        }

        result = self.db.table("documents").insert(row).execute()
        if not result.data:
            raise ValidationError("Failed to create document record")
        return result.data[0]

    # ── List ────────────────────────────────────────────

    async def list_documents(self, patient_id: UUID) -> Any:
        """List all documents for a patient, newest first."""
        result = (
            self.db.table("documents")
            .select("*")
            .eq("patient_id", str(patient_id))
            .order("created_at", desc=True)
            .execute()
        )
        # Refresh signed URLs for each document
        data = cast(list[dict[str, Any]], result.data or [])
        for doc in data:
            if self._should_sign_url(doc):
                doc["file_url"] = self._generate_signed_url(doc["file_path"])
        return data

    # ── Get One ─────────────────────────────────────────

    async def get_document(self, document_id: UUID, patient_id: UUID) -> Any:
        """Get a single document with a fresh signed URL."""
        data = self._get_document_row(document_id, patient_id)

        # Refresh the signed URL
        if self._should_sign_url(data):
            data["file_url"] = self._generate_signed_url(data["file_path"])
        return data

    def _get_document_row(self, document_id: UUID, patient_id: UUID) -> dict[str, Any]:
        """Fetch a patient-owned document row without mutating signed URLs."""
        result = (
            self.db.table("documents")
            .select("*")
            .eq("id", str(document_id))
            .eq("patient_id", str(patient_id))
            .single()
            .execute()
        )
        if not result.data:
            raise NotFoundError("Document", str(document_id))

        return cast(dict[str, Any], result.data)

    async def delete_document(self, document_id: UUID, patient_id: UUID) -> None:
        """Delete a patient-owned document metadata row and its storage object."""
        document = self._get_document_row(document_id, patient_id)
        self._delete_document_derived_records(document_id, patient_id)

        file_path = str(document.get("file_path") or "").strip()
        if file_path:
            self._delete_storage_file(file_path)

        (
            self.db.table("documents")
            .delete()
            .eq("id", str(document_id))
            .eq("patient_id", str(patient_id))
            .execute()
        )

    def _delete_document_derived_records(self, document_id: UUID, patient_id: UUID) -> None:
        """Delete Today-feed records that were created from this document."""
        medication_ids = self._get_document_derived_record_ids(
            "medications",
            document_id,
            patient_id,
        )
        obligation_ids = self._get_document_derived_record_ids(
            "obligations",
            document_id,
            patient_id,
        )

        self._delete_feed_target_records("medication", medication_ids, patient_id)
        self._delete_feed_target_records("obligation", obligation_ids, patient_id)
        self._delete_document_derived_rows("medications", medication_ids, patient_id)
        self._delete_document_derived_rows("obligations", obligation_ids, patient_id)

    def _get_document_derived_record_ids(
        self,
        table_name: str,
        document_id: UUID,
        patient_id: UUID,
    ) -> list[str]:
        """Find patient-owned rows that were extracted from a document."""
        result = (
            self.db.table(table_name)
            .select("id")
            .eq("patient_id", str(patient_id))
            .eq("source_document_id", str(document_id))
            .execute()
        )
        rows = cast(list[dict[str, Any]], result.data or [])
        return [str(row["id"]) for row in rows if row.get("id")]

    def _delete_feed_target_records(
        self,
        target_type: str,
        target_ids: list[str],
        patient_id: UUID,
    ) -> None:
        """Delete logs and reminder schedules for removed feed targets."""
        if not target_ids:
            return

        (
            self.db.table("adherence_logs")
            .delete()
            .eq("patient_id", str(patient_id))
            .eq("target_type", target_type)
            .in_("target_id", target_ids)
            .execute()
        )
        (
            self.db.table("reminder_schedules")
            .delete()
            .eq("patient_id", str(patient_id))
            .eq("target_type", target_type)
            .in_("target_id", target_ids)
            .execute()
        )

    def _delete_document_derived_rows(
        self,
        table_name: str,
        row_ids: list[str],
        patient_id: UUID,
    ) -> None:
        """Delete document-derived medication or obligation rows."""
        if not row_ids:
            return

        (
            self.db.table(table_name)
            .delete()
            .eq("patient_id", str(patient_id))
            .in_("id", row_ids)
            .execute()
        )

    async def update_summary(self, document_id: UUID, patient_id: UUID, summary: str) -> None:
        """Cache an AI summary on the document row."""
        (
            self.db.table("documents")
            .update({"ai_summary": summary, "parsed": True})
            .eq("id", str(document_id))
            .eq("patient_id", str(patient_id))
            .execute()
        )

    def update_parse_result(
        self,
        document_id: UUID,
        patient_id: UUID,
        *,
        ai_summary: str | None,
        parse_status: str,
        parsed: bool,
        parse_error: str | None = None,
    ) -> None:
        """Persist a completed or failed parse result for a patient document."""
        (
            self.db.table("documents")
            .update(
                {
                    "ai_summary": ai_summary,
                    "parse_error": parse_error,
                    "parse_status": parse_status,
                    "parsed": parsed,
                }
            )
            .eq("id", str(document_id))
            .eq("patient_id", str(patient_id))
            .execute()
        )

    # ── Helpers ─────────────────────────────────────────

    def _validate_file(self, mime_type: str, file_size_bytes: int) -> None:
        """Reject disallowed file types or oversized files."""
        if mime_type not in ALLOWED_MIME_TYPES:
            raise ValidationError(
                f"File type '{mime_type}' not allowed. "
                f"Accepted: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
            )
        if file_size_bytes > MAX_FILE_SIZE_BYTES:
            raise ValidationError(
                f"File too large ({file_size_bytes / 1024 / 1024:.1f}MB). "
                f"Maximum: {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f}MB"
            )

    def _generate_signed_url(self, file_path: str) -> str:
        """Create a time-limited download URL from Supabase Storage."""
        try:
            response = self.db.storage.from_("documents").create_signed_url(
                file_path, SIGNED_URL_EXPIRY_SECONDS
            )
            signed_url = response.get("signedURL")
            return signed_url or ""
        except Exception as e:
            logger.warning("Failed to sign URL for %s: %s", file_path, e)
            return ""

    def _delete_storage_file(self, file_path: str) -> None:
        """Best-effort removal of a document object from Supabase Storage."""
        try:
            self.db.storage.from_("documents").remove([file_path])
        except Exception as e:
            logger.warning("Failed to delete storage object %s: %s", file_path, e)

    def _should_sign_url(self, document: dict[str, Any]) -> bool:
        """Only storage-backed documents have a path that should be signed."""
        return bool(document.get("file_path"))
