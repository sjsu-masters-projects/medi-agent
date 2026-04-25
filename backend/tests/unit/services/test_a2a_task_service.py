"""Unit tests for A2A task lifecycle persistence."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.a2a_task_service import A2ATaskService


def _response(data):
    return SimpleNamespace(data=data)


@pytest.fixture
def mock_db():
    db = MagicMock()
    table = MagicMock()
    db.table.return_value = table

    for method in ["select", "eq", "lte", "order", "limit", "insert", "update"]:
        getattr(table, method).return_value = table

    return db


@pytest.mark.asyncio
async def test_run_symptom_to_pharmacovigilance_completes_lifecycle(mock_db):
    task_id = str(uuid4())
    submitted = {
        "id": task_id,
        "status": "submitted",
        "target_agent": "pharmacovigilance",
    }
    working = {
        "id": task_id,
        "status": "working",
        "target_agent": "pharmacovigilance",
    }
    completed = {
        "id": task_id,
        "status": "completed",
        "target_agent": "pharmacovigilance",
    }
    mock_db.table().execute.side_effect = [
        _response([]),
        _response([submitted]),
        _response([working]),
        _response([completed]),
    ]

    service = A2ATaskService(mock_db)
    result = await service.run_symptom_to_pharmacovigilance(
        patient_id=str(uuid4()),
        payload={
            "session_id": "s-1",
            "symptom_report": {
                "symptom": "dizziness",
                "severity": 8,
                "flagged_for_adr": True,
            },
            "flagged_for_adr": True,
        },
    )

    assert result["status"] == "completed"
    statuses = [event["status"] for event in result["events"]]
    assert statuses == ["submitted", "working", "completed"]
    assert result["output"]["requires_clinician_review"] is True


@pytest.mark.asyncio
async def test_run_symptom_to_pharmacovigilance_marks_failed_on_error(mock_db, monkeypatch):
    task_id = str(uuid4())
    submitted = {
        "id": task_id,
        "status": "submitted",
        "target_agent": "pharmacovigilance",
    }
    retrying = {
        "id": task_id,
        "status": "retrying",
        "target_agent": "pharmacovigilance",
        "retry_attempt": 1,
        "max_retries": 3,
    }
    mock_db.table().execute.side_effect = [
        _response([]),
        _response([submitted]),
        _response([submitted]),
        _response([retrying]),
    ]

    service = A2ATaskService(mock_db)

    async def _boom(**_kwargs):
        raise RuntimeError("worker failure")

    monkeypatch.setattr(service, "mark_working", _boom)

    result = await service.run_symptom_to_pharmacovigilance(
        patient_id=str(uuid4()),
        payload={
            "session_id": "s-2",
            "symptom_event_id": str(uuid4()),
            "symptom_report": {"symptom": "nausea", "severity": 5},
        },
    )

    assert result["status"] == "retrying"
    statuses = [event["status"] for event in result["events"]]
    assert statuses[-1] == "retrying"


@pytest.mark.asyncio
async def test_submit_task_returns_existing_row_for_same_idempotency_key(mock_db):
    task_id = str(uuid4())
    existing = {
        "id": task_id,
        "patient_id": str(uuid4()),
        "idempotency_key": "symptom_event:test-1",
        "status": "submitted",
        "target_agent": "pharmacovigilance",
    }
    mock_db.table().execute.side_effect = [
        _response([existing]),
    ]

    service = A2ATaskService(mock_db)
    result = await service.submit_task(
        patient_id=existing["patient_id"],
        payload={
            "session_id": "session-1",
            "task_type": "symptom_adr_screen",
            "source_agent": "symptom",
            "target_agent": "pharmacovigilance",
            "symptom_event_id": "test-1",
            "idempotency_key": existing["idempotency_key"],
            "input_payload": {"severity": 8},
        },
    )

    assert result["id"] == task_id


@pytest.mark.asyncio
async def test_mark_failed_moves_task_to_dead_letter_after_max_retries(mock_db):
    task_id = str(uuid4())
    exhausted_task = {
        "id": task_id,
        "retry_attempt": 3,
        "max_retries": 3,
    }
    dead_letter_row = {
        "id": task_id,
        "status": "dead_letter",
        "retry_attempt": 4,
        "max_retries": 3,
    }
    mock_db.table().execute.side_effect = [
        _response([exhausted_task]),
        _response([dead_letter_row]),
    ]

    service = A2ATaskService(mock_db)
    result = await service.mark_failed(task_id=task_id, error_message="permanent worker failure")

    assert result["status"] == "dead_letter"
    assert result["retry_attempt"] == 4


@pytest.mark.asyncio
async def test_process_due_retries_completes_due_task(mock_db):
    task_id = str(uuid4())
    due_task = {
        "id": task_id,
        "task_type": "symptom_adr_screen",
        "retry_attempt": 1,
        "max_retries": 3,
        "input_payload": {
            "symptom_report": {
                "symptom": "rash",
                "severity": 8,
                "flagged_for_adr": True,
            }
        },
    }
    working = {
        "id": task_id,
        "status": "working",
        "target_agent": "pharmacovigilance",
    }
    completed = {
        "id": task_id,
        "status": "completed",
        "target_agent": "pharmacovigilance",
    }
    mock_db.table().execute.side_effect = [
        _response([due_task]),
        _response([due_task]),
        _response([working]),
        _response([completed]),
    ]

    service = A2ATaskService(mock_db)
    summary = await service.process_due_retries(batch_size=10)

    assert summary == {
        "scanned": 1,
        "completed": 1,
        "rescheduled": 0,
        "dead_lettered": 0,
        "failed": 0,
    }


@pytest.mark.asyncio
async def test_process_due_retries_dead_letters_unsupported_task_type(mock_db):
    task_id = str(uuid4())
    due_task = {
        "id": task_id,
        "task_type": "unknown_task",
        "retry_attempt": 2,
        "max_retries": 2,
        "input_payload": {},
    }
    working = {
        "id": task_id,
        "status": "working",
        "target_agent": "pharmacovigilance",
    }
    dead_letter = {
        "id": task_id,
        "status": "dead_letter",
        "retry_attempt": 3,
        "max_retries": 2,
    }
    mock_db.table().execute.side_effect = [
        _response([due_task]),
        _response([due_task]),
        _response([working]),
        _response([due_task]),
        _response([dead_letter]),
    ]

    service = A2ATaskService(mock_db)
    summary = await service.process_due_retries(batch_size=10)

    assert summary == {
        "scanned": 1,
        "completed": 0,
        "rescheduled": 0,
        "dead_lettered": 1,
        "failed": 0,
    }


@pytest.mark.asyncio
async def test_execute_retries_transient_connection_errors(mock_db):
    query = MagicMock()
    query.execute.side_effect = [
        RuntimeError("[Errno 54] Connection reset by peer"),
        _response([{"id": "task-1"}]),
    ]
    service = A2ATaskService(mock_db)

    result = await service._execute(query)

    assert result.data == [{"id": "task-1"}]
    assert query.execute.call_count == 2


@pytest.mark.asyncio
async def test_execute_does_not_retry_non_transient_errors(mock_db):
    query = MagicMock()
    query.execute.side_effect = RuntimeError("invalid select clause")
    service = A2ATaskService(mock_db)

    with pytest.raises(RuntimeError, match="invalid select clause"):
        await service._execute(query)

    assert query.execute.call_count == 1
