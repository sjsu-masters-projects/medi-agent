"""Medication confirmation routes and service rules (MED-002). Synthetic data only."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from postgrest.exceptions import APIError

from app.core.security import get_current_user
from app.main import app
from app.models.auth import CurrentUser
from app.routers.medication_confirmations import _service
from app.services.medication_confirmation_service import MedicationConfirmationService
from tests.unit.services.care_team_fake_db import CLINICIAN, PATIENT, TEAM, THIRD, FakeDB

FACT = "99999999-0000-4000-8000-000000000001"
MED = "99999999-0000-4000-8000-000000000002"
REQUEST = "99999999-0000-4000-8000-000000000003"
BASE = f"/api/v1/smart/patients/{PATIENT}/facts/{FACT}/confirmations"
MINE = "/api/v1/patients/me/medication-confirmations"


def as_user(user_id: str, role: str = "clinician") -> None:
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=UUID(user_id), email="u@example.test", role=role, aal="aal2"
    )


def stored(**over: Any) -> dict[str, Any]:
    row = {
        "id": REQUEST,
        "fact_id": FACT,
        "care_team_id": TEAM,
        "patient_id": PATIENT,
        "requested_by": CLINICIAN,
        "subject_kind": "imported",
        "medication_name": "Metformin",
        "dosage": "500 mg",
        "frequency": "twice daily",
        "status": "open",
        "answer": None,
        "answer_note": None,
        "created_at": "2026-10-22T10:00:00+00:00",
        "expires_at": "2026-11-05T10:00:00+00:00",
        "answered_at": None,
        "clinician_name": "Elena Park",
        "specialty": "Cardiology",
        "clinic_name": "Cedar Grove",
        "replayed": False,
    }
    row.update(over)
    return row


def api_error(code: str, message: str = "x", hint: str = "") -> APIError:
    return APIError({"code": code, "message": message, "hint": hint, "details": ""})


@pytest.fixture
def db() -> Iterator[FakeDB]:
    fake = FakeDB(
        {
            "clinical_facts": [
                {
                    "id": FACT,
                    "patient_id": PATIENT,
                    "fact_type": "medication",
                    "review_state": "pending_review",
                    "reconciliation_state": "not_started",
                    "value": {"name": "Metformin", "dosage": "500 mg", "frequency": "twice daily"},
                }
            ],
            "medications": [
                {
                    "id": MED,
                    "patient_id": PATIENT,
                    "name": "Metformin ER",
                    "dosage": "1000 mg",
                    "frequency": "once daily",
                }
            ],
        }
    )
    fake.rpc_handlers["create_medication_confirmation"] = lambda p: stored(
        id=p["p_request_id"],
        subject_kind=p["p_subject_kind"],
        medication_name=p["p_medication_name"],
        dosage=p["p_dosage"],
        frequency=p["p_frequency"],
    )
    fake.rpc_handlers["list_fact_medication_confirmations"] = lambda _p: [stored()]
    fake.rpc_handlers["list_patient_medication_confirmations"] = lambda _p: [
        {k: v for k, v in stored().items() if k not in {"patient_id", "requested_by"}}
    ]
    fake.rpc_handlers["answer_medication_confirmation"] = lambda p: {
        k: v
        for k, v in stored(status="answered", answer=p["p_answer"], answer_note=p["p_note"]).items()
        if k not in {"patient_id", "requested_by"}
    }
    app.dependency_overrides[_service] = lambda: MedicationConfirmationService(fake)  # type: ignore[arg-type]
    yield fake
    app.dependency_overrides.clear()


def test_a_clinician_asks_about_the_imported_version_for_their_own_team(client, db) -> None:
    as_user(CLINICIAN)
    key = str(uuid4())
    response = client.post(BASE, json={"client_request_id": key})
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["medication_name"], body["dosage"], body["frequency"]) == (
        "Metformin",
        "500 mg",
        "twice daily",
    )
    (name, params), *_ = db.rpc_calls
    assert name == "create_medication_confirmation"
    assert params["p_actor_id"] == CLINICIAN and params["p_care_team_id"] == TEAM
    assert params["p_request_id"] == key and params["p_ttl_days"] == 14


def test_a_replayed_ask_is_not_a_new_request(client, db) -> None:
    db.rpc_handlers["create_medication_confirmation"] = lambda _p: stored(replayed=True)
    as_user(CLINICIAN)
    assert client.post(BASE, json={}).status_code == 200


def test_the_question_can_be_about_a_matched_approved_medication(client, db) -> None:
    as_user(CLINICIAN)
    response = client.post(BASE, json={"subject": "approved", "medication_id": MED})
    assert response.status_code == 201
    params = db.rpc_calls[0][1]
    assert params["p_medication_name"] == "Metformin ER" and params["p_dosage"] == "1000 mg"
    assert params["p_medication_id"] == MED


def test_an_approved_question_must_name_a_medication_of_this_patient(client, db) -> None:
    as_user(CLINICIAN)
    assert client.post(BASE, json={"subject": "approved"}).status_code == 422
    other = str(uuid4())
    assert (
        client.post(BASE, json={"subject": "approved", "medication_id": other}).status_code == 404
    )
    assert not db.rpc_calls


def test_only_a_pending_medication_can_be_asked_about(client, db) -> None:
    as_user(CLINICIAN)
    db.tables["clinical_facts"][0]["reconciliation_state"] = "applied"
    assert client.post(BASE, json={}).status_code == 422
    db.tables["clinical_facts"][0].update(reconciliation_state="not_started", fact_type="allergy")
    assert client.post(BASE, json={}).status_code == 422
    assert not db.rpc_calls


def test_an_unassigned_clinician_is_refused_and_audited(client, db, denial_audit) -> None:
    as_user(THIRD)
    assert client.post(BASE, json={}).status_code == 403
    assert client.get(BASE).status_code == 403
    assert not db.rpc_calls
    assert denial_audit[0]["reason_code"] == "NO_CARE_TEAM_ASSIGNMENT"


def test_a_patient_cannot_use_the_clinician_routes(client, db) -> None:
    as_user(PATIENT, "patient")
    assert client.post(BASE, json={}).status_code == 403
    assert client.get(BASE).status_code == 403
    assert not db.rpc_calls


def test_a_clinician_cannot_use_the_patient_routes(client, db) -> None:
    as_user(CLINICIAN)
    assert client.get(MINE).status_code == 403
    assert client.post(f"{MINE}/{REQUEST}/answer", json={"answer": "yes"}).status_code == 403
    assert not db.rpc_calls


def test_the_database_denial_reads_as_not_found(client, db) -> None:
    def deny(_p: dict[str, Any]) -> Any:
        raise api_error("42501")

    db.rpc_handlers["create_medication_confirmation"] = deny
    db.rpc_handlers["list_fact_medication_confirmations"] = deny
    as_user(CLINICIAN)
    assert client.post(BASE, json={}).status_code == 404
    assert client.get(BASE).status_code == 404


def test_the_clinician_reads_the_answer_as_evidence_and_nothing_is_applied(client, db) -> None:
    db.rpc_handlers["list_fact_medication_confirmations"] = lambda _p: [
        stored(status="answered", answer="changed", answer_note="Now 250 mg", answered_at="x")
        | {"answered_at": "2026-10-23T10:00:00+00:00"}
    ]
    as_user(CLINICIAN)
    response = client.get(BASE)
    assert response.status_code == 200
    assert response.json()[0]["answer"] == "changed"
    assert response.json()[0]["answer_note"] == "Now 250 mg"
    # Reading testimony never touches the chart.
    assert not [q for q in db.queries if q[1] in {"insert", "update", "delete"}]
    assert [name for name, _ in db.rpc_calls] == ["list_fact_medication_confirmations"]


def test_the_patient_lists_their_questions_with_both_language_cadence_labels(client, db) -> None:
    as_user(PATIENT, "patient")
    response = client.get(MINE)
    assert response.status_code == 200
    row = response.json()[0]
    assert row["frequency_label_en"] == "Twice daily"
    assert row["frequency_label_es"] == "Dos veces al día"
    assert "requested_by" not in row and "patient_id" not in row
    assert db.rpc_calls == [("list_patient_medication_confirmations", {"p_patient_id": PATIENT})]


def test_an_unrecognised_cadence_is_left_as_written(client, db) -> None:
    db.rpc_handlers["list_patient_medication_confirmations"] = lambda _p: [
        stored(frequency="every other Tuesday after supper")
    ]
    as_user(PATIENT, "patient")
    row = client.get(MINE).json()[0]
    assert row["frequency"] == "every other Tuesday after supper"
    assert row["frequency_label_en"] is None and row["frequency_label_es"] is None


@pytest.mark.parametrize("answer", ["yes", "stopped", "unsure"])
def test_the_patient_answers_as_themselves(client, db, answer) -> None:
    as_user(PATIENT, "patient")
    response = client.post(f"{MINE}/{REQUEST}/answer", json={"answer": answer})
    assert response.status_code == 200 and response.json()["answer"] == answer
    (name, params), *_ = db.rpc_calls
    assert name == "answer_medication_confirmation"
    assert params["p_patient_id"] == PATIENT


def test_a_patient_supplied_actor_is_rejected(client, db) -> None:
    as_user(PATIENT, "patient")
    response = client.post(
        f"{MINE}/{REQUEST}/answer", json={"answer": "yes", "patient_id": str(uuid4())}
    )
    assert response.status_code == 422 and not db.rpc_calls


def test_it_changed_needs_a_note_and_the_note_is_bounded(client, db) -> None:
    as_user(PATIENT, "patient")
    assert client.post(f"{MINE}/{REQUEST}/answer", json={"answer": "changed"}).status_code == 422
    blank = {"answer": "changed", "note": "   "}
    assert client.post(f"{MINE}/{REQUEST}/answer", json=blank).status_code == 422
    long = {"answer": "changed", "note": "x" * 501}
    assert client.post(f"{MINE}/{REQUEST}/answer", json=long).status_code == 422
    ok = client.post(f"{MINE}/{REQUEST}/answer", json={"answer": "changed", "note": " 250 mg "})
    assert ok.status_code == 200 and db.rpc_calls[0][1]["p_note"] == "250 mg"


def test_an_unknown_answer_is_rejected(client, db) -> None:
    as_user(PATIENT, "patient")
    assert client.post(f"{MINE}/{REQUEST}/answer", json={"answer": "maybe"}).status_code == 422


def test_someone_elses_question_reads_as_not_found(client, db) -> None:
    def deny(_p: dict[str, Any]) -> Any:
        raise api_error("42501")

    db.rpc_handlers["answer_medication_confirmation"] = deny
    as_user(PATIENT, "patient")
    assert client.post(f"{MINE}/{uuid4()}/answer", json={"answer": "yes"}).status_code == 404


def test_a_different_second_answer_is_a_conflict_and_an_expired_one_is_refused(client, db) -> None:
    def answered(_p: dict[str, Any]) -> Any:
        raise api_error("40001", "MEDCONFIRM_ALREADY_ANSWERED: x", "MEDCONFIRM_ALREADY_ANSWERED")

    db.rpc_handlers["answer_medication_confirmation"] = answered
    as_user(PATIENT, "patient")
    conflict = client.post(f"{MINE}/{REQUEST}/answer", json={"answer": "stopped"})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "MEDCONFIRM_ALREADY_ANSWERED"

    def expired(_p: dict[str, Any]) -> Any:
        raise api_error("22023", "MEDCONFIRM_EXPIRED: x", "MEDCONFIRM_EXPIRED")

    db.rpc_handlers["answer_medication_confirmation"] = expired
    gone = client.post(f"{MINE}/{REQUEST}/answer", json={"answer": "yes"})
    assert gone.status_code == 422 and gone.json()["error"]["code"] == "MEDCONFIRM_EXPIRED"


def test_the_open_question_limit_is_a_validation_error(client, db) -> None:
    def full(_p: dict[str, Any]) -> Any:
        raise api_error("54000")

    db.rpc_handlers["create_medication_confirmation"] = full
    as_user(CLINICIAN)
    assert client.post(BASE, json={}).status_code == 422
