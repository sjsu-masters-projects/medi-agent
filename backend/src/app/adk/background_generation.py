"""Run a non-interactive workload through the central ADK routing registry.

Background services are deliberately not made into agents. They have a fixed input, one
bounded model operation, and an owning service that decides the safe durable outcome. This
adapter gives those services the same route selection, timeout, fallback, and telemetry
contract as the Care Coordinator without introducing a second orchestration runtime.
"""

from __future__ import annotations

import asyncio
import time

from app.adk.models.factory import provider_for
from app.adk.registry import Workload, route_for
from app.models.generation import (
    GenerationErrorCode,
    GenerationProviderError,
    GenerationRequest,
    GenerationResponse,
    GenerationTelemetry,
)
from app.services.model_telemetry_service import schedule_generation_record


def _failure_telemetry(*, provider: str, model: str, started: float) -> GenerationTelemetry:
    """Create safe telemetry for a call that failed before an adapter returned a response."""
    return GenerationTelemetry(
        provider=provider,
        model=model,
        latency_ms=round((time.perf_counter() - started) * 1000),
    )


async def generate_for_workload(
    workload: Workload,
    *,
    prompt: str,
    system_instruction: str | None = None,
    temperature: float = 0.2,
) -> GenerationResponse:
    """Generate through one named route and record every attempt without patient data.

    The service that owns a workload retains the deterministic path. For example,
    extraction marks a document for evidence review and care-plan drafting preserves the
    existing approved plan. Raising a normalized error here lets those services make that
    domain-specific decision without picking a model, timeout, fallback, or token budget.
    """
    route = route_for(workload)
    if not route.is_enabled():
        telemetry = GenerationTelemetry(
            provider=route.primary.key,
            model=route.primary.model_id,
            latency_ms=0,
        )
        schedule_generation_record(
            workload=workload.value,
            telemetry=telemetry,
            succeeded=False,
            error_code=GenerationErrorCode.CONFIGURATION.value,
        )
        raise GenerationProviderError(
            GenerationErrorCode.CONFIGURATION,
            f"AI is disabled for {workload.value}",
        )

    request = GenerationRequest(
        prompt=prompt,
        system_instruction=system_instruction,
        temperature=temperature,
        max_tokens=route.max_output_tokens,
        thinking_level=route.thinking_level,
        task=workload.value,
    )
    attempts = [route.primary, *([route.fallback] if route.fallback else [])]
    failures: list[str] = []

    for spec in attempts:
        provider = provider_for(spec, timeout_seconds=route.budget_seconds)
        started = time.perf_counter()
        try:
            # The transport timeout is not enough on its own: retry/backoff and an adapter
            # bug could otherwise outlive the route's person-facing budget.
            if route.budget_seconds is None:
                response = await provider.generate(request)
            else:
                response = await asyncio.wait_for(
                    provider.generate(request), timeout=route.budget_seconds
                )
        except TimeoutError:
            error = GenerationProviderError(
                GenerationErrorCode.TIMEOUT, f"{workload.value} exceeded its routing budget"
            )
            telemetry = _failure_telemetry(provider=spec.key, model=spec.model_id, started=started)
            schedule_generation_record(
                workload=workload.value,
                telemetry=telemetry,
                succeeded=False,
                error_code=error.code.value,
            )
            failures.append(f"{spec.key}:{error.code.value}")
            last_error: GenerationProviderError = error
        except GenerationProviderError as error:
            telemetry = _failure_telemetry(provider=spec.key, model=spec.model_id, started=started)
            schedule_generation_record(
                workload=workload.value,
                telemetry=telemetry,
                succeeded=False,
                error_code=error.code.value,
            )
            failures.append(f"{spec.key}:{error.code.value}")
            last_error = error
        else:
            response.telemetry.fallback_path = [*failures, spec.key]
            schedule_generation_record(workload=workload.value, telemetry=response.telemetry)
            return response

    raise last_error
