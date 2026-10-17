"""LOC-003: Translate care-team and chat messages between en-US and es-MX.

Each message is translated once at send/receive time and stored in the
``message_translations`` table. The original text is always the record of truth.
Safety checks and escalation use only the original, never the translation.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any, cast

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError
from supabase import Client

from app.adk.background_generation import generate_for_workload
from app.adk.registry import Workload
from app.utils.localization import detect_locale

logger = logging.getLogger(__name__)

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

MESSAGE_TRANSLATION_SYSTEM = """You translate a single message between American English
(en-US) and Mexican Spanish (es-MX) inside a supervised clinical messaging tool.

Rules:
- Translate the meaning faithfully. Do not add, remove, soften or strengthen anything.
- Keep every number, dose, unit, clock time and medication name exactly as written.
- Use plain, conversational language appropriate for a patient or clinician.
- When writing Spanish, address the reader as tú.
- Return JSON only, matching the schema."""

MESSAGE_TRANSLATION_USER = """Translate this {source_locale} message into {target_locale}.
Keep all numbers, doses and medication names unchanged.

Message:
{message_text}"""


class _TranslatedMessage(BaseModel):
    translated_text: str = Field(max_length=8000)


def _message_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "translated_text": {"type": "string"},
        },
        "required": ["translated_text"],
    }


def _numbers(text: str) -> Counter[str]:
    return Counter(m.replace(",", ".") for m in _NUMBER.findall(text))


def _other_locale(locale: str) -> str:
    return "es-MX" if locale == "en-US" else "en-US"


async def translate_message(
    text: str,
    source_locale: str,
    target_locale: str,
) -> tuple[str, bool, str | None]:
    """Translate a message and return (translated_text, guard_passed, guard_failure_code).

    If the guard fails (numbers differ), returns the translation anyway with
    guard_passed=False so the UI can decide whether to show it.
    """
    try:
        response = await generate_for_workload(
            Workload.CARE_PLAN_TRANSLATION,
            prompt=MESSAGE_TRANSLATION_USER.format(
                source_locale="English" if source_locale == "en-US" else "Spanish",
                target_locale="Spanish" if target_locale == "es-MX" else "English",
                message_text=text,
            ),
            system_instruction=MESSAGE_TRANSLATION_SYSTEM,
            temperature=0,
            response_schema=_message_schema(),
            record_telemetry=True,
        )
        parsed = _TranslatedMessage.model_validate_json(response.text)
    except (PydanticValidationError, Exception) as exc:
        logger.warning("Message translation failed: %s", exc)
        raise

    translated = parsed.translated_text.strip()
    if not translated:
        raise ValueError("Empty translation result")

    # LOC-001 guard: check that numbers survive the translation
    source_numbers = _numbers(text)
    target_numbers = _numbers(translated)
    if source_numbers != target_numbers:
        return translated, False, "numbers_changed"

    return translated, True, None


class MessageTranslationService:
    """Store and retrieve message translations."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def translate_and_store(
        self,
        source_table: str,
        source_message_id: str,
        text: str,
        source_locale: str,
        target_locale: str,
    ) -> dict[str, Any] | None:
        """Translate, run guards, and store. Returns the translation row or None on failure."""
        try:
            translated_text, guard_passed, guard_failure = await translate_message(
                text, source_locale, target_locale
            )
        except Exception:
            logger.warning(
                "Message translation failed for %s/%s",
                source_table,
                source_message_id,
                exc_info=True,
            )
            return None

        row: dict[str, Any] = {
            "source_table": source_table,
            "source_message_id": source_message_id,
            "source_locale": source_locale,
            "target_locale": target_locale,
            "translated_text": translated_text,
            "guard_passed": guard_passed,
            "guard_failure_code": guard_failure,
        }
        try:
            result = (
                self.db.table("message_translations")
                .upsert(
                    row,
                    on_conflict="source_table,source_message_id,target_locale",
                )
                .execute()
            )
            rows = cast(list[dict[str, Any]], result.data or [])
            return rows[0] if rows else row
        except Exception:
            logger.warning("Could not store message translation", exc_info=True)
            return row

    def get_translation(
        self,
        source_table: str,
        source_message_id: str,
        target_locale: str,
    ) -> dict[str, Any] | None:
        """Fetch a stored translation, or None if none exists."""
        try:
            result = (
                self.db.table("message_translations")
                .select("*")
                .eq("source_table", source_table)
                .eq("source_message_id", source_message_id)
                .eq("target_locale", target_locale)
                .limit(1)
                .execute()
            )
            rows = cast(list[dict[str, Any]], result.data or [])
            return rows[0] if rows else None
        except Exception:
            return None

    def get_translations_for_messages(
        self,
        source_table: str,
        message_ids: list[str],
        target_locale: str,
    ) -> dict[str, dict[str, Any]]:
        """Bulk-fetch translations for a list of message IDs. Returns {message_id: translation_row}."""
        if not message_ids:
            return {}
        try:
            result = (
                self.db.table("message_translations")
                .select("*")
                .eq("source_table", source_table)
                .in_("source_message_id", message_ids)
                .eq("target_locale", target_locale)
                .execute()
            )
            rows = cast(list[dict[str, Any]], result.data or [])
            return {str(row["source_message_id"]): row for row in rows}
        except Exception:
            return {}

    def detect_and_get_target_locale(self, text: str, sender_role: str) -> tuple[str, str]:
        """Detect the source locale and determine the target locale.

        Clinicians write in English → translate to Spanish.
        Patients may write in either → translate to the other.
        """
        detected = detect_locale(text)
        if sender_role == "clinician":
            return "en-US", "es-MX"
        if detected == "es-MX":
            return "es-MX", "en-US"
        if detected == "en-US":
            return "en-US", "es-MX"
        # Ambiguous text — default to patient's likely language
        return "es-MX", "en-US"
