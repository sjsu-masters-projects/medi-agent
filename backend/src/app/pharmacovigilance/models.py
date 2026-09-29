"""Typed inputs and outputs for deterministic ADR causality assistance."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import NaranjoCausality


class NaranjoAnswer(StrEnum):
    """Allowed answers on the Naranjo adverse-reaction probability scale."""

    YES = "yes"
    NO = "no"
    DO_NOT_KNOW = "do_not_know"


class NaranjoQuestion(StrEnum):
    """Stable identifiers for the scale's ten questions."""

    PREVIOUS_REPORTS = "previous_reports"
    EVENT_AFTER_DRUG = "event_after_drug"
    IMPROVED_ON_DECHALLENGE = "improved_on_dechallenge"
    REAPPEARED_ON_RECHALLENGE = "reappeared_on_rechallenge"
    ALTERNATIVE_CAUSES = "alternative_causes"
    REAPPEARED_WITH_PLACEBO = "reappeared_with_placebo"
    TOXIC_DRUG_CONCENTRATION = "toxic_drug_concentration"
    DOSE_RESPONSE = "dose_response"
    SIMILAR_PREVIOUS_REACTION = "similar_previous_reaction"
    OBJECTIVE_EVIDENCE = "objective_evidence"


class NaranjoItemScore(BaseModel):
    """One recorded answer and its deterministic contribution to the score."""

    model_config = ConfigDict(frozen=True)

    question: NaranjoQuestion
    answer: NaranjoAnswer
    points: int = Field(..., ge=-1, le=2)


class NaranjoAssessment(BaseModel):
    """A reproducible score, classification, and explicit evidence gaps."""

    model_config = ConfigDict(frozen=True)

    score: int = Field(..., ge=-4, le=13)
    causality: NaranjoCausality
    items: tuple[NaranjoItemScore, ...]
    missing_questions: tuple[NaranjoQuestion, ...]
