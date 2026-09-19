"""Turn a patient's description of a symptom into a structured report and a reply.

Two steps, both plain awaits: extract the fields, then write the message the patient
reads. It was a two-node state graph, which is the same two awaits with a framework
holding them.

**Nothing here guesses a symptom.** The previous implementation, when the model was
unavailable, inferred the symptom from substrings and invented a severity: "worst
headache pain today" became severity 8, and "tengo dolor fuerte en el pecho" — severe
chest pain — became `symptom="reported symptom"`, severity 4, unflagged. Those values
were not just shown to the patient, they were written to `symptom_reports`, counted
toward the adverse-event signal, and read later by a clinician as the patient's own
record. A guess that persists is worse than one that does not, so a failed extraction now
writes no report at all and says so.

The response step is different and keeps its fallback: by then the fields have been read
by a model from the patient's actual words, so a locally composed sentence about *those*
values states nothing that was not extracted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.adk.registry import Transport, Workload, route_for
from app.clients.gemini import GeminiClient
from app.core.llm_failures import categorize_llm_failure
from app.core.observability import record_chat_fallback
from app.followup.followup_copy import FOLLOWUP_COPY
from app.followup.models import SymptomExtractionResult
from app.followup.prompts import (
    SYMPTOM_EXTRACTION_SYSTEM_INSTRUCTION,
    SYMPTOM_RESPONSE_SYSTEM_INSTRUCTION,
    build_symptom_extraction_prompt,
    build_symptom_response_prompt,
)
from app.models.enums import Language, coerce_locale
from app.utils.localization import resolve_locale_resource

logger = logging.getLogger(__name__)

SEVERE_THRESHOLD = 8
"""At or above this the reply adds same-day guidance, matching the extraction scale."""


@dataclass(frozen=True)
class SymptomAnalysis:
    """What the caller needs to persist a report, answer the patient, and escalate.

    `symptom_report` is `None` when nothing was extracted. That is deliberately not an
    empty dict: the caller writes a row whenever this is truthy, and an empty report is
    indistinguishable from a real one at the point of writing.
    """

    status: str
    response_text: str
    symptom_report: dict[str, Any] | None = None
    follow_up_question: str | None = None
    flagged_for_adr: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def _extraction_client() -> GeminiClient:
    """Build the client the registry routes symptom extraction to.

    The transport is checked rather than assumed. Routing this workload to a model reached
    another way would otherwise send a bare model id to the wrong SDK and fail at call
    time, which reads like an outage instead of a configuration mistake.
    """
    route = route_for(Workload.ADR_EXTRACTION)
    if route.primary.transport is not Transport.VERTEX_GENAI:
        # Formatted without `.value` on purpose. `Transport` is a `StrEnum`, so this
        # renders identically for a real member — and this is the error path, which runs
        # when something is already wrong. It should not be able to raise an error of its
        # own on the way to reporting one.
        raise ValueError(
            f"Symptom extraction is routed to {route.primary.key}, which is reached over "
            f"{route.primary.transport}. This path builds a Gen AI client only."
        )
    return GeminiClient(
        model=route.primary.model_id,
        use_vertex_ai=True,
        timeout=int(route.budget_seconds or 30),
    )


async def _extract(
    *,
    language: str,
    message: str,
    history: list[dict[str, Any]],
    patient_context: dict[str, Any],
) -> SymptomExtractionResult | None:
    """Return the extracted fields, or None. None means nothing is recorded."""
    route = route_for(Workload.ADR_EXTRACTION)
    if not route.is_enabled():
        logger.info("Symptom extraction is disabled; no report will be written")
        return None

    prompt = build_symptom_extraction_prompt(
        language=language,
        message=message,
        history=history,
        patient_context=patient_context,
    )

    try:
        return await _extraction_client().generate_structured(
            prompt=prompt,
            response_model=SymptomExtractionResult,
            system_instruction=SYMPTOM_EXTRACTION_SYSTEM_INSTRUCTION,
            temperature=0.1,
            max_tokens=route.max_output_tokens,
            thinking_level=route.thinking_level,
        )
    except Exception as exc:
        reason = categorize_llm_failure(exc)
        record_chat_fallback(layer="symptom_extraction", reason=reason)
        logger.warning(
            "Symptom extraction failed; no report will be written: %s",
            exc,
            extra={
                "chat_fallback_layer": "symptom_extraction",
                "chat_fallback_reason": reason,
            },
        )
        return None


async def _respond(*, language: str, extraction: SymptomExtractionResult) -> str:
    """Write the patient's reply, falling back to a sentence about the extracted fields."""
    prompt = build_symptom_response_prompt(
        language=language,
        symptom=extraction.symptom,
        severity=extraction.severity,
        ai_assessment=extraction.ai_assessment,
        follow_up_question=extraction.follow_up_question,
    )

    try:
        answer = await _extraction_client().generate(
            prompt=prompt,
            system_instruction=SYMPTOM_RESPONSE_SYSTEM_INSTRUCTION,
            temperature=0.3,
            max_tokens=384,
        )
        cleaned = answer.strip()
        if cleaned:
            return cleaned
    except Exception as exc:
        reason = categorize_llm_failure(exc)
        record_chat_fallback(layer="symptom_response", reason=reason)
        logger.warning(
            "Symptom response generation failed; composing from the extracted fields: %s",
            exc,
            extra={
                "chat_fallback_layer": "symptom_response",
                "chat_fallback_reason": reason,
            },
        )

    return _compose_reply(language=language, extraction=extraction)


def _compose_reply(*, language: str, extraction: SymptomExtractionResult) -> str:
    """State back only what was extracted — never anything inferred here."""
    localized = resolve_locale_resource(language, FOLLOWUP_COPY)
    reply = localized["logged_prefix"].format(
        symptom=extraction.symptom, severity=extraction.severity
    )
    if extraction.severity >= SEVERE_THRESHOLD:
        reply += localized["severe_suffix"]
    question = (extraction.follow_up_question or "").strip()
    if question:
        reply += f" {question}"
    return reply


async def analyse_symptom(
    *,
    message: str,
    language: Language | str = Language.EN,
    history: list[dict[str, Any]] | None = None,
    patient_context: dict[str, Any] | None = None,
) -> SymptomAnalysis:
    """Extract a symptom report and write the patient's reply."""
    locale = coerce_locale(language).value
    text = (message or "").strip()

    if not text:
        return SymptomAnalysis(
            status="degraded",
            response_text="",
            metadata={"reason": "empty_message"},
        )

    extraction = await _extract(
        language=locale,
        message=text,
        history=history or [],
        patient_context=patient_context or {},
    )

    if extraction is None:
        # No report, and the patient is told. The caller writes a row whenever
        # `symptom_report` is set, so leaving it unset is what keeps an unread symptom
        # out of the record.
        return SymptomAnalysis(
            status="degraded",
            response_text=resolve_locale_resource(locale, FOLLOWUP_COPY)["report_unavailable"],
            metadata={"reason": "extraction_unavailable"},
        )

    return SymptomAnalysis(
        status="success",
        response_text=await _respond(language=locale, extraction=extraction),
        symptom_report=extraction.model_dump(),
        follow_up_question=extraction.follow_up_question,
        flagged_for_adr=extraction.flagged_for_adr,
    )


__all__ = ["SEVERE_THRESHOLD", "SymptomAnalysis", "analyse_symptom"]
