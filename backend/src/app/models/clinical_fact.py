"""Canonical clinical-fact and provenance schemas.

These schemas represent an evidence-backed candidate fact.  A candidate remains
``pending_review`` until an authorized reviewer explicitly approves it; callers
must use the review state rather than treating extraction output as clinical truth.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ClinicalFactReviewState(StrEnum):
    """Lifecycle states for a candidate clinical fact."""

    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DELETED = "deleted"


class ConfidenceBand(StrEnum):
    """Human-readable confidence category alongside the numeric score."""

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourceArtifactType(StrEnum):
    """Kinds of artifacts that can support a clinical fact."""

    DOCUMENT = "document"
    FHIR_RESOURCE = "fhir_resource"
    PATIENT_REPORT = "patient_report"
    CLINICIAN_ENTRY = "clinician_entry"
    EXTERNAL_RECORD = "external_record"


class SourceProvenanceCreate(BaseModel):
    """Immutable source metadata captured when a candidate is registered."""

    artifact_type: SourceArtifactType
    source_system: str = Field(min_length=1, max_length=100)
    source_reference: str = Field(min_length=1, max_length=500)
    document_id: UUID | None = None
    document_location: dict[str, Any] = Field(default_factory=dict)
    extractor_version: str | None = Field(default=None, max_length=100)
    model_version: str | None = Field(default=None, max_length=200)
    captured_at: datetime | None = None

    @model_validator(mode="after")
    def document_sources_require_document_id(self) -> SourceProvenanceCreate:
        if self.artifact_type is SourceArtifactType.DOCUMENT and self.document_id is None:
            raise ValueError("document_id is required when artifact_type is document")
        return self


class EvidenceCitationCreate(BaseModel):
    """The precise evidence excerpt and location supporting a fact."""

    excerpt: str = Field(min_length=1, max_length=5000)
    location: dict[str, Any] = Field(default_factory=dict)


class ClinicalFactCreate(BaseModel):
    """Input for a pending, evidence-backed candidate clinical fact."""

    patient_id: UUID
    fact_type: str = Field(min_length=1, max_length=100)
    subject_type: str = Field(min_length=1, max_length=100)
    subject_id: UUID | None = None
    value: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    confidence_band: ConfidenceBand = ConfidenceBand.UNKNOWN
    uncertainty: list[str] = Field(default_factory=list)
    provenance: SourceProvenanceCreate
    citations: list[EvidenceCitationCreate] = Field(default_factory=list)


class SourceProvenanceRead(SourceProvenanceCreate):
    id: UUID
    captured_at: datetime
    created_at: datetime


class EvidenceCitationRead(EvidenceCitationCreate):
    id: UUID
    fact_id: UUID
    provenance_id: UUID
    created_at: datetime


class ClinicalFactRead(BaseModel):
    id: UUID
    patient_id: UUID
    fact_type: str
    subject_type: str
    subject_id: UUID | None = None
    value: dict[str, Any]
    confidence_score: float | None = None
    confidence_band: ConfidenceBand
    uncertainty: list[str] = Field(default_factory=list)
    review_state: ClinicalFactReviewState
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    created_at: datetime
    updated_at: datetime


class ClinicalFactLineage(BaseModel):
    """A fact plus its source artifact and exact supporting citations."""

    fact: ClinicalFactRead
    provenance: SourceProvenanceRead
    citations: list[EvidenceCitationRead] = Field(default_factory=list)
