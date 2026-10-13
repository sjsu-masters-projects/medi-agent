"""Validation boundaries for patient-safe ADR follow-up payloads."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.models.adr import (
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
