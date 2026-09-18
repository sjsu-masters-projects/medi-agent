"""The OpenAI-compatible provider speaks one wire shape to many vendors.

What matters is that it honours the provider contract: a structured request asks for
native JSON-schema output, failures are classified rather than swallowed, and usage
reaches telemetry so cost can be estimated.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.clients.openai_compatible import OpenAICompatibleTextProvider
from app.models.generation import GenerationErrorCode, GenerationProviderError, GenerationRequest


def _provider(handler: Any, **kwargs: Any) -> OpenAICompatibleTextProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICompatibleTextProvider(
        name="local", model="test-model", base_url="http://models.test/v1", client=client, **kwargs
    )


def _ok_response(content: Any, *, usage: dict[str, int] | None = None) -> httpx.Response:
    body: dict[str, Any] = {
        "model": "test-model-2026",
        "choices": [{"message": {"content": content}}],
    }
    if usage is not None:
        body["usage"] = usage
    return httpx.Response(200, json=body)


@pytest.mark.asyncio
async def test_a_plain_request_returns_text_and_usage() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("Authorization")
        return _ok_response(
            "hello", usage={"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}
        )

    provider = _provider(handler, api_key="secret")
    response = await provider.generate(
        GenerationRequest(
            prompt="hi", system_instruction="be brief", temperature=0.2, max_tokens=64
        )
    )

    assert response.text == "hello"
    assert response.telemetry.provider == "local"
    assert response.telemetry.model == "test-model-2026"
    assert response.telemetry.usage == {"input_tokens": 12, "output_tokens": 3, "total_tokens": 15}
    assert seen["url"] == "http://models.test/v1/chat/completions"
    assert seen["auth"] == "Bearer secret"
    assert seen["body"]["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hi"},
    ]
    assert "response_format" not in seen["body"]


@pytest.mark.asyncio
async def test_a_schema_is_requested_natively_when_supported() -> None:
    seen: dict[str, Any] = {}
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return _ok_response('{"ok": true}')

    provider = _provider(handler)
    await provider.generate(GenerationRequest(prompt="x", response_schema=schema))

    assert seen["body"]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "response", "schema": schema},
    }


@pytest.mark.asyncio
async def test_native_schema_can_be_switched_off_for_endpoints_that_reject_it() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return _ok_response("{}")

    provider = _provider(handler, native_structured_output=False)
    await provider.generate(GenerationRequest(prompt="x", response_schema={"type": "object"}))

    assert "response_format" not in seen["body"]


@pytest.mark.asyncio
async def test_list_style_content_parts_are_joined() -> None:
    provider = _provider(
        lambda _r: _ok_response([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}])
    )

    response = await provider.generate(GenerationRequest(prompt="x"))

    assert response.text == "ab"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, GenerationErrorCode.AUTHENTICATION),
        (403, GenerationErrorCode.AUTHENTICATION),
        (404, GenerationErrorCode.CONFIGURATION),
        (429, GenerationErrorCode.RATE_LIMITED),
        (500, GenerationErrorCode.UNAVAILABLE),
        (503, GenerationErrorCode.UNAVAILABLE),
    ],
)
@pytest.mark.asyncio
async def test_http_failures_are_classified(status: int, code: GenerationErrorCode) -> None:
    provider = _provider(lambda _r: httpx.Response(status, json={"error": "nope"}))

    with pytest.raises(GenerationProviderError) as raised:
        await provider.generate(GenerationRequest(prompt="x"))

    assert raised.value.code is code


@pytest.mark.asyncio
async def test_a_timeout_is_a_timeout_not_an_outage() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    provider = _provider(handler)
    with pytest.raises(GenerationProviderError) as raised:
        await provider.generate(GenerationRequest(prompt="x"))

    assert raised.value.code is GenerationErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_a_connection_error_is_unavailable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    provider = _provider(handler)
    with pytest.raises(GenerationProviderError) as raised:
        await provider.generate(GenerationRequest(prompt="x"))

    assert raised.value.code is GenerationErrorCode.UNAVAILABLE


@pytest.mark.asyncio
async def test_an_empty_or_malformed_answer_is_invalid_response() -> None:
    provider = _provider(lambda _r: httpx.Response(200, json={"choices": []}))
    with pytest.raises(GenerationProviderError) as raised:
        await provider.generate(GenerationRequest(prompt="x"))
    assert raised.value.code is GenerationErrorCode.INVALID_RESPONSE

    provider = _provider(lambda _r: httpx.Response(200, content=b"not json"))
    with pytest.raises(GenerationProviderError) as raised:
        await provider.generate(GenerationRequest(prompt="x"))
    assert raised.value.code is GenerationErrorCode.INVALID_RESPONSE


def test_reasoning_effort_is_sent_only_when_configured() -> None:
    from unittest.mock import MagicMock

    from app.clients.openai_compatible import OpenAICompatibleTextProvider
    from app.models.generation import GenerationRequest

    request = GenerationRequest(prompt="hi")
    tuned = OpenAICompatibleTextProvider(
        name="t", model="m", base_url="https://x/v1", reasoning_effort="low", client=MagicMock()
    )
    plain = OpenAICompatibleTextProvider(
        name="p", model="m", base_url="https://x/v1", client=MagicMock()
    )

    assert tuned._body(request)["reasoning_effort"] == "low"
    assert "reasoning_effort" not in plain._body(request)


def _retry_provider(handler, max_retries, slept):  # type: ignore[no-untyped-def]
    import httpx

    from app.clients.openai_compatible import OpenAICompatibleTextProvider

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    return OpenAICompatibleTextProvider(
        name="p",
        model="m",
        base_url="https://x/v1",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_retries=max_retries,
        sleep=fake_sleep,
    )


def test_shared_capacity_errors_are_retried_with_growing_backoff() -> None:
    import asyncio

    import httpx

    from app.models.generation import GenerationRequest

    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, json={"error": {"code": 429}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    slept: list[float] = []
    response = asyncio.run(
        _retry_provider(handler, 3, slept).generate(GenerationRequest(prompt="hi"))
    )

    assert response.text == "ok"
    assert response.telemetry.retries == 2
    assert len(slept) == 2
    assert slept[1] >= slept[0]


def test_retries_stop_at_the_limit_and_keep_the_rate_limit_code() -> None:
    import asyncio

    import httpx
    import pytest

    from app.models.generation import (
        GenerationErrorCode,
        GenerationProviderError,
        GenerationRequest,
    )

    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429, json={"error": {"code": 429}})

    with pytest.raises(GenerationProviderError) as raised:
        asyncio.run(_retry_provider(handler, 2, []).generate(GenerationRequest(prompt="hi")))

    assert raised.value.code == GenerationErrorCode.RATE_LIMITED
    assert len(calls) == 3


def test_a_client_error_is_never_retried() -> None:
    import asyncio

    import httpx
    import pytest

    from app.models.generation import GenerationProviderError, GenerationRequest

    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": {"code": 400}})

    with pytest.raises(GenerationProviderError):
        asyncio.run(_retry_provider(handler, 3, []).generate(GenerationRequest(prompt="hi")))

    assert len(calls) == 1


def test_a_bearer_callable_supplies_a_fresh_token_for_every_request() -> None:
    import asyncio

    import httpx

    from app.clients.openai_compatible import OpenAICompatibleTextProvider
    from app.models.generation import GenerationRequest

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Authorization"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    tokens = iter(["first", "second"])
    provider = OpenAICompatibleTextProvider(
        name="p",
        model="m",
        base_url="https://x/v1",
        bearer_token=lambda: next(tokens),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    async def two_calls() -> None:
        await provider.generate(GenerationRequest(prompt="a"))
        await provider.generate(GenerationRequest(prompt="b"))

    asyncio.run(two_calls())

    assert seen == ["Bearer first", "Bearer second"]


def test_inline_reasoning_is_removed_before_the_answer() -> None:
    from app.clients.openai_compatible import _extract_text

    data = {
        "choices": [{"message": {"content": '<unused94>thought\nsecret plan<unused95>{"a": 1}'}}]
    }

    assert _extract_text(data) == '{"a": 1}'


def test_unterminated_reasoning_yields_no_answer_instead_of_leaking() -> None:
    from app.clients.openai_compatible import _extract_text

    data = {
        "choices": [{"message": {"content": "<unused94>thought\nstill reasoning when cut off"}}]
    }

    assert _extract_text(data) == ""


def test_plain_answers_are_untouched() -> None:
    from app.clients.openai_compatible import _extract_text

    assert _extract_text({"choices": [{"message": {"content": "  ok  "}}]}) == "ok"


@pytest.mark.asyncio
async def test_the_finish_reason_is_recorded_so_truncation_is_visible() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "partial answer"}, "finish_reason": "length"}]
            },
        )

    response = await _provider(handler).generate(GenerationRequest(prompt="x"))

    assert response.telemetry.finish_reason == "length"


@pytest.mark.asyncio
async def test_thinking_until_the_budget_runs_out_is_truncation_not_a_broken_reply() -> None:
    """A reasoning model can spend its whole budget and return empty content, no error."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
        )

    with pytest.raises(GenerationProviderError) as raised:
        await _provider(handler).generate(GenerationRequest(prompt="x"))

    assert raised.value.code is GenerationErrorCode.TRUNCATED


@pytest.mark.asyncio
async def test_an_empty_answer_that_finished_normally_is_still_invalid() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}
        )

    with pytest.raises(GenerationProviderError) as raised:
        await _provider(handler).generate(GenerationRequest(prompt="x"))

    assert raised.value.code is GenerationErrorCode.INVALID_RESPONSE


@pytest.mark.asyncio
async def test_a_rejected_schema_is_not_reported_as_an_outage() -> None:
    """MedGemma's container rejects some schemas with 400; that is our request's fault."""
    provider = _provider(lambda _r: httpx.Response(400, json={"error": "'type' must be a string"}))

    with pytest.raises(GenerationProviderError) as raised:
        await provider.generate(GenerationRequest(prompt="x"))

    assert raised.value.code is GenerationErrorCode.INVALID_REQUEST


@pytest.mark.asyncio
async def test_reasoning_tokens_are_counted_separately_from_the_answer() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 900,
                    "total_tokens": 910,
                    "completion_tokens_details": {"reasoning_tokens": 850},
                },
            },
        )

    response = await _provider(handler).generate(GenerationRequest(prompt="x"))

    assert response.telemetry.usage["output_tokens"] == 900
    assert response.telemetry.usage["reasoning_tokens"] == 850
