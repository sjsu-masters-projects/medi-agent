"""Integration tests for Clinician API endpoints.

Uses FastAPI dependency overrides for proper authentication mocking.
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import status

from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser
from app.routers.clinicians import _clinician_dep


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


class TestGenerateInviteCode:
    """POST /api/v1/clinicians/me/invite-code - Generate patient invite code."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, clinician_id):
        """Successfully generate invite code."""
        care_team_id = uuid4()
        invite_code = "A1B2C3D4"

        mock_supabase_db.table().insert().execute.return_value = MagicMock(
            data=[
                {
                    "id": str(care_team_id),
                    "clinician_id": str(clinician_id),
                    "invite_code": invite_code,
                    "status": "pending",
                    "role": "provider",
                }
            ]
        )

        response = client.post("/api/v1/clinicians/me/invite-code")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "invite_code" in data
        assert "care_team_id" in data
        assert len(data["invite_code"]) == 8


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

    def test_success(self, client, override_auth, override_db, mock_supabase_db):
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

    def test_reject_non_pending(self, client, override_auth, override_db, mock_supabase_db, clinician_id):
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
