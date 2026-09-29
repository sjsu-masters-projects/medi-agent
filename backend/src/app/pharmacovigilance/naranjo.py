"""Deterministically calculate Naranjo ADR probability assistance.

The ten questions, answer weights, and classification thresholds follow the NCBI
LiverTox presentation of the Naranjo scale:
https://www.ncbi.nlm.nih.gov/books/NBK548069/

This score is decision support, not a clinical conclusion. It records unknown evidence
as unknown and leaves the causality decision to a clinician or pharmacist.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from app.models.enums import NaranjoCausality
from app.pharmacovigilance.models import (
    NaranjoAnswer,
    NaranjoAssessment,
    NaranjoItemScore,
    NaranjoQuestion,
)

_UNKNOWN = NaranjoAnswer.DO_NOT_KNOW

NARANJO_WEIGHTS: Mapping[NaranjoQuestion, Mapping[NaranjoAnswer, int]] = MappingProxyType(
    {
        NaranjoQuestion.PREVIOUS_REPORTS: MappingProxyType(
            {NaranjoAnswer.YES: 1, NaranjoAnswer.NO: 0, _UNKNOWN: 0}
        ),
        NaranjoQuestion.EVENT_AFTER_DRUG: MappingProxyType(
            {NaranjoAnswer.YES: 2, NaranjoAnswer.NO: -1, _UNKNOWN: 0}
        ),
        NaranjoQuestion.IMPROVED_ON_DECHALLENGE: MappingProxyType(
            {NaranjoAnswer.YES: 1, NaranjoAnswer.NO: 0, _UNKNOWN: 0}
        ),
        NaranjoQuestion.REAPPEARED_ON_RECHALLENGE: MappingProxyType(
            {NaranjoAnswer.YES: 2, NaranjoAnswer.NO: -1, _UNKNOWN: 0}
        ),
        NaranjoQuestion.ALTERNATIVE_CAUSES: MappingProxyType(
            {NaranjoAnswer.YES: -1, NaranjoAnswer.NO: 2, _UNKNOWN: 0}
        ),
        NaranjoQuestion.REAPPEARED_WITH_PLACEBO: MappingProxyType(
            {NaranjoAnswer.YES: -1, NaranjoAnswer.NO: 1, _UNKNOWN: 0}
        ),
        NaranjoQuestion.TOXIC_DRUG_CONCENTRATION: MappingProxyType(
            {NaranjoAnswer.YES: 1, NaranjoAnswer.NO: 0, _UNKNOWN: 0}
        ),
        NaranjoQuestion.DOSE_RESPONSE: MappingProxyType(
            {NaranjoAnswer.YES: 1, NaranjoAnswer.NO: 0, _UNKNOWN: 0}
        ),
        NaranjoQuestion.SIMILAR_PREVIOUS_REACTION: MappingProxyType(
            {NaranjoAnswer.YES: 1, NaranjoAnswer.NO: 0, _UNKNOWN: 0}
        ),
        NaranjoQuestion.OBJECTIVE_EVIDENCE: MappingProxyType(
            {NaranjoAnswer.YES: 1, NaranjoAnswer.NO: 0, _UNKNOWN: 0}
        ),
    }
)


def _causality_for(score: int) -> NaranjoCausality:
    if score >= 9:
        return NaranjoCausality.DEFINITE
    if score >= 5:
        return NaranjoCausality.PROBABLE
    if score >= 1:
        return NaranjoCausality.POSSIBLE
    return NaranjoCausality.DOUBTFUL


def score_naranjo(
    answers: Mapping[NaranjoQuestion | str, NaranjoAnswer | str],
) -> NaranjoAssessment:
    """Score provided answers and represent omitted answers as explicit unknowns."""
    normalized = {
        NaranjoQuestion(question): NaranjoAnswer(answer) for question, answer in answers.items()
    }
    items = tuple(
        NaranjoItemScore(
            question=question,
            answer=normalized.get(question, _UNKNOWN),
            points=NARANJO_WEIGHTS[question][normalized.get(question, _UNKNOWN)],
        )
        for question in NaranjoQuestion
    )
    total = sum(item.points for item in items)
    missing = tuple(item.question for item in items if item.answer is _UNKNOWN)
    return NaranjoAssessment(
        score=total,
        causality=_causality_for(total),
        items=items,
        missing_questions=missing,
    )


__all__ = ["NARANJO_WEIGHTS", "score_naranjo"]
