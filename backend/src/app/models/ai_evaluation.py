"""Synthetic evaluation scenarios and scored results for comparing AI providers.

`EVA-001` compares providers per workload, not globally. These models describe one
gold-labeled synthetic scenario, one provider's scored attempt at it, and the per
workload summary that release thresholds are checked against. Scenario content is
synthetic by construction; nothing here may carry real patient data.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ScenarioLocale = Literal["en-US", "es-MX"]


class EvalWorkload(StrEnum):
    TRIAGE_CLASSIFICATION = "triage_classification"
    DOCUMENT_EXTRACTION = "document_extraction"
    MEDICATION_DISCREPANCY = "medication_discrepancy"
    ADR_EXTRACTION = "adr_extraction"
    PATIENT_EXPLANATION = "patient_explanation"


class EvalRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AdjudicationStatus(StrEnum):
    PENDING = "pending"
    CLINICIAN_ADJUDICATED = "clinician_adjudicated"


class ScenarioAdjudication(BaseModel):
    """Whether a clinician or pharmacist has confirmed the gold label."""

    status: AdjudicationStatus = AdjudicationStatus.PENDING
    reviewer_role: Literal["clinician", "pharmacist"] | None = None
    reviewed_on: date | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _adjudicated_needs_reviewer(self) -> ScenarioAdjudication:
        if self.status is AdjudicationStatus.CLINICIAN_ADJUDICATED and not self.reviewer_role:
            raise ValueError("an adjudicated scenario must name the reviewer role")
        return self


class EvalScenario(BaseModel):
    """One gold-labeled synthetic case for one workload."""

    scenario_id: str = Field(pattern=r"^[a-z]{3}-[0-9]{3}$")
    workload: EvalWorkload
    locale: ScenarioLocale
    risk: EvalRisk = EvalRisk.MEDIUM
    # Links the English and Spanish versions of the same case so parity can be checked.
    pair_id: str | None = Field(default=None, pattern=r"^[a-z]{3}-p[0-9]{2}$")
    tags: list[str] = Field(default_factory=list)
    inputs: dict[str, Any]
    expected: dict[str, Any]
    adjudication: ScenarioAdjudication = Field(default_factory=ScenarioAdjudication)
    rationale: str | None = None


class EvalScenarioSet(BaseModel):
    """A versioned file of scenarios for one workload."""

    version: str = Field(min_length=1, max_length=64)
    workload: EvalWorkload
    scenarios: list[EvalScenario] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent_and_unique(self) -> EvalScenarioSet:
        seen: set[str] = set()
        for scenario in self.scenarios:
            if scenario.workload is not self.workload:
                raise ValueError(
                    f"scenario {scenario.scenario_id} belongs to {scenario.workload}, "
                    f"not {self.workload}"
                )
            if scenario.scenario_id in seen:
                raise ValueError(f"duplicate scenario id {scenario.scenario_id}")
            seen.add(scenario.scenario_id)
        return self


class ScoreDisposition(StrEnum):
    """How a single attempt ended, before any question of whether it was right.

    Accuracy counts `ANSWERED`, `UNPARSEABLE` and `REFUSED`: the model was given its
    chance and the contract it failed to meet is its own. `INFRA_ERROR` and `TRUNCATED`
    leave the accuracy denominator, because a rate limit on a shared quota and a token
    budget we chose say nothing about clinical ability. Both are reported as their own
    rates so a provider cannot look good by failing to answer.
    """

    ANSWERED = "answered"
    INFRA_ERROR = "infra_error"
    TRUNCATED = "truncated"
    UNPARSEABLE = "unparseable"
    REFUSED = "refused"


SCORED_DISPOSITIONS = frozenset(
    {ScoreDisposition.ANSWERED, ScoreDisposition.UNPARSEABLE, ScoreDisposition.REFUSED}
)
"""The dispositions that belong in an accuracy denominator."""


class ScenarioScore(BaseModel):
    """One provider's scored attempt at one scenario."""

    scenario_id: str
    workload: EvalWorkload
    locale: ScenarioLocale
    risk: EvalRisk
    provider: str
    model: str
    ok: bool
    error_code: str | None = None
    # Which denominator this attempt belongs in. See ScoreDisposition.
    disposition: ScoreDisposition = ScoreDisposition.ANSWERED
    schema_valid: bool = False
    # 0..1 headline score whose meaning is workload-specific (see services.ai_evaluation).
    score: float = Field(default=0.0, ge=0, le=1)
    # None when the workload has no safety dimension for this scenario.
    safety_pass: bool | None = None
    abstain_expected: bool = False
    abstained: bool | None = None
    latency_ms: int = Field(default=0, ge=0)
    usage: dict[str, int] = Field(default_factory=dict)
    # Capacity retries the call needed before it answered. A model that only works after
    # backoff is a demo-day risk even when its score is perfect.
    retries: int = Field(default=0, ge=0)
    output_text: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class WorkloadSummary(BaseModel):
    """Aggregate for one provider on one workload, with threshold checks."""

    provider: str
    model: str
    workload: EvalWorkload
    scenarios: int
    # How the attempts ended. These are counts, not rates, so a reader can see the
    # denominator that every rate below was computed against.
    answered: int = 0
    infra_errors: int = 0
    truncated: int = 0
    unparseable: int = 0
    refused: int = 0
    # Availability and capability, always published side by side. A provider that fails
    # half its calls must not look good by vanishing from the accuracy denominator.
    answered_rate: float | None = Field(default=None, ge=0, le=1)
    accuracy_on_answered: float | None = Field(default=None, ge=0, le=1)
    # 95% interval on the line above. At eight scenarios a perfect score still admits a
    # true accuracy near two thirds, so the point estimate alone means very little.
    accuracy_ci_low: float | None = Field(default=None, ge=0, le=1)
    accuracy_ci_high: float | None = Field(default=None, ge=0, le=1)
    ok_rate: float = Field(ge=0, le=1)
    schema_valid_rate: float = Field(ge=0, le=1)
    mean_score: float = Field(ge=0, le=1)
    safety_pass_rate: float | None = None
    abstention_accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    evidence_valid_rate: float | None = None
    p50_latency_ms: int = 0
    # Kept for continuity with earlier reports, but not published at these sample sizes:
    # with eight to ten calls the 95th percentile is simply the slowest one.
    p95_latency_ms: int = 0
    min_latency_ms: int = 0
    max_latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float | None = None
    # Threshold name -> passed. Only thresholds that apply to the workload appear.
    thresholds: dict[str, bool] = Field(default_factory=dict)


class EvalRunReport(BaseModel):
    """Everything needed to reproduce and review one evaluation run."""

    run_id: str
    started_at: datetime
    finished_at: datetime
    scenario_set_versions: dict[str, str]
    environment: dict[str, Any] = Field(default_factory=dict)
    summaries: list[WorkloadSummary] = Field(default_factory=list)
    scores: list[ScenarioScore] = Field(default_factory=list)
