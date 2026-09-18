"""The emergency floor must answer without the model, in the patient's language.

The defect this replaces was shaped like a gap rather than a bug: the streaming chat path
reached the floor only when the model happened to fail. These tests pin the opposite
property — on an emergency message the run is halted before any agent exists to see it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.genai import types

from app.adk.plugins import LOCALE_STATE_KEY, SafetyFloorPlugin
from app.models.enums import Language


def _context(message: str | None, locale: str | None = None) -> SimpleNamespace:
    content = (
        None if message is None else types.Content(role="user", parts=[types.Part(text=message)])
    )
    state = {} if locale is None else {LOCALE_STATE_KEY: locale}
    return SimpleNamespace(user_content=content, session=SimpleNamespace(state=state))


async def _run(message: str | None, locale: str | None = None) -> types.Content | None:
    return await SafetyFloorPlugin().before_run_callback(
        invocation_context=_context(message, locale)
    )


def _text(content: types.Content | None) -> str:
    assert content is not None and content.parts
    return content.parts[0].text or ""


@pytest.mark.asyncio
async def test_an_emergency_message_halts_the_run() -> None:
    """Returning content is what halts; None would let the agents run."""
    result = await _run("I have crushing chest pain")

    assert result is not None
    assert "911" in _text(result)


@pytest.mark.asyncio
async def test_the_halt_returns_content_and_never_an_event() -> None:
    """Measured on adk 2.9.1: an `Event` does not halt, despite ADK's prose saying it does.

    Returning one here would send an emergency message to the model with no halt at all.
    """
    result = await _run("I have crushing chest pain")

    assert isinstance(result, types.Content)


@pytest.mark.asyncio
async def test_self_harm_gets_the_crisis_line_not_the_general_response() -> None:
    result = await _run("I want to kill myself")

    assert "988" in _text(result)


@pytest.mark.asyncio
async def test_self_harm_wins_when_a_message_carries_both_signals() -> None:
    """The floor checks self-harm first, and the copy must follow that ordering."""
    result = await _run("I have chest pain and I want to kill myself")

    assert "988" in _text(result)


@pytest.mark.asyncio
async def test_an_ordinary_message_lets_the_agents_run() -> None:
    """None is the ordinary case: the floor must not intercept routine conversation."""
    assert await _run("Can you explain my lab results?") is None


@pytest.mark.asyncio
async def test_an_empty_turn_is_not_treated_as_an_emergency() -> None:
    assert await _run("   ") is None
    assert await _run(None) is None


@pytest.mark.asyncio
async def test_a_spanish_speaker_is_answered_in_spanish() -> None:
    """An emergency is the worst moment to reply in a language the patient cannot read."""
    result = await _run("Tengo dolor de pecho", locale=Language.ES.value)

    assert "911" in _text(result)
    assert "urgencias" in _text(result)


@pytest.mark.asyncio
async def test_spanish_self_harm_reaches_the_spanish_crisis_copy() -> None:
    result = await _run("quiero suicidarme", locale=Language.ES.value)

    assert "988" in _text(result)
    assert "Suicidio" in _text(result)


@pytest.mark.asyncio
async def test_an_unknown_locale_still_gets_actionable_copy() -> None:
    """Falling back is acceptable; saying nothing actionable is not."""
    result = await _run("I have crushing chest pain", locale="fr-FR")

    assert "911" in _text(result)


@pytest.mark.asyncio
async def test_a_missing_session_state_does_not_break_the_floor() -> None:
    """The floor must survive a malformed context rather than fail open."""
    context = SimpleNamespace(
        user_content=types.Content(role="user", parts=[types.Part(text="chest pain")]),
        session=None,
    )

    result = await SafetyFloorPlugin().before_run_callback(invocation_context=context)

    assert result is not None
    assert "911" in _text(result)


@pytest.mark.asyncio
async def test_the_reply_is_authored_as_the_model_role() -> None:
    """The patient sees it as the assistant's answer, not as their own echoed turn."""
    result = await _run("I have crushing chest pain")

    assert result is not None
    assert result.role == "model"


def test_the_plugin_is_named_for_the_runner_to_register() -> None:
    assert SafetyFloorPlugin().name == "safety_floor"
