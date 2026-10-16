"""Real HTTP boundaries with synthetic services; SQL ownership is tested separately."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser
from app.services.symptom_intake_service import SymptomIntakeService

ROOT = "/api/v1/patients/me/symptom-intakes"


@pytest.fixture
def patient_dependencies():
    user = CurrentUser(id=uuid4(), email="synthetic@invalid.test", role="patient")
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: MagicMock()
    try:
        yield user
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_owned_read_is_private_no_store(client, patient_dependencies, monkeypatch):
    active = AsyncMock(return_value=None)
    monkeypatch.setattr(SymptomIntakeService, "active", active)
    response = client.get(ROOT + "/active?session_id=default")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.json() is None
    active.assert_awaited_once_with("default")


@pytest.mark.parametrize("role", ["clinician", "admin"])
def test_private_intake_has_no_staff_route(client, patient_dependencies, monkeypatch, role):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=uuid4(), email="synthetic@invalid.test", role=role
    )
    active = AsyncMock()
    monkeypatch.setattr(SymptomIntakeService, "active", active)
    assert client.get(ROOT + "/active").status_code == 403
    active.assert_not_awaited()


@pytest.mark.parametrize(
    "extra", [{"patient_id": str(uuid4())}, {"timezone": "UTC"}, {"answers": {"severity": 9}}]
)
def test_start_rejects_browser_identity_and_answers(
    client, patient_dependencies, monkeypatch, extra
):
    start = AsyncMock()
    monkeypatch.setattr(SymptomIntakeService, "start", start)
    response = client.post(
        ROOT, json={"source_message_id": str(uuid4()), "session_id": "default", **extra}
    )
    assert response.status_code == 422
    start.assert_not_awaited()


@pytest.mark.parametrize("consent", [False, None, "yes", 1])
def test_confirmation_requires_explicit_true_consent(
    client, patient_dependencies, monkeypatch, consent
):
    confirm = AsyncMock()
    monkeypatch.setattr(SymptomIntakeService, "confirm", confirm)
    response = client.post(
        ROOT + f"/{uuid4()}/confirm",
        json={
            "expected_revision": 4,
            "confirmation_id": str(uuid4()),
            "preview_hash": "a" * 64,
            "consent": consent,
        },
    )
    assert response.status_code == 422
    confirm.assert_not_awaited()
