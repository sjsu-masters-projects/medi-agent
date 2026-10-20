"""LOC-003: back-translation is scoped to the patient's own plan and fails safely."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.models.generation import GenerationErrorCode, GenerationProviderError
from app.services.care_plan_service import CarePlanService

PATIENT_ID = UUID("00000000-0000-0000-0000-000000000201")
CLINICIAN_ID = UUID("00000000-0000-0000-0000-000000000202")
PLAN_ID = UUID("00000000-0000-0000-0000-000000000203")
ITEM_ID = UUID("00000000-0000-0000-0000-000000000204")

ITEM = {
    "id": str(ITEM_ID),
    "wording": {"es-MX": {"title": "Tomar"}, "en-US": {"title": "Take"}},
}


def _service(plan_found: bool = True) -> CarePlanService:
    service = CarePlanService(MagicMock())
    service._require_assignment = MagicMock()
    if plan_found:
        service._plan = MagicMock(return_value={"id": str(PLAN_ID)})
    else:
        service._plan = MagicMock(side_effect=NotFoundError("Care plan", str(PLAN_ID)))
    service._items = MagicMock(return_value=[ITEM])
    return service


@pytest.mark.asyncio
async def test_foreign_plan_is_not_found_and_items_are_never_read() -> None:
    service = _service(plan_found=False)
    with pytest.raises(NotFoundError):
        await service.back_translate_item(CLINICIAN_ID, PATIENT_ID, PLAN_ID, ITEM_ID)
    service._plan.assert_called_once_with(PLAN_ID, PATIENT_ID)
    service._items.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        GenerationProviderError(GenerationErrorCode.UNAVAILABLE, "down"),
        ValueError("Back-translation response did not match schema"),
    ],
)
async def test_model_failure_is_a_handled_validation_error(error: Exception) -> None:
    service = _service()
    with (
        patch(
            "app.services.care_plan_translation.back_translate_spanish",
            AsyncMock(side_effect=error),
        ),
        pytest.raises(ValidationError),
    ):
        await service.back_translate_item(CLINICIAN_ID, PATIENT_ID, PLAN_ID, ITEM_ID)


# ── LOC-003 item 8: the back-translation is cached against the wording it covered ──

FULL_WORDING = {
    "es-MX": {
        "title": "Metformina 500 mg",
        "instructions": "Toma 1 tableta dos veces al día.",
        "frequency": "dos veces al día",
    },
    "en-US": {
        "title": "Metformin 500 mg",
        "instructions": "Take 1 tablet twice daily.",
        "frequency": "twice daily",
    },
}

BACK = {
    "title": "Metformin 500 mg",
    "instructions": "Take 1 tablet twice a day.",
    "frequency": "twice a day",
}
GUARDS = {"numbers_match": True, "medication_names_match": True}


def _cacheable_service(item: dict[str, object]) -> CarePlanService:
    service = _service()
    service._items = MagicMock(return_value=[item])
    service._store_back_translation = MagicMock()
    return service


def _item(**changes: object) -> dict[str, object]:
    return {
        "id": str(ITEM_ID),
        "wording": FULL_WORDING,
        "medication": {"name": "Metformin"},
        **changes,
    }


def _cached_record() -> dict[str, object]:
    from app.services.care_plan_translation import wording_fingerprint

    return {
        "back_translation": BACK,
        "guards": GUARDS,
        "fingerprints": {
            "es-MX": wording_fingerprint(FULL_WORDING["es-MX"]),
            "en-US": wording_fingerprint(FULL_WORDING["en-US"]),
        },
    }


@pytest.mark.asyncio
async def test_a_cached_back_translation_is_served_without_a_model_call() -> None:
    service = _cacheable_service(_item(back_translation=_cached_record()))
    translate = AsyncMock()
    with patch("app.services.care_plan_translation.back_translate_spanish", translate):
        result = await service.back_translate_item(CLINICIAN_ID, PATIENT_ID, PLAN_ID, ITEM_ID)
    translate.assert_not_awaited()
    assert result == {"back_translation": BACK, "guards": GUARDS, "cached": True}


@pytest.mark.asyncio
async def test_changed_spanish_wording_invalidates_the_cache() -> None:
    """A back-translation describes exact text; it must never outlive the text it covered."""
    stale = _cached_record()
    stale["fingerprints"]["es-MX"] = "0" * 32
    service = _cacheable_service(_item(back_translation=stale))
    fresh = MagicMock(
        title="Metformin 500 mg",
        instructions="Take 1 tablet twice daily.",
        frequency="twice daily",
        numbers_match=True,
        medication_names_match=True,
    )
    with patch(
        "app.services.care_plan_translation.back_translate_spanish", AsyncMock(return_value=fresh)
    ) as translate:
        result = await service.back_translate_item(CLINICIAN_ID, PATIENT_ID, PLAN_ID, ITEM_ID)
    translate.assert_awaited_once()
    assert result["cached"] is False
    service._store_back_translation.assert_called_once()
    stored = service._store_back_translation.call_args.args[2]
    assert stored["fingerprints"]["es-MX"] != "0" * 32


@pytest.mark.asyncio
async def test_check_again_asks_the_model_for_the_same_wording() -> None:
    """Decision 9's "Check again" must reach the model even when a cache entry matches."""
    service = _cacheable_service(_item(back_translation=_cached_record()))
    fresh = MagicMock(
        title="Metformin 500 mg",
        instructions="Take 1 tablet twice daily.",
        frequency="twice daily",
        numbers_match=True,
        medication_names_match=True,
    )
    with patch(
        "app.services.care_plan_translation.back_translate_spanish", AsyncMock(return_value=fresh)
    ) as translate:
        result = await service.back_translate_item(
            CLINICIAN_ID, PATIENT_ID, PLAN_ID, ITEM_ID, refresh=True
        )
    translate.assert_awaited_once()
    assert result["cached"] is False


@pytest.mark.asyncio
async def test_a_failure_to_cache_never_fails_the_back_translation() -> None:
    service = _service()
    service._items = MagicMock(return_value=[_item()])
    service.db.table.return_value.update.side_effect = RuntimeError("write failed")
    fresh = MagicMock(
        title="Metformin 500 mg",
        instructions="Take 1 tablet twice daily.",
        frequency="twice daily",
        numbers_match=True,
        medication_names_match=True,
    )
    with patch(
        "app.services.care_plan_translation.back_translate_spanish", AsyncMock(return_value=fresh)
    ):
        result = await service.back_translate_item(CLINICIAN_ID, PATIENT_ID, PLAN_ID, ITEM_ID)
    assert result["back_translation"]["title"] == "Metformin 500 mg"
