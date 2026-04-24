"""Document schemas."""

from uuid import UUID

from pydantic import BaseModel

from app.models.enums import (
    DocumentReviewStatus,
    DocumentType,
    DocumentVisibility,
    UploaderRole,
)


class DocumentUpload(BaseModel):
    """Multipart metadata — file itself is sent separately."""

    document_type: DocumentType
    source_clinic: str | None = None
    notes: str | None = None


class DocumentRead(BaseModel):
    id: UUID
    patient_id: UUID
    uploaded_by: UUID
    uploaded_by_role: UploaderRole
    document_type: DocumentType
    file_name: str
    file_url: str  # Supabase Storage signed URL
    mime_type: str = "application/pdf"
    file_size_bytes: int
    parsed: bool = False
    ai_summary: str | None = None
    parse_status: str = "none"
    parse_error: str | None = None
    parse_attempts: int = 0
    source_clinic: str | None = None
    visibility: DocumentVisibility = DocumentVisibility.ALL_PROVIDERS
    review_status: DocumentReviewStatus | None = None
    reviewed_by: UUID | None = None
    reviewed_at: str | None = None
    review_note: str | None = None
    created_at: str
