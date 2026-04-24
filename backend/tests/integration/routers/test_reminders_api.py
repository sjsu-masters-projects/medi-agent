"""Integration tests for patient reminder schedule routes."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.main import app
from app.models.auth import CurrentUser
from app.routers.reminders import _get_service, _patient_dep


@pytest.fixture
def patient_user():
    return CurrentUser(id=uuid4(), email="patient@test.com", role="patient")


@pytest.fixture
def override_patient_auth(patient_user):
    app.dependency_overrides[_patient_dep] = lambda: patient_user
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def mock_reminder_service():
    service = AsyncMock()
    app.dependency_overrides[_get_service] = lambda: service
    yield service
    app.dependency_overrides.clear()


def test_list_reminder_targets(client, override_patient_auth, mock_reminder_service):
    target_id = str(uuid4())
    mock_reminder_service.list_targets_for_patient.return_value = [
        {
            "target_type": "medication",
            "target_id": target_id,
            "name": "Metformin",
            "description": "Take with breakfast",
            "frequency": "twice daily",
            "provider_name": "Dr. Patel",
            "reminder_schedule": None,
            "guidance": {
                "supports_automatic_reminders": True,
                "recommended_times_per_day": 2,
                "recommended_days_per_week": 7,
                "guidance_text": "Set two reminder times.",
            },
        }
    ]

    response = client.get("/api/v1/reminders/targets")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["target_id"] == target_id
    mock_reminder_service.list_targets_for_patient.assert_awaited_once()


def test_upsert_reminder_schedule(client, override_patient_auth, mock_reminder_service):
    target_id = uuid4()
    schedule_id = str(uuid4())
    mock_reminder_service.upsert_schedule.return_value = {
        "id": schedule_id,
        "patient_id": str(uuid4()),
        "target_type": "medication",
        "target_id": str(target_id),
        "timezone": "America/Los_Angeles",
        "times_of_day": ["08:00:00", "20:00:00"],
        "days_of_week": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
        "is_enabled": True,
        "created_at": "2026-04-24T12:00:00+00:00",
        "updated_at": "2026-04-24T12:00:00+00:00",
    }

    response = client.put(
        f"/api/v1/reminders/medication/{target_id}",
        json={
            "timezone": "America/Los_Angeles",
            "times_of_day": ["08:00", "20:00"],
            "days_of_week": ["monday", "wednesday", "friday"],
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == schedule_id
    mock_reminder_service.upsert_schedule.assert_awaited_once()


def test_delete_reminder_schedule(client, override_patient_auth, mock_reminder_service):
    target_id = uuid4()

    response = client.delete(f"/api/v1/reminders/obligation/{target_id}")

    assert response.status_code == 204
    mock_reminder_service.delete_schedule.assert_awaited_once()
