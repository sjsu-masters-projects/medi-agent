"""Integration tests for Document API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch
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
def mock_patient_user(patient_id):
    """Mock authenticated patient user."""
    return CurrentUser(id=patient_id, email="patient@test.com", role="patient")


@pytest.fixture
def mock_supabase_db():
    """Mock Supabase client with chainable methods and storage."""
    db = MagicMock()
    table = MagicMock()
    db.table.return_value = table

    # Make all query methods chainable
    for method in ["select", "eq", "single", "insert", "order", "delete", "in_"]:
        getattr(table, method).return_value = table

    # Mock storage
    storage = MagicMock()
    bucket = MagicMock()
    bucket.create_signed_url.return_value = {"signedURL": "https://storage.example.com/signed-url"}
    bucket.remove.return_value = []
    storage.from_.return_value = bucket
    db.storage = storage

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


class TestCreateDocument:
    """POST /api/v1/documents/ - Register uploaded document."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully create document metadata."""
        document_id = uuid4()
        document_data = {
            "id": str(document_id),
            "patient_id": str(patient_id),
            "uploaded_by": str(patient_id),
            "uploaded_by_role": "patient",
            "file_name": "lab-results.pdf",
            "file_url": "https://storage.example.com/signed-url",
            "file_path": f"{patient_id}/lab-results.pdf",
            "file_size_bytes": 1024000,
            "mime_type": "application/pdf",
            "document_type": "lab_report",
            "source_clinic": "Test Clinic",
            "notes": "Annual checkup results",
            "parsed": False,
            "ai_summary": None,
            "parse_status": "pending",
            "parse_error": None,
            "parse_attempts": 0,
            "visibility": "all_providers",
            "created_at": "2025-01-15T00:00:00Z",
        }

        mock_supabase_db.table().insert().execute.return_value = MagicMock(data=[document_data])

        with patch(
            "app.routers.documents._run_ingestion_safe",
            new=AsyncMock(),
        ) as mock_ingest:
            response = client.post(
                "/api/v1/documents/",
                json={
                    "file_name": "lab-results.pdf",
                    "file_path": f"{patient_id}/lab-results.pdf",
                    "file_size_bytes": 1024000,
                    "mime_type": "application/pdf",
                    "document_type": "lab_report",
                    "source_clinic": "Test Clinic",
                    "notes": "Annual checkup results",
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["file_name"] == "lab-results.pdf"
        assert data["document_type"] == "lab_report"
        assert "file_url" in data
        assert data["parse_status"] == "pending"
        mock_ingest.assert_awaited_once()

    def test_invalid_mime_type(self, client, override_auth, override_db):
        """Reject unsupported file type."""
        response = client.post(
            "/api/v1/documents/",
            json={
                "file_name": "document.exe",
                "file_path": "path/to/document.exe",
                "file_size_bytes": 1024,
                "mime_type": "application/x-msdownload",
                "document_type": "other",
            },
        )

        # ValidationError returns 422 for invalid data
        assert response.status_code == 422

    def test_file_too_large(self, client, override_auth, override_db):
        """Reject oversized file."""
        response = client.post(
            "/api/v1/documents/",
            json={
                "file_name": "huge-file.pdf",
                "file_path": "path/to/huge-file.pdf",
                "file_size_bytes": 25 * 1024 * 1024,  # 25 MB
                "mime_type": "application/pdf",
                "document_type": "other",
            },
        )

        # ValidationError returns 422 for invalid data
        assert response.status_code == 422

    def test_missing_required_fields(self, client, override_auth, override_db):
        """Reject request with missing required fields."""
        response = client.post(
            "/api/v1/documents/",
            json={
                "file_name": "test.pdf"
                # Missing file_path, file_size_bytes, mime_type, document_type
            },
        )

        assert response.status_code == 422


class TestListDocuments:
    """GET /api/v1/documents/ - List my documents."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully retrieve document list."""
        documents_data = [
            {
                "id": str(uuid4()),
                "patient_id": str(patient_id),
                "uploaded_by": str(patient_id),
                "uploaded_by_role": "patient",
                "file_name": "lab-results.pdf",
                "file_path": f"{patient_id}/lab-results.pdf",
                "file_url": "https://storage.example.com/signed-url-1",
                "file_size_bytes": 1024000,
                "mime_type": "application/pdf",
                "document_type": "lab_report",
                "source_clinic": None,
                "parsed": False,
                "ai_summary": None,
                "parse_status": "pending",
                "parse_error": None,
                "parse_attempts": 1,
                "visibility": "all_providers",
                "created_at": "2025-01-15T00:00:00Z",
            },
            {
                "id": str(uuid4()),
                "patient_id": str(patient_id),
                "uploaded_by": str(patient_id),
                "uploaded_by_role": "patient",
                "file_name": "prescription.pdf",
                "file_path": f"{patient_id}/prescription.pdf",
                "file_url": "https://storage.example.com/signed-url-2",
                "file_size_bytes": 512000,
                "mime_type": "application/pdf",
                "document_type": "prescription",
                "source_clinic": "Test Clinic",
                "parsed": True,
                "ai_summary": "Prescription for medication X",
                "parse_status": "completed",
                "parse_error": None,
                "parse_attempts": 1,
                "visibility": "all_providers",
                "created_at": "2025-01-14T00:00:00Z",
            },
        ]

        mock_supabase_db.table().select().eq().order().execute.return_value = MagicMock(
            data=documents_data
        )

        response = client.get("/api/v1/documents/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["file_name"] == "lab-results.pdf"

    def test_empty_list(self, client, override_auth, override_db, mock_supabase_db):
        """Handle empty document list."""
        mock_supabase_db.table().select().eq().order().execute.return_value = MagicMock(data=[])

        response = client.get("/api/v1/documents/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0


class TestGetDocument:
    """GET /api/v1/documents/{document_id} - Get document detail."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully retrieve document detail."""
        document_id = uuid4()
        document_data = {
            "id": str(document_id),
            "patient_id": str(patient_id),
            "uploaded_by": str(patient_id),
            "uploaded_by_role": "patient",
            "file_name": "lab-results.pdf",
            "file_path": f"{patient_id}/lab-results.pdf",
            "file_url": "https://storage.example.com/signed-url",
            "file_size_bytes": 1024000,
            "mime_type": "application/pdf",
            "document_type": "lab_report",
            "source_clinic": None,
            "parsed": False,
            "ai_summary": None,
            "parse_status": "processing",
            "parse_error": None,
            "parse_attempts": 1,
            "visibility": "all_providers",
            "created_at": "2025-01-15T00:00:00Z",
        }

        mock_supabase_db.table().select().eq().eq().single().execute.return_value = MagicMock(
            data=document_data
        )

        response = client.get(f"/api/v1/documents/{document_id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["file_name"] == "lab-results.pdf"
        assert "file_url" in data

    def test_not_found(self, client, override_auth, override_db, mock_supabase_db):
        """Handle document not found."""
        document_id = uuid4()

        mock_supabase_db.table().select().eq().eq().single().execute.return_value = MagicMock(
            data=None
        )

        response = client.get(f"/api/v1/documents/{document_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_wrong_patient(self, client, override_auth, override_db, mock_supabase_db):
        """Reject access to another patient's document."""
        document_id = uuid4()

        mock_supabase_db.table().select().eq().eq().single().execute.return_value = MagicMock(
            data=None  # Query filters by patient_id, so returns None
        )

        response = client.get(f"/api/v1/documents/{document_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestDeleteDocument:
    """DELETE /api/v1/documents/{document_id} - Delete a document."""

    def test_success_removes_document_and_storage_object(
        self, client, override_auth, override_db, mock_supabase_db, patient_id
    ):
        document_id = uuid4()
        medication_id = uuid4()
        obligation_id = uuid4()
        file_path = f"{patient_id}/lab-results.pdf"
        document_data = {
            "id": str(document_id),
            "patient_id": str(patient_id),
            "uploaded_by": str(patient_id),
            "uploaded_by_role": "patient",
            "file_name": "lab-results.pdf",
            "file_path": file_path,
            "file_url": "https://storage.example.com/signed-url",
            "file_size_bytes": 1024000,
            "mime_type": "application/pdf",
            "document_type": "lab_report",
            "source_clinic": None,
            "parsed": False,
            "ai_summary": None,
            "parse_status": "completed",
            "parse_error": None,
            "parse_attempts": 1,
            "visibility": "all_providers",
            "created_at": "2025-01-15T00:00:00Z",
        }
        mock_supabase_db.table().execute.side_effect = [
            MagicMock(data=document_data),
            MagicMock(data=[{"id": str(medication_id)}]),
            MagicMock(data=[{"id": str(obligation_id)}]),
            MagicMock(data=[]),
            MagicMock(data=[]),
            MagicMock(data=[]),
            MagicMock(data=[]),
            MagicMock(data=[]),
            MagicMock(data=[]),
            MagicMock(data=[document_data]),
        ]

        response = client.delete(f"/api/v1/documents/{document_id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_supabase_db.table.assert_any_call("adherence_logs")
        mock_supabase_db.table.assert_any_call("reminder_schedules")
        mock_supabase_db.table.assert_any_call("medications")
        mock_supabase_db.table.assert_any_call("obligations")
        mock_supabase_db.storage.from_.assert_called_with("documents")
        mock_supabase_db.storage.from_().remove.assert_called_once_with([file_path])
        assert mock_supabase_db.table().delete.call_count == 7

    def test_not_found(self, client, override_auth, override_db, mock_supabase_db):
        document_id = uuid4()
        mock_supabase_db.table().execute.return_value = MagicMock(data=None)

        response = client.delete(f"/api/v1/documents/{document_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        mock_supabase_db.table().delete.assert_not_called()


class TestExplainDocument:
    """POST /api/v1/documents/{document_id}/explain - Explain a document."""

    def test_returns_cached_english_summary(
        self, client, override_auth, override_db, mock_supabase_db, patient_id
    ):
        """English explanation returns cached ai_summary without LLM call."""
        document_id = uuid4()
        mock_supabase_db.table().select().eq().eq().single().execute.return_value = MagicMock(
            data={
                "id": str(document_id),
                "patient_id": str(patient_id),
                "uploaded_by": str(patient_id),
                "uploaded_by_role": "patient",
                "file_name": "lab-results.pdf",
                "file_path": f"{patient_id}/lab-results.pdf",
                "file_url": "https://storage.example.com/signed-url",
                "file_size_bytes": 1024000,
                "mime_type": "application/pdf",
                "document_type": "lab_report",
                "source_clinic": None,
                "parsed": True,
                "ai_summary": "Cached summary",
                "parse_status": "completed",
                "parse_error": None,
                "parse_attempts": 1,
                "visibility": "all_providers",
                "created_at": "2025-01-15T00:00:00Z",
            }
        )

        response = client.post(
            f"/api/v1/documents/{document_id}/explain",
            json={"language": "en"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["summary"] == "Cached summary"
        assert data["cached"] is True

    def test_translates_summary(
        self, client, override_auth, override_db, mock_supabase_db, patient_id
    ):
        """Non-English explanation uses the explanation service."""
        document_id = uuid4()
        mock_supabase_db.table().select().eq().eq().single().execute.return_value = MagicMock(
            data={
                "id": str(document_id),
                "patient_id": str(patient_id),
                "uploaded_by": str(patient_id),
                "uploaded_by_role": "patient",
                "file_name": "lab-results.pdf",
                "file_path": f"{patient_id}/lab-results.pdf",
                "file_url": "https://storage.example.com/signed-url",
                "file_size_bytes": 1024000,
                "mime_type": "application/pdf",
                "document_type": "lab_report",
                "source_clinic": None,
                "parsed": True,
                "ai_summary": "English summary",
                "parse_status": "completed",
                "parse_error": None,
                "parse_attempts": 1,
                "visibility": "all_providers",
                "created_at": "2025-01-15T00:00:00Z",
            }
        )

        with patch(
            "app.routers.documents.ExplanationService.explain",
            new=AsyncMock(return_value="Resumen en español"),
        ) as mock_explain:
            response = client.post(
                f"/api/v1/documents/{document_id}/explain",
                json={"language": "es"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["summary"] == "Resumen en español"
        assert data["cached"] is False
        mock_explain.assert_awaited_once()


class TestAuthorization:
    """Test authorization requirements."""

    def test_no_auth_header(self, client):
        """Reject request without authorization header."""
        response = client.get("/api/v1/documents/")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_token(self, client):
        """Reject request with invalid token."""
        response = client.get(
            "/api/v1/documents/", headers={"Authorization": "Bearer invalid-token"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
