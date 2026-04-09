"""Integration tests for Staff API endpoints."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import status

from app.core.security import get_current_user, require_role
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser
from app.services.staff_service import StaffService


@pytest.fixture
def admin_id():
    return uuid4()


@pytest.fixture
def mock_admin_user(admin_id):
    return CurrentUser(id=admin_id, email="admin@clinic.com", role="clinician")


@pytest.fixture
def mock_staff_service():
    return MagicMock(spec=StaffService)


@pytest.fixture(autouse=True)
def override_deps(mock_admin_user, mock_staff_service):
    """Override auth and service dependencies."""
    from app.routers.staff import _clinician_dep, _get_service

    app.dependency_overrides[_clinician_dep] = lambda: mock_admin_user
    app.dependency_overrides[_get_service] = lambda: mock_staff_service
    yield
    app.dependency_overrides.clear()


class TestListStaff:
    @pytest.mark.asyncio
    async def test_success(self, client, mock_staff_service):
        mock_staff_service.list_staff.return_value = {
            "staff": [
                {
                    "id": str(uuid4()),
                    "email": "doc@test.com",
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "role": "provider",
                    "specialty": "Cardiology",
                    "created_at": "2025-01-01T00:00:00Z",
                }
            ],
            "clinic_name": "Heart Clinic",
        }

        response = client.get("/api/v1/staff/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["clinic_name"] == "Heart Clinic"
        assert len(data["staff"]) == 1
        assert data["staff"][0]["email"] == "doc@test.com"


class TestInviteMember:
    @pytest.mark.asyncio
    async def test_success(self, client, mock_staff_service):
        mock_staff_service.invite_member.return_value = {
            "status": "added",
            "email": "new@test.com",
            "role": "nurse",
        }

        response = client.post(
            "/api/v1/staff/invite",
            json={"email": "new@test.com", "role": "nurse"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["status"] == "added"

    @pytest.mark.asyncio
    async def test_invalid_role(self, client):
        response = client.post(
            "/api/v1/staff/invite",
            json={"email": "x@test.com", "role": "superadmin"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_invalid_email(self, client):
        response = client.post(
            "/api/v1/staff/invite",
            json={"email": "not-an-email", "role": "provider"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestUpdateRole:
    @pytest.mark.asyncio
    async def test_success(self, client, mock_staff_service):
        target_id = uuid4()
        mock_staff_service.update_role.return_value = {
            "id": str(target_id),
            "role": "admin",
        }

        response = client.put(
            f"/api/v1/staff/{target_id}/role",
            json={"role": "admin"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["role"] == "admin"


class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_success(self, client, mock_staff_service):
        target_id = uuid4()
        mock_staff_service.remove_member.return_value = {
            "status": "removed",
            "id": str(target_id),
        }

        response = client.delete(f"/api/v1/staff/{target_id}")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "removed"


class TestNoAuth:
    def test_unauthenticated(self, client):
        app.dependency_overrides.clear()
        response = client.get("/api/v1/staff/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
