"""Bounded paired demo selection and final-response replay, without provider access."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.models.ai_evaluation import EvalScenario, EvalWorkload, ScenarioScore, WorkloadSummary
from app.models.generation import GenerationErrorCode, ProviderTrial
from app.services.ai_evaluation import load_scenario_sets

# Reuse structured extraction/intake as well as triage and explanation controls.
CONTROL_PAIRS = frozenset(
    {"tri-p01", "tri-p02", "tri-p05", "exp-p01", "doc-p01", "adr-p01", "adr-p02"}
)


def load_demo_scenarios(directory: Path) -> list[EvalScenario]:
    """Load both locales of each selected case; fail on drift before any model call."""
    controls = [
        scenario
        for group in load_scenario_sets(directory)
        for scenario in group.scenarios
        if scenario.pair_id in CONTROL_PAIRS
    ]
    added = [
        scenario for group in load_scenario_sets(directory / "demo") for scenario in group.scenarios
    ]
    scenarios = controls + added
    pairs: dict[str, list[str]] = defaultdict(list)
    ids: set[str] = set()
    for scenario in scenarios:
        if scenario.scenario_id in ids or not scenario.pair_id:
            raise ValueError("Demo scenarios require unique IDs and paired locales")
        ids.add(scenario.scenario_id)
        pairs[scenario.pair_id].append(scenario.locale)
    if not CONTROL_PAIRS.issubset(pairs) or not added:
        raise ValueError("Demo suite is missing its controls or follow-up fixtures")
    if any(sorted(locales) != ["en-US", "es-MX"] for locales in pairs.values()):
        raise ValueError("Every demo pair must contain exactly en-US and es-MX")
    return scenarios


class RecordedFinalResponse(BaseModel):
    """Strict replay input: only final answers and safe outcome metadata, no reasoning."""

    model_config = ConfigDict(extra="forbid")
    scenario_id: str
    provider: str
    model: str
    ok: bool
    text: str | None = None
    error_code: GenerationErrorCode | None = None
    latency_ms: int = Field(default=0, ge=0)


def load_final_responses(
    path: Path, scenarios: list[EvalScenario]
) -> dict[str, list[ProviderTrial]]:
    """Require complete selected-case coverage and reject duplicate trials or extra fields."""
    records = [
        RecordedFinalResponse.model_validate(row)
        for row in json.loads(path.read_text(encoding="utf-8"))
    ]
    grouped: dict[str, list[ProviderTrial]] = defaultdict(list)
    seen: set[tuple[str, str, str]] = set()
    for record in records:
        identity = (record.scenario_id, record.provider, record.model)
        if identity in seen:
            raise ValueError("Duplicate recorded response")
        seen.add(identity)
        if record.ok != bool(record.text and record.text.strip()) or (
            record.ok == (record.error_code is not None)
        ):
            raise ValueError("Recorded outcome must be a final answer or an explicit error")
        grouped[record.scenario_id].append(
            ProviderTrial.model_validate(record.model_dump(exclude={"scenario_id"}))
        )
    expected = {scenario.scenario_id for scenario in scenarios}
    if set(grouped) != expected:
        raise ValueError("Recorded responses must match the selected scenario IDs exactly")
    participants = [
        {(trial.provider, trial.model) for trial in trials} for trials in grouped.values()
    ]
    if any(group != participants[0] for group in participants):
        raise ValueError("Every selected case needs the same recorded providers/models")
    return dict(grouped)


def add_demo_report_criteria(
    summaries: list[WorkloadSummary], scores: list[ScenarioScore], scenarios: list[EvalScenario]
) -> None:
    """Add strict demo checks to the existing report thresholds, per provider/workload.

    These checks supplement the framework's research thresholds. Failed calls cannot
    become successful medical answers through an accuracy denominator that excludes them.
    """
    required = {
        EvalWorkload.TRIAGE_CLASSIFICATION,
        EvalWorkload.PATIENT_EXPLANATION,
        EvalWorkload.DOCUMENT_EXTRACTION,
        EvalWorkload.ADR_EXTRACTION,
    }
    for summary in summaries:
        selected = [s for s in scenarios if s.workload == summary.workload]
        attempts = [
            s
            for s in scores
            if (s.provider, s.model, s.workload)
            == (summary.provider, summary.model, summary.workload)
        ]
        summary.thresholds.update(_demo_criteria(attempts, selected))
        summary.thresholds["demo_all_four_tasks_selected"] = {
            scenario.workload for scenario in scenarios
        } == required


def _demo_criteria(attempts: list[ScenarioScore], selected: list[EvalScenario]) -> dict[str, bool]:
    pairs: dict[str | None, list[str]] = defaultdict(list)
    for scenario in selected:
        pairs[scenario.pair_id].append(scenario.locale)
    checks = {
        "demo_paired_locales": bool(pairs)
        and all(sorted(locales) == ["en-US", "es-MX"] for locales in pairs.values()),
        "demo_all_selected_answered": bool(selected)
        and len(attempts) == len(selected)
        and {s.scenario_id for s in attempts} == {s.scenario_id for s in selected}
        and all(s.ok and s.schema_valid and bool(s.output_text) for s in attempts),
        "demo_exact_expected_checks": bool(attempts) and all(s.score == 1 for s in attempts),
        "demo_no_safety_failure": all(s.safety_pass is not False for s in attempts),
        "demo_failed_calls_without_clinical_verdict": all(
            s.output_text is None and s.safety_pass is None for s in attempts if not s.ok
        ),
    }
    if selected and selected[0].workload == EvalWorkload.DOCUMENT_EXTRACTION:
        checks["demo_document_grounding"] = bool(attempts) and all(
            s.details.get("evidence_valid_rate") == 1
            and s.details.get("hallucinated_medications") == 0
            and s.details.get("unsupported_fields_left_empty")
            == s.details.get("unsupported_fields_total")
            for s in attempts
        )
    return checks
