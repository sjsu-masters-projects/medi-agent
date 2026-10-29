"""Document schemas."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

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
    preview_url: str | None = None
    preview_mime_type: str | None = None
    preview_status: str = "not_required"
    preview_failure_code: str | None = None
    file_size_bytes: int
    parsed: bool = False
    ai_summary: str | None = None
    # Short list title per locale, drafted from the summary; the file name stays the source.
    display_title: dict[str, str] = Field(default_factory=dict)
    parse_status: str = "none"
    parse_failure_code: str | None = None
    parse_attempts: int = 0
    # The optional explanation has its own lifecycle; it never gates the clinical result.
    summary_status: str = "not_required"
    summary_failure_code: str | None = None
    summary_attempts: int = 0
    summary_next_attempt_at: str | None = None
    source_clinic: str | None = None
    visibility: DocumentVisibility = DocumentVisibility.ALL_PROVIDERS
    review_status: DocumentReviewStatus | None = None
    reviewed_by: UUID | None = None
    reviewed_at: str | None = None
    review_note: str | None = None
    # PLAN-002: the care team that owns the document; none while it is unrouted.
    care_team_id: UUID | None = None
    routing_state: Literal["routed", "unrouted"] = "routed"
    created_at: str


class DocumentCareTeamOption(BaseModel):
    """One of the patient's active care teams, as offered when uploading. Names only."""

    care_team_id: UUID
    specialty: str | None = None
    clinician_name: str | None = None
    clinic_name: str | None = None
    clinic_id: UUID | None = None


class DocumentRemovalStatus(BaseModel):
    can_remove: bool
    reason: Literal["care_team_upload", "reviewed", "processing", "used_in_record"] | None = None


class DocumentClaimRead(BaseModel):
    document_id: UUID
    care_team_id: UUID
    status: str
    replayed: bool = False


class DocumentResultRead(BaseModel):
    """One test result or measurement read from a patient's own document.

    Values are as printed. ``flag_meaning`` and ``range_status`` restate the report's own
    flag and printed range; nothing here interprets the result.
    """

    kind: Literal["lab_result", "vital_sign"]
    name: str
    value: str
    unit: str | None = None
    reference_range: str | None = None
    flag: str | None = None
    flag_meaning: str | None = None
    range_status: str | None = None
    panel: str | None = None
    observed_at: str | None = None
    page: int | None = None
    reviewed: bool
