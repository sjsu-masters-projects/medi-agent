"""NVIDIA NIM client.

NIM is the one provider in the comparison that is not Google-hosted, so its failure
modes are the ones least likely to correlate with the others. These tests pin the
behaviour that matters to an evaluation: a failure is raised rather than returned as
empty text, and no prompt or response body reaches a log or an exception message.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

import app.clients.nvidia_nim as nim_module
from app.core.exceptions import LLMError

PROMPT = "Patient reports chest tightness after starting lisinopril."


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nim_module.settings, "nvidia_nim_api_key", "test-key")
    monkeypatch.setattr(
        nim_module.settings, "nvidia_nim_base_url", "https://nim.example.test/v1"
    )
    monkeypatch.setattr(nim_module.settings, "nvidia_nim_model", "vendor/model-1")


def _client() -> Any:
    return nim_module.NvidiaNimClient()


def _stub_post(monkeypatch: pytest.MonkeyPatch, response: httpx.Response) -> dict[str, Any]:
    """Capture the outgoing request and return a canned response."""
    seen: dict[str, Any] = {}

    async def _post(self: Any, url: str, **kwargs: Any) -> httpx.Response:
        seen["url"] = url
        seen["json"] = kwargs.get("json")
        seen["headers"] = kwargs.get("headers")
        return response

    monkeypatch.setattr(httpx.AsyncClient, "post", _post)
    return seen


def _ok(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_requires_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nim_module.settings, "nvidia_nim_api_key", "")

    with pytest.raises(ValueError, match="NVIDIA_NIM_API_KEY"):
        _client()


@pytest.mark.asyncio
async def test_sends_an_openai_shaped_chat_request(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _stub_post(monkeypatch, _ok("answer"))

    result = await _client().generate(PROMPT, system_instruction="Be brief", temperature=0.1, max_tokens=64)

    assert result == "answer"
    assert seen["url"] == "https://nim.example.test/v1/chat/completions"
    assert seen["json"]["model"] == "vendor/model-1"
    assert seen["json"]["messages"] == [
        {"role": "system", "content": "Be brief"},
        {"role": "user", "content": PROMPT},
    ]
    assert seen["headers"]["Authorization"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_omits_the_system_message_when_none_is_given(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _stub_post(monkeypatch, _ok("answer"))

    await _client().generate(PROMPT)

    assert [m["role"] for m in seen["json"]["messages"]] == ["user"]


@pytest.mark.asyncio
async def test_accepts_the_older_completion_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """NIM hosts many models and not all return a message object."""
    _stub_post(monkeypatch, httpx.Response(200, json={"choices": [{"text": " spaced "}]}))

    assert await _client().generate(PROMPT) == "spaced"


@pytest.mark.asyncio
async def test_an_unrecognized_shape_raises_rather_than_returning_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty text would read downstream as a model that answered with nothing."""
    _stub_post(monkeypatch, httpx.Response(200, json={"choices": [{"unexpected": 1}]}))

    with pytest.raises(LLMError):
        await _client().generate(PROMPT)


@pytest.mark.asyncio
async def test_no_choices_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_post(monkeypatch, httpx.Response(200, json={"choices": []}))

    with pytest.raises(LLMError):
        await _client().generate(PROMPT)


@pytest.mark.asyncio
async def test_an_error_status_raises_without_echoing_the_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The body can contain the prompt, which is clinical scenario text."""
    _stub_post(monkeypatch, httpx.Response(429, text=f"rate limited while handling: {PROMPT}"))

    with pytest.raises(LLMError) as caught:
        await _client().generate(PROMPT)

    assert "429" in str(caught.value)
    assert PROMPT not in str(caught.value)


@pytest.mark.asyncio
async def test_a_transport_failure_becomes_an_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(self: Any, url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(httpx.AsyncClient, "post", _boom)

    with pytest.raises(LLMError, match="NIM request failed"):
        await _client().generate(PROMPT)


@pytest.mark.asyncio
async def test_an_image_is_ignored_rather_than_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The signature stays interchangeable with the other clients."""
    _stub_post(monkeypatch, _ok("answer"))

    assert await _client().generate(PROMPT, image=b"\x89PNG") == "answer"
