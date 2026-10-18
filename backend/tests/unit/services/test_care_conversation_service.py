"""No real database/provider credentials; verify trusted RPC boundary."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from app.core.exceptions import AuthorizationError, ExternalServiceError, ValidationError
from app.models.auth import CurrentUser
from app.models.care_conversation import (
    ConversationCreate,
    ConversationReadMarker,
    ConversationSend,
)
from app.services.care_conversation_service import CareConversationService


@pytest.fixture
def service():
    db = MagicMock()
    db.rpc.return_value.execute.return_value = SimpleNamespace(data={"saved": True})
    actor = CurrentUser(id=uuid4(), email="synthetic@example.com", role="patient")
    return CareConversationService(db, actor), db


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["patient", "clinician"])
async def test_send_uses_only_authenticated_actor_and_one_rpc(service, role):
    svc, db = service
    svc.actor.role = role
    conversation, key = uuid4(), uuid4()
    assert await svc.send(
        conversation, ConversationSend(body="  Synthetic reply\n", client_message_id=key)
    ) == {"saved": True}
    db.rpc.assert_called_once_with(
        "care_conversation_operation",
        {
            "p_actor_id": str(svc.actor.id),
            "p_actor_role": role,
            "p_action": "send",
            "p_payload": {
                "conversation_id": str(conversation),
                "body": "Synthetic reply",
                "client_message_id": str(key),
            },
        },
    )
    db.table.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["recipients", "list", "open", "messages", "read"])
async def test_every_read_or_write_is_fresh_rpc(service, action):
    svc, db = service
    ident = uuid4()
    if action == "recipients":
        await svc.recipients()
    elif action == "list":
        await svc.list_conversations()
    elif action == "open":
        await svc.open_conversation(ConversationCreate(recipient_id=ident))
    elif action == "messages":
        await svc.messages(ident, {"before": None, "limit": 50})
    else:
        await svc.mark_read(ident, ConversationReadMarker(last_message_id=uuid4()))
    assert db.rpc.call_args.args[1]["p_action"] == action
    await svc.recipients()
    assert db.rpc.call_count == 2
    db.table.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code,exception",
    [
        ("42501", AuthorizationError),
        ("22023", ValidationError),
        ("23505", ValidationError),
        ("40001", ExternalServiceError),
        ("XX000", ExternalServiceError),
    ],
)
async def test_database_errors_are_neutral_and_never_echo_body(service, code, exception, caplog):
    svc, db = service
    private = "Synthetic private body must not escape"
    db.rpc.return_value.execute.side_effect = APIError(
        {"code": code, "message": private, "details": private, "hint": private}
    )
    with pytest.raises(exception) as caught:
        await svc.recipients()
    assert private not in str(caught.value)
    assert private not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["unknown", "admin", "assistant"])
async def test_unknown_actor_never_calls_database(service, role):
    svc, db = service
    svc.actor.role = role
    with pytest.raises(AuthorizationError):
        await svc.recipients()
    db.rpc.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "private", 1])
async def test_invalid_database_response_fails_closed(service, value):
    svc, db = service
    db.rpc.return_value.execute.return_value.data = value
    with pytest.raises(ExternalServiceError):
        await svc.recipients()


@pytest.mark.asyncio
async def test_clinician_conversations_are_tagged_and_filtered_by_link_clinic(service):
    from unittest.mock import AsyncMock, patch

    from app.services.clinic_link_scope import ClinicLinkScope

    svc, db = service
    svc.actor.role = "clinician"
    here, there = str(uuid4()), str(uuid4())
    db.rpc.return_value.execute.return_value = SimpleNamespace(
        data=[{"id": "t1", "patient_id": here}, {"id": "t2", "patient_id": there}]
    )
    both = ClinicLinkScope({here: ("c1", "One"), there: ("c2", "Two")})
    only_one = ClinicLinkScope({here: ("c1", "One")})
    path = "app.services.clinic_membership_service.ClinicMembershipService.link_scope"
    with patch(path, new=AsyncMock(return_value=both)):
        rows = await svc.list_conversations()
    assert [(r["id"], r["clinic_id"]) for r in rows] == [("t1", "c1"), ("t2", "c2")]
    db.rpc.return_value.execute.return_value = SimpleNamespace(
        data=[{"id": "t1", "patient_id": here}, {"id": "t2", "patient_id": there}]
    )
    with patch(path, new=AsyncMock(return_value=only_one)):
        assert [r["id"] for r in await svc.list_conversations(uuid4())] == ["t1"]
    with patch(path, new=AsyncMock(return_value=ClinicLinkScope())):
        assert await svc.list_conversations(uuid4()) == []


@pytest.mark.asyncio
async def test_patient_conversations_ignore_the_clinic_filter(service):
    svc, db = service
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=[{"id": "t1"}])
    assert await svc.list_conversations(uuid4()) == [{"id": "t1"}]


# ── LOC-003 translation reads are bounded, logged, and never fail the read ──


def _translating_service(role: str = "clinician"):
    db = MagicMock()
    actor = CurrentUser(id=uuid4(), email="synthetic@example.com", role=role)
    return CareConversationService(db, actor)


def _spanish_page(count: int) -> dict:
    return {
        "items": [
            {
                "id": f"m-{i}",
                "sender_role": "patient",
                "body": "Hola doctora, no me siento bien y tengo mucho dolor hoy.",
            }
            for i in range(count)
        ]
    }


@pytest.mark.asyncio
async def test_on_the_fly_translation_is_bounded_and_skips_stored(monkeypatch):
    from unittest.mock import AsyncMock, patch

    from app.services import care_conversation_service as module

    fake = MagicMock()
    fake.get_translations_for_messages = AsyncMock(
        return_value={"m-0": {"translated_text": "stored", "guard_passed": True}}
    )
    fake.translate_and_store = AsyncMock(
        return_value={"translated_text": "x", "guard_passed": True}
    )
    svc = _translating_service()
    page = _spanish_page(module.MAX_ON_THE_FLY_TRANSLATIONS + 5)
    with patch("app.services.message_translation.MessageTranslationService", return_value=fake):
        await svc._attach_translations(page)
    assert fake.translate_and_store.await_count == module.MAX_ON_THE_FLY_TRANSLATIONS
    called = {c.kwargs["source_message_id"] for c in fake.translate_and_store.await_args_list}
    assert "m-0" not in called
    assert page["items"][0]["translation"] == "stored"


@pytest.mark.asyncio
async def test_translation_failure_is_logged_without_message_text(caplog):
    from unittest.mock import AsyncMock, patch

    fake = MagicMock()
    fake.get_translations_for_messages = AsyncMock(return_value={})
    fake.translate_and_store = AsyncMock(side_effect=RuntimeError("provider down"))
    svc = _translating_service()
    page = _spanish_page(2)
    with (
        patch("app.services.message_translation.MessageTranslationService", return_value=fake),
        caplog.at_level("WARNING"),
    ):
        await svc._attach_translations(page)  # must not raise
    assert "translation" in caplog.text.lower()
    assert "dolor" not in caplog.text
    assert "translation" not in page["items"][0]


# ── LOC-003 review fixes: the patient's own language, stored rows, failure markers ──


def _page(*messages: tuple[str, str, str]) -> dict:
    return {
        "items": [
            {"id": mid, "conversation_id": "c-1", "sender_role": role, "body": body}
            for mid, role, body in messages
        ]
    }


def _fake_translator(stored: dict | None = None, result: dict | None = None):
    from unittest.mock import AsyncMock

    fake = MagicMock()
    fake.get_translations_for_messages = AsyncMock(return_value=stored or {})
    fake.translate_and_store = AsyncMock(
        return_value=result or {"translated_text": "translated", "guard_passed": True}
    )
    # The real routing helper decides who translates what; keep it real.
    from app.services.message_translation import MessageTranslationService

    fake.detect_and_get_target_locale = MessageTranslationService(
        MagicMock()
    ).detect_and_get_target_locale
    return fake


def _patched(svc, fake, locale: str):
    from unittest.mock import AsyncMock, patch

    svc._patient_locale = AsyncMock(return_value=locale)
    svc._medication_names = AsyncMock(return_value=[])
    return patch("app.services.message_translation.MessageTranslationService", return_value=fake)


ENGLISH_REPLY = "Please take your medication every morning with breakfast and some water."


@pytest.mark.asyncio
async def test_english_patient_sees_original_english_with_no_model_call():
    fake = _fake_translator()
    svc = _translating_service("patient")
    page = _page(("m-1", "clinician", ENGLISH_REPLY))
    with _patched(svc, fake, "en-US"):
        await svc._attach_translations(page)
    svc._patient_locale.assert_awaited()  # the patient's own language decides the target
    fake.translate_and_store.assert_not_awaited()
    assert "translation" not in page["items"][0]


@pytest.mark.asyncio
async def test_spanish_patient_sees_the_translation_into_spanish():
    fake = _fake_translator(result={"translated_text": "Toma tu medicina", "guard_passed": True})
    svc = _translating_service("patient")
    page = _page(("m-1", "clinician", ENGLISH_REPLY))
    with _patched(svc, fake, "es-MX"):
        await svc._attach_translations(page)
    assert fake.translate_and_store.await_args.kwargs["target_locale"] == "es-MX"
    assert page["items"][0]["translation"] == "Toma tu medicina"
    assert page["items"][0]["translation_locale"] == "es-MX"


@pytest.mark.asyncio
async def test_clinician_sees_a_spanish_patient_message_in_english_only():
    fake = _fake_translator(result={"translated_text": "I feel bad", "guard_passed": True})
    svc = _translating_service("clinician")
    page = _page(
        ("m-1", "patient", "Hola doctora, no me siento bien y tengo mucho dolor hoy."),
        ("m-2", "patient", "Thank you doctor, I feel better and the pain is gone today."),
    )
    with _patched(svc, fake, "es-MX"):
        await svc._attach_translations(page)
    assert fake.translate_and_store.await_count == 1
    assert fake.translate_and_store.await_args.kwargs["target_locale"] == "en-US"
    assert page["items"][0]["translation"] == "I feel bad"
    assert "translation" not in page["items"][1]


@pytest.mark.asyncio
@pytest.mark.parametrize(("locale", "calls"), [("en-US", 0), ("es-MX", 1)])
async def test_clinician_reply_is_translated_only_for_a_spanish_patient(locale, calls):
    fake = _fake_translator(result={"translated_text": "Toma tu medicina", "guard_passed": True})
    svc = _translating_service("clinician")
    message = {
        "id": "m-9",
        "conversation_id": "c-1",
        "sender_role": "clinician",
        "body": ENGLISH_REPLY,
    }
    with _patched(svc, fake, locale):
        await svc._translate_message(message)
    assert fake.translate_and_store.await_count == calls
    assert ("translation" in message) is bool(calls)


@pytest.mark.asyncio
async def test_stored_translations_are_attached_beyond_the_new_call_cap():
    from app.services import care_conversation_service as module

    count = module.MAX_ON_THE_FLY_TRANSLATIONS + 5
    page = _spanish_page(count)
    for item in page["items"]:
        item["conversation_id"] = "c-1"
    stored = {
        f"m-{i}": {"translated_text": f"stored {i}", "guard_passed": True} for i in range(count)
    }
    fake = _fake_translator(stored=stored)
    svc = _translating_service("clinician")
    with _patched(svc, fake, "es-MX"):
        await svc._attach_translations(page)
    fake.translate_and_store.assert_not_awaited()
    assert all(item["translation"] == f"stored {i}" for i, item in enumerate(page["items"]))


@pytest.mark.asyncio
async def test_new_calls_are_capped_but_messages_after_the_cap_still_get_stored_rows():
    from app.services import care_conversation_service as module

    cap = module.MAX_ON_THE_FLY_TRANSLATIONS
    page = _spanish_page(cap + 3)
    for item in page["items"]:
        item["conversation_id"] = "c-1"
    last = f"m-{cap + 2}"
    fake = _fake_translator(stored={last: {"translated_text": "stored last", "guard_passed": True}})
    svc = _translating_service("clinician")
    with _patched(svc, fake, "es-MX"):
        await svc._attach_translations(page)
    assert fake.translate_and_store.await_count == cap
    assert page["items"][-1]["translation"] == "stored last"


@pytest.mark.asyncio
async def test_a_recent_failure_marker_is_not_retried_or_shown():
    from datetime import UTC, datetime

    marker = {
        "translated_text": "-",
        "guard_passed": False,
        "guard_failure_code": "model_error",
        "translated_at": datetime.now(UTC).isoformat(),
    }
    page = _spanish_page(1)
    page["items"][0]["conversation_id"] = "c-1"
    fake = _fake_translator(stored={"m-0": marker})
    svc = _translating_service("clinician")
    with _patched(svc, fake, "es-MX"):
        await svc._attach_translations(page)
    fake.translate_and_store.assert_not_awaited()
    assert "translation" not in page["items"][0]


@pytest.mark.asyncio
async def test_an_old_failure_marker_is_retried():
    marker = {
        "translated_text": "-",
        "guard_passed": False,
        "guard_failure_code": "model_error",
        "translated_at": "2020-01-01T00:00:00+00:00",
    }
    page = _spanish_page(1)
    page["items"][0]["conversation_id"] = "c-1"
    fake = _fake_translator(stored={"m-0": marker})
    svc = _translating_service("clinician")
    with _patched(svc, fake, "es-MX"):
        await svc._attach_translations(page)
    fake.translate_and_store.assert_awaited_once()
