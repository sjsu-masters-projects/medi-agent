"""What a symptom report contains once a model has read the patient's message.

This lived inside the symptom agent's graph module. It is the contract the evaluation
harness scores against and the shape written to `symptom_reports`, so it must not be
deleted along with the runtime that happened to host it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SymptomExtractionResult(BaseModel):
    """Structured symptom fields, as extracted from the patient's own words.

    `severity` is the patient's description rated on a stated scale, not a clinical
    judgement of how serious the symptom is. The distinction matters because this value
    reaches a clinician's queue: it says "this is how bad they said it was".
    """

    symptom: str = Field(..., min_length=1)
    severity: int = Field(..., ge=1, le=10)
    onset: str | None = None
    duration: str | None = None
    body_area: str | None = None
    related_medication_name: str | None = None
    needs_follow_up: bool = False
    follow_up_question: str | None = None
    flagged_for_adr: bool = False
    ai_assessment: str = Field(default="Patient reported symptom requires monitoring.")
