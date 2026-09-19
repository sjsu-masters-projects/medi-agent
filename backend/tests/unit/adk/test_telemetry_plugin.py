"""Agent model calls must be measured, and measured correctly.

Two failure modes here are silent rather than loud: recording a row per streaming chunk,
which floods the table and makes latency meaningless; and mapping the SDK's token fields
onto the wrong names, which writes NULL into every token column without failing anything.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.adk.plugins import TelemetryPlugin
from app.adk.plugins import telemetry as telemetry_module


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    def _schedule(*, workload, telemetry, succeeded=True, error_code=None):
        rows.append(
            {
                "workload": workload,
                "model": telemetry.model,
                "usage": dict(telemetry.usage),
                "finish_reason": telemetry.finish_reason,
                "latency_ms": telemetry.latency_ms,
                "succeeded": succeeded,
                "error_code": error_code,
            }
        )
        return None

    monkeypatch.setattr(telemetry_module, "schedule_generation_record", _schedule)
    return rows


def _context(agent: str = "care_coordinator") -> SimpleNamespace:
    return SimpleNamespace(agent_name=agent, invocation_id="inv-1")


def _usage_metadata(prompt: int, candidates: int, thoughts: int | None) -> SimpleNamespace:
    return SimpleNamespace(
        prompt_token_count=prompt,
        candidates_token_count=candidates,
        thoughts_token_count=thoughts,
    )


def _response(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "partial": False,
        "model_version": "gemini-3.8-flash",
        "error_code": None,
        "finish_reason": SimpleNamespace(name="STOP"),
        "usage_metadata": _usage_metadata(300, 120, 460),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


async def _call(plugin: TelemetryPlugin, response: SimpleNamespace) -> None:
    context = _context()
    await plugin.before_model_callback(callback_context=context, llm_request=SimpleNamespace())
    await plugin.after_model_callback(callback_context=context, llm_response=response)


@pytest.mark.asyncio
async def test_a_completed_call_is_recorded(recorded: list[dict[str, object]]) -> None:
    await _call(TelemetryPlugin(), _response())

    assert len(recorded) == 1
    assert recorded[0]["model"] == "gemini-3.8-flash"
    assert recorded[0]["succeeded"] is True


@pytest.mark.asyncio
async def test_the_sdk_token_fields_are_mapped_not_assumed(
    recorded: list[dict[str, object]],
) -> None:
    """The SDK says prompt/candidates/thoughts; the table stores input/output/reasoning."""
    await _call(TelemetryPlugin(), _response())

    assert recorded[0]["usage"] == {
        "input_tokens": 300,
        "output_tokens": 120,
        "reasoning_tokens": 460,
    }


@pytest.mark.asyncio
async def test_streaming_chunks_are_not_recorded(recorded: list[dict[str, object]]) -> None:
    """One row per token-chunk would flood the table and make latency meaningless."""
    plugin = TelemetryPlugin()
    context = _context()
    await plugin.before_model_callback(callback_context=context, llm_request=SimpleNamespace())

    for _ in range(5):
        await plugin.after_model_callback(
            callback_context=context, llm_response=_response(partial=True)
        )

    assert recorded == []

    await plugin.after_model_callback(callback_context=context, llm_response=_response())

    assert len(recorded) == 1


@pytest.mark.asyncio
async def test_truncation_is_preserved(recorded: list[dict[str, object]]) -> None:
    """`MAX_TOKENS` means a budget we chose cut the answer off — the alerting signal."""
    await _call(TelemetryPlugin(), _response(finish_reason=SimpleNamespace(name="MAX_TOKENS")))

    assert recorded[0]["finish_reason"] == "MAX_TOKENS"


@pytest.mark.asyncio
async def test_latency_is_measured_rather_than_defaulted(
    recorded: list[dict[str, object]],
) -> None:
    await _call(TelemetryPlugin(), _response())

    assert isinstance(recorded[0]["latency_ms"], int)
    assert recorded[0]["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_a_response_without_usage_metadata_still_records(
    recorded: list[dict[str, object]],
) -> None:
    """Missing token counts must not cost the whole row."""
    await _call(TelemetryPlugin(), _response(usage_metadata=None))

    assert len(recorded) == 1
    assert recorded[0]["usage"] == {}


@pytest.mark.asyncio
async def test_a_failed_call_is_recorded_as_a_failure(
    recorded: list[dict[str, object]],
) -> None:
    await _call(TelemetryPlugin(), _response(error_code="RESOURCE_EXHAUSTED"))

    assert recorded[0]["succeeded"] is False
    assert recorded[0]["error_code"] == "RESOURCE_EXHAUSTED"


@pytest.mark.asyncio
async def test_a_model_error_is_recorded_without_its_message(
    recorded: list[dict[str, object]],
) -> None:
    """An exception string can carry prompt fragments; the type cannot."""
    plugin = TelemetryPlugin()
    context = _context()
    await plugin.before_model_callback(callback_context=context, llm_request=SimpleNamespace())

    await plugin.on_model_error_callback(
        callback_context=context,
        llm_request=SimpleNamespace(model="gemini-3.8-flash"),
        error=ValueError("patient Maria Gomez asked about warfarin"),
    )

    assert recorded[0]["succeeded"] is False
    assert recorded[0]["error_code"] == "ValueError"
    assert "Maria Gomez" not in str(recorded[0])


@pytest.mark.asyncio
async def test_the_agent_is_recorded_as_the_workload(
    recorded: list[dict[str, object]],
) -> None:
    plugin = TelemetryPlugin()
    context = _context("medication_safety")
    await plugin.before_model_callback(callback_context=context, llm_request=SimpleNamespace())
    await plugin.after_model_callback(callback_context=context, llm_response=_response())

    assert recorded[0]["workload"] == "medication_safety"


@pytest.mark.asyncio
async def test_timing_state_does_not_accumulate(recorded: list[dict[str, object]]) -> None:
    """A start time left behind for every call would leak memory across a long run."""
    plugin = TelemetryPlugin()

    for _ in range(3):
        await _call(plugin, _response())

    assert plugin._started == {}


def test_the_plugin_is_named_for_the_runner_to_register() -> None:
    assert TelemetryPlugin().name == "telemetry"
