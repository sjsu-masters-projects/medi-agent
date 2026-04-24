"""Integration tests for clinic API endpoints."""

from unittest.mock import MagicMock

import pytest
from fastapi import status

from app.main import app
from app.models.clinic import ClinicCodeResolveResponse
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
