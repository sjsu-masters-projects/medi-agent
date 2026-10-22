"""Handoff share routes: roles, errors, caching, and what a recipient is shown (CON-001)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.security import get_current_user
from app.main import app
from app.models.auth import CurrentUser
from app.routers.handoff_shares import _service
from app.services.handoff_share_service import HandoffShareService
from tests.unit.services.care_team_fake_db import CLINICIAN, OTHER, PATIENT, FakeDB
from tests.unit.services.test_handoff_summary import api_error

NOW = datetime.now(UTC).isoformat()
SUMMARY = str(uuid4())
SHARE = str(uuid4())
AUTHOR = f"/api/v1/care-team/clinician/handoff-summaries/{SUMMARY}"
SHARED = "/api/v1/care-team/clinician/shared-handoffs"


def as_user(user_id: str, role: str = "clinician") -> None:
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=UUID(user_id), email="c@example.test", role=role, aal="aal2"
    )


def share_row(**over: Any) -> dict[str, Any]:
    return {
        "id": SHARE,
        "summary_id": SUMMARY,
        "version": 1,
        "recipient_id": OTHER,
        "recipient_name": "Omar Reyes",
        "recipient_specialty": "Orthopaedics",
        "shared_at": NOW,
        "revoked_at": None,
        "replayed": False,
        **over,
    }


def shared_detail(**over: Any) -> dict[str, Any]:
    return {
        "share_id": SHARE,
        "summary_id": SUMMARY,
        "version": 1,
        "title": "Handoff",
        "purpose": "colleague",
        "patient_id": PATIENT,
        "patient_name": "Lucia Synthetic",
        "author_id": CLINICIAN,
        "author_name": "Elena Park",
        "author_specialty": "Cardiology",
        "author_clinic": "Cedar Grove",
        "shared_at": NOW,
        "approved_by": CLINICIAN,
        "approved_by_name": "Elena Park",
        "approved_at": NOW,
        "built_at": NOW,
        "sections": [
            {
                "key": "shared_core",
                "title": "Shared record",
                "status": "available",
                "items": [
                    {
                        "id": "m1",
                        "text": "Medication: Lisinopril",
                        "source": {
                            "kind": "record",
                            "table": "medications",
                            "id": "abc",
                            "label": "Recorded by Elena Park",
                            "href": f"/patients/{PATIENT}?tab=profile",
                        },
                    }
                ],
            }
        ],
        "narrative": "Stable.",
        "notes": None,
        "newer": None,
        **over,
    }


@pytest.fixture
def db() -> Iterator[FakeDB]:
    fake = FakeDB()
    app.dependency_overrides[_service] = lambda: HandoffShareService(fake)  # type: ignore[arg-type]
    yield fake
    app.dependency_overrides.clear()


ROUTES = [
    ("GET", AUTHOR + "/share-candidates", None),
    ("GET", AUTHOR + "/shares", None),
    ("POST", AUTHOR + "/shares", {"version": 1, "recipient_id": OTHER}),
    ("DELETE", f"/api/v1/care-team/clinician/handoff-shares/{SHARE}", None),
    ("GET", SHARED, None),
    ("GET", f"{SHARED}/{SHARE}", None),
    ("POST", f"{SHARED}/{SHARE}/export", {"format": "print"}),
]


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
def test_a_patient_session_is_refused_everywhere(client, db, method, path, body) -> None:
    as_user(PATIENT, "patient")
    assert client.request(method, path, json=body).status_code == 403
    assert not db.rpc_calls


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
def test_every_refusal_by_the_database_is_the_same_empty_not_found(
    client, db, method, path, body
) -> None:
    def refuse(_p: dict[str, Any]) -> Any:
        raise api_error("42501")

    for name in (
        "list_care_handoff_share_candidates",
        "list_care_handoff_shares",
        "share_care_handoff_summary",
        "revoke_care_handoff_share",
        "list_care_handoff_shared_with_me",
        "read_shared_care_handoff",
        "record_shared_care_handoff_export",
    ):
        db.rpc_handlers[name] = refuse
    as_user(OTHER)
    response = client.request(method, path, json=body)
    assert response.status_code == 404
    assert "Lisinopril" not in response.text and "Omar" not in response.text


def test_sharing_returns_201_then_200_on_a_replay_and_maps_database_rules(client, db) -> None:
    as_user(CLINICIAN)
    db.rpc_handlers["share_care_handoff_summary"] = lambda _p: share_row()
    created = client.post(AUTHOR + "/shares", json={"version": 1, "recipient_id": OTHER})
    assert created.status_code == 201 and created.headers["cache-control"] == "no-store"
    assert db.rpc_calls[-1][1]["p_actor_id"] == CLINICIAN  # the actor is the session, not input
    db.rpc_handlers["share_care_handoff_summary"] = lambda _p: share_row(replayed=True)
    assert (
        client.post(AUTHOR + "/shares", json={"version": 1, "recipient_id": OTHER}).status_code
        == 200
    )

    def not_approved(_p: dict[str, Any]) -> Any:
        raise api_error("22023", "HANDOFF_NOT_APPROVED: no", "HANDOFF_NOT_APPROVED")

    db.rpc_handlers["share_care_handoff_summary"] = not_approved
    body = client.post(AUTHOR + "/shares", json={"version": 1, "recipient_id": OTHER})
    assert body.status_code == 422 and "HANDOFF_NOT_APPROVED" in body.text

    def not_allowed(_p: dict[str, Any]) -> Any:
        raise api_error(
            "22023", "HANDOFF_RECIPIENT_NOT_ALLOWED: x", "HANDOFF_RECIPIENT_NOT_ALLOWED"
        )

    db.rpc_handlers["share_care_handoff_summary"] = not_allowed
    body = client.post(AUTHOR + "/shares", json={"version": 1, "recipient_id": OTHER})
    assert body.status_code == 422 and "HANDOFF_RECIPIENT_NOT_ALLOWED" in body.text


def test_unknown_fields_and_bad_input_are_rejected_before_any_work(client, db) -> None:
    as_user(CLINICIAN)
    assert (
        client.post(
            AUTHOR + "/shares", json={"version": 1, "recipient_id": OTHER, "actor_id": OTHER}
        ).status_code
        == 422
    )
    assert (
        client.post(AUTHOR + "/shares", json={"version": 0, "recipient_id": OTHER}).status_code
        == 422
    )
    assert (
        client.post(AUTHOR + "/shares", json={"version": 1, "recipient_id": "x"}).status_code == 422
    )
    assert client.post(f"{SHARED}/{SHARE}/export", json={"format": "pdf"}).status_code == 422
    assert not db.rpc_calls


def test_candidates_and_shares_are_listed_uncached(client, db) -> None:
    as_user(CLINICIAN)
    db.rpc_handlers["list_care_handoff_share_candidates"] = lambda _p: [
        {
            "clinician_id": OTHER,
            "first_name": "Omar",
            "last_name": "Reyes",
            "specialty": "Orthopaedics",
            "clinics": [{"id": str(uuid4()), "name": "Birch Clinic"}],
            "bases": ["care_team"],
        }
    ]
    db.rpc_handlers["list_care_handoff_shares"] = lambda _p: [share_row()]
    found = client.get(AUTHOR + "/share-candidates?q=omar")
    assert found.status_code == 200 and found.json()[0]["clinics"][0]["name"] == "Birch Clinic"
    assert db.rpc_calls[-1][1]["p_query"] == "omar"
    listed = client.get(AUTHOR + "/shares")
    assert listed.status_code == 200 and listed.headers["cache-control"] == "no-store"
    assert client.get(AUTHOR + "/share-candidates?q=" + "a" * 101).status_code == 422


def test_a_recipient_is_shown_the_content_without_record_links_or_team(client, db) -> None:
    as_user(OTHER)
    db.rpc_handlers["read_shared_care_handoff"] = lambda _p: shared_detail()
    response = client.get(f"{SHARED}/{SHARE}")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    text = response.text
    assert "Lisinopril" in text and "Stable." in text
    source = response.json()["sections"][0]["items"][0]["source"]
    assert source == {
        "kind": "record",
        "table": None,
        "id": None,
        "label": "Recorded by Elena Park",
        "href": None,
    }
    assert "care_team" not in text and f"/patients/{PATIENT}" not in text


def test_a_recipient_export_is_audited_and_fhir_is_a_valid_bundle(client, db) -> None:
    as_user(OTHER)
    db.tables["patients"] = [
        {
            "id": PATIENT,
            "first_name": "Lucia",
            "last_name": "Synthetic",
            "date_of_birth": "1961-07-14",
        }
    ]
    db.rpc_handlers["record_shared_care_handoff_export"] = lambda _p: shared_detail()
    printed = client.post(f"{SHARED}/{SHARE}/export", json={"format": "print"})
    assert printed.status_code == 200 and printed.json()["bundle"] is None
    fhir = client.post(f"{SHARED}/{SHARE}/export", json={"format": "fhir"})
    assert fhir.status_code == 200 and fhir.json()["bundle"]["resourceType"] == "Bundle"
    assert "abc" not in fhir.text  # no source record ids reach an unlinked recipient
    assert [c[1]["p_format"] for c in db.rpc_calls] == ["print", "fhir"]
    assert db.rpc_calls[0][1]["p_actor_id"] == OTHER
