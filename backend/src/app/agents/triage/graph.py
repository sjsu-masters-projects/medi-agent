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
from app.utils.localization import resolve_locale_resource

logger = logging.getLogger(__name__)

EMERGENCY_KEYWORDS = frozenset(
    {
        # English
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
        "heart attack",
        # Spanish
        "dolor de pecho",
        "no puedo respirar",
        "falta de aire",
        "infarto",
        "ataque cardiaco",
        "ataque al corazon",
        "ataque al corazón",
        "derrame cerebral",
        "embolia",
        "convulsion",
        "convulsión",
        "sangrado severo",
        "anafilaxia",
        "perdi el conocimiento",
        "perdí el conocimiento",
        "me desmaye",
        "me desmayé",
    }
)
MENTAL_HEALTH_EMERGENCY_KEYWORDS = frozenset(
    {
        # English
        "suicidal",
        "suicide",
        "kill myself",
        "want to die",
        "end my life",
        "harm myself",
        # Spanish
        "suicidio",
        "suicidarme",
        "matarme",
        "quitarme la vida",
        "hacerme dano",
        "hacerme daño",
        "quiero morir",
    }
)
DOCUMENT_KEYWORDS = frozenset(
    {
        "document",
        "record",
        "report",
        "result",
        "results",
        "lab",
        "labs",
        "prescription",
        "discharge",
        "informe",
        "resultado",
        "resultados",
        "laboratorio",
        "receta",
        "alta",
    }
)
DOCUMENT_CONTEXT_REFERENCES = frozenset(
    {"this", "that", "it", "these", "those", "esto", "eso", "este", "esta", "estos", "estas"}
)
SCHEDULE_KEYWORDS = frozenset(
    {"appointment", "reschedule", "book", "visit", "cita", "agendar", "reagendar", "visita"}
)
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
        "aspirin",
        "ibuprofen",
        "acetaminophen",
        "tylenol",
        "advil",
    }
)
MEDICATION_NAME_HINTS = frozenset(
    {
        "amoxicillin",
        "atorvastatin",
        "insulin",
        "lisinopril",
        "metformin",
        "omeprazole",
        "prednisone",
    }
)
MENTAL_HEALTH_KEYWORDS = frozenset(
    {
        # English
        "panic",
        "anxious",
        "anxiety",
        "depressed",
        "depression",
        "hopeless",
        "overwhelmed",
        # Spanish
        "panico",
        "pánico",
        "ansioso",
        "ansiosa",
        "ansiedad",
        "deprimido",
        "deprimida",
        "depresion",
        "depresión",
        "sin esperanza",
        "abrumado",
        "abrumada",
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

IntentType = Literal[
    "symptom",
    "medication_question",
    "schedule",
    "document_question",
    "mental_health",
    "general",
]
UrgencyType = Literal["routine", "urgent", "emergency"]

TRIAGE_COPY = {
    "default": {
        "emergency_response": (
            "This may be an emergency. Please call 911 now or go to the nearest emergency "
            "department immediately. If possible, notify your care team as well."
        ),
        "mental_health_emergency_response": (
            "If you are in immediate danger, call 911 now. If you are thinking about hurting "
            "yourself or feeling unsafe, call or text 988 (Suicide and Crisis Lifeline) right "
            "away — they are available 24/7. You are not alone, and help is available."
        ),
        "fallback_general": (
            "Thanks for sharing this. I am here to help and can continue tracking your symptoms."
        ),
        "fallback_medication_question": (
            "I can help track your medication-related concerns. If symptoms worsen, please "
            "contact your care team right away."
        ),
        "fallback_document_question": (
            "I can help explain the attached record in plain language. I will stick to what is "
            "available in your record and suggest questions for your care team when details are unclear."
        ),
        "fallback_schedule": (
            "I can help you prepare scheduling questions. For appointment changes, please confirm "
            "directly with your clinic."
        ),
        "fallback_mental_health": (
            "I am sorry you are feeling this way. If you might hurt yourself or feel unsafe, call "
            "988 or emergency services now. Otherwise, contact your care team today for support."
        ),
        "fallback_urgent": (
            "Thank you for sharing this. Please contact your care team today for timely "
            "clinical guidance."
        ),
        "fallback_non_clinical": (
            "I am focused on health support. For medication, symptoms, records, or appointments, "
            "I can give more specific help."
        ),
    },
    Language.EN.value: {
        "emergency_response": (
            "This may be an emergency. Please call 911 now or go to the nearest emergency "
            "department immediately. If possible, notify your care team as well."
        ),
        "mental_health_emergency_response": (
            "If you are in immediate danger, call 911 now. If you are thinking about hurting "
            "yourself or feeling unsafe, call or text 988 (Suicide and Crisis Lifeline) right "
            "away — they are available 24/7. You are not alone, and help is available."
        ),
        "fallback_general": (
            "Thanks for sharing this. I am here to help and can continue tracking your symptoms."
        ),
        "fallback_medication_question": (
            "I can help track your medication-related concerns. If symptoms worsen, please "
            "contact your care team right away."
        ),
        "fallback_document_question": (
            "I can help explain the attached record in plain language. I will stick to what is "
            "available in your record and suggest questions for your care team when details are unclear."
        ),
        "fallback_schedule": (
            "I can help you prepare scheduling questions. For appointment changes, please confirm "
            "directly with your clinic."
        ),
        "fallback_mental_health": (
            "I am sorry you are feeling this way. If you might hurt yourself or feel unsafe, call "
            "988 or emergency services now. Otherwise, contact your care team today for support."
        ),
        "fallback_urgent": (
            "Thank you for sharing this. Please contact your care team today for timely "
            "clinical guidance."
        ),
        "fallback_non_clinical": (
            "I am focused on health support. For medication, symptoms, records, or appointments, "
            "I can give more specific help."
        ),
    },
    Language.ES.value: {
        "emergency_response": (
            "Esto podría ser una emergencia. Llama al 911 ahora o acude al servicio de "
            "urgencias más cercano de inmediato. Si puedes, avisa también a tu equipo clínico."
        ),
        "mental_health_emergency_response": (
            "Si estás en peligro inmediato, llama al 911 ahora. Si tienes pensamientos de "
            "hacerte daño o no te sientes a salvo, llama o envía un mensaje al 988 (Línea de "
            "Prevención del Suicidio y Crisis) de inmediato — están disponibles 24/7. No estás "
            "solo y hay ayuda disponible."
        ),
        "fallback_general": (
            "Gracias por el mensaje. Estoy aquí para ayudarte y puedo seguir dando seguimiento a tus síntomas."
        ),
        "fallback_medication_question": (
            "Puedo ayudarte a revisar tus síntomas relacionados con medicamentos. Si notas "
            "empeoramiento, contacta a tu equipo clínico de inmediato."
        ),
        "fallback_document_question": (
            "Puedo ayudarte a explicar el documento adjunto en lenguaje sencillo. Me basaré en "
            "la información disponible y sugeriré preguntas para tu equipo clínico si algo no queda claro."
        ),
        "fallback_schedule": (
            "Puedo ayudarte a preparar preguntas sobre citas. Para cambiar una cita, confirma "
            "directamente con tu clínica."
        ),
        "fallback_mental_health": (
            "Siento que te estés sintiendo así. Si podrías hacerte daño o no te sientes a salvo, "
            "llama al 988 o a emergencias ahora. Si no, contacta a tu equipo clínico hoy para recibir apoyo."
        ),
        "fallback_urgent": (
            "Gracias por compartir esto. Es importante que hables con tu equipo clínico hoy "
            "mismo para una evaluación oportuna."
        ),
        "fallback_non_clinical": (
            "Estoy enfocada en apoyo de salud. Si tienes preguntas sobre medicamentos, síntomas, "
            "documentos o citas, puedo ayudarte mejor."
        ),
    },
}


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
    rule_result = llm_result or _classify_with_rules(context)
    result = _apply_safety_override(rule_result, context.message)
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


def _classify_with_rules(context: _MessageContext) -> TriageClassificationResult:
    normalized = context.message.lower()
    if _matches_any(normalized, MENTAL_HEALTH_EMERGENCY_KEYWORDS):
        return TriageClassificationResult(
            intent="mental_health",
            urgency="emergency",
            reason="Mental-health emergency keyword match",
        )

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

    if _matches_any(normalized, MEDICATION_NAME_HINTS):
        return TriageClassificationResult(
            intent="medication_question",
            urgency="routine",
            reason="Medication name hint match",
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

    if _has_document_signal(normalized, has_document_context=bool(context.document_context)):
        return TriageClassificationResult(
            intent="document_question",
            urgency="routine",
            reason="Document context or document keyword match",
        )

    return TriageClassificationResult(
        intent="general",
        urgency="routine",
        reason="No high-signal keywords matched",
    )


def _contains_adverse_effect_signal(text: str) -> bool:
    normalized = text.lower()
    return _matches_any(normalized, ADVERSE_EFFECT_KEYWORDS)


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
    if result.urgency == "emergency":
        return result

    if not _contains_adverse_effect_signal(message):
        return result

    if result.intent == "medication_question":
        return TriageClassificationResult(
            intent="medication_question",
            urgency="urgent",
            reason="Potential medication side-effect pattern detected",
        )

    if result.urgency == "routine":
        return TriageClassificationResult(
            intent=result.intent,
            urgency="urgent",
            reason=f"{result.reason} + adverse-effect signal forced urgent",
        )

    return result


def _matches_any(text: str, keywords: frozenset[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _has_document_signal(text: str, *, has_document_context: bool) -> bool:
    if _matches_any(text, DOCUMENT_KEYWORDS):
        return True
    if not has_document_context or not _matches_any(text, DOCUMENT_CONTEXT_REFERENCES):
        return False
    document_verbs = ("explain", "mean", "understand", "review", "explica", "significa", "entender")
    return any(verb in text for verb in document_verbs)


def _route_for_intent(intent: str) -> str:
    if intent == "symptom":
        return "symptom"
    return "triage"
