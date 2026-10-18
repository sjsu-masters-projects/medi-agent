"""My schedule and busy-times routes (UX-006)."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser

WINDOW = "from=2099-10-17T00:00:00Z&to=2099-10-18T00:00:00Z"


@pytest.fixture
def caller():
    def build(role: str):
        actor = CurrentUser(id=uuid4(), email="synthetic@example.com", role=role)
        db, chain = MagicMock(), MagicMock()
        for method in ("select", "eq", "in_", "gte", "lt", "order", "limit"):
            getattr(chain, method).return_value = chain
        chain.execute.return_value = SimpleNamespace(data=[])
        db.table.return_value = chain
        db.rpc.return_value.execute.return_value = SimpleNamespace(data={"expired_count": 0})
        app.dependency_overrides[get_current_user] = lambda: actor
        app.dependency_overrides[get_db] = lambda: db
        return actor, chain

    yield build
    app.dependency_overrides.clear()


def test_clinician_reads_an_empty_schedule(client, caller):
    caller("clinician")
    response = client.get(f"/api/v1/appointments/schedule?{WINDOW}")
    assert response.status_code == 200
    assert response.json() == {"visits": [], "needs_action": [], "next_visit": None}


def test_schedule_is_scoped_to_the_callers_own_visits(client, caller):
    actor, chain = caller("clinician")
    client.get(f"/api/v1/appointments/schedule?{WINDOW}")
    chain.eq.assert_any_call("clinician_id", str(actor.id))


@pytest.mark.parametrize("path", ["schedule", "busy"])
def test_patients_have_no_clinician_schedule(client, caller, path):
    caller("patient")
    assert client.get(f"/api/v1/appointments/{path}?{WINDOW}").status_code == 403


def test_busy_times_route_returns_no_patient_fields(client, caller):
    _, chain = caller("clinician")
    chain.execute.return_value = SimpleNamespace(
        data=[
            {
                "scheduled_at": "2099-10-17T16:00:00Z",
                "duration_minutes": 30,
                "clinic_id": str(uuid4()),
                "clinics": {"display_name": "Cedar Grove"},
            }
        ]
    )
    response = client.get(f"/api/v1/appointments/busy?{WINDOW}")
    assert response.status_code == 200
    assert set(response.json()[0]) == {"starts_at", "ends_at", "clinic_id", "clinic_name"}


def test_range_must_be_bounded(client, caller):
    caller("clinician")
    assert (
        client.get(
            "/api/v1/appointments/busy?from=2099-10-17T00:00:00Z&to=2099-12-30T00:00:00Z"
        ).status_code
        == 422
    )
