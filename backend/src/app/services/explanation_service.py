"""Explanation service — generates patient-friendly document summaries."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agents.ingestion.prompts import (
    GENERATE_SUMMARY_SYSTEM,
    GENERATE_SUMMARY_USER,
    TRANSLATE_SUMMARY_SYSTEM,
    TRANSLATE_SUMMARY_USER,
)
from app.clients.model_router import TaskType, get_router
from app.models.enums import Language, coerce_locale
from app.utils.localization import get_locale_display_name, resolve_locale_resource

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = (
    "A summary is not available at this time. Please ask your care team for an explanation."
)

# Why an explanation is missing, in the patient's own locale. A patient who sees nothing
# cannot tell "this document had nothing to explain" from "the service is down", and the
# second one is the case where asking the care team is the right next step.
SUMMARY_UNAVAILABLE_MESSAGES: dict[str, dict[str, str]] = {
    "not_required": {
        Language.EN.value: (
            "There is no extracted information in this document to explain. "
            "You can still open the original document or ask your care team about it."
        ),
        Language.ES.value: (
            "Este documento no tiene información extraída que se pueda explicar. "
            "Puede abrir el documento original o preguntarle a su equipo de atención."
        ),
    },
    "pending": {
        Language.EN.value: (
            "This explanation is still being prepared. "
            "You can open the original document now and check back shortly."
        ),
        Language.ES.value: (
            "Esta explicación todavía se está preparando. "
            "Puede abrir el documento original ahora y volver a consultarla en unos minutos."
        ),
    },
    "failed": {
        Language.EN.value: (
            "An explanation is not available right now. This does not change your document "
            "or your medical record. Your care team can request it again."
        ),
        Language.ES.value: (
            "La explicación no está disponible en este momento. Esto no cambia su documento "
            "ni su expediente médico. Su equipo de atención puede solicitarla de nuevo."
        ),
    },
}


def summary_unavailable_message(status: str, language: str) -> str:
    """Explain a missing summary in the patient's locale, without inventing content."""
    resources = SUMMARY_UNAVAILABLE_MESSAGES.get(status) or SUMMARY_UNAVAILABLE_MESSAGES["failed"]
    return resolve_locale_resource(language, resources)


def normalize_patient_summary(value: str) -> str:
    """Return readable plain text when a model disregards the no-Markdown contract.

    The patient portals deliberately render summaries as text, not rich HTML. Removing
    presentation syntax here prevents raw model formatting from becoming a clinical UI
    defect while preserving the source-grounded words themselves.
    """
    without_fences = value.replace("```", "")
    without_emphasis = re.sub(r"[*_`]+", "", without_fences)
    without_heading = re.sub(r"(?m)^\s*#{1,6}\s*", "", without_emphasis)
    return "\n\n".join(
        " ".join(paragraph.split())
        for paragraph in without_heading.splitlines()
        if paragraph.strip()
    ).strip()


class ExplanationService:
    """Generates AI explanations for documents."""

    async def explain(
        self,
        document_data: dict[str, Any],
        language: str = Language.EN.value,
    ) -> str:
        """Generate a patient-friendly explanation."""
        target_language = coerce_locale(language).value
        cached_summary = str(document_data.get("ai_summary") or "").strip()

        try:
            if target_language == Language.EN.value and cached_summary:
                return normalize_patient_summary(cached_summary) or FALLBACK_MESSAGE

            english_summary = cached_summary or await self._generate_summary(document_data)
            if target_language == Language.EN.value:
                return english_summary

            return await self._translate_summary(english_summary, target_language)
        except Exception as exc:
            logger.warning(
                "Failed to generate explanation for document %s: %s", document_data.get("id"), exc
            )
            return FALLBACK_MESSAGE

    async def _generate_summary(self, document_data: dict[str, Any]) -> str:
        """Generate an English summary from document data using Flash Lite."""
        router = get_router()

        follow_up_instructions = document_data.get("follow_up_instructions") or []
        if not follow_up_instructions:
            follow_up_instructions = [
                {
                    "description": document_data.get("notes")
                    or f"Document type: {document_data.get('document_type', 'medical document')}",
                    "provider": document_data.get("source_clinic"),
                }
            ]

        prompt = GENERATE_SUMMARY_USER.format(
            medications=json.dumps(document_data.get("medications", []), default=str),
            conditions=json.dumps(document_data.get("conditions", []), default=str),
            follow_up_instructions=json.dumps(follow_up_instructions, default=str),
        )
        response = await router.generate_text(
            TaskType.PATIENT_EXPLANATION,
            prompt=prompt,
            system_instruction=GENERATE_SUMMARY_SYSTEM,
            temperature=0.4,
            max_tokens=512,
        )
        return normalize_patient_summary(response) or FALLBACK_MESSAGE

    async def translate(self, summary: str, target_language: str) -> str:
        """Translate an existing English summary, letting a provider failure surface.

        `explain` swallows failures into a generic message. A caller that reports summary
        availability needs the failure itself so it can say why nothing is shown.
        """
        return await self._translate_summary(summary, target_language)

    async def _translate_summary(self, summary: str, target_language: str) -> str:
        """Translate an English summary to the target language using Flash Lite."""
        if target_language == Language.EN.value:
            return summary

        router = get_router()
        language_name = get_locale_display_name(target_language)
        response = await router.generate_text(
            TaskType.PATIENT_EXPLANATION,
            prompt=TRANSLATE_SUMMARY_USER.format(
                summary=summary,
                target_language=language_name,
            ),
            system_instruction=TRANSLATE_SUMMARY_SYSTEM.format(target_language=language_name),
            temperature=0.2,
            max_tokens=512,
        )
        return normalize_patient_summary(response) or FALLBACK_MESSAGE
