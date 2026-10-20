"""LOC-003: which facts ingestion translates, in how many calls, and how it marks them."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.services.fact_display_translation import FactTranslation
from app.services.ingestion_service import IngestionService

PATIENT = UUID("00000000-0000-0000-0000-000000000301")
DOCUMENT = UUID("00000000-0000-0000-0000-000000000302")

SPANISH = "Tome un vaso de agua con cada comida y camine hoy"


def _fact(fact_id: str, description: str = SPANISH) -> dict[str, Any]:
    return {
        "id": fact_id,
        "fact_type": "obligation",
        "value": {"description": description},
        "display_locale": None,
    }


def _updates(db: MagicMock) -> list[dict[str, Any]]:
    return [call.args[0] for call in db.table.return_value.update.call_args_list]


@pytest.mark.asyncio
async def test_translation_reads_the_documents_facts_not_the_most_recent_fifty() -> None:
    db = MagicMock()
    service = IngestionService(db, intelligence=MagicMock())
    ours = _fact("f-ours")
    requested: list[list[str]] = []

    async def fake_translate(facts: list[tuple[str, str, dict[str, Any]]]):
        requested.append([fact_id for fact_id, _, _ in facts])
        return {
            "f-ours": FactTranslation(fields={"description": "Drink water"}, model_id="gemini-test")
        }

    with (
        patch(
            "app.services.clinical_fact_service.ClinicalFactService.list_facts_for_document",
            return_value=[ours],
        ) as listing,
        patch(
            "app.services.fact_display_translation.translate_facts_to_english",
            AsyncMock(side_effect=fake_translate),
        ),
    ):
        await service._translate_spanish_facts(PATIENT, DOCUMENT, MagicMock(created=1))

    listing.assert_called_once_with(DOCUMENT, PATIENT)
    assert requested == [["f-ours"]]
    assert _updates(db) == [
        {
            "display_locale": "es-MX",
            "display_value": {"description": "Drink water"},
            "display_model_id": "gemini-test",
        }
    ]
    eq_ids = [c.args[1] for c in db.table.return_value.update.return_value.eq.call_args_list]
    assert eq_ids == ["f-ours"]


@pytest.mark.asyncio
async def test_a_documents_spanish_facts_are_translated_in_one_batch() -> None:
    """Item 7: one call carries the document's Spanish facts, not one call per fact."""
    db = MagicMock()
    service = IngestionService(db, intelligence=MagicMock())
    facts = [_fact(f"f-{index}") for index in range(4)]
    calls: list[list[str]] = []

    async def fake_translate(batch: list[tuple[str, str, dict[str, Any]]]):
        calls.append([fact_id for fact_id, _, _ in batch])
        return {
            fact_id: FactTranslation(fields={"description": "Drink water"}, model_id="gemini-test")
            for fact_id, _, _ in batch
        }

    with (
        patch(
            "app.services.clinical_fact_service.ClinicalFactService.list_facts_for_document",
            return_value=facts,
        ),
        patch(
            "app.services.fact_display_translation.translate_facts_to_english",
            AsyncMock(side_effect=fake_translate),
        ),
    ):
        await service._translate_spanish_facts(PATIENT, DOCUMENT, MagicMock(created=4))

    assert calls == [["f-0", "f-1", "f-2", "f-3"]]


@pytest.mark.asyncio
async def test_a_rejected_translation_marks_the_fact_spanish_and_untranslated() -> None:
    """Item 6: a guard-rejected fact keeps its Spanish and carries no English display."""
    db = MagicMock()
    service = IngestionService(db, intelligence=MagicMock())
    facts = [_fact("f-kept"), _fact("f-rejected")]

    with (
        patch(
            "app.services.clinical_fact_service.ClinicalFactService.list_facts_for_document",
            return_value=facts,
        ),
        patch(
            "app.services.fact_display_translation.translate_facts_to_english",
            AsyncMock(
                return_value={
                    "f-kept": FactTranslation(
                        fields={"description": "Drink water"}, model_id="gemini-test"
                    )
                }
            ),
        ),
    ):
        await service._translate_spanish_facts(PATIENT, DOCUMENT, MagicMock(created=2))

    assert {"display_locale": "es-MX"} in _updates(db)
    assert {
        "display_locale": "es-MX",
        "display_value": {"description": "Drink water"},
        "display_model_id": "gemini-test",
    } in _updates(db)
    rejected = [
        call.args[1]
        for call in db.table.return_value.update.return_value.in_.call_args_list
        if call.args[0] == "id"
    ]
    assert ["f-rejected"] in rejected


@pytest.mark.asyncio
async def test_english_facts_are_marked_together_without_a_model_call() -> None:
    db = MagicMock()
    service = IngestionService(db, intelligence=MagicMock())
    facts = [
        _fact("f-en-1", "Drink a glass of water with each meal"),
        _fact("f-en-2", "Walk for fifteen minutes today"),
    ]
    translate = AsyncMock(return_value={})

    with (
        patch(
            "app.services.clinical_fact_service.ClinicalFactService.list_facts_for_document",
            return_value=facts,
        ),
        patch("app.services.fact_display_translation.translate_facts_to_english", translate),
    ):
        await service._translate_spanish_facts(PATIENT, DOCUMENT, MagicMock(created=2))

    translate.assert_not_awaited()
    assert _updates(db) == [{"display_locale": "en-US"}]
    marked = [
        call.args[1]
        for call in db.table.return_value.update.return_value.in_.call_args_list
        if call.args[0] == "id"
    ]
    assert marked == [["f-en-1", "f-en-2"]]


@pytest.mark.asyncio
async def test_a_failed_batch_leaves_every_spanish_fact_untranslated() -> None:
    db = MagicMock()
    service = IngestionService(db, intelligence=MagicMock())
    facts = [_fact("f-1"), _fact("f-2")]

    with (
        patch(
            "app.services.clinical_fact_service.ClinicalFactService.list_facts_for_document",
            return_value=facts,
        ),
        patch(
            "app.services.fact_display_translation.translate_facts_to_english",
            AsyncMock(side_effect=RuntimeError("model unavailable")),
        ),
    ):
        await service._translate_spanish_facts(PATIENT, DOCUMENT, MagicMock(created=2))

    assert _updates(db) == [{"display_locale": "es-MX"}]
    assert not any("display_value" in update for update in _updates(db))
