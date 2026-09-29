"""The care-plan preflight is safe to run before a deployment."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from scripts import preflight_care_plan_classification as preflight
from scripts.preflight_care_plan_classification import parse_args, run, synthetic_facts


def test_preflight_accepts_dry_run() -> None:
    assert parse_args(["--dry-run"]).dry_run is True


def test_preflight_generated_facts_are_distinct_and_synthetic() -> None:
    facts = synthetic_facts(12)

    assert len({fact["id"] for fact in facts}) == 12
    assert {fact["fact_type"] for fact in facts} == {"medication", "obligation"}
    assert all("Sampleformin" in fact["value"].get("name", "Sampleformin") for fact in facts)


@pytest.mark.asyncio
async def test_preflight_dry_run_never_calls_a_provider(capsys: pytest.CaptureFixture[str]) -> None:
    assert await run(dry_run=True) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "dry_run_passed"
    assert output["fact_count"] == 12


@pytest.mark.asyncio
async def test_live_preflight_suppresses_database_telemetry(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    classify = AsyncMock(
        return_value={str(fact["id"]): fact["fact_type"] for fact in synthetic_facts(2)}
    )
    monkeypatch.setattr(preflight, "classify_facts", classify)

    assert await run(dry_run=False, fact_count=2) == 0

    assert classify.await_args.kwargs["record_telemetry"] is False
    assert json.loads(capsys.readouterr().out)["status"] == "passed"
