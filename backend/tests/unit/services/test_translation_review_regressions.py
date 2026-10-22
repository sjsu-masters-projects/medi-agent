"""Review failures must stay outside approved patient-facing wording."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.care_plan_service import CarePlanService
from app.services.message_translation import back_translate_message
from app.services.translation_guards import same_language_negation_changed


def test_english_backtranslation_cannot_drop_one_of_several_negations() -> None:
    assert same_language_negation_changed(
        "Do not take 500 mg without water", "Take 500 mg without water"
    )
    assert not same_language_negation_changed(
        "Do not take 500 mg without water", "Do not take 500 mg without water"
    )


def test_stub_cannot_cross_the_publication_guard() -> None:
    from app.core.exceptions import ValidationError

    with pytest.raises(ValidationError, match="Offline stub wording"):
        CarePlanService._require_wording_guards(
            {"translation_model_id": "offline-translation-stub"}
        )


@pytest.mark.asyncio
async def test_back_translation_never_returns_guard_rejected_text() -> None:
    with (
        patch(
            "app.services.message_translation.translate_message",
            AsyncMock(return_value=("Take 250 mg", False, "numbers_changed", "test-model")),
        ),
        pytest.raises(ValueError, match="Back-translation guard rejected"),
    ):
        await back_translate_message("Toma 500 mg", "es-MX", "en-US")


@pytest.mark.asyncio
async def test_lookup_failure_is_distinct_from_a_missing_translation() -> None:
    from unittest.mock import MagicMock

    from app.services.message_translation import MessageTranslationService

    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.side_effect = RuntimeError(
        "down"
    )
    with pytest.raises(RuntimeError, match="Stored translation unavailable"):
        await MessageTranslationService(db).get_translation(
            "care_team_conversation_messages", "m1", "es-MX"
        )


@pytest.mark.asyncio
async def test_failed_store_does_not_return_unpersisted_automatic_wording() -> None:
    from unittest.mock import MagicMock

    from app.services.message_translation import MessageTranslationService

    service = MessageTranslationService(MagicMock())
    service._store = AsyncMock(return_value=None)
    with patch(
        "app.services.message_translation.translate_message",
        AsyncMock(return_value=("Hola", True, None, "test-model")),
    ):
        assert (
            await service.translate_and_store(
                "care_team_conversation_messages", "m1", "Hello", "en-US", "es-MX"
            )
            is None
        )
