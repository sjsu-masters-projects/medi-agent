"""Authenticated human messages: all authorization and writes share a DB transaction."""

import asyncio
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


class CareConversationService:
    def __init__(self, db: Client, actor: CurrentUser) -> None:
        self.db = db
        self.actor = actor

    async def recipients(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], await self._call("recipients"))

    async def list_conversations(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], await self._call("list"))

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

    async def _translate_message(self, message: dict[str, Any]) -> None:
        """LOC-003: Translate a newly sent message and store the translation."""
        try:
            from app.services.message_translation import MessageTranslationService

            body = str(message.get("body") or "").strip()
            message_id = str(message.get("id") or "")
            sender_role = str(message.get("sender_role") or self.actor.role)
            if not body or not message_id:
                return
            service = MessageTranslationService(self.db)
            source_locale, target_locale = service.detect_and_get_target_locale(body, sender_role)
            result = await service.translate_and_store(
                source_table="care_team_conversation_messages",
                source_message_id=message_id,
                text=body,
                source_locale=source_locale,
                target_locale=target_locale,
            )
            if result:
                message["translation"] = result.get("translated_text")
                message["translation_locale"] = target_locale
                message["translation_guard_passed"] = result.get("guard_passed", True)
        except Exception:
            pass  # Translation is optional; never fail the send.

    async def _attach_translations(self, page: dict[str, Any]) -> None:
        """LOC-003: Attach stored translations to messages, translating on the fly if needed."""
        try:
            from app.services.message_translation import MessageTranslationService
            from app.utils.localization import detect_locale

            items = page.get("items") or []
            if not items:
                return
            # Determine the viewer's target locale: clinician sees English, patient sees their language.
            target_locale = "en-US" if self.actor.role == "clinician" else "es-MX"
            message_ids = [str(msg["id"]) for msg in items if msg.get("id")]
            if not message_ids:
                return
            service = MessageTranslationService(self.db)
            translations = service.get_translations_for_messages(
                source_table="care_team_conversation_messages",
                message_ids=message_ids,
                target_locale=target_locale,
            )
            for msg in items:
                msg_id = str(msg.get("id") or "")
                tr = translations.get(msg_id)
                if tr:
                    msg["translation"] = tr.get("translated_text")
                    msg["translation_locale"] = target_locale
                    msg["translation_guard_passed"] = tr.get("guard_passed", True)
                else:
                    # No stored translation — translate on the fly for messages from the
                    # other party (clinician sees patient's Spanish, patient sees clinician's English).
                    body = str(msg.get("body") or "").strip()
                    sender_role = str(msg.get("sender_role") or "")
                    is_other_party = (
                        self.actor.role == "clinician" and sender_role == "patient"
                    ) or (self.actor.role == "patient" and sender_role == "clinician")
                    if not is_other_party or not body:
                        continue
                    detected = detect_locale(body)
                    needs_translation = (
                        self.actor.role == "clinician" and detected == "es-MX"
                    ) or (self.actor.role == "patient" and detected == "en-US")
                    if not needs_translation:
                        continue
                    source_locale = detected or ("es-MX" if target_locale == "en-US" else "en-US")
                    result = await service.translate_and_store(
                        source_table="care_team_conversation_messages",
                        source_message_id=msg_id,
                        text=body,
                        source_locale=source_locale,
                        target_locale=target_locale,
                    )
                    if result:
                        msg["translation"] = result.get("translated_text")
                        msg["translation_locale"] = target_locale
                        msg["translation_guard_passed"] = result.get("guard_passed", True)
        except Exception:
            pass  # Translations are optional; never fail the read.
