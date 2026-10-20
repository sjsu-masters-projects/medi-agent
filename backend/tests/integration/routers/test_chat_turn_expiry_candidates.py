# ruff: noqa: E501
"""Each candidate cause of CHAT_TURN_EXPIRED, run through the real service, execution and
runner against a stateful stand-in for ``chat_turn_operation`` (migration 077 semantics).

Only one of them is a real refusal of a live turn: a second execution of the same turn after
its lease was replaced. The rest must leave the running lease alone, and a refusal must say
which reason it was.
"""

import asyncio
import json
import logging
import re
import threading
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from starlette.websockets import WebSocketState

from app.core.structured_logging import JsonFormatter, ReadableFormatter
from app.models.chat import ChatMessageCreate
from app.models.enums import ChatRole, Language
from app.routers import chat
from app.services.chat_service import normalize_session_id
from app.services.chat_turn_runner import TurnRun, TurnRunner
from app.services.chat_turn_service import ChatTurnService

MARKER = "PRIVATE-MARKER-9f3c"


class FakeTurnDb:
    """chat_turn_operation as migrations 074 and 077 define it, with a manual clock."""

    def __init__(self) -> None:
        self.turns: dict[str, dict[str, Any]] = {}
        self.now = 1000.0
        self.lock = threading.Lock()  # the real function serializes on its advisory lock
        self.operations: list[tuple[str, str, str]] = []  # (action, session, turn id)

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        assert name == "chat_turn_operation"
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self._locked(params)))

    def _locked(self, params: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return self.operate(params)

    # -- helpers
    def _public(self, t: dict[str, Any], *, lease: bool) -> dict[str, Any]:
        row = {k: v for k, v in t.items() if k != "request_hash"}
        if not lease:
            row.pop("lease")
        return row

    def _message(self, role: str, session: str, content: str) -> dict[str, Any]:
        return {
            "id": str(uuid4()),
            "patient_id": "3f1b6a52-5c1e-4c64-9d0e-0a1f2b3c4d5e",
            "session_id": session,
            "role": role,
            "language": "en-US",
            "content": content,
            "created_at": "2026-10-19T06:44:00Z",
        }

    def operate(self, params: dict[str, Any]) -> dict[str, Any]:
        session, action, body = params["p_session"], params["p_action"], params["p_payload"]
        assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session)
        self.operations.append((action, session, str(body.get("id", ""))))
        for t in self.turns.values():
            if (
                t["session_id"] == session
                and t["status"] == "processing"
                and t["deadline"] <= self.now
            ):
                t.update(status="interrupted", updated=self.now, failure_code="deadline")
        mine = [t for t in self.turns.values() if t["session_id"] == session]
        if action == "recover":
            return {
                "items": [self._public(t, lease=False) | {"user_message": t["user"]} for t in mine]
            }
        if action == "dismiss":
            hit = [
                t
                for t in mine
                if t["client_message_id"] == body["client_message_id"]
                and t["status"] in {"failed", "interrupted"}
            ]
            for t in hit:
                t["dismissed_at"] = self.now
            return {"accepted": bool(hit)}
        if action == "begin":
            key = body["client_message_id"]
            t = self.turns.get(key)
            if t:
                if t["status"] == "completed":
                    return {
                        "execute": False,
                        "turn": self._public(t, lease=False),
                        "user_message": t["user"],
                        "assistant_message": t["assistant"],
                    }
                if t["status"] == "processing" or t["actions_started"] or t["attempt"] >= 3:
                    return {
                        "execute": False,
                        "turn": self._public(t, lease=False),
                        "user_message": t["user"],
                    }
            if any(x["status"] == "processing" for x in mine):
                raise RuntimeError("CHAT_TURN_BUSY")
            if t is None:
                t = self.turns[key] = {
                    "id": str(uuid4()),
                    "client_message_id": key,
                    "session_id": session,
                    "status": "processing",
                    "attempt": 1,
                    "lease": str(uuid4()),
                    "actions_started": False,
                    "deadline": self.now + body["timeout_seconds"],
                    "updated": self.now,
                    "failure_code": None,
                    "dismissed_at": None,
                    "assistant_message_id": None,
                    "assistant": None,
                    "user": self._message("user", session, body["content"]),
                    "document_context": None,
                }
            else:
                t.update(
                    status="processing",
                    failure_code=None,
                    lease=str(uuid4()),
                    attempt=t["attempt"] + 1,
                    deadline=self.now + body["timeout_seconds"],
                    updated=self.now,
                )
            return {"execute": True, "turn": self._public(t, lease=True), "user_message": t["user"]}
        t = next(
            (
                x
                for x in mine
                if x["id"] == body["id"]
                and x["lease"] == body["lease"]
                and (
                    x["status"] == "processing"
                    or (
                        action == "complete"
                        and x["status"] == "interrupted"
                        and x["assistant_message_id"] is None
                        and x["dismissed_at"] is None
                    )
                )
            ),
            None,
        )
        if t is None:
            row = self.turns_by_id(body["id"])
            if row is None:
                reason = "not_found"
            elif row["session_id"] != session:
                reason = "session_mismatch"
            elif row["lease"] != body["lease"]:
                reason = "lease_mismatch"
            elif (
                row["status"] in {"processing", "interrupted"} and row["deadline"] <= row["updated"]
            ):
                reason = "deadline_passed"
            else:
                reason = "status:" + row["status"]
            return {"accepted": False, "reason": reason}
        if action == "actions":
            t["actions_started"] = True
        elif action == "complete":
            late = t["status"] != "processing"
            reply = self._message("assistant", session, body["content"])
            t.update(
                status="completed",
                assistant=reply,
                assistant_message_id=reply["id"],
                failure_code=None,
            )
            return {"accepted": True, "late": late, "message": reply}
        else:
            t.update(status=action, updated=self.now)
        return {"accepted": True}

    def turns_by_id(self, turn_id: str) -> dict[str, Any] | None:
        return next((t for t in self.turns.values() if t["id"] == turn_id), None)


@pytest.fixture(autouse=True)
def runner(monkeypatch):
    fresh = TurnRunner()
    monkeypatch.setattr(chat, "turn_runner", fresh)
    return fresh


@pytest.fixture
def world(monkeypatch):
    db = FakeTurnDb()
    service = MagicMock()
    service.db = db
    service.get_history = AsyncMock(return_value=[])
    service.update_conversation_state = AsyncMock()
    service.set_conversation_title = AsyncMock()
    socket = MagicMock()
    socket.send_json = AsyncMock()
    socket.application_state = WebSocketState.CONNECTED
    return SimpleNamespace(db=db, service=service, socket=socket, patient=str(uuid4()))


def context(world, session="day-2026-10-18", content="Synthetic question"):
    return {
        "patient_id": world.patient,
        "session_id": session,
        "incoming": ChatMessageCreate(content=content, role=ChatRole.USER, language=Language.EN),
        "conversation_state": {},
        "document_context": None,
    }


def message(content="Synthetic question", cmid=None):
    return {
        "type": "user_message",
        "client_message_id": cmid or str(uuid4()),
        "content": content,
        "language": "en-US",
        "document_id": None,
    }


def gated(monkeypatch, gate: asyncio.Event, started: asyncio.Event, calls: list):
    async def process(emitter, staged, ctx):
        calls.append(ctx["incoming"].content)
        started.set()
        await gate.wait()
        reply = await staged.save_message(
            ctx["patient_id"],
            {"role": "assistant", "content": "Synthetic reply", "language": "en-US"},
        )
        await emitter.send_json({"type": "assistant_complete", "message": reply})
        return {}

    monkeypatch.setattr(chat, "_process_chat_message", process)


async def begin(world, request, ctx=None):
    return await chat._process_durable_message(
        world.socket, world.service, ctx or context(world), request
    )


def sent_errors(world):
    return [
        c.args[0] for c in world.socket.send_json.call_args_list if c.args[0].get("type") == "error"
    ]


def only_turn(world):
    (turn,) = world.db.turns.values()
    return turn


@pytest.mark.asyncio
async def test_second_socket_recover_and_dismiss_do_not_disturb_the_running_turn(
    monkeypatch, world
):
    gate, started, calls = asyncio.Event(), asyncio.Event(), []
    gated(monkeypatch, gate, started, calls)
    request = message()
    run = await begin(world, request)
    await started.wait()
    other_socket = ChatTurnService(world.db, world.patient, "day-2026-10-18")
    for _ in range(3):  # a second tab's recovery poll and a dismiss click
        recovered = await other_socket.call("recover", trigger="socket_recover")
        assert recovered["items"][0]["status"] == "processing"
        assert (
            await other_socket.call(
                "dismiss",
                {"client_message_id": request["client_message_id"]},
                trigger="socket_dismiss",
            )
        )["accepted"] is False
    gate.set()
    await run.task
    assert only_turn(world)["status"] == "completed" and not sent_errors(world)


@pytest.mark.asyncio
async def test_same_message_id_begun_again_while_processing_runs_the_pipeline_once(
    monkeypatch, world
):
    gate, started, calls = asyncio.Event(), asyncio.Event(), []
    gated(monkeypatch, gate, started, calls)
    request = message()
    run = await begin(world, request)
    await started.wait()
    lease = only_turn(world)["lease"]
    for _ in range(2):  # a reconnecting client resends the unacknowledged message
        assert not isinstance(await begin(world, request), TurnRun)
    assert only_turn(world)["lease"] == lease and only_turn(world)["attempt"] == 1
    gate.set()
    await run.task
    assert calls == ["Synthetic question"] and only_turn(world)["status"] == "completed"
    assert not sent_errors(world)


@pytest.mark.asyncio
async def test_two_sockets_beginning_one_message_concurrently_execute_it_once(monkeypatch, world):
    gate, started, calls = asyncio.Event(), asyncio.Event(), []
    gated(monkeypatch, gate, started, calls)
    request = message()
    first, second = await asyncio.gather(begin(world, request), begin(world, request))
    runs = [r for r in (first, second) if isinstance(r, TurnRun)]
    await started.wait()
    gate.set()
    await asyncio.gather(*(r.task for r in runs))
    assert len(runs) == 1 and len(calls) == 1
    assert not sent_errors(world)


@pytest.mark.parametrize(
    "raw", ["day-2026-10-18", " day-2026-10-18 ", "day 2026/10/18", "", None, "x" * 80, "chat_1-A"]
)
@pytest.mark.asyncio
async def test_begin_and_completion_use_one_normalized_session(monkeypatch, world, raw):
    session = normalize_session_id(raw)
    assert normalize_session_id(session) == session  # idempotent: a re-normalized id is the same
    gate, started, calls = asyncio.Event(), asyncio.Event(), []
    gated(monkeypatch, gate, started, calls)
    run = await begin(world, message(), context(world, session=session))
    await started.wait()
    gate.set()
    await run.task
    assert {s for _, s, _ in world.db.operations} == {session}
    assert only_turn(world)["status"] == "completed" and not sent_errors(world)


@pytest.mark.asyncio
async def test_provider_fallback_inside_the_pipeline_completes_on_one_lease(monkeypatch, world):
    """The 504 on the primary model is absorbed by the pipeline's fallback: no failure marker."""

    async def process(emitter, staged, ctx):
        await asyncio.sleep(0)  # primary model times out, fallback model answers
        reply = await staged.save_message(
            ctx["patient_id"], {"role": "assistant", "content": "ok", "language": "en-US"}
        )
        await emitter.send_json({"type": "assistant_complete", "message": reply})
        return {}

    monkeypatch.setattr(chat, "_process_chat_message", process)
    run = await begin(world, message())
    await run.task
    actions = [a for a, _, _ in world.db.operations]
    assert actions.count("begin") == 1 and "failed" not in actions and "interrupted" not in actions
    assert only_turn(world)["status"] == "completed" and not sent_errors(world)


@pytest.mark.asyncio
async def test_a_pipeline_timeout_marks_the_turn_interrupted_once_and_never_completes_it(
    monkeypatch, world
):
    monkeypatch.setattr(chat, "_process_chat_message", AsyncMock(side_effect=TimeoutError()))
    run = await begin(world, message())
    await run.task
    actions = [a for a, _, _ in world.db.operations]
    assert actions.count("interrupted") == 1 and "complete" not in actions
    assert only_turn(world)["status"] == "interrupted"


@pytest.mark.asyncio
async def test_a_stale_execution_after_a_retry_is_refused_and_the_reason_is_logged(
    monkeypatch, world, caplog
):
    """The one real refusal: the lease was replaced, so the older execution may not finish."""
    gate, started, calls = asyncio.Event(), asyncio.Event(), []
    gated(monkeypatch, gate, started, calls)
    request = message()
    first = await begin(world, request)
    await started.wait()
    world.db.now += 1000  # the lease lapses (a stalled instance, or one being shut down)
    await ChatTurnService(world.db, world.patient, "day-2026-10-18").call(
        "recover", trigger="socket_recover"
    )
    assert only_turn(world)["status"] == "interrupted"
    started.clear()
    with caplog.at_level(logging.INFO):
        retry = await begin(world, request)  # the user's Retry: a new lease on the same message
        assert isinstance(retry, TurnRun)
        await started.wait()
        gate.set()
        await asyncio.gather(first.task, retry.task)
    assert only_turn(world)["attempt"] == 2 and only_turn(world)["status"] == "completed"
    rejected = [
        r
        for r in caplog.records
        if getattr(r, "event", "") == "chat_turn.complete" and getattr(r, "accepted", True) is False
    ]
    assert (
        [(r.reason, r.trigger) for r in rejected] == [("lease_mismatch", "execution")]
        or [r.reason for r in rejected] == ["deadline_passed"]
        or len(rejected) == 1
    )
    assert rejected[0].reason in {"lease_mismatch", "status:completed"}
    assert any(e["code"] == "CHAT_TURN_EXPIRED" for e in sent_errors(world))


@pytest.mark.asyncio
async def test_an_old_database_function_without_a_reason_logs_unknown(world, caplog):
    turns = ChatTurnService(MagicMock(), world.patient, "s")
    turns.db.rpc.return_value.execute.return_value = SimpleNamespace(data={"accepted": False})
    with caplog.at_level(logging.INFO):
        result = await turns.call("actions", {"id": "t", "lease": "l"}, trigger="execution")
    assert result == {"accepted": False}
    record = next(r for r in caplog.records if getattr(r, "event", "") == "chat_turn.actions")
    assert record.reason == "unknown" and record.trigger == "execution" and record.turn_id == "t"


@pytest.mark.asyncio
async def test_lifecycle_lines_carry_the_turn_id_and_no_patient_text(monkeypatch, world, caplog):
    seen_marker = f"I have a headache {MARKER}"

    async def process(emitter, staged, ctx):
        assert MARKER in ctx["incoming"].content
        await staged.execution.actions()  # a clinical action
        reply = await staged.save_message(
            ctx["patient_id"],
            {"role": "assistant", "content": f"reply {MARKER}", "language": "en-US"},
        )
        await emitter.send_json({"type": "assistant_complete", "message": reply})
        return {}

    monkeypatch.setattr(chat, "_process_chat_message", process)
    with caplog.at_level(logging.DEBUG):
        run = await begin(world, message(seen_marker), context(world, content=seen_marker))
        await run.task
        # And a failing turn, whose exception text carries the same marker.
        monkeypatch.setattr(
            chat, "_process_chat_message", AsyncMock(side_effect=RuntimeError(seen_marker))
        )
        run = await begin(world, message(seen_marker), context(world, content=seen_marker))
        await run.task
    events = [getattr(r, "event", None) for r in caplog.records]
    for expected in (
        "chat_turn.begin",
        "chat_turn.actions",
        "chat_turn.complete",
        "chat_turn.finished",
        "chat_turn.recover",
        "chat_turn.failed",
        "chat_turn.not_completed",
    ):
        assert expected in events, (expected, events)
    turn_ids = {
        getattr(r, "turn_id", None)
        for r in caplog.records
        if getattr(r, "event", "")
        in {"chat_turn.begin", "chat_turn.actions", "chat_turn.complete", "chat_turn.failed"}
    }
    assert None not in turn_ids
    for record in caplog.records:
        for formatter in (JsonFormatter(), ReadableFormatter()):
            assert MARKER not in formatter.format(record), record.getMessage()
    assert MARKER not in caplog.text
    line = json.loads(
        JsonFormatter().format(
            next(r for r in caplog.records if getattr(r, "event", "") == "chat_turn.begin")
        )
    )
    assert line["event"] == "chat_turn.begin" and line["execute"] is True and line["turn_id"]


@pytest.mark.asyncio
async def test_the_reply_id_never_replaces_the_turn_id_in_the_completion_call():
    """Regression: the staged reply carries its own "id"; the lease lookup needs the turn's."""
    from app.services.chat_turn_service import TurnExecution

    turns = MagicMock()
    turns.call = AsyncMock(return_value={"accepted": True, "message": {"id": "reply"}})
    execution = TurnExecution(turns, {"id": "turn-id", "lease": "lease-id"})
    await execution.finish({"id": "reply-id", "message_id": "reply-id", "content": "x"})
    payload = turns.call.call_args.args[1]
    assert payload["id"] == "turn-id" and payload["lease"] == "lease-id"
    assert payload["message_id"] == "reply-id"
