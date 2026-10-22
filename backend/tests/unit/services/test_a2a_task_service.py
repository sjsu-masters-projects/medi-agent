"""Unit tests for A2A task lifecycle persistence."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.services.a2a_task_service import A2ATaskService


def _response(data):
    return SimpleNamespace(data=data)


@pytest.fixture
def mock_db():
    db = MagicMock()
    table = MagicMock()
    db.table.return_value = table

    for method in ["select", "eq", "lte", "order", "limit", "insert", "update", "upsert"]:
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
    symptom_id = str(uuid4())
    medication_id = str(uuid4())
    assessment_id = str(uuid4())
    mock_db.table().execute.side_effect = [
        _response([]),
        _response([]),
        _response([submitted]),
        _response([working]),
        _response([]),
        _response([{"id": assessment_id}]),
        _response([completed]),
    ]

    service = A2ATaskService(mock_db)
    result = await service.run_symptom_to_pharmacovigilance(
        patient_id=str(uuid4()),
        payload={
            "session_id": "s-1",
            "symptom_report": {
                "id": symptom_id,
                "symptom": "dizziness",
                "severity": 8,
                "flagged_for_adr": False,
                "confirmed_content": {
                    "answers": {
                        "product": {
                            "state": "answered",
                            "value": {"concern": True, "name": "Metformin"},
                        }
                    },
                    "context": {"medications": [{"source_id": medication_id, "name": "Metformin"}]},
                },
            },
            "naranjo_answers": {"event_after_drug": "yes"},
            "adr_evidence": [
                {
                    "question": "event_after_drug",
                    "answer": "yes",
                    "evidence": "I became dizzy after starting metformin.",
                }
            ],
        },
    )

    assert result["status"] == "completed"
    statuses = [event["status"] for event in result["events"]]
    assert statuses == ["submitted", "working", "completed"]
    assert result["output"]["requires_clinician_review"] is True
    assert result["output"]["adr_assessment_id"] == assessment_id
    assert result["output"]["naranjo_assistance"]["score"] == 2
    assert len(result["output"]["naranjo_assistance"]["missing_questions"]) == 9
    task_row = mock_db.table().insert.call_args_list[0].args[0]
    assert task_row["symptom_event_id"] == symptom_id
    assert task_row["idempotency_key"] == f"confirmed_symptom:{symptom_id}"
    assessment_row = mock_db.table().insert.call_args_list[1].args[0]
    assert assessment_row["symptom_report_id"] == symptom_id
    assert assessment_row["suspect_medication_id"] == medication_id
    assert assessment_row["naranjo_answers"] == {"event_after_drug": "yes"}
    assert assessment_row["evidence"][0]["evidence"].startswith("I became dizzy")


@pytest.mark.asyncio
async def test_completed_report_task_is_not_reopened_or_rewritten(mock_db):
    task_id = str(uuid4())
    assessment_id = str(uuid4())
    completed = {
        "id": task_id,
        "status": "completed",
        "target_agent": "pharmacovigilance",
        "output_payload": {
            "requires_clinician_review": True,
            "adr_assessment_id": assessment_id,
        },
    }
    mock_db.table().execute.side_effect = [_response([completed])]
    service = A2ATaskService(mock_db)

    result = await service.run_symptom_to_pharmacovigilance(
        patient_id=str(uuid4()),
        payload={
            "session_id": "s-1",
            "symptom_report": {"id": str(uuid4()), "flagged_for_adr": True},
        },
    )

    assert result["status"] == "completed"
    assert result["output"]["adr_assessment_id"] == assessment_id
    mock_db.table().update.assert_not_called()
    mock_db.table().insert.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["retrying", "working", "completed"])
async def test_confirmation_reuses_transactionally_queued_report_task(mock_db, status):
    report_id = str(uuid4())
    existing = {"id": str(uuid4()), "status": status, "target_agent": "pharmacovigilance"}
    mock_db.table().execute.side_effect = [_response([existing])]
    result = await A2ATaskService(mock_db).run_symptom_to_pharmacovigilance(
        patient_id=str(uuid4()), payload={"symptom_report": {"id": report_id}}
    )
    assert result["task_id"] == existing["id"]
    assert result["status"] == status
    mock_db.table().eq.assert_any_call("idempotency_key", f"confirmed_symptom:{report_id}")
    mock_db.table().insert.assert_not_called()
    mock_db.table().update.assert_not_called()


@pytest.mark.asyncio
async def test_confirmed_report_without_canonical_task_retains_legacy_task(mock_db):
    report_id = str(uuid4())
    existing = {"id": str(uuid4()), "status": "completed", "target_agent": "pharmacovigilance"}
    mock_db.table().execute.side_effect = [_response([]), _response([existing])]
    result = await A2ATaskService(mock_db).run_symptom_to_pharmacovigilance(
        patient_id=str(uuid4()), payload={"symptom_report": {"id": report_id}}
    )
    assert result["task_id"] == existing["id"]
    mock_db.table().eq.assert_any_call("idempotency_key", f"symptom_event:{report_id}")
    mock_db.table().insert.assert_not_called()
    mock_db.table().update.assert_not_called()


@pytest.mark.asyncio
async def test_existing_reviewed_assessment_is_never_reset_to_draft(mock_db):
    assessment = {
        "id": str(uuid4()),
        "symptom_report_id": str(uuid4()),
        "status": "reviewed",
    }
    mock_db.table().execute.side_effect = [_response([assessment])]
    service = A2ATaskService(mock_db)

    result = await service._persist_adr_assessment(
        patient_id=str(uuid4()),
        payload={
            "symptom_report": {
                "id": assessment["symptom_report_id"],
                "related_medication_id": str(uuid4()),
                "related_medication_name": "Metformin",
            }
        },
        output_payload={"naranjo_assistance": {"score": 0, "causality": "Doubtful"}},
    )

    assert result == assessment
    mock_db.table().insert.assert_not_called()


def test_pharmacovigilance_result_scores_only_explicit_naranjo_answers(mock_db):
    service = A2ATaskService(mock_db)

    result = service._build_pharmacovigilance_result(
        {
            "symptom_report": {"symptom": "rash", "severity": 10},
            "naranjo_answers": {
                "previous_reports": "yes",
                "event_after_drug": "yes",
                "alternative_causes": "no",
            },
        }
    )

    assert result["naranjo_assistance"]["score"] == 5
    assert result["naranjo_assistance"]["causality"] == "Probable"
    assert len(result["naranjo_assistance"]["missing_questions"]) == 7


def test_symptom_severity_never_changes_the_naranjo_score(mock_db):
    service = A2ATaskService(mock_db)

    result = service._build_pharmacovigilance_result(
        {"symptom_report": {"symptom": "rash", "severity": 10}}
    )

    assert result["requires_clinician_review"] is False
    assert result["naranjo_assistance"]["score"] == 0
    assert result["naranjo_assistance"]["causality"] == "Doubtful"


def test_confirmed_product_concern_uses_owned_active_medication_context(mock_db):
    medication_id = str(uuid4())
    report = {
        "id": str(uuid4()),
        "symptom": "nausea",
        "severity": 4,
        "flagged_for_adr": False,
        "confirmed_content": {
            "answers": {
                "product": {
                    "state": "answered",
                    "value": {"concern": True, "name": "metformin"},
                }
            },
            "context": {
                "medications": [{"source_id": medication_id, "name": "Metformin", "dose": "500 mg"}]
            },
        },
    }
    service = A2ATaskService(mock_db)

    result = service._build_pharmacovigilance_result({"symptom_report": report})

    assert result["requires_clinician_review"] is True
    assert service.confirmed_medication(report) == (medication_id, "Metformin")


def test_confirmed_unlisted_product_routes_to_identity_review_without_an_adr_score(mock_db):
    report = {
        "confirmation_state": "patient_confirmed",
        "symptom": "Synthetic concern",
        "severity": None,
        "confirmed_content": {
            "answers": {
                "product": {
                    "state": "answered",
                    "value": {
                        "concern": True,
                        "name": "Synthetic supplement",
                    },
                }
            },
            # A retrieval snapshot cannot manufacture the missing canonical FK.
            "context": {
                "medications": [{"source_id": str(uuid4()), "name": "Synthetic supplement"}]
            },
        },
    }
    service = A2ATaskService(mock_db)
    result = service._build_pharmacovigilance_result({"symptom_report": report})
    assert result["requires_clinician_review"] is True
    assert result["requires_medication_reconciliation"] is True
    assert result["naranjo_assistance"] is None
    assert "No medication or adverse reaction is confirmed" in result["recommendation"]
    assert service.confirmed_medication(report) == ("", "Synthetic supplement")


@pytest.mark.asyncio
async def test_retry_finishes_unlisted_product_screen_without_attempting_adr_creation(mock_db):
    service = A2ATaskService(mock_db)
    report = {
        "confirmation_state": "patient_confirmed",
        "symptom": "Synthetic concern",
        "confirmed_content": {
            "answers": {
                "product": {
                    "state": "answered",
                    "value": {"concern": True, "name": "Synthetic supplement"},
                }
            }
        },
    }
    working = {
        "id": str(uuid4()),
        "status": "working",
        "patient_id": str(uuid4()),
        "task_type": "symptom_adr_screen",
        "input_payload": {"symptom_report": report},
    }
    service._get_task = AsyncMock(return_value={**working, "status": "retrying"})
    service._claim_task = AsyncMock(return_value=(working, True))
    service._persist_adr_assessment = AsyncMock(
        side_effect=AssertionError("Must not invent an ADR")
    )
    service.mark_completed = AsyncMock(return_value={"status": "completed"})
    service.mark_failed = AsyncMock()
    assert (await service.retry_task(working["id"]))["status"] == "completed"
    service._persist_adr_assessment.assert_not_called()
    service.mark_failed.assert_not_called()
    assert service.mark_completed.call_args.kwargs["output_payload"][
        "requires_medication_reconciliation"
    ]


@pytest.mark.parametrize("answers", [[], "yes", 3])
def test_naranjo_answers_must_be_a_json_object(mock_db, answers):
    service = A2ATaskService(mock_db)

    with pytest.raises(ValidationError, match="naranjo_answers must be a JSON object"):
        service._build_pharmacovigilance_result(
            {
                "symptom_report": {"symptom": "rash", "severity": 7},
                "naranjo_answers": answers,
            }
        )


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

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("worker failure")

    monkeypatch.setattr(service, "_claim_submitted_task", _boom)

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
        "status": "working",
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
async def test_mark_failed_never_regresses_a_completed_task(mock_db):
    completed = {
        "id": str(uuid4()),
        "status": "completed",
        "retry_attempt": 0,
        "output_payload": {"adr_assessment_id": str(uuid4())},
    }
    mock_db.table().execute.side_effect = [_response([completed])]

    result = await A2ATaskService(mock_db).mark_failed(
        task_id=completed["id"], error_message="late response uncertainty"
    )

    assert result == completed
    mock_db.table().update.assert_not_called()


@pytest.mark.asyncio
async def test_process_due_retries_completes_due_task(mock_db):
    task_id = str(uuid4())
    patient_id = str(uuid4())
    symptom_id = str(uuid4())
    medication_id = str(uuid4())
    due_task = {
        "id": task_id,
        "status": "retrying",
        "patient_id": patient_id,
        "task_type": "symptom_adr_screen",
        "retry_attempt": 1,
        "max_retries": 3,
        "input_payload": {
            "symptom_report": {
                "id": symptom_id,
                "symptom": "rash",
                "severity": 8,
                "flagged_for_adr": True,
                "related_medication_id": medication_id,
                "related_medication_name": "Metformin",
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
        _response([]),
        _response([due_task]),
        _response([due_task]),
        _response([working]),
        _response([]),
        _response([{"id": str(uuid4())}]),
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
        "status": "retrying",
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
        _response([]),
        _response([due_task]),
        _response([due_task]),
        _response([working]),
        _response([{**due_task, "status": "working"}]),
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
async def test_worker_recovers_submitted_confirmed_report_task(mock_db):
    task_id = str(uuid4())
    patient_id = str(uuid4())
    symptom_id = str(uuid4())
    medication_id = str(uuid4())
    submitted = {
        "id": task_id,
        "status": "submitted",
        "patient_id": patient_id,
        "task_type": "symptom_adr_screen",
        "retry_attempt": 0,
        "max_retries": 3,
        "input_payload": {
            "symptom_report": {
                "id": symptom_id,
                "confirmed_content": {
                    "answers": {
                        "product": {
                            "state": "answered",
                            "value": {"concern": True, "name": "Metformin"},
                        }
                    },
                    "context": {"medications": [{"source_id": medication_id, "name": "Metformin"}]},
                },
            }
        },
    }
    working = {**submitted, "status": "working"}
    completed = {**submitted, "status": "completed"}
    mock_db.table().execute.side_effect = [
        _response([submitted]),
        _response([]),
        _response([submitted]),
        _response([working]),
        _response([]),
        _response([{"id": str(uuid4())}]),
        _response([completed]),
    ]

    summary = await A2ATaskService(mock_db).process_due_retries(batch_size=10)

    assert summary == {
        "scanned": 1,
        "completed": 1,
        "rescheduled": 0,
        "dead_lettered": 0,
        "failed": 0,
    }


@pytest.mark.asyncio
async def test_retry_task_does_not_reopen_terminal_task(mock_db):
    completed = {
        "id": str(uuid4()),
        "status": "completed",
        "output_payload": {"adr_assessment_id": str(uuid4())},
    }
    mock_db.table().execute.side_effect = [_response([completed])]

    result = await A2ATaskService(mock_db).retry_task(completed["id"])

    assert result == completed
    mock_db.table().update.assert_not_called()


def test_calculate_retry_delay_starts_at_one_second(mock_db):
    service = A2ATaskService(mock_db)

    assert service._calculate_retry_delay_seconds(0) == 1
    assert service._calculate_retry_delay_seconds(1) == 1
    assert service._calculate_retry_delay_seconds(2) == 2
    assert service._calculate_retry_delay_seconds(3) == 4


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
