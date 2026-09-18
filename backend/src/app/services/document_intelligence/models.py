"""Deterministic document-intelligence contracts.

Extraction output is evidence, never clinical truth. These models describe what an
extractor saw on each page, how confident it is, and exactly where it saw it, so that
every candidate fact can cite a page, a region, and a source quote. Nothing here
writes to canonical clinical tables.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.clinical_fact import ConfidenceBand


class DocumentClass(StrEnum):
    """What kind of artifact the whole upload turned out to be."""

    BORN_DIGITAL_TEXT = "born_digital_text"
    SCANNED_IMAGE = "scanned_image"
    MIXED = "mixed"
    BLANK = "blank"
    UNREADABLE = "unreadable"
    ENCRYPTED = "encrypted"
    UNSUPPORTED = "unsupported"


class PageClass(StrEnum):
    """What one page contains, decided before any OCR runs."""

    BORN_DIGITAL_TEXT = "born_digital_text"
    SCANNED_IMAGE = "scanned_image"
    MIXED = "mixed"
    BLANK = "blank"
    UNREADABLE = "unreadable"


class ExtractionMethod(StrEnum):
    EMBEDDED_TEXT = "embedded_text"
    OCR = "ocr"
    NONE = "none"


class PageQuality(StrEnum):
    """How a page's text may be used downstream."""

    USABLE = "usable"
    LOW = "low"
    UNUSABLE = "unusable"
    EMPTY = "empty"


class ExtractionRoute(StrEnum):
    """Where the document goes after deterministic extraction.

    Every candidate remains ``pending_review`` regardless of route; the route decides
    whether model extraction may even be attempted and how loudly the result is flagged.
    """

    AUTOMATED_CANDIDATES = "automated_candidates"
    REVIEW_WITH_CAUTION = "review_with_caution"
    CLINICIAN_ONLY = "clinician_only"
    REJECTED = "rejected"


class FailureKind(StrEnum):
    NONE = "none"
    PERMANENT = "permanent"
    TRANSIENT = "transient"


class BoundingBox(BaseModel):
    """Axis-aligned region in the page's coordinate unit (see ``PageExtraction``)."""

    x0: float
    y0: float
    x1: float
    y1: float

    def union(self, other: BoundingBox) -> BoundingBox:
        return BoundingBox(
            x0=min(self.x0, other.x0),
            y0=min(self.y0, other.y0),
            x1=max(self.x1, other.x1),
            y1=max(self.y1, other.y1),
        )

    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)

    def overlap_ratio(self, other: BoundingBox) -> float:
        """Fraction of this box covered by ``other``."""
        width = min(self.x1, other.x1) - max(self.x0, other.x0)
        height = min(self.y1, other.y1) - max(self.y0, other.y0)
        if width <= 0 or height <= 0:
            return 0.0
        own_area = self.area()
        return (width * height) / own_area if own_area else 0.0


class WordBox(BaseModel):
    text: str
    bbox: BoundingBox
    confidence: float = Field(ge=0.0, le=1.0)
    line_id: int
    method: ExtractionMethod


class TextLine(BaseModel):
    line_id: int
    text: str
    bbox: BoundingBox
    confidence: float = Field(ge=0.0, le=1.0)


class TableCell(BaseModel):
    row: int
    col: int
    text: str
    bbox: BoundingBox


class TableExtraction(BaseModel):
    bbox: BoundingBox
    row_count: int
    col_count: int
    cells: list[TableCell] = Field(default_factory=list)


class PageExtraction(BaseModel):
    """Everything the deterministic layer knows about one page."""

    page_number: int = Field(ge=1)
    page_class: PageClass
    method: ExtractionMethod
    coordinate_unit: str = "pt"
    width: float
    height: float
    source_rotation: int = 0
    rotation_applied: int = 0
    render_dpi: int | None = None
    languages: list[str] = Field(default_factory=list)
    words: list[WordBox] = Field(default_factory=list)
    lines: list[TextLine] = Field(default_factory=list)
    tables: list[TableExtraction] = Field(default_factory=list)
    text: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    quality: PageQuality = PageQuality.EMPTY
    warnings: list[str] = Field(default_factory=list)
    latency_ms: int = 0

    @property
    def has_words(self) -> bool:
        return bool(self.words)


class DocumentExtraction(BaseModel):
    """The versioned, retained record of one extraction run over one source file."""

    document_class: DocumentClass
    mime_type: str
    file_name: str | None = None
    source_sha256: str
    page_count: int = 0
    pages: list[PageExtraction] = Field(default_factory=list)
    route: ExtractionRoute
    route_reason: str
    failure_kind: FailureKind = FailureKind.NONE
    repaired: bool = False
    extractor_version: str
    engine_versions: dict[str, str] = Field(default_factory=dict)
    languages_requested: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    latency_ms: int = 0

    @property
    def content_pages(self) -> list[PageExtraction]:
        return [page for page in self.pages if page.page_class is not PageClass.BLANK]

    def model_input_pages(self) -> list[PageExtraction]:
        """Pages whose text may be shown to an extraction model."""
        return [
            page
            for page in self.pages
            if page.quality in (PageQuality.USABLE, PageQuality.LOW) and page.has_words
        ]

    def text_for_model(self) -> str:
        """Page-delimited text that excludes unusable pages entirely.

        A page below the usable floor is not summarized, paraphrased, or partially
        included: garbled OCR is the input most likely to make a model invent a dose.
        """
        return "\n\n".join(
            f"[[page {page.page_number}]]\n{page.text}" for page in self.model_input_pages()
        )

    def page(self, page_number: int) -> PageExtraction | None:
        return next((page for page in self.pages if page.page_number == page_number), None)


class EvidenceAnchor(BaseModel):
    """Where a value was actually read on the page."""

    page_number: int
    bbox: BoundingBox
    coordinate_unit: str
    quote: str
    matched_text: str
    match_score: float = Field(ge=0.0, le=1.0)
    word_confidence: float = Field(ge=0.0, le=1.0)
    method: ExtractionMethod
    line_ids: list[int] = Field(default_factory=list)


class DocumentIntelligencePolicy(BaseModel):
    """Thresholds and limits for extraction, quality routing, and anchoring.

    Values are the calibrated defaults from the synthetic benchmark recorded in
    ``.agent/specs/rec-003-document-intelligence-plan.md``; change them there first.
    """

    render_dpi: int = 300
    min_raster_side_px: int = 1000
    languages: list[str] = Field(default_factory=lambda: ["eng", "spa"])
    ocr_enabled: bool = True
    high_confidence: float = 0.90
    medium_confidence: float = 0.75
    page_usable_floor: float = 0.50
    rotation_search_below: float = 0.60
    min_text_chars: int = 20
    embedded_text_sanity_floor: float = 0.60
    mixed_page_image_coverage: float = 0.10
    min_region_coverage: float = 0.02
    scanned_page_image_coverage: float = 0.05
    blank_ink_ratio: float = 0.002
    anchor_min_similarity: float = 0.85
    max_pages: int = 50
    ocr_timeout_seconds: int = 60
    max_quote_chars: int = 300

    def band(self, score: float | None) -> ConfidenceBand:
        if score is None:
            return ConfidenceBand.UNKNOWN
        if score >= self.high_confidence:
            return ConfidenceBand.HIGH
        if score >= self.medium_confidence:
            return ConfidenceBand.MEDIUM
        return ConfidenceBand.LOW

    def page_quality(self, confidence: float, *, has_words: bool) -> PageQuality:
        if not has_words:
            return PageQuality.EMPTY
        if confidence >= self.medium_confidence:
            return PageQuality.USABLE
        if confidence >= self.page_usable_floor:
            return PageQuality.LOW
        return PageQuality.UNUSABLE
