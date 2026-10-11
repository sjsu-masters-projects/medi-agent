"""Recipient identity comes from authentication, never a browser-supplied ID."""

from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser
from app.routers.care_conversations import conversation_actor


@pytest.fixture
def email_actor():
    actor = CurrentUser(id=uuid4(), email="demo@example.com", role="patient")
    db = MagicMock()
    db.rpc.return_value.execute.return_value = Mock(
        data={
            "email": "demo@example.com",
            "verified": False,
            "synthetic": False,
            "preferences": {},
        }
    )
    app.dependency_overrides[conversation_actor] = lambda: actor
    app.dependency_overrides[get_db] = lambda: db
    yield actor, db
    app.dependency_overrides.clear()


def test_preferences_require_authentication(client):
    assert client.get("/api/v1/email/preferences").status_code == 401


def test_preferences_use_authenticated_account_and_no_store(client, email_actor):
    actor, db = email_actor
    response = client.get("/api/v1/email/preferences")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert not response.json()["verified"]
    assert db.rpc.call_args.args[1]["p_actor_id"] == str(actor.id)
    assert db.rpc.call_args.args[1]["p_role"] == "patient"


@pytest.mark.parametrize(
    "payload",
    [
        {"messages": "true"},
        {"messages": True, "recipient_id": "someone"},
        {"action_url": "https://outside.example.com"},
    ],
)
def test_preferences_reject_coercion_and_arbitrary_targets(client, email_actor, payload):
    assert client.put("/api/v1/email/preferences", json=payload).status_code == 422
    email_actor[1].rpc.assert_not_called()


def test_verification_is_scoped_to_actor(client, email_actor):
    actor, db = email_actor
    db.rpc.return_value.execute.return_value = Mock(data={"verified": False})
    assert client.post("/api/v1/email/verify", json={"code": "123456"}).json() == {
        "verified": False
    }
    params = db.rpc.call_args.args[1]
    assert params["p_actor_id"] == str(actor.id)
    assert params["p_payload"]["hash"] != "123456"


def test_verification_rejects_extra_recipient(client, email_actor):
    assert (
        client.post(
            "/api/v1/email/verify", json={"code": "123456", "email": "other@example.com"}
        ).status_code
        == 422
    )
    email_actor[1].rpc.assert_not_called()
