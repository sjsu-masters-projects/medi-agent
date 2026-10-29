"""Presentation reuse, invalidation and cancellation without live providers."""

import asyncio
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.document_presentation_service import DocumentPresentationService
from app.services.explanation_service import StructuredExplanation

SOURCE = "The document says Metformina 500 mg once a day with dinner."


def presentation(text=SOURCE, locale="en-US"):
    return StructuredExplanation.model_validate(
        {"language": locale, "sections": [{"kind": "medicines", "items": [text]}]}
    )


def database():
    saved = {}
    filters = {}
    db = MagicMock()
    query = db.table.return_value
    query.select.return_value = query

    def eq(key, value):
        filters[key] = value
        return query

    def execute():
        row = saved.get((filters.get("document_id"), filters.get("language")))
        data = [row] if row and all(row.get(k) == v for k, v in filters.items()) else []
        filters.clear()
        return MagicMock(data=data)

    def upsert(row, **kwargs):
        saved[(row["document_id"], row["language"])] = row
        return MagicMock()

    query.eq.side_effect = eq
    query.execute.side_effect = execute
    query.upsert.side_effect = upsert
    return db, saved


@pytest.mark.asyncio
async def test_reopening_reuses_persisted_presentation_across_service_instances():
    db, saved = database()
    doc = uuid4()
    with patch(
        "app.services.document_presentation_service.ExplanationService.present",
        new=AsyncMock(return_value=presentation()),
    ) as generate:
        first = await DocumentPresentationService(db).read_or_present(doc, SOURCE, "en-US")
        second = await DocumentPresentationService(db).read_or_present(doc, SOURCE, "en-US")
    assert first[1] is False and second[1] is True
    assert second[0] == first[0]
    generate.assert_awaited_once()
    assert len(saved) == 1
    assert next(iter(saved.values()))["source_hash"] == hashlib.sha256(SOURCE.encode()).hexdigest()


@pytest.mark.asyncio
async def test_source_locale_document_and_prompt_version_invalidate_reuse():
    db, saved = database()
    doc = uuid4()
    spanish = "El documento dice Metformina 500 mg una vez al día con la cena."
    new = SOURCE.replace("500", "750")
    generate = AsyncMock(
        side_effect=[
            presentation(),
            presentation(spanish, "es-MX"),
            presentation(new),
            presentation(new),
            presentation(new),
        ]
    )
    with patch(
        "app.services.document_presentation_service.ExplanationService.present", new=generate
    ):
        service = DocumentPresentationService(db)
        await service.read_or_present(doc, SOURCE, "en-US")
        await service.read_or_present(doc, SOURCE, "es-MX")
        await service.read_or_present(doc, new, "en-US")
        with patch("app.services.document_presentation_service.PRESENTATION_VERSION", 2):
            await service.read_or_present(doc, new, "en-US")
        await service.read_or_present(uuid4(), new, "en-US")
    assert generate.await_count == 5
    # One current entry per document/locale, even after source/version changes.
    assert len(saved) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"language": "es-MX", "sections": [{"kind": "medicines", "items": [SOURCE]}]},
        {
            "language": "en-US",
            "sections": [{"kind": "medicines", "items": [SOURCE.replace("500", "1000")]}],
        },
    ],
)
async def test_invalid_cached_content_is_never_served(bad):
    db, saved = database()
    doc = uuid4()
    with patch(
        "app.services.document_presentation_service.ExplanationService.present",
        new=AsyncMock(return_value=presentation()),
    ) as generate:
        service = DocumentPresentationService(db)
        await service.read_or_present(doc, SOURCE, "en-US")
        saved[(str(doc), "en-US")]["payload"] = bad
        result, reused = await service.read_or_present(doc, SOURCE, "en-US")
    assert result.plain_text() == SOURCE and reused is False
    assert generate.await_count == 2


@pytest.mark.asyncio
async def test_closing_a_waiter_preserves_generation_and_reopen_shares_it():
    db, _ = database()
    started, release = asyncio.Event(), asyncio.Event()

    async def generate(*args):
        started.set()
        await release.wait()
        return presentation()

    with patch(
        "app.services.document_presentation_service.ExplanationService.present",
        new=AsyncMock(side_effect=generate),
    ) as model:
        service = DocumentPresentationService(db)
        doc = uuid4()
        original = asyncio.create_task(service.read_or_present(doc, SOURCE, "en-US"))
        await started.wait()
        original.cancel()
        with pytest.raises(asyncio.CancelledError):
            await original
        reopened = asyncio.create_task(service.read_or_present(doc, SOURCE, "en-US"))
        await asyncio.sleep(0)
        release.set()
        assert (await reopened)[0].plain_text() == SOURCE
        assert (await service.read_or_present(doc, SOURCE, "en-US"))[1] is True
    model.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_generation_is_not_saved_and_can_retry():
    db, saved = database()
    with patch(
        "app.services.document_presentation_service.ExplanationService.present",
        new=AsyncMock(side_effect=[ValueError("unverified"), presentation()]),
    ) as model:
        service = DocumentPresentationService(db)
        doc = uuid4()
        with pytest.raises(ValueError):
            await service.read_or_present(doc, SOURCE, "en-US")
        assert not saved
        assert (await service.read_or_present(doc, SOURCE, "en-US"))[0].plain_text() == SOURCE
    assert model.await_count == 2


@pytest.mark.asyncio
async def test_missing_cache_schema_never_falls_back_to_per_view_generation():
    db, _ = database()
    db.table.return_value.execute.side_effect = RuntimeError("missing table")
    with (
        patch(
            "app.services.document_presentation_service.ExplanationService.present", new=AsyncMock()
        ) as model,
        pytest.raises(RuntimeError),
    ):
        await DocumentPresentationService(db).read_or_present(uuid4(), SOURCE, "en-US")
    model.assert_not_awaited()
