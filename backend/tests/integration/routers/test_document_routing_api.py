"""Route contracts for choosing, claiming and reading care-team-owned documents. Synthetic data."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser
from app.routers import documents, smart
from tests.unit.services.care_team_fake_db import (
    CLINICIAN,
    OTHER_TEAM,
    PATIENT,
    TEAM,
    THIRD,
    FakeDB,
)

DOC_THEIRS = "dddddddd-dddd-4ddd-8ddd-ddddddddddd2"
DOC_OPEN = "dddddddd-dddd-4ddd-8ddd-ddddddddddd3"
FACT_THEIRS = "ffffffff-ffff-4fff-8fff-fffffffffff2"
FACT_MINE = "ffffffff-ffff-4fff-8fff-fffffffffff1"

UPLOAD = {
    "file_name": "labs.pdf",
    "file_path": f"{PATIENT}/labs.pdf",
    "file_size_bytes": 100,
    "mime_type": "application/pdf",
    "document_type": "lab_report",
}


def _row(doc_id: str, team: str | None, state: str = "routed") -> dict:
    return {
        "id": doc_id,
        "patient_id": PATIENT,
        "file_name": "x.pdf",
        "display_title": {},
        "document_type": "lab_report",
        "created_at": "2026-10-01T10:00:00Z",
        "review_status": "pending",
        "uploaded_by_role": "patient",
        "parse_status": "completed",
        "routing_state": state,
        "care_team_id": team,
    }


@pytest.fixture
def db() -> FakeDB:
    database = FakeDB(
        {
            "documents": [_row(DOC_THEIRS, OTHER_TEAM), _row(DOC_OPEN, None, "unrouted")],
            "clinical_facts": [
                {
                    "id": FACT_MINE,
                    "patient_id": PATIENT,
                    "fact_type": "medication",
                    "review_state": "pending_review",
                    "value": {},
                },
                {
                    "id": FACT_THEIRS,
                    "patient_id": PATIENT,
                    "fact_type": "medication",
                    "review_state": "pending_review",
                    "value": {},
                },
            ],
            "source_provenances": [
                {"id": "p1", "document_id": None, "care_team_id": TEAM},
                {"id": "p2", "document_id": DOC_THEIRS, "care_team_id": None},
            ],
            "evidence_citations": [
                {"id": "c1", "fact_id": FACT_MINE, "provenance_id": "p1"},
                {"id": "c2", "fact_id": FACT_THEIRS, "provenance_id": "p2"},
            ],
        }
    )
    app.dependency_overrides[get_db] = lambda: database
    yield database
    app.dependency_overrides.clear()


def _as(user_id: str, role: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=UUID(user_id), email="synthetic@example.test", role=role, aal="aal2"
    )


@pytest.fixture
def document_service() -> MagicMock:
    service = MagicMock()
    service.create_document = AsyncMock(
        side_effect=lambda **kwargs: {
            **_row(str(uuid4()), kwargs["care_team_id"], kwargs["routing_state"]),
            "uploaded_by": kwargs["uploaded_by"],
            "uploaded_by_role": kwargs["uploaded_by_role"],
            "file_url": "",
            "file_size_bytes": 100,
            "mime_type": "application/pdf",
        }
    )
    app.dependency_overrides[documents._get_service] = lambda: service
    return service


def test_patient_with_two_teams_must_choose_before_upload(db, document_service) -> None:
    _as(PATIENT, "patient")
    client = TestClient(app)
    refused = client.post("/api/v1/documents/", json=UPLOAD)
    assert refused.status_code in (400, 422)
    assert refused.json()["error"]["code"] == "CARE_TEAM_REQUIRED"
    document_service.create_document.assert_not_called()

    chosen = client.post("/api/v1/documents/", json={**UPLOAD, "care_team_id": OTHER_TEAM})
    assert chosen.status_code == 201
    assert (
        chosen.json()["care_team_id"] == OTHER_TEAM and chosen.json()["routing_state"] == "routed"
    )

    unsure = client.post("/api/v1/documents/", json={**UPLOAD, "not_sure": True})
    assert unsure.status_code == 201
    assert unsure.json()["care_team_id"] is None and unsure.json()["routing_state"] == "unrouted"


def test_care_team_options_are_for_the_patient_only(db) -> None:
    _as(PATIENT, "patient")
    options = TestClient(app).get("/api/v1/documents/care-team-options")
    assert options.status_code == 200
    assert {item["care_team_id"] for item in options.json()} == {TEAM, OTHER_TEAM}
    _as(CLINICIAN, "clinician")
    assert TestClient(app).get("/api/v1/documents/care-team-options").status_code == 403


def test_clinician_upload_needs_a_link_and_lands_on_their_team(db, document_service) -> None:
    client = TestClient(app)
    _as(THIRD, "clinician")
    assert client.post(f"/api/v1/documents/patients/{PATIENT}", json=UPLOAD).status_code == 403
    document_service.create_document.assert_not_called()
    _as(CLINICIAN, "clinician")
    created = client.post(f"/api/v1/documents/patients/{PATIENT}", json=UPLOAD)
    assert created.status_code == 201 and created.json()["care_team_id"] == TEAM
    not_sure = client.post(
        f"/api/v1/documents/patients/{PATIENT}", json={**UPLOAD, "not_sure": True}
    )
    assert not_sure.status_code in (400, 422)


def test_claim_route_is_for_clinicians_with_the_exact_link(db) -> None:
    db.rpc_handlers["claim_document"] = lambda p: {
        "document_id": p["p_document_id"],
        "care_team_id": p["p_care_team_id"],
        "status": "claimed",
        "replayed": False,
    }
    client = TestClient(app)
    _as(PATIENT, "patient")
    assert (
        client.post(f"/api/v1/documents/{DOC_OPEN}/claim", json={"care_team_id": TEAM}).status_code
        == 403
    )
    _as(CLINICIAN, "clinician")
    refused = client.post(f"/api/v1/documents/{DOC_OPEN}/claim", json={"care_team_id": OTHER_TEAM})
    assert refused.status_code == 404 and db.rpc_calls == []
    claimed = client.post(f"/api/v1/documents/{DOC_OPEN}/claim", json={"care_team_id": TEAM})
    assert claimed.status_code == 200 and claimed.json()["care_team_id"] == TEAM


def test_claimable_queue_never_lists_another_teams_document(db) -> None:
    _as(CLINICIAN, "clinician")
    listed = TestClient(app).get("/api/v1/documents/claimable")
    assert listed.status_code == 200
    assert {row["id"] for row in listed.json()} == {DOC_OPEN}


def test_clinician_source_preview_and_retries_refuse_another_teams_document(db) -> None:
    _as(CLINICIAN, "clinician")
    client = TestClient(app)
    base = f"/api/v1/documents/patients/{PATIENT}/{DOC_THEIRS}"
    assert client.get(f"{base}/source").status_code == 404
    assert client.post(f"{base}/summary/retry").status_code == 404
    assert client.post(f"{base}/ingestion/retry").status_code == 404
    assert db.rpc_calls == []


def test_fact_routes_refuse_another_teams_fact(db) -> None:
    app.dependency_overrides[smart._service] = lambda: MagicMock()
    _as(CLINICIAN, "clinician")
    client = TestClient(app)
    base = f"/api/v1/smart/patients/{PATIENT}/facts"
    assert client.get(f"{base}/{FACT_MINE}/lineage").status_code == 200
    for method, path, body in (
        ("get", f"{base}/{FACT_THEIRS}/lineage", None),
        ("get", f"{base}/{FACT_THEIRS}/source", None),
        ("get", f"{base}/{FACT_THEIRS}/fhir-audit", None),
        ("get", f"{base}/{FACT_THEIRS}/reconciliation-preview", None),
        ("get", f"{base}/{FACT_THEIRS}/medication-reference", None),
        ("post", f"{base}/{FACT_THEIRS}/approve", {"note": "ok"}),
        ("post", f"{base}/{FACT_THEIRS}/reject", {"note": "no"}),
        ("post", f"{base}/{FACT_THEIRS}/correct", {"value": {"name": "x"}, "note": "n"}),
        (
            "post",
            f"{base}/{FACT_THEIRS}/reconcile",
            {"decision": "keep_existing", "idempotency_key": str(uuid4())},
        ),
    ):
        response = getattr(client, method)(path, **({"json": body} if body else {}))
        assert response.status_code == 404, (path, response.status_code)
    assert db.rpc_calls == []
    assert {row["id"]: row["review_state"] for row in db.tables["clinical_facts"]}[
        FACT_THEIRS
    ] == "pending_review"
