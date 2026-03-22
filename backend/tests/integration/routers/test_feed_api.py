"""Integration tests for Feed API endpoints.

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


@pytest.fixture
def patient_id():
    """Fixed patient ID for testing."""
    return uuid4()


@pytest.fixture
def clinician_id():
    """Fixed clinician ID for testing."""
    return uuid4()


@pytest.fixture
def mock_patient_user(patient_id):
    """Mock authenticated patient user."""
    return CurrentUser(id=patient_id, email="patient@test.com", role="patient")


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
    for method in ["select", "eq", "gte", "lt", "execute"]:
        getattr(table, method).return_value = table

    return db


@pytest.fixture
def override_patient_auth(mock_patient_user):
    """Override authentication dependency with patient."""

    def _get_current_user_override():
        return mock_patient_user

    app.dependency_overrides[get_current_user] = _get_current_user_override
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_clinician_auth(mock_clinician_user):
    """Override authentication dependency with clinician."""

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


class TestGetTodayFeed:
    """GET /api/v1/feed/today - Get today's feed."""

    def test_success_with_authenticated_patient(
        self, client, override_patient_auth, override_db, mock_supabase_db, patient_id
    ):
        """Successfully retrieve today's feed for authenticated patient."""
        # Mock medications response
        med_id = str(uuid4())
        medications_data = [
            {
                "id": med_id,
                "name": "Ibuprofen",
                "dosage": "200mg",
                "frequency": "twice daily",
                "instructions": "Take with food",
                "care_teams": {
                    "id": str(uuid4()),
                    "clinicians": {
                        "id": str(uuid4()),
                        "first_name": "Jane",
                        "last_name": "Smith",
                        "specialty": "Primary Care",
                        "clinic_name": "Health Clinic",
                    },
                },
            }
        ]

        # Mock obligations response
        obl_id = str(uuid4())
        obligations_data = [
            {
                "id": obl_id,
                "description": "Morning walk",
                "frequency": "daily",
                "care_teams": {
                    "id": str(uuid4()),
                    "clinicians": {
                        "id": str(uuid4()),
                        "first_name": "John",
                        "last_name": "Doe",
                        "specialty": "Cardiology",
                        "clinic_name": "Heart Center",
                    },
                },
            }
        ]

        # Mock adherence logs response
        adherence_data = [
            {
                "target_id": med_id,
                "target_type": "medication",
                "status": "completed",
                "logged_at": "2024-01-15T08:15:00Z",
                "scheduled_time": "08:00:00",
            }
        ]

        # Setup mock to return different data based on table name
        def table_side_effect(table_name):
            mock_table = MagicMock()
            mock_result = MagicMock()

            if table_name == "medications":
                mock_result.data = medications_data
            elif table_name == "obligations":
                mock_result.data = obligations_data
            elif table_name == "adherence_logs":
                mock_result.data = adherence_data
            else:
                mock_result.data = []

            # Make all methods chainable
            for method in ["select", "eq", "gte", "lt"]:
                getattr(mock_table, method).return_value = mock_table
            mock_table.execute.return_value = mock_result

            return mock_table

        mock_supabase_db.table.side_effect = table_side_effect

        response = client.get("/api/v1/feed/today")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert "date" in data
        assert "timezone" in data
        assert "tasks" in data
        assert "summary" in data

        # Verify tasks
        assert len(data["tasks"]) == 2
        assert data["summary"]["total"] == 2
        assert data["summary"]["completed"] == 1
        assert data["summary"]["pending"] == 1

    def test_success_empty_feed(self, client, override_patient_auth, override_db, mock_supabase_db):
        """Successfully retrieve empty feed when no tasks exist."""

        # Mock empty responses
        def table_side_effect(table_name):
            mock_table = MagicMock()
            mock_result = MagicMock()
            mock_result.data = []

            for method in ["select", "eq", "gte", "lt"]:
                getattr(mock_table, method).return_value = mock_table
            mock_table.execute.return_value = mock_result

            return mock_table

        mock_supabase_db.table.side_effect = table_side_effect

        response = client.get("/api/v1/feed/today")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["tasks"] == []
        assert data["summary"]["total"] == 0
        assert data["summary"]["completed"] == 0
        assert data["summary"]["pending"] == 0

    def test_success_with_multiple_medications(
        self, client, override_patient_auth, override_db, mock_supabase_db
    ):
        """Successfully retrieve feed with multiple medications."""
        medications_data = [
            {
                "id": str(uuid4()),
                "name": "Ibuprofen",
                "dosage": "200mg",
                "frequency": "twice daily",
                "instructions": "Take with food",
                "care_teams": None,
            },
            {
                "id": str(uuid4()),
                "name": "Aspirin",
                "dosage": "81mg",
                "frequency": "daily",
                "instructions": None,
                "care_teams": None,
            },
            {
                "id": str(uuid4()),
                "name": "Lisinopril",
                "dosage": "10mg",
                "frequency": "once daily",
                "instructions": "Take in morning",
                "care_teams": None,
            },
        ]

        def table_side_effect(table_name):
            mock_table = MagicMock()
            mock_result = MagicMock()

            if table_name == "medications":
                mock_result.data = medications_data
            else:
                mock_result.data = []

            for method in ["select", "eq", "gte", "lt"]:
                getattr(mock_table, method).return_value = mock_table
            mock_table.execute.return_value = mock_result

            return mock_table

        mock_supabase_db.table.side_effect = table_side_effect

        response = client.get("/api/v1/feed/today")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data["tasks"]) == 3
        assert all(task["type"] == "medication" for task in data["tasks"])

    def test_success_with_multiple_obligations(
        self, client, override_patient_auth, override_db, mock_supabase_db
    ):
        """Successfully retrieve feed with multiple obligations."""
        obligations_data = [
            {
                "id": str(uuid4()),
                "description": "Morning walk",
                "frequency": "daily",
                "care_teams": None,
            },
            {
                "id": str(uuid4()),
                "description": "Blood pressure check",
                "frequency": "twice daily",
                "care_teams": None,
            },
        ]

        def table_side_effect(table_name):
            mock_table = MagicMock()
            mock_result = MagicMock()

            if table_name == "obligations":
                mock_result.data = obligations_data
            else:
                mock_result.data = []

            for method in ["select", "eq", "gte", "lt"]:
                getattr(mock_table, method).return_value = mock_table
            mock_table.execute.return_value = mock_result

            return mock_table

        mock_supabase_db.table.side_effect = table_side_effect

        response = client.get("/api/v1/feed/today")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data["tasks"]) == 2
        assert all(task["type"] == "obligation" for task in data["tasks"])

    def test_success_with_mixed_completed_pending_tasks(
        self, client, override_patient_auth, override_db, mock_supabase_db
    ):
        """Successfully retrieve feed with mixed task statuses."""
        med_id_1 = str(uuid4())
        med_id_2 = str(uuid4())
        obl_id = str(uuid4())

        medications_data = [
            {
                "id": med_id_1,
                "name": "Ibuprofen",
                "dosage": "200mg",
                "frequency": "twice daily",
                "instructions": None,
                "care_teams": None,
            },
            {
                "id": med_id_2,
                "name": "Aspirin",
                "dosage": "81mg",
                "frequency": "daily",
                "instructions": None,
                "care_teams": None,
            },
        ]

        obligations_data = [
            {
                "id": obl_id,
                "description": "Morning walk",
                "frequency": "daily",
                "care_teams": None,
            }
        ]

        adherence_data = [
            {
                "target_id": med_id_1,
                "target_type": "medication",
                "status": "completed",
                "logged_at": "2024-01-15T08:15:00Z",
                "scheduled_time": "08:00:00",
            },
            {
                "target_id": obl_id,
                "target_type": "obligation",
                "status": "skipped",
                "logged_at": "2024-01-15T07:00:00Z",
                "scheduled_time": "07:00:00",
            },
        ]

        def table_side_effect(table_name):
            mock_table = MagicMock()
            mock_result = MagicMock()

            if table_name == "medications":
                mock_result.data = medications_data
            elif table_name == "obligations":
                mock_result.data = obligations_data
            elif table_name == "adherence_logs":
                mock_result.data = adherence_data
            else:
                mock_result.data = []

            for method in ["select", "eq", "gte", "lt"]:
                getattr(mock_table, method).return_value = mock_table
            mock_table.execute.return_value = mock_result

            return mock_table

        mock_supabase_db.table.side_effect = table_side_effect

        response = client.get("/api/v1/feed/today")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["summary"]["total"] == 3
        assert data["summary"]["completed"] == 1
        assert data["summary"]["pending"] == 1
        assert data["summary"]["skipped"] == 1

    def test_success_with_multiple_providers(
        self, client, override_patient_auth, override_db, mock_supabase_db
    ):
        """Successfully retrieve feed with tasks from multiple providers."""
        medications_data = [
            {
                "id": str(uuid4()),
                "name": "Ibuprofen",
                "dosage": "200mg",
                "frequency": "twice daily",
                "instructions": None,
                "care_teams": {
                    "id": str(uuid4()),
                    "clinicians": {
                        "id": str(uuid4()),
                        "first_name": "Jane",
                        "last_name": "Smith",
                        "specialty": "Primary Care",
                        "clinic_name": "Health Clinic",
                    },
                },
            },
            {
                "id": str(uuid4()),
                "name": "Aspirin",
                "dosage": "81mg",
                "frequency": "daily",
                "instructions": None,
                "care_teams": {
                    "id": str(uuid4()),
                    "clinicians": {
                        "id": str(uuid4()),
                        "first_name": "John",
                        "last_name": "Doe",
                        "specialty": "Cardiology",
                        "clinic_name": "Heart Center",
                    },
                },
            },
        ]

        def table_side_effect(table_name):
            mock_table = MagicMock()
            mock_result = MagicMock()

            if table_name == "medications":
                mock_result.data = medications_data
            else:
                mock_result.data = []

            for method in ["select", "eq", "gte", "lt"]:
                getattr(mock_table, method).return_value = mock_table
            mock_table.execute.return_value = mock_result

            return mock_table

        mock_supabase_db.table.side_effect = table_side_effect

        response = client.get("/api/v1/feed/today")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data["tasks"]) == 2
        assert data["tasks"][0]["provider"]["name"] == "Dr. Jane Smith"
        assert data["tasks"][1]["provider"]["name"] == "Dr. John Doe"

    def test_success_with_self_reported_tasks(
        self, client, override_patient_auth, override_db, mock_supabase_db
    ):
        """Successfully retrieve feed with self-reported tasks (no provider)."""
        medications_data = [
            {
                "id": str(uuid4()),
                "name": "Vitamin D",
                "dosage": "1000 IU",
                "frequency": "daily",
                "instructions": None,
                "care_teams": None,
            }
        ]

        def table_side_effect(table_name):
            mock_table = MagicMock()
            mock_result = MagicMock()

            if table_name == "medications":
                mock_result.data = medications_data
            else:
                mock_result.data = []

            for method in ["select", "eq", "gte", "lt"]:
                getattr(mock_table, method).return_value = mock_table
            mock_table.execute.return_value = mock_result

            return mock_table

        mock_supabase_db.table.side_effect = table_side_effect

        response = client.get("/api/v1/feed/today")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["provider"] is None

    def test_success_with_date_parameter(
        self, client, override_patient_auth, override_db, mock_supabase_db
    ):
        """Successfully retrieve feed with custom date parameter."""

        def table_side_effect(table_name):
            mock_table = MagicMock()
            mock_result = MagicMock()
            mock_result.data = []

            for method in ["select", "eq", "gte", "lt"]:
                getattr(mock_table, method).return_value = mock_table
            mock_table.execute.return_value = mock_result

            return mock_table

        mock_supabase_db.table.side_effect = table_side_effect

        response = client.get("/api/v1/feed/today?date=2024-01-15")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["date"] == "2024-01-15"

    def test_error_invalid_date_format(self, client, override_patient_auth, override_db):
        """Return 400 for invalid date format."""
        response = client.get("/api/v1/feed/today?date=invalid-date")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid date format" in response.json()["detail"]

    def test_error_non_patient_user(self, client, override_clinician_auth, override_db):
        """Return 403 for non-patient user."""
        response = client.get("/api/v1/feed/today")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Only patients can access the feed" in response.json()["detail"]

    def test_error_unauthenticated_user(self, client):
        """Return 401 for unauthenticated user."""
        response = client.get("/api/v1/feed/today")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_response_format_matches_model(
        self, client, override_patient_auth, override_db, mock_supabase_db
    ):
        """Verify response format matches TodayFeedResponse model."""
        med_id = str(uuid4())
        medications_data = [
            {
                "id": med_id,
                "name": "Ibuprofen",
                "dosage": "200mg",
                "frequency": "twice daily",
                "instructions": "Take with food",
                "care_teams": {
                    "id": str(uuid4()),
                    "clinicians": {
                        "id": str(uuid4()),
                        "first_name": "Jane",
                        "last_name": "Smith",
                        "specialty": "Primary Care",
                        "clinic_name": "Health Clinic",
                    },
                },
            }
        ]

        def table_side_effect(table_name):
            mock_table = MagicMock()
            mock_result = MagicMock()

            if table_name == "medications":
                mock_result.data = medications_data
            else:
                mock_result.data = []

            for method in ["select", "eq", "gte", "lt"]:
                getattr(mock_table, method).return_value = mock_table
            mock_table.execute.return_value = mock_result

            return mock_table

        mock_supabase_db.table.side_effect = table_side_effect

        response = client.get("/api/v1/feed/today")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify top-level structure
        assert "date" in data
        assert "timezone" in data
        assert "tasks" in data
        assert "summary" in data

        # Verify task structure
        task = data["tasks"][0]
        assert "id" in task
        assert "type" in task
        assert "target_id" in task
        assert "name" in task
        assert "description" in task
        assert "frequency" in task
        assert "scheduled_time" in task
        assert "status" in task
        assert "completed_at" in task
        assert "provider" in task

        # Verify provider structure
        assert "id" in task["provider"]
        assert "name" in task["provider"]
        assert "specialty" in task["provider"]
        assert "clinic_name" in task["provider"]

        # Verify summary structure
        summary = data["summary"]
        assert "total" in summary
        assert "completed" in summary
        assert "pending" in summary
        assert "skipped" in summary
        assert "missed" in summary
