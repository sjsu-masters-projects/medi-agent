# ruff: noqa: F811  (pytest fixtures are imported by name)
"""Socket-level recovery: handshake failures, dismissal, busy claims, caps and lost confirmations."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ExternalServiceError, ValidationError
from tests.integration.routers.chat_turn_helpers import run_turn
from tests.integration.routers.test_chat_document_focus import (  # noqa: F401
    _FakeChatStore,
    _opening_events,
    _types,
    connect,
    patient_id,
)


class _Turns:
    """A scripted ChatTurnService shared by every connection in the test."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self.recover: Any = {"items": []}
        self.begin_result: Any = None

    def factory(self, *_args: Any) -> MagicMock:
        turns = MagicMock()

        async def call(action: str, payload: dict[str, Any] | None = None, **_: Any) -> Any:
            self.calls.append((action, payload))
            if action == "recover":
                if isinstance(self.recover, Exception):
                    raise self.recover
                return self.recover
            return {"accepted": True}

        async def begin(request: dict[str, Any], timeout: int) -> Any:
            self.calls.append(("begin", request))
            if isinstance(self.begin_result, Exception):
                raise self.begin_result
            return self.begin_result

        turns.call = call
        turns.begin = begin
        return turns


@pytest.fixture
def turns(monkeypatch, patient_id):
    _FakeChatStore(str(patient_id), {}).install(monkeypatch)
    scripted = _Turns()
    monkeypatch.setattr("app.routers.chat.ChatTurnService", scripted.factory)
    return scripted


def test_failing_recover_during_the_handshake_sends_an_explicit_unavailable_error(connect, turns):
    turns.recover = ExternalServiceError("Chat", "down")
    with connect("turn_protocol=1") as socket:
        events: list[dict[str, Any]] = []
        while True:
            events.append(socket.receive_json())
            if events[-1]["type"] == "error":
                break
    assert events[-1]["code"] == "CHAT_STARTUP_UNAVAILABLE"
    assert "chat_turns" not in _types(events)


def test_dismiss_through_the_socket_dismisses_then_recovers(connect, turns):
    key = str(uuid4())
    with connect("turn_protocol=1") as socket:
        _opening_events(socket)
        socket.send_json({"type": "dismiss_turn", "client_message_id": key})
        assert _types([socket.receive_json(), socket.receive_json()]) == [
            "chat_history",
            "chat_turns",
        ]
        socket.send_json({"type": "dismiss_turn", "client_message_id": "not-a-uuid"})
        assert socket.receive_json()["code"] == "CHAT_TURN_INVALID"
    actions = [name for name, _ in turns.calls]
    assert actions.count("dismiss") == 1
    assert ("dismiss", {"client_message_id": key}) in turns.calls


def test_a_failing_recovery_request_keeps_the_socket_open(connect, turns):
    with connect("turn_protocol=1") as socket:
        _opening_events(socket)
        turns.recover = ExternalServiceError("Chat", "down")
        socket.send_json({"type": "recover_turns"})
        assert socket.receive_json()["code"] == "CHAT_TURN_UNAVAILABLE"
        turns.recover = {"items": []}
        socket.send_json({"type": "recover_turns"})
        assert _types([socket.receive_json(), socket.receive_json()]) == [
            "chat_history",
            "chat_turns",
        ]


def _message(client_message_id: str, **changes: Any) -> dict[str, Any]:
    return {
        "type": "user_message",
        "client_message_id": client_message_id,
        "content": "What does this mean?",
        "language": "en-US",
        "document_id": None,
        **changes,
    }


@pytest.mark.parametrize("code", ["CHAT_TURN_BUSY", "CHAT_DOCUMENT_CHANGED"])
def test_rejected_claims_report_their_code_and_recover(connect, turns, code):
    turns.begin_result = ValidationError(code)
    request_id = str(uuid4())
    with connect("turn_protocol=1") as socket:
        _opening_events(socket)
        socket.send_json(_message(request_id))
        error = socket.receive_json()
        assert error["code"] == code and error["client_message_id"] == request_id
        assert socket.receive_json()["type"] == "chat_turns"


def test_exhausted_attempts_are_reported_not_rerun(connect, turns):
    request_id = str(uuid4())
    record = {
        "id": str(uuid4()),
        "client_message_id": request_id,
        "status": "failed",
        "attempt": 3,
        "actions_started": False,
    }
    user = {
        "id": str(uuid4()),
        "patient_id": str(uuid4()),
        "role": "user",
        "content": "q",
        "language": "en-US",
        "created_at": "2026-10-17T10:00:00Z",
    }
    turns.begin_result = {"execute": False, "turn": record, "user_message": user}
    with connect("turn_protocol=1") as socket:
        _opening_events(socket)
        socket.send_json(_message(request_id))
        turn = socket.receive_json()
        assert turn["type"] == "chat_turn" and turn["turn"]["retryable"] is False
        assert socket.receive_json()["type"] == "user_message_saved"


def test_a_completed_turn_with_a_missing_reply_is_reported_as_unavailable(connect, turns):
    request_id = str(uuid4())
    record = {
        "id": str(uuid4()),
        "client_message_id": request_id,
        "status": "completed",
        "attempt": 1,
    }
    user = {
        "id": str(uuid4()),
        "patient_id": str(uuid4()),
        "role": "user",
        "content": "q",
        "language": "en-US",
        "created_at": "2026-10-17T10:00:00Z",
    }
    turns.begin_result = {
        "execute": False,
        "reply_unavailable": True,
        "turn": record,
        "user_message": user,
    }
    with connect("turn_protocol=1") as socket:
        _opening_events(socket)
        socket.send_json(_message(request_id))
        events = [socket.receive_json() for _ in range(3)]
    unavailable = events[-1]["turn"]
    assert unavailable["status"] == "failed" and unavailable["retryable"] is False
    assert unavailable["failure_code"] == "reply_unavailable"


@pytest.mark.asyncio
async def test_lost_completion_confirmation_delivers_the_committed_reply(monkeypatch):
    from app.routers import chat

    request_id = str(uuid4())
    committed = {"id": str(uuid4()), "client_message_id": request_id, "status": "completed"}
    turns = MagicMock()
    turns.begin = AsyncMock(
        return_value={
            "execute": True,
            "turn": {
                "id": "t",
                "client_message_id": request_id,
                "lease": "l",
                "status": "processing",
            },
            "user_message": {"id": str(uuid4()), "content": "q", "language": "en-US"},
        }
    )
    turns.call = AsyncMock(
        side_effect=lambda action, payload=None, **_: {"items": [committed]}
        if action == "recover"
        else {"accepted": True}
    )
    monkeypatch.setattr(chat, "ChatTurnService", lambda *_: turns)
    monkeypatch.setattr(
        chat,
        "_process_chat_message",
        AsyncMock(side_effect=ExternalServiceError("Chat", "timeout")),
    )
    reply = {
        "id": str(uuid4()),
        "patient_id": str(uuid4()),
        "role": "assistant",
        "content": "Saved",
        "language": "en-US",
        "created_at": "2026-10-17T10:00:00Z",
        "session_id": "s",
    }
    service = MagicMock()
    service.get_history = AsyncMock(return_value=[reply])
    service.set_conversation_title = AsyncMock()
    socket = MagicMock()
    socket.application_state = chat.WebSocketState.CONNECTED
    socket.send_json = AsyncMock()
    context = {
        "patient_id": str(uuid4()),
        "session_id": "s",
        "conversation_state": {},
        "incoming": chat.ChatMessageCreate(content="q", role=chat.ChatRole.USER, language="en-US"),
    }
    await run_turn(socket, service, context, {"client_message_id": request_id})
    sent = [call.args[0]["type"] for call in socket.send_json.call_args_list]
    assert sent.index("chat_history") < sent.index("chat_turns")


@pytest.mark.asyncio
async def test_disconnect_mid_stream_then_retry_after_reconnect(monkeypatch):
    """The first run is cut off (interrupted, one attempt); the retry is a new lease that completes."""
    from app.routers import chat

    request_id = str(uuid4())
    user = {"id": str(uuid4()), "content": "q", "language": "en-US"}

    def record(attempt: int) -> dict[str, Any]:
        return {
            "id": "t",
            "client_message_id": request_id,
            "lease": f"lease{attempt}",
            "status": "processing",
            "attempt": attempt,
        }

    saved = {
        "id": str(uuid4()),
        "patient_id": str(uuid4()),
        "role": "assistant",
        "content": "ok",
        "language": "en-US",
        "created_at": "2026-10-17T10:00:00Z",
    }
    turns = MagicMock()
    turns.begin = AsyncMock(
        side_effect=[
            {"execute": True, "turn": record(1), "user_message": user},
            {"execute": True, "turn": record(2), "user_message": user},
        ]
    )
    turns.call = AsyncMock(
        side_effect=lambda action, payload=None, **_: {"items": []}
        if action == "recover"
        else {"accepted": True, "message": saved}
    )
    monkeypatch.setattr(chat, "ChatTurnService", lambda *_: turns)
    service = MagicMock()
    service.get_history = AsyncMock(return_value=[])
    service.set_conversation_title = AsyncMock()
    service.update_conversation_state = AsyncMock()
    socket = MagicMock()
    socket.application_state = chat.WebSocketState.DISCONNECTED
    socket.send_json = AsyncMock()
    context = {
        "patient_id": str(uuid4()),
        "session_id": "s",
        "conversation_state": {},
        "incoming": chat.ChatMessageCreate(content="q", role=chat.ChatRole.USER, language="en-US"),
    }
    request = {"client_message_id": request_id}
    monkeypatch.setattr(chat, "_process_chat_message", AsyncMock(side_effect=TimeoutError()))
    await run_turn(socket, service, context, request)
    actions = [call.args[0] for call in turns.call.call_args_list]
    assert actions.count("interrupted") == 1 and turns.begin.await_count == 1

    async def finish(emitter, staged, ctx):
        message = await staged.save_message(
            ctx["patient_id"], {"role": "assistant", "content": "ok", "language": "en-US"}
        )
        await emitter.send_json({"type": "assistant_complete", "message": message})
        return {}

    monkeypatch.setattr(chat, "_process_chat_message", finish)
    await run_turn(socket, service, context, request)
    actions = [call.args[0] for call in turns.call.call_args_list]
    assert actions.count("complete") == 1 and turns.begin.await_count == 2
