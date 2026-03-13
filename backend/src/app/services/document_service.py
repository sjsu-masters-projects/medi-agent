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

logger = logging.getLogger(__name__)

# File validation constants
ALLOWED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
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
    ) -> Any:
        """Store document metadata after the frontend has uploaded the file.

        Validates file type and size before inserting.
        """
        self._validate_file(mime_type, file_size_bytes)

        # Generate a signed URL for immediate access
        file_url = self._generate_signed_url(file_path)

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
            if doc.get("file_path"):
                doc["file_url"] = self._generate_signed_url(doc["file_path"])
        return data

    # ── Get One ─────────────────────────────────────────

    async def get_document(self, document_id: UUID, patient_id: UUID) -> Any:
        """Get a single document with a fresh signed URL."""
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

        # Refresh the signed URL
        data = cast(dict[str, Any], result.data)
        if data.get("file_path"):
            data["file_url"] = self._generate_signed_url(data["file_path"])
        return data

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
            return response.get("signedURL", "")
        except Exception as e:
            logger.warning("Failed to sign URL for %s: %s", file_path, e)
            return ""
