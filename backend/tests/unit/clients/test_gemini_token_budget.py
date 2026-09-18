"""Token budgets, thinking ceilings, and refusing to pass off a truncated answer.

Three defects are pinned here, all of them silent in production:

- every request was raised to `max(max_tokens, 8192)` on a false premise, so callers were
  billed for up to sixteen times the budget they asked for;
- a response that stopped at `MAX_TOKENS` was logged as a warning and then **returned**,
  so a clinical answer cut off mid-sentence reached the patient looking finished;
- the streaming path, which is the patient-facing one, set no ceiling at all and never
  read `finish_reason`, so a severed reply was indistinguishable from a complete one.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from app.core.exceptions import LLMError


def _response(text: str, finish_reason: str | None = "STOP") -> SimpleNamespace:
    reason = SimpleNamespace(name=finish_reason) if finish_reason else None
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=reason)])


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    from app.config import settings

    monkeypatch.setattr(settings, "google_project_id", "test-project")
    with patch("google.genai.Client") as factory:
        factory.return_value = MagicMock()
        from app.clients.gemini import GeminiClient

        return GeminiClient(model="gemini-3.8-flash", use_vertex_ai=True)


def _capture(client, *responses):
    """Record the budget in force at each call, since escalation mutates the config."""
    budgets: list[int] = []
    levels: list[object] = []
    queue = list(responses)

    async def _generate_content(**kwargs):
        config = kwargs["config"]
        budgets.append(config.max_output_tokens)
        levels.append(getattr(config.thinking_config, "thinking_level", None))
        return queue.pop(0)

    client.genai_client.aio.models.generate_content = _generate_content
    return budgets, levels


@pytest.mark.asyncio
async def test_the_callers_budget_is_honoured(client) -> None:
    """The 8192 floor is gone. It rested on a false premise: the SDK default is None."""
    budgets, _ = _capture(client, _response("ok"))

    await client.generate(prompt="hi", max_tokens=512)

    assert budgets == [512]


@pytest.mark.asyncio
async def test_a_small_budget_is_not_quietly_inflated(client) -> None:
    budgets, _ = _capture(client, _response("ok"))

    await client.generate(prompt="hi", max_tokens=384)

    assert budgets == [384]
    assert 8192 not in budgets


@pytest.mark.asyncio
async def test_the_thinking_level_reaches_the_request(client) -> None:
    _, levels = _capture(client, _response("ok"))

    await client.generate(prompt="hi", max_tokens=1024, thinking_level="LOW")

    assert levels == ["LOW"]


@pytest.mark.asyncio
async def test_no_thinking_config_is_sent_when_none_is_asked_for(client) -> None:
    _, levels = _capture(client, _response("ok"))

    await client.generate(prompt="hi", max_tokens=1024)

    assert levels == [None]


@pytest.mark.asyncio
async def test_a_truncated_answer_is_regenerated_at_a_larger_budget(client) -> None:
    """A regeneration, not a continuation.

    Stitching a second call onto a half sentence of clinical advice risks duplicated or
    contradictory instructions across the seam, and there is no resume API.
    """
    budgets, _ = _capture(
        client,
        _response("partial advice", finish_reason="MAX_TOKENS"),
        _response("the complete advice"),
    )

    result = await client.generate(prompt="hi", max_tokens=1024)

    assert result == "the complete advice"
    assert budgets == [1024, 2048]


@pytest.mark.asyncio
async def test_a_still_truncated_answer_raises_rather_than_being_returned(client) -> None:
    """The defect this exists to prevent: half an answer presented as the whole one."""
    _capture(
        client,
        _response("partial advice", finish_reason="MAX_TOKENS"),
        _response("still partial", finish_reason="MAX_TOKENS"),
    )

    with pytest.raises(LLMError, match="truncated"):
        await client.generate(prompt="hi", max_tokens=1024)


@pytest.mark.asyncio
async def test_the_partial_text_never_leaks_through_the_error(client) -> None:
    _capture(
        client,
        _response("take 40mg of", finish_reason="MAX_TOKENS"),
        _response("take 40mg of", finish_reason="MAX_TOKENS"),
    )

    with pytest.raises(LLMError) as raised:
        await client.generate(prompt="hi", max_tokens=1024)

    assert "take 40mg of" not in str(raised.value)


@pytest.mark.asyncio
async def test_an_empty_answer_that_spent_its_budget_thinking_is_truncation(client) -> None:
    """Measured: MEDIUM at 1024 produced 984 thought tokens and 36 answer tokens.

    A thinking model can return no text at all. That is our budget running out, not the
    model returning an empty reply, and the two must not be reported the same way.
    """
    budgets, _ = _capture(
        client,
        _response("", finish_reason="MAX_TOKENS"),
        _response("the complete advice"),
    )

    assert await client.generate(prompt="hi", max_tokens=1024) == "the complete advice"
    assert budgets == [1024, 2048]


@pytest.mark.asyncio
async def test_structured_output_passes_its_own_budget_through(client) -> None:
    """It used to call `generate` with no budget, taking the default and then the floor."""
    budgets, levels = _capture(client, _response('{"value": "x"}'))

    await client.generate_structured(
        prompt="hi", response_model=_Shape, max_tokens=4096, thinking_level="MEDIUM"
    )

    assert budgets == [4096]
    assert levels == ["MEDIUM"]


def test_finish_reason_reads_an_enum_a_string_and_nothing() -> None:
    """Misreading this decides whether a half answer is treated as a finished one."""
    from app.clients.gemini import _finish_reason

    assert _finish_reason(_response("x", finish_reason="MAX_TOKENS")) == "MAX_TOKENS"
    assert (
        _finish_reason(SimpleNamespace(candidates=[SimpleNamespace(finish_reason="STOP")]))
        == "STOP"
    )
    assert _finish_reason(SimpleNamespace(candidates=[])) is None
    assert _finish_reason(SimpleNamespace(candidates=None)) is None


class _Stream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        async def _iter():
            for chunk in self._chunks:
                yield chunk

        return _iter()


@pytest.mark.asyncio
async def test_the_streaming_path_sets_a_ceiling(client) -> None:
    """It previously set none, so a reply could run until the model stopped on its own."""
    captured: dict[str, object] = {}

    async def _stream(**kwargs):
        captured["budget"] = kwargs["config"].max_output_tokens
        return _Stream([_response("hello")])

    client.genai_client.aio.models.generate_content_stream = _stream

    chunks = [chunk async for chunk in client.generate_stream(prompt="hi", max_tokens=2048)]

    assert chunks == ["hello"]
    assert captured["budget"] == 2048


@pytest.mark.asyncio
async def test_a_severed_stream_raises_after_its_chunks(client) -> None:
    """The patient-facing path. A sentence that stops halfway must not pass as an answer."""
    client.genai_client.aio.models.generate_content_stream = AsyncMock(
        return_value=_Stream(
            [_response("Take your", finish_reason=None), _response("", finish_reason="MAX_TOKENS")]
        )
    )

    with pytest.raises(LLMError, match="cut off"):
        async for _ in client.generate_stream(prompt="hi", max_tokens=512):
            pass


@pytest.mark.asyncio
async def test_a_complete_stream_does_not_raise(client) -> None:
    client.genai_client.aio.models.generate_content_stream = AsyncMock(
        return_value=_Stream([_response("all done", finish_reason="STOP")])
    )

    chunks = [chunk async for chunk in client.generate_stream(prompt="hi", max_tokens=512)]

    assert chunks == ["all done"]


# ---------------------------------------------------------------------------
# Sampling parameters
#
# Gemini 3.x accepts `temperature` and ignores it. Sending it anyway makes a call site
# look like it controls determinism when it does not — measured, `temperature=0.0` gave
# four different answers to one prompt in four calls.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Structured output
#
# The schema used to be pasted into the prompt on every path, which asks for a shape
# instead of constraining one. Vertex enforces it natively, and — verified on the locked
# SDK — does so without disabling thinking.
# ---------------------------------------------------------------------------


class _Shape(BaseModel):
    value: str


def _structured_config(client) -> list[object]:
    seen: list[object] = []

    async def _generate_content(**kwargs):
        seen.append(kwargs["config"])
        return _response('{"value": "x"}')

    client.genai_client.aio.models.generate_content = _generate_content
    return seen


@pytest.mark.asyncio
async def test_vertex_enforces_the_schema_natively(client) -> None:
    seen = _structured_config(client)

    await client.generate_structured(prompt="hi", response_model=_Shape)

    assert seen[0].response_schema is _Shape
    assert seen[0].response_mime_type == "application/json"


@pytest.mark.asyncio
async def test_the_schema_is_not_also_pasted_into_the_prompt(client) -> None:
    """Asking twice is not stronger than constraining once, and it costs input tokens."""
    prompts: list[str] = []

    async def _generate_content(**kwargs):
        prompts.append(kwargs["contents"][0])
        return _response('{"value": "x"}')

    client.genai_client.aio.models.generate_content = _generate_content

    await client.generate_structured(prompt="summarize this", response_model=_Shape)

    assert prompts == ["summarize this"]
    assert "JSON response:" not in prompts[0]


@pytest.mark.asyncio
async def test_no_schema_is_sent_for_an_unstructured_call(client) -> None:
    seen: list[object] = []

    async def _generate_content(**kwargs):
        seen.append(kwargs["config"])
        return _response("plain text")

    client.genai_client.aio.models.generate_content = _generate_content

    await client.generate(prompt="hi", max_tokens=512)

    assert seen[0].response_schema is None
    assert seen[0].response_mime_type is None


@pytest.mark.asyncio
async def test_structured_output_still_honours_the_thinking_ceiling(client) -> None:
    """Constraining the shape must not cost the reasoning — it collided on MedGemma."""
    seen = _structured_config(client)

    await client.generate_structured(prompt="hi", response_model=_Shape, thinking_level="MEDIUM")

    assert seen[0].response_schema is _Shape
    assert seen[0].thinking_config.thinking_level == "MEDIUM"


def test_gemini_3_models_do_not_honour_sampling_parameters() -> None:
    from app.clients.gemini import _honours_sampling_parameters

    assert _honours_sampling_parameters("gemini-3.8-flash") is False
    assert _honours_sampling_parameters("gemini-3.1-flash-lite") is False
    assert _honours_sampling_parameters("gemini-3-pro-image") is False


def test_older_models_still_honour_them() -> None:
    """The client is generic, and AI Studio still serves models where this works."""
    from app.clients.gemini import _honours_sampling_parameters

    assert _honours_sampling_parameters("gemini-2.5-flash") is True
    assert _honours_sampling_parameters("gemini-1.5-pro") is True


def _temperatures(client) -> list[object]:
    seen: list[object] = []

    async def _generate_content(**kwargs):
        seen.append(kwargs["config"].temperature)
        return _response("ok")

    client.genai_client.aio.models.generate_content = _generate_content
    return seen


@pytest.mark.asyncio
async def test_temperature_is_not_sent_to_a_gemini_3_model(client) -> None:
    seen = _temperatures(client)

    await client.generate(prompt="hi", temperature=0.2, max_tokens=512)

    assert seen == [None]


@pytest.mark.asyncio
async def test_temperature_is_still_sent_to_an_older_model(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "google_project_id", "test-project")
    with patch("google.genai.Client") as factory:
        factory.return_value = MagicMock()
        from app.clients.gemini import GeminiClient

        older = GeminiClient(model="gemini-2.5-flash", use_vertex_ai=True)

    seen = _temperatures(older)

    await older.generate(prompt="hi", temperature=0.2, max_tokens=512)

    assert seen == [0.2]


@pytest.mark.asyncio
async def test_the_streaming_path_drops_it_too(client) -> None:
    captured: dict[str, object] = {}

    async def _stream(**kwargs):
        captured["temperature"] = kwargs["config"].temperature
        return _Stream([_response("hello", finish_reason="STOP")])

    client.genai_client.aio.models.generate_content_stream = _stream

    async for _ in client.generate_stream(prompt="hi", temperature=0.2, max_tokens=512):
        pass

    assert captured["temperature"] is None
