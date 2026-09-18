"""The evaluation runner and the scenario files it reads.

Two things are pinned here. The CLI must refuse malformed provider specs rather than
call the wrong endpoint, and the committed scenario set must stay valid, synthetic, and
mirrored in both locales for every high-risk case.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pytest
from scripts.run_ai_eval import (
    DEFAULT_SCENARIOS,
    ProviderSpec,
    _select,
    parse_args,
    parse_provider_spec,
    render_summary_table,
)

from app.models.ai_evaluation import EvalRisk, EvalScenario, EvalWorkload, WorkloadSummary
from app.services.ai_evaluation import build_request, load_scenario_sets

FIXTURE_ROOT = Path(__file__).resolve().parent.parent.parent / "fixtures" / "eval"


def test_default_scenario_directory_is_the_committed_fixture_set() -> None:
    assert DEFAULT_SCENARIOS == FIXTURE_ROOT


def test_provider_spec_parses_with_and_without_a_key() -> None:
    with_key = parse_provider_spec(
        "gemma4=https://models.test/v1|gemma-4-26b-a4b-it|GOOGLE_API_KEY"
    )
    without_key = parse_provider_spec("local=http://localhost:11434/v1|medgemma-1.5-4b|")

    assert with_key == ProviderSpec(
        "gemma4", "https://models.test/v1", "gemma-4-26b-a4b-it", "GOOGLE_API_KEY"
    )
    assert without_key.api_key_env is None


def test_provider_spec_accepts_an_optional_reasoning_effort() -> None:
    tuned = parse_provider_spec("flash38=https://models.test/v1|gemini-3.8-flash|TOKEN|LOW")
    plain = parse_provider_spec("flash35=https://models.test/v1|gemini-3.5-flash-lite|TOKEN")

    assert tuned.reasoning_effort == "low"
    assert plain.reasoning_effort is None


def test_an_unknown_reasoning_effort_is_rejected() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_provider_spec("x=https://models.test/v1|m|TOKEN|extreme")


@pytest.mark.parametrize("raw", ["nomodel=https://x", "=https://x|m", "name=|m", "name=https://x|"])
def test_malformed_provider_specs_are_rejected(raw: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_provider_spec(raw)


def test_dry_run_and_filters_parse() -> None:
    args = parse_args(
        ["--dry-run", "--workload", "triage_classification", "--locale", "es-MX", "--limit", "3"]
    )

    assert args.dry_run is True
    assert args.workload == ["triage_classification"]
    assert args.locale == "es-MX"
    assert args.limit == 3
    assert args.prompt_variant == "candidate"


# ── The committed scenario set ───────────────────────────────────────────────


@pytest.fixture(scope="module")
def scenario_sets():
    return load_scenario_sets(FIXTURE_ROOT)


def test_every_workload_has_a_scenario_file(scenario_sets) -> None:
    assert {group.workload for group in scenario_sets} == set(EvalWorkload)


def test_scenario_ids_are_unique_across_files(scenario_sets) -> None:
    ids = [s.scenario_id for group in scenario_sets for s in group.scenarios]
    assert len(ids) == len(set(ids))


def test_every_scenario_builds_a_request_without_a_model(scenario_sets) -> None:
    for group in scenario_sets:
        for scenario in group.scenarios:
            for variant in ("production", "candidate"):
                request = build_request(scenario, variant=variant)
                assert request.prompt.strip(), scenario.scenario_id
                assert request.task == scenario.workload.value


def test_golden_fixtures_are_inlined_into_document_scenarios(scenario_sets) -> None:
    documents = next(
        group for group in scenario_sets if group.workload is EvalWorkload.DOCUMENT_EXTRACTION
    )
    prescription = next(s for s in documents.scenarios if s.scenario_id == "doc-001")

    assert "PRESCRIPTION" in prescription.inputs["document_text"]
    assert len(prescription.expected["medications"]) == 4
    assert "document_file" not in prescription.inputs
    assert "expected_file" not in prescription.expected


def test_high_risk_scenarios_are_mirrored_in_both_locales(scenario_sets) -> None:
    """Bilingual parity is a release threshold, so every high-risk pair needs both halves."""
    for group in scenario_sets:
        by_pair: dict[str, set[str]] = {}
        for scenario in group.scenarios:
            if scenario.pair_id:
                by_pair.setdefault(scenario.pair_id, set()).add(scenario.locale)
        for pair_id, locales in by_pair.items():
            assert locales == {"en-US", "es-MX"}, f"{group.workload}: {pair_id} has {locales}"
        unpaired_high = [
            s.scenario_id
            for s in group.scenarios
            if s.risk is EvalRisk.HIGH and not s.pair_id and s.locale == "en-US"
        ]
        # Golden-set documents and single-locale edge cases are allowed but must be few.
        assert len(unpaired_high) <= 5, (
            f"{group.workload}: too many unpaired high-risk cases {unpaired_high}"
        )


def test_the_set_covers_both_locales_and_the_required_risk_classes(scenario_sets) -> None:
    scenarios = [s for group in scenario_sets for s in group.scenarios]
    locales = Counter(s.locale for s in scenarios)
    tags = {tag for s in scenarios for tag in s.tags}

    assert locales["en-US"] >= 30 and locales["es-MX"] >= 25
    for required in (
        "emergency",
        "self_harm",
        "allergy_conflict",
        "dose_mismatch",
        "incomplete",
        "contradiction",
        "red_flag",
        "prompt_injection",
    ):
        assert required in tags, f"missing coverage tag {required}"
    assert sum(s.risk is EvalRisk.HIGH for s in scenarios) >= 30


def test_scenarios_never_carry_real_identifiers(scenario_sets) -> None:
    """Names, MRNs, and dates of birth do not belong in a scenario body."""
    forbidden = ("mrn", "dob:", "date of birth", "ssn")
    for group in scenario_sets:
        for scenario in group.scenarios:
            body = str(scenario.inputs).lower()
            if scenario.scenario_id in {"doc-001", "doc-002", "doc-003", "doc-004"}:
                continue  # golden fixtures are synthetic by construction and reviewed separately
            assert not any(marker in body for marker in forbidden), scenario.scenario_id


def test_select_applies_workload_locale_risk_and_limit(scenario_sets) -> None:
    scenarios = [s for group in scenario_sets for s in group.scenarios]
    args = parse_args(
        [
            "--workload",
            "triage_classification",
            "--locale",
            "es-MX",
            "--risk",
            "high",
            "--limit",
            "2",
        ]
    )

    chosen = _select(scenarios, args)

    assert len(chosen) == 2
    assert all(
        isinstance(s, EvalScenario) and s.locale == "es-MX" and s.risk is EvalRisk.HIGH
        for s in chosen
    )


def test_summary_table_renders_thresholds() -> None:
    summary = WorkloadSummary(
        provider="flash",
        model="gemini-3.1-flash-lite",
        workload=EvalWorkload.TRIAGE_CLASSIFICATION,
        scenarios=2,
        ok_rate=1.0,
        schema_valid_rate=1.0,
        mean_score=0.75,
        safety_pass_rate=1.0,
        thresholds={"urgent_false_negative_zero": True, "schema_valid_98": True},
    )

    table = render_summary_table([summary])

    assert "gemini-3.1-flash-lite" in table
    assert "✅ urgent_false_negative_zero" in table
