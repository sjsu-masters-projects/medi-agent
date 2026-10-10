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
