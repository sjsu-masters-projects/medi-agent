"""Explanation service — generates patient-friendly document summaries."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.ingestion.prompts import (
    GENERATE_SUMMARY_SYSTEM,
    GENERATE_SUMMARY_USER,
    TRANSLATE_SUMMARY_SYSTEM,
    TRANSLATE_SUMMARY_USER,
)
from app.clients.model_router import TaskType, get_router

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = (
    "A summary is not available at this time. Please ask your care team for an explanation."
)
LANGUAGE_NAMES = {"en": "English", "es": "Spanish"}


class ExplanationService:
    """Generates AI explanations for documents."""

    async def explain(
        self,
        document_data: dict[str, Any],
        language: str = "en",
    ) -> str:
        """Generate a patient-friendly explanation."""
        target_language = language if language in LANGUAGE_NAMES else "en"
        cached_summary = str(document_data.get("ai_summary") or "").strip()

        try:
            if target_language == "en" and cached_summary:
                return cached_summary

            english_summary = cached_summary or await self._generate_summary(document_data)
            if target_language == "en":
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
        client = router.get_client_with_fallback(TaskType.PATIENT_EXPLANATION)

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
        response = await client.generate(
            prompt=prompt,
            system_instruction=GENERATE_SUMMARY_SYSTEM,
            temperature=0.4,
            max_tokens=512,
        )
        return response.strip() or FALLBACK_MESSAGE

    async def _translate_summary(self, summary: str, target_language: str) -> str:
        """Translate an English summary to the target language using Flash Lite."""
        if target_language == "en":
            return summary

        router = get_router()
        client = router.get_client_with_fallback(TaskType.PATIENT_EXPLANATION)
        language_name = LANGUAGE_NAMES.get(target_language, target_language)
        response = await client.generate(
            prompt=TRANSLATE_SUMMARY_USER.format(
                summary=summary,
                target_language=language_name,
            ),
            system_instruction=TRANSLATE_SUMMARY_SYSTEM.format(target_language=language_name),
            temperature=0.2,
            max_tokens=512,
        )
        return response.strip() or FALLBACK_MESSAGE
