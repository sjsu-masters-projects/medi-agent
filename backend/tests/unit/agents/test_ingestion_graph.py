"""Tests for IngestionState and graph creation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.ingestion.graph import IngestionState, create_ingestion_graph


def test_ingestion_state_structure():
    """Test IngestionState has correct structure."""
    # Create a valid state
    state: IngestionState = {
        "document_id": "doc-123",
        "document_bytes": b"test data",
        "document_type": "pdf",
        "patient_id": "patient-456",
        "raw_text": None,
        "parsed_data": None,
        "normalized_meds": None,
        "saved_ids": None,
        "summary": None,
        "error": None,
        "retry_count": 0,
        "messages": [],
    }

    assert state["document_id"] == "doc-123"
    assert state["document_bytes"] == b"test data"
    assert state["document_type"] == "pdf"
    assert state["patient_id"] == "patient-456"
    assert state["raw_text"] is None
    assert state["retry_count"] == 0


def test_ingestion_state_with_intermediate_data():
    """Test IngestionState with intermediate processing data."""
    state: IngestionState = {
        "document_id": "doc-123",
        "document_bytes": b"test data",
        "document_type": "pdf",
        "patient_id": "patient-456",
        "raw_text": "Extracted text from document",
        "parsed_data": {"medications": ["aspirin"], "conditions": ["hypertension"]},
        "normalized_meds": [{"rxcui": "1191", "name": "aspirin"}],
        "saved_ids": {"medications": ["med-1"], "conditions": ["cond-1"]},
        "summary": "Document processed successfully",
        "error": None,
        "retry_count": 0,
        "messages": [],
    }

    assert state["raw_text"] == "Extracted text from document"
    assert state["parsed_data"] is not None
    assert "medications" in state["parsed_data"]
    assert state["normalized_meds"] is not None
    assert len(state["normalized_meds"]) == 1


def test_ingestion_state_with_error():
    """Test IngestionState with error."""
    state: IngestionState = {
        "document_id": "doc-123",
        "document_bytes": b"test data",
        "document_type": "pdf",
        "patient_id": "patient-456",
        "raw_text": None,
        "parsed_data": None,
        "normalized_meds": None,
        "saved_ids": None,
        "summary": None,
        "error": "Failed to extract text",
        "retry_count": 1,
        "messages": [],
    }

    assert state["error"] == "Failed to extract text"
    assert state["retry_count"] == 1


def test_create_ingestion_graph():
    """Test that create_ingestion_graph returns a compiled graph."""
    graph = create_ingestion_graph()

    # Graph should be compiled and ready to use
    assert graph is not None

    # Note: Graph is empty until IngestionAgent is implemented
    # This test just verifies the graph compiles without errors


def test_ingestion_state_document_types():
    """Test different document types."""
    for doc_type in ["pdf", "image", "text"]:
        state: IngestionState = {
            "document_id": "doc-123",
            "document_bytes": b"test data",
            "document_type": doc_type,
            "patient_id": "patient-456",
            "raw_text": None,
            "parsed_data": None,
            "normalized_meds": None,
            "saved_ids": None,
            "summary": None,
            "error": None,
            "retry_count": 0,
            "messages": [],
        }

        assert state["document_type"] == doc_type


def test_ingestion_state_saved_ids_structure():
    """Test saved_ids structure."""
    state: IngestionState = {
        "document_id": "doc-123",
        "document_bytes": b"test data",
        "document_type": "pdf",
        "patient_id": "patient-456",
        "raw_text": None,
        "parsed_data": None,
        "normalized_meds": None,
        "saved_ids": {
            "medications": ["med-1", "med-2"],
            "conditions": ["cond-1"],
        },
        "summary": None,
        "error": None,
        "retry_count": 0,
        "messages": [],
    }

    assert "medications" in state["saved_ids"]
    assert "conditions" in state["saved_ids"]
    assert len(state["saved_ids"]["medications"]) == 2
    assert len(state["saved_ids"]["conditions"]) == 1


@pytest.mark.asyncio
async def test_receive_document():
    from app.agents.ingestion.graph import receive_document

    state = {"document_id": "123", "file_url": "http://test", "document_type": "pdf"}
    result = await receive_document(state)
    assert result["raw_content"] == "[Document content from http://test]"
    assert result["error"] is None


@pytest.mark.asyncio
async def test_extract_content_success():
    from app.agents.ingestion.graph import extract_content

    with patch("app.agents.ingestion.graph.get_router") as mock_get_router:
        mock_client = AsyncMock()
        mock_client.generate.return_value = '```json\n{"medications": [], "conditions": []}\n```'
        mock_router = MagicMock()
        mock_router.get_client.return_value = mock_client
        mock_get_router.return_value = mock_router

        state = {"document_id": "123", "raw_content": "Some text"}
        result = await extract_content(state)

        assert result["extracted_data"] == {"medications": [], "conditions": []}
        assert result["error"] is None


@pytest.mark.asyncio
async def test_extract_content_failure():
    from app.agents.ingestion.graph import extract_content

    with patch("app.agents.ingestion.graph.get_router") as mock_get_router:
        mock_router = MagicMock()
        mock_router.get_client.side_effect = Exception("Router failed")
        mock_get_router.return_value = mock_router

        state = {"document_id": "123", "raw_content": "Some text"}
        result = await extract_content(state)

        assert result["error"] == "Router failed"


@pytest.mark.asyncio
async def test_validate_fhir():
    from app.agents.ingestion.graph import validate_fhir

    state = {"document_id": "123", "extracted_data": {"medications": [{"name": "Aspirin"}]}}
    result = await validate_fhir(state)
    assert result["validated_data"] == state["extracted_data"]
    assert result["validation_errors"] is None


@pytest.mark.asyncio
async def test_validate_fhir_empty_meds():
    from app.agents.ingestion.graph import validate_fhir

    state = {"document_id": "123", "extracted_data": {"conditions": []}}
    result = await validate_fhir(state)
    assert "No medications found" in result["validation_errors"]


@pytest.mark.asyncio
async def test_normalize_medications():
    from app.agents.ingestion.graph import normalize_medications

    state = {
        "document_id": "123",
        "validated_data": {"medications": [{"name": "Aspirin", "dosage": "81mg"}]},
    }
    result = await normalize_medications(state)
    assert len(result["normalized_medications"]) == 1
    assert result["normalized_medications"][0]["name"] == "Aspirin"
    assert result["normalized_medications"][0]["dosage"] == "81mg"


@pytest.mark.asyncio
async def test_save_to_database():
    from app.agents.ingestion.graph import save_to_database

    state = {"document_id": "123"}
    result = await save_to_database(state)
    assert "medications" in result["saved_ids"]


@pytest.mark.asyncio
async def test_generate_summary_success():
    from app.agents.ingestion.graph import generate_summary

    with patch("app.agents.ingestion.graph.get_router") as mock_get_router:
        mock_client = AsyncMock()
        mock_client.generate.return_value = "Patient summary"
        mock_router = MagicMock()
        mock_router.get_client.return_value = mock_client
        mock_get_router.return_value = mock_router

        state = {"document_id": "123", "extracted_data": {}}
        result = await generate_summary(state)

        assert result["patient_summary"] == "Patient summary"


@pytest.mark.asyncio
async def test_create_feed_tasks():
    from app.agents.ingestion.graph import create_feed_tasks

    state = {
        "document_id": "123",
        "normalized_medications": [{"name": "A"}],
        "extracted_data": {"follow_up_instructions": ["Rest"]},
    }
    result = await create_feed_tasks(state)
    assert result["created_tasks"] == 2
