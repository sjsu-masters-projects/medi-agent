"""PV-001-D: clinician Naranjo answers on an open ADR assessment."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from app.models.adr import ADRClinicianAnswersRequest
from app.services.care_team_access import PatientAccess
from app.services.clinician_service import ClinicianService

TEAM_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"
OTHER_TEAM = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2"


def _response(data):
    return SimpleNamespace(data=data, count=None)


class _Access:
    def __init__(self, teams=frozenset({TEAM_ID})):
        self.teams = teams

    def for_patient(self, clinician_id, patient_id, *, require=True):
        return PatientAccess(str(clinician_id), str(patient_id), self.teams)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def service(mock_db):
    built = ClinicianService(db=mock_db)
    built.care_access = _Access()  # type: ignore[assignment]
    built._assert_patient_assignment = AsyncMock()  # type: ignore[method-assign]
    return built


def _assessment(patient_id, **overrides):
    row = {
        "id": str(uuid4()),
        "patient_id": str(patient_id),
        "status": "draft",
        "naranjo_answers": {"reappeared_on_rechallenge": "yes", "dose_response": "yes"},
        "reviewed_by": None,
        "reviewed_by_care_team_id": None,
    }
    row.update(overrides)
    return row


def _request(**overrides):
    body = {
        "answers": [
            {"question": "alternative_causes", "answer": "no", "basis": "No other cause found."},
            {"question": "objective_evidence", "answer": "do_not_know"},
        ]
    }
    body.update(overrides)
    return ADRClinicianAnswersRequest.model_validate(body)


def _api_error(code):
    return APIError({"code": code, "message": "PATIENT TEXT MUST NOT LEAK", "details": None})


@pytest.mark.asyncio
async def test_records_merged_answers_with_a_deterministic_rescore(service, mock_db):
    clinician_id, patient_id = uuid4(), uuid4()
    assessment = _assessment(patient_id)
    saved = {**assessment, "naranjo_score": 5, "causality": "Probable"}
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[_response(assessment), _response([saved])]
    )

    result = await service.record_adr_clinician_answers(clinician_id, assessment["id"], _request())

    assert result == saved
    name, payload = mock_db.rpc.call_args.args
    assert name == "record_adr_clinician_answers"
    assert payload["p_actor_id"] == str(clinician_id)
    assert payload["p_care_team_id"] == TEAM_ID
    # Stored patient answers are kept and the clinician answers are added.
    assert payload["p_naranjo_answers"] == {
        "reappeared_on_rechallenge": "yes",
        "dose_response": "yes",
        "alternative_causes": "no",
        "objective_evidence": "do_not_know",
    }
    # Restart yes +2, dose-response yes +1, alternative causes no +2: 5 is Probable.
    assert payload["p_score"] == 5
    assert payload["p_causality"] == "Probable"
    assert payload["p_naranjo_assessment"]["score"] == 5
    assert payload["p_answers"] == [
        {"question": "alternative_causes", "answer": "no", "basis": "No other cause found."},
        {"question": "objective_evidence", "answer": "do_not_know", "basis": None},
    ]
    service._assert_patient_assignment.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_concurrent_answer_rereads_and_retries_once(service, mock_db):
    patient_id = uuid4()
    first = _assessment(patient_id, naranjo_answers={})
    second = _assessment(patient_id, id=first["id"], naranjo_answers={"dose_response": "yes"})
    saved = {**second, "naranjo_score": 3}
    mock_db.rpc.side_effect = [object(), object()]
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _response(first),
            _api_error("40001"),
            _response(second),
            _response([saved]),
        ]
    )

    result = await service.record_adr_clinician_answers(uuid4(), first["id"], _request())

    assert result == saved
    retried = mock_db.rpc.call_args_list[-1].args[1]
    assert retried["p_naranjo_answers"]["dose_response"] == "yes"
    assert retried["p_score"] == 3  # dose-response +1, alternative causes no +2


@pytest.mark.asyncio
async def test_a_second_concurrent_change_is_a_conflict(service):
    patient_id = uuid4()
    assessment = _assessment(patient_id)
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _response(assessment),
            _api_error("40001"),
            _response(assessment),
            _api_error("40001"),
        ]
    )

    with pytest.raises(ConflictError) as raised:
        await service.record_adr_clinician_answers(uuid4(), assessment["id"], _request())
    assert raised.value.code == "ADR_ASSESSMENT_CHANGED"


@pytest.mark.parametrize(
    ("code", "error", "text"),
    [
        ("P0002", NotFoundError, None),
        ("42501", NotFoundError, None),
        ("23514", ValidationError, "already been completed"),
        ("22023", ValidationError, "could not be accepted"),
        ("PGRST202", ServiceUnavailableError, "not available yet"),
        ("XX000", ExternalServiceError, None),
    ],
)
@pytest.mark.asyncio
async def test_database_refusals_map_to_service_errors_without_details(service, code, error, text):
    assessment = _assessment(uuid4())
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[_response(assessment), _api_error(code)]
    )

    with pytest.raises(error) as raised:
        await service.record_adr_clinician_answers(uuid4(), assessment["id"], _request())
    assert "PATIENT TEXT" not in str(raised.value)
    if text:
        assert text in str(raised.value)


@pytest.mark.asyncio
async def test_a_completed_review_is_refused_before_the_database(service, mock_db):
    assessment = _assessment(
        uuid4(), status="reviewed", reviewed_by=str(uuid4()), reviewed_by_care_team_id=TEAM_ID
    )
    service._execute = AsyncMock(return_value=_response(assessment))  # type: ignore[method-assign]

    with pytest.raises(ValidationError, match="already been completed"):
        await service.record_adr_clinician_answers(uuid4(), assessment["id"], _request())
    mock_db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_another_teams_assessment_looks_unknown(service, mock_db):
    assessment = _assessment(uuid4(), reviewed_by=str(uuid4()), reviewed_by_care_team_id=OTHER_TEAM)
    service._execute = AsyncMock(return_value=_response(assessment))  # type: ignore[method-assign]

    with pytest.raises(NotFoundError):
        await service.record_adr_clinician_answers(uuid4(), assessment["id"], _request())
    mock_db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_an_unassigned_clinician_is_denied(service, mock_db):
    service._assert_patient_assignment = AsyncMock(  # type: ignore[method-assign]
        side_effect=AuthorizationError("You are not assigned to this patient")
    )
    assessment = _assessment(uuid4())
    service._execute = AsyncMock(return_value=_response(assessment))  # type: ignore[method-assign]

    with pytest.raises(AuthorizationError):
        await service.record_adr_clinician_answers(uuid4(), assessment["id"], _request())
    mock_db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_a_clinician_with_two_teams_must_choose(service, mock_db):
    service.care_access = _Access(frozenset({TEAM_ID, OTHER_TEAM}))  # type: ignore[assignment]
    assessment = _assessment(uuid4())
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[_response(assessment), _response(assessment), _response([assessment])]
    )

    with pytest.raises(ValidationError) as raised:
        await service.record_adr_clinician_answers(uuid4(), assessment["id"], _request())
    assert raised.value.code == "CARE_TEAM_REQUIRED"
    mock_db.rpc.assert_not_called()

    await service.record_adr_clinician_answers(
        uuid4(), assessment["id"], _request(care_team_id=OTHER_TEAM)
    )
    assert mock_db.rpc.call_args.args[1]["p_care_team_id"] == OTHER_TEAM


def _clinician_entry(question, answer, basis=None, **overrides):
    entry = {"question": question, "answer": answer, "source": "clinician_entry"}
    if basis:
        entry["evidence"] = basis
    entry.update(overrides)
    return entry


def _already_saved(patient_id):
    """The case after the default request was saved once."""
    return _assessment(
        patient_id,
        naranjo_answers={"alternative_causes": "no", "objective_evidence": "do_not_know"},
        evidence=[
            _clinician_entry("alternative_causes", "no", "No other cause found."),
            _clinician_entry("objective_evidence", "do_not_know"),
        ],
    )


@pytest.mark.asyncio
async def test_a_repeated_save_changes_nothing(service, mock_db):
    assessment = _already_saved(uuid4())
    service._execute = AsyncMock(side_effect=[_response(assessment)])  # type: ignore[method-assign]

    result = await service.record_adr_clinician_answers(uuid4(), assessment["id"], _request())

    # No write, no new evidence and no audit event: the case is returned as it stands.
    assert result == assessment
    mock_db.rpc.assert_not_called()
    service._execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_only_the_changed_answers_are_sent(service, mock_db):
    assessment = _already_saved(uuid4())
    saved = {**assessment, "naranjo_score": 4}
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[_response(assessment), _response([saved])]
    )
    request = _request(
        answers=[
            {"question": "alternative_causes", "answer": "no", "basis": "No other cause found."},
            {"question": "objective_evidence", "answer": "yes", "basis": "Positive test result."},
        ]
    )

    await service.record_adr_clinician_answers(uuid4(), assessment["id"], request)

    payload = mock_db.rpc.call_args.args[1]
    assert payload["p_answers"] == [
        {"question": "objective_evidence", "answer": "yes", "basis": "Positive test result."}
    ]
    assert payload["p_naranjo_answers"]["objective_evidence"] == "yes"
    assert payload["p_naranjo_answers"]["alternative_causes"] == "no"


@pytest.mark.asyncio
async def test_the_same_answer_with_a_new_basis_is_recorded(service, mock_db):
    assessment = _already_saved(uuid4())
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[_response(assessment), _response([assessment])]
    )
    request = _request(
        answers=[
            {"question": "alternative_causes", "answer": "no", "basis": "Chart reviewed again."}
        ]
    )

    await service.record_adr_clinician_answers(uuid4(), assessment["id"], request)

    assert mock_db.rpc.call_args.args[1]["p_answers"] == [
        {"question": "alternative_causes", "answer": "no", "basis": "Chart reviewed again."}
    ]


@pytest.mark.asyncio
async def test_a_stored_answer_without_a_clinician_entry_still_gets_the_clinicians_basis(
    service, mock_db
):
    # The answer is stored, but it came from extraction, so there is no clinician basis yet.
    assessment = _assessment(
        uuid4(),
        naranjo_answers={"alternative_causes": "no"},
        evidence=[
            {"question": "alternative_causes", "answer": "no", "evidence": "No other cause found."}
        ],
    )
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[_response(assessment), _response([assessment])]
    )
    request = _request(
        answers=[
            {"question": "alternative_causes", "answer": "no", "basis": "No other cause found."}
        ]
    )

    await service.record_adr_clinician_answers(uuid4(), assessment["id"], request)

    assert [item["question"] for item in mock_db.rpc.call_args.args[1]["p_answers"]] == [
        "alternative_causes"
    ]


@pytest.mark.asyncio
async def test_the_latest_entry_decides_whether_an_answer_changed(service, mock_db):
    # No, then Yes, then No again: saving No now is a change from the latest answer, Yes.
    assessment = _assessment(
        uuid4(),
        naranjo_answers={"alternative_causes": "yes"},
        evidence=[
            _clinician_entry("alternative_causes", "no", "No other cause found."),
            _clinician_entry("alternative_causes", "yes", "A new drug was started."),
        ],
    )
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[_response(assessment), _response([assessment])]
    )
    request = _request(
        answers=[
            {"question": "alternative_causes", "answer": "no", "basis": "No other cause found."}
        ]
    )

    await service.record_adr_clinician_answers(uuid4(), assessment["id"], request)

    assert mock_db.rpc.call_count == 1
