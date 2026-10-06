"""HTTP contract and authorization for grouped appointment proposals."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser


def _mock_db_dependency():
    return MagicMock()


@pytest.fixture(autouse=True)
def proposal_dependencies():
    actor = CurrentUser(id=uuid4(), email="synthetic@example.com", role="clinician")
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_db] = _mock_db_dependency
    yield actor
    app.dependency_overrides.clear()


def body():
    return {"care_team_id": str(uuid4()), "slots": ["2099-10-01T10:00:00Z", "2099-10-02T10:00:00Z"]}


def test_proposal_returns_grouped_slots(client, monkeypatch, proposal_dependencies):
    request = body()
    group = str(uuid4())
    rows = [
        {
            "id": str(uuid4()),
            "patient_id": str(uuid4()),
            "care_team_id": request["care_team_id"],
            "scheduled_at": slot,
            "status": "proposed",
            "appointment_type": "follow_up",
            "proposal_group_id": group,
            "created_at": "2026-09-26T00:00:00Z",
        }
        for slot in request["slots"]
    ]
    propose = AsyncMock(return_value=rows)
    monkeypatch.setattr("app.routers.appointments.AppointmentService.propose_for_user", propose)
    response = client.post("/api/v1/appointments/propose", json=request)
    assert response.status_code == 201, response.text
    assert len(response.json()) == 2
    assert {row["proposal_group_id"] for row in response.json()} == {group}
    assert propose.call_args.kwargs["user_id"] == proposal_dependencies.id


@pytest.mark.parametrize(
    "slots",
    [
        ["2099-10-01T10:00:00Z"],
        [f"2099-10-0{day}T10:00:00Z" for day in range(1, 6)],
        ["2099-10-01T10:00:00", "2099-10-02T10:00:00Z"],
        ["2099-10-01T10:00:00Z", "2099-10-01T12:00:00+02:00"],
        ["bad", "2099-10-02T10:00:00Z"],
    ],
)
def test_invalid_slot_sets_rejected_before_service(client, monkeypatch, slots):
    propose = AsyncMock()
    monkeypatch.setattr("app.routers.appointments.AppointmentService.propose_for_user", propose)
    request = body()
    request["slots"] = slots
    assert client.post("/api/v1/appointments/propose", json=request).status_code == 422
    propose.assert_not_called()


def test_patient_cannot_create_offer(client):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=uuid4(), email="synthetic@example.com", role="patient"
    )
    assert client.post("/api/v1/appointments/propose", json=body()).status_code == 403
