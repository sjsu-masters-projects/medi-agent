"""Project-owned document extraction schema.

This is the normalized handoff between document parsing adapters and the app's
pending clinical-fact candidates. Inputs may come from PDF OCR, clinician
entry, or a future FHIR adapter; persistence never creates canonical clinical
records directly.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, field_validator


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
    # The printed action for this medication in this document ("STOP", "New", "Continue",
    # "Increase to 1000 mg", "Suspender"). A stopped or held medication must never become
    # an active care-plan item; ``medication_action`` is derived from this text.
    status: str | None = Field(default=None, max_length=200)
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


def _as_source_text(value: object) -> object:
    """Models sometimes return a printed number as a JSON number; keep the printed text."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        return str(value)
    return value


class ExtractedLabResult(BaseModel):
    """One printed test result, copied as written. Never interpreted at extraction time."""

    test_name: str = Field(..., min_length=1, max_length=200)
    value: str = Field(..., min_length=1, max_length=100)
    unit: str | None = Field(default=None, max_length=50)
    reference_range: str | None = Field(default=None, max_length=100)
    flag: str | None = Field(default=None, max_length=30)
    collected_at: str | None = Field(default=None, max_length=100)
    specimen: str | None = Field(default=None, max_length=100)
    panel: str | None = Field(default=None, max_length=200)
    evidence: list[ExtractionEvidence] = Field(min_length=1)

    @field_validator("value", "reference_range", mode="before")
    @classmethod
    def _printed_text(cls, value: object) -> object:
        return _as_source_text(value)


class ExtractedVitalSign(BaseModel):
    """One measured vital sign (blood pressure, pulse, weight...), copied as written."""

    name: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., min_length=1, max_length=50)
    unit: str | None = Field(default=None, max_length=30)
    measured_at: str | None = Field(default=None, max_length=100)
    evidence: list[ExtractionEvidence] = Field(min_length=1)

    @field_validator("value", mode="before")
    @classmethod
    def _printed_text(cls, value: object) -> object:
        return _as_source_text(value)


class ExtractedImmunization(BaseModel):
    """One recorded vaccine dose, copied as written."""

    vaccine: str = Field(..., min_length=1, max_length=200)
    administered_at: str | None = Field(default=None, max_length=100)
    dose_number: str | None = Field(default=None, max_length=50)
    evidence: list[ExtractionEvidence] = Field(min_length=1)


class ExtractedProcedure(BaseModel):
    """A performed procedure or study (imaging, endoscopy, biopsy...) with its printed result."""

    name: str = Field(..., min_length=1, max_length=200)
    performed_at: str | None = Field(default=None, max_length=100)
    # The printed impression, finding or result, verbatim; never a model's interpretation.
    result: str | None = Field(default=None, max_length=1500)
    evidence: list[ExtractionEvidence] = Field(min_length=1)


class ExtractedAppointment(BaseModel):
    """A scheduled or requested visit, referral or test the document names. Review-only."""

    description: str = Field(..., min_length=1, max_length=300)
    scheduled_for: str | None = Field(default=None, max_length=100)
    provider: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    evidence: list[ExtractionEvidence] = Field(min_length=1)


DOCUMENT_TYPES = (
    "lab_report",
    "discharge_summary",
    "prescription",
    "diagnostic_report",
    "referral",
    "insurance",
    "other",
)


class DocumentExtractionResult(BaseModel):
    """Normalized records produced from a clinical document."""

    document: ExtractedDocumentMetadata = Field(default_factory=ExtractedDocumentMetadata)
    summary: str | None = None
    medications: list[ExtractedMedication] = Field(default_factory=list)
    conditions: list[ExtractedCondition] = Field(default_factory=list)
    allergies: list[ExtractedAllergy] = Field(default_factory=list)
    obligations: list[ExtractedObligation] = Field(default_factory=list)
    lab_results: list[ExtractedLabResult] = Field(default_factory=list)
    vital_signs: list[ExtractedVitalSign] = Field(default_factory=list)
    immunizations: list[ExtractedImmunization] = Field(default_factory=list)
    procedures: list[ExtractedProcedure] = Field(default_factory=list)
    appointments: list[ExtractedAppointment] = Field(default_factory=list)


_ITEM_MODELS: dict[str, type[BaseModel]] = {
    "medications": ExtractedMedication,
    "conditions": ExtractedCondition,
    "allergies": ExtractedAllergy,
    "obligations": ExtractedObligation,
    "lab_results": ExtractedLabResult,
    "vital_signs": ExtractedVitalSign,
    "immunizations": ExtractedImmunization,
    "procedures": ExtractedProcedure,
    "appointments": ExtractedAppointment,
}


def parse_model_extraction(data: object) -> tuple[DocumentExtractionResult, int]:
    """Validate model output item by item; return the result and how many items were invalid.

    One malformed item (a result without evidence, an over-long name) used to fail the whole
    document and discard every valid fact with it. Each invalid item is dropped and counted
    instead; the document's other facts still reach clinician review. A response that is not
    an object at all is still an error.
    """
    if not isinstance(data, dict):
        raise ValueError("Model extraction output must be a JSON object")
    dropped = 0
    lists: dict[str, list[BaseModel]] = {}
    for key, model in _ITEM_MODELS.items():
        raw = data.get(key) or []
        if not isinstance(raw, list):
            dropped += 1
            raw = []
        valid: list[BaseModel] = []
        for item in raw:
            try:
                valid.append(model.model_validate(item))
            except ValidationError:
                dropped += 1
        lists[key] = valid
    try:
        metadata = ExtractedDocumentMetadata.model_validate(data.get("document") or {})
    except ValidationError:
        metadata = ExtractedDocumentMetadata()
    if metadata.document_type not in DOCUMENT_TYPES:
        metadata.document_type = None
    return DocumentExtractionResult(document=metadata, **lists), dropped


class DocumentExtractionImportRequest(BaseModel):
    """Explicit, verified extraction payload for candidate registration."""

    document_id: UUID | None = None
    extraction: DocumentExtractionResult
