"""Validation boundaries for patient-safe ADR follow-up payloads."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.models.adr import (
    ADRFollowUpOverviewRead,
    ADRFollowUpRequestRead,
    ADRInformationAnswer,
    ADRInformationResponseRequest,
    ADRReviewAction,
    ADRReviewDecisionRequest,
)
from app.pharmacovigilance import NaranjoAnswer, NaranjoQuestion


def test_clinician_can_request_only_patient_answerable_questions() -> None:
    with pytest.raises(PydanticValidationError, match="patient-answerable"):
        ADRReviewDecisionRequest(
            action=ADRReviewAction.REQUEST_INFORMATION,
            note="Please provide more information.",
            requested_information=[NaranjoQuestion.OBJECTIVE_EVIDENCE],
        )


def test_information_request_requires_at_least_one_question() -> None:
    with pytest.raises(PydanticValidationError, match="Select at least one"):
        ADRReviewDecisionRequest(
            action=ADRReviewAction.REQUEST_INFORMATION,
            note="Please provide more information.",
        )


def test_known_patient_answer_requires_description() -> None:
    with pytest.raises(PydanticValidationError, match="Describe what happened"):
        ADRInformationAnswer(
            question=NaranjoQuestion.DOSE_RESPONSE,
            answer=NaranjoAnswer.YES,
        )


def test_patient_response_must_be_confirmed_and_unique() -> None:
    answer = ADRInformationAnswer(
        question=NaranjoQuestion.SIMILAR_PREVIOUS_REACTION,
        answer=NaranjoAnswer.DO_NOT_KNOW,
    )
    with pytest.raises(PydanticValidationError, match="Confirm the answers"):
        ADRInformationResponseRequest(answers=[answer], confirmed=False)
    with pytest.raises(PydanticValidationError, match="answered once"):
        ADRInformationResponseRequest(answers=[answer, answer], confirmed=True)


def _follow_up_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": "00000000-0000-4000-8000-000000000001",
        "adr_assessment_id": "00000000-0000-4000-8000-000000000002",
        "status": "answered",
        "symptom": "Synthetic dizziness",
        "suspect_medication_name": "Synthetic medicine",
        "requested_information": ["dose_response"],
        "patient_message": "Please tell us what happened.",
        "created_at": "2026-10-01T10:00:00+00:00",
        "responded_at": "2026-10-02T10:00:00+00:00",
        "responses": [
            {"question": "dose_response", "answer": "yes", "evidence": "It eased."},
        ],
    }
    row.update(overrides)
    return row


def test_follow_up_read_keeps_only_patient_answerable_questions_in_order() -> None:
    item = ADRFollowUpRequestRead.model_validate(
        _follow_up_row(
            requested_information=[
                "similar_previous_reaction",
                "objective_evidence",
                "free text",
                7,
                "dose_response",
                "similar_previous_reaction",
            ]
        )
    )
    assert item.requested_information == [
        NaranjoQuestion.SIMILAR_PREVIOUS_REACTION,
        NaranjoQuestion.DOSE_RESPONSE,
    ]
    assert (
        ADRFollowUpRequestRead.model_validate(
            _follow_up_row(requested_information=None)
        ).requested_information
        == []
    )


def test_follow_up_read_never_serializes_score_or_causality() -> None:
    item = ADRFollowUpRequestRead.model_validate(
        _follow_up_row(current_naranjo_score=6, current_causality="probable", naranjo_score=6)
    )
    dumped = ADRFollowUpOverviewRead(selected=item, recent=[item]).model_dump(mode="json")
    serialized = str(dumped)
    assert "naranjo_score" not in serialized
    assert "causality" not in serialized
    assert dumped["selected"]["responses"] == [
        {"question": "dose_response", "answer": "yes", "evidence": "It eased."}
    ]
    assert dumped["selected"]["closed_at"] is None
    assert dumped["selected"]["replacement_request_id"] is None


def test_follow_up_overview_bounds_recent_history() -> None:
    item = ADRFollowUpRequestRead.model_validate(_follow_up_row())
    assert ADRFollowUpOverviewRead().model_dump() == {
        "selected": None,
        "pending": [],
        "recent": [],
    }
    with pytest.raises(PydanticValidationError):
        ADRFollowUpOverviewRead(recent=[item] * 6)
