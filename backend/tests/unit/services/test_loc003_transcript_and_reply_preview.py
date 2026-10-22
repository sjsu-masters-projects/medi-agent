"""LOC-003 items 3 and 4: the Nora transcript in English, and a confirmed reply.

Item 3 — a clinician reads the patient–Nora transcript in English. Reading it never calls
the model: stored translations are attached and the rest are marked pending, exactly as a
care-conversation read behaves.

Item 4 — before sending, the clinician sees the wording the patient will receive and its
English back-translation, and confirms it. What they confirmed is what gets stored, and the
server re-checks it, because the browser asking for something is not permission to skip a
guard.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.models.auth import CurrentUser
from app.models.care_conversation import ConfirmedTranslation, ConversationSend
from app.services.care_conversation_service import CareConversationService
from app.services.clinician_service import ClinicianService

CLINICIAN = UUID("00000000-0000-0000-0000-0000000003a1")
PATIENT = UUID("00000000-0000-0000-0000-0000000003a2")
CONVERSATION = UUID("00000000-0000-0000-0000-0000000003a3")
MESSAGE = UUID("00000000-0000-0000-0000-0000000003a4")

SPANISH_TURN = "Me duele la cabeza desde ayer y tomé 500 mg"
ENGLISH_TURN = "My head has hurt since yesterday and I took 500 mg"


# ── Item 3: the Nora transcript ───────────────────────────────────────────


def _clinician_service() -> ClinicianService:
    service = ClinicianService(MagicMock())
    service._assert_patient_assignment = AsyncMock()  # type: ignore[method-assign]
    service._active_medication_names = AsyncMock(return_value=["Metformin"])  # type: ignore[method-assign]
    return service


def _turn(content: str, **changes: Any) -> dict[str, Any]:
    return {"id": str(MESSAGE), "role": "user", "content": content, **changes}


class TestWhichTurnsNeedTranslating:
    def test_a_spanish_turn_does(self) -> None:
        assert ClinicianService._transcript_needs_translation(_turn(SPANISH_TURN)) is True

    def test_an_english_turn_does_not(self) -> None:
        assert ClinicianService._transcript_needs_translation(_turn(ENGLISH_TURN)) is False

    def test_an_empty_turn_does_not(self) -> None:
        assert ClinicianService._transcript_needs_translation(_turn("   ")) is False


@pytest.mark.asyncio
class TestAttachingTranscriptTranslations:
    async def _attach(
        self, messages: list[dict[str, Any]], stored: dict[str, Any] | None = None
    ) -> None:
        service = _clinician_service()
        with patch(
            "app.services.message_translation.MessageTranslationService.get_translations_for_messages",
            AsyncMock(return_value=stored or {}),
        ):
            await service._attach_transcript_translations(messages)

    async def test_a_stored_translation_is_attached_with_its_model(self) -> None:
        messages = [_turn(SPANISH_TURN)]
        await self._attach(
            messages,
            {
                str(MESSAGE): {
                    "translated_text": ENGLISH_TURN,
                    "guard_passed": True,
                    "model_id": "gemini-test",
                }
            },
        )
        assert messages[0]["translation"] == ENGLISH_TURN
        assert messages[0]["translation_locale"] == "en-US"
        assert messages[0]["translation_model_id"] == "gemini-test"
        assert "translation_pending" not in messages[0]

    async def test_a_turn_with_nothing_stored_is_marked_pending(self) -> None:
        """A read must not call the model: the portal asks for each pending turn itself."""
        messages = [_turn(SPANISH_TURN)]
        await self._attach(messages)
        assert messages[0]["translation_pending"] is True
        assert "translation" not in messages[0]

    async def test_an_english_turn_is_neither_translated_nor_pending(self) -> None:
        messages = [_turn(ENGLISH_TURN)]
        await self._attach(messages)
        assert "translation_pending" not in messages[0]
        assert "translation" not in messages[0]

    async def test_a_stored_translation_that_failed_its_guard_is_not_shown(self) -> None:
        messages = [_turn(SPANISH_TURN)]
        await self._attach(
            messages,
            {str(MESSAGE): {"translated_text": "I took 250 mg", "guard_passed": False}},
        )
        assert "translation" not in messages[0]
        assert messages[0]["translation_guard_passed"] is False

    async def test_a_fresh_failure_marker_is_neither_shown_nor_requested(self) -> None:
        messages = [_turn(SPANISH_TURN)]
        await self._attach(
            messages,
            {
                str(MESSAGE): {
                    "translated_text": "-",
                    "guard_passed": False,
                    "guard_failure_code": "model_error",
                    "translated_at": datetime.now(UTC).isoformat(),
                }
            },
        )
        assert "translation" not in messages[0]
        assert "translation_pending" not in messages[0]

    async def test_a_failure_to_read_translations_never_fails_the_transcript(self) -> None:
        messages = [_turn(SPANISH_TURN)]
        service = _clinician_service()
        with patch(
            "app.services.message_translation.MessageTranslationService.get_translations_for_messages",
            AsyncMock(side_effect=RuntimeError("database down")),
        ):
            await service._attach_transcript_translations(messages)
        assert messages[0]["content"] == SPANISH_TURN

    async def test_a_turn_with_no_id_is_skipped_rather_than_crashing(self) -> None:
        messages = [{"role": "user", "content": SPANISH_TURN}]
        await self._attach(messages)
        assert "translation_pending" not in messages[0]


@pytest.mark.asyncio
class TestTranslatingOneTranscriptTurn:
    async def test_it_translates_stores_and_returns_the_turn(self) -> None:
        service = _clinician_service()
        service._transcript_message = AsyncMock(return_value=_turn(SPANISH_TURN))  # type: ignore[method-assign]
        with (
            patch(
                "app.services.message_translation.MessageTranslationService.get_translation",
                AsyncMock(return_value=None),
            ),
            patch(
                "app.services.message_translation.MessageTranslationService.translate_and_store",
                AsyncMock(
                    return_value={
                        "translated_text": ENGLISH_TURN,
                        "guard_passed": True,
                        "model_id": "gemini-test",
                    }
                ),
            ) as store,
        ):
            result = await service.translate_transcript_message(CLINICIAN, PATIENT, MESSAGE)
        assert result["translation"] == ENGLISH_TURN
        assert result["translation_model_id"] == "gemini-test"
        # The patient's medication names are protected in the translation.
        assert store.await_args.kwargs["protected_terms"] == ["Metformin"]
        assert store.await_args.kwargs["target_locale"] == "en-US"

    async def test_a_stored_translation_costs_no_model_call(self) -> None:
        service = _clinician_service()
        service._transcript_message = AsyncMock(return_value=_turn(SPANISH_TURN))  # type: ignore[method-assign]
        translate = AsyncMock()
        with (
            patch(
                "app.services.message_translation.MessageTranslationService.get_translation",
                AsyncMock(return_value={"translated_text": ENGLISH_TURN, "guard_passed": True}),
            ),
            patch(
                "app.services.message_translation.MessageTranslationService.translate_and_store",
                translate,
            ),
        ):
            result = await service.translate_transcript_message(CLINICIAN, PATIENT, MESSAGE)
        translate.assert_not_awaited()
        assert result["translation"] == ENGLISH_TURN

    async def test_an_english_turn_is_never_sent_to_the_model(self) -> None:
        service = _clinician_service()
        service._transcript_message = AsyncMock(return_value=_turn(ENGLISH_TURN))  # type: ignore[method-assign]
        translate = AsyncMock()
        with patch(
            "app.services.message_translation.MessageTranslationService.translate_and_store",
            translate,
        ):
            result = await service.translate_transcript_message(CLINICIAN, PATIENT, MESSAGE)
        translate.assert_not_awaited()
        assert result["translation"] is None

    async def test_an_unassigned_clinician_is_refused_before_any_read(self) -> None:
        from app.core.exceptions import AuthorizationError

        service = ClinicianService(MagicMock())
        service._assert_patient_assignment = AsyncMock(  # type: ignore[method-assign]
            side_effect=AuthorizationError("not assigned")
        )
        service._transcript_message = AsyncMock()  # type: ignore[method-assign]
        with pytest.raises(AuthorizationError):
            await service.translate_transcript_message(CLINICIAN, PATIENT, MESSAGE)
        service._transcript_message.assert_not_awaited()

    async def test_another_patients_turn_is_not_found(self) -> None:
        service = _clinician_service()
        service._execute = AsyncMock(return_value=MagicMock(data=[]))  # type: ignore[method-assign]
        with pytest.raises(NotFoundError):
            await service.translate_transcript_message(CLINICIAN, PATIENT, MESSAGE)


# ── Item 4: the reply preview and the confirmed translation ───────────────


def _conversation_service(patient_locale: str = "es-MX") -> CareConversationService:
    actor = CurrentUser(id=CLINICIAN, email="c@synthetic.invalid", role="clinician")
    service = CareConversationService(MagicMock(), actor)
    service._call = AsyncMock(return_value={"items": []})  # type: ignore[method-assign]
    service._patient_locale = AsyncMock(return_value=patient_locale)  # type: ignore[method-assign]
    service._medication_names = AsyncMock(return_value=["Metformin"])  # type: ignore[method-assign]
    return service


REPLY = "Take 1 tablet of Metformin 500 mg twice daily"
REPLY_ES = "Toma 1 tableta de Metformin 500 mg dos veces al día"


@pytest.mark.asyncio
class TestReplyPreview:
    async def test_it_returns_the_patient_wording_and_its_back_translation(self) -> None:
        service = _conversation_service()
        with (
            patch(
                "app.services.message_translation.translate_message",
                AsyncMock(return_value=(REPLY_ES, True, None, "gemini-test")),
            ),
            patch(
                "app.services.message_translation.back_translate_message",
                AsyncMock(return_value=REPLY),
            ),
        ):
            result = await service.preview_reply(CONVERSATION, REPLY)
        assert result["needed"] is True
        assert result["target_locale"] == "es-MX"
        assert result["translation"] == REPLY_ES
        assert result["back_translation"] == REPLY
        assert result["guard_passed"] is True
        assert result["model_id"] == "gemini-test"

    async def test_a_patient_who_reads_english_needs_no_preview(self) -> None:
        service = _conversation_service(patient_locale="en-US")
        translate = AsyncMock()
        with patch("app.services.message_translation.translate_message", translate):
            result = await service.preview_reply(CONVERSATION, REPLY)
        translate.assert_not_awaited()
        assert result["needed"] is False
        assert result["translation"] is None

    async def test_a_guard_failure_is_reported_and_never_back_translated(self) -> None:
        """Wording that moved a number is not offered, so it cannot be confirmed."""
        service = _conversation_service()
        back = AsyncMock()
        with (
            patch(
                "app.services.message_translation.translate_message",
                AsyncMock(return_value=("Toma 250 mg", False, "numbers_changed", "gemini-test")),
            ),
            patch("app.services.message_translation.back_translate_message", back),
        ):
            result = await service.preview_reply(CONVERSATION, REPLY)
        back.assert_not_awaited()
        assert result["guard_passed"] is False
        assert result["guard_failure_code"] == "numbers_changed"
        assert result["back_translation"] is None

    async def test_a_model_failure_leaves_a_previewable_nothing_not_an_error(self) -> None:
        service = _conversation_service()
        with patch(
            "app.services.message_translation.translate_message",
            AsyncMock(side_effect=RuntimeError("model down")),
        ):
            result = await service.preview_reply(CONVERSATION, REPLY)
        assert result["needed"] is True
        assert result["translation"] is None
        assert result["guard_passed"] is None

    async def test_a_failed_back_translation_still_returns_the_wording(self) -> None:
        service = _conversation_service()
        with (
            patch(
                "app.services.message_translation.translate_message",
                AsyncMock(return_value=(REPLY_ES, True, None, "gemini-test")),
            ),
            patch(
                "app.services.message_translation.back_translate_message",
                AsyncMock(side_effect=RuntimeError("model down")),
            ),
        ):
            result = await service.preview_reply(CONVERSATION, REPLY)
        assert result["translation"] == REPLY_ES
        assert result["back_translation"] is None

    async def test_a_patient_cannot_preview_a_clinician_reply(self) -> None:
        from app.core.exceptions import AuthorizationError

        actor = CurrentUser(id=PATIENT, email="p@synthetic.invalid", role="patient")
        service = CareConversationService(MagicMock(), actor)
        with pytest.raises(AuthorizationError):
            await service.preview_reply(CONVERSATION, REPLY)

    async def test_it_is_authorized_like_a_read_of_the_thread(self) -> None:
        service = _conversation_service()
        with (
            patch(
                "app.services.message_translation.translate_message",
                AsyncMock(return_value=(REPLY_ES, True, None, "m")),
            ),
            patch(
                "app.services.message_translation.back_translate_message",
                AsyncMock(return_value=REPLY),
            ),
        ):
            await service.preview_reply(CONVERSATION, REPLY)
        assert service._call.await_args.args[0] == "messages"


@pytest.mark.asyncio
class TestConfirmedTranslationOnSend:
    async def test_the_confirmation_reaches_one_atomic_send(self) -> None:
        service = _conversation_service()
        saved = {
            "id": str(MESSAGE),
            "translation": REPLY_ES,
            "translation_locale": "es-MX",
            "translation_guard_passed": True,
        }
        service._call = AsyncMock(return_value=saved)
        data = ConversationSend(
            body=REPLY,
            client_message_id=UUID(int=7),
            confirmed_translation=ConfirmedTranslation(
                text=REPLY_ES, locale="es-MX", model_id="gemini-test"
            ),
        )
        assert await service.send(CONVERSATION, data) == saved
        calls = service._call.await_args_list
        assert [call.args[0] for call in calls] == ["messages", "send"]
        assert calls[-1].args[1]["confirmed_translation"] == {
            "text": REPLY_ES,
            "locale": "es-MX",
            "model_id": "gemini-test",
            "source_locale": "en-US",
        }

    @pytest.mark.parametrize(
        "confirmed",
        [
            ConfirmedTranslation(text="Toma 250 mg", locale="es-MX"),
            ConfirmedTranslation(text=REPLY, locale="en-US"),
            ConfirmedTranslation(
                text=REPLY_ES, locale="es-MX", model_id="offline-translation-stub"
            ),
        ],
    )
    async def test_invalid_confirmation_is_rejected_before_send(self, confirmed) -> None:
        service = _conversation_service()
        with pytest.raises(ValidationError):
            await service.send(
                CONVERSATION,
                ConversationSend(
                    body=REPLY, client_message_id=UUID(int=7), confirmed_translation=confirmed
                ),
            )
        assert all(call.args[0] != "send" for call in service._call.await_args_list)

    async def test_patient_cannot_supply_a_clinician_facing_translation(self) -> None:
        from app.core.exceptions import AuthorizationError

        service = _conversation_service()
        service.actor = CurrentUser(id=PATIENT, email="p@synthetic.invalid", role="patient")
        with pytest.raises(AuthorizationError):
            await service.send(
                CONVERSATION,
                ConversationSend(
                    body="Me duele la cabeza",
                    client_message_id=UUID(int=7),
                    confirmed_translation=ConfirmedTranslation(text="I feel fine", locale="en-US"),
                ),
            )
        service._call.assert_not_awaited()

    async def test_changed_patient_locale_rejects_before_delivery(self) -> None:
        service = _conversation_service(patient_locale="en-US")
        with pytest.raises(ValidationError):
            await service.send(
                CONVERSATION,
                ConversationSend(
                    body=REPLY,
                    client_message_id=UUID(int=7),
                    confirmed_translation=ConfirmedTranslation(text=REPLY_ES, locale="es-MX"),
                ),
            )
        assert all(call.args[0] != "send" for call in service._call.await_args_list)

    async def test_a_send_without_confirmation_uses_existing_payload(self) -> None:
        service = _conversation_service()
        service._call = AsyncMock(return_value={"id": str(MESSAGE)})
        result = await service.send(
            CONVERSATION, ConversationSend(body=REPLY, client_message_id=UUID(int=7))
        )
        service._call.assert_awaited_once()
        assert "confirmed_translation" not in service._call.await_args.args[1]
        assert "translation" not in result
