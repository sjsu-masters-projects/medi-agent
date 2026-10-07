"""Integration tests for the appointment respond endpoint (SCH-001, Slice 1)."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import status

from app.core.exceptions import ValidationError
from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser


def _mock_db_dependency():
    return MagicMock()


def _confirmed_appointment(appointment_id, patient_id, care_team_id, new_status):
    return {
        "id": str(appointment_id),
        "patient_id": str(patient_id),
        "care_team_id": str(care_team_id),
        "clinician_name": "Elena Park",
        "scheduled_at": "2026-05-08T17:00:00Z",
        "duration_minutes": 30,
        "appointment_type": "follow_up",
        "location": "Telehealth",
        "reason": "Follow-up",
        "notes": None,
        "status": new_status,
        "source_document_id": None,
        "created_at": "2026-05-07T10:00:00Z",
    }


def test_patient_accepts_proposed_appointment(client, monkeypatch):
    patient_id = uuid4()
    appointment_id = uuid4()
    care_team_id = uuid4()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=patient_id,
        email="patient@test.com",
        role="patient",
    )
    app.dependency_overrides[get_db] = _mock_db_dependency

    respond_mock = AsyncMock(
        return_value=_confirmed_appointment(appointment_id, patient_id, care_team_id, "confirmed")
    )
    monkeypatch.setattr(
        "app.routers.appointments.AppointmentService.respond_to_appointment",
        respond_mock,
    )

    response = client.post(
        f"/api/v1/appointments/{appointment_id}/respond",
        json={"action": "accept"},
    )

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()["status"] == "confirmed"
    respond_mock.assert_awaited_once()
    app.dependency_overrides.clear()


def test_patient_declines_proposed_appointment(client, monkeypatch):
    patient_id = uuid4()
    appointment_id = uuid4()
    care_team_id = uuid4()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=patient_id,
        email="patient@test.com",
        role="patient",
    )
    app.dependency_overrides[get_db] = _mock_db_dependency

    respond_mock = AsyncMock(
        return_value=_confirmed_appointment(appointment_id, patient_id, care_team_id, "declined")
    )
    monkeypatch.setattr(
        "app.routers.appointments.AppointmentService.respond_to_appointment",
        respond_mock,
    )

    response = client.post(
        f"/api/v1/appointments/{appointment_id}/respond",
        json={"action": "decline"},
    )

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()["status"] == "declined"
    app.dependency_overrides.clear()


def test_patient_requests_alternative_with_note(client, monkeypatch):
    patient_id = uuid4()
    appointment_id = uuid4()
    care_team_id = uuid4()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=patient_id,
        email="patient@test.com",
        role="patient",
    )
    app.dependency_overrides[get_db] = _mock_db_dependency

    respond_mock = AsyncMock(
        return_value=_confirmed_appointment(
            appointment_id, patient_id, care_team_id, "alternative_requested"
        )
    )
    monkeypatch.setattr(
        "app.routers.appointments.AppointmentService.respond_to_appointment",
        respond_mock,
    )

    response = client.post(
        f"/api/v1/appointments/{appointment_id}/respond",
        json={"action": "request_alternative", "note": "Mornings work better"},
    )

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()["status"] == "alternative_requested"
    assert respond_mock.await_args.kwargs["note"] == "Mornings work better"
    app.dependency_overrides.clear()


def test_patient_cancels_appointment(client, monkeypatch):
    patient_id = uuid4()
    appointment_id = uuid4()
    care_team_id = uuid4()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=patient_id,
        email="patient@test.com",
        role="patient",
    )
    app.dependency_overrides[get_db] = _mock_db_dependency

    respond_mock = AsyncMock(
        return_value=_confirmed_appointment(appointment_id, patient_id, care_team_id, "cancelled")
    )
    monkeypatch.setattr(
        "app.routers.appointments.AppointmentService.respond_to_appointment",
        respond_mock,
    )

    response = client.post(
        f"/api/v1/appointments/{appointment_id}/respond",
        json={"action": "cancel"},
    )

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()["status"] == "cancelled"
    app.dependency_overrides.clear()


def test_invalid_action_is_rejected(client):
    patient_id = uuid4()
    appointment_id = uuid4()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=patient_id,
        email="patient@test.com",
        role="patient",
    )
    app.dependency_overrides[get_db] = _mock_db_dependency

    response = client.post(
        f"/api/v1/appointments/{appointment_id}/respond",
        json={"action": "maybe"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, response.text
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "code",
    ["APPOINTMENT_CONFLICT", "APPOINTMENT_EXPIRED", "APPOINTMENT_UNAVAILABLE", "APPOINTMENT_PAST"],
)
def test_booking_failures_expose_stable_codes(client, monkeypatch, code):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=uuid4(), email="synthetic@example.com", role="patient"
    )
    app.dependency_overrides[get_db] = _mock_db_dependency
    monkeypatch.setattr(
        "app.routers.appointments.AppointmentService.respond_to_appointment",
        AsyncMock(side_effect=ValidationError("Safe booking failure", code=code)),
    )
    try:
        response = client.post(f"/api/v1/appointments/{uuid4()}/respond", json={"action": "accept"})
        assert response.status_code == 422
        assert response.json() == {"error": {"code": code, "message": "Safe booking failure"}}
    finally:
        app.dependency_overrides.clear()
