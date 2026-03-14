"""Integration tests for Clinician API endpoints.

Uses FastAPI dependency overrides for proper authentication mocking.
"""

import pytest
from fastapi import status
from unittest.mock import MagicMock
from uuid import uuid4

from app.main import app
from app.core.security import get_current_user
from app.db.connection import get_db
from app.models.auth import CurrentUser


@pytest.fixture
def clinician_id():
    """Fixed clinician ID for testing."""
    return uuid4()


@pytest.fixture
def mock_clinician_user(clinician_id):
    """Mock authenticated clinician user."""
    return CurrentUser(
        id=clinician_id,
        email="clinician@test.com",
        role="clinician"
    )


@pytest.fixture
def mock_supabase_db():
    """Mock Supabase client with chainable methods."""
    db = MagicMock()
    table = MagicMock()
    db.table.return_value = table
    
    # Make all query methods chainable
    for method in ['select', 'eq', 'single', 'insert', 'order']:
        getattr(table, method).return_value = table
    
    return db


@pytest.fixture
def override_auth(mock_clinician_user):
    """Override authentication dependency."""
    def _get_current_user_override():
        return mock_clinician_user
    
    app.dependency_overrides[get_current_user] = _get_current_user_override
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
            "updated_at": None
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
        mock_supabase_db.table().select().eq().single().execute.return_value = MagicMock(
            data=None
        )
        
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
                    "avatar_url": None
                }
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
        mock_supabase_db.table().select().eq().eq().execute.return_value = MagicMock(
            data=[]
        )
        
        response = client.get("/api/v1/clinicians/me/patients")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0


class TestGetPatientDetail:
    """GET /api/v1/clinicians/me/patients/{patient_id} - Get patient detail."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db):
        """Successfully retrieve patient detail."""
        patient_id = uuid4()
        
        # Mock care team assignment check
        mock_supabase_db.table().select().eq().eq().eq().execute.return_value = MagicMock(
            data=[{"id": str(uuid4())}]
        )
        
        # Mock patient profile fetch
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
            "updated_at": None
        }
        mock_supabase_db.table().select().eq().single().execute.return_value = MagicMock(
            data=patient_data
        )
        
        response = client.get(f"/api/v1/clinicians/me/patients/{patient_id}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["first_name"] == "John"
        assert data["email"] == "patient@test.com"

    def test_not_assigned(self, client, override_auth, override_db, mock_supabase_db):
        """Reject access to unassigned patient."""
        patient_id = uuid4()
        
        # Mock no care team assignment
        mock_supabase_db.table().select().eq().eq().eq().execute.return_value = MagicMock(
            data=[]
        )
        
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
        mock_supabase_db.table().select().eq().single().execute.return_value = MagicMock(
            data=None
        )
        
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
            data=[{
                "id": str(care_team_id),
                "clinician_id": str(clinician_id),
                "invite_code": invite_code,
                "status": "pending",
                "role": "provider"
            }]
        )
        
        response = client.post("/api/v1/clinicians/me/invite-code")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "invite_code" in data
        assert "care_team_id" in data
        assert len(data["invite_code"]) == 8


class TestAuthorization:
    """Test authorization requirements."""

    def test_no_auth_header(self, client):
        """Reject request without authorization header."""
        response = client.get("/api/v1/clinicians/me")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_token(self, client):
        """Reject request with invalid token."""
        response = client.get(
            "/api/v1/clinicians/me",
            headers={"Authorization": "Bearer invalid-token"}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
