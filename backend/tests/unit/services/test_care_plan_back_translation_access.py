"""LOC-003: back-translation is scoped to the patient's own plan and fails safely."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.models.generation import GenerationErrorCode, GenerationProviderError
from app.services.care_plan_service import CarePlanService
from tests.unit.services.care_plan_ownership_stub import stub_ownership

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
    stub_ownership(service)
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
