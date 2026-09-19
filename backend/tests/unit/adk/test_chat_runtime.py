"""Normalising the agent runtime's event stream into the websocket's contract.

Every test here drives a real `Runner` with stub models, because the properties being
pinned are properties of ADK's stream rather than of our own code, and three of them are
not what the framework's documentation says. Asserting them against a mock of our own
design would prove only that the mock agrees with itself.

The failures these exist to catch are all silent: the patient shown the reasoning stage's
internal notes, the emergency answer dropped by a filter, the reply delivered twice, and a
turn labelled with the previous turn's classification.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.models import BaseLlm, LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import types

from app.adk.agents.care_coordinator import (
    COORDINATOR_AGENT_NAME,
    RESPONDER_AGENT_NAME,
    TOOL_ALLOWLIST,
)
from app.adk.chat_runtime import APP_NAME, CareCoordinatorRuntime
from app.adk.runner import build_runner
from app.adk.tools import submit_triage_decision
from app.models.enums import Language
from app.safety import TRIAGE_COPY
from app.utils.localization import resolve_locale_resource

PATIENT_ID = "11111111-1111-1111-1111-111111111111"

COORDINATOR_NOTES = "NOTES: patient takes metformin 500mg"
REPLY = "Take it with food, and tell your care team if that changes."

STANDARD_DECISION: dict[str, Any] = {
    "intent": "medication_question",
    "urgency": "routine",
    "reason": "asked about a dose",
}

_UNSET = object()
"""Distinguishes "use the standard decision" from an explicit "make no tool call"."""


class _Coordinator(BaseLlm):
    """Reports a decision by calling the tool, then emits internal working notes."""

    decision: dict[str, Any] | None = None
    fired: bool = False

    async def generate_content_async(
        self, llm_request: Any, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        if self.decision is not None and not self.fired:
            self.fired = True
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="submit_triage_decision", args=dict(self.decision)
                            )
                        )
                    ],
                )
            )
            return
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=COORDINATOR_NOTES)])
        )


class _Responder(BaseLlm):
    """Streams a partial, then a final carrying the whole answer."""

    explode: bool = False
    must_not_run: bool = False

    async def generate_content_async(
        self, llm_request: Any, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        if self.must_not_run:
            raise AssertionError("The safety floor must answer without consulting a model")
        if self.explode:
            raise RuntimeError("model unavailable")
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=REPLY[:10])]),
            partial=True,
        )
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=REPLY)]))


def _build_runner(
    *,
    decision: dict[str, Any] | None,
    explode: bool = False,
    must_not_run: bool = False,
    session_service: BaseSessionService | None = None,
) -> Runner:
    return build_runner(
        app_name=APP_NAME,
        agent=SequentialAgent(
            name="pipeline",
            sub_agents=[
                LlmAgent(
                    name=COORDINATOR_AGENT_NAME,
                    model=_Coordinator(model="stub-coordinator", decision=decision),
                    instruction="stub",
                    tools=[submit_triage_decision],
                ),
                LlmAgent(
                    name=RESPONDER_AGENT_NAME,
                    model=_Responder(
                        model="stub-responder", explode=explode, must_not_run=must_not_run
                    ),
                    instruction="stub",
                ),
            ],
        ),
        tool_allowlist=TOOL_ALLOWLIST,
        session_service=session_service,
    )


def _runtime(
    *,
    decision: Any = _UNSET,
    explode: bool = False,
    must_not_run: bool = False,
    session_service: BaseSessionService | None = None,
) -> CareCoordinatorRuntime:
    chosen = STANDARD_DECISION if decision is _UNSET else decision
    return CareCoordinatorRuntime(
        runner=_build_runner(
            decision=chosen,
            explode=explode,
            must_not_run=must_not_run,
            session_service=session_service,
        )
    )


async def _turn(
    runtime: CareCoordinatorRuntime,
    message: str,
    *,
    language: str = Language.EN.value,
    session_id: str = "session-1",
) -> list[dict[str, Any]]:
    return [
        event
        async for event in runtime.process_stream(
            patient_id=PATIENT_ID,
            user_id="user-1",
            session_id=session_id,
            message=message,
            language=language,
        )
    ]


def _first(events: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    return next(event for event in events if event["type"] == kind)


def _chunks(events: list[dict[str, Any]]) -> str:
    return "".join(e["content"] for e in events if e["type"] == "chunk")


# ---------------------------------------------------------------------------
# The contract's shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_turn_yields_a_classification_then_a_completion() -> None:
    events = await _turn(_runtime(), "when do I take my metformin")

    assert events[0]["type"] == "classification"
    assert events[-1]["type"] == "complete"


@pytest.mark.asyncio
async def test_the_classification_comes_from_the_typed_decision() -> None:
    events = await _turn(_runtime(), "when do I take my metformin")

    classification = _first(events, "classification")

    assert classification["intent"] == "medication_question"
    assert classification["urgency"] == "routine"
    assert classification["route"] == "triage"
    assert classification["escalation_required"] is False


@pytest.mark.asyncio
async def test_the_reply_reaches_the_patient() -> None:
    events = await _turn(_runtime(), "when do I take my metformin")

    assert _first(events, "complete")["response_text"] == REPLY


# ---------------------------------------------------------------------------
# The reasoning stage's notes are not for the patient
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_coordinators_working_notes_never_reach_the_patient() -> None:
    """Measured: those notes are ordinary events that report themselves as final."""
    events = await _turn(_runtime(decision=None), "when do I take my metformin")

    rendered = _chunks(events) + _first(events, "complete")["response_text"]

    assert COORDINATOR_NOTES not in rendered
    assert "metformin 500mg" not in rendered


# ---------------------------------------------------------------------------
# The emergency answer must survive the filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_emergency_is_answered_without_consulting_a_model() -> None:
    """The floor's halt arrives authored `model`, not by an agent.

    A filter that kept only the responder's events would have dropped it. The responder
    raises if it is reached at all, so this also proves no model was consulted.
    """
    events = await _turn(_runtime(must_not_run=True), "I have crushing chest pain")

    classification = _first(events, "classification")

    assert classification["urgency"] == "emergency"
    assert classification["escalation_required"] is True
    assert "911" in _first(events, "complete")["response_text"]


@pytest.mark.asyncio
async def test_a_spanish_emergency_is_answered_in_spanish() -> None:
    events = await _turn(
        _runtime(must_not_run=True), "tengo dolor de pecho muy fuerte", language=Language.ES.value
    )

    text = _first(events, "complete")["response_text"]

    assert "911" in text
    assert "emergencia" in text.lower()


@pytest.mark.asyncio
async def test_self_harm_is_routed_for_the_crisis_line() -> None:
    events = await _turn(_runtime(must_not_run=True), "I want to kill myself")

    classification = _first(events, "classification")

    assert classification["intent"] == "mental_health"
    assert "988" in _first(events, "complete")["response_text"]


@pytest.mark.asyncio
async def test_spanish_self_harm_also_reaches_the_crisis_line() -> None:
    """Covered separately from the English case and from the Spanish emergency case.

    Those two between them would leave this exact combination — Spanish *and* self-harm —
    asserted nowhere, and it is the one where a missing translation costs the most.
    """
    events = await _turn(
        _runtime(must_not_run=True), "quiero quitarme la vida", language=Language.ES.value
    )

    classification = _first(events, "classification")
    text = _first(events, "complete")["response_text"]

    assert classification["intent"] == "mental_health"
    assert classification["urgency"] == "emergency"
    assert "988" in text
    assert "911" in text
    assert "suicidio" in text.lower()


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_final_answer_is_not_also_sent_as_a_chunk() -> None:
    """Measured: the final event repeats the whole answer, not the remaining delta.

    Streaming the partials and then the final would deliver the reply twice, so only the
    partial is chunked and the final becomes the authoritative text.
    """
    events = await _turn(_runtime(), "when do I take my metformin")

    assert _chunks(events) == REPLY[:10]
    assert _first(events, "complete")["response_text"] == REPLY


# ---------------------------------------------------------------------------
# Degradation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failing_model_tells_the_patient_rather_than_guessing() -> None:
    events = await _turn(_runtime(explode=True), "when do I take my metformin")

    complete = _first(events, "complete")
    expected = resolve_locale_resource(Language.EN.value, TRIAGE_COPY)["service_unavailable"]

    assert complete["response_text"] == expected
    assert complete["fallback_used"] is True


@pytest.mark.asyncio
async def test_an_outage_still_points_at_emergency_care() -> None:
    events = await _turn(_runtime(explode=True), "when do I take my metformin")

    assert "911" in _first(events, "complete")["response_text"]


@pytest.mark.asyncio
async def test_a_turn_without_a_decision_still_answers() -> None:
    """A missed tool call costs the label, not the reply, which is grounded either way."""
    events = await _turn(_runtime(decision=None), "when do I take my metformin")

    classification = _first(events, "classification")

    assert classification["intent"] == "general"
    assert classification["urgency"] == "routine"
    assert _first(events, "complete")["response_text"] == REPLY


@pytest.mark.asyncio
async def test_an_empty_message_matches_the_established_contract() -> None:
    events = await _turn(_runtime(), "   ")

    assert _first(events, "classification")["classification_reason"] == "Empty patient message"
    assert _first(events, "complete")["response_text"] == ""


# ---------------------------------------------------------------------------
# The staleness this design exists to prevent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_later_turn_does_not_inherit_an_earlier_classification() -> None:
    """The decision key is not `temp:`-scoped, because a `temp:` key never reaches a delta.

    It therefore persists in session state, and a turn where the model never called the
    tool could otherwise be labelled with the previous turn's intent and urgency. The
    caller reads only the current turn's delta, which is what makes that impossible rather
    than merely unlikely. Both turns share one session service, which is what carries the
    stale value across.
    """
    classifying = _runtime()
    first = await _turn(classifying, "when do I take my metformin", session_id="shared")

    assert _first(first, "classification")["intent"] == "medication_question"

    silent = _runtime(decision=None, session_service=classifying.runner.session_service)
    second = await _turn(silent, "thanks, that helps", session_id="shared")

    classification = _first(second, "classification")

    assert classification["intent"] == "general"
    assert classification["urgency"] == "routine"


# ---------------------------------------------------------------------------
# Escalation is re-applied in code, not trusted to the model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_model_cannot_talk_an_emergency_down() -> None:
    """`apply_safety_override` is monotonic: it may raise an urgency and never lower one."""
    understated = _runtime(
        decision={"intent": "general", "urgency": "routine", "reason": "seems fine"},
        must_not_run=True,
    )

    events = await _turn(understated, "I have crushing chest pain")

    assert _first(events, "classification")["urgency"] == "emergency"
