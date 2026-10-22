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

import asyncio
import json
import logging
import time
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
    RESPONDER_AGENT_NAME,
    TOOL_ALLOWLIST,
    build_care_coordinator,
    route_for_intent,
)
from app.adk.evidence import build_evidence, care_plan_ids_of, tool_names_of
from app.adk.grounding import (
    StreamingReplyFilter,
    cited_sources,
    plain_reply,
    source_line,
    sources_from_event,
    unsupported_doses,
    without_source_lines,
)
from app.adk.models.resilient import DRAFT_RESET_KEY, ResilientLlm
from app.adk.plugins import LOCALE_STATE_KEY
from app.adk.recap import build_recap
from app.adk.runner import build_runner
from app.adk.tools import (
    DOCUMENT_CONTEXT_STATE_KEY,
    PATIENT_ID_STATE_KEY,
    RECENT_CONVERSATION_STATE_KEY,
    REPLY_LANGUAGE_STATE_KEY,
    TRIAGE_DECISION_STATE_KEY,
)
from app.adk.tools.turn_sources import DOCUMENT_SOURCE
from app.config import settings
from app.core.llm_failures import categorize_llm_failure
from app.core.observability import record_chat_fallback
from app.core.structured_logging import log_event
from app.models.generation import GenerationErrorCode, GenerationProviderError
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
    ResilientLlm.reset_circuits()


def _text_of(event: Any) -> str:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    return "".join(part.text or "" for part in parts if getattr(part, "text", None))


def _is_draft_reset(event: Any) -> bool:
    metadata = getattr(event, "custom_metadata", None)
    return isinstance(metadata, dict) and bool(metadata.get(DRAFT_RESET_KEY))


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
    ) -> list[Any]:
        """Create the session if needed; return its prior events for the recap."""
        service = self.runner.session_service
        existing = await service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        if existing is None:
            await service.create_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id, state=state
            )
            return []
        return list(getattr(existing, "events", None) or [])

    async def process_stream(
        self,
        *,
        patient_id: str,
        user_id: str,
        session_id: str,
        message: str,
        language: str,
        document_context: dict[str, Any] | None = None,
        earlier_messages: list[dict[str, Any]] | None = None,
        conversation_summary: str | None = None,
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

        # Keyed by patient as well as conversation: a clinician's user id with the same
        # conversation id for two patients must never reuse the first patient's session,
        # whose state names that patient for every tool.
        runtime_session_id = f"{patient_id}:{session_id}"
        prior_events = await self._ensure_session(
            user_id=user_id,
            session_id=runtime_session_id,
            state={PATIENT_ID_STATE_KEY: patient_id, LOCALE_STATE_KEY: language},
        )
        # The stored conversation is the source of the recap when the caller has it; the
        # in-process session is lost on every restart and deploy.
        recap = (
            recap_from_messages(earlier_messages, conversation_summary)
            if earlier_messages is not None
            else recent_conversation(prior_events, conversation_summary)
        )
        turn_state: dict[str, Any] = {
            RECENT_CONVERSATION_STATE_KEY: recap,
            REPLY_LANGUAGE_STATE_KEY: language,
        }
        if document_context is not None:
            turn_state[DOCUMENT_CONTEXT_STATE_KEY] = document_context

        classified = floor is not None
        answer = ""
        streamed = False
        # What the patient sees while the reply is written is already in its final form: source
        # lines and Markdown marks are removed as the text arrives, not afterwards, so a draft
        # (and any sentence spoken from it) is a prefix of the saved reply.
        reply_filter = StreamingReplyFilter()
        shown: list[str] = []
        sources: list[dict[str, Any]] = []
        tool_results: list[str] = []
        tools_used: list[str] = []
        plan_ids: list[str] = []

        model_started = time.monotonic()
        model_seen: list[str] = []
        log_event(
            logger,
            "chat_model.start",
            message="Chat model stream starting",
            model=settings.gemini_flash_model,
        )

        def model_end(outcome: str) -> None:
            # The provider's own model id when events carry it; a name that differs from the
            # configured primary means the model fallback answered.
            used = model_seen[-1] if model_seen else settings.gemini_flash_model
            log_event(
                logger,
                "chat_model.end",
                message="Chat model stream ended",
                model=used,
                fallback_used=bool(model_seen) and not used.startswith(settings.gemini_flash_model),
                outcome=outcome,
                duration_ms=int((time.monotonic() - model_started) * 1000),
            )

        try:
            stream = self.runner.run_async(
                user_id=user_id,
                session_id=runtime_session_id,
                new_message=types.Content(role="user", parts=[types.Part(text=text)]),
                state_delta=turn_state,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
            async with asyncio.timeout(settings.chat_turn_timeout_seconds):
                async for event in stream:
                    version = getattr(event, "model_version", None)
                    if isinstance(version, str) and version:
                        model_seen.append(version)
                    decision = _decision_from(event)
                    if decision is not None and not classified:
                        intent, urgency, reason, escalate = _apply_floor_rules(decision, text)
                        classified = True
                        yield _classification(intent, urgency, reason, escalate)

                    if _is_draft_reset(event):
                        # The model failed after text was shown and the backup is answering
                        # from the start: withdraw what was shown, then stream the new reply.
                        reply_filter = StreamingReplyFilter()
                        if shown:
                            yield {"type": "chunk_reset"}
                        shown.clear()
                        streamed = False
                        continue

                    used = sources_from_event(event)
                    if used is not None:
                        sources = used
                    tool_results.extend(_tool_results_of(event))
                    tools_used.extend(tool_names_of(event))
                    plan_ids.extend(care_plan_ids_of(event))

                    if event.author == COORDINATOR_AGENT_NAME:
                        # Internal working notes. Never shown to the patient.
                        continue

                    body = _text_of(event)
                    if not body:
                        continue

                    if not classified:
                        # A prose answer does not prove triage occurred. Do not silently
                        # invent a routine label for a missing decision; return the reviewed
                        # localized outage response before any generated prose is exposed.
                        raise GenerationProviderError(
                            GenerationErrorCode.INVALID_RESPONSE,
                            "Coordinator did not submit a triage decision",
                        )

                    if getattr(event, "partial", False):
                        visible = reply_filter.feed(body)
                        if visible:
                            streamed = True
                            shown.append(visible)
                            yield {"type": "chunk", "content": visible}
                    else:
                        # The final event repeats the whole answer rather than the remainder,
                        # so it becomes the authoritative text and is not re-sent as a chunk.
                        answer = body
        except Exception as exc:
            reason = categorize_llm_failure(exc)
            model_end(f"error:{reason}")
            record_chat_fallback(layer="adk_turn", reason=reason)
            logger.warning(
                "Care Coordinator turn failed: %s",
                type(exc).__name__,
                extra={"chat_fallback_layer": "adk_turn", "chat_fallback_reason": reason},
            )
            if not classified:
                yield _classification("general", "routine", "Model unavailable", False)
            if answer:
                yield {
                    "type": "complete",
                    "response_text": plain_reply(without_source_lines(answer)),
                    "fallback_used": True,
                }
                return
            unavailable = localized["service_unavailable"]
            if streamed:
                # Text the patient already saw is not a finished answer: it is withdrawn and the
                # reviewed message replaces it (viewers and any audio stop and use this).
                yield {"type": "chunk_reset"}
            yield {"type": "chunk", "content": unavailable}
            yield {"type": "complete", "response_text": unavailable, "fallback_used": True}
            return

        model_end("ok")
        if not classified:
            yield _classification("general", "routine", "Model unavailable", False)

        held = reply_filter.finish()  # the end of a reply that ended mid-line
        if held:
            streamed = True
            shown.append(held)
            yield {"type": "chunk", "content": held}

        if not answer and not streamed:
            # Nothing was produced at all. The patient is told so rather than handed an
            # empty bubble, which is the same rule the rest of the product follows.
            unavailable = localized["service_unavailable"]
            yield {"type": "chunk", "content": unavailable}
            yield {"type": "complete", "response_text": unavailable, "fallback_used": True}
            return

        # The citation is written from what the tools returned, never by the model: a
        # source line it wrote is removed whether or not a tool returned anything. The
        # patient's documents are cited the same way as reference pages, in one line.
        answer = plain_reply(without_source_lines(answer))
        cited_documents: list[str] = []
        cited: list[dict[str, Any]] = []
        if sources:
            cited = cited_sources(sources, answer)
            cited_documents = [
                str(item["document_id"])
                for item in cited
                if item.get("source") == DOCUMENT_SOURCE and item.get("document_id")
            ]
            line = source_line(cited, language)
            if line:
                if streamed:
                    yield {"type": "chunk", "content": f"\n\n{line}"}
                answer = f"{answer}\n\n{line}"
        if streamed and not answer.startswith("".join(shown).strip()):
            # The reply changed after it was shown: viewers replace it with this one. Counts
            # only, never the text.
            log_event(
                logger,
                "chat_model.draft_replaced",
                level=logging.WARNING,
                message="The saved reply differs from the draft shown while it was written",
                draft_chars=len("".join(shown)),
                reply_chars=len(answer),
            )
        unsupported = unsupported_doses(answer, *tool_results)
        if unsupported:
            # Measured before it is allowed to block: the count, never the text.
            logger.warning(
                "Reply mentions a dose not found in the record or sources",
                extra={"unsupported_dose_count": len(unsupported)},
            )

        yield {
            "type": "complete",
            "response_text": answer,
            "fallback_used": False,
            # The server attaches these documents' results to the saved reply.
            "cited_documents": cited_documents,
            # What the reply rested on, stored beside the saved reply (never shown as text).
            "evidence": build_evidence(tools=tools_used, cited=cited, care_plan_ids=plan_ids),
        }


_REFERENCE_TOOLS = frozenset({"get_medication_information", "get_condition_information"})


def _tool_results_of(event: Any) -> list[str]:
    """The patient's own record from this event's tool results, for the dose check.

    Reference tools are left out on purpose: a dose found only in general reference text
    is exactly what the check exists to catch.
    """
    responses = event.get_function_responses() if hasattr(event, "get_function_responses") else []
    return [
        json.dumps(getattr(item, "response", None), default=str)
        for item in responses or []
        if getattr(item, "name", None) not in _REFERENCE_TOOLS
    ]


def recent_conversation(events: list[Any], summary: str | None = None) -> str:
    """The recap built from in-process session events (used when stored messages are absent).

    Tool calls, tool results and internal notes are left out on purpose: replaying them
    is what made the coordinator skip the current turn's decision.
    """
    messages: list[dict[str, Any]] = []
    for event in events:
        if getattr(event, "partial", False):
            continue
        author = getattr(event, "author", "")
        role = "user" if author == "user" else "assistant" if author == RESPONDER_AGENT_NAME else ""
        if role:
            messages.append({"role": role, "content": _text_of(event)})
    return build_recap(messages, summary)


def recap_from_messages(messages: list[dict[str, Any]], summary: str | None = None) -> str:
    """The same recap, built from stored chat messages rather than in-process events."""
    return build_recap(messages, summary)


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
