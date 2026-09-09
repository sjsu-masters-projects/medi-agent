"""Comparing providers side by side.

The property that matters is that a comparison survives its participants. A provider
that fails must not take the other providers' answers down with it, because "this one
was unavailable" is one of the things the comparison is measuring.
"""

import asyncio

import pytest

from app.models.generation import (
    GenerationCapability,
    GenerationErrorCode,
    GenerationProviderError,
    GenerationRequest,
    GenerationResponse,
    GenerationTelemetry,
)
from app.services.provider_comparison import compare_text_providers


class _StubProvider:
    capabilities = frozenset({GenerationCapability.TEXT})

    def __init__(self, name: str, *, text: str = "ok", raises: Exception | None = None):
        self.name = name
        self.model = f"{name}-1"
        self._text = text
        self._raises = raises
        self.calls = 0

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return GenerationResponse(
            text=self._text,
            telemetry=GenerationTelemetry(provider=self.name, model=self.model, latency_ms=7),
        )


def _request(prompt: str = "Summarize the medication list.") -> GenerationRequest:
    return GenerationRequest(prompt=prompt, task="evaluation")


@pytest.mark.asyncio
async def test_every_provider_answers_the_same_request():
    providers = [_StubProvider("medgemma"), _StubProvider("flash"), _StubProvider("pro")]

    comparison = await compare_text_providers(_request(), providers)

    assert [t.provider for t in comparison.trials] == ["medgemma", "flash", "pro"]
    assert all(t.ok for t in comparison.trials)
    assert all(p.calls == 1 for p in providers)


@pytest.mark.asyncio
async def test_a_failing_provider_does_not_lose_the_others():
    providers = [
        _StubProvider("medgemma", raises=GenerationProviderError(
            GenerationErrorCode.UNAVAILABLE, "endpoint cold"
        )),
        _StubProvider("flash", text="answer"),
    ]

    comparison = await compare_text_providers(_request(), providers)

    failed, succeeded = comparison.trials
    assert failed.ok is False
    assert failed.error_code == GenerationErrorCode.UNAVAILABLE
    assert succeeded.ok is True
    assert succeeded.text == "answer"
    assert [t.provider for t in comparison.succeeded] == ["flash"]


@pytest.mark.asyncio
async def test_failure_outside_the_provider_contract_is_still_recorded():
    """An unclassified crash is a reliability data point, not a lost comparison."""
    providers = [_StubProvider("medgemma", raises=RuntimeError("boom")), _StubProvider("flash")]

    comparison = await compare_text_providers(_request(), providers)

    assert comparison.trials[0].ok is False
    assert comparison.trials[0].error_code == GenerationErrorCode.UNAVAILABLE
    assert comparison.trials[1].ok is True


@pytest.mark.asyncio
async def test_every_provider_failing_is_a_result_not_an_exception():
    providers = [
        _StubProvider("medgemma", raises=RuntimeError("boom")),
        _StubProvider("flash", raises=RuntimeError("boom")),
    ]

    comparison = await compare_text_providers(_request(), providers)

    assert len(comparison.trials) == 2
    assert comparison.succeeded == []


@pytest.mark.asyncio
async def test_the_prompt_is_not_carried_in_the_result():
    """Comparisons run over clinical scenario text; only a digest travels onward."""
    prompt = "Patient reports chest tightness after starting lisinopril."

    comparison = await compare_text_providers(_request(prompt), [_StubProvider("flash")])

    assert prompt not in comparison.model_dump_json()
    assert len(comparison.prompt_digest) == 32


@pytest.mark.asyncio
async def test_the_same_prompt_digests_identically_and_a_different_one_does_not():
    same = await compare_text_providers(_request("a"), [_StubProvider("flash")])
    again = await compare_text_providers(_request("a"), [_StubProvider("pro")])
    other = await compare_text_providers(_request("b"), [_StubProvider("flash")])

    assert same.prompt_digest == again.prompt_digest
    assert same.prompt_digest != other.prompt_digest


@pytest.mark.asyncio
async def test_providers_run_concurrently_rather_than_in_series():
    """Serial execution would make each provider's latency depend on the previous one."""

    class _SlowProvider(_StubProvider):
        async def generate(self, request: GenerationRequest) -> GenerationResponse:
            await asyncio.sleep(0.05)
            return await super().generate(request)

    providers = [_SlowProvider(f"p{i}") for i in range(4)]

    started = asyncio.get_running_loop().time()
    await compare_text_providers(_request(), providers)
    elapsed = asyncio.get_running_loop().time() - started

    # Four 50ms providers in series would be ~200ms.
    assert elapsed < 0.15


@pytest.mark.asyncio
async def test_an_empty_provider_list_is_a_programming_error():
    with pytest.raises(ValueError):
        await compare_text_providers(_request(), [])
