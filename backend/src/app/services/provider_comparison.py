"""Run one request across several providers so they can be compared.

`EVA-001` has to compare providers on accuracy, safety, evidence, latency, reliability,
and zero-cost feasibility. Production routing cannot answer that question: `TASK_MODEL_MAP`
binds each task to exactly one model, which is correct for serving a request and useless
for judging alternatives. This module asks every named provider the same question and
returns what each one said.

It never raises. A provider that is down, misconfigured, or timing out has told you
something about its reliability, and losing the other providers' answers to that
exception would throw away the comparison that was the point of the call.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Sequence

from app.models.generation import (
    GenerationErrorCode,
    GenerationProviderError,
    GenerationRequest,
    ProviderComparison,
    ProviderTrial,
)
from app.services.generation_providers import TextProvider

logger = logging.getLogger(__name__)


def _digest(prompt: str) -> str:
    """Short, stable fingerprint proving two trials answered the same input."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:32]


async def _run_trial(provider: TextProvider, request: GenerationRequest) -> ProviderTrial:
    """Ask one provider, converting any outcome into a recorded trial."""
    started = asyncio.get_running_loop().time()

    def _elapsed_ms() -> int:
        return round((asyncio.get_running_loop().time() - started) * 1000)

    try:
        response = await provider.generate(request)
    except GenerationProviderError as exc:
        # The provider contract's own failure mode: already classified, so keep the code.
        logger.info("Provider %s declined the comparison request: %s", provider.name, exc.code)
        return ProviderTrial(
            provider=provider.name,
            model=provider.model,
            ok=False,
            error_code=exc.code,
            latency_ms=_elapsed_ms(),
        )
    except Exception:
        # Anything else is a provider that failed outside its own contract — a
        # comparison result in its own right. No prompt or response text is logged:
        # comparisons run over clinical scenario content.
        logger.warning("Provider %s failed outside the generation contract", provider.name)
        return ProviderTrial(
            provider=provider.name,
            model=provider.model,
            ok=False,
            error_code=GenerationErrorCode.UNAVAILABLE,
            latency_ms=_elapsed_ms(),
        )

    return ProviderTrial(
        provider=provider.name,
        model=provider.model,
        ok=True,
        text=response.text,
        latency_ms=response.telemetry.latency_ms,
        telemetry=response.telemetry,
    )


async def compare_text_providers(
    request: GenerationRequest,
    providers: Sequence[TextProvider],
) -> ProviderComparison:
    """Ask every provider the same question and return all the answers.

    Providers run concurrently. Sequentially would make each one's latency depend on
    how slow the previous one was, which is exactly the measurement being taken; these
    are independent backends, so overlapping them does not distort it.
    """
    if not providers:
        raise ValueError("At least one provider is required for a comparison")

    trials = await asyncio.gather(*(_run_trial(provider, request) for provider in providers))
    return ProviderComparison(
        task=request.task,
        prompt_digest=_digest(request.prompt),
        trials=list(trials),
    )
