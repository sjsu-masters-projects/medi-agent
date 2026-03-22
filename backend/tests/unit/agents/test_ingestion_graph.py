"""Tests for IngestionState and graph creation."""

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

    assert state["saved_ids"] is not None
    assert "medications" in state["saved_ids"]
    assert "conditions" in state["saved_ids"]
    assert len(state["saved_ids"]["medications"]) == 2
    assert len(state["saved_ids"]["conditions"]) == 1
