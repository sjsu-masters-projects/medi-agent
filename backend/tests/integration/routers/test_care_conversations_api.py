"""API shape, validation, auth and safe errors against the real service RPC boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from app.core import security
from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser

ROOT = "/api/v1/care-conversations"


@pytest.fixture
def conversation():
    actor = CurrentUser(id=uuid4(), email="synthetic@example.com", role="patient", aal="aal2")
    thread = {
        "id": str(uuid4()),
        "patient_id": str(actor.id),
        "clinician_id": str(uuid4()),
        "patient_name": "Synthetic Patient",
        "clinician_name": "Synthetic Clinician",
        "clinic_name": "Synthetic clinic",
        "last_message_at": None,
        "last_message_preview": None,
        "unread_count": 0,
        "writable": True,
    }
    message = {
        "id": str(uuid4()),
        "conversation_id": thread["id"],
        "sender_id": str(actor.id),
        "sender_role": "patient",
        "sender_name": "Synthetic Patient",
        "body": "Synthetic message",
        "created_at": "2026-10-09T12:00:00Z",
    }
    db = MagicMock()
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=thread)
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_db] = lambda: db
    yield actor, thread, message, db
    app.dependency_overrides.clear()


@pytest.mark.parametrize("role", ["patient", "clinician"])
def test_all_six_contract_endpoints(client, conversation, role):
    actor, thread, message, db = conversation
    actor.role = role
    message["sender_role"] = role
    recipient = {
        "id": str(uuid4()),
        "name": "Synthetic recipient",
        "role": "provider",
        "clinic_name": "Synthetic clinic",
    }
    cases = [
        ("GET", ROOT + "/recipients", None, [recipient]),
        ("GET", ROOT + "/", None, [thread]),
        ("POST", ROOT + "/", {"recipient_id": recipient["id"]}, thread),
        (
            "GET",
            ROOT + f"/{thread['id']}/messages",
            None,
            {"items": [message], "next_cursor": None},
        ),
        (
            "POST",
            ROOT + f"/{thread['id']}/messages",
            {"body": message["body"], "client_message_id": str(uuid4())},
            message,
        ),
        (
            "POST",
            ROOT + f"/{thread['id']}/read",
            {"last_message_id": message["id"]},
            {"read_at": message["created_at"]},
        ),
    ]
    for method, path, payload, result in cases:
        db.rpc.return_value.execute.return_value.data = result
        response = client.request(method, path, json=payload)
        assert response.status_code == 200, response.text
        assert response.json() == result
        assert response.headers["cache-control"] == "private, no-store"
        assert db.rpc.call_args.args[1]["p_actor_id"] == str(actor.id)
        assert db.rpc.call_args.args[1]["p_actor_role"] == role


@pytest.mark.parametrize(
    "payload",
    [
        {"body": " \n\t", "client_message_id": str(uuid4())},
        {"body": "x" * 4001, "client_message_id": str(uuid4())},
        {"body": "hello", "client_message_id": "not-uuid"},
        {"body": "hello"},
        {"body": "hello", "client_message_id": str(uuid4()), "sender_id": str(uuid4())},
        {"body": "hello", "client_message_id": str(uuid4()), "sender_role": "clinician"},
        {"body": "hello", "client_message_id": str(uuid4()), "sender_name": "Impersonation"},
    ],
)
def test_invalid_or_impersonated_send_rejected_before_database(client, conversation, payload):
    _, thread, _, db = conversation
    assert client.post(ROOT + f"/{thread['id']}/messages", json=payload).status_code == 422
    db.rpc.assert_not_called()


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "before=not-uuid"])
def test_invalid_pagination(client, conversation, query):
    _, thread, _, db = conversation
    assert client.get(ROOT + f"/{thread['id']}/messages?{query}").status_code == 422
    db.rpc.assert_not_called()


def test_valid_page_and_trimmed_send(client, conversation):
    _, thread, message, db = conversation
    db.rpc.return_value.execute.return_value.data = {"items": [], "next_cursor": None}
    assert (
        client.get(ROOT + f"/{thread['id']}/messages?before={message['id']}&limit=100").status_code
        == 200
    )
    assert db.rpc.call_args.args[1]["p_payload"] == {
        "conversation_id": thread["id"],
        "before": message["id"],
        "limit": 100,
    }
    db.rpc.return_value.execute.return_value.data = message
    assert (
        client.post(
            ROOT + f"/{thread['id']}/messages",
            json={"body": " \nSynthetic message\t", "client_message_id": str(uuid4())},
        ).status_code
        == 200
    )
    assert db.rpc.call_args.args[1]["p_payload"]["body"] == "Synthetic message"


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/recipients"),
        ("GET", "/"),
        ("POST", "/"),
        ("GET", "/{id}/messages"),
        ("POST", "/{id}/messages"),
        ("POST", "/{id}/read"),
    ],
)
def test_denial_is_neutral_on_every_endpoint(client, conversation, method, path):
    _, thread, _, db = conversation
    db.rpc.return_value.execute.side_effect = APIError(
        {"code": "42501", "message": "Private patient name"}
    )
    payload = (
        {"recipient_id": str(uuid4())}
        if path == "/"
        else (
            {"last_message_id": str(uuid4())}
            if path.endswith("read")
            else {"body": "synthetic", "client_message_id": str(uuid4())}
        )
    )
    response = client.request(
        method, ROOT + path.format(id=thread["id"]), json=payload if method == "POST" else None
    )
    assert response.status_code == 403
    assert response.json()["error"]["message"] == "Conversation unavailable"
    assert "Private patient name" not in response.text


def test_unauthenticated_and_unknown_role(client, conversation):
    actor, _, _, db = conversation
    actor.role = "unknown"
    assert client.get(ROOT + "/recipients").status_code == 403
    app.dependency_overrides.pop(get_current_user)
    assert client.get(ROOT + "/recipients").status_code == 401
    db.rpc.assert_not_called()


def test_clinician_keeps_existing_mfa_guard(client, conversation, monkeypatch):
    actor, _, _, db = conversation
    actor.role, actor.aal = "clinician", "aal1"
    monkeypatch.setattr(security, "_has_verified_mfa_factor", AsyncMock(return_value=True))
    assert (
        client.get(ROOT + "/recipients", headers={"Authorization": "Bearer synthetic"}).status_code
        == 403
    )
    db.rpc.assert_not_called()
