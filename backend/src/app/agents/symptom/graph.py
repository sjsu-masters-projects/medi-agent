"""LangGraph workflow for Symptom Analysis Agent."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.agents.symptom.prompts import (
    SYMPTOM_EXTRACTION_SYSTEM_INSTRUCTION,
    SYMPTOM_RESPONSE_SYSTEM_INSTRUCTION,
    build_symptom_extraction_prompt,
    build_symptom_response_prompt,
)
from app.clients.model_router import ModelRouter, TaskType
from app.models.enums import Language, coerce_locale
from app.utils.localization import resolve_locale_resource

logger = logging.getLogger(__name__)

SYMPTOM_COPY = {
    "default": {
        "fallback_prefix": "Thanks for sharing this about {symptom}. I logged it for follow-up (estimated severity {severity}/10).",
        "fallback_question_start": "When did this symptom start?",
        "fallback_severe_suffix": " Please contact your care team today for urgent guidance.",
        "rule_assessment": "Patient reported symptom captured for clinician review.",
    },
    Language.EN.value: {
        "fallback_prefix": "Thanks for sharing this about {symptom}. I logged it for follow-up (estimated severity {severity}/10).",
        "fallback_question_start": "When did this symptom start?",
        "fallback_severe_suffix": " Please contact your care team today for urgent guidance.",
        "rule_assessment": "Patient reported symptom captured for clinician review.",
    },
    Language.ES.value: {
        "fallback_prefix": "Gracias por compartir lo de {symptom}. Lo registré para seguimiento (severidad aproximada {severity}/10).",
        "fallback_question_start": "¿Cuándo empezó este síntoma?",
        "fallback_severe_suffix": " Es importante contactar a tu equipo clínico hoy mismo.",
        "rule_assessment": "Síntoma reportado por el paciente y registrado para revisión clínica.",
    },
}


class SymptomExtractionResult(BaseModel):
    symptom: str = Field(..., min_length=1)
    severity: int = Field(..., ge=1, le=10)
    onset: str | None = None
    duration: str | None = None
    body_area: str | None = None
    related_medication_name: str | None = None
    needs_follow_up: bool = False
    follow_up_question: str | None = None
    flagged_for_adr: bool = False
    ai_assessment: str = Field(default="Patient reported symptom requires monitoring.")


class SymptomState(TypedDict, total=False):
    message: str
    language: str
    history: list[dict[str, Any]]
    patient_context: dict[str, Any]

    symptom_report: dict[str, Any]
    follow_up_question: str | None
    flagged_for_adr: bool
    assistant_response: str
    error: str | None


async def extract_symptom(state: SymptomState, router: ModelRouter) -> SymptomState:
    message = str(state.get("message", "")).strip()
    language = coerce_locale(state.get("language", Language.EN.value)).value
    history = state.get("history", [])
    patient_context = state.get("patient_context", {})

    if not message:
        return {
            **state,
            "error": "Empty symptom message",
        }

    prompt = build_symptom_extraction_prompt(
        language=language,
        message=message,
        history=history,
        patient_context=patient_context,
    )

    try:
        client = router.get_client(TaskType.TRIAGE_CLASSIFICATION)
        extraction = await client.generate_structured(
            prompt=prompt,
            response_model=SymptomExtractionResult,
            system_instruction=SYMPTOM_EXTRACTION_SYSTEM_INSTRUCTION,
            temperature=0.1,
        )
    except Exception as exc:
        logger.warning("Symptom extraction LLM call failed; using fallback: %s", exc)
        extraction = _extract_with_rules(message, language)

    return {
        **state,
        "symptom_report": extraction.model_dump(),
        "follow_up_question": extraction.follow_up_question,
        "flagged_for_adr": extraction.flagged_for_adr,
        "error": None,
    }


async def generate_response(state: SymptomState, router: ModelRouter) -> SymptomState:
    if state.get("error"):
        return state

    language = coerce_locale(state.get("language", Language.EN.value)).value
    report = state.get("symptom_report", {})
    symptom = str(report.get("symptom", "symptom")).strip() or "symptom"
    severity = int(report.get("severity") or 5)
    ai_assessment = str(report.get("ai_assessment") or "Please monitor closely.")
    follow_up = report.get("follow_up_question")

    prompt = build_symptom_response_prompt(
        language=language,
        symptom=symptom,
        severity=severity,
        ai_assessment=ai_assessment,
        follow_up_question=str(follow_up) if follow_up else None,
    )

    try:
        client = router.get_client(TaskType.CHAT_RESPONSE)
        assistant_response = await client.generate(
            prompt=prompt,
            system_instruction=SYMPTOM_RESPONSE_SYSTEM_INSTRUCTION,
            temperature=0.3,
            max_tokens=384,
        )
    except Exception as exc:
        logger.warning("Symptom response LLM call failed; using fallback: %s", exc)
        assistant_response = _fallback_response(language=language, report=report)

    cleaned = assistant_response.strip() or _fallback_response(language=language, report=report)
    return {
        **state,
        "assistant_response": cleaned,
        "error": None,
    }


def build_symptom_graph(router: ModelRouter) -> Any:
    async def _extract(state: SymptomState) -> SymptomState:
        return await extract_symptom(state, router)

    async def _respond(state: SymptomState) -> SymptomState:
        return await generate_response(state, router)

    workflow: StateGraph[SymptomState] = StateGraph(SymptomState)
    workflow.add_node("extract_symptom", _extract)
    workflow.add_node("generate_response", _respond)

    workflow.add_edge(START, "extract_symptom")
    workflow.add_edge("extract_symptom", "generate_response")
    workflow.add_edge("generate_response", END)

    return workflow.compile()


def _extract_with_rules(message: str, language: str) -> SymptomExtractionResult:
    normalized = message.lower()
    symptom = _guess_symptom(normalized)
    severity = _guess_severity(normalized)
    copy = resolve_locale_resource(language, SYMPTOM_COPY)
    flagged_for_adr = "after" in normalized and (
        "med" in normalized or "medicine" in normalized or "medication" in normalized
    )
    follow_up_question = None
    if "since" not in normalized and "for " not in normalized:
        follow_up_question = copy["fallback_question_start"]

    assessment = copy["rule_assessment"]
    return SymptomExtractionResult(
        symptom=symptom,
        severity=severity,
        onset=None,
        duration=None,
        body_area=None,
        related_medication_name=None,
        needs_follow_up=bool(follow_up_question),
        follow_up_question=follow_up_question,
        flagged_for_adr=flagged_for_adr,
        ai_assessment=assessment,
    )


def _guess_symptom(normalized: str) -> str:
    if "pain" in normalized:
        return "pain"
    if "dizzy" in normalized or "dizziness" in normalized:
        return "dizziness"
    if "nausea" in normalized or "vomit" in normalized:
        return "nausea"
    if "fever" in normalized:
        return "fever"
    return "reported symptom"


def _guess_severity(normalized: str) -> int:
    if any(keyword in normalized for keyword in {"severe", "worst", "cannot", "can't"}):
        return 8
    if any(keyword in normalized for keyword in {"bad", "worse", "strong"}):
        return 6
    return 4


def _fallback_response(*, language: str, report: dict[str, Any]) -> str:
    symptom = str(report.get("symptom") or "your symptom")
    severity = int(report.get("severity") or 5)
    question = str(report.get("follow_up_question") or "").strip()
    localized_copy = resolve_locale_resource(language, SYMPTOM_COPY)
    base = localized_copy["fallback_prefix"].format(symptom=symptom, severity=severity)
    if severity >= 8:
        base += localized_copy["fallback_severe_suffix"]
    if question:
        base += f" {question}"
    return base
