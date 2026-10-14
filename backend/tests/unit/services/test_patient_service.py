"""Tests for patient-scoped ADR information requests."""

import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, call
from uuid import UUID, uuid4

import pytest
from postgrest.exceptions import APIError

from app.core.exceptions import ExternalServiceError, NotFoundError, ValidationError
from app.models.adr import (
    ADRFollowUpOverviewRead,
    ADRInformationAnswer,
    ADRInformationResponseRequest,
)
from app.pharmacovigilance import NaranjoAnswer, NaranjoQuestion
from app.services.patient_service import PatientService


def _query(response: SimpleNamespace) -> MagicMock:
    query = MagicMock()
    for method in ("select", "eq", "in_", "gte", "order", "limit"):
        getattr(query, method).return_value = query
    query.execute.return_value = response
    return query


@pytest.mark.asyncio
async def test_list_adr_information_requests_filters_non_patient_questions() -> None:
    patient_id = uuid4()
    request_id = uuid4()
    assessment_id = uuid4()
    db = MagicMock()
    db.table.return_value = _query(
        SimpleNamespace(
            data=[
                {
                    "id": str(request_id),
                    "adr_assessment_id": str(assessment_id),
                    "requested_information": [
                        "dose_response",
                        "objective_evidence",
                    ],
                    "patient_message": "Tell us what happened after the prior dose change.",
                    "status": "pending",
                    "created_at": "2026-10-06T10:00:00Z",
                    "adr_assessments": {
                        "suspect_medication_name": "lisinopril",
                        "naranjo_score": 3,
                        "causality": "Possible",
                        "symptom_reports": {"symptom": "dizziness", "severity": 4},
                    },
                }
            ]
        )
    )

    result = await PatientService(db).list_adr_information_requests(patient_id)

    assert len(result) == 1
    assert result[0]["requested_information"] == [NaranjoQuestion.DOSE_RESPONSE]
    assert result[0]["symptom"] == "dizziness"
    assert result[0]["suspect_medication_name"] == "lisinopril"


@pytest.mark.asyncio
async def test_patient_response_rescores_and_appends_attributed_evidence() -> None:
    patient_id = uuid4()
    request_id = uuid4()
    assessment_id = uuid4()
    db = MagicMock()
    request_query = _query(
        SimpleNamespace(
            data=[
                {
                    "id": str(request_id),
                    "adr_assessment_id": str(assessment_id),
                    "patient_id": str(patient_id),
                    "requested_information": ["dose_response"],
                    "status": "pending",
                    "adr_assessments": {
                        "naranjo_answers": {"event_after_drug": "yes"},
                        "naranjo_assessment": {},
                        "evidence": [
                            {
                                "question": "event_after_drug",
                                "answer": "yes",
                                "evidence": "The symptom started after the medication.",
                            }
                        ],
                        "status": "draft",
                    },
                }
            ]
        )
    )
    rpc_query = MagicMock()
    rpc_query.execute.return_value = SimpleNamespace(
        data=[
            {
                "id": str(request_id),
                "adr_assessment_id": str(assessment_id),
                "status": "answered",
                "resolved_naranjo_score": 3,
                "resolved_causality": "Possible",
                "responded_at": "2026-10-06T10:05:00Z",
            }
        ]
    )
    db.table.return_value = request_query
    db.rpc.return_value = rpc_query

    result = await PatientService(db).respond_to_adr_information_request(
        patient_id,
        request_id,
        ADRInformationResponseRequest(
            answers=[
                ADRInformationAnswer(
                    question=NaranjoQuestion.DOSE_RESPONSE,
                    answer=NaranjoAnswer.YES,
                    evidence="It improved after my clinician lowered the dose.",
                )
            ],
            confirmed=True,
        ),
    )

    assert result["status"] == "answered"
    assert result["naranjo_score"] == 3
    assert db.table.call_args_list == [call("adr_information_requests")]
    rpc_payload = db.rpc.call_args.args[1]
    assert rpc_payload["p_naranjo_answers"] == {
        "event_after_drug": "yes",
        "dose_response": "yes",
    }
    assert rpc_payload["p_score"] == 3
    assert rpc_payload["p_causality"] == "Possible"
    assert rpc_payload["p_evidence"][-1] == {
        "question": "dose_response",
        "answer": "yes",
        "evidence": "It improved after my clinician lowered the dose.",
        "source": "patient_follow_up",
        "information_request_id": str(request_id),
    }


@pytest.mark.asyncio
async def test_patient_cannot_answer_another_patients_request() -> None:
    patient_id = uuid4()
    request_id = uuid4()
    db = MagicMock()
    # The service filters patient_id in the query; a foreign row is never returned, so
    # the zero-row result is the realistic case and must give the same 404.
    request_query = _query(SimpleNamespace(data=[]))
    db.table.return_value = request_query

    with pytest.raises(NotFoundError):
        await PatientService(db).respond_to_adr_information_request(
            patient_id,
            request_id,
            ADRInformationResponseRequest(
                answers=[
                    ADRInformationAnswer(
                        question=NaranjoQuestion.DOSE_RESPONSE,
                        answer=NaranjoAnswer.DO_NOT_KNOW,
                    )
                ],
                confirmed=True,
            ),
        )
    request_query.eq.assert_any_call("patient_id", str(patient_id))
    request_query.single.assert_not_called()
    db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_patient_must_answer_every_requested_question() -> None:
    patient_id = uuid4()
    request_id = uuid4()
    db = MagicMock()
    db.table.return_value = _query(
        SimpleNamespace(
            data=[
                {
                    "id": str(request_id),
                    "patient_id": str(patient_id),
                    "status": "pending",
                    "requested_information": [
                        "dose_response",
                        "similar_previous_reaction",
                    ],
                    "adr_assessments": {"status": "draft"},
                }
            ]
        )
    )

    with pytest.raises(ValidationError, match="every requested question"):
        await PatientService(db).respond_to_adr_information_request(
            patient_id,
            request_id,
            ADRInformationResponseRequest(
                answers=[
                    ADRInformationAnswer(
                        question=NaranjoQuestion.DOSE_RESPONSE,
                        answer=NaranjoAnswer.DO_NOT_KNOW,
                    )
                ],
                confirmed=True,
            ),
        )
    db.rpc.assert_not_called()


def _dose_response_answer() -> ADRInformationResponseRequest:
    return ADRInformationResponseRequest(
        answers=[
            ADRInformationAnswer(
                question=NaranjoQuestion.DOSE_RESPONSE,
                answer=NaranjoAnswer.DO_NOT_KNOW,
            )
        ],
        confirmed=True,
    )


@pytest.mark.asyncio
async def test_answered_request_is_reported_closed() -> None:
    patient_id = uuid4()
    request_id = uuid4()
    db = MagicMock()
    db.table.return_value = _query(
        SimpleNamespace(
            data=[
                {
                    "id": str(request_id),
                    "patient_id": str(patient_id),
                    "status": "answered",
                    "requested_information": ["dose_response"],
                    "adr_assessments": {"status": "draft"},
                }
            ]
        )
    )

    with pytest.raises(ValidationError) as raised:
        await PatientService(db).respond_to_adr_information_request(
            patient_id, request_id, _dose_response_answer()
        )
    assert raised.value.code == "ADR_REQUEST_CLOSED"
    db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_rpc_check_violation_is_reported_closed_without_detail() -> None:
    patient_id = uuid4()
    request_id = uuid4()
    db = MagicMock()
    db.table.return_value = _query(
        SimpleNamespace(
            data=[
                {
                    "id": str(request_id),
                    "adr_assessment_id": str(uuid4()),
                    "patient_id": str(patient_id),
                    "status": "pending",
                    "requested_information": ["dose_response"],
                    "adr_assessments": {"status": "draft"},
                }
            ]
        )
    )
    db.rpc.return_value.execute.side_effect = APIError(
        {"code": "23514", "message": "ADR information request has already been completed"}
    )

    with pytest.raises(ValidationError) as raised:
        await PatientService(db).respond_to_adr_information_request(
            patient_id, request_id, _dose_response_answer()
        )
    assert raised.value.code == "ADR_REQUEST_CLOSED"
    assert "already been completed" not in raised.value.message


# ── Follow-up overview read model (R6.1-R6.5) ────────────────────────────────


def _follow_up_row(
    *,
    status: str = "pending",
    assessment_id: str | None = None,
    request_id: str | None = None,
    requested_information: list[str] | None = None,
    created_at: str = "2026-10-06T10:00:00Z",
    **overrides: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": request_id or str(uuid4()),
        "adr_assessment_id": assessment_id or str(uuid4()),
        "requested_information": (
            ["dose_response"] if requested_information is None else requested_information
        ),
        "patient_message": "Tell us about the prior dose change.",
        "status": status,
        "responses": [],
        "created_at": created_at,
        "responded_at": None,
        "updated_at": "2026-10-07T09:00:00Z",
        # Score and causality are deliberately present so tests prove they never leak.
        "resolved_naranjo_score": 4,
        "resolved_causality": "Possible",
        "adr_assessments": {
            "suspect_medication_name": "lisinopril",
            "naranjo_score": 3,
            "causality": "Possible",
            "symptom_reports": {"symptom": "dizziness"},
        },
    }
    row.update(overrides)
    return row


def _overview_db(*row_sets: list[dict[str, Any]]) -> tuple[MagicMock, list[MagicMock]]:
    """A db whose successive ``table()`` calls return pending, recent, then selected queries."""
    queries = [_query(SimpleNamespace(data=rows)) for rows in row_sets]
    db = MagicMock()
    db.table.side_effect = queries
    return db, queries


def _contains_key_fragment(value: Any, fragments: tuple[str, ...]) -> bool:
    if isinstance(value, dict):
        return any(
            any(fragment in str(key) for fragment in fragments)
            or _contains_key_fragment(item, fragments)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_key_fragment(item, fragments) for item in value)
    return False


@pytest.mark.asyncio
@pytest.mark.parametrize("selector", ["none", "request", "assessment"])
async def test_overview_filters_patient_id_on_every_query(selector: str) -> None:
    patient_id = uuid4()
    selected = _follow_up_row(status="answered")
    row_sets: list[list[dict[str, Any]]] = [[], []]
    kwargs: dict[str, UUID] = {}
    if selector == "request":
        row_sets.append([selected])
        kwargs["request_id"] = UUID(selected["id"])
    elif selector == "assessment":
        row_sets.append([selected])
        kwargs["assessment_id"] = UUID(selected["adr_assessment_id"])
    db, queries = _overview_db(*row_sets)

    await PatientService(db).get_adr_follow_up_overview(patient_id, **kwargs)

    assert len(queries) == db.table.call_count
    for query in queries:
        query.eq.assert_any_call("patient_id", str(patient_id))
        select_columns = query.select.call_args.args[0]
        assert "naranjo" not in select_columns
        assert "causality" not in select_columns
    assert db.table.call_args_list == [call("adr_information_requests")] * len(queries)


@pytest.mark.asyncio
async def test_overview_pending_and_recent_bounds_and_ordering() -> None:
    patient_id = uuid4()
    newer = _follow_up_row(created_at="2026-10-06T10:00:00Z")
    older = _follow_up_row(created_at="2026-10-01T10:00:00Z")
    no_allowed_questions = _follow_up_row(requested_information=["objective_evidence"])
    recent_rows = [_follow_up_row(status="answered") for _ in range(6)]
    db, (pending_query, recent_query) = _overview_db(
        [newer, no_allowed_questions, older], recent_rows
    )

    before = datetime.now(UTC)
    result = await PatientService(db).get_adr_follow_up_overview(patient_id)
    after = datetime.now(UTC)

    pending_query.eq.assert_any_call("status", "pending")
    pending_query.order.assert_called_once_with("created_at", desc=True)
    # Newest first is preserved, and a row with no patient-answerable question is dropped.
    assert [item["id"] for item in result["pending"]] == [newer["id"], older["id"]]

    recent_query.in_.assert_called_once_with("status", ["answered", "cancelled"])
    recent_query.order.assert_called_once_with("created_at", desc=True)
    recent_query.limit.assert_called_once_with(5)
    gte_column, cutoff = recent_query.gte.call_args.args
    assert gte_column == "created_at"
    cutoff_at = datetime.fromisoformat(cutoff)
    assert before - timedelta(days=90) <= cutoff_at <= after - timedelta(days=90)
    assert len(result["recent"]) == 5
    assert result["selected"] is None


@pytest.mark.asyncio
async def test_overview_selects_request_in_any_status() -> None:
    patient_id = uuid4()
    cancelled = _follow_up_row(status="cancelled")
    db, queries = _overview_db([], [], [cancelled])

    result = await PatientService(db).get_adr_follow_up_overview(
        patient_id, request_id=UUID(cancelled["id"])
    )

    selected_query = queries[2]
    selected_query.eq.assert_any_call("id", cancelled["id"])
    selected_query.limit.assert_called_once_with(1)
    selected_query.in_.assert_not_called()
    assert result["selected"]["id"] == cancelled["id"]
    assert result["selected"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_overview_selects_newest_request_for_assessment() -> None:
    patient_id = uuid4()
    newest = _follow_up_row(status="answered")
    db, queries = _overview_db([], [], [newest])

    result = await PatientService(db).get_adr_follow_up_overview(
        patient_id, assessment_id=UUID(newest["adr_assessment_id"])
    )

    selected_query = queries[2]
    selected_query.eq.assert_any_call("adr_assessment_id", newest["adr_assessment_id"])
    selected_query.order.assert_called_once_with("created_at", desc=True)
    selected_query.limit.assert_called_once_with(1)
    assert result["selected"]["id"] == newest["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("selector", ["request_id", "assessment_id"])
async def test_overview_missing_and_foreign_ids_raise_the_same_not_found(selector: str) -> None:
    # The query filters patient_id, so another patient's row and a missing row both
    # come back as zero rows and must produce an indistinguishable error.
    errors = []
    for _ in ("missing", "foreign"):
        target = uuid4()
        db, _queries = _overview_db([], [], [])
        with pytest.raises(NotFoundError) as raised:
            await PatientService(db).get_adr_follow_up_overview(uuid4(), **{selector: target})
        errors.append((type(raised.value), raised.value.code, raised.value.message, target))

    for error_type, code, message, target in errors:
        assert error_type is NotFoundError
        assert code == "NOT_FOUND"
        assert message == f"ADR information request '{target}' not found"


@pytest.mark.asyncio
async def test_overview_rejects_both_request_and_assessment() -> None:
    db = MagicMock()

    with pytest.raises(ValidationError):
        await PatientService(db).get_adr_follow_up_overview(
            uuid4(), request_id=uuid4(), assessment_id=uuid4()
        )
    db.table.assert_not_called()


@pytest.mark.asyncio
async def test_overview_lifecycle_fields_are_status_specific() -> None:
    patient_id = uuid4()
    assessment_id = str(uuid4())
    replacement = _follow_up_row(assessment_id=assessment_id)
    cancelled = _follow_up_row(status="cancelled", assessment_id=assessment_id)
    cancelled_alone = _follow_up_row(status="cancelled")
    answered = _follow_up_row(
        status="answered",
        assessment_id=assessment_id,
        responded_at="2026-10-06T11:00:00Z",
        responses=[
            {"question": "dose_response", "answer": "yes", "evidence": "It eased."},
            {"question": "objective_evidence", "answer": "yes", "evidence": "Lab value"},
            {"question": "similar_previous_reaction", "answer": "maybe"},
        ],
    )
    cancelled_with_responses = _follow_up_row(
        status="cancelled",
        responses=[{"question": "dose_response", "answer": "no"}],
    )
    db, _queries = _overview_db(
        [replacement], [cancelled, cancelled_alone, answered, cancelled_with_responses]
    )

    result = await PatientService(db).get_adr_follow_up_overview(patient_id)

    by_id = {item["id"]: item for item in [*result["pending"], *result["recent"]]}
    assert by_id[cancelled["id"]]["replacement_request_id"] == replacement["id"]
    assert by_id[cancelled_alone["id"]]["replacement_request_id"] is None
    assert by_id[answered["id"]]["replacement_request_id"] is None
    assert by_id[replacement["id"]]["replacement_request_id"] is None

    assert by_id[cancelled["id"]]["closed_at"] == cancelled["updated_at"]
    assert by_id[answered["id"]]["closed_at"] is None
    assert by_id[replacement["id"]]["closed_at"] is None

    assert by_id[answered["id"]]["responses"] == [
        {"question": "dose_response", "answer": "yes", "evidence": "It eased."}
    ]
    assert by_id[cancelled_with_responses["id"]]["responses"] == []
    assert by_id[replacement["id"]]["responses"] == []


@pytest.mark.asyncio
async def test_overview_replacement_is_never_the_request_itself() -> None:
    patient_id = uuid4()
    request_id = str(uuid4())
    assessment_id = str(uuid4())
    pending = _follow_up_row(request_id=request_id, assessment_id=assessment_id)
    # Selected by ID as cancelled while the pending read still returns the same row
    # (a status change between reads): it must not point at itself.
    selected = _follow_up_row(
        status="cancelled", request_id=request_id, assessment_id=assessment_id
    )
    db, _queries = _overview_db([pending], [], [selected])

    result = await PatientService(db).get_adr_follow_up_overview(
        patient_id, request_id=UUID(request_id)
    )

    assert result["selected"]["replacement_request_id"] is None


@pytest.mark.asyncio
async def test_overview_output_carries_no_score_or_causality() -> None:
    patient_id = uuid4()
    selected = _follow_up_row(status="answered")
    db, _queries = _overview_db(
        [_follow_up_row()], [_follow_up_row(status="cancelled")], [selected]
    )

    result = await PatientService(db).get_adr_follow_up_overview(
        patient_id, request_id=UUID(selected["id"])
    )
    dumped = ADRFollowUpOverviewRead.model_validate(result).model_dump(mode="json")

    assert not _contains_key_fragment(result, ("naranjo", "causality"))
    assert not _contains_key_fragment(dumped, ("naranjo", "causality"))
    assert "Possible" not in str(dumped)


@pytest.mark.asyncio
async def test_overview_read_failure_is_external_without_postgrest_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    detail = "row contains patient text: chest pain after new dose"
    query = _query(SimpleNamespace(data=[]))
    query.execute.side_effect = APIError({"code": "42501", "message": detail, "details": detail})
    db = MagicMock()
    db.table.return_value = query

    with caplog.at_level(logging.DEBUG), pytest.raises(ExternalServiceError) as raised:
        await PatientService(db).get_adr_follow_up_overview(uuid4())

    assert raised.value.__cause__ is None
    assert detail not in raised.value.message
    assert detail not in caplog.text


# ── Respond error mapping (R3.7, R6.3, R6.4) ────────────────────────────────


def _pending_request_db(
    patient_id: UUID,
    request_id: UUID,
    *,
    status: str = "pending",
    assessment_status: str = "draft",
) -> MagicMock:
    db = MagicMock()
    db.table.return_value = _query(
        SimpleNamespace(
            data=[
                {
                    "id": str(request_id),
                    "adr_assessment_id": str(uuid4()),
                    "patient_id": str(patient_id),
                    "status": status,
                    "requested_information": ["dose_response"],
                    "adr_assessments": {"status": assessment_status},
                }
            ]
        )
    )
    return db


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "assessment_status"),
    [("cancelled", "draft"), ("pending", "reviewed")],
)
async def test_closed_request_or_reviewed_assessment_is_reported_closed(
    status: str, assessment_status: str
) -> None:
    patient_id = uuid4()
    request_id = uuid4()
    db = _pending_request_db(
        patient_id, request_id, status=status, assessment_status=assessment_status
    )

    with pytest.raises(ValidationError) as raised:
        await PatientService(db).respond_to_adr_information_request(
            patient_id, request_id, _dose_response_answer()
        )
    assert raised.value.code == "ADR_REQUEST_CLOSED"
    db.rpc.assert_not_called()


_RPC_SERVER_DETAIL = "server detail echoing patient answer: chest pain after new dose"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sqlstate", "error_type", "code"),
    [
        ("P0002", NotFoundError, "NOT_FOUND"),
        ("22023", ValidationError, "ADR_RESPONSE_INVALID"),
        ("XX000", ExternalServiceError, "EXTERNAL_SERVICE_ERROR"),
    ],
)
async def test_rpc_errors_map_by_sqlstate_without_server_text(
    sqlstate: str,
    error_type: type[Exception],
    code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    patient_id = uuid4()
    request_id = uuid4()
    db = _pending_request_db(patient_id, request_id)
    db.rpc.return_value.execute.side_effect = APIError(
        {"code": sqlstate, "message": _RPC_SERVER_DETAIL, "details": _RPC_SERVER_DETAIL}
    )

    with caplog.at_level(logging.DEBUG), pytest.raises(error_type) as raised:
        await PatientService(db).respond_to_adr_information_request(
            patient_id, request_id, _dose_response_answer()
        )

    error = raised.value
    assert type(error) is error_type
    assert getattr(error, "code", None) == code
    assert _RPC_SERVER_DETAIL not in str(error)
    assert _RPC_SERVER_DETAIL not in caplog.text


@pytest.mark.asyncio
async def test_respond_load_failure_is_external_without_postgrest_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    query = _query(SimpleNamespace(data=[]))
    query.execute.side_effect = APIError(
        {"code": "42501", "message": _RPC_SERVER_DETAIL, "details": _RPC_SERVER_DETAIL}
    )
    db = MagicMock()
    db.table.return_value = query

    with caplog.at_level(logging.DEBUG), pytest.raises(ExternalServiceError) as raised:
        await PatientService(db).respond_to_adr_information_request(
            uuid4(), uuid4(), _dose_response_answer()
        )

    assert _RPC_SERVER_DETAIL not in raised.value.message
    assert _RPC_SERVER_DETAIL not in caplog.text
    db.rpc.assert_not_called()
