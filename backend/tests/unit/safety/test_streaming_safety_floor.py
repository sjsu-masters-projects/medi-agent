"""The streaming chat path must reach the safety floor before the model.

This is the regression that shipped to production: `classify_intent` consulted the floor
first, but `TriageAgent.process_stream` — the method the websocket actually uses, and the
only production chat path — reached it only through the rule cascade that ran when the LLM
*failed*. A healthy model that misread "crushing chest pain" as small talk had nothing
behind it.

These tests assert the model is never consulted, not merely that the answer came out
right, because a correct answer from a consulted model would still be the bug.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.triage import agent as triage_agent_module
from app.agents.triage.agent import TriageAgent, TriageInput
from app.models.enums import Language


class _ExplodingRouter:
    """Any use of this router is a test failure: the floor must not call a model."""

    def get_client(self, _task_type: object) -> object:
        raise AssertionError("The safety floor must decide without consulting a model")


def _input(message: str, language: Language = Language.EN) -> TriageInput:
    return TriageInput(
        user_id=uuid4(),
        patient_id=uuid4(),
        message=message,
        language=language,
    )


async def _collect(agent: TriageAgent, message: str, language: Language) -> list[dict]:
    return [event async for event in agent.process_stream(_input(message, language))]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "language"),
    [
        ("I'm having crushing chest pain right now", Language.EN),
        ("tengo dolor de pecho muy fuerte", Language.ES),
        ("no puedo respirar", Language.ES),
    ],
)
async def test_streaming_emergency_never_reaches_the_model(
    message: str, language: Language, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    async def _must_not_run(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(triage_agent_module, "_classify_with_llm", _must_not_run)

    events = await _collect(TriageAgent(router=_ExplodingRouter()), message, language)

    assert called is False
    classification = next(e for e in events if e["type"] == "classification")
    assert classification["urgency"] == "emergency"
    assert classification["escalation_required"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "language"),
    [
        ("I want to kill myself", Language.EN),
        ("quiero quitarme la vida", Language.ES),
    ],
)
async def test_streaming_self_harm_gets_the_crisis_copy(message: str, language: Language) -> None:
    """Self-harm must route to mental_health — the 988 copy hangs off that intent."""
    events = await _collect(TriageAgent(router=_ExplodingRouter()), message, language)

    classification = next(e for e in events if e["type"] == "classification")
    assert classification["intent"] == "mental_health"
    assert classification["urgency"] == "emergency"

    complete = next(e for e in events if e["type"] == "complete")
    assert "988" in complete["response_text"]


@pytest.mark.asyncio
async def test_spanish_emergency_answers_in_spanish() -> None:
    events = await _collect(
        TriageAgent(router=_ExplodingRouter()), "no puedo respirar", Language.ES
    )

    complete = next(e for e in events if e["type"] == "complete")
    assert "911" in complete["response_text"]
    assert "emergencia" in complete["response_text"].lower()


@pytest.mark.asyncio
async def test_an_ordinary_message_is_still_handed_to_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The floor must not swallow ordinary traffic — that would be its own failure."""
    consulted = False

    async def _record(*_args: object, **_kwargs: object) -> None:
        nonlocal consulted
        consulted = True
        return None

    monkeypatch.setattr(triage_agent_module, "_classify_with_llm", _record)

    await _collect(
        TriageAgent(router=_ExplodingRouter()),
        "can I move my appointment to Tuesday",
        Language.EN,
    )

    assert consulted is True
