"""LangGraph state machine for Triage Agent."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.agents.triage.prompts import (
    CHAT_RESPONSE_SYSTEM_INSTRUCTION,
    TRIAGE_CLASSIFICATION_SYSTEM_INSTRUCTION,
    build_triage_classification_prompt,
    build_triage_response_prompt,
)
from app.clients.model_router import ModelRouter, TaskType
from app.core.observability import record_chat_fallback
from app.models.enums import Language, coerce_locale
from app.safety import TRIAGE_COPY, apply_safety_override, deterministic_safety_floor
from app.utils.localization import resolve_locale_resource

logger = logging.getLogger(__name__)

IntentType = Literal[
    "symptom",
    "medication_question",
    "schedule",
    "document_question",
    "mental_health",
    "general",
]
UrgencyType = Literal["routine", "urgent", "emergency"]


class TriageClassificationResult(BaseModel):
    """Structured classification output returned by the model."""

    intent: IntentType
    urgency: UrgencyType
    reason: str = Field(default="")
    # Set only by the deterministic safety floor, never by the model. It names which
    # rule forced the classification so an escalation can be traced to its cause.
    safety_rule: str | None = Field(default=None)


class TriageState(TypedDict, total=False):
    """State passed across triage graph nodes."""

    # Set when the model could not classify the message. It is not an intent — it is the
    # absence of one, kept distinct so no downstream node reads a placeholder
    # classification as though it were a finding.
    classification_unavailable: bool
    patient_id: str
    user_id: str
    language: str
    message: str
    history: list[dict[str, Any]]
    patient_context: dict[str, Any]
    document_context: dict[str, Any] | None
    conversation_state: dict[str, Any]

    intent: str
    urgency: str
    route: str
    classification_reason: str
    safety_rule: str | None
    escalation_required: bool

    assistant_response: str
    error: str | None


@dataclass(frozen=True)
class _MessageContext:
    message: str
    language: str
    history: list[dict[str, Any]]
    patient_context: dict[str, Any]
    document_context: dict[str, Any] | None
    conversation_state: dict[str, Any]


@dataclass(frozen=True)
class _ResponseRequest:
    context: _MessageContext
    intent: str
    urgency: str


async def classify_intent(state: TriageState, router: ModelRouter) -> TriageState:
    """Node 1: classify intent and urgency."""
    context = _build_context(state)
    if not context.message:
        return _empty_message_state(state)

    # The safety floor runs before the model, not after it. These rules previously ran
    # only in the fallback for a failed LLM call, so a healthy model that misread
    # "crushing chest pain" as small talk had nothing behind it. Deciding first also skips
    # a network round trip on the messages that can least afford one.
    floor = _deterministic_safety_floor(context.message)
    if floor is not None:
        logger.warning(
            "Triage safety floor forced an emergency classification: %s", floor.safety_rule
        )
        return _merge_classification(state, floor)

    llm_result = await _classify_with_llm(router, context)
    if llm_result is None:
        # No guess. This previously fell back to a keyword cascade that would decide
        # "medication question" from a list of seven drug names, producing a confident
        # answer to a question nobody had understood. For clinical content that is worse
        # than saying nothing, so the patient is told the service is unavailable instead.
        # The emergency floor has already run above and is unaffected.
        return _unavailable_classification_state(state)

    result = _apply_safety_override(llm_result, context.message)
    return _merge_classification(state, result)


async def generate_response(state: TriageState, router: ModelRouter) -> TriageState:
    """Node 2: generate patient-facing response."""
    context = _build_context(state)
    intent = str(state.get("intent", "general"))
    urgency = str(state.get("urgency", "routine"))
    if urgency == "emergency":
        return _merge_response(
            state,
            _emergency_response(context.language, intent=intent),
            escalation_required=True,
        )

    if state.get("classification_unavailable"):
        # Nothing was understood, so nothing is generated. Calling the model here would
        # be a second doomed round trip on a path that has already failed once, and any
        # answer it produced would be addressing a question we never classified.
        return _merge_response(state, service_unavailable_response(context.language))

    response = await _generate_response_with_llm(
        router,
        _ResponseRequest(context=context, intent=intent, urgency=urgency),
    )
    if response:
        return _merge_response(state, response)

    fallback = _fallback_response(
        language=context.language,
        intent=intent,
        urgency=urgency,
        message=context.message,
    )
    return _merge_response(state, fallback)


def build_triage_graph(router: ModelRouter) -> Any:
    """Build and compile triage graph."""

    async def _classify(state: TriageState) -> TriageState:
        return await classify_intent(state, router)

    async def _respond(state: TriageState) -> TriageState:
        return await generate_response(state, router)

    workflow: StateGraph[TriageState] = StateGraph(TriageState)
    workflow.add_node("classify_intent", _classify)
    workflow.add_node("generate_response", _respond)

    workflow.add_edge(START, "classify_intent")
    workflow.add_edge("classify_intent", "generate_response")
    workflow.add_edge("generate_response", END)

    return workflow.compile()


async def _classify_with_llm(
    router: ModelRouter,
    context: _MessageContext,
) -> TriageClassificationResult | None:
    prompt = build_triage_classification_prompt(
        message=context.message,
        language=context.language,
        history=context.history,
        patient_context=context.patient_context,
        document_context=context.document_context,
        conversation_state=context.conversation_state,
    )

    try:
        client = router.get_client(TaskType.TRIAGE_CLASSIFICATION)
        return await client.generate_structured(
            prompt=prompt,
            response_model=TriageClassificationResult,
            system_instruction=TRIAGE_CLASSIFICATION_SYSTEM_INSTRUCTION,
            temperature=0.1,
        )
    except Exception as exc:
        fallback_reason = categorize_llm_failure(exc)
        record_chat_fallback(layer="L1_classification", reason=fallback_reason)
        logger.warning(
            "Triage LLM classification failed; falling back to rules: %s",
            exc,
            extra={
                "chat_fallback_layer": "L1_classification",
                "chat_fallback_reason": fallback_reason,
            },
        )
        return None


async def _generate_response_with_llm(router: ModelRouter, request: _ResponseRequest) -> str | None:
    prompt = build_triage_response_prompt(
        message=request.context.message,
        intent=request.intent,
        urgency=request.urgency,
        language=request.context.language,
        history=request.context.history,
        patient_context=request.context.patient_context,
        document_context=request.context.document_context,
        conversation_state=request.context.conversation_state,
    )

    try:
        response = await router.generate_text(
            TaskType.CHAT_RESPONSE,
            prompt=prompt,
            system_instruction=CHAT_RESPONSE_SYSTEM_INSTRUCTION,
            temperature=0.35,
            max_tokens=512,
        )
    except Exception as exc:
        fallback_reason = categorize_llm_failure(exc)
        record_chat_fallback(layer="L2_response", reason=fallback_reason)
        logger.warning(
            "Triage LLM response generation failed; using fallback: %s",
            exc,
            extra={
                "chat_fallback_layer": "L2_response",
                "chat_fallback_reason": fallback_reason,
            },
        )
        return None

    cleaned = response.strip()
    if not cleaned:
        record_chat_fallback(layer="L2_response", reason="empty_response")
        logger.info(
            "Triage LLM returned empty response; using fallback",
            extra={
                "chat_fallback_layer": "L2_response",
                "chat_fallback_reason": "empty_response",
            },
        )
        return None
    return cleaned


def _deterministic_safety_floor(message: str) -> TriageClassificationResult | None:
    """Classify the messages that must never depend on a model, or return None.

    The rules themselves live in `app.safety.triage_floor`, which has no framework
    imports, so replacing the agent runtime cannot disturb them. This wrapper only
    adapts the verdict to the classification model this graph passes around.
    """
    verdict = deterministic_safety_floor(message)
    if verdict is None:
        return None

    return TriageClassificationResult(
        intent=verdict.intent,
        urgency=verdict.urgency,
        reason=verdict.reason,
        safety_rule=verdict.safety_rule,
    )


def categorize_llm_failure(exc: BaseException) -> str:
    """Bucket an LLM exception into a stable label for metrics/dashboards."""
    name = type(exc).__name__
    text = f"{name}: {exc}".lower()
    if "credentials" in text or "permissiondenied" in name.lower() or "403" in text:
        return "auth_error"
    if "notfound" in name.lower() or "404" in text:
        return "endpoint_not_found"
    if "timeout" in name.lower() or "deadline" in text or "timed out" in text:
        return "timeout"
    if "429" in text or "quota" in text or "resourceexhausted" in name.lower():
        return "quota_exceeded"
    if "validation" in name.lower() or "json" in name.lower() or "parse" in text:
        return "parse_error"
    if "connection" in name.lower() or "network" in name.lower():
        return "network_error"
    return "unknown_error"


def _emergency_response(language: str, *, intent: str = "symptom") -> str:
    localized = resolve_locale_resource(language, TRIAGE_COPY)
    if intent == "mental_health":
        return localized["mental_health_emergency_response"]
    return localized["emergency_response"]


def _fallback_response(*, language: str, intent: str, urgency: str, message: str) -> str:
    localized_copy = resolve_locale_resource(language, TRIAGE_COPY)
    if intent == "medication_question":
        return localized_copy["fallback_medication_question"]
    if intent == "document_question":
        return localized_copy["fallback_document_question"]
    if intent == "schedule":
        return localized_copy["fallback_schedule"]
    if intent == "mental_health":
        return localized_copy["fallback_mental_health"]
    if urgency == "urgent":
        return localized_copy["fallback_urgent"]
    if _is_non_clinical_math_query(message):
        return localized_copy["fallback_non_clinical"]
    return localized_copy["fallback_general"]


def _is_non_clinical_math_query(message: str) -> bool:
    cleaned = message.strip().lower()
    if not cleaned:
        return False
    if any(
        token in cleaned
        for token in ("symptom", "medication", "medicine", "dolor", "síntoma", "sintoma")
    ):
        return False
    return bool(re.fullmatch(r"[0-9\s+\-*/().=?]+", cleaned))


def _build_context(state: TriageState) -> _MessageContext:
    return _MessageContext(
        message=str(state.get("message", "")).strip(),
        language=coerce_locale(state.get("language", Language.EN.value)).value,
        history=state.get("history", []),
        patient_context=state.get("patient_context", {}),
        document_context=state.get("document_context"),
        conversation_state=state.get("conversation_state", {}),
    )


def _merge_classification(
    state: TriageState,
    result: TriageClassificationResult,
) -> TriageState:
    route = _route_for_intent(result.intent)
    return {
        **state,
        "intent": result.intent,
        "urgency": result.urgency,
        "route": route,
        "classification_reason": result.reason,
        "safety_rule": result.safety_rule,
        "escalation_required": result.urgency in {"urgent", "emergency"},
    }


def _merge_response(
    state: TriageState,
    response_text: str,
    escalation_required: bool | None = None,
) -> TriageState:
    escalate = escalation_required
    if escalate is None:
        escalate = bool(state.get("escalation_required", False))

    return {
        **state,
        "assistant_response": response_text,
        "escalation_required": escalate,
    }


def _empty_message_state(state: TriageState) -> TriageState:
    return {
        **state,
        "intent": "general",
        "urgency": "routine",
        "route": "triage",
        "classification_reason": "Empty patient message",
        "escalation_required": False,
    }


UNAVAILABLE_REASON = "Model unavailable; no classification was made"


def service_unavailable_response(language: str) -> str:
    """What a patient is told when the model could not answer.

    It admits the failure, avoids implying anything clinical was understood, and still
    names where to go — because "we are having trouble" on its own is unsafe for someone
    who is actually unwell and whose wording did not trip the emergency floor.
    """
    return str(resolve_locale_resource(language, TRIAGE_COPY)["service_unavailable"])


def _unavailable_classification_state(state: TriageState) -> TriageState:
    """The shape of "we did not classify this", following `_empty_message_state`.

    `general` and `routine` are carried only because the wire contract requires an intent
    and an urgency on every turn. `classification_unavailable` is what downstream nodes
    actually read, so neither value is ever mistaken for something the model decided.
    """
    return {
        **state,
        "classification_unavailable": True,
        "intent": "general",
        "urgency": "routine",
        "route": "triage",
        "classification_reason": UNAVAILABLE_REASON,
        "escalation_required": False,
    }


def _apply_safety_override(
    result: TriageClassificationResult,
    message: str,
) -> TriageClassificationResult:
    """Escalate a classification when a deterministic signal outranks it.

    Delegates to `app.safety.escalation`, which is monotonic: it may raise urgency and
    never lower it, and unlike the previous implementation it can reach `emergency`
    rather than stopping at `urgent`.
    """
    intent, urgency, reason = apply_safety_override(
        intent=result.intent,
        urgency=result.urgency,
        reason=result.reason,
        message=message,
    )
    if (intent, urgency, reason) == (result.intent, result.urgency, result.reason):
        return result

    return TriageClassificationResult(
        intent=intent,  # type: ignore[arg-type]
        urgency=urgency,
        reason=reason,
        safety_rule=result.safety_rule,
    )


def _route_for_intent(intent: str) -> str:
    if intent == "symptom":
        return "symptom"
    return "triage"
