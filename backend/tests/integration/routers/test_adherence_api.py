"""Integration tests for Adherence API endpoints.

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
    for method in ['select', 'eq', 'insert', 'gte']:
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


class TestLogAdherence:
    """POST /api/v1/adherence/ - Log adherence event."""

    def test_success_medication_completed(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully log medication taken."""
        medication_id = uuid4()
        log_id = uuid4()
        
        # Mock medication exists check
        mock_supabase_db.table().select().eq().eq().execute.return_value = MagicMock(
            data=[{"id": str(medication_id)}]
        )
        
        # Mock adherence log creation
        log_data = {
            "id": str(log_id),
            "patient_id": str(patient_id),
            "target_type": "medication",
            "target_id": str(medication_id),
            "status": "completed",
            "scheduled_time": "2025-01-15T08:00:00Z",
            "notes": "Took with breakfast",
            "logged_at": "2025-01-15T08:05:00Z"
        }
        mock_supabase_db.table().insert().execute.return_value = MagicMock(
            data=[log_data]
        )
        
        response = client.post(
            "/api/v1/adherence/",
            json={
                "target_type": "medication",
                "target_id": str(medication_id),
                "status": "completed",
                "scheduled_time": "2025-01-15T08:00:00Z",
                "notes": "Took with breakfast"
            }
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["target_type"] == "medication"
        assert data["status"] == "completed"

    def test_success_medication_skipped(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully log medication skipped."""
        medication_id = uuid4()
        log_id = uuid4()
        
        # Mock medication exists check
        mock_supabase_db.table().select().eq().eq().execute.return_value = MagicMock(
            data=[{"id": str(medication_id)}]
        )
        
        # Mock adherence log creation
        log_data = {
            "id": str(log_id),
            "patient_id": str(patient_id),
            "target_type": "medication",
            "target_id": str(medication_id),
            "status": "skipped",
            "scheduled_time": "2025-01-15T08:00:00Z",
            "notes": "Forgot to take",
            "logged_at": "2025-01-15T20:00:00Z"
        }
        mock_supabase_db.table().insert().execute.return_value = MagicMock(
            data=[log_data]
        )
        
        response = client.post(
            "/api/v1/adherence/",
            json={
                "target_type": "medication",
                "target_id": str(medication_id),
                "status": "skipped",
                "scheduled_time": "2025-01-15T08:00:00Z",
                "notes": "Forgot to take"
            }
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["status"] == "skipped"

    def test_success_obligation_completed(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully log obligation completed."""
        obligation_id = uuid4()
        log_id = uuid4()
        
        # Mock obligation exists check
        mock_supabase_db.table().select().eq().eq().execute.return_value = MagicMock(
            data=[{"id": str(obligation_id)}]
        )
        
        # Mock adherence log creation
        log_data = {
            "id": str(log_id),
            "patient_id": str(patient_id),
            "target_type": "obligation",
            "target_id": str(obligation_id),
            "status": "completed",
            "scheduled_time": None,
            "notes": "Completed morning walk",
            "logged_at": "2025-01-15T09:00:00Z"
        }
        mock_supabase_db.table().insert().execute.return_value = MagicMock(
            data=[log_data]
        )
        
        response = client.post(
            "/api/v1/adherence/",
            json={
                "target_type": "obligation",
                "target_id": str(obligation_id),
                "status": "completed",
                "notes": "Completed morning walk"
            }
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["target_type"] == "obligation"

    def test_invalid_target(self, client, override_auth, override_db, mock_supabase_db):
        """Reject log for non-existent target."""
        medication_id = uuid4()
        
        # Mock medication not found
        mock_supabase_db.table().select().eq().eq().execute.return_value = MagicMock(
            data=[]
        )
        
        response = client.post(
            "/api/v1/adherence/",
            json={
                "target_type": "medication",
                "target_id": str(medication_id),
                "status": "completed"
            }
        )
        
        # ValidationError returns 422
        assert response.status_code == 422

    def test_missing_required_fields(self, client, override_auth, override_db):
        """Reject request with missing required fields."""
        response = client.post(
            "/api/v1/adherence/",
            json={
                "target_type": "medication"
                # Missing target_id and status
            }
        )
        
        assert response.status_code == 422


class TestGetAdherenceStats:
    """GET /api/v1/adherence/stats - Get adherence statistics."""

    def test_success_with_data(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully retrieve adherence stats with data."""
        # Mock adherence logs
        logs_data = [
            {
                "id": str(uuid4()),
                "patient_id": str(patient_id),
                "target_type": "medication",
                "target_id": str(uuid4()),
                "status": "completed",
                "logged_at": "2025-01-15T08:00:00Z"
            },
            {
                "id": str(uuid4()),
                "patient_id": str(patient_id),
                "target_type": "medication",
                "target_id": str(uuid4()),
                "status": "completed",
                "logged_at": "2025-01-14T08:00:00Z"
            },
            {
                "id": str(uuid4()),
                "patient_id": str(patient_id),
                "target_type": "obligation",
                "target_id": str(uuid4()),
                "status": "completed",
                "logged_at": "2025-01-15T09:00:00Z"
            }
        ]
        
        # Mock active medications count
        medications_data = [{"id": str(uuid4())}, {"id": str(uuid4())}]
        
        # Mock active obligations count
        obligations_data = [{"id": str(uuid4())}]
        
        # Configure mock to return different data based on table
        def table_side_effect(table_name):
            table_mock = MagicMock()
            if table_name == "adherence_logs":
                table_mock.select().eq().gte().execute.return_value = MagicMock(data=logs_data)
            elif table_name == "medications":
                table_mock.select().eq().eq().execute.return_value = MagicMock(data=medications_data)
            elif table_name == "obligations":
                table_mock.select().eq().eq().execute.return_value = MagicMock(data=obligations_data)
            return table_mock
        
        mock_supabase_db.table.side_effect = table_side_effect
        
        response = client.get("/api/v1/adherence/stats?period_days=30")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "overall_score" in data
        assert "medication_score" in data
        assert "obligation_score" in data
        assert "current_streak_days" in data
        assert data["period_days"] == 30

    def test_success_no_data(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully retrieve stats with no adherence data."""
        # Mock empty logs
        mock_supabase_db.table().select().eq().gte().execute.return_value = MagicMock(
            data=[]
        )
        
        # Mock no active medications or obligations
        mock_supabase_db.table().select().eq().eq().execute.return_value = MagicMock(
            data=[]
        )
        
        response = client.get("/api/v1/adherence/stats")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["overall_score"] == 0.0
        assert data["medication_score"] == 0.0
        assert data["obligation_score"] == 0.0
        assert data["current_streak_days"] == 0

    def test_custom_period(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully retrieve stats with custom period."""
        # Mock empty data for simplicity
        mock_supabase_db.table().select().eq().gte().execute.return_value = MagicMock(
            data=[]
        )
        mock_supabase_db.table().select().eq().eq().execute.return_value = MagicMock(
            data=[]
        )
        
        response = client.get("/api/v1/adherence/stats?period_days=7")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["period_days"] == 7


class TestAuthorization:
    """Test authorization requirements."""

    def test_no_auth_header(self, client):
        """Reject request without authorization header."""
        response = client.get("/api/v1/adherence/stats")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_token(self, client):
        """Reject request with invalid token."""
        response = client.get(
            "/api/v1/adherence/stats",
            headers={"Authorization": "Bearer invalid-token"}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
