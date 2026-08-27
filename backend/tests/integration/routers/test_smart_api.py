"""Route contracts for locally authorized SMART imports."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from urllib.parse import urlparse
from uuid import uuid4

import pytest

from app.main import app
from app.models.auth import CurrentUser
from app.routers.smart import _clinician_dep, _fhir_audit_export_service, _service


@pytest.fixture
def smart_service() -> MagicMock:
    service = MagicMock()
    app.dependency_overrides[_service] = lambda: service
    yield service
    app.dependency_overrides.clear()


@pytest.fixture
def clinician() -> CurrentUser:
    user = CurrentUser(id=uuid4(), email="clinician@example.test", role="clinician", aal="aal2")
    app.dependency_overrides[_clinician_dep] = lambda: user
    yield user
    app.dependency_overrides.clear()


@pytest.fixture
def fhir_audit_export_service() -> MagicMock:
    service = MagicMock()
    app.dependency_overrides[_fhir_audit_export_service] = lambda: service
    yield service
    app.dependency_overrides.clear()


def test_start_launch_requires_local_clinician_and_returns_redirect_url(
    client, smart_service, clinician
) -> None:
    patient_id = uuid4()
    smart_service.start_launch.return_value = {
        "authorization_url": "https://sandbox.example/authorize?state=opaque",
        "expires_at": datetime.now(UTC) + timedelta(minutes=10),
    }

    response = client.post(
        "/api/v1/smart/launch",
        json={"patient_id": str(patient_id), "issuer": "https://sandbox.example/fhir"},
    )

    assert response.status_code == 200
    authorization_url = urlparse(response.json()["authorization_url"])
    assert authorization_url.scheme == "https"
    assert authorization_url.netloc == "sandbox.example"
    assert authorization_url.path == "/authorize"
    smart_service.start_launch.assert_called_once_with(
        clinician_id=clinician.id,
        patient_id=patient_id,
        issuer="https://sandbox.example/fhir",
        launch_context=None,
    )


def test_start_launch_binds_ehr_launch_context_to_local_clinician_and_patient(
    client, smart_service, clinician
) -> None:
    patient_id = uuid4()
    smart_service.start_launch.return_value = {
        "authorization_url": "https://sandbox.example/authorize?state=opaque",
        "expires_at": datetime.now(UTC) + timedelta(minutes=10),
    }

    response = client.post(
        "/api/v1/smart/launch",
        json={
            "patient_id": str(patient_id),
            "issuer": "https://sandbox.example/fhir",
            "launch_context": "opaque-ehr-handle",
        },
    )

    assert response.status_code == 200
    smart_service.start_launch.assert_called_once_with(
        clinician_id=clinician.id,
        patient_id=patient_id,
        issuer="https://sandbox.example/fhir",
        launch_context="opaque-ehr-handle",
    )


def test_callback_redirects_with_one_time_handoff_only(client, smart_service) -> None:
    import_id = uuid4()
    smart_service.handle_callback.return_value = {"import_id": str(import_id), "ticket": "x" * 48}

    response = client.get(
        "/api/v1/smart/callback?state=" + "s" * 32 + "&code=authorization-code",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "ticket=" + "x" * 48 in response.headers["location"]
    assert "authorization-code" not in response.headers["location"]


def test_fact_fhir_audit_requires_assignment_and_returns_generated_resources(
    client, smart_service, fhir_audit_export_service, clinician
) -> None:
    patient_id = uuid4()
    fact_id = uuid4()
    fhir_audit_export_service.export_for_fact.return_value = {
        "provenance": {"resourceType": "Provenance"},
        "audit_events": [{"resourceType": "AuditEvent"}],
    }

    response = client.get(f"/api/v1/smart/patients/{patient_id}/facts/{fact_id}/fhir-audit")

    assert response.status_code == 200
    assert response.json()["provenance"]["resourceType"] == "Provenance"
    smart_service.ensure_assignment.assert_called_once_with(
        clinician_id=clinician.id, patient_id=patient_id
    )
    fhir_audit_export_service.export_for_fact.assert_called_once_with(
        fact_id=fact_id, patient_id=patient_id
    )
