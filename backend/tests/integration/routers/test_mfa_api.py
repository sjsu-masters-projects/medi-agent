"""Integration tests for MFA API endpoints."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import status

from app.core.security import get_current_user
from app.main import app
from app.models.auth import CurrentUser
from app.routers.mfa import _extract_token, _get_mfa_service
from app.services.mfa_service import MFAService


@pytest.fixture
def mock_clinician_user():
    return CurrentUser(id=uuid4(), email="doc@test.com", role="clinician")


@pytest.fixture
def mock_mfa_service():
    return MagicMock(spec=MFAService)


@pytest.fixture(autouse=True)
def override_deps(mock_clinician_user, mock_mfa_service):
    app.dependency_overrides[get_current_user] = lambda: mock_clinician_user
    app.dependency_overrides[_get_mfa_service] = lambda: mock_mfa_service
    app.dependency_overrides[_extract_token] = lambda: "fake-jwt-token"
    yield
    app.dependency_overrides.clear()


class TestMFAEnroll:
    @pytest.mark.asyncio
    async def test_success(self, client, mock_mfa_service):
        mock_mfa_service.enroll.return_value = {
            "factor_id": "factor-123",
            "totp": {
                "qr_code": "data:image/png;base64,abc",
                "secret": "JBSWY3DPEHPK3PXP",
                "uri": "otpauth://totp/MediAgent?secret=JBSWY3DPEHPK3PXP",
            },
            "friendly_name": "Authenticator",
        }

        response = client.post(
            "/api/v1/auth/mfa/enroll",
            json={"friendly_name": "Authenticator"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["factor_id"] == "factor-123"
        assert "qr_code" in data["totp"]


class TestMFAVerify:
    @pytest.mark.asyncio
    async def test_success(self, client, mock_mfa_service):
        mock_mfa_service.verify.return_value = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "token_type": "bearer",
        }

        response = client.post(
            "/api/v1/auth/mfa/verify",
            json={"factor_id": "factor-123", "code": "123456"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["access_token"] == "new-access"

    @pytest.mark.asyncio
    async def test_invalid_code_format(self, client):
        response = client.post(
            "/api/v1/auth/mfa/verify",
            json={"factor_id": "factor-123", "code": "abc"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestMFAListFactors:
    @pytest.mark.asyncio
    async def test_success(self, client, mock_mfa_service):
        mock_mfa_service.list_factors.return_value = [
            {
                "id": "factor-1",
                "friendly_name": "My Phone",
                "factor_type": "totp",
                "status": "verified",
                "created_at": "2025-01-01T00:00:00Z",
            }
        ]

        response = client.get("/api/v1/auth/mfa/factors")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["factors"]) == 1
        assert data["factors"][0]["status"] == "verified"


class TestMFAUnenroll:
    @pytest.mark.asyncio
    async def test_success(self, client, mock_mfa_service):
        mock_mfa_service.unenroll.return_value = {
            "status": "removed",
            "factor_id": "factor-123",
        }

        response = client.post(
            "/api/v1/auth/mfa/unenroll",
            json={"factor_id": "factor-123"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "removed"
