"""Preview uses clinician-role protection, assignment denial audit and no-store."""

from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.core.exceptions import AuthorizationError, ValidationError
from app.core.security import get_current_user
from app.main import app
from app.models.auth import CurrentUser
from app.routers.care_plans import _preview_service

PATIENT = UUID("00000000-0000-0000-0000-000000000201")
CLINICIAN = UUID("00000000-0000-0000-0000-000000000202")
PLAN = UUID("00000000-0000-0000-0000-000000000203")
URL = f"/api/v1/care-plans/clinician/patients/{PATIENT}/{PLAN}/today-preview"


@pytest.fixture
def preview_service():
    service = AsyncMock()
    app.dependency_overrides[_preview_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=CLINICIAN, email="clinician@example.test", role="clinician", aal="aal2"
    )
    yield service
    app.dependency_overrides.clear()


def test_preview_response_and_no_store(client, preview_service):
    preview_service.preview.return_value = {
        "plan_id": str(PLAN),
        "version_number": 2,
        "generated_at": "2026-10-02T18:00:00Z",
        "feed": {
            "date": "2026-10-02",
            "timezone": "America/Los_Angeles",
            "tasks": [],
            "summary": {"total": 0, "completed": 0, "pending": 0, "skipped": 0, "missed": 0},
        },
    }
    response = client.get(URL)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    preview_service.preview.assert_awaited_once_with(CLINICIAN, PATIENT, PLAN)


def test_patient_role_cannot_preview(client, preview_service, denial_audit):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=PATIENT, email="patient@example.test", role="patient"
    )
    assert client.get(URL).status_code == 403
    preview_service.preview.assert_not_awaited()
    assert denial_audit


def test_assignment_denial_is_audited(client, preview_service, denial_audit):
    preview_service.preview.side_effect = AuthorizationError(
        "Not assigned",
        reason_code="NO_CARE_TEAM_ASSIGNMENT",
        actor_id=str(CLINICIAN),
        actor_role="clinician",
        target_type="patient",
        target_id=str(PATIENT),
    )
    assert client.get(URL).status_code == 403
    assert denial_audit[0]["reason_code"] == "NO_CARE_TEAM_ASSIGNMENT"


def test_review_error_does_not_return_successful_empty_feed(client, preview_service):
    preview_service.preview.side_effect = ValidationError("Resolve review requirements")
    response = client.get(URL)
    assert response.status_code == 422
    assert "Resolve review requirements" in response.text
