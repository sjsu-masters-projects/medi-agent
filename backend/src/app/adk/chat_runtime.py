"""Drive one patient chat turn on the agent runtime, in the shape the websocket expects.

This is an adapter, and that is the point. The websocket contract — `classification`, then
zero or more `chunk`s, then `complete` — is what the portal renders and what the
integration tests pin. Rewriting the router's turn loop around ADK's event stream would
have put that contract at the mercy of a framework's internals. Instead the stream is
normalised here, so the contract is preserved by construction and the router changes
barely at all.

Three properties of ADK's stream decide this code, and all three were measured against a
live runner on adk 2.9.1 rather than read from documentation:

**The reasoning stage's working notes are ordinary events, and they report themselves as
final responses.** Forwarding every event would show the patient the coordinator's
internal notes. Events authored by the coordinator are therefore dropped. The filter
excludes that author rather than including the responder, because of the next point.

**The safety floor's halt arrives authored `model`, not by any agent.** It is a single
event carrying the reviewed 911/988 copy. A filter that kept only the responder would have
silently dropped the emergency answer — the one message in the product that must never be
lost.

**The final event repeats the whole answer rather than the remaining delta.** Streaming
the partials and then the final would deliver the reply twice, so the final event sets the
authoritative text and is not re-emitted as a chunk.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.agents import RunConfig

# `StreamingMode` really does live here at runtime; the `google.adk.agents` package just
# does not re-export it, which mypy reads as reaching into something private. Ignored
# narrowly at the import rather than loosened anywhere else, because the alternative is
# importing the streaming mode from a module that does not define it.
from google.adk.agents.run_config import StreamingMode  # type: ignore[attr-defined]
from google.adk.runners import Runner
from google.genai import types

from app.adk.agents.care_coordinator import (
    COORDINATOR_AGENT_NAME,
    TOOL_ALLOWLIST,
    build_care_coordinator,
    route_for_intent,
)
from app.adk.plugins import LOCALE_STATE_KEY
from app.adk.runner import build_runner
from app.adk.tools import (
    DOCUMENT_CONTEXT_STATE_KEY,
    PATIENT_ID_STATE_KEY,
    TRIAGE_DECISION_STATE_KEY,
)
from app.core.llm_failures import categorize_llm_failure
from app.core.observability import record_chat_fallback
from app.safety import TRIAGE_COPY, apply_safety_override, deterministic_safety_floor
from app.utils.localization import resolve_locale_resource

logger = logging.getLogger(__name__)

APP_NAME = "mediagent"

_runner: Runner | None = None


def get_chat_runner() -> Runner:
    """Build the chat runner once per process, not once per connection.

    Constructing it resolves Application Default Credentials and builds a Vertex client.
    Doing that per websocket connection would spend a patient's first-token budget on
    setup and turn a credential problem into a per-connection failure. Sessions are keyed
    per conversation inside the one runner, so a single instance still keeps conversations
    apart.
    """
    global _runner
    if _runner is None:
        _runner = build_runner(
            app_name=APP_NAME,
            agent=build_care_coordinator(),
            tool_allowlist=TOOL_ALLOWLIST,
        )
    return _runner


def reset_chat_runner() -> None:
    """Drop the cached runner. For tests, which must not share one between cases."""
    global _runner
    _runner = None


def _text_of(event: Any) -> str:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    return "".join(part.text or "" for part in parts if getattr(part, "text", None))


def _decision_from(event: Any) -> dict[str, Any] | None:
    """Read this turn's triage decision from the event's state delta, and only from there.

    Deliberately not read from session state. A `temp:`-scoped key would never appear in a
    delta at all (measured), so the key is a plain one and does persist — which means a
    turn where the model never called the tool could otherwise inherit the previous turn's
    intent and urgency and label a new message with them. Reading only the current turn's
    delta makes that stale value unreadable rather than merely unlikely to be read.
    """
    actions = getattr(event, "actions", None)
    delta = getattr(actions, "state_delta", None) if actions else None
    if not delta:
        return None
    decision = delta.get(TRIAGE_DECISION_STATE_KEY)
    return decision if isinstance(decision, dict) else None


class CareCoordinatorRuntime:
    """Runs one chat turn and yields the router's event shape."""

    def __init__(self, runner: Runner | None = None) -> None:
        self._runner = runner

    @property
    def runner(self) -> Runner:
        return self._runner if self._runner is not None else get_chat_runner()

    async def _ensure_session(
        self, *, user_id: str, session_id: str, state: dict[str, Any]
    ) -> None:
        service = self.runner.session_service
        existing = await service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        if existing is None:
            await service.create_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id, state=state
            )

    async def process_stream(
        self,
        *,
        patient_id: str,
        user_id: str,
        session_id: str,
        message: str,
        language: str,
        document_context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield `classification`, then `chunk`s, then `complete` for one turn."""
        text = message.strip()
        if not text:
            yield _classification("general", "routine", "Empty patient message", False)
            yield {"type": "complete", "response_text": "", "fallback_used": True}
            return

        localized = resolve_locale_resource(language, TRIAGE_COPY)

        # The floor is consulted here for the *label* only. The halt itself is enforced by
        # `SafetyFloorPlugin` before any agent runs; this does not re-decide it, it reads
        # the same deterministic rules so the turn can report an intent and an urgency the
        # plugin's single event does not carry.
        floor = deterministic_safety_floor(text)
        if floor is not None:
            yield _classification(floor.intent, floor.urgency, floor.reason, True)

        await self._ensure_session(
            user_id=user_id,
            session_id=session_id,
            state={PATIENT_ID_STATE_KEY: patient_id, LOCALE_STATE_KEY: language},
        )

        classified = floor is not None
        answer = ""
        streamed = False

        try:
            stream = self.runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=types.Content(role="user", parts=[types.Part(text=text)]),
                state_delta=(
                    {DOCUMENT_CONTEXT_STATE_KEY: document_context}
                    if document_context is not None
                    else {}
                ),
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
            async for event in stream:
                decision = _decision_from(event)
                if decision is not None and not classified:
                    intent, urgency, reason, escalate = _apply_floor_rules(decision, text)
                    classified = True
                    yield _classification(intent, urgency, reason, escalate)

                if event.author == COORDINATOR_AGENT_NAME:
                    # Internal working notes. Never shown to the patient.
                    continue

                body = _text_of(event)
                if not body:
                    continue

                if not classified:
                    # The model answered without recording a decision. The reply is still
                    # grounded, so it ships; only the label is missing, and a neutral one
                    # is honest about that. Escalation cannot be lost this way — it is
                    # re-applied deterministically from the message itself.
                    intent, urgency, reason, escalate = _apply_floor_rules(
                        {"intent": "general", "urgency": "routine", "reason": ""}, text
                    )
                    classified = True
                    yield _classification(intent, urgency, reason, escalate)

                if getattr(event, "partial", False):
                    streamed = True
                    yield {"type": "chunk", "content": body}
                else:
                    # The final event repeats the whole answer rather than the remainder,
                    # so it becomes the authoritative text and is not re-sent as a chunk.
                    answer = body
        except Exception as exc:
            reason = categorize_llm_failure(exc)
            record_chat_fallback(layer="adk_turn", reason=reason)
            logger.warning(
                "Care Coordinator turn failed: %s",
                exc,
                extra={"chat_fallback_layer": "adk_turn", "chat_fallback_reason": reason},
            )
            if not classified:
                yield _classification("general", "routine", "Model unavailable", False)
            if not streamed:
                unavailable = localized["service_unavailable"]
                yield {"type": "chunk", "content": unavailable}
                yield {"type": "complete", "response_text": unavailable, "fallback_used": True}
                return
            yield {"type": "complete", "response_text": answer, "fallback_used": True}
            return

        if not classified:
            yield _classification("general", "routine", "Model unavailable", False)

        if not answer and not streamed:
            # Nothing was produced at all. The patient is told so rather than handed an
            # empty bubble, which is the same rule the rest of the product follows.
            unavailable = localized["service_unavailable"]
            yield {"type": "chunk", "content": unavailable}
            yield {"type": "complete", "response_text": unavailable, "fallback_used": True}
            return

        yield {"type": "complete", "response_text": answer, "fallback_used": False}


def _apply_floor_rules(decision: dict[str, Any], message: str) -> tuple[str, str, str, bool]:
    """Re-apply deterministic escalation over whatever the model decided.

    `apply_safety_override` is monotonic: it may raise an urgency and never lower one. So
    a model that under-calls urgency cannot talk the turn down, and one that over-calls it
    is left alone.
    """
    intent, urgency, reason = apply_safety_override(
        intent=str(decision.get("intent") or "general"),
        urgency=str(decision.get("urgency") or "routine"),
        reason=str(decision.get("reason") or ""),
        message=message,
    )
    return intent, urgency, reason, urgency in {"urgent", "emergency"}


def _classification(intent: str, urgency: str, reason: str, escalate: bool) -> dict[str, Any]:
    return {
        "type": "classification",
        "intent": intent,
        "urgency": urgency,
        "route": route_for_intent(intent),
        "escalation_required": escalate,
        "classification_reason": reason,
    }
