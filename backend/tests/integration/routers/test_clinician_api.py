"""Integration tests for Clinician API endpoints.

Uses FastAPI dependency overrides for proper authentication mocking.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import status

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.middleware.rate_limit import RateLimitResult
from app.models.auth import CurrentUser
from app.routers.clinicians import _clinician_dep, _get_medwatch_service, _get_service
from app.services.medwatch_3500.pdf import Form3500RenderError
from app.services.medwatch_3500.template import TemplateMismatchError
from app.services.medwatch_service import MedWatchService


@pytest.fixture
def clinician_id():
    """Fixed clinician ID for testing."""
    return uuid4()


@pytest.fixture
def mock_clinician_user(clinician_id):
    """Mock authenticated clinician user."""
    return CurrentUser(id=clinician_id, email="clinician@test.com", role="clinician")


@pytest.fixture
def mock_supabase_db():
    """Mock Supabase client with chainable methods."""
    db = MagicMock()
    table = MagicMock()
    db.table.return_value = table

    # Make all query methods chainable
    for method in ["select", "eq", "single", "insert", "order", "update", "limit", "in_"]:
        getattr(table, method).return_value = table

    return db


@pytest.fixture
def override_auth(mock_clinician_user):
    """Override authentication dependency."""

    def _get_current_user_override():
        return mock_clinician_user

    app.dependency_overrides[get_current_user] = _get_current_user_override
    app.dependency_overrides[_clinician_dep] = _get_current_user_override
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_db(mock_supabase_db):
    """Override database dependency."""

    def _get_db_override():
        return mock_supabase_db

    app.dependency_overrides[get_db] = _get_db_override
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_service():
    service = MagicMock()

    def _get_service_override():
        return service

    app.dependency_overrides[_get_service] = _get_service_override
    yield service
    app.dependency_overrides.clear()


@pytest.fixture
def override_medwatch_service():
    service = MagicMock()

    def _get_medwatch_service_override():
        return service

    app.dependency_overrides[_get_medwatch_service] = _get_medwatch_service_override
    yield service
    app.dependency_overrides.clear()


class TestGetMyProfile:
    """GET /api/v1/clinicians/me - Get clinician profile."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, clinician_id):
        """Successfully retrieve clinician profile."""
        profile_data = {
            "id": str(clinician_id),
            "email": "clinician@test.com",
            "first_name": "Dr. Sarah",
            "last_name": "Smith",
            "specialty": "Cardiology",
            "clinic_name": "Heart Health Clinic",
            "npi_number": "1234567890",
            "role": "provider",
            "avatar_url": None,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": None,
        }

        mock_supabase_db.table().select().eq().single().execute.return_value = MagicMock(
            data=profile_data
        )

        response = client.get("/api/v1/clinicians/me")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == "clinician@test.com"
        assert data["first_name"] == "Dr. Sarah"
        assert data["specialty"] == "Cardiology"

    def test_not_found(self, client, override_auth, override_db, mock_supabase_db):
        """Handle clinician not found."""
        mock_supabase_db.table().select().eq().single().execute.return_value = MagicMock(data=None)

        response = client.get("/api/v1/clinicians/me")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestGetMyPatients:
    """GET /api/v1/clinicians/me/patients - List assigned patients."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db):
        """Successfully retrieve patient list."""
        patient_id = uuid4()
        care_team_data = [
            {
                "id": str(uuid4()),
                "clinician_id": str(uuid4()),
                "patient_id": str(patient_id),
                "status": "active",
                "role": "provider",
                "patients": {
                    "id": str(patient_id),
                    "email": "patient@test.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "date_of_birth": "1990-01-15",
                    "avatar_url": None,
                },
            }
        ]

        mock_supabase_db.table().select().eq().eq().execute.return_value = MagicMock(
            data=care_team_data
        )

        response = client.get("/api/v1/clinicians/me/patients")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["first_name"] == "John"

    def test_empty_patient_list(self, client, override_auth, override_db, mock_supabase_db):
        """Handle empty patient list."""
        mock_supabase_db.table().select().eq().eq().execute.return_value = MagicMock(data=[])

        response = client.get("/api/v1/clinicians/me/patients")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0


class TestUpdateMyProfile:
    """PUT /api/v1/clinicians/me - Update clinician profile."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, clinician_id):
        updated_data = {
            "id": str(clinician_id),
            "email": "clinician@test.com",
            "first_name": "Dr. Sarah",
            "last_name": "Smith",
            "specialty": "Internal Medicine",
            "clinic_name": "City Health",
            "npi_number": "1234567890",
            "role": "provider",
            "avatar_url": None,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-15T00:00:00Z",
        }

        mock_supabase_db.table().update().eq().execute.return_value = MagicMock(data=[updated_data])

        response = client.put(
            "/api/v1/clinicians/me",
            json={"specialty": "Internal Medicine", "clinic_name": "City Health"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["specialty"] == "Internal Medicine"
        assert data["clinic_name"] == "City Health"

    def test_success_with_clinic_code_resolution(
        self, client, override_auth, override_db, mock_supabase_db, clinician_id
    ):
        updated_data = {
            "id": str(clinician_id),
            "email": "clinician@test.com",
            "first_name": "Dr. Sarah",
            "last_name": "Smith",
            "specialty": "Internal Medicine",
            "clinic_name": "City Health",
            "npi_number": "1234567890",
            "role": "provider",
            "avatar_url": None,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-15T00:00:00Z",
        }
        mock_supabase_db.table().execute.side_effect = [
            MagicMock(
                data=[
                    {
                        "id": "clinic-1",
                        "code": "ABC123",
                        "display_name": "City Health",
                        "status": "active",
                    }
                ]
            ),
            MagicMock(data=[updated_data]),
        ]

        response = client.put(
            "/api/v1/clinicians/me",
            json={
                "specialty": "Internal Medicine",
                "clinic_code": "ABC123",
                "type1_npi": "1234567890",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["specialty"] == "Internal Medicine"
        assert data["clinic_name"] == "City Health"


class TestGetPatientDetail:
    """GET /api/v1/clinicians/me/patients/{patient_id} - Get patient detail."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db):
        """Successfully retrieve patient detail."""
        patient_id = uuid4()

        patient_data = {
            "id": str(patient_id),
            "email": "patient@test.com",
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "1990-01-15",
            "gender": "male",
            "preferred_language": "en",
            "phone": "+1234567890",
            "avatar_url": None,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": None,
        }
        mock_supabase_db.table().execute.side_effect = [
            MagicMock(data=[{"id": str(uuid4())}]),
            MagicMock(data=patient_data),
        ]

        response = client.get(f"/api/v1/clinicians/me/patients/{patient_id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["first_name"] == "John"
        assert data["email"] == "patient@test.com"

    def test_not_assigned(self, client, override_auth, override_db, mock_supabase_db):
        """Reject access to unassigned patient."""
        patient_id = uuid4()

        # Mock no care team assignment
        mock_supabase_db.table().select().eq().eq().eq().execute.return_value = MagicMock(data=[])

        response = client.get(f"/api/v1/clinicians/me/patients/{patient_id}")

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestClinicianPatientMessages:
    def test_send_patient_message(self, client, override_auth, override_service):
        patient_id = uuid4()
        message_id = uuid4()
        clinician_id = uuid4()
        override_service.send_patient_message = AsyncMock(
            return_value={
                "id": str(message_id),
                "clinician_id": str(clinician_id),
                "patient_id": str(patient_id),
                "channel": "in_app",
                "subject": "Follow-up",
                "body": "Please bring your medication list.",
                "is_read": False,
                "created_at": "2026-05-07T10:00:00Z",
            }
        )

        response = client.post(
            f"/api/v1/clinicians/me/patients/{patient_id}/message",
            json={"subject": "Follow-up", "body": "Please bring your medication list."},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["body"] == "Please bring your medication list."
        override_service.send_patient_message.assert_awaited_once()

    def test_legacy_email_endpoint_does_not_claim_delivery(
        self, client, override_auth, override_service
    ):
        override_service.get_patient_detail = AsyncMock(return_value={})
        patient_id = uuid4()
        override_service.send_patient_message = AsyncMock(
            return_value={
                "id": str(uuid4()),
                "clinician_id": str(uuid4()),
                "patient_id": str(patient_id),
                "channel": "email",
                "subject": "Lab follow-up",
                "body": "Please schedule labs this week.",
                "is_read": False,
                "created_at": "2026-05-07T10:00:00Z",
            }
        )

        response = client.post(
            f"/api/v1/clinicians/me/patients/{patient_id}/email",
            json={
                "channel": "in_app",
                "subject": "Lab follow-up",
                "body": "Please schedule labs this week.",
            },
        )

        assert response.status_code == status.HTTP_410_GONE
        override_service.send_patient_message.assert_not_awaited()

    def test_patient_not_found(self, client, override_auth, override_db, mock_supabase_db):
        """Handle patient not found after authorization check."""
        patient_id = uuid4()

        # Mock care team assignment exists
        mock_supabase_db.table().select().eq().eq().eq().execute.return_value = MagicMock(
            data=[{"id": str(uuid4())}]
        )

        # Mock patient not found
        mock_supabase_db.table().select().eq().single().execute.return_value = MagicMock(data=None)

        response = client.get(f"/api/v1/clinicians/me/patients/{patient_id}")

        # Service raises AuthorizationError first (403), not NotFoundError
        # because the check happens in sequence
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_patient_messages(self, client, override_auth, override_service):
        patient_id = uuid4()
        override_service.list_patient_messages = AsyncMock(
            return_value=[
                {
                    "id": str(uuid4()),
                    "clinician_id": str(uuid4()),
                    "patient_id": str(patient_id),
                    "channel": "in_app",
                    "subject": "Follow-up",
                    "body": "Bring your medication list.",
                    "is_read": False,
                    "created_at": "2026-05-10T10:00:00Z",
                },
            ]
        )

        response = client.get(f"/api/v1/clinicians/me/patients/{patient_id}/messages")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["body"] == "Bring your medication list."
        override_service.list_patient_messages.assert_awaited_once_with(
            override_service.list_patient_messages.await_args.args[0],
            patient_id,
        )

    def test_list_patient_messages_empty(self, client, override_auth, override_service):
        patient_id = uuid4()
        override_service.list_patient_messages = AsyncMock(return_value=[])

        response = client.get(f"/api/v1/clinicians/me/patients/{patient_id}/messages")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    def test_list_patient_messages_unassigned(self, client, override_auth, override_service):
        patient_id = uuid4()
        override_service.list_patient_messages = AsyncMock(
            side_effect=AuthorizationError("You are not assigned to this patient")
        )

        response = client.get(f"/api/v1/clinicians/me/patients/{patient_id}/messages")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_all_sent_messages(self, client, override_auth, override_service):
        override_service.list_all_sent_messages = AsyncMock(
            return_value=[
                {
                    "id": str(uuid4()),
                    "clinician_id": str(uuid4()),
                    "patient_id": str(uuid4()),
                    "channel": "in_app",
                    "subject": "Reminder",
                    "body": "Your labs are ready.",
                    "is_read": False,
                    "created_at": "2026-05-11T08:00:00Z",
                    "patient_first_name": "Elena",
                    "patient_last_name": "Park",
                },
            ]
        )

        response = client.get("/api/v1/clinicians/me/messages")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["patient_first_name"] == "Elena"
        assert data[0]["body"] == "Your labs are ready."


class TestGetPatientRiskSnapshot:
    """GET /api/v1/clinicians/me/patients/{patient_id}/risk - Risk card snapshot."""

    def test_success(self, client, override_auth, override_db, monkeypatch):
        patient_id = uuid4()

        async def _mock_get_risk_snapshot(self, clinician_id, incoming_patient_id):
            assert incoming_patient_id == patient_id
            return {
                "patient_id": patient_id,
                "first_name": "Taylor",
                "last_name": "Mills",
                "risk_level": "high",
                "adherence_score": 0.52,
                "open_adr_count": 1,
                "active_med_count": 3,
                "recent_symptom_severity": 8,
                "last_activity": "Reported 'dizziness' 35m ago",
            }

        monkeypatch.setattr(
            "app.services.clinician_service.ClinicianService.get_patient_risk_snapshot",
            _mock_get_risk_snapshot,
        )

        response = client.get(f"/api/v1/clinicians/me/patients/{patient_id}/risk")

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert payload["patient_id"] == str(patient_id)
        assert payload["risk_level"] == "high"
        assert payload["adherence_score"] == 0.52

    def test_not_assigned(self, client, override_auth, override_db, monkeypatch):
        patient_id = uuid4()

        async def _mock_get_risk_snapshot(self, _clinician_id, _incoming_patient_id):
            raise AuthorizationError("You are not assigned to this patient")

        monkeypatch.setattr(
            "app.services.clinician_service.ClinicianService.get_patient_risk_snapshot",
            _mock_get_risk_snapshot,
        )

        response = client.get(f"/api/v1/clinicians/me/patients/{patient_id}/risk")

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestGenerateSoapNoteRateLimit:
    """POST /api/v1/clinicians/me/patients/{patient_id}/soap-note rate limiting."""

    def test_returns_429_with_retry_hint_when_limited(
        self,
        client,
        override_auth,
        override_db,
        monkeypatch,
    ):
        patient_id = uuid4()

        async def _mock_patient_access(self, _clinician_id, _patient_id):
            return {"id": str(patient_id)}

        async def _deny_request(_key):
            return RateLimitResult(allowed=False, retry_after_seconds=42, remaining=0)

        monkeypatch.setattr(
            "app.services.clinician_service.ClinicianService.get_patient_detail",
            _mock_patient_access,
        )
        monkeypatch.setattr(
            "app.routers.clinicians.soap_note_rate_limiter.check",
            _deny_request,
        )

        response = client.post(
            f"/api/v1/clinicians/me/patients/{patient_id}/soap-note",
            json={"lookback_days": 30},
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.headers["Retry-After"] == "42"
        payload = response.json()
        assert payload["error"]["code"] == "RATE_LIMITED"
        assert "Retry after 42 seconds" in payload["error"]["message"]


class TestGenerateInviteCode:
    """POST /api/v1/clinicians/me/invite-code - Generate patient invite code."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, clinician_id):
        """Successfully generate invite code."""
        care_team_id = uuid4()
        clinic_id = str(uuid4())
        invite_code = "A1B2C3D4"

        mock_supabase_db.table().execute.side_effect = [
            # The clinician's one active clinic membership tags the code.
            MagicMock(
                data=[
                    {
                        "clinician_id": str(clinician_id),
                        "clinic_id": clinic_id,
                        "role": "provider",
                        "status": "active",
                    }
                ]
            ),
            MagicMock(
                data=[
                    {
                        "id": str(care_team_id),
                        "clinician_id": str(clinician_id),
                        "invite_code": invite_code,
                        "status": "pending",
                        "role": "provider",
                        "clinic_id": clinic_id,
                    }
                ]
            ),
        ]

        response = client.post("/api/v1/clinicians/me/invite-code")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "invite_code" in data
        assert "care_team_id" in data
        assert len(data["invite_code"]) == 8
        assert mock_supabase_db.table().insert.call_args.args[0]["clinic_id"] == clinic_id


class TestGetCurrentInviteCode:
    """GET /api/v1/clinicians/me/invite-code - Read latest pending patient invite code."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, clinician_id):
        """Returns latest pending invite code when available."""
        care_team_id = uuid4()

        mock_supabase_db.table().select().eq().eq().order().execute.return_value = MagicMock(
            data=[
                {
                    "id": str(care_team_id),
                    "invite_code": "QWERTY12",
                    "created_at": "2026-04-10T00:00:00Z",
                }
            ]
        )

        response = client.get("/api/v1/clinicians/me/invite-code")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["invite_code"] == "QWERTY12"
        assert data["care_team_id"] == str(care_team_id)

    def test_empty(self, client, override_auth, override_db, mock_supabase_db):
        """Returns null payload when no pending invite exists."""
        mock_supabase_db.table().select().eq().eq().order().execute.return_value = MagicMock(
            data=[]
        )

        response = client.get("/api/v1/clinicians/me/invite-code")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["invite_code"] is None
        assert data["care_team_id"] is None


class TestListInviteCodes:
    """GET /api/v1/clinicians/me/invite-codes - Read invite lifecycle list."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, clinician_id):
        mock_supabase_db.table().execute.side_effect = [
            MagicMock(
                data={
                    "id": str(uuid4()),
                    "clinic_id": "clinic-1",
                    "clinic_name": "City Health",
                    "role": "provider",
                }
            ),
            MagicMock(
                data=[
                    {
                        "clinician_id": str(clinician_id),
                        "clinic_id": str(uuid4()),
                        "role": "provider",
                        "status": "active",
                    }
                ]
            ),
            MagicMock(
                data=[
                    {
                        "id": str(uuid4()),
                        "invite_code": "ACTIVE123",
                        "status": "pending",
                        "patient_id": None,
                        "role": "provider",
                        "created_at": "2026-04-10T00:00:00Z",
                        "invite_expires_at": "2099-01-01T00:00:00+00:00",
                        "invite_claimed_at": None,
                        "patients": None,
                        "clinicians": {
                            "id": str(uuid4()),
                            "first_name": "Taylor",
                            "last_name": "Mills",
                            "email": "taylor@example.com",
                        },
                    },
                    {
                        "id": str(uuid4()),
                        "invite_code": "USED1234",
                        "status": "active",
                        "patient_id": str(uuid4()),
                        "role": "provider",
                        "created_at": "2026-04-09T00:00:00Z",
                        "invite_expires_at": "2099-01-01T00:00:00+00:00",
                        "invite_claimed_at": "2026-04-09T09:00:00Z",
                        "patients": {
                            "id": str(uuid4()),
                            "first_name": "Sam",
                            "last_name": "Lee",
                            "email": "sam@example.com",
                        },
                        "clinicians": {
                            "id": str(uuid4()),
                            "first_name": "Taylor",
                            "last_name": "Mills",
                            "email": "taylor@example.com",
                        },
                    },
                ]
            ),
        ]

        response = client.get("/api/v1/clinicians/me/invite-codes")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "invites" in data
        assert "counts" in data
        assert data["counts"]["active"] == 1
        assert data["counts"]["claimed"] == 1
        assert data["invites"][0]["created_by"]["email"] == "taylor@example.com"


class TestRevokeInviteCode:
    """POST /api/v1/clinicians/me/invite-codes/{care_team_id}/revoke"""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, clinician_id):
        care_team_id = uuid4()

        mock_supabase_db.table().execute.side_effect = [
            MagicMock(
                data={
                    "id": str(care_team_id),
                    "clinician_id": str(clinician_id),
                    "status": "pending",
                    "patient_id": None,
                    "invite_code": "REVOKE12",
                }
            ),
            MagicMock(data=[{"id": str(care_team_id), "status": "inactive"}]),
        ]

        response = client.post(f"/api/v1/clinicians/me/invite-codes/{care_team_id}/revoke")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["care_team_id"] == str(care_team_id)
        assert data["status"] == "inactive"

    def test_reject_non_pending(
        self, client, override_auth, override_db, mock_supabase_db, clinician_id
    ):
        care_team_id = uuid4()

        mock_supabase_db.table().select().eq().eq().single().execute.return_value = MagicMock(
            data={
                "id": str(care_team_id),
                "clinician_id": str(clinician_id),
                "status": "active",
                "patient_id": str(uuid4()),
                "invite_code": "USED1234",
            }
        )

        response = client.post(f"/api/v1/clinicians/me/invite-codes/{care_team_id}/revoke")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestDashboardRoutes:
    """GET /api/v1/clinicians/me/dashboard"""

    def test_success(self, client, override_auth, override_service):
        patient_id = uuid4()
        override_service.get_dashboard_data = AsyncMock(
            return_value={
                "patients": [
                    {
                        "patient_id": str(patient_id),
                        "first_name": "John",
                        "last_name": "Doe",
                        "risk_level": "high",
                        "adherence_score": 0.4,
                        "open_adr_count": 1,
                        "active_med_count": 5,
                        "recent_symptom_severity": 8,
                        "last_activity": "Reported symptom 2h ago",
                    }
                ],
                "total": 1,
                "high_risk": 1,
                "medium_risk": 0,
                "low_risk": 0,
                "pending_adr_reviews": 2,
                "medwatch_pending": 0,
            }
        )

        response = client.get(
            "/api/v1/clinicians/me/dashboard", params={"page": 1, "page_size": 25}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 1
        assert data["patients"][0]["risk_level"] == "high"


class TestADRReviewQueueRoutes:
    """GET /api/v1/clinicians/me/adr-assessments"""

    def test_success_returns_patient_grounded_naranjo_evidence(
        self, client, override_auth, override_service, clinician_id
    ):
        patient_id = uuid4()
        assessment_id = uuid4()
        symptom_report_id = uuid4()
        medication_id = uuid4()
        override_service.list_adr_review_queue = AsyncMock(
            return_value={
                "items": [
                    {
                        "id": str(assessment_id),
                        "patient_id": str(patient_id),
                        "patient_first_name": "Maya",
                        "patient_last_name": "Patel",
                        "symptom_report_id": str(symptom_report_id),
                        "symptom": "dizziness",
                        "severity": 2,
                        "onset": "after starting medication",
                        "symptom_created_at": "2026-10-02T09:59:00Z",
                        "suspect_medication_id": str(medication_id),
                        "suspect_medication_name": "fluticasone/salmeterol inhaler",
                        "naranjo_score": 3,
                        "causality": "Possible",
                        "naranjo_answers": {"event_after_drug": "yes"},
                        "naranjo_assessment": {"missing_questions": ["alternative_causes"]},
                        "evidence": [
                            {
                                "question": "event_after_drug",
                                "answer": "yes",
                                "evidence": "Dizziness began after starting the inhaler.",
                            }
                        ],
                        "status": "draft",
                        "created_at": "2026-10-02T10:00:00Z",
                    }
                ],
                "total": 1,
            }
        )

        response = client.get(
            "/api/v1/clinicians/me/adr-assessments",
            params={"status": "draft", "limit": 25},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["naranjo_score"] == 3
        assert data["items"][0]["evidence"][0]["question"] == "event_after_drug"
        assert "thinking_chain" not in data["items"][0]
        override_service.list_adr_review_queue.assert_awaited_once_with(
            clinician_id,
            status_filter="draft",
            limit=25,
        )

    def test_review_action_is_passed_to_the_clinician_service(
        self, client, override_auth, override_service, clinician_id
    ):
        patient_id = uuid4()
        assessment_id = uuid4()
        override_service.review_adr_assessment = AsyncMock(
            return_value={
                "id": str(assessment_id),
                "patient_id": str(patient_id),
                "status": "draft",
                "last_review_action": "request_information",
                "review_note": "Please confirm whether symptoms recurred.",
                "requested_information": ["reappeared_on_rechallenge"],
                "reviewed_by": str(clinician_id),
                "reviewed_at": "2026-10-06T10:00:00Z",
                "dismiss_reason": None,
                "updated_at": "2026-10-06T10:00:00Z",
            }
        )

        response = client.post(
            f"/api/v1/clinicians/me/adr-assessments/{assessment_id}/review",
            json={
                "action": "request_information",
                "note": "Please confirm whether symptoms recurred.",
                "requested_information": ["reappeared_on_rechallenge"],
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["last_review_action"] == "request_information"
        decision = override_service.review_adr_assessment.await_args.args[2]
        assert decision.requested_information == ["reappeared_on_rechallenge"]

    def test_dismiss_action_requires_a_reason(self, client, override_auth, override_service):
        response = client.post(
            f"/api/v1/clinicians/me/adr-assessments/{uuid4()}/review",
            json={"action": "dismiss", "note": ""},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        override_service.review_adr_assessment.assert_not_called()


class TestPatientDeepDiveRoutes:
    """GET /api/v1/clinicians/me/patients/{patient_id}/deep-dive"""

    def test_success_includes_review_metadata(self, client, override_auth, override_service):
        patient_id = uuid4()
        document_id = uuid4()
        reviewer_id = uuid4()
        override_service.get_patient_deep_dive = AsyncMock(
            return_value={
                "patient_id": str(patient_id),
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com",
                "risk_level": "medium",
                "adherence_score": 0.78,
                "medications": [],
                "adherence_series": [],
                "symptom_reports": [],
                "chat_messages": [],
                "conditions": [],
                "allergies": [],
                "documents": [
                    {
                        "id": str(document_id),
                        "file_name": "lab.pdf",
                        "document_type": "lab_report",
                        "parse_status": "completed",
                        "ai_summary": "Summary",
                        "created_at": "2026-04-21T10:00:00Z",
                        "uploaded_by_role": "patient",
                        "clinician_annotation": "Looks good",
                        "review_status": "approved",
                        "reviewed_by": str(reviewer_id),
                        "reviewed_at": "2026-04-22T08:00:00Z",
                        "review_note": "Clinically consistent",
                        "reviewer": {
                            "id": str(reviewer_id),
                            "first_name": "Priya",
                            "last_name": "Shah",
                        },
                    }
                ],
                "latest_soap_note": None,
                "obligations": [
                    {
                        "id": str(uuid4()),
                        "obligation_type": "exercise",
                        "description": "Walk daily",
                        "frequency": "daily",
                        "is_active": True,
                        "created_at": "2026-04-20T08:00:00Z",
                    }
                ],
                "obligation_completion_rate": 0.5,
                "adherence_barriers": [
                    {
                        "target_type": "obligation",
                        "target_id": str(patient_id),
                        "barrier_code": "schedule",
                        "notes": "Synthetic schedule conflict",
                        "logged_at": "2026-10-02T09:00:00Z",
                    }
                ],
            }
        )

        response = client.get(f"/api/v1/clinicians/me/patients/{patient_id}/deep-dive")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["documents"][0]["review_status"] == "approved"
        assert data["documents"][0]["reviewer"]["first_name"] == "Priya"
        assert data["obligations"][0]["description"] == "Walk daily"
        assert data["adherence_barriers"][0]["barrier_code"] == "schedule"
        assert data["adherence_barriers"][0]["notes"] == "Synthetic schedule conflict"


class TestDocumentReviewQueueRoutes:
    """Review queue route coverage."""

    def test_list_review_queue(self, client, override_auth, override_service):
        patient_id = uuid4()
        document_id = uuid4()
        override_service.list_document_review_queue = AsyncMock(
            return_value=[
                {
                    "id": str(document_id),
                    "patient_id": str(patient_id),
                    "patient_first_name": "Nina",
                    "patient_last_name": "West",
                    "file_name": "upload.pdf",
                    "document_type": "lab_report",
                    "parse_status": "pending",
                    "ai_summary": "Summary",
                    "source_clinic": "North Clinic",
                    "created_at": "2026-04-20T10:00:00Z",
                    "uploaded_by_role": "patient",
                    "review_status": "pending",
                }
            ]
        )

        response = client.get("/api/v1/clinicians/me/document-review-queue")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["patient_first_name"] == "Nina"

    def test_approve_document_review(self, client, override_auth, override_service):
        patient_id = uuid4()
        document_id = uuid4()
        clinician_id = uuid4()
        override_service.approve_document_review = AsyncMock(
            return_value={
                "status": "reviewed",
                "document_id": str(document_id),
                "patient_id": str(patient_id),
                "review_status": "approved",
                "reviewed_by": str(clinician_id),
                "reviewed_at": "2026-04-22T10:00:00Z",
                "review_note": None,
            }
        )

        response = client.post(
            f"/api/v1/clinicians/me/patients/{patient_id}/documents/{document_id}/approve"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["review_status"] == "approved"

    def test_reject_document_review(self, client, override_auth, override_service):
        patient_id = uuid4()
        document_id = uuid4()
        clinician_id = uuid4()
        override_service.reject_document_review = AsyncMock(
            return_value={
                "status": "reviewed",
                "document_id": str(document_id),
                "patient_id": str(patient_id),
                "review_status": "rejected",
                "reviewed_by": str(clinician_id),
                "reviewed_at": "2026-04-22T10:00:00Z",
                "review_note": "Unreadable upload",
            }
        )

        response = client.post(
            f"/api/v1/clinicians/me/patients/{patient_id}/documents/{document_id}/reject",
            json={"review_note": "Unreadable upload"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["review_status"] == "rejected"


class TestPatientA2ATimeline:
    """GET /api/v1/clinicians/me/patients/{patient_id}/a2a-timeline"""

    def test_success(self, client, override_auth, override_db, mock_supabase_db):
        patient_id = uuid4()
        task_id = uuid4()

        mock_supabase_db.table().execute.side_effect = [
            MagicMock(data=[{"id": str(uuid4())}]),
            MagicMock(data={"id": str(patient_id), "first_name": "John"}),
            MagicMock(
                data=[
                    {
                        "id": str(task_id),
                        "patient_id": str(patient_id),
                        "symptom_event_id": str(uuid4()),
                        "idempotency_key": "symptom_event:test-1",
                        "conversation_session_id": "session-1",
                        "source_agent": "symptom",
                        "target_agent": "pharmacovigilance",
                        "task_type": "symptom_adr_screen",
                        "status": "retrying",
                        "retry_attempt": 1,
                        "max_retries": 3,
                        "next_retry_at": "2026-04-17T12:00:00Z",
                        "dead_lettered_at": None,
                        "error_message": "worker timeout",
                        "created_at": "2026-04-17T11:59:00Z",
                        "started_at": "2026-04-17T11:59:05Z",
                        "completed_at": None,
                        "input_payload": {},
                        "output_payload": None,
                        "worker_payload": {},
                    }
                ]
            ),
        ]

        response = client.get(
            f"/api/v1/clinicians/me/patients/{patient_id}/a2a-timeline",
            params={"session_id": "session-1", "limit": 25},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["patient_id"] == str(patient_id)
        assert data["session_id"] == "session-1"
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["status"] == "retrying"
        assert data["tasks"][0]["id"] == str(task_id)

    def test_not_assigned(self, client, override_auth, override_db, mock_supabase_db):
        patient_id = uuid4()
        mock_supabase_db.table().execute.side_effect = [
            MagicMock(data=[]),
        ]

        response = client.get(f"/api/v1/clinicians/me/patients/{patient_id}/a2a-timeline")

        assert response.status_code == status.HTTP_403_FORBIDDEN


def _medwatch_draft_payload(
    *, draft_id=None, assessment_id=None, patient_id=None, clinician_id=None
):
    draft_id = draft_id or uuid4()
    assessment_id = assessment_id or uuid4()
    patient_id = patient_id or uuid4()
    clinician_id = clinician_id or uuid4()
    return {
        "id": str(draft_id),
        "adr_assessment_id": str(assessment_id),
        "patient_id": str(patient_id),
        "form_data": {
            "form_version": "fda-3500-2025-09",
            "section_a": {"identifier": "XX-ABCD"},
            "section_b": {"report_types": ["adverse_event"], "narrative": "Dizziness"},
            "section_d": {"product_1": {"name": "Synthetic product"}},
            "mediagent_review": {
                "naranjo_score": 6,
                "causality": "Probable",
                "reportability_rationale": "Clinically significant new event.",
            },
        },
        "source_evidence": [],
        "clinician_edited_fields": [],
        "de_identified": False,
        "status": "draft",
        "patient_reference": "XX-ABCD",
        "created_by": str(clinician_id),
        "approved_by": None,
        "approved_at": None,
        "approval_note": None,
        "revision": 1,
        "export_version": "fda-3500-2025-09",
        "created_at": "2026-10-09T10:00:00Z",
        "updated_at": "2026-10-09T10:00:00Z",
        "missing_for_approval": [{"path": "section_g.occupation", "code": "occupation_missing"}],
        "name_warnings": [],
        "pdf_available": False,
        "current_submission": None,
        "submission_history": [],
        "attestation": {"version": "medwatch-3500-approval-v1", "text": "Synthetic text"},
    }


_DRAFTS = "/api/v1/clinicians/me/medwatch-drafts"


class TestMedWatchDraftRoutes:
    def test_create_draft_records_explicit_decision(
        self, client, override_auth, override_medwatch_service, clinician_id
    ):
        assessment_id = uuid4()
        payload = _medwatch_draft_payload(assessment_id=assessment_id, clinician_id=clinician_id)
        override_medwatch_service.create_draft = AsyncMock(return_value=payload)

        response = client.post(
            f"/api/v1/clinicians/me/adr-assessments/{assessment_id}/medwatch-draft",
            json={
                "decision": "prepare_draft",
                "reportability_rationale": "Clinically significant new event.",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["status"] == "draft"
        assert body["form_data"]["form_version"] == "fda-3500-2025-09"
        assert body["missing_for_approval"] == payload["missing_for_approval"]
        assert body["attestation"]["version"] == "medwatch-3500-approval-v1"
        request = override_medwatch_service.create_draft.await_args.args[2]
        assert request.decision.value == "prepare_draft"
        assert request.reportability_rationale == "Clinically significant new event."

    @pytest.mark.parametrize(
        "body",
        [
            {
                "approval_note": "Reviewed.",
                "expected_revision": 1,
                "attested": False,
                "attestation_version": "medwatch-3500-approval-v1",
            },
            {"approval_note": "Reviewed.", "expected_revision": 1, "attested": True},
            {
                "approval_note": "Reviewed.",
                "expected_revision": 1,
                "attested": True,
                "attestation_version": "medwatch-3500-approval-v0",
            },
        ],
    )
    def test_approval_requires_attestation_and_its_version(
        self, client, override_auth, override_medwatch_service, body
    ):
        response = client.post(f"{_DRAFTS}/{uuid4()}/approve", json=body)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        override_medwatch_service.approve_draft.assert_not_called()

    @pytest.mark.parametrize("state", ["active", "submitted", "discarded"])
    def test_list_passes_the_state(self, client, override_auth, override_medwatch_service, state):
        override_medwatch_service.list_drafts = AsyncMock(
            return_value={"items": [_medwatch_draft_payload()], "total": 1}
        )

        response = client.get(_DRAFTS, params={"state": state})

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["total"] == 1
        assert override_medwatch_service.list_drafts.await_args.args[1] == state

    def test_list_defaults_to_active_and_rejects_an_unknown_state(
        self, client, override_auth, override_medwatch_service
    ):
        override_medwatch_service.list_drafts = AsyncMock(return_value={"items": [], "total": 0})

        assert client.get(_DRAFTS).status_code == status.HTTP_200_OK
        assert override_medwatch_service.list_drafts.await_args.args[1] == "active"
        response = client.get(_DRAFTS, params={"state": "deleted"})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_form_options_come_from_the_template(self, client, override_auth, override_db):
        response = client.get(f"{_DRAFTS}/form-3500-options")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert {"value": "Oral", "label": "Oral"} in body["routes"]
        assert {"value": "medwatch_online", "label": "MedWatch Online"} in body[
            "submission_methods"
        ]
        assert len(body["countries"]) > 100

    def test_preview_route(self, client, override_auth, override_medwatch_service):
        draft_id = uuid4()
        override_medwatch_service.get_preview = AsyncMock(
            return_value={
                "draft_id": str(draft_id),
                "status": "draft",
                "revision": 1,
                "export_version": "fda-3500-2025-09",
                "discarded": False,
                "sections": [
                    {
                        "section": "C",
                        "title": "Product availability",
                        "completion": "not_completed_by_mediagent",
                        "items": [],
                    }
                ],
                "mediagent_review": {"naranjo_score": 6},
                "template": {
                    "title": "FORM FDA 3500",
                    "revision": "09/2025",
                    "omb_number": "0910-0291",
                    "expires": "2027-09-30",
                    "may_be_superseded": False,
                },
            }
        )

        response = client.get(f"{_DRAFTS}/{draft_id}/preview")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["not_submitted_to_fda"] is True
        assert override_medwatch_service.get_preview.await_args.args[1] == draft_id

    def test_json_export_is_marked_not_submitted(
        self, client, override_auth, override_medwatch_service
    ):
        draft_id = uuid4()
        override_medwatch_service.export_draft = AsyncMock(
            return_value={
                "filename": f"fda-3500-{str(draft_id)[:8]}-not-submitted.json",
                "media_type": "application/json",
                "content": {"artifact_type": "fda_3500_draft", "not_submitted_to_fda": True},
            }
        )

        response = client.get(f"{_DRAFTS}/{draft_id}/export")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["content"]["artifact_type"] == "fda_3500_draft"
        override_medwatch_service.export_draft.assert_awaited_once()

    def test_pdf_download_headers_and_filename(
        self, client, override_auth, override_medwatch_service
    ):
        draft_id = uuid4()
        filename = f"fda-3500-{str(draft_id)[:8]}-not-submitted.pdf"
        override_medwatch_service.export_pdf = AsyncMock(
            return_value={
                "filename": filename,
                "media_type": "application/pdf",
                "content": b"%PDF-synthetic",
            }
        )

        response = client.get(f"{_DRAFTS}/{draft_id}/export.pdf")

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["content-disposition"] == f'attachment; filename="{filename}"'
        assert response.headers["cache-control"] == "no-store"
        assert response.content == b"%PDF-synthetic"

    @pytest.mark.parametrize(
        ("error", "expected_status", "code"),
        [
            (lambda: NotFoundError("MedWatch draft", "x"), 404, "NOT_FOUND"),
            (lambda: AuthorizationError("Not assigned"), 403, "AUTHORIZATION_ERROR"),
            (
                lambda: ConflictError("Changed", code="MEDWATCH_REVISION_CONFLICT"),
                409,
                "MEDWATCH_REVISION_CONFLICT",
            ),
            (
                lambda: ValidationError("Not approved", code="MEDWATCH_NOT_APPROVED"),
                422,
                "MEDWATCH_NOT_APPROVED",
            ),
            (
                lambda: ValidationError("Legacy", code="MEDWATCH_LEGACY_DRAFT_INCOMPLETE"),
                422,
                "MEDWATCH_LEGACY_DRAFT_INCOMPLETE",
            ),
            (lambda: TemplateMismatchError("synthetic"), 503, "FORM_3500_TEMPLATE_MISMATCH"),
            (lambda: Form3500RenderError(uuid4()), 502, "FORM_3500_RENDER_FAILED"),
        ],
    )
    def test_pdf_error_codes(
        self, client, override_auth, override_medwatch_service, error, expected_status, code
    ):
        override_medwatch_service.export_pdf = AsyncMock(side_effect=error())

        response = client.get(f"{_DRAFTS}/{uuid4()}/export.pdf")

        assert response.status_code == expected_status
        assert response.json()["error"]["code"] == code
        assert response.headers["content-type"].startswith("application/json")

    def test_incomplete_approval_returns_the_missing_items(
        self, client, override_auth, override_medwatch_service
    ):
        missing = [{"path": "section_g.occupation", "code": "occupation_missing"}]
        override_medwatch_service.approve_draft = AsyncMock(
            side_effect=ValidationError(
                "Incomplete",
                code="MEDWATCH_APPROVAL_INCOMPLETE",
                details={"missing_for_approval": missing},
            )
        )

        response = client.post(
            f"{_DRAFTS}/{uuid4()}/approve",
            json={
                "approval_note": "Reviewed.",
                "expected_revision": 1,
                "attested": True,
                "attestation_version": "medwatch-3500-approval-v1",
                "non_serious_attested": True,
                "acknowledged_warnings": [{"path": "section_b.narrative", "kind": "patient_name"}],
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["error"] == {
            "code": "MEDWATCH_APPROVAL_INCOMPLETE",
            "message": "Incomplete",
            "details": {"missing_for_approval": missing},
        }
        request = override_medwatch_service.approve_draft.await_args.args[2]
        assert request.non_serious_attested is True

    def test_discard_submission_and_amend_routes(
        self, client, override_auth, override_medwatch_service
    ):
        draft_id = uuid4()
        payload = _medwatch_draft_payload(draft_id=draft_id)
        for name in ("discard_draft", "record_submission", "amend_submission"):
            setattr(override_medwatch_service, name, AsyncMock(return_value=payload))

        discard = client.post(
            f"{_DRAFTS}/{draft_id}/discard", json={"reason": "Wrong drug", "expected_revision": 2}
        )
        record = client.post(
            f"{_DRAFTS}/{draft_id}/submission",
            json={
                "submitted_on": "2026-10-12",
                "method": "fax",
                "method_detail": None,
                "fda_reference": None,
                "attested": True,
                "expected_revision": 3,
            },
        )
        amend = client.post(
            f"{_DRAFTS}/{draft_id}/submission/amend",
            json={
                "amends_id": str(uuid4()),
                "submitted_on": "2026-10-12",
                "method": "other",
                "method_detail": "Synthetic courier",
                "fda_reference": None,
                "reason": "Wrong method",
            },
        )

        assert [r.status_code for r in (discard, record, amend)] == [200, 200, 200]
        assert override_medwatch_service.discard_draft.await_args.args[2].reason == "Wrong drug"
        assert override_medwatch_service.record_submission.await_args.args[2].method == "fax"
        assert override_medwatch_service.amend_submission.await_args.args[2].reason == (
            "Wrong method"
        )

    @pytest.mark.parametrize(
        ("path", "body"),
        [
            ("discard", {"reason": "   ", "expected_revision": 1}),
            ("discard", {"reason": "x" * 2001, "expected_revision": 1}),
            (
                "submission",
                {
                    "submitted_on": "2026-10-12",
                    "method": "fax",
                    "attested": False,
                    "expected_revision": 1,
                },
            ),
            (
                "submission",
                {
                    "submitted_on": "2999-01-01",
                    "method": "fax",
                    "attested": True,
                    "expected_revision": 1,
                },
            ),
            (
                "submission",
                {
                    "submitted_on": "2026-10-12",
                    "method": "other",
                    "attested": True,
                    "expected_revision": 1,
                },
            ),
            (
                "submission",
                {
                    "submitted_on": "2026-10-12",
                    "method": "pigeon",
                    "attested": True,
                    "expected_revision": 1,
                },
            ),
            (
                "submission/amend",
                {
                    "amends_id": str(uuid4()),
                    "submitted_on": "2026-10-12",
                    "method": "fax",
                    "reason": " ",
                },
            ),
        ],
    )
    def test_invalid_record_requests_are_422(
        self, client, override_auth, override_medwatch_service, path, body
    ):
        response = client.post(f"{_DRAFTS}/{uuid4()}/{path}", json=body)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert override_medwatch_service.method_calls == []

    def test_no_pdf_bytes_when_the_export_audit_fails(self, client, override_auth, clinician_id):
        from tests.unit.services.medwatch_fake_db import api_error, seeded

        draft_id = str(uuid4())
        db = seeded()
        for team in db.tables["care_teams"]:
            team["clinician_id"] = str(clinician_id)
        db.tables["medwatch_drafts"] = [
            {
                **_medwatch_draft_payload(
                    draft_id=draft_id, patient_id=db.tables["patients"][0]["id"]
                ),
                "status": "reviewed",
                "approved_by": str(clinician_id),
                "approved_at": "2026-10-12T18:00:00+00:00",
                "discarded_at": None,
            }
        ]
        db.errors["record_medwatch_draft_export"] = api_error("XX000")
        app.dependency_overrides[_get_medwatch_service] = lambda: MedWatchService(db)

        response = client.get(f"{_DRAFTS}/{draft_id}/export.pdf")

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert response.headers["content-type"].startswith("application/json")
        assert b"%PDF" not in response.content
        assert "SECRET" not in response.text
        assert [name for name, _ in db.rpc_calls] == ["record_medwatch_draft_export"]


class TestAuthorization:
    """Test authorization requirements."""

    def test_no_auth_header(self, client):
        """Reject request without authorization header."""
        response = client.get("/api/v1/clinicians/me")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_token(self, client):
        """Reject request with invalid token."""
        response = client.get(
            "/api/v1/clinicians/me", headers={"Authorization": "Bearer invalid-token"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
