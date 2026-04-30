"""Tests for medication knowledge RAG service."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.agents.triage.prompts import build_triage_response_prompt
from app.services.drug_knowledge_service import (
    DrugKnowledgeService,
    format_drug_knowledge_for_prompt,
    should_retrieve_drug_knowledge,
)


async def _embedder(_text: str) -> list[float]:
    return [0.1, 0.2, 0.3]


def _response(data: list[dict[str, object]]) -> SimpleNamespace:
    return SimpleNamespace(data=data)


def test_build_dailymed_label_chunks_keeps_citation_metadata():
    service = DrugKnowledgeService(MagicMock(), embedder=_embedder)

    chunks = service.build_dailymed_label_chunks(
        {
            "setid": "set-1",
            "title": "Ibuprofen tablet label",
            "generic_name": "Ibuprofen",
            "brand_name": "Advil",
            "manufacturer": "DailyMed labeler",
            "warnings": "May cause stomach bleeding. Ask a doctor before use if you take anticoagulants.",
            "adverse_reactions": "Nausea and headache have been reported.",
        },
        drug_name="Advil",
        rxcui="5640",
    )

    assert len(chunks) == 2
    assert chunks[0]["source"] == "dailymed"
    assert chunks[0]["source_id"] == "set-1"
    assert chunks[0]["source_title"] == "Ibuprofen tablet label"
    assert chunks[0]["source_url"] == (
        "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=set-1"
    )
    assert chunks[0]["chunk_hash"]


@pytest.mark.asyncio
async def test_ingest_dailymed_label_embeds_and_upserts_chunks():
    mock_db = MagicMock()
    mock_upsert = MagicMock()
    mock_upsert.execute.return_value = _response([{"id": "chunk-1"}])
    mock_db.table.return_value.upsert.return_value = mock_upsert
    service = DrugKnowledgeService(mock_db, embedder=_embedder)

    count = await service.ingest_dailymed_label(
        {
            "setid": "set-1",
            "title": "Ibuprofen tablet label",
            "warnings": "May cause stomach bleeding. Ask a doctor before use if you take anticoagulants.",
        },
        drug_name="Ibuprofen",
        rxcui="5640",
    )

    assert count == 1
    mock_db.table.assert_called_once_with("drug_knowledge_chunks")
    payload = mock_db.table.return_value.upsert.call_args.args[0]
    assert payload[0]["embedding"] == "[0.1,0.2,0.3]"
    assert mock_db.table.return_value.upsert.call_args.kwargs == {
        "on_conflict": "source,source_id,section,chunk_hash"
    }


@pytest.mark.asyncio
async def test_retrieve_for_patient_message_returns_cited_chunks():
    mock_db = MagicMock()
    mock_rpc = MagicMock()
    mock_rpc.execute.return_value = _response(
        [
            {
                "drug_name": "Ibuprofen",
                "generic_name": "Ibuprofen",
                "rxcui": "5640",
                "source": "dailymed",
                "source_id": "set-1",
                "source_title": "Ibuprofen tablet label",
                "source_url": "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=set-1",
                "section": "Warnings",
                "chunk_text": "May cause stomach bleeding.",
                "similarity": 0.91,
            }
        ]
    )
    mock_db.rpc.return_value = mock_rpc
    service = DrugKnowledgeService(mock_db, embedder=_embedder)

    context = await service.retrieve_for_patient_message(
        message="Can ibuprofen cause stomach side effects?",
        medications=[{"name": "Ibuprofen", "rxcui": "5640"}],
    )

    assert context["status"] == "grounded"
    assert context["chunks"][0]["citation_id"] == 1
    assert context["citations"][0]["title"] == "Ibuprofen tablet label"
    mock_db.rpc.assert_called_once()
    rpc_payload = mock_db.rpc.call_args.args[1]
    assert rpc_payload["p_drug_names"] == ["Ibuprofen"]
    assert rpc_payload["p_rxcuis"] == ["5640"]


@pytest.mark.asyncio
async def test_retrieve_for_patient_message_uses_weak_fallback_on_empty_results():
    mock_db = MagicMock()
    mock_rpc = MagicMock()
    mock_rpc.execute.return_value = _response([])
    mock_db.rpc.return_value = mock_rpc
    service = DrugKnowledgeService(mock_db, embedder=_embedder)

    context = await service.retrieve_for_patient_message(
        message="Can this medication cause nausea?",
        medications=[{"name": "Metformin", "rxcui": "6809"}],
    )

    assert context == {"status": "weak", "chunks": [], "citations": []}


def test_should_retrieve_drug_knowledge_matches_keywords_and_medication_names():
    medications = [{"name": "Metformin"}]

    assert should_retrieve_drug_knowledge("Can this medicine cause nausea?", medications)
    assert should_retrieve_drug_knowledge("What does Metformin do?", medications)
    assert not should_retrieve_drug_knowledge("Can I book an appointment?", medications)


def test_format_drug_knowledge_for_prompt_includes_citation_ids():
    prompt_context = format_drug_knowledge_for_prompt(
        {
            "status": "grounded",
            "chunks": [
                {
                    "citation_id": 1,
                    "source_title": "Ibuprofen tablet label",
                    "section": "Warnings",
                    "chunk_text": "May cause stomach bleeding.",
                }
            ],
        }
    )

    assert "[1] Ibuprofen tablet label" in prompt_context
    assert "May cause stomach bleeding" in prompt_context


def test_triage_prompt_includes_medication_rag_context():
    prompt = build_triage_response_prompt(
        message="Can ibuprofen cause stomach side effects?",
        intent="medication_question",
        urgency="routine",
        language="en-US",
        history=[],
        patient_context={
            "medications": [{"name": "Ibuprofen"}],
            "drug_knowledge": {
                "status": "grounded",
                "chunks": [
                    {
                        "citation_id": 1,
                        "source_title": "Ibuprofen tablet label",
                        "section": "Warnings",
                        "chunk_text": "May cause stomach bleeding.",
                    }
                ],
            },
        },
    )

    assert "Medication knowledge chunks" in prompt
    assert "[1] Ibuprofen tablet label" in prompt
    assert "cite the chunks used" in prompt
