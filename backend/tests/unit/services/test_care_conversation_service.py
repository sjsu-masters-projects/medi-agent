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
    fake.get_translations_for_messages.return_value = {
        "m-0": {"translated_text": "stored", "guard_passed": True}
    }
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
    fake.get_translations_for_messages.return_value = {}
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
