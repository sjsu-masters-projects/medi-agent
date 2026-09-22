"""Retrying a patient explanation is care-team gated and clinically inert."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.core.exceptions import AuthorizationError
from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser
from app.routers.documents import _clinician_dep, _get_service


@pytest.fixture
def clinician_id():
    return uuid4()


@pytest.fixture
def patient_id():
    return uuid4()


@pytest.fixture
def document_id():
    return uuid4()


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_service(document_id, patient_id):
    service = MagicMock()
    service.get_document = AsyncMock(
        return_value={
            "id": str(document_id),
            "patient_id": str(patient_id),
            "uploaded_by": str(patient_id),
            "uploaded_by_role": "patient",
            "file_name": "lab-results.pdf",
            "file_url": "https://storage.example.com/signed-url",
            "file_size_bytes": 2048,
            "mime_type": "application/pdf",
            "document_type": "lab_report",
            "parsed": True,
            "parse_status": "completed",
            "summary_status": "pending",
            "summary_failure_code": None,
            "summary_attempts": 0,
            "visibility": "all_providers",
            "created_at": "2026-09-20T00:00:00Z",
        }
    )
    return service


@pytest.fixture
def client(clinician_id, mock_db, mock_service):
    def _user():
        return CurrentUser(id=clinician_id, email="clinician@test.com", role="clinician")

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[_clinician_dep] = _user
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[_get_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def _url(patient_id, document_id) -> str:
    return f"/api/v1/documents/patients/{patient_id}/{document_id}/summary/retry"


def test_assigned_clinician_requeues_only_the_explanation(
    client, mock_db, clinician_id, patient_id, document_id
):
    with patch("app.routers.documents.SmartLaunchService") as smart:
        response = client.post(_url(patient_id, document_id))

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.json()["summary_status"] == "pending"
    smart.return_value.ensure_assignment.assert_called_once_with(
        clinician_id=clinician_id, patient_id=patient_id
    )
    mock_db.rpc.assert_called_once_with(
        "enqueue_document_summary_retry",
        {
            "p_document_id": str(document_id),
            "p_patient_id": str(patient_id),
            "p_actor_id": str(clinician_id),
        },
    )
    # The clinical lifecycle is untouched: no ingestion re-claim, no candidate write.
    assert mock_db.table.call_count == 0


def test_unassigned_clinician_cannot_requeue_an_explanation(
    client, mock_db, patient_id, document_id
):
    with patch("app.routers.documents.SmartLaunchService") as smart:
        smart.return_value.ensure_assignment.side_effect = AuthorizationError("not assigned")
        response = client.post(_url(patient_id, document_id))

    assert response.status_code == status.HTTP_403_FORBIDDEN
    mock_db.rpc.assert_not_called()
