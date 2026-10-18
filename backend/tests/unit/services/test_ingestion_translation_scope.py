"""LOC-003: only the document being ingested has its facts translated."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.services.ingestion_service import IngestionService

PATIENT = UUID("00000000-0000-0000-0000-000000000301")
DOCUMENT = UUID("00000000-0000-0000-0000-000000000302")


@pytest.mark.asyncio
async def test_translation_reads_the_documents_facts_not_the_most_recent_fifty() -> None:
    db = MagicMock()
    service = IngestionService(db, intelligence=MagicMock())
    ours = {
        "id": "f-ours",
        "fact_type": "obligation",
        "value": {"description": "Tome un vaso de agua con cada comida y camine hoy"},
        "display_locale": None,
    }
    other = dict(ours, id="f-other-document")
    translated: list[str] = []

    async def fake_translate(_type, value):
        translated.append(value["description"])
        return {"description": "Drink water"}

    with (
        patch(
            "app.services.clinical_fact_service.ClinicalFactService.list_facts_for_document",
            return_value=[ours],
        ) as listing,
        patch(
            "app.services.fact_display_translation.translate_fact_to_english",
            AsyncMock(side_effect=fake_translate),
        ),
    ):
        await service._translate_spanish_facts(PATIENT, DOCUMENT, MagicMock(created=1))
    listing.assert_called_once_with(DOCUMENT, PATIENT)
    assert len(translated) == 1
    updated = [c.args[0] for c in db.table.return_value.update.call_args_list]
    assert updated == [{"display_locale": "es-MX", "display_value": {"description": "Drink water"}}]
    eq_ids = [c.args[1] for c in db.table.return_value.update.return_value.eq.call_args_list]
    assert eq_ids == ["f-ours"]
    assert other["id"] not in eq_ids
