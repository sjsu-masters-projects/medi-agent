"""The typed decision that gives every turn an intent and an urgency.

This is the one thing the websocket contract needs that prose cannot supply. The failures
worth pinning are the quiet ones: a value outside the accepted set reaching the wire, a
rejection that echoes clinical detail back, and a decision silently not recorded.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import get_args

import pytest

from app.adk.tools.triage_decision import (
    TRIAGE_DECISION_STATE_KEY,
    VALID_INTENTS,
    VALID_URGENCIES,
    submit_triage_decision,
)
from app.safety import IntentType, UrgencyType


def _context() -> SimpleNamespace:
    return SimpleNamespace(state={})


# ---------------------------------------------------------------------------
# The accepted values come from app.safety, not a second copy
# ---------------------------------------------------------------------------


def test_the_accepted_values_are_the_shared_literals() -> None:
    """A restated copy would drift, and the symptom would be a valid answer refused."""
    assert frozenset(get_args(IntentType)) == VALID_INTENTS
    assert frozenset(get_args(UrgencyType)) == VALID_URGENCIES


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_valid_decision_is_recorded() -> None:
    context = _context()

    result = await submit_triage_decision(
        intent="medication_question",
        urgency="routine",
        reason="Asked when to take metformin",
        tool_context=context,
    )

    assert result == {"recorded": True}
    assert context.state[TRIAGE_DECISION_STATE_KEY] == {
        "intent": "medication_question",
        "urgency": "routine",
        "reason": "Asked when to take metformin",
    }


@pytest.mark.asyncio
async def test_an_escalating_urgency_is_accepted() -> None:
    """Escalation upward is always safe; only lowering one would need refusing."""
    context = _context()

    await submit_triage_decision(
        intent="symptom", urgency="emergency", reason="Reported worsening", tool_context=context
    )

    assert context.state[TRIAGE_DECISION_STATE_KEY]["urgency"] == "emergency"


@pytest.mark.asyncio
async def test_casing_and_padding_do_not_reject_a_real_decision() -> None:
    context = _context()

    result = await submit_triage_decision(
        intent="  Medication_Question ",
        urgency=" ROUTINE",
        reason="  spaced  ",
        tool_context=context,
    )

    assert result == {"recorded": True}
    assert context.state[TRIAGE_DECISION_STATE_KEY]["intent"] == "medication_question"
    assert context.state[TRIAGE_DECISION_STATE_KEY]["urgency"] == "routine"
    assert context.state[TRIAGE_DECISION_STATE_KEY]["reason"] == "spaced"


@pytest.mark.asyncio
async def test_a_long_reason_is_bounded() -> None:
    """The reason is a clinician-facing note, not somewhere to paste the conversation."""
    context = _context()

    await submit_triage_decision(
        intent="general", urgency="routine", reason="x" * 2000, tool_context=context
    )

    assert len(context.state[TRIAGE_DECISION_STATE_KEY]["reason"]) == 500


# ---------------------------------------------------------------------------
# Rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("intent", "urgency"),
    [
        ("not_an_intent", "routine"),
        ("general", "catastrophic"),
        ("", ""),
    ],
)
async def test_a_value_outside_the_accepted_set_is_refused(intent: str, urgency: str) -> None:
    """An unrecognised label would reach the portal and render as something it is not."""
    context = _context()

    result = await submit_triage_decision(
        intent=intent, urgency=urgency, reason="why", tool_context=context
    )

    assert result["error"] == "invalid_decision"
    assert TRIAGE_DECISION_STATE_KEY not in context.state


@pytest.mark.asyncio
async def test_a_rejection_is_readable_rather_than_raised() -> None:
    """A raised error ends the turn; a result lets the model correct itself."""
    result = await submit_triage_decision(
        intent="nonsense", urgency="routine", reason="why", tool_context=_context()
    )

    assert "message" in result


@pytest.mark.asyncio
async def test_a_rejection_does_not_echo_what_was_sent() -> None:
    """The rejected value came from a model reasoning over a patient's own message."""
    result = await submit_triage_decision(
        intent="maria_gomez_has_warfarin_toxicity",
        urgency="routine",
        reason="Patient Maria Gomez reported bleeding",
        tool_context=_context(),
    )

    assert "maria_gomez" not in str(result).lower()
    assert "warfarin" not in str(result).lower()
    assert "bleeding" not in str(result).lower()


@pytest.mark.asyncio
async def test_a_missing_state_is_reported_rather_than_silently_succeeding() -> None:
    """This is the only route to an intent for the turn, so losing it must be visible."""
    result = await submit_triage_decision(
        intent="general", urgency="routine", reason="why", tool_context=SimpleNamespace(state=None)
    )

    assert result["error"] == "not_recorded"


# ---------------------------------------------------------------------------
# Surface
# ---------------------------------------------------------------------------


def test_the_model_cannot_supply_a_patient() -> None:
    """No patient identifier is part of this tool's surface, as with every other tool."""
    parameters = list(inspect.signature(submit_triage_decision).parameters)

    assert parameters == ["intent", "urgency", "reason", "tool_context"]


def test_the_state_key_is_readable_from_a_stream_delta() -> None:
    """Measured on adk 2.9.1: a `temp:`-scoped key never appears in `state_delta`.

    The caller reads this decision from the current turn's delta, so the key must not be
    `temp:`-prefixed or the turn would carry no classification at all.
    """
    assert not TRIAGE_DECISION_STATE_KEY.startswith("temp:")
