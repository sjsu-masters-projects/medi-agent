"""Calendar export exercises the real service and authorization against a stub DB."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser


@pytest.fixture
def calendar():
    actor = CurrentUser(id=uuid4(), email="synthetic@example.com", role="patient")
    row = {
        "id": str(uuid4()),
        "patient_id": str(actor.id),
        "care_team_id": str(uuid4()),
        "scheduled_at": "2026-10-06T16:00:00Z",
        "duration_minutes": 30,
        "appointment_type": "follow_up",
        "status": "confirmed",
        "created_at": "2026-10-03T00:00:00Z",
        "location": "Synthetic clinic, Suite 2",
        "reason": "Private clinical reason",
        "notes": "Private clinician notes",
        "patient_note": "Private patient notes",
    }
    db = MagicMock()
    chain = MagicMock()
    for method in ("select", "eq", "limit"):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = SimpleNamespace(data=[row])
    db.table.return_value = chain
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_db] = lambda: db
    yield actor, row, db, chain
    app.dependency_overrides.clear()


def endpoint(row):
    return f"/api/v1/appointments/{row['id']}/calendar"


@pytest.mark.parametrize("status", ["confirmed", "scheduled"])
@pytest.mark.parametrize(
    "locale,title", [("en-US", "MediAgent appointment"), ("es-MX", "Cita de MediAgent")]
)
def test_export_booked_visit(client, calendar, status, locale, title):
    _, row, db, _ = calendar
    row["status"] = status
    response = client.get(endpoint(row), params={"locale": locale})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    data = response.json()
    assert data["filename"] == f"appointment-{row['id']}.ics"
    content = data["content"].replace("\r\n ", "")
    assert f"SUMMARY;LANGUAGE={locale}:{title}\r\n" in content
    assert "DTSTART:20261006T160000Z\r\nDTEND:20261006T163000Z" in content
    assert "LOCATION:Synthetic clinic\\, Suite 2" in content
    assert all(row[key] not in content for key in ("reason", "notes", "patient_note", "patient_id"))
    assert "ATTENDEE" not in content and "VALARM" not in content
    db.rpc.assert_not_called()
    db.table.return_value.update.assert_not_called()


@pytest.mark.parametrize(
    "status",
    [
        "proposed",
        "expired",
        "cancelled",
        "withdrawn",
        "declined",
        "completed",
        "no_show",
        "alternative_requested",
    ],
)
def test_current_status_checked_before_each_export(client, calendar, status):
    _, row, _, _ = calendar
    assert client.get(endpoint(row)).status_code == 200
    row["status"] = status
    response = client.get(endpoint(row))
    assert response.status_code == 422
    assert "APPOINTMENT_UNAVAILABLE" in response.text
    assert "BEGIN:VCALENDAR" not in response.text


def test_other_patient_denied(client, calendar):
    actor, row, _, _ = calendar
    actor.id = uuid4()
    assert client.get(endpoint(row)).status_code == 403


@pytest.mark.parametrize("assigned", [True, False])
def test_clinician_requires_current_active_assignment(client, calendar, assigned):
    actor, row, _, chain = calendar
    actor.role = "clinician"
    chain.execute.side_effect = [
        SimpleNamespace(data=[row]),
        SimpleNamespace(data=[{"id": "assignment"}] if assigned else []),
    ]
    response = client.get(endpoint(row))
    assert response.status_code == (200 if assigned else 403)
    assert ("status", "active") in [call.args for call in chain.eq.call_args_list]


def test_unauthenticated_export_denied(client, calendar):
    _, row, _, _ = calendar
    app.dependency_overrides.pop(get_current_user)
    assert client.get(endpoint(row)).status_code in (401, 403)


def test_missing_and_invalid_requests(client, calendar):
    _, row, _, chain = calendar
    assert client.get(endpoint(row), params={"locale": "fr-FR"}).status_code == 422
    assert client.get("/api/v1/appointments/not-a-uuid/calendar").status_code == 422
    chain.execute.return_value = SimpleNamespace(data=[])
    assert client.get(endpoint(row)).status_code == 404
