"""Record titles describe a document in both languages and fall back to its file name."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from postgrest.exceptions import APIError

from app.models.generation import (
    GenerationErrorCode,
    GenerationProviderError,
    GenerationResponse,
    GenerationTelemetry,
)
from app.services import document_title_service
from app.services.document_title_service import DocumentTitleService, valid_title

ROW = {
    "id": str(UUID(int=1)),
    "patient_id": str(UUID(int=2)),
    "file_name": "Morgan-Ellis-01-Hidratacion-es-MX-2026-10-09.pdf",
    "document_type": "other",
    "ai_summary": "Your care team asks you to drink water with each meal.",
    "display_title_attempts": 0,
}


def _response(payload: dict[str, str] | str) -> GenerationResponse:
    return GenerationResponse(
        text=payload if isinstance(payload, str) else json.dumps(payload),
        telemetry=GenerationTelemetry(provider="flash", model="gemini-test", latency_ms=1),
    )


def _service(rows: list[dict[str, Any]]) -> tuple[MagicMock, DocumentTitleService]:
    db = MagicMock()
    chain = db.table.return_value
    for method in ("select", "eq", "lt", "in_", "order", "limit", "update"):
        getattr(chain, method).return_value = chain
    chain.execute.return_value.data = rows
    facts = MagicMock()
    facts.list_facts_for_document.return_value = [
        {"value": {"description": "Tome un vaso de agua con cada comida 3 veces"}}
    ]
    return db, DocumentTitleService(db, facts=facts)


@pytest.mark.parametrize(
    "title,valid",
    [
        ("Hydration instructions", True),
        ("Indicaciones de hidratación", True),
        ("Metformin 500 mg prescription", False),
        ("Drink", True),
        ("A", False),
        ("Line one\nLine two", False),
        ("one two three four five six seven eight nine", False),
    ],
)
def test_titles_are_short_descriptions_without_numbers(title, valid) -> None:
    assert valid_title(title) is valid


@pytest.mark.asyncio
async def test_drafts_both_languages_from_summary_without_numbers(monkeypatch) -> None:
    db, service = _service([ROW])
    generate = AsyncMock(
        return_value=_response(
            {"en_us": "Hydration instructions", "es_mx": "Indicaciones de hidratación"}
        )
    )
    monkeypatch.setattr(document_title_service, "generate_for_workload", generate)

    counts = await service.fill_missing(limit=10)

    assert counts == {"titles_claimed": 1, "titles_ready": 1, "titles_failed": 0}
    prompt = generate.await_args.kwargs["prompt"]
    assert "Morgan Ellis 01 Hidratacion" in prompt
    assert "2026" not in prompt and "es-MX" not in prompt
    assert '"Tome un vaso de agua con cada comida"' in prompt  # topic kept, digits dropped
    payload = db.table.return_value.update.call_args.args[0]
    assert payload == {
        "display_title_attempts": 1,
        "display_title": {
            "en-US": "Hydration instructions",
            "es-MX": "Indicaciones de hidratación",
        },
    }
    db.table.return_value.eq.assert_any_call("display_title_attempts", 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [
        GenerationProviderError(GenerationErrorCode.UNAVAILABLE, "down"),
        _response("not json"),
        _response({"en_us": "Metformin 500 mg", "es_mx": "Metformina 500 mg"}),
    ],
)
async def test_failed_or_rejected_title_only_counts_the_attempt(monkeypatch, outcome) -> None:
    db, service = _service([ROW])
    generate = AsyncMock(
        side_effect=outcome if isinstance(outcome, Exception) else None,
        return_value=None if isinstance(outcome, Exception) else outcome,
    )
    monkeypatch.setattr(document_title_service, "generate_for_workload", generate)

    counts = await service.fill_missing(limit=10)

    assert counts["titles_failed"] == 1
    assert db.table.return_value.update.call_args.args[0] == {"display_title_attempts": 1}


@pytest.mark.asyncio
async def test_missing_title_column_is_tolerated_before_migration() -> None:
    db, service = _service([])
    db.table.return_value.execute.side_effect = APIError(
        {"message": "column documents.display_title does not exist", "code": "42703"}
    )
    assert (await service.fill_missing(limit=10))["titles_schema_unavailable"] == 1
