"""Legacy appointment updates cannot bypass the audited response workflow."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser


@pytest.fixture
def appointment_update():
    actor = CurrentUser(id=uuid4(), email="synthetic@example.com", role="patient")
    row = {
        "id": str(uuid4()),
        "patient_id": str(actor.id),
        "care_team_id": str(uuid4()),
        "scheduled_at": "2099-10-06T16:00:00Z",
        "duration_minutes": 30,
        "appointment_type": "follow_up",
        "status": "proposed",
        "proposal_group_id": None,
        "created_at": "2026-10-06T00:00:00Z",
    }
    db, chain = MagicMock(), MagicMock()
    for method in ("select", "eq", "limit", "update"):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = SimpleNamespace(data=[row])
    db.table.return_value = chain
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_db] = lambda: db
    yield actor, row, db, chain
    app.dependency_overrides.clear()


@pytest.mark.parametrize("prior_status", ["proposed", "declined", "cancelled", "completed"])
def test_patient_cannot_book_or_reopen_standalone_visit_through_put(
    client, appointment_update, prior_status
):
    _, row, db, chain = appointment_update
    row["status"] = prior_status
    response = client.put(
        f"/api/v1/appointments/{row['id']}",
        json={"status": "confirmed", "scheduled_at": "2099-10-07T16:00:00Z"},
    )
    assert response.status_code == 403
    chain.update.assert_not_called()
    db.rpc.assert_not_called()
    assert row["status"] == prior_status


@pytest.mark.parametrize(
    "payload",
    [
        {"scheduled_at": "2099-10-07T16:00:00Z"},
        {"duration_minutes": 60},
        {"location": "Different clinic"},
    ],
)
def test_patient_cannot_change_booked_visit_details(client, appointment_update, payload):
    _, row, _, chain = appointment_update
    row["status"] = "confirmed"
    assert client.put(f"/api/v1/appointments/{row['id']}", json=payload).status_code == 403
    chain.update.assert_not_called()


@pytest.mark.parametrize("new_status", ["confirmed", "scheduled", "cancelled", "completed"])
def test_clinician_generic_put_cannot_change_standalone_lifecycle(
    client, appointment_update, new_status
):
    actor, row, db, chain = appointment_update
    actor.role = "clinician"
    actor.id = uuid4()
    chain.execute.side_effect = [
        SimpleNamespace(data=[row]),
        SimpleNamespace(data=[{"id": row["care_team_id"]}]),
    ]
    response = client.put(f"/api/v1/appointments/{row['id']}", json={"status": new_status})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "APPOINTMENT_UNAVAILABLE"
    chain.update.assert_not_called()
    db.rpc.assert_not_called()


def test_assigned_clinician_can_still_edit_standalone_metadata(client, appointment_update):
    actor, row, _, chain = appointment_update
    actor.role = "clinician"
    actor.id = uuid4()
    changed = {**row, "location": "Synthetic clinic, Suite 3"}
    chain.execute.side_effect = [
        SimpleNamespace(data=[row]),
        SimpleNamespace(data=[{"id": row["care_team_id"]}]),
        SimpleNamespace(data=[changed]),
    ]
    response = client.put(
        f"/api/v1/appointments/{row['id']}", json={"location": changed["location"]}
    )
    assert response.status_code == 200
    assert response.json()["location"] == changed["location"]
    chain.update.assert_called_once_with({"location": changed["location"]})


@pytest.mark.parametrize(
    "action,new_status",
    [("accept", "confirmed"), ("decline", "declined"), ("cancel", "cancelled")],
)
def test_standalone_response_still_uses_atomic_audited_rpc(
    client, appointment_update, action, new_status
):
    actor, row, db, chain = appointment_update
    db.rpc.return_value.execute.return_value = SimpleNamespace(
        data={"appointment": {**row, "status": new_status}}
    )
    response = client.post(f"/api/v1/appointments/{row['id']}/respond", json={"action": action})
    assert response.status_code == 200
    assert response.json()["status"] == new_status
    db.rpc.assert_called_once_with(
        "respond_to_appointment_offer",
        {
            "p_actor_id": str(actor.id),
            "p_appointment_id": row["id"],
            "p_action": action,
            "p_note": None,
        },
    )
    chain.update.assert_not_called()
