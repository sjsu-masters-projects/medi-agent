"""API shape, validation, auth and safe errors against the real service RPC boundary."""

from copy import deepcopy
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
from app.services.clinic_link_scope import ClinicLinkScope
from app.services.clinic_membership_service import ClinicMembershipService

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
        # LOC-003: optional stored-translation metadata, null when no translation exists.
        "translation": None,
        "translation_locale": None,
        "translation_guard_passed": None,
        "translation_pending": False,
        "activity_context": None,
    }
    db = MagicMock()
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=thread)
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_db] = lambda: db
    yield actor, thread, message, db
    app.dependency_overrides.clear()


@pytest.mark.parametrize("role", ["patient", "clinician"])
def test_all_six_contract_endpoints(client, conversation, role, monkeypatch):
    actor, thread, message, db = conversation
    clinic = "00000000-0000-0000-0000-0000000000c1"
    actor.role = role
    message["sender_role"] = role
    recipient = {
        "id": str(uuid4()),
        "name": "Synthetic recipient",
        "role": "provider",
        "clinic_name": "Synthetic clinic",
    }
    # A clinician's lists are tagged with the clinic of their link (slice C); a patient's
    # carry no clinic id.
    scope = ClinicLinkScope(
        {
            recipient["id"]: (clinic, "Synthetic clinic"),
            thread["patient_id"]: (clinic, "Synthetic clinic"),
        }
    )
    monkeypatch.setattr(ClinicMembershipService, "link_scope", AsyncMock(return_value=scope))
    tagged = clinic if role == "clinician" else None
    cases = [
        ("GET", ROOT + "/recipients", None, [recipient], [{**recipient, "clinic_id": tagged}]),
        ("GET", ROOT + "/", None, [thread], [{**thread, "clinic_id": tagged}]),
        (
            "POST",
            ROOT + "/",
            {"recipient_id": recipient["id"]},
            thread,
            {**thread, "clinic_id": None},
        ),
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
    for method, path, payload, result, *expected in cases:
        db.rpc.return_value.execute.return_value.data = deepcopy(result)
        response = client.request(method, path, json=payload)
        assert response.status_code == 200, response.text
        assert response.json() == (expected[0] if expected else result)
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


def test_activity_attachment_uses_authenticated_atomic_rpc(client, conversation):
    actor, thread, message, db = conversation
    item = str(uuid4())
    db.rpc.return_value.execute.return_value.data = message
    response = client.post(
        ROOT + f"/{thread['id']}/messages",
        json={
            "body": "Question about approved frequency",
            "client_message_id": str(uuid4()),
            "care_plan_item_id": item,
        },
    )
    assert response.status_code == 200
    name, payload = db.rpc.call_args.args
    assert name == "care_conversation_activity_operation"
    assert payload["p_actor_id"] == str(actor.id)
    assert payload["p_payload"]["care_plan_item_id"] == item


def test_patient_cannot_open_activity_review(client, conversation):
    _, thread, _, db = conversation
    response = client.post(ROOT + f"/{thread['id']}/messages/{uuid4()}/activity-review")
    assert response.status_code == 403
    db.rpc.assert_not_called()


def test_clinician_review_routes_only_to_authorized_rpc(client, conversation):
    actor, thread, message, db = conversation
    actor.role = "clinician"
    result = {"patient_id": thread["patient_id"], "plan_id": str(uuid4()), "item_id": str(uuid4())}
    db.rpc.return_value.execute.return_value.data = result
    response = client.post(ROOT + f"/{thread['id']}/messages/{message['id']}/activity-review")
    assert response.status_code == 200
    assert response.json() == result
    name, payload = db.rpc.call_args.args
    assert name == "care_conversation_activity_operation"
    assert payload["p_action"] == "review"
    assert payload["p_payload"] == {"conversation_id": thread["id"], "message_id": message["id"]}


@pytest.mark.parametrize(
    "hint,expected_code",
    [
        ("activity_context_unavailable", "ACTIVITY_CONTEXT_UNAVAILABLE"),
        ("activity_context_stale", "ACTIVITY_CONTEXT_STALE"),
        ("care_plan_draft_exists", "CARE_PLAN_DRAFT_EXISTS"),
    ],
)
def test_activity_review_returns_stable_safe_error_codes(
    client, conversation, hint, expected_code
):
    actor, thread, message, db = conversation
    actor.role = "clinician"
    db.rpc.return_value.execute.side_effect = APIError(
        {"code": "22023", "message": "private record", "details": "private record", "hint": hint}
    )
    response = client.post(ROOT + f"/{thread['id']}/messages/{message['id']}/activity-review")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == expected_code
    assert "private record" not in response.text


def test_invalid_attached_send_has_its_own_stable_error(client, conversation):
    _, thread, _, db = conversation
    db.rpc.return_value.execute.side_effect = APIError(
        {"code": "22023", "message": "private record", "details": None, "hint": None}
    )
    response = client.post(
        ROOT + f"/{thread['id']}/messages",
        json={
            "body": "Synthetic question",
            "client_message_id": str(uuid4()),
            "care_plan_item_id": str(uuid4()),
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_CONVERSATION_REQUEST"


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


def test_translation_endpoint_refuses_an_outsider_without_a_model_call(
    client, conversation, monkeypatch
):
    from unittest.mock import AsyncMock

    from postgrest.exceptions import APIError

    _, thread, message, db = conversation
    db.rpc.return_value.execute.side_effect = APIError(
        {"code": "42501", "message": "denied", "details": "", "hint": ""}
    )
    model = AsyncMock()
    monkeypatch.setattr("app.services.message_translation.translate_message", model)
    response = client.post(
        f"/api/v1/care-conversations/{thread['id']}/messages/{message['id']}/translation"
    )
    assert response.status_code in {403, 404}
    model.assert_not_awaited()
