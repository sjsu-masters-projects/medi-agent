"""Integration tests for appointment and notification endpoints."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import status

from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser


def _mock_db_dependency():
    return MagicMock()


def test_create_appointment_for_authenticated_patient(client, monkeypatch):
    patient_id = uuid4()
    appointment_id = uuid4()
    care_team_id = uuid4()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=patient_id,
        email="patient@test.com",
        role="patient",
    )
    app.dependency_overrides[get_db] = _mock_db_dependency

    create_mock = AsyncMock(
        return_value={
            "id": str(appointment_id),
            "patient_id": str(patient_id),
            "care_team_id": str(care_team_id),
            "clinician_name": "Emily Smith",
            "scheduled_at": "2026-05-08T17:00:00Z",
            "duration_minutes": 30,
            "appointment_type": "follow_up",
            "location": "Telehealth",
            "reason": "Chat follow-up",
            "notes": None,
            "status": "scheduled",
            "source_document_id": None,
            "created_at": "2026-05-07T10:00:00Z",
        }
    )
    monkeypatch.setattr(
        "app.routers.appointments.AppointmentService.create_for_user",
        create_mock,
    )

    response = client.post(
        "/api/v1/appointments/",
        json={
            "care_team_id": str(care_team_id),
            "scheduled_at": "2026-05-08T17:00:00Z",
            "duration_minutes": 30,
            "appointment_type": "follow_up",
            "location": "Telehealth",
            "reason": "Chat follow-up",
        },
    )

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert response.json()["status"] == "scheduled"
    create_mock.assert_awaited_once()
    app.dependency_overrides.clear()


def test_patient_lists_and_marks_notifications_read(client, monkeypatch):
    patient_id = uuid4()
    notification_id = uuid4()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=patient_id,
        email="patient@test.com",
        role="patient",
    )
    app.dependency_overrides[get_db] = _mock_db_dependency

    list_mock = AsyncMock(
        return_value=[
            {
                "id": str(notification_id),
                "patient_id": str(patient_id),
                "notification_type": "doctor_message",
                "title": "New message from your care team",
                "body": "Please check your chat.",
                "action_url": "/chat",
                "is_read": False,
                "created_at": "2026-05-07T10:00:00Z",
            }
        ]
    )
    mark_mock = AsyncMock(
        return_value={
            "id": str(notification_id),
            "patient_id": str(patient_id),
            "notification_type": "doctor_message",
            "title": "New message from your care team",
            "body": "Please check your chat.",
            "action_url": "/chat",
            "is_read": True,
            "created_at": "2026-05-07T10:00:00Z",
        }
    )
    monkeypatch.setattr(
        "app.routers.notifications.NotificationService.list_for_patient",
        list_mock,
    )
    monkeypatch.setattr(
        "app.routers.notifications.NotificationService.mark_read",
        mark_mock,
    )

    list_response = client.get("/api/v1/notifications/")
    read_response = client.put(f"/api/v1/notifications/{notification_id}/read")

    assert list_response.status_code == status.HTTP_200_OK, list_response.text
    assert list_response.json()[0]["notification_type"] == "doctor_message"
    assert read_response.status_code == status.HTTP_200_OK
    assert read_response.json()["is_read"] is True
    app.dependency_overrides.clear()
