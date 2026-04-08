"""Integration-style tests for ingestion orchestration and explanation flow."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.core.exceptions import DocumentParseError
from app.services.explanation_service import ExplanationService
from app.services.ingestion_service import IngestionService

DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000111")
PATIENT_ID = UUID("00000000-0000-0000-0000-000000000222")


def _make_table(result_data):
    table = MagicMock()
    for method in ["select", "eq", "single", "update", "insert"]:
        getattr(table, method).return_value = table
    table.execute.return_value = MagicMock(data=result_data)
    return table


def _make_db(parse_attempts: int = 0):
    documents_table = _make_table({"parse_attempts": parse_attempts})
    conditions_table = _make_table([{"id": "condition-1"}])
    allergies_table = _make_table([{"id": "allergy-1"}])

    tables = {
        "documents": documents_table,
        "conditions": conditions_table,
        "allergies": allergies_table,
    }

    db = MagicMock()
    db.table.side_effect = lambda name: tables[name]
    return db


@pytest.mark.asyncio
async def test_full_ingestion_pipeline():
    db = _make_db()
    service = IngestionService(db)
    service._graph.ainvoke = AsyncMock(
        return_value={
            "error": None,
            "validated_data": {
                "conditions": [{"name": "Hypertension", "status": "active"}],
                "allergies": [{"allergen": "Penicillin", "severity": "moderate"}],
            },
            "extracted_data": {
                "follow_up_instructions": [{"description": "Walk daily", "timing": "daily"}]
            },
            "normalized_medications": [
                {
                    "name": "Aspirin",
                    "generic_name": "aspirin",
                    "rxcui": "1191",
                    "dosage": "81mg",
                    "frequency": "daily",
                    "route": "oral",
                }
            ],
            "patient_summary": "Take aspirin daily and walk every day.",
        }
    )
    service._med_service.create_medication = AsyncMock(return_value={"id": "med-1"})
    service._obligation_service.create_obligation = AsyncMock(return_value={"id": "obl-1"})

    result = await service.ingest_document(
        document_id=DOCUMENT_ID,
        patient_id=PATIENT_ID,
        file_path="patient/doc.pdf",
        document_type="lab_report",
    )

    assert result["status"] == "completed"
    assert result["medications_created"] == 1
    assert result["obligations_created"] == 1
    service._med_service.create_medication.assert_awaited()
    service._obligation_service.create_obligation.assert_awaited()
    assert db.table("documents").update.call_count >= 2


@pytest.mark.asyncio
async def test_ingestion_pipeline_llm_failure():
    db = _make_db()
    service = IngestionService(db)
    service._graph.ainvoke = AsyncMock(return_value={"error": "LLM crashed"})

    result = await service.ingest_document(
        document_id=DOCUMENT_ID,
        patient_id=PATIENT_ID,
        file_path="patient/doc.pdf",
        document_type="lab_report",
    )

    assert result["status"] == "failed"
    assert "LLM crashed" in result["error"]


@pytest.mark.asyncio
async def test_ingestion_pipeline_rxnorm_failure():
    db = _make_db()
    service = IngestionService(db)
    service._graph.ainvoke = AsyncMock(
        return_value={
            "error": None,
            "validated_data": {"conditions": [], "allergies": []},
            "extracted_data": {"follow_up_instructions": []},
            "normalized_medications": [
                {
                    "name": "Aspirin",
                    "generic_name": "Aspirin",
                    "rxcui": None,
                    "dosage": "81mg",
                    "frequency": "daily",
                    "route": "oral",
                }
            ],
            "patient_summary": "Take aspirin daily.",
        }
    )
    service._med_service.create_medication = AsyncMock(return_value={"id": "med-1"})
    service._obligation_service.create_obligation = AsyncMock(return_value={"id": "obl-1"})

    result = await service.ingest_document(
        document_id=DOCUMENT_ID,
        patient_id=PATIENT_ID,
        file_path="patient/doc.pdf",
        document_type="prescription",
    )

    assert result["status"] == "completed"
    payload = service._med_service.create_medication.await_args_list[0].args[1]
    assert payload["rxcui"] is None


@pytest.mark.asyncio
async def test_ingestion_max_retries():
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
async def test_explain_cached_summary():
    service = ExplanationService()
    document = {"id": str(DOCUMENT_ID), "ai_summary": "Already cached"}

    with patch("app.services.explanation_service.get_router") as mock_get_router:
        summary = await service.explain(document_data=document, language="en")

    assert summary == "Already cached"
    mock_get_router.assert_not_called()


@pytest.mark.asyncio
async def test_explain_spanish_translation():
    service = ExplanationService()
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(return_value="Resumen en español")
    mock_router = MagicMock()
    mock_router.get_client_with_fallback.return_value = mock_client

    with patch(
        "app.services.explanation_service.get_router",
        return_value=mock_router,
    ):
        summary = await service.explain(
            document_data={"id": str(DOCUMENT_ID), "ai_summary": "English summary"},
            language="es",
        )

    assert summary == "Resumen en español"
