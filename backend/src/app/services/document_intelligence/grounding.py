"""Ground extracted values in page evidence and register page-cited candidates.

A model may propose a medication, condition, allergy, or obligation; only the
deterministic layer decides whether the proposal was actually read on a page. The
result carries the same ``{page, excerpt, confidence}`` shape the ingestion graph
already validates, plus the region and word confidence needed for a clinician to
open the page and see the words. Nothing here writes canonical clinical records.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from supabase import Client

from app.models.clinical_fact import (
    ClinicalFactCreate,
    ConfidenceBand,
    EvidenceCitationCreate,
    SourceArtifactType,
    SourceProvenanceCreate,
)
from app.services.clinical_fact_service import ClinicalFactService
from app.services.document_intelligence.anchoring import anchor_value, normalize_for_match
from app.services.document_intelligence.models import (
    DocumentExtraction,
    DocumentIntelligencePolicy,
    EvidenceAnchor,
    ExtractionRoute,
    PageQuality,
)

SOURCE_SYSTEM = "document_intelligence"
REVIEW_NOTE = "Document extraction requires clinician review before clinical use."
_PLACEHOLDER_VALUES = frozenset({"", "as directed", "unknown", "active"})

# Attributes that must be read on the page for each candidate type. The first is the
# primary anchor; a candidate whose primary value is not on any page scores zero.
ANCHOR_FIELDS: dict[str, tuple[str, ...]] = {
    "medication": ("name", "dosage", "frequency"),
    "condition": ("name",),
    "allergy": ("allergen", "reaction"),
    "obligation": ("description",),
}


class GroundedEvidence(BaseModel):
    """One located value: the ingestion evidence shape plus where on the page it sits."""

    page: int = Field(ge=1)
    excerpt: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0.0, le=1.0)
    field: str
    location: dict[str, Any] = Field(default_factory=dict)


class GroundedItem(BaseModel):
    fact_type: str
    value: dict[str, Any]
    confidence_score: float = Field(ge=0.0, le=1.0)
    confidence_band: ConfidenceBand
    uncertainty: list[str] = Field(default_factory=list)
    evidence: list[GroundedEvidence] = Field(default_factory=list)

    @property
    def anchored(self) -> bool:
        return bool(self.evidence)

    @property
    def pages(self) -> list[int]:
        return sorted({item.page for item in self.evidence})


class CandidateRegistrationSummary(BaseModel):
    created: int = 0
    low_confidence: int = 0
    unanchored: int = 0
    fact_ids: list[str] = Field(default_factory=list)


def ground_item(
    extraction: DocumentExtraction,
    fact_type: str,
    value: dict[str, Any],
    *,
    policy: DocumentIntelligencePolicy | None = None,
) -> GroundedItem:
    """Locate every anchorable attribute of one extracted item on the page text."""
    policy = policy or DocumentIntelligencePolicy()
    anchors, uncertainty = _anchor_attributes(extraction, fact_type, value, policy)
    uncertainty.extend(_check_claimed_evidence(extraction, value, anchors))
    primary = ANCHOR_FIELDS.get(fact_type, ("name",))[0]
    score = _confidence_score(anchors, primary)
    evidence = [_grounded_evidence(field, anchor) for field, anchor in anchors.items()]
    pages = sorted({item.page for item in evidence})
    return GroundedItem(
        fact_type=fact_type,
        value={key: item for key, item in value.items() if key != "evidence"},
        confidence_score=score,
        confidence_band=policy.band(score),
        uncertainty=[REVIEW_NOTE, *uncertainty, *_page_quality_notes(extraction, pages)],
        evidence=evidence,
    )


def candidate_from_grounded(
    item: GroundedItem,
    *,
    patient_id: UUID,
    document_id: UUID,
    extraction: DocumentExtraction,
    index: int,
    model_version: str | None = None,
) -> ClinicalFactCreate:
    """Build the pending candidate; every citation points at a page, region, and quote."""
    if not item.anchored or item.confidence_score <= 0:
        raise ValueError("An unanchored extraction item cannot become a clinical candidate")
    return ClinicalFactCreate(
        patient_id=patient_id,
        fact_type=item.fact_type,
        subject_type=item.fact_type,
        value=item.value,
        confidence_score=item.confidence_score,
        confidence_band=item.confidence_band,
        uncertainty=item.uncertainty,
        external_source_key=f"document/{document_id}/{item.fact_type}/{index}",
        external_source_version=extraction.source_sha256,
        provenance=SourceProvenanceCreate(
            artifact_type=SourceArtifactType.DOCUMENT,
            source_system=SOURCE_SYSTEM,
            source_reference=f"document:{document_id}",
            document_id=document_id,
            document_location={
                "scope": "document",
                "document_class": extraction.document_class.value,
                "route": extraction.route.value,
                "pages": item.pages,
                "source_sha256": extraction.source_sha256,
            },
            extractor_version=extraction.extractor_version[:100],
            model_version=model_version,
        ),
        citations=_citations(item),
    )


def items_from_extraction_result(result: Any) -> list[tuple[str, dict[str, Any]]]:
    """Flatten a ``DocumentExtractionResult`` into ``(fact_type, value)`` pairs."""
    pairs: list[tuple[str, dict[str, Any]]] = []
    for fact_type, attribute in (
        ("medication", "medications"),
        ("condition", "conditions"),
        ("allergy", "allergies"),
        ("obligation", "obligations"),
    ):
        for row in getattr(result, attribute, []) or []:
            pairs.append((fact_type, row.model_dump(mode="json")))
    return pairs


class DocumentEvidenceCandidateService:
    """Register grounded extraction output as pending, page-cited candidates."""

    def __init__(
        self,
        db: Client,
        *,
        policy: DocumentIntelligencePolicy | None = None,
        registry: ClinicalFactService | None = None,
    ) -> None:
        self.policy = policy or DocumentIntelligencePolicy()
        self.registry = registry or ClinicalFactService(db)

    def register(
        self,
        *,
        patient_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        extraction: DocumentExtraction,
        items: Sequence[tuple[str, dict[str, Any]]],
        model_version: str | None = None,
    ) -> CandidateRegistrationSummary:
        if extraction.route in (ExtractionRoute.REJECTED, ExtractionRoute.CLINICIAN_ONLY):
            raise ValueError(
                f"Extraction route {extraction.route.value!r} does not permit candidates"
            )
        summary = CandidateRegistrationSummary()
        for index, (fact_type, value) in enumerate(items):
            grounded = ground_item(extraction, fact_type, value, policy=self.policy)
            # A page citation is a safety boundary, not a best-effort enrichment.  A
            # proposed value without its primary value on the source page must be
            # surfaced for review rather than written as a candidate with a synthetic
            # "no evidence" citation.
            if not grounded.anchored or grounded.confidence_score <= 0:
                summary.unanchored += 1
                continue
            candidate = candidate_from_grounded(
                grounded,
                patient_id=patient_id,
                document_id=document_id,
                extraction=extraction,
                index=index,
                model_version=model_version,
            )
            fact = self.registry.create_candidate(candidate, actor_id=actor_id)
            summary.created += 1
            summary.fact_ids.append(str(fact.get("id")))
            if grounded.confidence_band is ConfidenceBand.LOW:
                summary.low_confidence += 1
        return summary


# ── Helpers ──────────────────────────────────────────────


def _anchor_attributes(
    extraction: DocumentExtraction,
    fact_type: str,
    value: dict[str, Any],
    policy: DocumentIntelligencePolicy,
) -> tuple[dict[str, EvidenceAnchor], list[str]]:
    anchors: dict[str, EvidenceAnchor] = {}
    uncertainty: list[str] = []
    for field in ANCHOR_FIELDS.get(fact_type, ("name",)):
        raw = value.get(field)
        text = str(raw).strip() if raw is not None else ""
        if text.casefold() in _PLACEHOLDER_VALUES:
            continue
        anchor = anchor_value(extraction, text, policy=policy)
        if anchor is None:
            uncertainty.append(
                f"The {field} '{text}' was not found in the source text; "
                "it may have been inferred rather than read."
            )
            continue
        anchors[field] = anchor
        if anchor.match_score < 1.0:
            uncertainty.append(
                f"The {field} matched the source approximately "
                f"(similarity {anchor.match_score:.2f}): '{anchor.matched_text}'."
            )
    return anchors, uncertainty


def _check_claimed_evidence(
    extraction: DocumentExtraction,
    value: dict[str, Any],
    anchors: dict[str, EvidenceAnchor],
) -> list[str]:
    """Compare model-cited evidence with what the page text actually contains."""
    claimed = value.get("evidence")
    if not isinstance(claimed, list):
        return []
    notes: list[str] = []
    anchored_pages = {anchor.page_number for anchor in anchors.values()}
    for item in claimed:
        if not isinstance(item, dict):
            continue
        page_number = item.get("page")
        excerpt = str(item.get("excerpt") or "")
        page = extraction.page(page_number) if isinstance(page_number, int) else None
        if page is None:
            notes.append(f"Model-cited page {page_number!r} does not exist in the document.")
            continue
        if normalize_for_match(excerpt) not in normalize_for_match(page.text):
            notes.append(f"Model-cited excerpt was not found on page {page_number}.")
        elif anchored_pages and page_number not in anchored_pages:
            notes.append(
                f"Model cited page {page_number} but the value was read on page(s) "
                f"{', '.join(str(number) for number in sorted(anchored_pages))}."
            )
    return notes


def _confidence_score(anchors: dict[str, EvidenceAnchor], primary_field: str) -> float:
    """The weakest anchored attribute bounds the item; no primary anchor means zero."""
    if primary_field not in anchors:
        return 0.0
    return round(min(anchor.match_score * anchor.word_confidence for anchor in anchors.values()), 3)


def _page_quality_notes(extraction: DocumentExtraction, pages: list[int]) -> list[str]:
    notes: list[str] = []
    for page_number in pages:
        page = extraction.page(page_number)
        if page is not None and page.quality is PageQuality.LOW:
            notes.append(
                f"Page {page_number} OCR quality is low "
                f"(confidence {page.confidence:.2f}); verify against the original image."
            )
    return notes


def _grounded_evidence(field: str, anchor: EvidenceAnchor) -> GroundedEvidence:
    return GroundedEvidence(
        page=anchor.page_number,
        excerpt=anchor.quote,
        confidence=round(anchor.match_score * anchor.word_confidence, 3),
        field=field,
        location={
            "scope": "page",
            "page": anchor.page_number,
            "bbox": anchor.bbox.model_dump(),
            "unit": anchor.coordinate_unit,
            "field": field,
            "matched_text": anchor.matched_text,
            "match_score": anchor.match_score,
            "word_confidence": anchor.word_confidence,
            "method": anchor.method.value,
            "line_ids": anchor.line_ids,
            "anchored": True,
        },
    )


def _citations(item: GroundedItem) -> list[EvidenceCitationCreate]:
    if not item.evidence:
        return [
            EvidenceCitationCreate(
                excerpt=(
                    f"No source text matched this {item.fact_type}; review the original document."
                ),
                location={"scope": "document", "anchored": False},
            )
        ]
    return [
        EvidenceCitationCreate(excerpt=evidence.excerpt, location=evidence.location)
        for evidence in item.evidence
    ]
