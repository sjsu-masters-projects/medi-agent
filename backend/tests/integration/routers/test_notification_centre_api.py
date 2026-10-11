"""HTTP contract and signed-view isolation against the real notification service."""

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
from app.services.notification_centre_tokens import issue_token

ROOT = "/api/v1/notification-centre"


@pytest.fixture
def centre():
    actor = CurrentUser(id=uuid4(), email="synthetic@example.com", role="patient", aal="aal2")
    row = {
        "id": str(uuid4()),
        "event_type": "message_received",
        "category": "messages",
        "source_id": str(uuid4()),
        "patient_id": str(actor.id),
        "metadata": {},
        "actor_name": "Dr. Synthetic Reviewer",
        "patient_name": "Synthetic Patient",
        "clinic_name": "Synthetic clinic",
        "created_at": "2026-10-11T12:00:00Z",
        "is_read": False,
        "actionable": True,
        "can_acknowledge": False,
    }
    db = MagicMock()
    db.rpc.return_value.execute.return_value = SimpleNamespace(
        data={"items": [row], "read_ids": [row["id"]], "next_cursor": None}
    )
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_db] = lambda: db
    yield actor, row, db
    app.dependency_overrides.clear()


@pytest.mark.parametrize("role", ["patient", "clinician"])
def test_list_is_scoped_no_store_and_only_safe_display_fields(client, centre, role):
    actor, row, db = centre
    actor.role = role
    response = client.get(ROOT + "?locale=es-MX")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    item = response.json()["items"][0]
    assert item["title"] == (
        "Nuevo mensaje de Dr. Synthetic Reviewer"
        if role == "patient"
        else "New message from Synthetic Patient"
    )
    assert row["source_id"] not in item["body"]
    assert "metadata" not in item and "patient_id" not in item
    assert db.rpc.call_args.args[1]["p_actor_id"] == str(actor.id)
    assert db.rpc.call_args.args[1]["p_actor_role"] == role


def test_snapshot_marks_only_receipts_in_the_issued_view(client, centre):
    _, row, db = centre
    token = client.get(ROOT).json()["read_through"]
    db.rpc.return_value.execute.return_value.data = {"updated_count": 0, "skipped_count": 1}
    response = client.post(ROOT + "/read-through", json={"read_through": token})
    assert response.status_code == 200
    # A receipt that is no longer visible is skipped, not a failure for the whole view.
    assert response.json() == {"updated_count": 0, "skipped_count": 1}
    assert db.rpc.call_args.args[1]["p_action"] == "read_through"
    assert db.rpc.call_args.args[1]["p_payload"] == {"ids": [row["id"]]}


def test_read_through_with_an_unexpected_result_is_unavailable_not_a_crash(client, centre):
    _, _, db = centre
    token = client.get(ROOT).json()["read_through"]
    db.rpc.return_value.execute.return_value.data = {"updated": 1}
    response = client.post(ROOT + "/read-through", json={"read_through": token})
    assert response.status_code == 502
    assert "updated" not in response.text


@pytest.mark.parametrize("purpose", ["read", "cursor"])
def test_snapshot_cannot_be_used_by_another_actor(client, centre, purpose):
    actor, _, db = centre
    token = issue_token(actor, purpose, [])
    actor.id = uuid4()
    response = (
        client.post(ROOT + "/read-through", json={"read_through": token})
        if purpose == "read"
        else client.get(ROOT + "?cursor=" + token)
    )
    assert response.status_code == 422
    db.rpc.assert_not_called()


def test_snapshot_purpose_and_role_are_bound(client, centre):
    actor, _, db = centre
    wrong_purpose = issue_token(actor, "cursor", [])
    assert (
        client.post(ROOT + "/read-through", json={"read_through": wrong_purpose}).status_code == 422
    )
    token = issue_token(actor, "read", [])
    actor.role = "clinician"
    assert client.post(ROOT + "/read-through", json={"read_through": token}).status_code == 422
    db.rpc.assert_not_called()


def test_pagination_uses_signed_server_cursor(client, centre):
    _, row, db = centre
    before = {"created_at": row["created_at"], "id": row["id"]}
    db.rpc.return_value.execute.return_value.data["next_cursor"] = before
    cursor = client.get(ROOT).json()["next_cursor"]
    assert client.get(ROOT + "?cursor=" + cursor).status_code == 200
    assert db.rpc.call_args.args[1]["p_payload"]["before"] == before


def test_summary_and_idempotent_single_read(client, centre):
    _, row, db = centre
    db.rpc.return_value.execute.return_value.data = {"unread_count": 2, "action_item_count": 0}
    assert client.get(ROOT + "/summary").json() == {"unread_count": 2, "action_item_count": 0}
    db.rpc.return_value.execute.return_value.data = {"updated": 1}
    for _ in range(2):
        assert client.put(ROOT + f"/{row['id']}/read").status_code == 200
    assert db.rpc.call_args.args[1]["p_payload"] == {"id": row["id"]}


def test_patient_cannot_get_or_acknowledge_clinician_work(client, centre):
    _, row, db = centre
    assert client.get(ROOT + "/action-items").status_code == 403
    assert client.post(ROOT + f"/action-items/{row['id']}/acknowledge", json={}).status_code == 403
    db.rpc.assert_not_called()


def test_clinician_work_and_acknowledgment_use_separate_operations(client, centre):
    actor, row, db = centre
    actor.role = "clinician"
    assert client.get(ROOT + "/action-items?category=safety").status_code == 200
    assert db.rpc.call_args.args[1]["p_action"] == "action_items"
    assert db.rpc.call_args.args[1]["p_payload"] == {"category": "safety", "limit": 50}
    db.rpc.return_value.execute.return_value.data = {"acknowledged": True}
    assert (
        client.post(
            ROOT + f"/action-items/{row['id']}/acknowledge", json={"note": "Seen for follow-up"}
        ).status_code
        == 200
    )
    assert db.rpc.call_args.args[1]["p_action"] == "acknowledge"
    assert db.rpc.call_args.args[1]["p_payload"]["note"] == "Seen for follow-up"


@pytest.mark.parametrize(
    "path",
    ["?limit=0", "?limit=101", "?locale=fr", "?cursor=bad", "/action-items?category=invalid"],
)
def test_invalid_requests_rejected_before_rpc(client, centre, path):
    _, _, db = centre
    assert client.get(ROOT + path).status_code == 422
    db.rpc.assert_not_called()


@pytest.mark.parametrize(
    "code,status", [("42501", 403), ("P0002", 403), ("22023", 422), ("PGRST202", 502)]
)
def test_database_errors_do_not_leak_private_details(client, centre, code, status):
    _, _, db = centre
    db.rpc.return_value.execute.side_effect = APIError(
        {"code": code, "message": "Private patient name and SQL"}
    )
    response = client.get(ROOT)
    assert response.status_code == status
    assert "Private patient name" not in response.text


def test_unknown_role_and_unauthenticated_requests(client, centre):
    actor, _, db = centre
    actor.role = "unknown"
    assert client.get(ROOT).status_code == 403
    app.dependency_overrides.pop(get_current_user)
    assert client.get(ROOT).status_code == 401
    db.rpc.assert_not_called()


def test_clinician_mfa_guard_is_retained(client, centre, monkeypatch):
    actor, _, db = centre
    actor.role, actor.aal = "clinician", "aal1"
    monkeypatch.setattr(security, "_has_verified_mfa_factor", AsyncMock(return_value=True))
    assert client.get(ROOT, headers={"Authorization": "Bearer synthetic"}).status_code == 403
    db.rpc.assert_not_called()


def test_acknowledgment_cannot_inject_actor_or_clinical_action(client, centre):
    actor, row, db = centre
    actor.role = "clinician"
    for payload in [{"note": "x" * 1001}, {"actor_id": str(uuid4())}, {"approve": True}]:
        assert (
            client.post(ROOT + f"/action-items/{row['id']}/acknowledge", json=payload).status_code
            == 422
        )
    db.rpc.assert_not_called()
