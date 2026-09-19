"""Integration-style tests for durable candidate-only document ingestion."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import DocumentParseError
from app.models.document_extraction import DocumentExtractionResult
from app.services.document_intelligence.grounding import CandidateRegistrationSummary
from app.services.document_intelligence.models import ExtractionRoute
from app.services.explanation_service import ExplanationService
from app.services.ingestion_service import IngestionService

DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000111")
PATIENT_ID = UUID("00000000-0000-0000-0000-000000000222")


def _make_table(result_data: object) -> MagicMock:
    table = MagicMock()
    for method in ["select", "eq", "single", "update", "insert"]:
        getattr(table, method).return_value = table
    table.execute.return_value = MagicMock(data=result_data)
    return table


def _make_db(parse_attempts: int = 0) -> MagicMock:
    document_table = _make_table({"parse_attempts": parse_attempts})
    run_table = _make_table([{"id": "00000000-0000-0000-0000-000000000333"}])
    tables = {"documents": document_table, "document_ingestion_runs": run_table}
    db = MagicMock()
    db.table.side_effect = lambda name: tables.get(name, _make_table([{"id": "fact-1"}]))
    if parse_attempts >= 3:
        db.rpc.side_effect = DocumentParseError(str(DOCUMENT_ID), "attempt limit reached")
    else:
        db.rpc().execute.return_value = MagicMock(
            data={
                "run_id": "00000000-0000-0000-0000-000000000333",
                "attempt": parse_attempts + 1,
                "file_path": "patient/doc.pdf",
                "document_type": "lab_report",
                "mime_type": "application/pdf",
                "content_hash": None,
            }
        )
    return db


def _model_extraction() -> DocumentExtractionResult:
    return DocumentExtractionResult.model_validate(
        {
            "medications": [
                {
                    "name": "Aspirin",
                    "dosage": "81 mg",
                    "frequency": "daily",
                    "route": "oral",
                    "evidence": [{"page": 1, "excerpt": "Aspirin 81 mg", "confidence": 0.9}],
                }
            ]
        }
    )


def _source_extraction() -> MagicMock:
    extraction = MagicMock()
    extraction.route = ExtractionRoute.AUTOMATED_CANDIDATES
    extraction.page_count = 1
    extraction.pages = []
    extraction.warnings = []
    extraction.text_for_model.return_value = "[[page 1]]\nAspirin 81 mg daily"
    return extraction


@pytest.mark.asyncio
async def test_full_ingestion_pipeline_creates_only_grounded_candidates() -> None:
    db = _make_db()
    intelligence = MagicMock()
    intelligence.extract.return_value = _source_extraction()
    service = IngestionService(db, intelligence=intelligence)
    service._extract_structured = AsyncMock(return_value=(_model_extraction(), "gemini-test"))
    service._optional_summary = AsyncMock(return_value="Take aspirin daily.")

    with patch("app.services.ingestion_service.DocumentEvidenceCandidateService") as registry:
        registry.return_value.register.return_value = CandidateRegistrationSummary(created=1)
        result = await service.ingest_document(
            document_id=DOCUMENT_ID,
            patient_id=PATIENT_ID,
            file_path="patient/doc.pdf",
            document_type="lab_report",
        )

    assert result["status"] == "completed"
    assert result["candidate_facts_created"] == 1
    registry.return_value.register.assert_called_once()
    assert db.table.call_args_list


@pytest.mark.asyncio
async def test_ingestion_records_source_failure() -> None:
    db = _make_db()
    intelligence = MagicMock()
    intelligence.extract.side_effect = ValueError("source could not be read")
    service = IngestionService(db, intelligence=intelligence)

    result = await service.ingest_document(
        document_id=DOCUMENT_ID,
        patient_id=PATIENT_ID,
        file_path="patient/doc.pdf",
        document_type="lab_report",
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "source_unreadable"


@pytest.mark.asyncio
async def test_invalid_model_shape_stops_for_clinician_review_without_another_retry() -> None:
    db = _make_db()
    intelligence = MagicMock()
    intelligence.extract.return_value = _source_extraction()
    service = IngestionService(db, intelligence=intelligence)
    with pytest.raises(PydanticValidationError) as invalid:
        DocumentExtractionResult.model_validate({"medications": [{"name": "Aspirin"}]})
    service._extract_structured = AsyncMock(side_effect=invalid.value)

    result = await service.ingest_document(
        document_id=DOCUMENT_ID,
        patient_id=PATIENT_ID,
        file_path="patient/doc.pdf",
        document_type="lab_report",
    )

    assert result["status"] == "needs_evidence_review"
    assert result["error_code"] == "invalid_model_response"
    db.table("documents").update.assert_called_once_with(
        {
            "parse_status": "needs_evidence_review",
            "parse_error": None,
            "parse_failure_code": "invalid_model_response",
            "parsed": False,
        }
    )


@pytest.mark.asyncio
async def test_ingestion_max_retries_stops_before_source_read() -> None:
    db = _make_db(parse_attempts=3)
    intelligence = MagicMock()
    service = IngestionService(db, intelligence=intelligence)

    with pytest.raises(DocumentParseError):
        await service.ingest_document(
            document_id=DOCUMENT_ID,
            patient_id=PATIENT_ID,
            file_path="patient/doc.pdf",
            document_type="lab_report",
        )

    intelligence.extract.assert_not_called()


@pytest.mark.asyncio
async def test_explain_cached_summary() -> None:
    service = ExplanationService()
    document = {"id": str(DOCUMENT_ID), "ai_summary": "Already cached"}

    with patch("app.services.explanation_service.get_router") as mock_get_router:
        summary = await service.explain(document_data=document, language="en-US")

    assert summary == "Already cached"
    mock_get_router.assert_not_called()


@pytest.mark.asyncio
async def test_explain_spanish_translation() -> None:
    service = ExplanationService()
    mock_router = MagicMock()
    mock_router.generate_text = AsyncMock(return_value="Resumen en español")

    with patch("app.services.explanation_service.get_router", return_value=mock_router):
        summary = await service.explain(
            document_data={"id": str(DOCUMENT_ID), "ai_summary": "English summary"},
            language="es-MX",
        )

    assert summary == "Resumen en español"
