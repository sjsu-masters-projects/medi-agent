"""HTTP boundaries for the confirmed-symptom history; the services are synthetic."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationError, NotFoundError
from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser
from app.routers.clinicians import _clinician_dep
from app.services.clinician_service import ClinicianService
from app.services.symptom_report_history_service import SymptomReportHistoryService

PATIENT_ROOT = "/api/v1/patients/me/symptom-history"


@pytest.fixture
def as_role():
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = lambda: MagicMock()

    def use(role):
        user = CurrentUser(id=uuid4(), email="synthetic@invalid.test", role=role)
        app.dependency_overrides[get_current_user] = lambda: user
        if role == "clinician":
            app.dependency_overrides[_clinician_dep] = lambda: user
        return user

    try:
        yield use
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_patient_history_is_private_and_scoped_to_caller(client, as_role, monkeypatch):
    user = as_role("patient")
    listed = AsyncMock(return_value={"items": [], "has_more": False, "timezone": "UTC"})
    monkeypatch.setattr(SymptomReportHistoryService, "list_for_patient", listed)
    response = client.get(PATIENT_ROOT)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    listed.assert_awaited_once_with(user.id, 50)


@pytest.mark.parametrize("role", ["clinician", "admin"])
def test_staff_cannot_use_the_patient_history_routes(client, as_role, monkeypatch, role):
    as_role(role)
    called = AsyncMock()
    monkeypatch.setattr(SymptomReportHistoryService, "list_for_patient", called)
    monkeypatch.setattr(SymptomReportHistoryService, "detail_for_patient", called)
    assert client.get(PATIENT_ROOT).status_code == 403
    assert client.get(f"{PATIENT_ROOT}/{uuid4()}").status_code == 403
    called.assert_not_awaited()


def test_someone_elses_report_is_not_found(client, as_role, monkeypatch):
    as_role("patient")
    monkeypatch.setattr(
        SymptomReportHistoryService,
        "detail_for_patient",
        AsyncMock(side_effect=NotFoundError("Symptom report", "x")),
    )
    assert client.get(f"{PATIENT_ROOT}/{uuid4()}").status_code == 404


def test_limit_is_bounded(client, as_role):
    as_role("patient")
    assert client.get(PATIENT_ROOT + "?limit=101").status_code == 422


@pytest.mark.parametrize("path", ["", "/review"])
def test_patient_cannot_reach_clinician_report_routes(client, as_role, path):
    as_role("patient")
    url = f"/api/v1/clinicians/me/patients/{uuid4()}/symptom-reports/{uuid4()}{path}"
    assert (client.get(url) if not path else client.post(url)).status_code == 403


def test_unassigned_clinician_is_denied_review(client, as_role, monkeypatch):
    as_role("clinician")
    denied = AsyncMock(side_effect=AuthorizationError("no"))
    monkeypatch.setattr(ClinicianService, "review_symptom_report", denied)
    url = f"/api/v1/clinicians/me/patients/{uuid4()}/symptom-reports/{uuid4()}/review"
    assert client.post(url).status_code == 403
    denied.assert_awaited_once()


def test_review_forwards_the_chosen_care_team_and_rejects_extra_fields(
    client, as_role, monkeypatch
):
    user = as_role("clinician")
    from app.services.symptom_report_presenter import present_clinician

    card = {
        "id": str(uuid4()),
        "patient_id": str(uuid4()),
        "symptom": "Dizziness",
        "confirmed_at": "2026-10-20T17:00:00+00:00",
        "locale": "en-US",
        "handoff_state": "sent",
        "handed_off_at": "2026-10-20T17:00:01+00:00",
        "reviews": [],
        "provenance": {"report_id": str(uuid4()), "consent_recorded": True},
    }
    reviewed = AsyncMock(return_value=present_clinician(card))
    monkeypatch.setattr(ClinicianService, "review_symptom_report", reviewed)
    patient, report, team = uuid4(), uuid4(), uuid4()
    url = f"/api/v1/clinicians/me/patients/{patient}/symptom-reports/{report}/review"
    assert client.post(url, json={"care_team_id": str(team)}).status_code == 200
    reviewed.assert_awaited_once_with(user.id, patient, report, team)
    assert client.post(url, json={"reviewed_by": str(uuid4())}).status_code == 422
