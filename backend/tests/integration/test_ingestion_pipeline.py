"""Integration-style tests for candidate-only ingestion and explanations."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.core.exceptions import DocumentParseError
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
    return db


@pytest.mark.asyncio
async def test_full_ingestion_pipeline_creates_candidates_not_canonical_records() -> None:
    db = _make_db()
    service = IngestionService(db)
    service._graph.ainvoke = AsyncMock(
        return_value={
            "error": None,
            "validated_data": {
                "conditions": [{"name": "Hypertension", "status": "active"}],
                "allergies": [{"allergen": "Penicillin", "severity": "mild"}],
            },
            "extracted_data": {"follow_up_instructions": [{"description": "Walk daily"}]},
            "normalized_medications": [
                {
                    "name": "Aspirin",
                    "dosage": "81 mg",
                    "frequency": "daily",
                    "route": "oral",
                }
            ],
            "patient_summary": "Take aspirin daily and walk every day.",
        }
    )
    service._register_candidates = MagicMock(return_value=4)  # type: ignore[method-assign]

    result = await service.ingest_document(
        document_id=DOCUMENT_ID,
        patient_id=PATIENT_ID,
        file_path="patient/doc.pdf",
        document_type="lab_report",
    )

    assert result["status"] == "completed"
    assert result["candidate_facts_created"] == 4
    assert result["medications_created"] == 0
    assert result["conditions_created"] == 0
    assert result["allergies_created"] == 0
    assert result["obligations_created"] == 0
    service._register_candidates.assert_called_once()
    assert db.table.call_args_list


@pytest.mark.asyncio
async def test_ingestion_pipeline_records_failed_run() -> None:
    db = _make_db()
    service = IngestionService(db)
    service._graph.ainvoke = AsyncMock(return_value={"error": "Parser failed"})

    result = await service.ingest_document(
        document_id=DOCUMENT_ID,
        patient_id=PATIENT_ID,
        file_path="patient/doc.pdf",
        document_type="lab_report",
    )

    assert result["status"] == "failed"
    assert "Parser failed" in result["error"]


@pytest.mark.asyncio
async def test_ingestion_max_retries() -> None:
    db = _make_db(parse_attempts=3)
    service = IngestionService(db)
    service._graph.ainvoke = AsyncMock()

    with pytest.raises(DocumentParseError):
        await service.ingest_document(
            document_id=DOCUMENT_ID,
            patient_id=PATIENT_ID,
            file_path="patient/doc.pdf",
            document_type="lab_report",
        )

    service._graph.ainvoke.assert_not_called()


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
