"""Project-owned document extraction schema.

This is the normalized handoff between document parsing adapters and the app's
relational clinical records. Inputs may come from PDF OCR, clinician entry, a
future FHIR adapter, or local demo data, but persistence should flow through
this shape.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.enums import DocumentType, MedicationRoute, ObligationType


class ExtractedDocumentMetadata(BaseModel):
    """Metadata for the source document that produced extracted records."""

    title: str = Field(default="Clinical Document", min_length=1, max_length=255)
    document_type: DocumentType = DocumentType.OTHER
    source_name: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class ExtractedMedication(BaseModel):
    """Medication record after document parsing and basic normalization."""

    name: str = Field(..., min_length=1, max_length=200)
    dosage: str = Field(default="as directed", min_length=1)
    frequency: str = Field(default="as directed", min_length=1)
    route: MedicationRoute = MedicationRoute.OTHER
    instructions: str | None = None
    generic_name: str | None = None
    rxcui: str | None = None


class ExtractedCondition(BaseModel):
    """Condition record after document parsing."""

    name: str = Field(..., min_length=1)
    status: str = Field(default="active", min_length=1)
    notes: str | None = None


class ExtractedAllergy(BaseModel):
    """Allergy record after document parsing."""

    allergen: str = Field(..., min_length=1)
    reaction: str | None = None
    severity: str = Field(default="moderate", pattern="^(mild|moderate|severe)$")


class ExtractedObligation(BaseModel):
    """Patient task or care-plan obligation extracted from a document."""

    description: str = Field(..., min_length=1, max_length=500)
    frequency: str = Field(default="as directed", min_length=1)
    obligation_type: ObligationType = ObligationType.CUSTOM


class DocumentExtractionResult(BaseModel):
    """Normalized records produced from a clinical document."""

    document: ExtractedDocumentMetadata = Field(default_factory=ExtractedDocumentMetadata)
    summary: str | None = None
    medications: list[ExtractedMedication] = Field(default_factory=list)
    conditions: list[ExtractedCondition] = Field(default_factory=list)
    allergies: list[ExtractedAllergy] = Field(default_factory=list)
    obligations: list[ExtractedObligation] = Field(default_factory=list)


class DocumentExtractionImportRequest(BaseModel):
    """Optional extraction payload for local/demo import flows."""

    extraction: DocumentExtractionResult | None = None
