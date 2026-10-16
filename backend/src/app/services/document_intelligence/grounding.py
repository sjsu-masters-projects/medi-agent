"""Ground extracted values in page evidence and register page-cited candidates.

A model may propose a medication, condition, allergy, or obligation; only the
deterministic layer decides whether the proposal was actually read on a page. The
result carries the same ``{page, excerpt, confidence}`` shape the ingestion graph
already validates, plus the region and word confidence needed for a clinician to
open the page and see the words. Nothing here writes canonical clinical records.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from supabase import Client

from app.agents.ingestion.prompts import EXTRACTION_PROMPT_VERSION
from app.models.clinical_fact import (
    ClinicalFactCreate,
    ConfidenceBand,
    EvidenceCitationCreate,
    SourceArtifactType,
    SourceProvenanceCreate,
)
from app.services.clinical_fact_service import ClinicalFactService
from app.services.document_intelligence.anchoring import (
    anchor_occurrences,
    anchor_on_page,
    anchor_value,
    normalize_for_match,
)
from app.services.document_intelligence.models import (
    DocumentExtraction,
    DocumentIntelligencePolicy,
    EvidenceAnchor,
    ExtractionRoute,
    PageQuality,
    WordBox,
)
from app.services.record_display import attach as attach_display

SOURCE_SYSTEM = "document_intelligence"
REVIEW_NOTE = "Document extraction requires clinician review before clinical use."
_PLACEHOLDER_VALUES = frozenset({"", "as directed", "unknown", "active"})

# Attributes that must be read on the page for each candidate type. The first is the
# primary anchor; a candidate whose primary value is not on any page scores zero.
ANCHOR_FIELDS: dict[str, tuple[str, ...]] = {
    "medication": (
        "name",
        "dosage",
        "frequency",
        "route",
        "instructions",
        "status",
        "generic_name",
        "rxcui",
    ),
    "condition": ("name", "status", "notes"),
    "allergy": ("allergen", "reaction", "severity"),
    "obligation": ("description", "frequency", "obligation_type"),
    "lab_result": (
        "test_name",
        "value",
        "unit",
        "reference_range",
        "flag",
        "collected_at",
        "specimen",
        "panel",
    ),
    "vital_sign": ("name", "value", "unit", "measured_at"),
    "immunization": ("vaccine", "administered_at", "dose_number"),
    "procedure": ("name", "performed_at", "result"),
    "appointment": ("description", "scheduled_for", "provider", "location"),
}
# Fields that must be read on the same printed row as the primary value. A short value
# such as "14" can appear many times on a report; only the copy beside the test name counts.
ROW_FIELDS: dict[str, frozenset[str]] = {
    "lab_result": frozenset({"value", "unit", "reference_range", "flag"}),
    "vital_sign": frozenset({"value", "unit"}),
}
# Fields without which a candidate is meaningless; all must be anchored.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "lab_result": ("test_name", "value"),
    "vital_sign": ("name", "value"),
}
# A printed number must match exactly: 7.8 and 7.9 are different results.
EXACT_FIELDS = frozenset({"value"})
# Results stay review-only evidence: they never become care-plan items.
CARE_PLAN_FACT_TYPES = frozenset({"medication", "obligation"})


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
    fact_types: set[str] = Field(default_factory=set)

    @property
    def informs_care_plan(self) -> bool:
        """Only medications and patient obligations can become care-plan proposals."""
        return bool(self.fact_types & CARE_PLAN_FACT_TYPES)


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
    source_value, dropped_fields = _source_backed_value(fact_type, value, anchors)
    uncertainty.extend(
        f"The {field} was omitted because it could not be located in the source text."
        for field in dropped_fields
    )
    required = REQUIRED_FIELDS.get(fact_type, (ANCHOR_FIELDS.get(fact_type, ("name",))[0],))
    score = _confidence_score(anchors, required)
    if fact_type == "lab_result" and score > 0:
        source_value.update(result_interpretation(source_value))
        disagreement = source_value.get("consistency")
        if disagreement:
            uncertainty.append(str(disagreement))
            # A flag that contradicts its own range is most often an OCR error (a dropped
            # decimal point); never let it present as a confident reading.
            score = min(score, policy.medium_confidence - 0.01)
        if source_value.get("flag_meaning") == "critical":
            uncertainty.append("The report marks this result as critical.")
    if fact_type == "medication" and score > 0:
        action = medication_action(source_value.get("status"))
        if action is not None:
            source_value["medication_action"] = action
            if action in INACTIVE_MEDICATION_ACTIONS:
                verb = {"stopped": "stop", "held": "hold"}[action]
                uncertainty.append(
                    f"The document says to {verb} this medication; "
                    "it must not become an active care-plan item."
                )
    evidence = [_grounded_evidence(field, anchor) for field, anchor in anchors.items()]
    primary_field = ANCHOR_FIELDS.get(fact_type, ("name",))[0]
    row_fields = ROW_FIELDS.get(fact_type)
    if row_fields and primary_field in anchors:
        # A result's evidence is its whole printed row ("Creatinine | 1.42 | H | mg/dL |
        # 0.74 - 1.35"), not the one cell a value was found in; the reviewer reads the row.
        row = _printed_row(extraction, anchors[primary_field])
        if row:
            evidence = [
                item.model_copy(update={"excerpt": row})
                if item.field == primary_field or item.field in row_fields
                else item
                for item in evidence
            ]
    evidence.sort(key=lambda item: item.field != primary_field)
    pages = sorted({item.page for item in evidence})
    return GroundedItem(
        fact_type=fact_type,
        value=source_value,
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
                "prompt_version": EXTRACTION_PROMPT_VERSION,
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
        ("lab_result", "lab_results"),
        ("vital_sign", "vital_signs"),
        ("immunization", "immunizations"),
        ("procedure", "procedures"),
        ("appointment", "appointments"),
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
        english_display: Mapping[int, Mapping[str, Any]] | None = None,
    ) -> CandidateRegistrationSummary:
        """Register grounded candidates; ``english_display`` is keyed by item position.

        English display text is attached after grounding, so it covers only the printed
        fields that were found on a page; it never decides whether a fact is registered.
        """
        if extraction.route in (ExtractionRoute.REJECTED, ExtractionRoute.CLINICIAN_ONLY):
            raise ValueError(
                f"Extraction route {extraction.route.value!r} does not permit candidates"
            )
        summary = CandidateRegistrationSummary()
        for index, (fact_type, value) in enumerate(items):
            grounded = ground_item(extraction, fact_type, value, policy=self.policy)
            if english_display and index in english_display:
                grounded.value = attach_display(grounded.value, english_display[index])
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
            summary.fact_types.add(fact_type)
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
    fields = ANCHOR_FIELDS.get(fact_type, ("name",))
    row_fields = ROW_FIELDS.get(fact_type, frozenset())
    for field in fields:
        raw = value.get(field)
        text = str(raw).strip() if raw is not None else ""
        if text.casefold() in _PLACEHOLDER_VALUES:
            continue
        if field in row_fields:
            primary = anchors.get(fields[0])
            anchor = (
                _anchor_on_row(extraction, primary, text, policy=policy)
                if primary is not None
                else None
            )
        elif field == fields[0] and row_fields:
            anchor = _row_primary(extraction, fields, row_fields, value, text, policy)
        elif field != fields[0] and fields[0] in anchors:
            anchor = _near_primary(extraction, anchors[fields[0]], text, policy)
        else:
            anchor = anchor_value(extraction, text, policy=policy)
        if anchor is not None and field in EXACT_FIELDS and anchor.match_score < 1.0:
            anchor = None
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


def _source_backed_value(
    fact_type: str, value: dict[str, Any], anchors: dict[str, EvidenceAnchor]
) -> tuple[dict[str, Any], list[str]]:
    """Persist only source-located clinical values, never an LLM-only interpretation."""
    stored = {key: item for key, item in value.items() if key != "evidence"}
    dropped: list[str] = []
    for field in ANCHOR_FIELDS.get(fact_type, ("name",)):
        if field not in stored or field in anchors:
            continue
        raw = stored.get(field)
        if raw is None or str(raw).strip().casefold() in _PLACEHOLDER_VALUES:
            stored.pop(field, None)
            continue
        stored.pop(field, None)
        dropped.append(field)
    return stored, dropped


def _row_primary(
    extraction: DocumentExtraction,
    fields: tuple[str, ...],
    row_fields: frozenset[str],
    value: dict[str, Any],
    text: str,
    policy: DocumentIntelligencePolicy,
) -> EvidenceAnchor | None:
    """The printed copy of a result's name whose row also carries its value and unit.

    "Hemoglobin A1c" in the heading "LIPID PANEL AND HEMOGLOBIN A1C" is an exact match too,
    and it comes first; anchoring there found no 8.1 on that line and dropped the result.
    """
    occurrences = anchor_occurrences(extraction, text, policy=policy)
    if len(occurrences) < 2:
        return occurrences[0] if occurrences else None

    def found_on_row(candidate: EvidenceAnchor) -> int:
        count = 0
        for field in fields[1:]:
            if field not in row_fields:
                continue
            raw = value.get(field)
            wanted = str(raw).strip() if raw is not None else ""
            if wanted.casefold() in _PLACEHOLDER_VALUES:
                continue
            anchor = _anchor_on_row(extraction, candidate, wanted, policy=policy)
            if anchor is not None and (field not in EXACT_FIELDS or anchor.match_score >= 1.0):
                count += 1
        return count

    # Ties keep the earlier, better-matching copy, which is the previous behaviour.
    return max(occurrences, key=lambda candidate: (found_on_row(candidate), candidate.match_score))


def _near_primary(
    extraction: DocumentExtraction,
    primary: EvidenceAnchor,
    text: str,
    policy: DocumentIntelligencePolicy,
) -> EvidenceAnchor | None:
    """The printed copy of an attribute nearest its item's name, preferring lines below it.

    "1 tablet by mouth daily" or "Continue" can belong to any medication in a list; the
    first copy on the page cited Metformin's line as Atorvastatin's dose.
    """
    occurrences = anchor_occurrences(extraction, text, policy=policy)
    if len(occurrences) < 2:
        return occurrences[0] if occurrences else None
    best = occurrences[0].match_score
    slack = 0.35 * max(primary.bbox.y1 - primary.bbox.y0, 1.0)

    def distance(candidate: EvidenceAnchor) -> tuple[int, int, float]:
        if candidate.page_number != primary.page_number:
            return (1, abs(candidate.page_number - primary.page_number), 0.0)
        offset = candidate.bbox.y0 - primary.bbox.y0
        return (0, 0 if offset >= -slack else 1, abs(offset))

    # Only equally good matches compete; a closer but weaker copy never wins.
    return min((item for item in occurrences if item.match_score >= best), key=distance)


def _anchor_on_row(
    extraction: DocumentExtraction,
    primary: EvidenceAnchor,
    value: str,
    *,
    policy: DocumentIntelligencePolicy,
) -> EvidenceAnchor | None:
    """Anchor ``value`` only among the words printed on the primary value's row."""
    page = extraction.page(primary.page_number)
    if page is None:
        return None
    top, bottom = primary.bbox.y0, primary.bbox.y1
    slack = 0.35 * max(bottom - top, 1.0)

    def on_row(word: WordBox) -> bool:
        middle = (word.bbox.y0 + word.bbox.y1) / 2
        return top - slack <= middle <= bottom + slack

    row_page = page.model_copy(update={"words": [word for word in page.words if on_row(word)]})
    return anchor_on_page(row_page, value, policy=policy)


def _printed_row(extraction: DocumentExtraction, primary: EvidenceAnchor) -> str:
    """The text of the printed row the primary value sits on, left to right."""
    page = extraction.page(primary.page_number)
    if page is None:
        return ""
    top, bottom = primary.bbox.y0, primary.bbox.y1
    slack = 0.35 * max(bottom - top, 1.0)
    cells = [
        line
        for line in page.lines
        if top - slack <= (line.bbox.y0 + line.bbox.y1) / 2 <= bottom + slack
    ]
    return " | ".join(line.text for line in sorted(cells, key=lambda line: line.bbox.x0))[:2000]


def _confidence_score(anchors: dict[str, EvidenceAnchor], required: Sequence[str]) -> float:
    """The weakest anchored attribute bounds the item; a missing required anchor means zero."""
    if any(field not in anchors for field in required):
        return 0.0
    return round(min(anchor.match_score * anchor.word_confidence for anchor in anchors.values()), 3)


# Printed flags, in English and Spanish. "A" is "abnormal" in English reports and "alto"
# in Spanish ones, so it only ever means "outside the range", never a direction.
_CRITICAL_FLAGS = frozenset(
    {"hh", "ll", "c", "crit", "critical", "critico", "panic", "panico", "!!", "*h", "*l"}
)
_HIGH_FLAGS = frozenset({"h", "hi", "high", "alto", "elevado", "↑"})
_LOW_FLAGS = frozenset({"l", "lo", "low", "bajo", "↓"})
_ABNORMAL_FLAGS = frozenset({"a", "abn", "abnormal", "anormal", "*", "!"})
_NUMBER = r"[-+]?\d+(?:[.,]\d+)?"
_RANGE_BETWEEN = re.compile(rf"^\s*({_NUMBER})\s*(?:-|–|—|to|a)\s*({_NUMBER})\s*$", re.I)
_RANGE_BOUND = re.compile(rf"^\s*(<=|>=|≤|≥|<|>)\s*({_NUMBER})\s*$")
_PLAIN_VALUE = re.compile(rf"^\s*({_NUMBER})\s*$")


def _number(text: str) -> float:
    return float(text.replace(",", "."))


# Printed medication actions, in English and Spanish, checked in this order. A stop or hold
# word wins over any other, so "do not stop" is read as a stop: that blocks the plan for
# clinician review instead of silently continuing a medicine the document may have ended.
INACTIVE_MEDICATION_ACTIONS = frozenset({"stopped", "held"})
_MEDICATION_ACTION_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "stopped",
        ("stop", "discontinu", "d/c", "dc'd", "cease", "suspend", "suspender", "deje de"),
    ),
    ("held", ("hold", "pause", "withhold", "no tomar hasta", "pausar")),
    ("continued", ("no change", "unchanged", "sin cambio", "same dose", "misma dosis")),
    (
        "changed",
        ("change", "increase", "decrease", "reduce", "adjust", "cambi", "aument", "disminu"),
    ),
    ("new", ("new", "start", "begin", "initiat", "nuevo", "nueva", "inici", "empez", "comenz")),
    ("continued", ("continu", "same", "no change", "sin cambio", "seguir", "siga")),
)


def medication_action(status: str | None) -> str | None:
    """Classify a printed medication action; text that names no action stays unknown."""
    if not status or not status.strip():
        return None
    folded = unicodedata.normalize("NFKD", status)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch)).casefold()
    for action, words in _MEDICATION_ACTION_WORDS:
        if any(re.search(rf"(?<![a-z]){re.escape(word)}", folded) for word in words):
            return action
    return "unknown"


def flag_meaning(flag: str | None) -> str | None:
    """Translate a printed flag to high/low/abnormal/critical; unknown flags stay unknown."""
    if not flag:
        return None
    folded = unicodedata.normalize("NFKD", flag)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch)).strip().casefold()
    folded = folded.strip("() ")
    if folded in _CRITICAL_FLAGS:
        return "critical"
    if folded in _HIGH_FLAGS:
        return "high"
    if folded in _LOW_FLAGS:
        return "low"
    if folded in _ABNORMAL_FLAGS:
        return "abnormal"
    return "unrecognized"


def range_status(value: str | None, reference_range: str | None) -> str | None:
    """Compare a plain printed number with a plain printed range: below/within/above.

    Anything else (qualifiers such as "<5", text results, ranges with words or units) is
    left undetermined rather than guessed.
    """
    if not value or not reference_range:
        return None
    number = _PLAIN_VALUE.match(value)
    if number is None:
        return None
    result = _number(number.group(1))
    between = _RANGE_BETWEEN.match(reference_range)
    if between:
        low, high = _number(between.group(1)), _number(between.group(2))
        if low > high:
            return None
        return "below" if result < low else "above" if result > high else "within"
    bound = _RANGE_BOUND.match(reference_range)
    if bound:
        operator, limit = bound.group(1), _number(bound.group(2))
        if operator in ("<", "<=", "≤"):
            inside = result < limit if operator == "<" else result <= limit
            return "within" if inside else "above"
        inside = result > limit if operator == ">" else result >= limit
        return "within" if inside else "below"
    return None


def result_interpretation(value: dict[str, Any]) -> dict[str, Any]:
    """Deterministic reading of a result's own printed flag and range; never a model's."""
    meaning = flag_meaning(value.get("flag"))
    status = range_status(value.get("value"), value.get("reference_range"))
    derived: dict[str, Any] = {}
    if meaning is not None:
        derived["flag_meaning"] = meaning
    if status is not None:
        derived["range_status"] = status
    contradiction = (meaning == "high" and status in ("below", "within")) or (
        meaning == "low" and status in ("above", "within")
    )
    if contradiction:
        derived["consistency"] = (
            f"The printed flag '{value.get('flag')}' does not match the value "
            f"'{value.get('value')}' and range '{value.get('reference_range')}'; "
            "verify all three against the original document."
        )
    elif meaning is None and status in ("above", "below"):
        derived["consistency"] = (
            f"The value '{value.get('value')}' is outside the printed range "
            f"'{value.get('reference_range')}' but no flag was read; verify against the original."
        )
    return derived


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
