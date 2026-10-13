"""A translated patient explanation must carry exactly the English numbers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.explanation_service import ExplanationService, numbers_in

ENGLISH = "Your A1c was 7.8%, marked high (its range is 4.0 - 5.6%). Visit on 10/16/2026."


def test_numbers_in_reads_decimal_and_thousands_commas_alike() -> None:
    assert numbers_in("7,8 y 1,245") == {"7.8", "1245"}
    assert numbers_in(ENGLISH) == {"7.8", "4.0", "5.6", "10", "16", "2026"}


@pytest.mark.asyncio
async def test_translation_that_keeps_every_number_is_returned() -> None:
    router = MagicMock()
    router.generate_text = AsyncMock(
        return_value="Tu A1c fue 7,8%, marcada alta (rango 4.0 - 5.6%). Cita el 16/10/2026."
    )
    with patch("app.services.explanation_service.get_router", return_value=router):
        translated = await ExplanationService().translate(ENGLISH, "es-MX")
    assert translated.startswith("Tu A1c")
    assert router.generate_text.await_count == 1


@pytest.mark.asyncio
async def test_translation_that_changes_a_number_is_retried_then_refused() -> None:
    router = MagicMock()
    router.generate_text = AsyncMock(
        return_value="Tu A1c fue 7.9%, marcada alta (rango 4.0 - 5.6%). Cita el 16/10/2026."
    )
    with (
        patch("app.services.explanation_service.get_router", return_value=router),
        pytest.raises(ValueError),
    ):
        await ExplanationService().translate(ENGLISH, "es-MX")
    assert router.generate_text.await_count == 2
    assert router.generate_text.call_args.kwargs["temperature"] == 0.0


def test_digits_inside_test_names_are_not_values() -> None:
    assert numbers_in("A1c, vitamin B12 and 500mg") == {"500"}
