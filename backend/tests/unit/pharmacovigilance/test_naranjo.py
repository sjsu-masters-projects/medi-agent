"""The deterministic Naranjo scale used for clinician ADR decision support."""

from __future__ import annotations

import pytest

from app.models.enums import NaranjoCausality
from app.pharmacovigilance import NaranjoAnswer, NaranjoQuestion, score_naranjo
from app.pharmacovigilance.naranjo import NARANJO_WEIGHTS

EXPECTED_WEIGHTS = {
    NaranjoQuestion.PREVIOUS_REPORTS: (1, 0, 0),
    NaranjoQuestion.EVENT_AFTER_DRUG: (2, -1, 0),
    NaranjoQuestion.IMPROVED_ON_DECHALLENGE: (1, 0, 0),
    NaranjoQuestion.REAPPEARED_ON_RECHALLENGE: (2, -1, 0),
    NaranjoQuestion.ALTERNATIVE_CAUSES: (-1, 2, 0),
    NaranjoQuestion.REAPPEARED_WITH_PLACEBO: (-1, 1, 0),
    NaranjoQuestion.TOXIC_DRUG_CONCENTRATION: (1, 0, 0),
    NaranjoQuestion.DOSE_RESPONSE: (1, 0, 0),
    NaranjoQuestion.SIMILAR_PREVIOUS_REACTION: (1, 0, 0),
    NaranjoQuestion.OBJECTIVE_EVIDENCE: (1, 0, 0),
}


@pytest.mark.parametrize(("question", "expected"), EXPECTED_WEIGHTS.items())
def test_each_question_uses_the_published_answer_weights(
    question: NaranjoQuestion, expected: tuple[int, int, int]
) -> None:
    weights = NARANJO_WEIGHTS[question]

    assert (
        weights[NaranjoAnswer.YES],
        weights[NaranjoAnswer.NO],
        weights[NaranjoAnswer.DO_NOT_KNOW],
    ) == expected


@pytest.mark.parametrize(
    ("answers", "expected_score", "expected_causality"),
    [
        (
            {question: NaranjoAnswer.YES for question in NaranjoQuestion},
            8,
            NaranjoCausality.PROBABLE,
        ),
        (
            {
                **{question: NaranjoAnswer.YES for question in NaranjoQuestion},
                NaranjoQuestion.ALTERNATIVE_CAUSES: NaranjoAnswer.NO,
                NaranjoQuestion.REAPPEARED_WITH_PLACEBO: NaranjoAnswer.NO,
            },
            13,
            NaranjoCausality.DEFINITE,
        ),
        (
            {
                NaranjoQuestion.EVENT_AFTER_DRUG: NaranjoAnswer.NO,
                NaranjoQuestion.REAPPEARED_ON_RECHALLENGE: NaranjoAnswer.NO,
                NaranjoQuestion.ALTERNATIVE_CAUSES: NaranjoAnswer.YES,
                NaranjoQuestion.REAPPEARED_WITH_PLACEBO: NaranjoAnswer.YES,
            },
            -4,
            NaranjoCausality.DOUBTFUL,
        ),
        ({NaranjoQuestion.PREVIOUS_REPORTS: NaranjoAnswer.YES}, 1, NaranjoCausality.POSSIBLE),
        (
            {
                NaranjoQuestion.EVENT_AFTER_DRUG: NaranjoAnswer.YES,
                NaranjoQuestion.ALTERNATIVE_CAUSES: NaranjoAnswer.NO,
                NaranjoQuestion.PREVIOUS_REPORTS: NaranjoAnswer.YES,
            },
            5,
            NaranjoCausality.PROBABLE,
        ),
        ({}, 0, NaranjoCausality.DOUBTFUL),
    ],
)
def test_score_and_causality_are_derived_only_from_recorded_answers(
    answers: dict[NaranjoQuestion, NaranjoAnswer],
    expected_score: int,
    expected_causality: NaranjoCausality,
) -> None:
    result = score_naranjo(answers)

    assert result.score == expected_score
    assert result.causality is expected_causality


def test_omitted_and_unknown_answers_are_visible_as_missing_information() -> None:
    result = score_naranjo(
        {
            NaranjoQuestion.EVENT_AFTER_DRUG: NaranjoAnswer.YES,
            NaranjoQuestion.DOSE_RESPONSE: NaranjoAnswer.DO_NOT_KNOW,
        }
    )

    assert result.score == 2
    assert len(result.items) == 10
    assert NaranjoQuestion.EVENT_AFTER_DRUG not in result.missing_questions
    assert NaranjoQuestion.DOSE_RESPONSE in result.missing_questions
    assert len(result.missing_questions) == 9


def test_string_values_are_normalized_at_the_boundary() -> None:
    result = score_naranjo({"event_after_drug": "yes", "alternative_causes": "no"})

    assert result.score == 4
    assert result.items[1].answer is NaranjoAnswer.YES


@pytest.mark.parametrize(
    "answers",
    [
        {"invented_question": "yes"},
        {"event_after_drug": "maybe"},
    ],
)
def test_unknown_questions_and_answers_fail_closed(answers: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        score_naranjo(answers)
