"""Integration tests for middleware and exception handlers.

Tests CORS middleware and global exception handling.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import status

from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser


@pytest.fixture
def mock_patient_user():
    """Mock authenticated patient user."""
    return CurrentUser(
        id="00000000-0000-0000-0000-000000000000", email="patient@test.com", role="patient"
    )


@pytest.fixture
def override_auth(mock_patient_user):
    """Override authentication dependency."""

    def _get_current_user_override():
        return mock_patient_user

    app.dependency_overrides[get_current_user] = _get_current_user_override
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def mock_supabase_db():
    """Mock Supabase client."""
    db = MagicMock()
    table = MagicMock()
    db.table.return_value = table

    for method in ["select", "eq", "single"]:
        getattr(table, method).return_value = table

    return db


@pytest.fixture
def override_db(mock_supabase_db):
    """Override database dependency."""

    def _get_db_override():
        return mock_supabase_db

    app.dependency_overrides[get_db] = _get_db_override
    yield
    app.dependency_overrides.clear()


class TestCORSMiddleware:
    """Test CORS middleware configuration."""

    def test_cors_headers_present(self, client):
        """Verify CORS headers are added to responses."""
        response = client.options(
            "/api/v1/patients/me",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

        # CORS preflight should return 200
        assert response.status_code == status.HTTP_200_OK

        # Check CORS headers
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers
        assert "access-control-allow-headers" in response.headers

    def test_cors_allows_credentials(self, client):
        """Verify credentials are allowed."""
        response = client.options(
            "/api/v1/patients/me",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
        )

        assert "access-control-allow-credentials" in response.headers
        assert response.headers["access-control-allow-credentials"] == "true"

    def test_cors_allows_all_methods(self, client):
        """Verify all HTTP methods are allowed."""
        response = client.options(
            "/api/v1/patients/me",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "DELETE"},
        )

        assert response.status_code == status.HTTP_200_OK
        allowed_methods = response.headers.get("access-control-allow-methods", "")
        # Should allow all methods (*)
        assert len(allowed_methods) > 0


class TestExceptionHandlers:
    """Test global exception handlers."""

    def test_not_found_error_handler(self, client, override_auth, override_db, mock_supabase_db):
        """Test NotFoundError returns 404 with proper format."""
        # Mock patient not found
        mock_supabase_db.table().select().eq().single().execute.return_value = MagicMock(data=None)

        response = client.get("/api/v1/patients/me")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]

    def test_authentication_error_handler(self, client):
        """Test AuthenticationError returns 401 with proper format."""
        # No auth header
        response = client.get("/api/v1/patients/me")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.json()
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]

    def test_validation_error_handler(self, client, override_auth, override_db):
        """Test ValidationError returns 422 with proper format."""
        # Invalid gender value
        response = client.put("/api/v1/patients/me", json={"gender": "invalid_value"})

        assert response.status_code == 422
        data = response.json()
        # Pydantic validation errors have a different format
        assert "detail" in data or "error" in data

    def test_authorization_error_handler(
        self, client, override_auth, override_db, mock_supabase_db
    ):
        """Test AuthorizationError returns 403 with proper format."""
        from uuid import uuid4

        # Mock no care team assignment (authorization failure)
        mock_supabase_db.table().select().eq().eq().eq().execute.return_value = MagicMock(data=[])

        # Try to access patient detail without assignment
        patient_id = uuid4()

        # Override auth to be a clinician
        clinician_user = CurrentUser(id=uuid4(), email="clinician@test.com", role="clinician")

        def _get_clinician_override():
            return clinician_user

        app.dependency_overrides[get_current_user] = _get_clinician_override

        response = client.get(f"/api/v1/clinicians/me/patients/{patient_id}")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]

        # Clean up
        app.dependency_overrides.clear()

    def test_error_response_format_consistency(self, client):
        """Test all error responses follow consistent format."""
        # Test 401
        response_401 = client.get("/api/v1/patients/me")
        assert response_401.status_code == 401
        data_401 = response_401.json()
        assert "error" in data_401
        assert "code" in data_401["error"]
        assert "message" in data_401["error"]

        # Test 404 (non-existent endpoint)
        response_404 = client.get("/api/v1/nonexistent")
        assert response_404.status_code == 404


class TestHealthEndpoints:
    """Test health check and version endpoints."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "mediagent-backend"

    def test_version_endpoint(self, client):
        """Test version endpoint."""
        response = client.get("/version")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "version" in data
        assert data["service"] == "mediagent-backend"

    def test_health_no_auth_required(self, client):
        """Verify health endpoint doesn't require authentication."""
        # Should work without any auth headers
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK

    def test_version_no_auth_required(self, client):
        """Verify version endpoint doesn't require authentication."""
        # Should work without any auth headers
        response = client.get("/version")
        assert response.status_code == status.HTTP_200_OK
