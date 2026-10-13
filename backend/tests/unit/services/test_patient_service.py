"""Tests for patient-scoped ADR information requests."""

from types import SimpleNamespace
from unittest.mock import MagicMock, call
from uuid import uuid4

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.models.adr import (
    ADRInformationAnswer,
    ADRInformationResponseRequest,
)
from app.pharmacovigilance import NaranjoAnswer, NaranjoQuestion
from app.services.patient_service import PatientService


def _query(response: SimpleNamespace) -> MagicMock:
    query = MagicMock()
    for method in ("select", "eq", "single", "order"):
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
            data={
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
    db.table.return_value = _query(
        SimpleNamespace(
            data={
                "id": str(request_id),
                "patient_id": str(uuid4()),
                "status": "pending",
            }
        )
    )

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
    db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_patient_must_answer_every_requested_question() -> None:
    patient_id = uuid4()
    request_id = uuid4()
    db = MagicMock()
    db.table.return_value = _query(
        SimpleNamespace(
            data={
                "id": str(request_id),
                "patient_id": str(patient_id),
                "status": "pending",
                "requested_information": [
                    "dose_response",
                    "similar_previous_reaction",
                ],
            }
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
