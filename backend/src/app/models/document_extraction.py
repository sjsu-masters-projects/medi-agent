"""Project-owned document extraction schema.

This is the normalized handoff between document parsing adapters and the app's
pending clinical-fact candidates. Inputs may come from PDF OCR, clinician
entry, or a future FHIR adapter; persistence never creates canonical clinical
records directly.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ExtractionEvidence(BaseModel):
    """Verifiable source support for one extracted candidate."""

    page: int = Field(ge=1)
    excerpt: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)


class ExtractedDocumentMetadata(BaseModel):
    """Metadata for the source document that produced extracted records."""

    title: str = Field(default="Clinical Document", min_length=1, max_length=255)
    document_type: str | None = Field(default=None, max_length=100)
    source_name: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class ExtractedMedication(BaseModel):
    """Source-worded medication proposal, never a canonical medication record."""

    name: str = Field(..., min_length=1, max_length=200)
    dosage: str = Field(default="as directed", min_length=1)
    frequency: str = Field(default="as directed", min_length=1)
    # This is the exact source wording, such as ``by mouth`` or ``sublingual``. Controlled
    # route codes belong to an explicit terminology/clinician-review step, not extraction.
    route: str | None = Field(default=None, max_length=100)
    instructions: str | None = None
    generic_name: str | None = None
    rxcui: str | None = None
    evidence: list[ExtractionEvidence] = Field(min_length=1)


class ExtractedCondition(BaseModel):
    """Condition record after document parsing."""

    name: str = Field(..., min_length=1)
    status: str = Field(default="active", min_length=1)
    notes: str | None = None
    evidence: list[ExtractionEvidence] = Field(min_length=1)


class ExtractedAllergy(BaseModel):
    """Allergy record after document parsing."""

    allergen: str = Field(..., min_length=1)
    reaction: str | None = None
    severity: str | None = Field(default=None, max_length=100)
    evidence: list[ExtractionEvidence] = Field(min_length=1)


class ExtractedObligation(BaseModel):
    """Patient task or care-plan obligation extracted from a document."""

    description: str = Field(..., min_length=1, max_length=500)
    frequency: str = Field(default="as directed", min_length=1)
    obligation_type: str | None = Field(default=None, max_length=100)
    evidence: list[ExtractionEvidence] = Field(min_length=1)


class DocumentExtractionResult(BaseModel):
    """Normalized records produced from a clinical document."""

    document: ExtractedDocumentMetadata = Field(default_factory=ExtractedDocumentMetadata)
    summary: str | None = None
    medications: list[ExtractedMedication] = Field(default_factory=list)
    conditions: list[ExtractedCondition] = Field(default_factory=list)
    allergies: list[ExtractedAllergy] = Field(default_factory=list)
    obligations: list[ExtractedObligation] = Field(default_factory=list)


class DocumentExtractionImportRequest(BaseModel):
    """Explicit, verified extraction payload for candidate registration."""

    document_id: UUID | None = None
    extraction: DocumentExtractionResult
