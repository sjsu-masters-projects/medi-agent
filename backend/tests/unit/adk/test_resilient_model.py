"""Provider deadlines and circuit breaking for ADK model routes."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from google.adk.models import BaseLlm, FallbackModel, LlmRequest, LlmResponse
from google.genai import types

from app.adk.models.resilient import (
    ModelAttemptDeadlineError,
    ModelCircuitOpenError,
    ResilientLlm,
)


class _ProviderError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"provider returned {status_code}")


class _StubModel(BaseLlm):
    delay_seconds: float = 0.0
    status_code: int | None = None
    text: str = "ok"
    calls: int = 0

    async def generate_content_async(
        self, llm_request: Any, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.calls += 1
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.status_code is not None:
            raise _ProviderError(self.status_code)
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=self.text)]))


def _request() -> LlmRequest:
    return LlmRequest(
        model="route",
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])],
    )


@pytest.fixture(autouse=True)
def clear_circuits() -> None:
    ResilientLlm.reset_circuits()


@pytest.mark.asyncio
async def test_a_stalled_attempt_becomes_a_retriable_504() -> None:
    wrapper = ResilientLlm(
        model="slow",
        delegate=_StubModel(model="slow", delay_seconds=1),
        timeout_seconds=0.01,
    )

    with pytest.raises(ModelAttemptDeadlineError) as raised:
        _ = [response async for response in wrapper.generate_content_async(_request())]

    assert raised.value.status_code == 504


@pytest.mark.asyncio
async def test_a_timeout_moves_to_the_declared_fallback() -> None:
    slow = ResilientLlm(
        model="slow",
        delegate=_StubModel(model="slow", delay_seconds=1),
        timeout_seconds=0.01,
    )
    backup = ResilientLlm(
        model="backup",
        delegate=_StubModel(model="backup", text="from backup"),
        timeout_seconds=0.1,
    )
    route = FallbackModel(models=[slow, backup])

    responses = [response async for response in route.generate_content_async(_request())]

    assert responses[-1].content.parts[0].text == "from backup"


@pytest.mark.asyncio
async def test_partials_are_not_exposed_before_an_attempt_completes() -> None:
    class _PartialThenStall(BaseLlm):
        async def generate_content_async(
            self, llm_request: Any, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text="half")]),
                partial=True,
            )
            await asyncio.sleep(1)

    primary = ResilientLlm(
        model="partial",
        delegate=_PartialThenStall(model="partial"),
        timeout_seconds=0.01,
    )
    backup = ResilientLlm(
        model="backup",
        delegate=_StubModel(model="backup", text="whole"),
        timeout_seconds=0.1,
    )
    route = FallbackModel(models=[primary, backup])

    responses = [response async for response in route.generate_content_async(_request(), True)]

    assert [response.content.parts[0].text for response in responses] == ["whole"]


@pytest.mark.asyncio
async def test_a_429_opens_the_circuit_and_the_next_call_skips_the_provider() -> None:
    delegate = _StubModel(model="throttled", status_code=429)
    wrapper = ResilientLlm(
        model="throttled",
        delegate=delegate,
        timeout_seconds=1,
        circuit_breaker=True,
        cooldown_seconds=60,
    )

    with pytest.raises(_ProviderError):
        _ = [response async for response in wrapper.generate_content_async(_request())]

    started = time.monotonic()
    with pytest.raises(ModelCircuitOpenError) as raised:
        _ = [response async for response in wrapper.generate_content_async(_request())]

    assert raised.value.status_code == 503
    assert delegate.calls == 1
    assert time.monotonic() - started < 0.05


@pytest.mark.asyncio
async def test_a_successful_probe_closes_an_existing_circuit() -> None:
    delegate = _StubModel(model="recovering", status_code=429)
    wrapper = ResilientLlm(
        model="recovering",
        delegate=delegate,
        timeout_seconds=1,
        circuit_breaker=True,
        cooldown_seconds=0.01,
    )

    with pytest.raises(_ProviderError):
        _ = [response async for response in wrapper.generate_content_async(_request())]
    await asyncio.sleep(0.02)
    delegate.status_code = None

    responses = [response async for response in wrapper.generate_content_async(_request())]

    assert responses[-1].content.parts[0].text == "ok"
    assert delegate.calls == 2
