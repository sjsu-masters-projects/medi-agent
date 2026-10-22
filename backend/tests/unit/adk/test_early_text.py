"""Reply text that is shown, and may be spoken, while it is still being written.

The properties that matter: what is released early is a prefix of the saved reply; a held
tool round can still fall back but shown text cannot be spliced; a failure after text was
shown is withdrawn and replaced; the worker's draft checkpoints and the viewers follow.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

import pytest
from google.adk.models import BaseLlm, FallbackModel, LlmResponse
from google.genai import types
from tests.unit.adk.test_chat_runtime import (
    COORDINATOR_NOTES,
    PATIENT_ID,
    _build_runner,
    _first,
    _turn,
)

from app.adk.chat_runtime import CareCoordinatorRuntime
from app.adk.grounding import StreamingReplyFilter, plain_reply, without_source_lines
from app.adk.models.resilient import DRAFT_RESET_KEY, ReplyRoute, ResilientLlm
from app.config import settings
from app.core.ai_availability import classify_outcome
from app.core.model_traffic import ModelAdmissionError, model_slot, use_workload
from app.services import chat_turn_worker as worker
from app.services.chat_turn_events import event_to_messages
from app.services.voice_live import SentenceChunker


def _norm(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


SAMPLES = [
    "Hello **there**, take it with food.\n\nSource: MedlinePlus: Foo (checked Oct 1, 2026)",
    "* one\n* two\n- three\n\n\n\nAfter **bold** and __under__ `code`\nSources: x\nFin.",
    "# Heading\nText with * star and 5 * 3\n  \nFuentes: algo\n\nEnd",
    "Sorry, I can't say. Source of pain? Sourced item\nFuente: x",
    "\n\n  leading ws\n\n**Source:** foo\nbar",
]


@pytest.mark.parametrize("text", SAMPLES)
def test_the_stream_filter_is_always_a_prefix_of_the_final_reply(text: str) -> None:
    rng = random.Random(7)
    expected = _norm(plain_reply(without_source_lines(text)))
    for _ in range(40):
        reply_filter, shown, index = StreamingReplyFilter(), "", 0
        while index < len(text):
            step = rng.randint(1, 7)
            shown += reply_filter.feed(text[index : index + step])
            index += step
            assert expected.startswith(_norm(shown))
        shown += reply_filter.finish()
        assert _norm(shown) == expected


def test_a_line_that_may_become_a_source_line_is_held_until_it_is_known() -> None:
    reply_filter = StreamingReplyFilter()
    assert reply_filter.feed("Hello.\nSou") == "Hello."
    assert reply_filter.feed("rce: x\nNext") == "\n\nNext"
    assert reply_filter.feed("") == ""


def test_the_voice_chunker_drops_a_source_line_even_when_its_title_has_a_full_stop() -> None:
    chunker = SentenceChunker(max_chars=240)
    spoken = chunker.feed(
        "Take it with food. Ask us.\n\nSource: MedlinePlus: Dr. Smith. Diabetes\n"
    )
    spoken += chunker.finish()
    assert spoken == ["Take it with food.", "Ask us."]


# -- the model boundary ----------------------------------------------------------------------


def _text(value: str, *, partial: bool = False) -> LlmResponse:
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text=value)]), partial=partial
    )


class _Script(BaseLlm):
    """Yields scripted responses; an Exception in the script is raised at that point."""

    script: list[Any] = []
    calls: int = 0

    async def generate_content_async(
        self, llm_request: Any, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.calls += 1
        for item in self.script:
            if isinstance(item, BaseException):
                raise item
            if isinstance(item, float):
                await asyncio.sleep(item)
                continue
            yield item


class _StatusError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(str(status_code))
        self.status_code = status_code


def _request() -> Any:
    from google.adk.models import LlmRequest

    return LlmRequest(
        model="r", contents=[types.Content(role="user", parts=[types.Part(text="x")])]
    )


@pytest.fixture(autouse=True)
def _reset() -> None:
    ResilientLlm.reset_circuits()


@pytest.mark.asyncio
async def test_a_text_route_releases_text_while_the_model_is_still_writing() -> None:
    seen: list[str] = []
    gate = asyncio.Event()

    class _Slow(BaseLlm):
        async def generate_content_async(
            self, llm_request: Any, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            yield _text("First sentence. ", partial=True)
            await gate.wait()
            yield _text("Second.", partial=True)

    route = ResilientLlm(
        model="m", delegate=_Slow(model="m"), timeout_seconds=5, stream_text=True, workload="reply"
    )
    stream = route.generate_content_async(_request(), True)
    seen.append((await stream.__anext__()).content.parts[0].text)
    assert seen == ["First sentence. "]  # before the model finished
    gate.set()
    seen.append((await stream.__anext__()).content.parts[0].text)
    assert [part async for part in stream] == []


@pytest.mark.asyncio
async def test_a_tool_round_is_still_held_and_can_fall_back_before_any_text() -> None:
    call = LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(name="t", args={}))],
        )
    )
    primary = ResilientLlm(
        model="a",
        delegate=_Script(model="a", script=[call, _StatusError(503)]),
        timeout_seconds=1,
        stream_text=True,
    )
    backup = ResilientLlm(
        model="b",
        delegate=_Script(model="b", script=[_text("from backup")]),
        timeout_seconds=1,
        stream_text=True,
    )
    out = [
        r
        async for r in FallbackModel(models=[primary, backup]).generate_content_async(
            _request(), True
        )
    ]
    assert [r.content.parts[0].text for r in out] == ["from backup"]


@pytest.mark.asyncio
async def test_a_failure_after_text_was_shown_is_raised_never_spliced() -> None:
    primary = ResilientLlm(
        model="a",
        delegate=_Script(model="a", script=[_text("Shown. ", partial=True), _StatusError(503)]),
        timeout_seconds=1,
        stream_text=True,
    )
    backup = _Script(model="b", script=[_text("other")])
    route = FallbackModel(models=[primary, backup])
    got: list[str] = []
    with pytest.raises(_StatusError):
        async for response in route.generate_content_async(_request(), True):
            got.append(response.content.parts[0].text)
    assert got == ["Shown. "] and backup.calls == 0


@pytest.mark.asyncio
async def test_the_attempt_deadline_still_bounds_a_stream_that_stalls_after_text() -> None:
    from app.adk.models.resilient import ModelAttemptDeadlineError

    route = ResilientLlm(
        model="a",
        delegate=_Script(model="a", script=[_text("Shown. ", partial=True), 5.0]),
        timeout_seconds=0.05,
        stream_text=True,
    )
    with pytest.raises(ModelAttemptDeadlineError):
        _ = [r async for r in route.generate_content_async(_request(), True)]


@pytest.mark.asyncio
async def test_a_thought_only_chunk_does_not_commit_the_attempt() -> None:
    thought = LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text="thinking", thought=True)]),
        partial=True,
    )
    primary = ResilientLlm(
        model="a",
        delegate=_Script(model="a", script=[thought, _StatusError(503)]),
        timeout_seconds=1,
        stream_text=True,
    )
    backup = ResilientLlm(
        model="b", delegate=_Script(model="b", script=[_text("ok")]), timeout_seconds=1
    )
    out = [
        r
        async for r in FallbackModel(models=[primary, backup]).generate_content_async(
            _request(), True
        )
    ]
    assert out[-1].content.parts[0].text == "ok"


# -- the runtime ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_chunks_are_already_in_their_final_form() -> None:
    from tests.unit.adk import test_chat_runtime as base

    class _Marked(base._Responder):
        async def generate_content_async(
            self, llm_request: Any, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            for piece in ("Take **it", "** with food. ", "\nSource: x. y\n", "Done."):
                yield _text(piece, partial=True)
            yield _text("Take **it** with food. \nSource: x. y\nDone.")

    runtime = CareCoordinatorRuntime(runner=_build_runner(decision=base.STANDARD_DECISION))
    # Swap the stub responder for the marked-up one.
    agent = runtime.runner.agent.sub_agents[1]
    agent.model = _Marked(model="stub-responder")
    events = await _turn(runtime, "when do I take it")
    shown = "".join(e["content"] for e in events if e["type"] == "chunk")
    final = _first(events, "complete")["response_text"]
    assert "**" not in shown and "Source" not in shown
    assert _norm(final).startswith(_norm(shown))
    assert COORDINATOR_NOTES not in shown


@pytest.mark.asyncio
async def test_a_stream_that_fails_after_text_is_withdrawn_and_replaced() -> None:
    from tests.unit.adk import test_chat_runtime as base

    class _Dies(base._Responder):
        async def generate_content_async(
            self, llm_request: Any, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            yield _text("Half an answer. ", partial=True)
            raise RuntimeError("boom")

    runtime = CareCoordinatorRuntime(runner=_build_runner(decision=base.STANDARD_DECISION))
    runtime.runner.agent.sub_agents[1].model = _Dies(model="stub-responder")
    events = await _turn(runtime, "when do I take it")
    kinds = [e["type"] for e in events]
    assert kinds.index("chunk_reset") > kinds.index("chunk")
    complete = _first(events, "complete")
    assert complete["fallback_used"] is True and complete["response_text"]
    assert "Half an answer" not in complete["response_text"]


# -- worker draft checkpoints and viewers ----------------------------------------------------

TURN, LEASE = "t1", "l1"


def _sink(appended: list[dict[str, Any]]) -> worker.DraftCheckpointer:
    ops = MagicMock()

    async def call(turn_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        appended.append(payload)
        return {"accepted": True, "next_seq": payload["seq"] + 1}

    ops.call = call
    return worker.DraftCheckpointer(ops, TURN, LEASE, 2)


@pytest.mark.asyncio
async def test_text_that_arrives_after_tool_calls_is_checkpointed_within_the_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker, "DRAFT_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(worker, "DRAFT_TICK_SECONDS", 0.01)
    appended: list[dict[str, Any]] = []
    sink = _sink(appended)
    sink.start()
    sink.publish({"type": "assistant_start", "intent": "general", "urgency": "routine"})
    await asyncio.sleep(0.1)  # the tool rounds: no text yet
    sink.publish({"type": "assistant_chunk", "content": "First sentence. "})
    await asyncio.sleep(0.12)
    during = [p["payload"]["content"] for p in appended]
    sink.publish({"type": "assistant_chunk", "content": "Second."})
    await asyncio.sleep(0.12)
    await sink.stop()
    assert "First sentence. " in during  # written while the reply was still being produced
    assert appended[-1]["payload"]["content"] == "First sentence. Second."
    assert [p["seq"] for p in appended] == list(range(2, 2 + len(appended)))


@pytest.mark.asyncio
async def test_a_reset_is_checkpointed_with_a_higher_epoch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker, "DRAFT_INTERVAL_SECONDS", 0.02)
    monkeypatch.setattr(worker, "DRAFT_TICK_SECONDS", 0.01)
    appended: list[dict[str, Any]] = []
    sink = _sink(appended)
    sink.start()
    sink.publish({"type": "assistant_chunk", "content": "Half."})
    await asyncio.sleep(0.08)
    sink.publish({"type": "assistant_reset"})
    sink.publish({"type": "assistant_chunk", "content": "Fixed."})
    await asyncio.sleep(0.08)
    await sink.stop()
    assert appended[-1]["payload"]["content"] == "Fixed."
    assert appended[-1]["payload"]["epoch"] == 1
    assert "epoch" not in appended[0]["payload"]


@pytest.mark.asyncio
async def test_drafting_is_bounded_per_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker, "DRAFT_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(worker, "DRAFT_TICK_SECONDS", 0.001)
    monkeypatch.setattr(worker, "MAX_DRAFT_APPENDS", 5)
    appended: list[dict[str, Any]] = []
    sink = _sink(appended)
    sink.start()
    for i in range(30):
        sink.publish({"type": "assistant_chunk", "content": f"{i} "})
        await asyncio.sleep(0.003)
    await sink.stop()
    assert len(appended) == 5


def test_a_redelivered_draft_is_idempotent_and_ordered_for_a_viewer() -> None:
    state: dict[str, Any] = {}
    base: dict[str, Any] = {"id": "t", "client_message_id": "c"}
    draft = {"type": "draft", "payload": {"content": "Hello", "intent": "g", "urgency": "routine"}}
    first = event_to_messages(draft, state, base)
    again = event_to_messages(draft, state, base)  # the same checkpoint delivered twice
    longer = event_to_messages(
        {
            "type": "draft",
            "payload": {"content": "Hello there", "intent": "g", "urgency": "routine"},
        },
        state,
        base,
    )
    assert [m["type"] for m in first] == ["assistant_start", "assistant_chunk"]
    assert again == []
    assert longer == [{"type": "assistant_chunk", "content": " there"}]


def test_a_retried_run_withdraws_the_earlier_draft_and_starts_again() -> None:
    state: dict[str, Any] = {}
    base: dict[str, Any] = {"id": "t", "client_message_id": "c"}
    event_to_messages({"type": "started", "payload": {"run": 1}}, state, base)
    event_to_messages(
        {"type": "draft", "payload": {"content": "Old text", "intent": "g", "urgency": "routine"}},
        state,
        base,
    )
    out = event_to_messages({"type": "started", "payload": {"run": 2}}, state, base)
    assert out[0] == {"type": "assistant_reset"}
    out = event_to_messages(
        {"type": "draft", "payload": {"content": "New", "intent": "g", "urgency": "routine"}},
        state,
        base,
    )
    assert [m["type"] for m in out] == ["assistant_start", "assistant_chunk"]


def test_an_epoch_bump_resets_the_viewer_before_the_replacement() -> None:
    state: dict[str, Any] = {}
    base: dict[str, Any] = {"id": "t", "client_message_id": "c"}
    event_to_messages(
        {"type": "draft", "payload": {"content": "Half.", "intent": "g", "urgency": "routine"}},
        state,
        base,
    )
    out = event_to_messages(
        {
            "type": "draft",
            "payload": {"content": "Fixed.", "intent": "g", "urgency": "routine", "epoch": 1},
        },
        state,
        base,
    )
    assert [m["type"] for m in out] == ["assistant_reset", "assistant_chunk"]
    assert PATIENT_ID  # imported fixture constant keeps the module's shared setup referenced


# -- backup model after text was shown -----------------------------------------------------------


def _reply_route(primary_script: list[Any], backup_script: list[Any], **kw: Any) -> ReplyRoute:
    primary = ResilientLlm(
        model="a",
        delegate=_Script(model="a", script=primary_script),
        timeout_seconds=kw.get("timeout", 5),
        stream_text=True,
    )
    backup = ResilientLlm(
        model="b",
        delegate=_Script(model="b", script=backup_script),
        timeout_seconds=kw.get("timeout", 5),
        stream_text=True,
    )
    return ReplyRoute(model="a", candidates=[primary, backup])


async def _collect(route: BaseLlm) -> tuple[list[LlmResponse], BaseException | None]:
    out: list[LlmResponse] = []
    try:
        async for response in route.generate_content_async(_request(), True):
            out.append(response)
    except Exception as error:
        return out, error
    return out, None


def _kinds(responses: list[LlmResponse]) -> list[str]:
    return [
        "reset" if (r.custom_metadata or {}).get(DRAFT_RESET_KEY) else r.content.parts[0].text
        for r in responses
    ]


@pytest.mark.asyncio
async def test_a_failure_after_text_withdraws_it_and_the_backup_answers_from_the_start() -> None:
    route = _reply_route(
        [_text("Half. ", partial=True), _StatusError(503)],
        [_text("Whole ", partial=True), _text("answer.")],
    )
    out, error = await _collect(route)
    assert error is None
    assert _kinds(out) == ["Half. ", "reset", "Whole ", "answer."]


@pytest.mark.asyncio
async def test_a_failure_before_any_text_still_falls_back_without_a_reset() -> None:
    out, error = await _collect(_reply_route([_StatusError(429)], [_text("From backup.")]))
    assert error is None and _kinds(out) == ["From backup."]


@pytest.mark.asyncio
async def test_when_the_backup_also_fails_the_error_reaches_the_runtime() -> None:
    route = _reply_route(
        [_text("Half. ", partial=True), _StatusError(503)],
        [_text("Other half. ", partial=True), _StatusError(500)],
    )
    out, error = await _collect(route)
    assert isinstance(error, _StatusError) and _kinds(out) == ["Half. ", "reset", "Other half. "]


@pytest.mark.asyncio
async def test_a_spent_budget_skips_the_backup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings, "reply_fallback_min_seconds", 10.0
    )  # more than is left of both budgets
    route = _reply_route([_text("Half. ", partial=True), _StatusError(503)], [_text("Never.")])
    backup = route.candidates[1].delegate
    out, error = await _collect(route)
    assert isinstance(error, _StatusError) and _kinds(out) == ["Half. "]
    assert backup.calls == 0  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_a_non_retriable_failure_never_reaches_the_backup() -> None:
    route = _reply_route([_text("Half. ", partial=True), ValueError("bad")], [_text("Never.")])
    out, error = await _collect(route)
    assert isinstance(error, ValueError) and _kinds(out) == ["Half. "]


@pytest.mark.asyncio
async def test_the_runtime_streams_the_backup_as_a_new_draft_and_saves_its_reply() -> None:
    from tests.unit.adk import test_chat_runtime as base

    class _Routed(base._Responder):
        async def generate_content_async(
            self, llm_request: Any, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            route = _reply_route(
                [_text("Half an answer. ", partial=True), _StatusError(503)],
                [_text("Backup ", partial=True), _text("Backup answer.")],
            )
            async for response in route.generate_content_async(llm_request, stream):
                yield response

    runtime = CareCoordinatorRuntime(runner=_build_runner(decision=base.STANDARD_DECISION))
    runtime.runner.agent.sub_agents[1].model = _Routed(model="stub-responder")
    events = await _turn(runtime, "when do I take it")
    kinds = [e["type"] for e in events]
    assert kinds.count("chunk_reset") == 1
    after = "".join(
        e["content"] for e in events[kinds.index("chunk_reset") :] if e["type"] == "chunk"
    )
    assert after == "Backup"
    complete = _first(events, "complete")
    assert complete["response_text"] == "Backup answer." and complete["fallback_used"] is False


# -- admission, labels ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_call_with_no_free_slot_is_shed_inside_the_admission_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "model_max_concurrency", 1)
    monkeypatch.setattr(settings, "model_admission_wait_seconds", 0.05)
    monkeypatch.setattr(settings, "model_min_start_interval_seconds", 0.0)
    async with model_slot("m-shed", "global"):
        started = time.monotonic()
        with pytest.raises(ModelAdmissionError) as raised:
            async with model_slot("m-shed", "global"):
                pytest.fail("must not be admitted")
        assert time.monotonic() - started < 0.5
        assert raised.value.status_code == 503
    async with model_slot("m-shed", "global"):  # the slot came back
        pass


@pytest.mark.asyncio
async def test_a_shed_call_moves_to_the_backup_and_is_counted_as_shed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "model_max_concurrency", 1)
    monkeypatch.setattr(settings, "model_admission_wait_seconds", 0.05)
    monkeypatch.setattr(settings, "model_min_start_interval_seconds", 0.0)
    primary = ResilientLlm(
        model="busy",
        delegate=_Script(model="busy", script=[_text("x")]),
        timeout_seconds=1,
        stream_text=True,
    )
    backup = ResilientLlm(
        model="free",
        delegate=_Script(model="free", script=[_text("from backup")]),
        timeout_seconds=1,
        stream_text=True,
    )
    route = ReplyRoute(model="busy", candidates=[primary, backup])
    async with model_slot("busy", settings.gemini_vertex_ai_location):
        out, error = await _collect(route)
    assert error is None and _kinds(out) == ["from backup"]
    assert classify_outcome(503, "admission_timeout") == "shed"


@pytest.mark.asyncio
async def test_background_attempts_carry_the_workload_that_asked() -> None:
    from app.core import model_traffic

    seen: list[str] = []
    original = model_traffic.availability.record
    model_traffic.availability.record = lambda **kw: seen.append(kw["workload"])  # type: ignore[method-assign]
    try:
        import time as _t

        model_traffic.record_attempt(
            model="m", endpoint="e", status=200, retry_count=0, cause="none", started=_t.monotonic()
        )
        with use_workload("extraction"):
            model_traffic.record_attempt(
                model="m",
                endpoint="e",
                status=200,
                retry_count=0,
                cause="none",
                started=_t.monotonic(),
            )
    finally:
        model_traffic.availability.record = original  # type: ignore[method-assign]
    assert seen == [] or seen[-1] == "extraction"
