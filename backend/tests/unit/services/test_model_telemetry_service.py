"""Model telemetry must be recorded, and must never cost the caller anything.

The figures the routing table was chosen on stopped being collected the moment the
decision was made — the router returned the text and dropped the envelope. These tests
pin both halves of the fix: the row is written, and a failure to write it never reaches
the caller or the patient.
"""

from __future__ import annotations

import asyncio

import pytest

from app.models.generation import GenerationTelemetry
from app.services import model_telemetry_service as telemetry_service


@pytest.fixture
def sink(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Substitute the in-memory sink the `_insert_row` seam exists for."""
    rows: list[dict[str, object]] = []

    async def _insert(payload: dict[str, object]) -> None:
        rows.append(payload)

    monkeypatch.setattr(telemetry_service, "_insert_row", _insert)
    return rows


def _telemetry(**overrides: object) -> GenerationTelemetry:
    base: dict[str, object] = {
        "provider": "flash",
        "model": "gemini-3.8-flash",
        "latency_ms": 2200,
        "usage": {"input_tokens": 300, "output_tokens": 120, "reasoning_tokens": 460},
        "retries": 0,
        "finish_reason": "STOP",
    }
    base.update(overrides)
    return GenerationTelemetry(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_a_successful_generation_is_recorded(sink) -> None:
    assert await telemetry_service.record_generation(workload="triage", telemetry=_telemetry())

    assert len(sink) == 1
    assert sink[0]["workload"] == "triage"
    assert sink[0]["model"] == "gemini-3.8-flash"
    assert sink[0]["succeeded"] is True
    assert sink[0]["latency_ms"] == 2200


@pytest.mark.asyncio
async def test_reasoning_tokens_are_recorded_separately(sink) -> None:
    """Thinking is billed inside the completion total, so it must not be folded in."""
    await telemetry_service.record_generation(workload="reply", telemetry=_telemetry())

    assert sink[0]["input_tokens"] == 300
    assert sink[0]["output_tokens"] == 120
    assert sink[0]["reasoning_tokens"] == 460


@pytest.mark.asyncio
async def test_truncation_is_recorded_as_its_own_finish_reason(sink) -> None:
    """`MAX_TOKENS` means a budget we chose cut the answer off — the alerting signal."""
    await telemetry_service.record_generation(
        workload="explanation", telemetry=_telemetry(finish_reason="MAX_TOKENS")
    )

    assert sink[0]["finish_reason"] == "MAX_TOKENS"


@pytest.mark.asyncio
async def test_the_fallback_path_is_kept(sink) -> None:
    """Which provider actually answered is the question fallbacks make hard to answer."""
    await telemetry_service.record_generation(
        workload="triage", telemetry=_telemetry(fallback_path=["gpt_oss:timeout", "flash"])
    )

    assert sink[0]["fallback_path"] == ["gpt_oss:timeout", "flash"]


@pytest.mark.asyncio
async def test_no_patient_data_is_ever_written(sink) -> None:
    """The row is about the model and the budget, not about a person."""
    await telemetry_service.record_generation(workload="reply", telemetry=_telemetry())

    forbidden = {"patient_id", "prompt", "response", "text", "content", "user_id"}
    assert forbidden.isdisjoint(sink[0].keys())


@pytest.mark.asyncio
async def test_over_long_values_are_trimmed_not_rejected(sink) -> None:
    """A too-long field must not cost the whole row — the column limits are in 035."""
    await telemetry_service.record_generation(
        workload="w" * 200, telemetry=_telemetry(model="m" * 400, finish_reason="f" * 90)
    )

    assert len(str(sink[0]["workload"])) == 60
    assert len(str(sink[0]["model"])) == 120
    assert len(str(sink[0]["finish_reason"])) == 40


@pytest.mark.asyncio
async def test_a_write_failure_never_reaches_the_caller(monkeypatch) -> None:
    """The generation succeeded. A bookkeeping failure must not turn it into an error."""

    async def _boom(_payload: dict[str, object]) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(telemetry_service, "_insert_row", _boom)

    assert (
        await telemetry_service.record_generation(workload="triage", telemetry=_telemetry())
        is False
    )


@pytest.mark.asyncio
async def test_a_stalled_database_cannot_hold_the_write_open(monkeypatch) -> None:
    """Bounded, so a hung insert cannot leak a task that never finishes."""

    async def _hang(_payload: dict[str, object]) -> None:
        await asyncio.sleep(3600)

    monkeypatch.setattr(telemetry_service, "_insert_row", _hang)
    monkeypatch.setattr(telemetry_service, "_TELEMETRY_TIMEOUT_SECONDS", 0.01)

    assert (
        await telemetry_service.record_generation(workload="triage", telemetry=_telemetry())
        is False
    )


@pytest.mark.asyncio
async def test_scheduling_does_not_block_the_caller(sink) -> None:
    """The point of scheduling: a turn's latency budget is not spent on bookkeeping."""
    task = telemetry_service.schedule_generation_record(workload="triage", telemetry=_telemetry())

    assert task is not None
    assert sink == []  # nothing written yet — the caller has already moved on

    assert await task is True
    assert len(sink) == 1


@pytest.mark.asyncio
async def test_a_scheduled_task_is_held_until_it_finishes(sink) -> None:
    """`create_task` keeps only a weak reference, so an unheld task can vanish."""
    task = telemetry_service.schedule_generation_record(workload="triage", telemetry=_telemetry())

    assert task in telemetry_service._pending
    await task
    assert task not in telemetry_service._pending


def test_scheduling_without_a_loop_is_a_no_op() -> None:
    """A synchronous caller gets nothing recorded rather than an exception."""
    assert (
        telemetry_service.schedule_generation_record(workload="triage", telemetry=_telemetry())
        is None
    )
