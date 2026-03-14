"""Integration tests for Medication API endpoints.

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
    for method in ['select', 'eq', 'single', 'insert', 'update', 'order']:
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


class TestListMedications:
    """GET /api/v1/medications/ - List medications."""

    def test_success_active_only(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully retrieve active medications."""
        medications_data = [
            {
                "id": str(uuid4()),
                "patient_id": str(patient_id),
                "name": "Lisinopril",
                "generic_name": "lisinopril",
                "rxcui": "104383",
                "dosage": "10mg",
                "frequency": "once daily",
                "route": "oral",
                "prescribed_by_care_team_id": None,
                "start_date": "2025-01-01",
                "end_date": None,
                "instructions": "Take in the morning",
                "source_document_id": None,
                "is_active": True,
                "created_at": "2025-01-01T00:00:00Z"
            },
            {
                "id": str(uuid4()),
                "patient_id": str(patient_id),
                "name": "Metformin",
                "generic_name": "metformin",
                "rxcui": "6809",
                "dosage": "500mg",
                "frequency": "twice daily",
                "route": "oral",
                "prescribed_by_care_team_id": None,
                "start_date": "2025-01-01",
                "end_date": None,
                "instructions": "Take with meals",
                "source_document_id": None,
                "is_active": True,
                "created_at": "2025-01-01T00:00:00Z"
            }
        ]
        
        mock_supabase_db.table().select().eq().order().eq().execute.return_value = MagicMock(
            data=medications_data
        )
        
        response = client.get("/api/v1/medications/?active_only=true")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["name"] == "Lisinopril"

    def test_success_all_medications(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully retrieve all medications including inactive."""
        medications_data = [
            {
                "id": str(uuid4()),
                "patient_id": str(patient_id),
                "name": "Lisinopril",
                "generic_name": "lisinopril",
                "rxcui": "104383",
                "dosage": "10mg",
                "frequency": "once daily",
                "route": "oral",
                "prescribed_by_care_team_id": None,
                "start_date": "2025-01-01",
                "end_date": None,
                "instructions": None,
                "source_document_id": None,
                "is_active": True,
                "created_at": "2025-01-01T00:00:00Z"
            },
            {
                "id": str(uuid4()),
                "patient_id": str(patient_id),
                "name": "Old Medication",
                "generic_name": None,
                "rxcui": None,
                "dosage": "5mg",
                "frequency": "once daily",
                "route": "oral",
                "prescribed_by_care_team_id": None,
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "instructions": None,
                "source_document_id": None,
                "is_active": False,
                "created_at": "2024-01-01T00:00:00Z"
            }
        ]
        
        mock_supabase_db.table().select().eq().order().execute.return_value = MagicMock(
            data=medications_data
        )
        
        response = client.get("/api/v1/medications/?active_only=false")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_empty_list(self, client, override_auth, override_db, mock_supabase_db):
        """Handle empty medication list."""
        mock_supabase_db.table().select().eq().order().eq().execute.return_value = MagicMock(
            data=[]
        )
        
        response = client.get("/api/v1/medications/")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0


class TestCreateMedication:
    """POST /api/v1/medications/ - Create medication."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully create medication."""
        medication_id = uuid4()
        medication_data = {
            "id": str(medication_id),
            "patient_id": str(patient_id),
            "name": "Aspirin",
            "generic_name": "aspirin",
            "rxcui": "1191",
            "dosage": "81mg",
            "frequency": "once daily",
            "route": "oral",
            "prescribed_by_care_team_id": None,
            "start_date": "2025-01-15",
            "end_date": None,
            "instructions": "Take with food",
            "source_document_id": None,
            "is_active": True,
            "created_at": "2025-01-15T00:00:00Z"
        }
        
        mock_supabase_db.table().insert().execute.return_value = MagicMock(
            data=[medication_data]
        )
        
        response = client.post(
            "/api/v1/medications/",
            json={
                "name": "Aspirin",
                "generic_name": "aspirin",
                "rxcui": "1191",
                "dosage": "81mg",
                "frequency": "once daily",
                "route": "oral",
                "start_date": "2025-01-15",
                "instructions": "Take with food"
            }
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "Aspirin"
        assert data["dosage"] == "81mg"

    def test_minimal_fields(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Create medication with only required fields."""
        medication_id = uuid4()
        medication_data = {
            "id": str(medication_id),
            "patient_id": str(patient_id),
            "name": "Vitamin D",
            "generic_name": None,
            "rxcui": None,
            "dosage": "1000 IU",
            "frequency": "once daily",
            "route": "oral",
            "prescribed_by_care_team_id": None,
            "start_date": None,
            "end_date": None,
            "instructions": None,
            "source_document_id": None,
            "is_active": True,
            "created_at": "2025-01-15T00:00:00Z"
        }
        
        mock_supabase_db.table().insert().execute.return_value = MagicMock(
            data=[medication_data]
        )
        
        response = client.post(
            "/api/v1/medications/",
            json={
                "name": "Vitamin D",
                "dosage": "1000 IU",
                "frequency": "once daily"
            }
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "Vitamin D"

    def test_missing_required_fields(self, client, override_auth, override_db):
        """Reject request with missing required fields."""
        response = client.post(
            "/api/v1/medications/",
            json={
                "name": "Aspirin"
                # Missing dosage and frequency
            }
        )
        
        assert response.status_code == 422


class TestUpdateMedication:
    """PUT /api/v1/medications/{medication_id} - Update medication."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully update medication."""
        medication_id = uuid4()
        updated_data = {
            "id": str(medication_id),
            "patient_id": str(patient_id),
            "name": "Lisinopril",
            "generic_name": "lisinopril",
            "rxcui": "104383",
            "dosage": "20mg",  # Updated
            "frequency": "once daily",
            "route": "oral",
            "prescribed_by_care_team_id": None,
            "start_date": "2025-01-01",
            "end_date": None,
            "instructions": "Take in the morning with water",  # Updated
            "source_document_id": None,
            "is_active": True,
            "created_at": "2025-01-01T00:00:00Z"
        }
        
        mock_supabase_db.table().update().eq().eq().execute.return_value = MagicMock(
            data=[updated_data]
        )
        
        response = client.put(
            f"/api/v1/medications/{medication_id}",
            json={
                "dosage": "20mg",
                "instructions": "Take in the morning with water"
            }
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["dosage"] == "20mg"
        assert data["instructions"] == "Take in the morning with water"

    def test_deactivate_medication(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully deactivate medication."""
        medication_id = uuid4()
        updated_data = {
            "id": str(medication_id),
            "patient_id": str(patient_id),
            "name": "Old Medication",
            "generic_name": None,
            "rxcui": None,
            "dosage": "10mg",
            "frequency": "once daily",
            "route": "oral",
            "prescribed_by_care_team_id": None,
            "start_date": "2024-01-01",
            "end_date": "2025-01-15",
            "instructions": None,
            "source_document_id": None,
            "is_active": False,
            "created_at": "2024-01-01T00:00:00Z"
        }
        
        mock_supabase_db.table().update().eq().eq().execute.return_value = MagicMock(
            data=[updated_data]
        )
        
        response = client.put(
            f"/api/v1/medications/{medication_id}",
            json={
                "is_active": False,
                "end_date": "2025-01-15"
            }
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_active"] is False

    def test_not_found(self, client, override_auth, override_db, mock_supabase_db):
        """Handle medication not found."""
        medication_id = uuid4()
        
        mock_supabase_db.table().update().eq().eq().execute.return_value = MagicMock(
            data=[]
        )
        
        response = client.put(
            f"/api/v1/medications/{medication_id}",
            json={"dosage": "20mg"}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestAuthorization:
    """Test authorization requirements."""

    def test_no_auth_header(self, client):
        """Reject request without authorization header."""
        response = client.get("/api/v1/medications/")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_token(self, client):
        """Reject request with invalid token."""
        response = client.get(
            "/api/v1/medications/",
            headers={"Authorization": "Bearer invalid-token"}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
