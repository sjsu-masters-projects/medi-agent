"""Recipient identity comes from authentication, never a browser-supplied ID."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser
from app.routers.care_conversations import conversation_actor


@pytest.fixture
def email_actor():
    actor = CurrentUser(id=uuid4(), email="demo@example.com", role="patient")
    db = MagicMock()
    db.auth.admin.get_user_by_id.return_value = SimpleNamespace(
        user=SimpleNamespace(email="Demo@Example.com")
    )
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
    # The address is read from Auth by the backend, never from the browser.
    assert db.rpc.call_args.args[1]["p_payload"]["account_email"] == "demo@example.com"
    assert response.json()["available"] is True


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


TOKEN = "t" * 43


@pytest.fixture
def invitation_db():
    db = MagicMock()
    db.auth.admin.get_user_by_id.return_value = SimpleNamespace(
        user=SimpleNamespace(email="invitee@example.com")
    )
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.clear()


def as_user(role):
    user = CurrentUser(id=uuid4(), email="invitee@example.com", role=role, aal="aal2")
    app.dependency_overrides[get_current_user] = lambda: user
    return user


def test_preview_is_unauthenticated_no_store_and_omits_clinic_code(client, invitation_db):
    invitation_db.rpc.return_value.execute.return_value = Mock(
        data={"email": "invitee@example.com", "role": "nurse", "clinic_name": "Clinic"}
    )
    response = client.post("/api/v1/email/invitations/preview", json={"token": TOKEN})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert "clinic_code" not in response.json()
    params = invitation_db.rpc.call_args.args[1]
    assert params["p_actor"] is None and params["p_payload"]["hash"] != TOKEN


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/api/v1/email/invitations", None),
        ("post", f"/api/v1/email/invitations/{uuid4()}/revoke", {}),
        ("post", "/api/v1/email/invitations/accept", {"token": TOKEN}),
    ],
)
def test_patients_cannot_manage_or_accept_invitations(client, invitation_db, method, path, body):
    as_user("patient")
    response = getattr(client, method)(path, **({"json": body} if body is not None else {}))
    assert response.status_code == 403
    invitation_db.rpc.assert_not_called()


def test_clinician_accept_uses_auth_address_and_returns_clinic(client, invitation_db):
    user = as_user("clinician")
    invitation_db.rpc.return_value.execute.return_value = Mock(
        data={
            "status": "accepted",
            "clinic_id": str(uuid4()),
            "clinic_code": "ABC123",
            "clinic_name": "Synthetic Clinic",
            "clinic_status": "active",
        }
    )
    response = client.post("/api/v1/email/invitations/accept", json={"token": TOKEN})
    assert response.status_code == 200
    assert response.json()["clinic"]["clinic_code"] == "ABC123"
    params = invitation_db.rpc.call_args.args[1]
    assert params["p_actor"] == str(user.id)
    assert params["p_payload"]["account_email"] == "invitee@example.com"


def test_clinician_history_is_private(client, invitation_db):
    as_user("clinician")
    invitation_db.rpc.return_value.execute.return_value = Mock(data={"items": []})
    response = client.get("/api/v1/email/invitations")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"


def test_missing_email_schema_is_503(client, invitation_db):
    from postgrest.exceptions import APIError

    as_user("clinician")
    invitation_db.rpc.return_value.execute.side_effect = APIError(
        {"code": "PGRST202", "message": "missing", "hint": None, "details": None}
    )
    response = client.get("/api/v1/email/invitations")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EMAIL_SETUP_PENDING"
