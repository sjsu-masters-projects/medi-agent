"""Sectioned explanations preserve source numbers and request the actual reader locale."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.explanation_service import ExplanationService, StructuredExplanation

SPANISH = "El documento dice Metformina 500 mg una vez al día con la cena."
ENGLISH = "The document says Metformina 500 mg once a day with dinner."


def presentation(text: str = ENGLISH, locale: str = "en-US") -> str:
    return json.dumps({"language": locale, "sections": [{"kind": "medicines", "items": [text]}]})


def test_sections_have_a_stable_reading_order() -> None:
    result = StructuredExplanation.model_validate(
        {
            "language": "en-US",
            "sections": [
                {"kind": "questions", "items": ["What does this mean?"]},
                {"kind": "medicines", "items": [ENGLISH]},
                {"kind": "overview", "items": ["This is a prescription."]},
            ],
        }
    )
    assert [section.kind for section in result.sections] == ["overview", "medicines", "questions"]


@pytest.mark.asyncio
@pytest.mark.parametrize("locale,text", [("en-US", ENGLISH), ("es-MX", SPANISH)])
async def test_presents_a_legacy_spanish_source_in_requested_locale(locale: str, text: str) -> None:
    router = MagicMock(generate_text=AsyncMock(return_value=presentation(text, locale)))
    with patch("app.services.explanation_service.get_router", return_value=router):
        result = await ExplanationService().present(SPANISH, locale)
    assert result.language == locale
    assert result.plain_text() == text
    kwargs = router.generate_text.call_args.kwargs
    assert json.loads(kwargs["prompt"]) == {"source_explanation": SPANISH}
    assert f'"language":"{locale}"' in kwargs["system_instruction"]
    assert "never assume it is English" in kwargs["system_instruction"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        presentation(ENGLISH.replace("500", "1000")),
        presentation("The document says Metformina."),
        presentation(ENGLISH + " Return in 3 days."),
        presentation(ENGLISH.replace("mg", "g")),
        presentation(ENGLISH + " 500 mg."),
        presentation("The document does not say Metformina 500 mg once a day with dinner."),
        presentation(SPANISH),
        presentation(ENGLISH, "es-MX"),
        "Not JSON",
        json.dumps({"language": "en-US", "sections": []}),
        json.dumps({"language": "en-US", "sections": [{"kind": "approved", "items": [ENGLISH]}]}),
        json.dumps({"language": "en-US", "sections": [{"kind": "medicines", "items": [""]}]}),
        json.dumps(
            {"language": "en-US", "sections": [{"kind": "medicines", "items": [ENGLISH]}] * 2}
        ),
    ],
)
async def test_refuses_changed_numbers_and_malformed_presentation(bad: str) -> None:
    router = MagicMock(generate_text=AsyncMock(return_value=bad))
    with (
        patch("app.services.explanation_service.get_router", return_value=router),
        pytest.raises(ValueError, match="could not be verified"),
    ):
        await ExplanationService().present(SPANISH, "en-US")
    assert router.generate_text.await_count == 2


@pytest.mark.asyncio
async def test_corrected_second_presentation_can_succeed() -> None:
    router = MagicMock(generate_text=AsyncMock(side_effect=["invalid", presentation()]))
    with patch("app.services.explanation_service.get_router", return_value=router):
        result = await ExplanationService().present(SPANISH, "en-US")
    assert result.plain_text() == ENGLISH
    assert router.generate_text.call_args.kwargs["temperature"] == 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["", "x" * 16001])
async def test_empty_or_oversized_source_never_calls_provider(source: str) -> None:
    with patch("app.services.explanation_service.get_router") as router, pytest.raises(ValueError):
        await ExplanationService().present(source, "en-US")
    router.assert_not_called()
