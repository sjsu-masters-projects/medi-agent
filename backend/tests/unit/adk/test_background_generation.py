"""Registry-backed generation for fixed background workflows."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adk.background_generation import generate_for_workload
from app.adk.registry import FLASH, GPT_OSS, Workload, WorkloadRoute
from app.models.generation import (
    GenerationErrorCode,
    GenerationProviderError,
    GenerationResponse,
    GenerationTelemetry,
)


def _response(*, provider: str = "flash", model: str = "gemini-test") -> GenerationResponse:
    return GenerationResponse(
        text='{"items": []}',
        telemetry=GenerationTelemetry(provider=provider, model=model, latency_ms=12),
    )


@pytest.mark.asyncio
async def test_background_generation_uses_the_registry_token_and_reasoning_limits() -> None:
    provider = MagicMock()
    provider.generate = AsyncMock(return_value=_response())
    route = WorkloadRoute(
        workload=Workload.CARE_PLAN_CLASSIFICATION,
        primary=FLASH,
        fallback=None,
        budget_seconds=None,
        deterministic="keep the draft retryable",
        enabled_setting="care_plan_ai_enabled",
        max_output_tokens=8192,
        thinking_level="LOW",
    )

    with (
        patch("app.adk.background_generation.route_for", return_value=route),
        patch("app.adk.background_generation.provider_for", return_value=provider),
        patch("app.adk.background_generation.schedule_generation_record") as telemetry,
    ):
        response = await generate_for_workload(
            Workload.CARE_PLAN_CLASSIFICATION,
            prompt="classify fixed source facts",
            response_schema={"type": "object"},
        )

    assert response.text == '{"items": []}'
    request = provider.generate.await_args.args[0]
    assert request.task == Workload.CARE_PLAN_CLASSIFICATION.value
    assert request.max_tokens == 8192
    assert request.thinking_level == "LOW"
    assert request.response_schema == {"type": "object"}
    assert response.telemetry.fallback_path == ["flash"]
    telemetry.assert_called_once()


@pytest.mark.asyncio
async def test_background_generation_records_primary_failure_then_uses_distinct_fallback() -> None:
    primary = MagicMock()
    primary.generate = AsyncMock(
        side_effect=GenerationProviderError(GenerationErrorCode.TIMEOUT, "timed out")
    )
    fallback = MagicMock()
    fallback.generate = AsyncMock(return_value=_response(provider="gpt_oss", model="gpt-test"))
    route = WorkloadRoute(
        workload=Workload.EXPLANATION,
        primary=FLASH,
        fallback=GPT_OSS,
        budget_seconds=30,
        deterministic="localized explanation template",
        enabled_setting="explanation_ai_enabled",
    )

    with (
        patch("app.adk.background_generation.route_for", return_value=route),
        patch("app.adk.background_generation.provider_for", side_effect=[primary, fallback]),
        patch("app.adk.background_generation.schedule_generation_record") as telemetry,
    ):
        response = await generate_for_workload(Workload.EXPLANATION, prompt="explain")

    assert response.telemetry.provider == "gpt_oss"
    assert response.telemetry.fallback_path == ["flash:timeout", "gpt_oss"]
    assert telemetry.call_count == 2
    assert telemetry.call_args.kwargs["workload"] == Workload.EXPLANATION.value


@pytest.mark.asyncio
async def test_background_generation_normalizes_wall_clock_expiry() -> None:
    provider = MagicMock()
    provider.generate = AsyncMock(side_effect=TimeoutError())
    route = WorkloadRoute(
        workload=Workload.EXPLANATION,
        primary=FLASH,
        fallback=None,
        budget_seconds=30,
        deterministic="localized explanation template",
        enabled_setting="explanation_ai_enabled",
    )

    with (
        patch("app.adk.background_generation.route_for", return_value=route),
        patch("app.adk.background_generation.provider_for", return_value=provider),
        patch("app.adk.background_generation.schedule_generation_record") as telemetry,
        pytest.raises(GenerationProviderError) as raised,
    ):
        await generate_for_workload(Workload.EXPLANATION, prompt="explain")

    assert raised.value.code is GenerationErrorCode.TIMEOUT
    assert telemetry.call_args.kwargs["error_code"] == GenerationErrorCode.TIMEOUT.value
