"""Handoff summary routes: roles, denial audit, error mapping and caching (CON-001)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.security import get_current_user
from app.main import app
from app.models.auth import CurrentUser
from app.routers.handoff_summaries import _service
from app.services.handoff_summary_service import HandoffSummaryService
from tests.unit.services.care_team_fake_db import CLINICIAN, PATIENT, THIRD, FakeDB
from tests.unit.services.test_handoff_summary import (
    SUMMARY,
    allow,
    api_error,
    approved_payload,
    detail_payload,
    make_db,
)

BASE = f"/api/v1/care-team/clinician/patients/{PATIENT}/handoff-summaries"


def as_user(user_id: str, role: str = "clinician") -> None:
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=UUID(user_id), email="c@example.test", role=role, aal="aal2"
    )


@pytest.fixture
def db() -> Iterator[FakeDB]:
    fake = make_db()
    fake.rpc_handlers["read_care_handoff_summary"] = lambda _p: detail_payload()
    app.dependency_overrides[_service] = lambda: HandoffSummaryService(fake, allow)  # type: ignore[arg-type]
    yield fake
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("GET", "", None),
        ("POST", "", {"purpose": "colleague"}),
        ("GET", f"/{SUMMARY}", None),
        ("PUT", f"/{SUMMARY}", {"expected_version": 1}),
        ("POST", f"/{SUMMARY}/approve", {"version": 1}),
        ("POST", f"/{SUMMARY}/export", {"version": 1, "format": "print"}),
    ],
)
def test_a_patient_session_is_refused_everywhere(client, db, method, suffix, body) -> None:
    as_user(PATIENT, "patient")
    response = client.request(method, BASE + suffix, json=body)
    assert response.status_code == 403
    assert not db.rpc_calls


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("GET", "", None),
        ("POST", "", {"purpose": "colleague"}),
        ("GET", f"/{SUMMARY}", None),
        ("PUT", f"/{SUMMARY}", {"expected_version": 1}),
        ("POST", f"/{SUMMARY}/approve", {"version": 1}),
        ("POST", f"/{SUMMARY}/export", {"version": 1, "format": "fhir"}),
    ],
)
def test_an_unassigned_clinician_is_refused_and_the_denial_audited(
    client, db, denial_audit, method, suffix, body
) -> None:
    as_user(THIRD)
    response = client.request(method, BASE + suffix, json=body)
    assert response.status_code == 403
    assert not db.rpc_calls
    assert denial_audit[0]["reason_code"] == "NO_CARE_TEAM_ASSIGNMENT"


def test_another_teams_summary_is_not_found_with_no_content(client, db) -> None:
    def unavailable(_p: dict[str, Any]) -> Any:
        raise api_error("42501")

    db.rpc_handlers["read_care_handoff_summary"] = unavailable
    as_user(CLINICIAN)
    response = client.get(f"{BASE}/{uuid4()}")
    assert response.status_code == 404
    assert "Lisinopril" not in response.text


def test_export_of_an_unapproved_summary_is_refused_with_a_stable_code(client, db) -> None:
    def refuse(_p: dict[str, Any]) -> Any:
        raise api_error("22023", "HANDOFF_NOT_APPROVED: no", "HANDOFF_NOT_APPROVED")

    db.rpc_handlers["record_care_handoff_export"] = refuse
    as_user(CLINICIAN)
    response = client.post(f"{BASE}/{SUMMARY}/export", json={"version": 2, "format": "fhir"})
    assert response.status_code in {400, 422}
    assert "HANDOFF_NOT_APPROVED" in response.text


def test_a_stale_save_is_a_conflict(client, db) -> None:
    def stale(_p: dict[str, Any]) -> Any:
        raise api_error("40001", "HANDOFF_VERSION_CONFLICT: changed")

    db.rpc_handlers["save_care_handoff_version"] = stale
    as_user(CLINICIAN)
    response = client.put(f"{BASE}/{SUMMARY}", json={"expected_version": 1, "narrative": "x"})
    assert response.status_code == 409


def test_unknown_fields_and_bad_formats_are_rejected_before_any_work(client, db) -> None:
    as_user(CLINICIAN)
    assert client.post(BASE, json={"purpose": "colleague", "sections": []}).status_code == 422
    assert (
        client.post(f"{BASE}/{SUMMARY}/export", json={"version": 1, "format": "pdf"}).status_code
        == 422
    )
    assert not db.rpc_calls


def test_an_approved_export_is_returned_uncached(client, db) -> None:
    db.rpc_handlers["read_care_handoff_summary"] = lambda _p: approved_payload()
    db.rpc_handlers["record_care_handoff_export"] = lambda _p: approved_payload()
    as_user(CLINICIAN)
    response = client.post(f"{BASE}/{SUMMARY}/export", json={"version": 2, "format": "fhir"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["bundle"]["resourceType"] == "Bundle"
