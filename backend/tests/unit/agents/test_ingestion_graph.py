"""Tests for IngestionState and graph creation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.ingestion.graph import IngestionState, create_ingestion_graph


def test_ingestion_state_structure():
    state: IngestionState = {
        "document_id": "doc-123",
        "file_url": "patient/doc.pdf",
        "document_type": "lab_report",
        "patient_id": "patient-456",
        "raw_content": None,
        "extracted_data": None,
        "validated_data": None,
        "validation_errors": None,
        "normalized_medications": None,
        "saved_ids": None,
        "patient_summary": None,
        "created_tasks": None,
        "error": None,
        "retry_count": 0,
        "messages": [],
    }

    assert state["file_url"] == "patient/doc.pdf"
    assert state["raw_content"] is None
    assert state["created_tasks"] is None


def test_create_ingestion_graph():
    graph = create_ingestion_graph()

    assert graph is not None


def test_ingestion_state_saved_ids_structure():
    state: IngestionState = {
        "document_id": "doc-123",
        "file_url": "patient/doc.pdf",
        "document_type": "lab_report",
        "patient_id": "patient-456",
        "raw_content": None,
        "extracted_data": None,
        "validated_data": None,
        "validation_errors": None,
        "normalized_medications": None,
        "saved_ids": {
            "medications": ["med-1", "med-2"],
            "conditions": ["cond-1"],
            "appointments": [],
        },
        "patient_summary": None,
        "created_tasks": None,
        "error": None,
        "retry_count": 0,
        "messages": [],
    }

    assert len(state["saved_ids"]["medications"]) == 2
    assert len(state["saved_ids"]["conditions"]) == 1


@pytest.mark.asyncio
async def test_receive_document():
    from app.agents.ingestion.graph import receive_document

    bucket = MagicMock()
    bucket.download.return_value = b"plain text document"
    admin = MagicMock()
    admin.storage.from_.return_value = bucket

    pil_module = MagicMock()
    pil_module.Image = MagicMock()
    with (
        patch("app.clients.supabase.get_admin_client", return_value=admin),
        patch.dict(
            "sys.modules",
            {
                "fitz": MagicMock(),
                "pytesseract": MagicMock(),
                "PIL": pil_module,
            },
        ),
    ):
        state = {
            "document_id": "123",
            "file_url": "patient/doc.txt",
            "document_type": "other",
        }
        result = await receive_document(state)

    assert result["raw_content"] == "plain text document"
    assert result["error"] is None


@pytest.mark.asyncio
async def test_extract_content_success():
    from app.agents.ingestion.graph import extract_content

    with patch("app.agents.ingestion.graph.get_router") as mock_get_router:
        mock_client = AsyncMock()
        mock_client.generate.return_value = '```json\n{"medications": [], "conditions": []}\n```'
        mock_router = MagicMock()
        mock_router.get_client_with_fallback.return_value = mock_client
        mock_get_router.return_value = mock_router

        state = {"document_id": "123", "raw_content": "Some text"}
        result = await extract_content(state)

    assert result["extracted_data"] == {"medications": [], "conditions": []}
    assert result["raw_content"] is None
    assert result["error"] is None


@pytest.mark.asyncio
async def test_extract_content_failure():
    from app.agents.ingestion.graph import extract_content

    with patch("app.agents.ingestion.graph.get_router") as mock_get_router:
        mock_router = MagicMock()
        mock_router.get_client_with_fallback.side_effect = Exception("Router failed")
        mock_get_router.return_value = mock_router

        state = {"document_id": "123", "raw_content": "Some text"}
        result = await extract_content(state)

    assert result["error"] == "Router failed"


@pytest.mark.asyncio
async def test_validate_fhir():
    from app.agents.ingestion.graph import validate_fhir

    with patch(
        "app.tools.fhir_builder.validate_extracted_data",
        return_value=({"medications": [{"name": "Aspirin"}]}, []),
    ):
        state = {
            "document_id": "00000000-0000-0000-0000-000000000123",
            "patient_id": "00000000-0000-0000-0000-000000000456",
            "extracted_data": {"medications": [{"name": "Aspirin"}]},
        }
        result = await validate_fhir(state)

    assert result["validated_data"] == {"medications": [{"name": "Aspirin"}]}
    assert result["validation_errors"] is None


@pytest.mark.asyncio
async def test_normalize_medications():
    from app.agents.ingestion.graph import normalize_medications

    with patch(
        "app.tools.medication_normalizer.normalize_all",
        new=AsyncMock(return_value=[{"name": "Aspirin", "dosage": "81mg"}]),
    ):
        state = {
            "document_id": "123",
            "validated_data": {"medications": [{"name": "Aspirin", "dosage": "81mg"}]},
        }
        result = await normalize_medications(state)

    assert len(result["normalized_medications"]) == 1
    assert result["normalized_medications"][0]["name"] == "Aspirin"


@pytest.mark.asyncio
async def test_save_to_database():
    from app.agents.ingestion.graph import save_to_database

    result = await save_to_database({"document_id": "123"})

    assert "medications" in result["saved_ids"]
    assert "obligations" in result["saved_ids"]


@pytest.mark.asyncio
async def test_generate_summary_success():
    from app.agents.ingestion.graph import generate_summary

    with patch("app.agents.ingestion.graph.get_router") as mock_get_router:
        mock_client = AsyncMock()
        mock_client.generate.return_value = "Patient summary"
        mock_router = MagicMock()
        mock_router.get_client_with_fallback.return_value = mock_client
        mock_get_router.return_value = mock_router

        state = {"document_id": "123", "validated_data": {"medications": []}}
        result = await generate_summary(state)

    assert result["patient_summary"] == "Patient summary"


@pytest.mark.asyncio
async def test_create_feed_tasks():
    from app.agents.ingestion.graph import create_feed_tasks

    state = {
        "document_id": "123",
        "normalized_medications": [{"name": "A"}],
        "validated_data": {"follow_up_instructions": [{"description": "Rest"}]},
        "extracted_data": {},
    }
    result = await create_feed_tasks(state)
    assert result["created_tasks"] == 2
