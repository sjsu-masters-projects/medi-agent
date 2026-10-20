"""Authenticated human messages: all authorization and writes share a DB transaction."""

import asyncio
import logging
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from app.core.exceptions import (
    AuthorizationError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from app.models.auth import CurrentUser
from app.models.care_conversation import (
    ConfirmedTranslation,
    ConversationCreate,
    ConversationReadMarker,
    ConversationSend,
)
from app.models.enums import Language, coerce_locale
from app.services.clinic_membership_service import ClinicMembershipService
from app.services.translation_guards import guard_failure
from app.utils.localization import detect_locale

logger = logging.getLogger(__name__)

# Translation never runs in the send or read path (Cloud Run only gives CPU while a request
# is open): reads mark what is missing, and the viewer asks for each one on its own request.
_SOURCE_TABLE = "care_team_conversation_messages"

#: Plain-language reasons a confirmed translation is rejected, for the clinician who sees it.
_GUARD_LABELS = {
    "numbers_changed": "a number or unit differs from your message",
    "negation_changed": "a negation (no, not, never, without) differs from your message",
    "medication_name_changed": "a medication name differs from your message",
}

_ACTIVITY_ERROR_HINTS: dict[str, tuple[str, str]] = {
    "activity_context_unavailable": (
        "ACTIVITY_CONTEXT_UNAVAILABLE",
        "This activity cannot be opened from this message. Reload the conversation.",
    ),
    "activity_context_stale": (
        "ACTIVITY_CONTEXT_STALE",
        "This activity is no longer in the approved plan. Open the current care plan.",
    ),
    "care_plan_draft_exists": (
        "CARE_PLAN_DRAFT_EXISTS",
        "A current care-plan draft needs review before this activity can be opened.",
    ),
}


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
        payload = data.model_dump(mode="json", exclude={"confirmed_translation"})
        result = cast(
            dict[str, Any],
            await self._call(
                "send",
                {
                    "conversation_id": str(conversation),
                    **payload,
                },
            ),
        )
        # LOC-003: no model call here. A reader asks for the translation of this message —
        # unless the clinician previewed and confirmed one, which is stored as-is so the
        # patient reads exactly the wording that was approved (decision 3).
        if data.confirmed_translation and result.get("id"):
            await self.store_confirmed_translation(
                str(conversation), str(result["id"]), data.body, data.confirmed_translation
            )
            result["translation"] = data.confirmed_translation.text
            result["translation_locale"] = data.confirmed_translation.locale.value
            result["translation_guard_passed"] = True
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

    async def review_activity(self, conversation: UUID, message: UUID) -> dict[str, Any]:
        """Explicit clinician action creates/reuses a draft, never publishes."""
        if self.actor.role != "clinician":
            raise self._denial()
        return cast(
            dict[str, Any],
            await self._call(
                "review",
                {
                    "conversation_id": str(conversation),
                    "message_id": str(message),
                },
            ),
        )

    async def _call(self, action: str, payload: dict[str, Any] | None = None) -> Any:
        if self.actor.role not in {"patient", "clinician"}:
            raise self._denial()
        try:
            result = await asyncio.to_thread(
                self.db.rpc(
                    "care_conversation_activity_operation"
                    if action in {"send", "review"}
                    else "care_conversation_operation",
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
            activity_error = _ACTIVITY_ERROR_HINTS.get(str(exc.hint or ""))
            if activity_error is not None:
                code, message = activity_error
                raise ValidationError(message, code=code) from None
            if action == "review" and exc.code in {"23505", "40001"}:
                raise ValidationError(
                    "The care-plan draft changed. Reload before opening this activity.",
                    code="CARE_PLAN_REVIEW_CONFLICT",
                ) from None
            if exc.code == "22023":
                raise ValidationError(
                    "Invalid conversation request",
                    code="INVALID_CONVERSATION_REQUEST",
                ) from None
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

    async def _viewer_target(self, conversation_id: str | None) -> str:
        """A clinician reads English; a patient reads their own ``preferred_language``."""
        if self.actor.role == "clinician":
            return Language.EN.value
        return await self._patient_locale(conversation_id)

    def _source_needing_translation(self, msg: dict[str, Any], target_locale: str) -> str | None:
        """The detected language of another party's message when it differs from the viewer's.

        Own messages, empty bodies and text already in the viewer's language need nothing.
        """
        body = str(msg.get("body") or "").strip()
        if not body or str(msg.get("sender_role") or "") == self.actor.role:
            return None
        source_locale = detect_locale(body)
        if source_locale is None or source_locale == target_locale:
            return None
        if self.actor.role == "clinician" and source_locale != "es-MX":
            return None
        return source_locale

    async def _attach_translations(self, page: dict[str, Any]) -> None:
        """LOC-003: Attach STORED translations and mark the messages still to be translated.

        No model call happens here. A message the viewer needs translated but which has none
        stored (or only a failure marker older than an hour) gets ``translation_pending``; the
        viewer then asks for it with ``translate_message``. A recent failure marker is neither
        shown nor pending.
        """
        try:
            from app.services.message_translation import (
                MessageTranslationService,
                failure_marker_is_recent,
                is_failure_marker,
            )

            items = page.get("items") or []
            message_ids = [str(msg["id"]) for msg in items if msg.get("id")]
            if not message_ids:
                return
            conversation_id = next(
                (str(m["conversation_id"]) for m in items if m.get("conversation_id")), None
            )
            target_locale = await self._viewer_target(conversation_id)
            translations = await MessageTranslationService(self.db).get_translations_for_messages(
                source_table=_SOURCE_TABLE,
                message_ids=message_ids,
                target_locale=target_locale,
            )
            for msg in items:
                tr = translations.get(str(msg.get("id") or ""))
                if tr and not is_failure_marker(tr):
                    msg["translation"] = tr.get("translated_text")
                    msg["translation_locale"] = target_locale
                    msg["translation_guard_passed"] = tr.get("guard_passed", True)
                    # LOC-003 item 5: which model produced it, so the reader can be told.
                    msg["translation_model_id"] = tr.get("model_id")
                    continue
                if tr and failure_marker_is_recent(tr):
                    continue  # failed recently: not shown, not requested again yet
                if self._source_needing_translation(msg, target_locale):
                    msg["translation_pending"] = True
        except Exception:
            # Translations are optional; never fail the read. Log the failure, never the text.
            logger.warning("Attaching message translations failed", exc_info=False)

    async def preview_reply(self, conversation: UUID, body: str) -> dict[str, Any]:
        """LOC-003 decision 3: the Spanish a patient will receive, and its back-translation.

        A clinician writes English. Before sending, they see exactly what the patient will
        read, plus an English back-translation of it and the guard results, so they can
        confirm the Spanish without reading Spanish. Nothing is stored: this is unsent text.

        When the patient reads English there is nothing to preview, and ``needed`` is false.
        """
        from app.services.message_translation import back_translate_message, translate_message

        if self.actor.role != "clinician":
            raise self._denial()
        conversation_id = str(conversation)
        # Same authorization as reading the thread: an outsider cannot preview into it.
        await self._call("messages", {"conversation_id": conversation_id, "limit": 1})
        target_locale = await self._patient_locale(conversation_id)
        text = body.strip()
        result: dict[str, Any] = {
            "needed": False,
            "target_locale": target_locale,
            "translation": None,
            "back_translation": None,
            "guard_passed": None,
            "guard_failure_code": None,
            "model_id": None,
        }
        source_locale = detect_locale(text) or Language.EN.value
        if not text or source_locale == target_locale:
            return result  # the patient reads this language already
        result["needed"] = True

        protected = await self._medication_names(conversation_id)
        try:
            translation, guard_passed, failure_code, model_id = await translate_message(
                text, source_locale, target_locale, protected
            )
        except Exception:
            logger.warning("Reply preview translation failed", exc_info=False)
            return result  # no preview; the caller offers to send the English as written
        result.update(
            {
                "translation": translation,
                "guard_passed": guard_passed,
                "guard_failure_code": failure_code,
                "model_id": model_id,
            }
        )
        if not guard_passed:
            # A translation that moved a number is never offered, so it is never confirmed.
            return result
        try:
            result["back_translation"] = await back_translate_message(
                translation, target_locale, source_locale, protected
            )
        except Exception:
            logger.warning("Reply preview back-translation failed", exc_info=False)
        return result

    async def store_confirmed_translation(
        self, conversation_id: str, message_id: str, body: str, confirmed: ConfirmedTranslation
    ) -> None:
        """Store the exact wording the clinician confirmed as this message's translation.

        The clinician approved specific Spanish, so that is what the patient must see rather
        than a fresh translation that could differ. The guards are re-run here against the
        message body: the browser asking for something must never be a way around them.
        """
        from app.services.message_translation import MessageTranslationService

        source_locale = detect_locale(body) or Language.EN.value
        if confirmed.locale == source_locale:
            raise ValidationError("A confirmed translation must be in the patient's language")
        failure = guard_failure(body, confirmed.text, await self._medication_names(conversation_id))
        if failure:
            raise ValidationError(
                "The confirmed translation no longer matches the message: "
                f"{_GUARD_LABELS.get(failure, failure)}. Preview it again."
            )
        await MessageTranslationService(self.db).store_gloss(
            source_table=_SOURCE_TABLE,
            source_message_id=message_id,
            translated_text=confirmed.text,
            guard_passed=True,
            model_id=confirmed.model_id,
            source_locale=source_locale,
            target_locale=confirmed.locale,
        )

    async def translate_message(self, conversation: UUID, message_id: UUID) -> dict[str, Any]:
        """Translate ONE message for the viewer, store it, and return it (idempotent).

        Authorized like reading the conversation. A stored translation or a fresh failure
        marker is returned without a model call. Nothing here can fail the viewer's reading:
        a model failure is stored as a marker and reported as "no translation".
        """
        from app.services.message_translation import (
            MessageTranslationService,
            failure_marker_is_recent,
            is_failure_marker,
        )

        conversation_id = str(conversation)
        # Same authorization as a read of this conversation; the cursor also proves the message
        # belongs to it (an unknown or foreign message id is "not found", not a distinct error).
        try:
            await self._call(
                "messages",
                {"conversation_id": conversation_id, "before": str(message_id), "limit": 1},
            )
        except ValidationError:
            raise NotFoundError("Message", str(message_id)) from None
        message = await self._load_message(conversation_id, str(message_id))
        target_locale = await self._viewer_target(conversation_id)
        result: dict[str, Any] = {
            "message_id": str(message_id),
            "translation": None,
            "translation_locale": target_locale,
            "translation_guard_passed": None,
            "translation_pending": False,
        }
        source_locale = self._source_needing_translation(message, target_locale)
        if source_locale is None:
            return result  # already in the viewer's language, or the viewer's own message
        service = MessageTranslationService(self.db)
        stored = await service.get_translation(_SOURCE_TABLE, str(message_id), target_locale)
        if stored and not is_failure_marker(stored):
            return self._with_translation(result, stored)
        if stored and failure_marker_is_recent(stored):
            return result
        row = await service.translate_and_store(
            source_table=_SOURCE_TABLE,
            source_message_id=str(message_id),
            text=str(message["body"]).strip(),
            source_locale=source_locale,
            target_locale=target_locale,
            protected_terms=await self._medication_names(conversation_id),
        )
        return self._with_translation(result, row) if row else result

    @staticmethod
    def _with_translation(result: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
        result["translation"] = row.get("translated_text")
        result["translation_guard_passed"] = row.get("guard_passed", True)
        result["translation_model_id"] = row.get("model_id")
        return result

    async def _load_message(self, conversation_id: str, message_id: str) -> dict[str, Any]:
        def read() -> list[dict[str, Any]]:
            return cast(
                list[dict[str, Any]],
                self.db.table("care_conversation_messages")
                .select("id, sender_role, body")
                .eq("id", message_id)
                .eq("conversation_id", conversation_id)
                .limit(1)
                .execute()
                .data
                or [],
            )

        try:
            rows = await asyncio.to_thread(read)
        except Exception:
            raise ExternalServiceError("Supabase", "Conversation operation failed") from None
        if not rows:
            raise NotFoundError("Message", message_id)
        return rows[0]
