"""Document schemas."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import DocumentType, DocumentVisibility, UploaderRole


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
    source_clinic: str | None = None
    visibility: DocumentVisibility = DocumentVisibility.ALL_PROVIDERS
    created_at: str
