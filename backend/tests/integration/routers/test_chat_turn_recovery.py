"""Durable websocket execution keeps saved replies independent of socket delivery."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from starlette.websockets import WebSocketState

from app.core.exceptions import ValidationError
from app.models.chat import ChatMessageCreate
from app.models.enums import ChatRole, Language
from app.routers import chat
from app.safety import TRIAGE_COPY
from app.services.chat_service import ChatService
from app.services.chat_turn_execution import TurnChatService
from app.services.chat_turn_service import ChatTurnService, TurnExecution, public_turn
from app.utils.localization import resolve_locale_resource


@pytest.fixture
def turn_runtime(monkeypatch):
    patient = str(uuid4())
    user = {
        "id": str(uuid4()),
        "patient_id": patient,
        "session_id": "chat-test",
        "role": "user",
        "language": "en-US",
        "content": "Synthetic question",
        "created_at": "2026-10-17T10:00:00Z",
    }
    record = {
        "id": str(uuid4()),
        "client_message_id": str(uuid4()),
        "lease": str(uuid4()),
        "status": "processing",
        "attempt": 1,
        "document_context": {"id": str(uuid4()), "summary": "Selected synthetic record"},
    }
    saved = {**user, "id": str(uuid4()), "role": "assistant", "content": "Synthetic reply"}
    turns = MagicMock()
    turns.begin = AsyncMock(return_value={"execute": True, "turn": record, "user_message": user})
    turns.call = AsyncMock(
        side_effect=lambda action, payload=None: {"items": []}
        if action == "recover"
        else {"accepted": True, "message": saved}
    )
    monkeypatch.setattr(chat, "ChatTurnService", lambda *_: turns)
    service = MagicMock()
    service.get_history = AsyncMock(return_value=[user])
    service.update_conversation_state = AsyncMock()
    service.set_conversation_title = AsyncMock()
    websocket = MagicMock()
    websocket.application_state = WebSocketState.CONNECTED
    websocket.send_json = AsyncMock()
    context = {
        "patient_id": patient,
        "session_id": "chat-test",
        "incoming": ChatMessageCreate(
            content=user["content"], role=ChatRole.USER, language=Language.EN
        ),
        "conversation_state": {},
        "document_context": {"id": "wrong-connection-document"},
    }
    return turns, service, websocket, context, record, saved


@pytest.mark.asyncio
async def test_completed_retry_replays_without_running_the_pipeline(monkeypatch, turn_runtime):
    turns, service, socket, context, record, saved = turn_runtime
    turns.begin.return_value.update(execute=False, assistant_message=saved)
    record["status"] = "completed"
    pipeline = AsyncMock()
    monkeypatch.setattr(chat, "_process_chat_message", pipeline)
    await chat._process_durable_message(socket, service, context, {})
    pipeline.assert_not_awaited()
    assert socket.send_json.call_args_list[-1].args[0]["message"]["id"] == saved["id"]


@pytest.mark.asyncio
async def test_disconnected_socket_does_not_discard_reply_and_uses_turn_document(
    monkeypatch, turn_runtime
):
    turns, service, socket, context, record, saved = turn_runtime
    socket.send_json.side_effect = RuntimeError(
        'Cannot call "send" once a close message has been sent.'
    )

    async def process(emitter, staged, ctx):
        assert ctx["document_context"] == record["document_context"]
        assert ctx["conversation_history"] == []
        message = await staged.save_message(
            ctx["patient_id"],
            {"role": "assistant", "content": "Synthetic reply", "language": "en-US"},
        )
        await emitter.send_json({"type": "assistant_complete", "message": message})
        return {}

    monkeypatch.setattr(chat, "_process_chat_message", process)
    await chat._process_durable_message(socket, service, context, {})
    assert any(call.args[0] == "complete" for call in turns.call.call_args_list)
    assert not any(call.args[0] in {"failed", "interrupted"} for call in turns.call.call_args_list)


@pytest.mark.asyncio
async def test_deadline_failure_is_persisted_and_recovers_without_exposing_provider_error(
    monkeypatch, turn_runtime
):
    turns, service, socket, context, _, _ = turn_runtime
    monkeypatch.setattr(
        chat,
        "_process_chat_message",
        AsyncMock(side_effect=TimeoutError("private provider detail")),
    )
    await chat._process_durable_message(socket, service, context, {})
    assert turns.call.call_args_list[0].args[0] == "interrupted"
    errors = [
        call.args[0] for call in socket.send_json.call_args_list if call.args[0]["type"] == "error"
    ]
    assert errors[0]["code"] == "CHAT_TURN_UNAVAILABLE"
    assert "private" not in str(errors)


@pytest.mark.asyncio
async def test_turn_request_identity_binds_language_content_and_document():
    service = ChatTurnService(MagicMock(), str(uuid4()), "chat-test")
    service.call = AsyncMock(return_value={})
    request = {
        "client_message_id": str(uuid4()),
        "content": "Synthetic",
        "language": "en-US",
        "document_id": None,
    }
    await service.begin(request, 30)
    first = service.call.call_args.args[1]["request_hash"]
    await service.begin(dict(request), 30)
    assert service.call.call_args.args[1]["request_hash"] == first
    await service.begin({**request, "document_id": str(uuid4())}, 30)
    assert service.call.call_args.args[1]["request_hash"] != first


def test_public_turn_never_exposes_snapshot_or_execution_lease():
    record = {
        "id": str(uuid4()),
        "lease": "private",
        "request_hash": "private",
        "document_context": {"id": "doc", "summary": "private"},
        "status": "interrupted",
        "attempt": 1,
        "actions_started": True,
    }
    result = public_turn(record)
    assert result["document_id"] == "doc" and not result["retryable"]
    assert "private" not in str(result)


@pytest.mark.asyncio
async def test_busy_claim_explains_an_existing_reply_and_recovers_it(turn_runtime):
    turns, service, socket, context, record, _ = turn_runtime
    turns.begin.side_effect = ValidationError("CHAT_TURN_BUSY")
    turns.call.side_effect = None
    turns.call.return_value = {
        "items": [{**record, "user_message": {"content": "Earlier synthetic question"}}]
    }
    await chat._process_durable_message(
        socket, service, context, {"client_message_id": str(uuid4())}
    )
    events = [call.args[0] for call in socket.send_json.call_args_list]
    assert events[0]["code"] == "CHAT_TURN_BUSY"
    assert "already in progress" in events[0]["message"]
    assert events[1]["turns"][0]["client_message_id"] == record["client_message_id"]


@pytest.mark.asyncio
async def test_document_execution_uses_the_existing_summary_cleanup():
    service = ChatTurnService(MagicMock(), str(uuid4()), "chat-test")
    service.call = AsyncMock(
        return_value={
            "turn": {
                "document_context": {
                    "id": "doc",
                    "context_version": "version",
                    "summary": "```# **Synthetic**\nsummary```",
                }
            }
        }
    )
    result = await service.begin(
        {
            "client_message_id": str(uuid4()),
            "content": "Synthetic",
            "document_id": str(uuid4()),
            "language": "en-US",
        },
        30,
    )
    assert result["turn"]["document_context"]["summary"] == "Synthetic\n\nsummary"
    assert result["turn"]["document_context"]["context_version"] == "version"


@pytest.mark.asyncio
async def test_expired_lease_cannot_start_a_clinical_write(monkeypatch, turn_runtime):
    turns, service, _, _, record, _ = turn_runtime
    turns.call.return_value = {"accepted": False}
    turns.call.side_effect = None
    write = AsyncMock()
    monkeypatch.setattr(ChatService, "save_symptom_report", write)
    staged = TurnChatService(service, TurnExecution(turns, record), {})
    with pytest.raises(ValidationError):
        await staged.save_symptom_report("patient", {"synthetic": True})
    write.assert_not_awaited()


@pytest.mark.parametrize("locale", ["en-US", "es-MX"])
@pytest.mark.parametrize("status", ["processing", "interrupted"])
@pytest.mark.parametrize(
    "text,key",
    [
        ("I have crushing chest pain", "emergency_response"),
        ("I want to kill myself", "mental_health_emergency_response"),
    ],
)
def test_reviewed_emergency_guidance_survives_deadline_and_reload(locale, status, text, key):
    record = {
        "status": status,
        "attempt": 1,
        "user_message": {"content": text, "language": locale},
    }
    assert (
        public_turn(record)["safety_guidance"] == resolve_locale_resource(locale, TRIAGE_COPY)[key]
    )


@pytest.mark.asyncio
async def test_turn_start_labels_the_conversation_before_the_reply(monkeypatch, turn_runtime):
    turns, service, socket, context, record, saved = turn_runtime
    monkeypatch.setattr(chat, "_process_chat_message", AsyncMock(return_value={}))
    await chat._process_durable_message(socket, service, context, {})
    service.set_conversation_title.assert_awaited_once_with(
        context["patient_id"], "chat-test", "Synthetic question"
    )


@pytest.mark.asyncio
async def test_title_failure_does_not_fail_the_turn(monkeypatch, turn_runtime):
    turns, service, socket, context, record, saved = turn_runtime
    service.set_conversation_title.side_effect = RuntimeError("down")
    pipeline = AsyncMock(return_value={})
    monkeypatch.setattr(chat, "_process_chat_message", pipeline)
    await chat._process_durable_message(socket, service, context, {})
    pipeline.assert_awaited_once()


@pytest.mark.asyncio
async def test_state_refresh_retries_after_a_concurrent_write_without_lowering_turn_count():
    service = MagicMock()
    calls = []

    async def update(patient, updates, expected_updated_at=None):
        calls.append((updates["turn_count"], expected_updated_at))
        if len(calls) == 1:
            raise chat.ConversationStateConflictError("changed")
        return {}

    service.update_conversation_state = update
    service.get_or_create_conversation_state = AsyncMock(
        return_value={"updated_at": "v2", "turn_count": 4}
    )
    assert await chat._refresh_conversation_state(service, "p", {"turn_count": 2}, "v1")
    assert calls == [(2, "v1"), (5, "v2")]


@pytest.mark.asyncio
async def test_state_refresh_failure_is_logged_with_its_category(caplog):
    service = MagicMock()
    service.update_conversation_state = AsyncMock(side_effect=RuntimeError("secret text"))
    with caplog.at_level("WARNING"):
        assert not await chat._refresh_conversation_state(service, "p", {"turn_count": 1}, None)
    assert "RuntimeError" in caplog.text
    assert "secret text" not in caplog.text


@pytest.mark.asyncio
async def test_turn_failure_category_is_in_the_log_message(monkeypatch, turn_runtime, caplog):
    turns, service, socket, context, _, _ = turn_runtime
    monkeypatch.setattr(chat, "_process_chat_message", AsyncMock(side_effect=KeyError("patient")))
    with caplog.at_level("WARNING"):
        await chat._process_durable_message(socket, service, context, {})
    assert "Durable chat turn did not complete: KeyError" in caplog.text
    assert "patient" not in caplog.text.replace("patient_id", "")
