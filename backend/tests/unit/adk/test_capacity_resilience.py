"""Capacity retries are bounded, observable, and never splice model answers."""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any

import pytest
from google.adk.models import BaseLlm, FallbackModel, LlmRequest, LlmResponse
from google.genai import types

from app.adk.models.resilient import ModelAttemptDeadlineError, ResilientLlm
from app.config import settings
from app.core.model_traffic import model_slot


class RejectionError(Exception):
    def __init__(self, status: int, retry_after: str = "0") -> None:
        self.status_code = status
        self.headers = {"Retry-After": retry_after}
        super().__init__("DO_NOT_LOG patient or credential")


class Recovering(BaseLlm):
    failures: int = 1
    status: int = 429
    retry_after: str = "0"
    calls: int = 0

    async def generate_content_async(
        self, llm_request: Any, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.calls += 1
        if self.calls <= self.failures:
            yield LlmResponse(
                content=types.Content(parts=[types.Part(text="discard")]), partial=True
            )
            llm_request.contents.clear()
            raise RejectionError(self.status, self.retry_after)
        assert llm_request.contents
        yield LlmResponse(content=types.Content(parts=[types.Part(text="whole")]))


def request() -> LlmRequest:
    return LlmRequest(contents=[types.Content(parts=[types.Part(text="synthetic")])])


def wrapper(model: Recovering, timeout: float = 2) -> ResilientLlm:
    return ResilientLlm(model=model.model, delegate=model, timeout_seconds=timeout, retry_429=True)


@pytest.fixture(autouse=True)
def fast_admission(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "model_max_concurrency", 2)
    monkeypatch.setattr(settings, "model_min_start_interval_seconds", 0)
    monkeypatch.setattr("app.adk.models.resilient.random.uniform", lambda a, b: a)


@pytest.mark.asyncio
async def test_one_429_retry_recovers_without_partial_or_mutated_request(caplog: Any) -> None:
    model = Recovering(model="recover")
    with caplog.at_level(logging.INFO):
        responses = [r async for r in wrapper(model).generate_content_async(request())]
    assert model.calls == 2
    assert [r.content.parts[0].text for r in responses] == ["whole"]
    attempts = [r.model_attempt for r in caplog.records if hasattr(r, "model_attempt")]
    assert [r["status"] for r in attempts] == [429, 200]
    assert [r["retry_count"] for r in attempts] == [0, 1]
    assert "DO_NOT_LOG" not in caplog.text


@pytest.mark.asyncio
async def test_repeat_429_falls_back_after_exactly_two_attempts() -> None:
    primary = Recovering(model="primary", failures=10)
    backup = Recovering(model="backup", failures=0)
    route = FallbackModel(models=[wrapper(primary), wrapper(backup)])
    responses = [r async for r in route.generate_content_async(request())]
    assert primary.calls == 2 and backup.calls == 1
    assert [r.content.parts[0].text for r in responses] == ["whole"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 500, 503])
async def test_non_429_is_not_retried(status: int) -> None:
    model = Recovering(model="terminal", status=status)
    with pytest.raises(RejectionError):
        _ = [r async for r in wrapper(model).generate_content_async(request())]
    assert model.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_after", ["10", "inf", "nan"])
async def test_retry_after_that_cannot_fit_is_not_ignored(retry_after: str) -> None:
    model = Recovering(model="long-wait", retry_after=retry_after)
    with pytest.raises(RejectionError):
        _ = [r async for r in wrapper(model).generate_content_async(request())]
    assert model.calls == 1


@pytest.mark.asyncio
async def test_retry_after_reserves_response_time() -> None:
    model = Recovering(model="tiny-budget", retry_after="0.1")
    with pytest.raises(RejectionError):
        _ = [r async for r in wrapper(model, 0.15).generate_content_async(request())]
    assert model.calls == 1


def test_http_date_retry_after() -> None:
    value = format_datetime(datetime.now(UTC) + timedelta(seconds=30))
    assert 28 < ResilientLlm._retry_delay(RejectionError(429, value)) <= 30


@pytest.mark.parametrize("value", ["bad date", "-1"])
def test_invalid_retry_after_uses_bounded_jitter(value: str) -> None:
    assert ResilientLlm._retry_delay(RejectionError(429, value)) == 0.2


def test_google_sdk_response_headers_and_status_are_supported() -> None:
    import httpx
    from google.genai.errors import ClientError

    error = ClientError(
        429,
        {"error": {"message": "DO_NOT_LOG"}},
        httpx.Response(429, headers={"Retry-After": "0.03"}),
    )
    assert ResilientLlm._status_code(error) == 429
    assert ResilientLlm._retry_delay(error) == 0.03


@pytest.mark.asyncio
async def test_a_short_retry_after_is_honored() -> None:
    model = Recovering(model="short-wait", retry_after="0.03")
    started = time.monotonic()
    assert [r async for r in wrapper(model).generate_content_async(request())]
    assert model.calls == 2 and time.monotonic() - started >= 0.03


@pytest.mark.asyncio
async def test_admission_queue_is_inside_deadline_and_cancellation_releases_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "model_max_concurrency", 1)
    model = Recovering(model="queue", failures=0)
    async with model_slot("queue", "global"):
        with pytest.raises(ModelAttemptDeadlineError):
            _ = [r async for r in wrapper(model, 0.01).generate_content_async(request())]
    assert model.calls == 0
    assert [r async for r in wrapper(model).generate_content_async(request())]


@pytest.mark.asyncio
async def test_concurrency_and_start_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "model_max_concurrency", 2)
    monkeypatch.setattr(settings, "model_min_start_interval_seconds", 0.02)
    active = 0
    peak = 0
    starts: list[float] = []

    async def call() -> None:
        nonlocal active, peak
        async with model_slot("paced", "global"):
            starts.append(time.monotonic())
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.04)
            finally:
                active -= 1

    await asyncio.gather(*(call() for _ in range(6)))
    assert peak == 2
    assert all(b - a >= 0.018 for a, b in zip(starts, starts[1:], strict=False))


@pytest.mark.asyncio
async def test_background_jobs_leave_a_slot_for_interactive_calls() -> None:
    first_started = asyncio.Event()
    release = asyncio.Event()
    starts: list[str] = []

    async def background(name: str) -> None:
        async with model_slot("reserved", "global", background=True):
            starts.append(name)
            first_started.set()
            await release.wait()

    first = asyncio.create_task(background("first"))
    await first_started.wait()
    second = asyncio.create_task(background("second"))
    await asyncio.sleep(0)
    async with asyncio.timeout(0.1), model_slot("reserved", "global"):
        assert starts == ["first"]
    second.cancel()
    with pytest.raises(asyncio.CancelledError):
        await second
    release.set()
    await first
    async with model_slot("reserved", "global", background=True):
        pass


@pytest.mark.asyncio
async def test_native_background_sanitized_diagnostics(caplog: Any) -> None:
    from types import SimpleNamespace

    from app.clients.gemini import GeminiClient

    client = object.__new__(GeminiClient)
    client.model_name = "native-background"
    calls = 0

    async def reject(**kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        raise RejectionError(429)

    client.genai_client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=reject))
    )
    with caplog.at_level(logging.INFO), pytest.raises(RejectionError):
        await client._paced_genai_call(["DO_NOT_LOG synthetic prompt"], None, 1)
    assert calls == 1
    attempts = [r.model_attempt for r in caplog.records if hasattr(r, "model_attempt")]
    assert attempts[0]["status"] == 429 and attempts[0]["retry_count"] == 1
    assert "DO_NOT_LOG" not in caplog.text
