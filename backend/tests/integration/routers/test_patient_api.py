"""Integration tests for Patient API endpoints.

Uses FastAPI dependency overrides for proper authentication mocking.
"""

import pytest
from fastapi import status
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.main import app
from app.core.security import get_current_user
from app.db.connection import get_db
from app.models.auth import CurrentUser


@pytest.fixture
def patient_id():
    """Fixed patient ID for testing."""
    return uuid4()


@pytest.fixture
def mock_patient_user(patient_id):
    """Mock authenticated patient user."""
    return CurrentUser(
        id=patient_id,
        email="patient@test.com",
        role="patient"
    )


@pytest.fixture
def mock_supabase_db():
    """Mock Supabase client with chainable methods."""
    db = MagicMock()
    table = MagicMock()
    db.table.return_value = table
    
    # Make all query methods chainable
    for method in ['select', 'eq', 'single', 'update', 'insert', 'is_', 'order', 'gte']:
        getattr(table, method).return_value = table
    
    return db


@pytest.fixture
def override_auth(mock_patient_user):
    """Override authentication dependency."""
    def _get_current_user_override():
        return mock_patient_user
    
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
    """GET /api/v1/patients/me - Get patient profile."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully retrieve patient profile."""
        profile_data = {
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
            data=profile_data
        )
        
        response = client.get("/api/v1/patients/me")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == "patient@test.com"
        assert data["first_name"] == "John"
        assert data["last_name"] == "Doe"

    def test_not_found(self, client, override_auth, override_db, mock_supabase_db):
        """Handle patient not found."""
        mock_supabase_db.table().select().eq().single().execute.return_value = MagicMock(
            data=None
        )
        
        response = client.get("/api/v1/patients/me")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestUpdateMyProfile:
    """PUT /api/v1/patients/me - Update patient profile."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully update patient profile."""
        updated_data = {
            "id": str(patient_id),
            "email": "patient@test.com",
            "first_name": "Jane",
            "last_name": "Doe",
            "date_of_birth": "1990-01-15",
            "gender": "male",
            "preferred_language": "en",
            "phone": "+9876543210",
            "avatar_url": None,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-15T00:00:00Z"
        }
        
        mock_supabase_db.table().update().eq().execute.return_value = MagicMock(
            data=[updated_data]
        )
        
        response = client.put(
            "/api/v1/patients/me",
            json={"first_name": "Jane", "phone": "+9876543210"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["first_name"] == "Jane"
        assert data["phone"] == "+9876543210"

    def test_partial_update(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Update only specific fields."""
        updated_data = {
            "id": str(patient_id),
            "email": "patient@test.com",
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "1990-01-15",
            "gender": "male",
            "preferred_language": "es",
            "phone": None,
            "avatar_url": None,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-15T00:00:00Z"
        }
        
        mock_supabase_db.table().update().eq().execute.return_value = MagicMock(
            data=[updated_data]
        )
        
        response = client.put(
            "/api/v1/patients/me",
            json={"preferred_language": "es"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["preferred_language"] == "es"

    def test_invalid_gender(self, client, override_auth, override_db):
        """Reject invalid gender value."""
        response = client.put(
            "/api/v1/patients/me",
            json={"gender": "invalid_gender"}
        )
        
        assert response.status_code == 422


class TestGetMyCareTeam:
    """GET /api/v1/patients/me/care-team - List care team."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db):
        """Successfully retrieve care team."""
        care_team_data = [
            {
                "id": str(uuid4()),
                "patient_id": str(uuid4()),
                "clinician_id": str(uuid4()),
                "status": "active",
                "role": "provider",
                "created_at": "2025-01-01T00:00:00Z",
                "clinicians": {
                    "first_name": "Dr. Sarah",
                    "last_name": "Smith",
                    "specialty": "Cardiology",
                    "clinic_name": "Heart Health Clinic"
                }
            }
        ]
        
        mock_supabase_db.table().select().eq().eq().execute.return_value = MagicMock(
            data=care_team_data
        )
        
        response = client.get("/api/v1/patients/me/care-team")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_empty_care_team(self, client, override_auth, override_db, mock_supabase_db):
        """Handle empty care team."""
        mock_supabase_db.table().select().eq().eq().execute.return_value = MagicMock(
            data=[]
        )
        
        response = client.get("/api/v1/patients/me/care-team")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0


class TestJoinClinic:
    """POST /api/v1/patients/me/care-team/join - Join clinic via invite code."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully join clinic with valid invite code."""
        care_team_id = uuid4()
        clinician_id = uuid4()
        
        # Mock finding the pending invite - .single() returns dict directly
        invite_data = {
            "id": str(care_team_id),
            "clinician_id": str(clinician_id),
            "invite_code": "ABC123",
            "status": "pending",
            "patient_id": None,
            "role": "provider",
            "created_at": "2025-01-01T00:00:00Z"
        }
        
        # Create separate mock chains for the two different queries
        # First query: select().eq().eq().is_().single() - finding the invite
        find_mock = MagicMock()
        find_mock.execute.return_value = MagicMock(data=invite_data)
        
        # Second query: update().eq() - updating the invite
        # Must include all CareTeamRead fields
        updated_data = {
            "id": str(care_team_id),
            "patient_id": str(patient_id),
            "clinician_id": str(clinician_id),
            "clinician_first_name": "Dr. Sarah",
            "clinician_last_name": "Smith",
            "role": "provider",
            "specialty_context": "Cardiology",
            "clinic_name": "Heart Health Clinic",
            "status": "active",
            "created_at": "2025-01-01T00:00:00Z"
        }
        update_mock = MagicMock()
        update_mock.execute.return_value = MagicMock(data=[updated_data])
        
        # Configure the table mock to return different chains based on method
        def table_side_effect(*args):
            table_mock = MagicMock()
            # For select chain
            select_chain = MagicMock()
            select_chain.eq.return_value.eq.return_value.is_.return_value.single.return_value = find_mock
            table_mock.select.return_value = select_chain
            # For update chain
            update_chain = MagicMock()
            update_chain.eq.return_value = update_mock
            table_mock.update.return_value = update_chain
            return table_mock
        
        mock_supabase_db.table.side_effect = table_side_effect
        
        response = client.post("/api/v1/patients/me/care-team/join?invite_code=ABC123")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "active"
        assert data["clinician_first_name"] == "Dr. Sarah"

    def test_invalid_code(self, client, override_auth, override_db, mock_supabase_db):
        """Reject invalid invite code."""
        # Mock raises exception when no data found
        from app.core.exceptions import ValidationError
        mock_supabase_db.table().select().eq().eq().is_().single().execute.return_value = MagicMock(
            data=None
        )
        
        response = client.post("/api/v1/patients/me/care-team/join?invite_code=INVALID")
        
        # ValidationError is caught and returns 400
        assert response.status_code in [400, 422]


class TestAuthorization:
    """Test authorization requirements."""

    def test_no_auth_header(self, client):
        """Reject request without authorization header."""
        response = client.get("/api/v1/patients/me")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_token(self, client):
        """Reject request with invalid token."""
        response = client.get(
            "/api/v1/patients/me",
            headers={"Authorization": "Bearer invalid-token"}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
