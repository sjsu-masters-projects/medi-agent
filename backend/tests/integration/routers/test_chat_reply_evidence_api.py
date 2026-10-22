"""AI-003: who may read the evidence one of Nora's replies used. Synthetic ids only."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import status

from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser

EVIDENCE = {
    "version": 1,
    "tools": ["get_patient_context"],
    "sources": [{"kind": "reference", "source": "MedlinePlus", "title": "Metformin"}],
    "care_plan_ids": [],
}


@pytest.fixture
def patient_id():
    return uuid4()


@pytest.fixture
def db():
    database = MagicMock()
    table = MagicMock()
    database.table.return_value = table
    for method in ("select", "eq", "limit"):
        getattr(table, method).return_value = table
    table.execute.return_value = MagicMock(data=[])
    app.dependency_overrides[get_db] = lambda: database
    yield database, table
    app.dependency_overrides.clear()


def _as(user: CurrentUser) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


def _row(patient_id, message_id):
    return {
        "message_id": str(message_id),
        "session_id": "day-2026-10-22",
        "evidence": EVIDENCE,
        "created_at": "2026-10-22T10:00:00+00:00",
    }


def test_patient_reads_the_evidence_of_their_own_reply(client, db, patient_id):
    _, table = db
    message_id = uuid4()
    _as(CurrentUser(id=patient_id, email="p@test.com", role="patient"))
    table.execute.return_value = MagicMock(data=[_row(patient_id, message_id)])

    response = client.get(f"/api/v1/chat/evidence/{patient_id}/{message_id}")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["evidence"]["tools"] == ["get_patient_context"]
    filters = {call.args for call in table.eq.call_args_list}
    assert ("patient_id", str(patient_id)) in filters  # ownership is part of the query


def test_a_patient_cannot_read_another_patients_evidence(client, db, patient_id):
    _, table = db
    _as(CurrentUser(id=uuid4(), email="other@test.com", role="patient"))

    response = client.get(f"/api/v1/chat/evidence/{patient_id}/{uuid4()}")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    table.execute.assert_not_called()  # denied before any evidence is read


def test_an_unassigned_clinician_is_denied(client, db, patient_id):
    _, table = db
    _as(CurrentUser(id=uuid4(), email="c@test.com", role="clinician", aal="aal2"))
    table.execute.return_value = MagicMock(data=[])  # no active care-team link

    response = client.get(f"/api/v1/chat/evidence/{patient_id}/{uuid4()}")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert table.execute.call_count == 1  # only the assignment check ran


def test_an_assigned_clinician_reads_their_patients_evidence(client, db, patient_id):
    _, table = db
    message_id = uuid4()
    _as(CurrentUser(id=uuid4(), email="c@test.com", role="clinician", aal="aal2"))
    table.execute.side_effect = [
        MagicMock(data=[{"id": str(uuid4())}]),
        MagicMock(data=[_row(patient_id, message_id)]),
    ]

    response = client.get(f"/api/v1/chat/evidence/{patient_id}/{message_id}")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message_id"] == str(message_id)


def test_a_reply_without_stored_evidence_is_not_found(client, db, patient_id):
    _as(CurrentUser(id=patient_id, email="p@test.com", role="patient"))

    response = client.get(f"/api/v1/chat/evidence/{patient_id}/{uuid4()}")

    assert response.status_code == status.HTTP_404_NOT_FOUND
