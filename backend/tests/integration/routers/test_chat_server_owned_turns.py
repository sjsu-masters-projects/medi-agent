# ruff: noqa: F811  (pytest fixtures are imported by name)
"""A Nora reply is owned by the server: a socket is only a viewer of it."""

import asyncio
from typing import Any

import pytest

from app.routers import chat
from app.services.chat_turn_runner import TurnRunner
from tests.integration.routers.test_chat_turn_recovery import turn_runtime  # noqa: F401


@pytest.fixture(autouse=True)
def runner(monkeypatch):
    fresh = TurnRunner()
    monkeypatch.setattr(chat, "turn_runner", fresh)
    return fresh


def _collector() -> tuple[list[dict[str, Any]], Any]:
    seen: list[dict[str, Any]] = []

    async def send(event: dict[str, Any]) -> bool:
        seen.append(event)
        return True

    return seen, send


def _gated_pipeline(monkeypatch, gate: asyncio.Event, started: asyncio.Event):
    async def process(emitter, staged, ctx):
        await emitter.send_json({"type": "assistant_start"})
        await emitter.send_json({"type": "assistant_chunk", "content": "Hello "})
        started.set()
        await gate.wait()
        await emitter.send_json({"type": "assistant_chunk", "content": "there"})
        message = await staged.save_message(
            ctx["patient_id"], {"role": "assistant", "content": "Hello there", "language": "en-US"}
        )
        await emitter.send_json({"type": "assistant_complete", "message": message})
        return {}

    monkeypatch.setattr(chat, "_process_chat_message", process)


def _actions(turns) -> list[str]:
    return [call.args[0] for call in turns.call.call_args_list]


@pytest.mark.asyncio
async def test_closing_the_socket_mid_reply_does_not_stop_the_turn(
    monkeypatch, runner, turn_runtime
):
    turns, service, socket, context, record, _ = turn_runtime
    gate, started = asyncio.Event(), asyncio.Event()
    _gated_pipeline(monkeypatch, gate, started)
    seen, send = _collector()
    key = (str(context["patient_id"]), context["session_id"])
    origin = runner.attach(key, send)
    run = await chat._process_durable_message(socket, service, context, {}, origin)
    await started.wait()
    origin.close()  # reload, phone lock, network blip
    assert not run.task.done()
    gate.set()
    await run.task
    actions = _actions(turns)
    assert "complete" in actions
    assert not {"failed", "interrupted"} & set(actions)
    assert not any(e.get("code") == "CHAT_TURN_EXPIRED" for e in seen)
    assert runner.running == 0


@pytest.mark.asyncio
async def test_a_second_socket_gets_the_draft_so_far_then_the_rest(
    monkeypatch, runner, turn_runtime
):
    _, service, socket, context, _, _ = turn_runtime
    gate, started = asyncio.Event(), asyncio.Event()
    _gated_pipeline(monkeypatch, gate, started)
    key = (str(context["patient_id"]), context["session_id"])
    first_seen, first_send = _collector()
    first = runner.attach(key, first_send)
    run = await chat._process_durable_message(socket, service, context, {}, first)
    await started.wait()
    second_seen, second_send = _collector()
    runner.attach(key, second_send)
    gate.set()
    await run.task
    types = [e["type"] for e in second_seen]
    assert types[:2] == ["chat_turn", "assistant_start"]
    assert second_seen[2] == {"type": "assistant_chunk", "content": "Hello "}
    assert [e.get("content") for e in second_seen if e["type"] == "assistant_chunk"] == [
        "Hello ",
        "there",
    ]
    assert "assistant_complete" in types
    assert types.count("assistant_complete") == 1


@pytest.mark.asyncio
async def test_another_instance_has_no_run_and_reads_the_saved_turn(runner, turn_runtime):
    turns, *_ = turn_runtime
    processing = {"items": [{"id": "t", "status": "processing"}]}
    turns.call.side_effect = None
    turns.call.return_value = processing
    seen, send = _collector()
    other_instance = TurnRunner()
    other_instance.attach(("p", "s"), send)
    await asyncio.sleep(0)
    assert seen == [] and other_instance.active(("p", "s")) is None
    assert (await turns.call("recover"))["items"][0]["status"] == "processing"


@pytest.mark.asyncio
async def test_registry_is_cleaned_up_after_the_turn(monkeypatch, runner, turn_runtime):
    _, service, socket, context, _, _ = turn_runtime
    gate, started = asyncio.Event(), asyncio.Event()
    gate.set()
    _gated_pipeline(monkeypatch, gate, started)
    key = (str(context["patient_id"]), context["session_id"])
    _, send = _collector()
    viewer = runner.attach(key, send)
    run = await chat._process_durable_message(socket, service, context, {}, viewer)
    await run.task
    assert runner._runs == {} and runner._by_key == {}
    viewer.close()
    assert runner._viewers == {}


@pytest.mark.asyncio
async def test_a_dead_socket_is_dropped_without_delaying_the_turn(
    monkeypatch, runner, turn_runtime
):
    turns, service, socket, context, _, _ = turn_runtime
    gate, started = asyncio.Event(), asyncio.Event()
    gate.set()
    _gated_pipeline(monkeypatch, gate, started)
    key = (str(context["patient_id"]), context["session_id"])

    async def dead(_: dict[str, Any]) -> bool:
        return False

    viewer = runner.attach(key, dead)
    run = await chat._process_durable_message(socket, service, context, {}, viewer)
    await run.task
    assert "complete" in _actions(turns) and viewer.closed and runner._viewers == {}


@pytest.mark.asyncio
async def test_shutdown_waits_for_running_turns(monkeypatch, runner, turn_runtime):
    turns, service, socket, context, _, _ = turn_runtime
    gate, started = asyncio.Event(), asyncio.Event()
    _gated_pipeline(monkeypatch, gate, started)
    run = await chat._process_durable_message(socket, service, context, {})
    await started.wait()
    asyncio.get_running_loop().call_later(0.05, gate.set)
    await runner.drain(2)
    assert run.task.done() and "complete" in _actions(turns) and runner.running == 0


@pytest.mark.asyncio
async def test_shutdown_leaves_a_stuck_turn_to_the_deadline(monkeypatch, runner, turn_runtime):
    turns, service, socket, context, _, _ = turn_runtime
    gate, started = asyncio.Event(), asyncio.Event()
    _gated_pipeline(monkeypatch, gate, started)
    run = await chat._process_durable_message(socket, service, context, {})
    await started.wait()
    await runner.drain(0.05)
    assert run.task.cancelled() or run.task.done()
    assert "complete" not in _actions(turns) and "interrupted" in _actions(turns)
    assert runner.running == 0


@pytest.mark.asyncio
async def test_a_real_model_error_still_fails_the_turn(monkeypatch, runner, turn_runtime):
    turns, service, socket, context, _, _ = turn_runtime
    seen, send = _collector()
    key = (str(context["patient_id"]), context["session_id"])
    viewer = runner.attach(key, send)

    async def boom(*_):
        raise RuntimeError("private provider detail")

    monkeypatch.setattr(chat, "_process_chat_message", boom)
    run = await chat._process_durable_message(socket, service, context, {}, viewer)
    await run.task
    assert "failed" in _actions(turns)
    errors = [e for e in seen if e["type"] == "error"]
    assert errors and "private" not in str(errors)
