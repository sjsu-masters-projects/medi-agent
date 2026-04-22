"""LangGraph state machine for Triage Agent."""

from __future__ import annotations

import logging
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
from app.models.enums import Language, coerce_locale

logger = logging.getLogger(__name__)

EMERGENCY_KEYWORDS = frozenset(
    {
        "chest pain",
        "cannot breathe",
        "can't breathe",
        "shortness of breath",
        "passed out",
        "unconscious",
        "stroke",
        "seizure",
        "severe bleeding",
        "anaphylaxis",
        "suicidal",
        "suicide",
        "kill myself",
    }
)
SCHEDULE_KEYWORDS = frozenset({"appointment", "reschedule", "book", "visit"})
MEDICATION_KEYWORDS = frozenset(
    {
        "medication",
        "medicine",
        "medicina",
        "medicamento",
        "dose",
        "dosis",
        "pill",
        "pastilla",
        "tablet",
        "drug",
        "refill",
        "side effect",
        "reaction",
    }
)
MENTAL_HEALTH_KEYWORDS = frozenset(
    {
        "panic",
        "anxious",
        "anxiety",
        "depressed",
        "hopeless",
        "overwhelmed",
    }
)
SYMPTOM_KEYWORDS = frozenset(
    {
        "pain",
        "dizzy",
        "dizziness",
        "nausea",
        "vomit",
        "fever",
        "rash",
        "swelling",
        "headache",
        "cough",
    }
)
ADVERSE_EFFECT_KEYWORDS = frozenset(
    {
        "side effect",
        "allergic",
        "rash",
        "swelling",
        "dizzy",
        "faint",
        "vomit",
        "nausea",
        "reaction",
    }
)

IntentType = Literal["symptom", "medication_question", "schedule", "mental_health", "general"]
UrgencyType = Literal["routine", "urgent", "emergency"]


class TriageClassificationResult(BaseModel):
    """Structured classification output returned by the model."""

    intent: IntentType
    urgency: UrgencyType
    reason: str = Field(default="")


class TriageState(TypedDict, total=False):
    """State passed across triage graph nodes."""

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

    llm_result = await _classify_with_llm(router, context)
    rule_result = llm_result or _classify_with_rules(context.message)
    result = _apply_safety_override(rule_result, context.message)
    return _merge_classification(state, result)


async def generate_response(state: TriageState, router: ModelRouter) -> TriageState:
    """Node 2: generate patient-facing response."""
    context = _build_context(state)
    intent = str(state.get("intent", "general"))
    urgency = str(state.get("urgency", "routine"))
    if urgency == "emergency":
        return _merge_response(
            state, _emergency_response(context.language), escalation_required=True
        )

    response = await _generate_response_with_llm(
        router,
        _ResponseRequest(context=context, intent=intent, urgency=urgency),
    )
    if response:
        return _merge_response(state, response)

    fallback = _fallback_response(language=context.language, intent=intent, urgency=urgency)
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
        logger.warning("Triage LLM classification failed; falling back to rules: %s", exc)
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
        client = router.get_client(TaskType.CHAT_RESPONSE)
        response = await client.generate(
            prompt=prompt,
            system_instruction=CHAT_RESPONSE_SYSTEM_INSTRUCTION,
            temperature=0.35,
            max_tokens=512,
        )
    except Exception as exc:
        logger.warning("Triage LLM response generation failed; using fallback: %s", exc)
        return None

    cleaned = response.strip()
    return cleaned or None


def _classify_with_rules(message: str) -> TriageClassificationResult:
    normalized = message.lower()
    if _matches_any(normalized, EMERGENCY_KEYWORDS):
        return TriageClassificationResult(
            intent="symptom",
            urgency="emergency",
            reason="Emergency symptom keyword match",
        )

    if _matches_any(normalized, SCHEDULE_KEYWORDS):
        return TriageClassificationResult(
            intent="schedule",
            urgency="routine",
            reason="Scheduling keyword match",
        )

    if _matches_any(normalized, MEDICATION_KEYWORDS):
        return TriageClassificationResult(
            intent="medication_question",
            urgency="urgent" if _contains_adverse_effect_signal(normalized) else "routine",
            reason="Medication keyword match",
        )

    if _matches_any(normalized, MENTAL_HEALTH_KEYWORDS):
        return TriageClassificationResult(
            intent="mental_health",
            urgency="urgent",
            reason="Mental-health distress keyword match",
        )

    if _matches_any(normalized, SYMPTOM_KEYWORDS):
        return TriageClassificationResult(
            intent="symptom",
            urgency="urgent",
            reason="Symptom keyword match",
        )

    return TriageClassificationResult(
        intent="general",
        urgency="routine",
        reason="No high-signal keywords matched",
    )


def _contains_adverse_effect_signal(text: str) -> bool:
    normalized = text.lower()
    return _matches_any(normalized, ADVERSE_EFFECT_KEYWORDS)


def _emergency_response(language: str) -> str:
    if _is_spanish(language):
        return (
            "Esto podria ser una emergencia. Llama al 911 ahora o acude al servicio de "
            "urgencias mas cercano de inmediato. Si puedes, avisa tambien a tu equipo clinico."
        )

    return (
        "This may be an emergency. Please call 911 now or go to the nearest emergency "
        "department immediately. If possible, notify your care team as well."
    )


def _fallback_response(*, language: str, intent: str, urgency: str) -> str:
    if _is_spanish(language):
        if urgency == "urgent":
            return (
                "Gracias por compartir esto. Es importante que hables con tu equipo clinico hoy "
                "mismo para una evaluacion oportuna."
            )
        if intent == "medication_question":
            return (
                "Puedo ayudarte a revisar tus sintomas relacionados con medicamentos. Si notas "
                "empeoramiento, contacta a tu equipo clinico de inmediato."
            )
        return "Gracias por el mensaje. Estoy aqui para ayudarte y puedo hacer seguimiento de tus sintomas."

    if urgency == "urgent":
        return (
            "Thank you for sharing this. Please contact your care team today for timely "
            "clinical guidance."
        )
    if intent == "medication_question":
        return (
            "I can help track your medication-related concerns. If symptoms worsen, please "
            "contact your care team right away."
        )
    return "Thanks for sharing this. I am here to help and can continue tracking your symptoms."


def _is_spanish(language: str) -> bool:
    return coerce_locale(language).is_spanish


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


def _apply_safety_override(
    result: TriageClassificationResult,
    message: str,
) -> TriageClassificationResult:
    if result.intent != "medication_question":
        return result

    if not _contains_adverse_effect_signal(message):
        return result

    return TriageClassificationResult(
        intent="medication_question",
        urgency="urgent",
        reason="Potential medication side-effect pattern detected",
    )


def _matches_any(text: str, keywords: frozenset[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _route_for_intent(intent: str) -> str:
    if intent == "symptom":
        return "symptom"
    return "triage"
