"""Authenticated human messages: all authorization and writes share a DB transaction."""

import asyncio
import logging
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from app.core.exceptions import AuthorizationError, ExternalServiceError, ValidationError
from app.models.auth import CurrentUser
from app.models.care_conversation import (
    ConversationCreate,
    ConversationReadMarker,
    ConversationSend,
)
from app.models.enums import Language, coerce_locale
from app.services.clinic_membership_service import ClinicMembershipService

logger = logging.getLogger(__name__)

# A read may translate at most this many messages that have no stored translation; the rest
# stay in the original language until a later read. (Follow-up: move this to a background job.)
MAX_ON_THE_FLY_TRANSLATIONS = 10
_SOURCE_TABLE = "care_team_conversation_messages"


class CareConversationService:
    def __init__(self, db: Client, actor: CurrentUser) -> None:
        self.db = db
        self.actor = actor

    async def recipients(self, clinic_id: UUID | None = None) -> list[dict[str, Any]]:
        items = cast(list[dict[str, Any]], await self._call("recipients"))
        return await self._clinician_view(items, "id", clinic_id)

    async def list_conversations(self, clinic_id: UUID | None = None) -> list[dict[str, Any]]:
        items = cast(list[dict[str, Any]], await self._call("list"))
        return await self._clinician_view(items, "patient_id", clinic_id)

    async def _clinician_view(
        self, items: list[dict[str, Any]], patient_key: str, clinic_id: UUID | None
    ) -> list[dict[str, Any]]:
        """Tag a clinician's items with the link's clinic and keep one clinic's, if asked.

        Patients have no clinic filter. Each thread already belongs to one link, so its own
        clinic is the link's clinic; a clinic the clinician does not belong to is empty.
        """
        if self.actor.role != "clinician":
            return items
        scope = await ClinicMembershipService(self).link_scope(self.actor.id, clinic_id)
        kept = [item for item in items if str(item.get(patient_key)) in scope]
        for item in kept:
            tag = scope.tag(item.get(patient_key))
            item["clinic_id"] = tag["clinic_id"]
        return kept

    async def open_conversation(self, data: ConversationCreate) -> dict[str, Any]:
        return cast(dict[str, Any], await self._call("open", data.model_dump(mode="json")))

    async def messages(self, conversation: UUID, options: dict[str, Any]) -> dict[str, Any]:
        result = cast(
            dict[str, Any],
            await self._call(
                "messages",
                {
                    "conversation_id": str(conversation),
                    **options,
                },
            ),
        )
        # LOC-003: Attach stored translations to messages.
        await self._attach_translations(result)
        return result

    async def send(self, conversation: UUID, data: ConversationSend) -> dict[str, Any]:
        result = cast(
            dict[str, Any],
            await self._call(
                "send",
                {
                    "conversation_id": str(conversation),
                    **data.model_dump(mode="json"),
                },
            ),
        )
        # LOC-003: Translate the sent message asynchronously and store the translation.
        await self._translate_message(result)
        return result

    async def mark_read(self, conversation: UUID, data: ConversationReadMarker) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._call(
                "read",
                {
                    "conversation_id": str(conversation),
                    **data.model_dump(mode="json"),
                },
            ),
        )

    async def _call(self, action: str, payload: dict[str, Any] | None = None) -> Any:
        if self.actor.role not in {"patient", "clinician"}:
            raise self._denial()
        try:
            result = await asyncio.to_thread(
                self.db.rpc(
                    "care_conversation_operation",
                    {
                        "p_actor_id": str(self.actor.id),
                        "p_actor_role": self.actor.role,
                        "p_action": action,
                        "p_payload": payload or {},
                    },
                ).execute
            )
        except APIError as exc:
            if exc.code == "42501":
                raise self._denial() from None
            if exc.code == "22023":
                raise ValidationError("Invalid conversation request") from None
            if exc.code == "23505":
                raise ValidationError(
                    "Message retry does not match the original request",
                    code="MESSAGE_IDEMPOTENCY_MISMATCH",
                ) from None
            # Never log PostgREST details: constraints can echo private message text.
            raise ExternalServiceError("Supabase", "Conversation operation failed") from None
        if not isinstance(result.data, dict | list):
            raise ExternalServiceError("Supabase", "Conversation operation failed")
        return result.data

    def _denial(self) -> AuthorizationError:
        return AuthorizationError(
            "Conversation unavailable",
            actor_id=str(self.actor.id),
            actor_role=self.actor.role,
            target_type="care_conversation",
        )

    async def _patient_locale(self, conversation_id: str | None) -> str:
        """The patient's own language (en-US or es-MX); English when it cannot be read."""

        def read() -> str:
            patient_id = str(self.actor.id)
            if self.actor.role != "patient":
                rows = cast(
                    list[dict[str, Any]],
                    self.db.table("care_conversations")
                    .select("patient_id")
                    .eq("id", str(conversation_id))
                    .limit(1)
                    .execute()
                    .data
                    or [],
                )
                if not rows:
                    return Language.EN.value
                patient_id = str(rows[0]["patient_id"])
            rows = cast(
                list[dict[str, Any]],
                self.db.table("patients")
                .select("preferred_language")
                .eq("id", patient_id)
                .limit(1)
                .execute()
                .data
                or [],
            )
            return coerce_locale(rows[0].get("preferred_language") if rows else None).value

        try:
            return await asyncio.to_thread(read)
        except Exception:
            logger.warning("Could not read the patient's language", exc_info=False)
            return Language.EN.value

    async def _medication_names(self, conversation_id: str | None) -> list[str]:
        """The patient's active medication names, which a translation must not change."""

        def read() -> list[str]:
            patient_id = str(self.actor.id)
            if self.actor.role != "patient":
                rows = cast(
                    list[dict[str, Any]],
                    self.db.table("care_conversations")
                    .select("patient_id")
                    .eq("id", str(conversation_id))
                    .limit(1)
                    .execute()
                    .data
                    or [],
                )
                if not rows:
                    return []
                patient_id = str(rows[0]["patient_id"])
            meds = cast(
                list[dict[str, Any]],
                self.db.table("medications")
                .select("name")
                .eq("patient_id", patient_id)
                .eq("is_active", True)
                .execute()
                .data
                or [],
            )
            return [str(row["name"]) for row in meds if row.get("name")]

        try:
            return await asyncio.to_thread(read)
        except Exception:
            return []

    async def _translate_message(self, message: dict[str, Any]) -> None:
        """LOC-003: Translate a newly sent message for its reader and store the translation.

        The send waits for this (a follow-up is to move it to a background job); a failure
        never fails the send. Nothing is translated when the reader's language is the
        message's own language.
        """
        try:
            from app.services.message_translation import MessageTranslationService

            body = str(message.get("body") or "").strip()
            message_id = str(message.get("id") or "")
            sender_role = str(message.get("sender_role") or self.actor.role)
            conversation_id = str(message.get("conversation_id") or "") or None
            if not body or not message_id:
                return
            service = MessageTranslationService(self.db)
            patient_locale = await self._patient_locale(conversation_id)
            source_locale, target_locale = service.detect_and_get_target_locale(
                body, sender_role, patient_locale
            )
            if source_locale == target_locale:
                return
            result = await service.translate_and_store(
                source_table=_SOURCE_TABLE,
                source_message_id=message_id,
                text=body,
                source_locale=source_locale,
                target_locale=target_locale,
                protected_terms=await self._medication_names(conversation_id),
            )
            if result:
                message["translation"] = result.get("translated_text")
                message["translation_locale"] = target_locale
                message["translation_guard_passed"] = result.get("guard_passed", True)
        except Exception:
            # Translation is optional; never fail the send. Log the failure, never the text.
            logger.warning("Message translation after send failed", exc_info=False)

    async def _attach_translations(self, page: dict[str, Any]) -> None:
        """LOC-003: Attach stored translations to every message; translate new ones on the fly.

        The viewer's language is the target: a clinician reads English, a patient reads their
        own ``preferred_language``. Stored rows are attached for the whole page; only NEW model
        calls are capped. A stored failure marker is never shown and is retried only after a
        while.
        """
        try:
            from app.services.message_translation import (
                MessageTranslationService,
                failure_marker_is_recent,
                is_failure_marker,
            )
            from app.utils.localization import detect_locale

            items = page.get("items") or []
            if not items:
                return
            conversation_id = next(
                (str(m["conversation_id"]) for m in items if m.get("conversation_id")), None
            )
            patient_locale = await self._patient_locale(conversation_id)
            target_locale = Language.EN.value if self.actor.role == "clinician" else patient_locale
            message_ids = [str(msg["id"]) for msg in items if msg.get("id")]
            if not message_ids:
                return
            service = MessageTranslationService(self.db)
            translations = await service.get_translations_for_messages(
                source_table=_SOURCE_TABLE,
                message_ids=message_ids,
                target_locale=target_locale,
            )
            protected: list[str] | None = None
            on_the_fly = 0
            for msg in items:
                msg_id = str(msg.get("id") or "")
                tr = translations.get(msg_id)
                if tr and is_failure_marker(tr) and failure_marker_is_recent(tr):
                    continue  # failed recently: not shown, not retried yet
                if tr and not is_failure_marker(tr):
                    msg["translation"] = tr.get("translated_text")
                    msg["translation_locale"] = target_locale
                    msg["translation_guard_passed"] = tr.get("guard_passed", True)
                    continue
                # No usable stored translation: translate messages from the other party whose
                # language differs from the viewer's.
                body = str(msg.get("body") or "").strip()
                sender_role = str(msg.get("sender_role") or "")
                if not body or sender_role == self.actor.role:
                    continue
                source_locale = detect_locale(body)
                if self.actor.role == "clinician":
                    needs_translation = source_locale == "es-MX"
                else:
                    needs_translation = source_locale is not None and source_locale != target_locale
                if not needs_translation or source_locale is None:
                    continue
                if on_the_fly >= MAX_ON_THE_FLY_TRANSLATIONS:
                    continue  # only NEW model calls are capped
                on_the_fly += 1
                if protected is None:
                    protected = await self._medication_names(conversation_id)
                try:
                    result = await service.translate_and_store(
                        source_table=_SOURCE_TABLE,
                        source_message_id=msg_id,
                        text=body,
                        source_locale=source_locale,
                        target_locale=target_locale,
                        protected_terms=protected,
                    )
                except Exception:
                    # One failed message must not hide the others; log the id, never the text.
                    logger.warning("Message translation failed for message %s", msg_id)
                    continue
                if result:
                    msg["translation"] = result.get("translated_text")
                    msg["translation_locale"] = target_locale
                    msg["translation_guard_passed"] = result.get("guard_passed", True)
        except Exception:
            # Translations are optional; never fail the read. Log the failure, never the text.
            logger.warning("Attaching message translations failed", exc_info=False)
