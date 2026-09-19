"""Candidate-only document ingestion graph tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.ingestion.graph import IngestionState, create_ingestion_graph


def _state(**overrides: object) -> IngestionState:
    state: IngestionState = {
        "document_id": "00000000-0000-0000-0000-000000000123",
        "file_url": "patient/document.pdf",
        "document_type": "prescription",
        "mime_type": "application/pdf",
        "patient_id": "00000000-0000-0000-0000-000000000456",
        "raw_content": None,
        "page_texts": None,
        "source_status": None,
        "source_warnings": [],
        "extracted_data": None,
        "validated_data": None,
        "validation_errors": None,
        "normalized_medications": None,
        "patient_summary": None,
        "summary_warning": None,
        "error": None,
        "retry_count": 0,
        "messages": [],
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def test_create_ingestion_graph_has_no_canonical_write_nodes() -> None:
    graph = create_ingestion_graph()

    assert graph is not None
    graph_repr = repr(graph.get_graph())
    assert "save_to_database" not in graph_repr
    assert "create_feed_tasks" not in graph_repr


@pytest.mark.asyncio
async def test_image_source_requires_ocr_without_calling_a_model() -> None:
    from app.agents.ingestion.graph import receive_document

    admin = MagicMock()
    admin.storage.from_().download.return_value = b"not-decoded-as-image"
    with patch("app.clients.supabase.get_admin_client", return_value=admin):
        result = await receive_document(_state(file_url="patient/scan.png", mime_type="image/png"))

    assert result["source_status"] == "needs_ocr"
    assert result["raw_content"] is None


@pytest.mark.asyncio
async def test_extract_content_keeps_page_text_for_evidence() -> None:
    from app.agents.ingestion.graph import extract_content

    router = MagicMock()
    router.generate_text_with_telemetry = AsyncMock(
        return_value=('{"medications": []}', MagicMock(model="gemini-3.8-flash"))
    )
    with patch("app.agents.ingestion.graph.get_router", return_value=router):
        result = await extract_content(_state(raw_content="[Page 1] Aspirin 81 mg", page_texts=["Aspirin 81 mg"]))

    assert result["extracted_data"] == {"medications": []}
    assert result["page_texts"] == ["Aspirin 81 mg"]
    assert result["raw_content"] is None
    # The model that actually answered, carried forward so the candidate written after
    # this graph can record which model produced it.
    assert result["extraction_model"] == "gemini-3.8-flash"


@pytest.mark.asyncio
async def test_optional_summary_failure_does_not_fail_extraction() -> None:
    from app.agents.ingestion.graph import generate_summary

    router = MagicMock()
    router.generate_text = AsyncMock(side_effect=RuntimeError("provider unavailable"))
    with patch("app.agents.ingestion.graph.get_router", return_value=router):
        result = await generate_summary(_state(validated_data={"medications": []}))

    assert result["error"] is None
    assert result["summary_warning"] == "RuntimeError"
