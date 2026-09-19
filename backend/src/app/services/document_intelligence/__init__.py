"""Deterministic document intelligence: classify, extract, anchor, and cite.

The pipeline decides how each page is read, runs OCR only when a page has no usable
text layer, records per-word confidence and coordinates, and anchors every extracted
value back to a page, region, and quote. No model output reaches canonical clinical
tables from here; candidates are registered as ``pending_review`` facts only.
"""

from app.services.document_intelligence.anchoring import anchor_value, normalize_for_match
from app.services.document_intelligence.grounding import (
    CandidateRegistrationSummary,
    DocumentEvidenceCandidateService,
    GroundedEvidence,
    GroundedItem,
    candidate_from_grounded,
    ground_item,
    items_from_extraction_result,
)
from app.services.document_intelligence.models import (
    DocumentClass,
    DocumentExtraction,
    DocumentIntelligencePolicy,
    EvidenceAnchor,
    ExtractionMethod,
    ExtractionRoute,
    FailureKind,
    PageClass,
    PageExtraction,
    PageQuality,
)
from app.services.document_intelligence.ocr import (
    OcrEngine,
    OcrEngineUnavailableError,
    TesseractOcrEngine,
)
from app.services.document_intelligence.pipeline import DocumentIntelligenceService

__all__ = [
    "CandidateRegistrationSummary",
    "DocumentClass",
    "DocumentEvidenceCandidateService",
    "DocumentExtraction",
    "DocumentIntelligencePolicy",
    "DocumentIntelligenceService",
    "EvidenceAnchor",
    "ExtractionMethod",
    "ExtractionRoute",
    "FailureKind",
    "GroundedEvidence",
    "GroundedItem",
    "OcrEngine",
    "OcrEngineUnavailableError",
    "PageClass",
    "PageExtraction",
    "PageQuality",
    "TesseractOcrEngine",
    "anchor_value",
    "candidate_from_grounded",
    "ground_item",
    "items_from_extraction_result",
    "normalize_for_match",
]
