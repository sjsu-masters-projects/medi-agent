"""No real database/provider credentials; verify trusted RPC boundary."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from app.core.exceptions import (
    AuthorizationError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
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
        "care_conversation_confirmed_operation"
        if role == "clinician"
        else "care_conversation_activity_operation",
        {
            "p_actor_id": str(svc.actor.id),
            "p_actor_role": role,
            "p_action": "send",
            "p_payload": {
                "conversation_id": str(conversation),
                "body": "Synthetic reply",
                "client_message_id": str(key),
                "care_plan_item_id": None,
                **({"original_source_locale": "en-US"} if role == "clinician" else {}),
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


# ── LOC-003 translation: no model call on send or read; one authorized request per message ──

from unittest.mock import AsyncMock, patch  # noqa: E402

SPANISH = "Hola doctora, no me siento bien y tengo mucho dolor hoy."
ENGLISH_REPLY = "Please take your medication every morning with breakfast and some water."
OLD_MARKER = {
    "translated_text": "-",
    "guard_passed": False,
    "guard_failure_code": "model_error",
    "translated_at": "2020-01-01T00:00:00+00:00",
}


def _translating_service(role: str = "clinician"):
    db = MagicMock()
    actor = CurrentUser(id=uuid4(), email="synthetic@example.com", role=role)
    return CareConversationService(db, actor)


def _page(*messages: tuple[str, str, str]) -> dict:
    return {
        "items": [
            {"id": mid, "conversation_id": "c-1", "sender_role": role, "body": body}
            for mid, role, body in messages
        ]
    }


def _fake_translator(stored: dict | None = None, row: dict | None = None):
    fake = MagicMock()
    fake.get_translations_for_messages = AsyncMock(return_value=stored or {})
    fake.get_translation = AsyncMock(return_value=None)
    fake.translate_and_store = AsyncMock(
        return_value=row or {"translated_text": "translated", "guard_passed": True}
    )
    return fake


def _patched(svc, fake, locale: str):
    svc._patient_locale = AsyncMock(return_value=locale)
    svc._medication_names = AsyncMock(return_value=[])
    return patch("app.services.message_translation.MessageTranslationService", return_value=fake)


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["en-US", "es-MX"])
async def test_send_makes_no_model_call(locale):
    svc = _translating_service("clinician")
    svc._call = AsyncMock(
        return_value={
            "id": "m-1",
            "conversation_id": "c-1",
            "sender_role": "clinician",
            "body": ENGLISH_REPLY,
        }
    )
    fake = _fake_translator()
    with (
        _patched(svc, fake, locale),
        patch("app.services.message_translation.translate_message", new=AsyncMock()) as model,
    ):
        sent = await svc.send(
            uuid4(), ConversationSend(body=ENGLISH_REPLY, client_message_id=uuid4())
        )
    model.assert_not_awaited()
    fake.translate_and_store.assert_not_awaited()
    assert "translation" not in sent


@pytest.mark.asyncio
async def test_read_makes_no_model_call_and_marks_missing_translations_pending():
    fake = _fake_translator()
    svc = _translating_service("clinician")
    page = _page(("m-1", "patient", SPANISH))
    with _patched(svc, fake, "es-MX"):
        await svc._attach_translations(page)
    fake.translate_and_store.assert_not_awaited()
    assert page["items"][0]["translation_pending"] is True
    assert "translation" not in page["items"][0]


@pytest.mark.asyncio
async def test_read_attaches_every_stored_translation_without_pending():
    stored = {f"m-{i}": {"translated_text": f"stored {i}", "guard_passed": True} for i in range(15)}
    page = _page(*[(f"m-{i}", "patient", SPANISH) for i in range(15)])
    svc = _translating_service("clinician")
    with _patched(svc, _fake_translator(stored=stored), "es-MX"):
        await svc._attach_translations(page)
    assert all(m["translation"] == f"stored {i}" for i, m in enumerate(page["items"]))
    assert not any(m.get("translation_pending") for m in page["items"])


@pytest.mark.asyncio
async def test_english_patient_gets_no_pending_marker_and_no_translation():
    page = _page(("m-1", "clinician", ENGLISH_REPLY))
    svc = _translating_service("patient")
    with _patched(svc, _fake_translator(), "en-US"):
        await svc._attach_translations(page)
    assert "translation" not in page["items"][0]
    assert not page["items"][0].get("translation_pending")


@pytest.mark.asyncio
async def test_spanish_patient_is_pending_for_english_replies_only():
    page = _page(("m-1", "clinician", ENGLISH_REPLY), ("m-2", "patient", SPANISH))
    svc = _translating_service("patient")
    with _patched(svc, _fake_translator(), "es-MX"):
        await svc._attach_translations(page)
    assert page["items"][0]["translation_pending"] is True
    assert not page["items"][1].get("translation_pending")  # their own message


@pytest.mark.asyncio
async def test_recent_failure_marker_is_neither_shown_nor_pending():
    from datetime import UTC, datetime

    marker = {**OLD_MARKER, "translated_at": datetime.now(UTC).isoformat()}
    page = _page(("m-1", "patient", SPANISH))
    svc = _translating_service("clinician")
    with _patched(svc, _fake_translator(stored={"m-1": marker}), "es-MX"):
        await svc._attach_translations(page)
    assert "translation" not in page["items"][0]
    assert not page["items"][0].get("translation_pending")


@pytest.mark.asyncio
async def test_old_failure_marker_is_pending_again():
    page = _page(("m-1", "patient", SPANISH))
    svc = _translating_service("clinician")
    with _patched(svc, _fake_translator(stored={"m-1": OLD_MARKER}), "es-MX"):
        await svc._attach_translations(page)
    assert page["items"][0]["translation_pending"] is True


def _endpoint_service(role="clinician", body=SPANISH, sender="patient"):
    svc = _translating_service(role)
    svc._call = AsyncMock(return_value={"items": [], "next_cursor": None})
    svc._load_message = AsyncMock(return_value={"id": "m-1", "sender_role": sender, "body": body})
    return svc


@pytest.mark.asyncio
async def test_translation_endpoint_translates_and_stores_one_message():
    svc = _endpoint_service()
    fake = _fake_translator(row={"translated_text": "I feel bad", "guard_passed": True})
    with _patched(svc, fake, "es-MX"):
        out = await svc.translate_message(uuid4(), uuid4())
    fake.translate_and_store.assert_awaited_once()
    assert fake.translate_and_store.await_args.kwargs["target_locale"] == "en-US"
    assert out["translation"] == "I feel bad"
    assert out["translation_guard_passed"] is True
    # Authorized exactly like a read of this conversation.
    assert svc._call.await_args.args[0] == "messages"


@pytest.mark.asyncio
async def test_translation_endpoint_is_idempotent_when_one_is_stored():
    svc = _endpoint_service()
    fake = _fake_translator()
    fake.get_translation = AsyncMock(return_value={"translated_text": "kept", "guard_passed": True})
    with _patched(svc, fake, "es-MX"):
        out = await svc.translate_message(uuid4(), uuid4())
    fake.translate_and_store.assert_not_awaited()
    assert out["translation"] == "kept"


@pytest.mark.asyncio
async def test_translation_endpoint_respects_failure_markers():
    from datetime import UTC, datetime

    svc = _endpoint_service()
    fake = _fake_translator()
    fake.get_translation = AsyncMock(
        return_value={**OLD_MARKER, "translated_at": datetime.now(UTC).isoformat()}
    )
    with _patched(svc, fake, "es-MX"):
        out = await svc.translate_message(uuid4(), uuid4())
    fake.translate_and_store.assert_not_awaited()
    assert out["translation"] is None
    # An hour-old marker may be retried once.
    fake.get_translation = AsyncMock(return_value=OLD_MARKER)
    with _patched(svc, fake, "es-MX"):
        await svc.translate_message(uuid4(), uuid4())
    fake.translate_and_store.assert_awaited_once()


@pytest.mark.asyncio
async def test_translation_endpoint_makes_no_call_when_languages_match():
    svc = _endpoint_service(role="patient", body=ENGLISH_REPLY, sender="clinician")
    fake = _fake_translator()
    with _patched(svc, fake, "en-US"):
        out = await svc.translate_message(uuid4(), uuid4())
    fake.translate_and_store.assert_not_awaited()
    assert out["translation"] is None


@pytest.mark.asyncio
async def test_original_only_fallback_cannot_be_translated_on_a_later_read():
    marker = {
        "translated_text": "-",
        "guard_passed": False,
        "guard_failure_code": "original_only",
        "translated_at": "2000-01-01T00:00:00Z",
    }
    svc = _endpoint_service(
        role="patient", body="Do not take 500 mg without food", sender="clinician"
    )
    fake = _fake_translator(stored={"m-1": marker})
    fake.get_translation = AsyncMock(return_value=marker)
    with _patched(svc, fake, "es-MX"):
        result = await svc.translate_message(uuid4(), uuid4())
        page = _page(("m-1", "clinician", "Do not take 500 mg without food"))
        await svc._attach_translations(page)
    assert result["translation"] is None
    assert not page["items"][0].get("translation_pending")
    assert not page["items"][0].get("translation")
    fake.translate_and_store.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_lookup_is_not_permission_to_regenerate_clinician_wording():
    svc = _endpoint_service(role="patient", body=ENGLISH_REPLY, sender="clinician")
    fake = _fake_translator()
    fake.get_translation = AsyncMock(side_effect=RuntimeError("unavailable"))
    with _patched(svc, fake, "es-MX"):
        result = await svc.translate_message(uuid4(), uuid4())
    assert result["translation"] is None
    fake.translate_and_store.assert_not_awaited()


@pytest.mark.asyncio
async def test_translation_endpoint_refuses_an_outsider_and_a_foreign_message():
    svc = _translating_service("clinician")
    svc._call = AsyncMock(side_effect=svc._denial())
    with pytest.raises(AuthorizationError):
        await svc.translate_message(uuid4(), uuid4())
    svc._call = AsyncMock(side_effect=ValidationError("Invalid conversation request"))
    with pytest.raises(NotFoundError):
        await svc.translate_message(uuid4(), uuid4())


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["23505", "40001"])
async def test_activity_review_race_is_not_a_message_idempotency_error(service, code):
    svc, db = service
    svc.actor.role = "clinician"
    db.rpc.return_value.execute.side_effect = APIError({"code": code, "message": "private detail"})
    with pytest.raises(ValidationError) as error:
        await svc.review_activity(uuid4(), uuid4())
    assert error.value.code == "CARE_PLAN_REVIEW_CONFLICT"
    assert "private detail" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hint,expected_code",
    [
        ("activity_context_unavailable", "ACTIVITY_CONTEXT_UNAVAILABLE"),
        ("activity_context_stale", "ACTIVITY_CONTEXT_STALE"),
        ("care_plan_draft_exists", "CARE_PLAN_DRAFT_EXISTS"),
    ],
)
async def test_activity_database_hints_map_to_stable_safe_codes(service, hint, expected_code):
    svc, db = service
    svc.actor.role = "clinician"
    private = "private database detail"
    db.rpc.return_value.execute.side_effect = APIError(
        {"code": "22023", "message": private, "details": private, "hint": hint}
    )
    with pytest.raises(ValidationError) as error:
        await svc.review_activity(uuid4(), uuid4())
    assert error.value.code == expected_code
    assert private not in str(error.value)


@pytest.mark.asyncio
async def test_invalid_attached_send_is_not_misreported_as_missing_activity(service):
    svc, db = service
    db.rpc.return_value.execute.side_effect = APIError(
        {"code": "22023", "message": "private detail", "details": None, "hint": None}
    )
    with pytest.raises(ValidationError) as error:
        await svc.send(
            uuid4(),
            ConversationSend(
                body="Synthetic question",
                client_message_id=uuid4(),
                care_plan_item_id=uuid4(),
            ),
        )
    assert error.value.code == "INVALID_CONVERSATION_REQUEST"
