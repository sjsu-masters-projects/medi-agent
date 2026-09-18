"""Grounded document candidates retain both model and extractor provenance."""

from unittest.mock import MagicMock
from uuid import UUID

from app.services.document_intelligence.grounding import DocumentEvidenceCandidateService
from app.services.document_intelligence.models import (
    BoundingBox,
    DocumentClass,
    DocumentExtraction,
    ExtractionMethod,
    ExtractionRoute,
    PageClass,
    PageExtraction,
    PageQuality,
    TextLine,
    WordBox,
)

DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000111")
PATIENT_ID = UUID("00000000-0000-0000-0000-000000000222")
UPLOADER_ID = UUID("00000000-0000-0000-0000-000000000333")


def _extraction() -> DocumentExtraction:
    box = BoundingBox(x0=10, y0=10, x1=90, y1=25)
    page = PageExtraction(
        page_number=1,
        page_class=PageClass.BORN_DIGITAL_TEXT,
        method=ExtractionMethod.EMBEDDED_TEXT,
        width=612,
        height=792,
        words=[
            WordBox(
                text="Hypertension",
                bbox=box,
                confidence=1.0,
                line_id=0,
                method=ExtractionMethod.EMBEDDED_TEXT,
            )
        ],
        lines=[TextLine(line_id=0, text="Hypertension", bbox=box, confidence=1.0)],
        text="Hypertension",
        confidence=1.0,
        quality=PageQuality.USABLE,
    )
    return DocumentExtraction(
        document_class=DocumentClass.BORN_DIGITAL_TEXT,
        mime_type="application/pdf",
        source_sha256="a" * 64,
        page_count=1,
        pages=[page],
        route=ExtractionRoute.AUTOMATED_CANDIDATES,
        route_reason="all_pages_usable",
        extractor_version="document-intelligence/1",
    )


def _register(model_version: str | None):
    registry = MagicMock()
    registry.create_candidate.return_value = {"id": "fact-1"}
    service = DocumentEvidenceCandidateService(MagicMock(), registry=registry)
    service.register(
        patient_id=PATIENT_ID,
        actor_id=UPLOADER_ID,
        document_id=DOCUMENT_ID,
        extraction=_extraction(),
        items=[("condition", {"name": "Hypertension"})],
        model_version=model_version,
    )
    return registry.create_candidate.call_args.args[0]


def test_a_candidate_records_the_model_that_produced_it() -> None:
    candidate = _register("gemini-3.8-flash")

    assert candidate.provenance.model_version == "gemini-3.8-flash"


def test_an_unknown_model_is_recorded_as_none_rather_than_guessed() -> None:
    candidate = _register(None)

    assert candidate.provenance.model_version is None


def test_the_extractor_version_is_recorded_alongside_model_provenance() -> None:
    candidate = _register("gemini-3.8-flash")

    assert candidate.provenance.extractor_version == "document-intelligence/1"
