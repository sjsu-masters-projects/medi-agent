"""Integration tests for Clinic API endpoints."""

from unittest.mock import MagicMock

import pytest
from fastapi import status

from app.main import app
from app.models.clinic import ClinicCodeResolveResponse, ClinicRead
from app.services.clinic_service import ClinicService


@pytest.fixture
def mock_clinic_service():
    return MagicMock(spec=ClinicService)


@pytest.fixture(autouse=True)
def override_service_dep(mock_clinic_service):
    from app.routers.clinics import _get_service

    app.dependency_overrides[_get_service] = lambda: mock_clinic_service
    yield
    app.dependency_overrides.clear()


class TestResolveClinicCode:
    def test_success(self, client, mock_clinic_service):
        mock_clinic_service.resolve_clinic_code.return_value = {
            "clinic_id": "8f8ffd0d-bd7f-4312-93f7-f9cb6f3f8a55",
            "clinic_code": "ABC123",
            "clinic_name": "City Health",
            "status": "active",
        }

        response = client.post(
            "/api/v1/clinics/resolve-code",
            json={"clinic_code": "ABC123"},
        )

        assert response.status_code == status.HTTP_200_OK
        payload = ClinicCodeResolveResponse(**response.json())
        assert str(payload.clinic_id) == "8f8ffd0d-bd7f-4312-93f7-f9cb6f3f8a55"
        assert payload.clinic_code == "ABC123"

    def test_rejects_empty_code(self, client):
        response = client.post(
            "/api/v1/clinics/resolve-code",
            json={"clinic_code": ""},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestProvisionClinic:
    @pytest.fixture(autouse=True)
    def override_internal_auth(self):
        from app.routers.clinics import _internal_admin_dep

        app.dependency_overrides[_internal_admin_dep] = lambda: None
        yield
        app.dependency_overrides.clear()

    def test_success(self, client, mock_clinic_service):
        mock_clinic_service.provision_clinic.return_value = {
            "id": "8f8ffd0d-bd7f-4312-93f7-f9cb6f3f8a55",
            "code": "ABC123",
            "display_name": "City Health",
            "canonical_name": "city health",
            "type2_npi": "1234567890",
            "status": "active",
            "created_at": "2026-01-01T00:00:00Z",
        }

        response = client.post(
            "/api/v1/clinics/internal/provision",
            json={
                "clinic_name": "City Health",
                "type2_npi": "1234567890",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        payload = ClinicRead(**response.json())
        assert str(payload.id) == "8f8ffd0d-bd7f-4312-93f7-f9cb6f3f8a55"
        assert payload.code == "ABC123"


class TestProvisionClinicAuth:
    def test_rejects_without_internal_token(self, client):
        response = client.post(
            "/api/v1/clinics/internal/provision",
            json={"clinic_name": "City Health", "type2_npi": "1234567890"},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
