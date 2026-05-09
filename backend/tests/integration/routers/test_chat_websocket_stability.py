"""Load and stability tests for chat websocket event processing."""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.agents.triage.agent import TriageOutput
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser


def _make_stream_mock(output: TriageOutput):
    """Build a TriageAgent.process_stream mock that yields events matching `output`."""

    async def _mock_process_stream(_self, _agent_input):
        intent = output.intent or "general"
        urgency = output.urgency or "routine"
        route = output.route or ("symptom" if intent == "symptom" else "triage")
        yield {
            "type": "classification",
            "intent": intent,
            "urgency": urgency,
            "route": route,
            "escalation_required": bool(output.escalation_required),
            "classification_reason": "test mock",
        }
        text = output.response_text or ""
        if text:
            yield {"type": "chunk", "content": text}
        yield {"type": "complete", "response_text": text, "fallback_used": False}

    return _mock_process_stream


@pytest.fixture
def patient_id():
    return uuid4()


@pytest.fixture
def mock_supabase_db():
    db = MagicMock()
    table = MagicMock()
    db.table.return_value = table
    for method in ["select", "eq", "single", "insert", "order", "limit", "lt", "update"]:
        getattr(table, method).return_value = table
    table.execute.return_value = MagicMock(data=[])
    return db


@pytest.fixture
def override_db(mock_supabase_db):
    def _get_db_override():
        return mock_supabase_db

    app.dependency_overrides[get_db] = _get_db_override
    yield
    app.dependency_overrides.clear()


def _patch_chat_runtime(monkeypatch, patient_id):
    token_user = CurrentUser(id=patient_id, email="patient@test.com", role="patient")
    monkeypatch.setattr("app.routers.chat.decode_access_token", lambda _token: token_user)

    async def _get_history(_self, patient_id, limit=50, before=None):
        return []

    async def _get_context(_self, patient_id, document_id=None):
        return {
            "medications": [],
            "conditions": [],
            "recent_symptoms": [],
            "document": None,
        }

    async def _get_or_create_state(_self, patient_id, options):
        return {
            "patient_id": patient_id,
            "session_id": str(options.get("session_id") or "default"),
            "turn_count": 0,
            "last_intent": "general",
            "last_urgency": "routine",
            "last_route": "triage",
            "summary": "",
            "document_context": None,
        }

    async def _update_state(_self, patient_id, updates):
        return {
            "patient_id": patient_id,
            **updates,
        }

    async def _save_message(_self, patient_id, data):
        return {
            "id": str(uuid4()),
            "patient_id": patient_id,
            "content": str(data.get("content", "")),
            "role": str(data.get("role", "user")),
            "intent": data.get("intent"),
            "language": str(data.get("language", "en")),
            "audio_url": data.get("audio_url"),
            "created_at": datetime.now(UTC).isoformat(),
        }

    monkeypatch.setattr("app.routers.chat.ChatService.get_history", _get_history)
    monkeypatch.setattr("app.routers.chat.ChatService.get_context", _get_context)
    monkeypatch.setattr(
        "app.routers.chat.ChatService.get_or_create_conversation_state",
        _get_or_create_state,
    )
    monkeypatch.setattr("app.routers.chat.ChatService.update_conversation_state", _update_state)
    monkeypatch.setattr("app.routers.chat.ChatService.save_message", _save_message)


class TestChatWebSocketStability:
    def test_websocket_handles_high_message_volume_without_disconnect(
        self,
        client,
        override_db,
        patient_id,
        monkeypatch,
    ):
        _patch_chat_runtime(monkeypatch, patient_id)

        triage_output = TriageOutput(
            agent_id="triage-load-test",
            status="success",
            intent="general",
            urgency="routine",
            response_text="Acknowledged. Please continue.",
            escalation_required=False,
            route="triage",
        )

        async def _mock_triage_process(_self, _agent_input):
            return triage_output

        monkeypatch.setattr("app.routers.chat.TriageAgent.process", _mock_triage_process)
        monkeypatch.setattr(
            "app.routers.chat.TriageAgent.process_stream",
            _make_stream_mock(triage_output),
        )

        with client.websocket_connect(f"/ws/chat/{patient_id}?token=test-token") as websocket:
            history = websocket.receive_json()
            assert history["type"] == "chat_history"

            for index in range(40):
                websocket.send_json(
                    {
                        "type": "user_message",
                        "content": f"load-check message {index}",
                        "language": "en",
                    }
                )

                assert websocket.receive_json()["type"] == "user_message_saved"
                assert websocket.receive_json()["type"] == "assistant_start"

                while True:
                    event = websocket.receive_json()
                    if event["type"] == "assistant_complete":
                        break
                    assert event["type"] == "assistant_chunk"

            websocket.send_json({"type": "ping"})
            assert websocket.receive_json()["type"] == "pong"

    def test_websocket_ping_burst_remains_stable(
        self,
        client,
        override_db,
        patient_id,
        monkeypatch,
    ):
        _patch_chat_runtime(monkeypatch, patient_id)

        triage_output = TriageOutput(
            agent_id="triage-load-test",
            status="success",
            intent="general",
            urgency="routine",
            response_text="ok",
            escalation_required=False,
            route="triage",
        )

        async def _mock_triage_process(_self, _agent_input):
            return triage_output

        monkeypatch.setattr("app.routers.chat.TriageAgent.process", _mock_triage_process)
        monkeypatch.setattr(
            "app.routers.chat.TriageAgent.process_stream",
            _make_stream_mock(triage_output),
        )

        with client.websocket_connect(f"/ws/chat/{patient_id}?token=test-token") as websocket:
            assert websocket.receive_json()["type"] == "chat_history"

            for _ in range(120):
                websocket.send_json({"type": "ping"})
                assert websocket.receive_json()["type"] == "pong"

            websocket.send_text("{")
            malformed = websocket.receive_json()
            assert malformed["type"] == "error"
            assert malformed["code"] == "invalid_json"

            websocket.send_json({"type": "ping"})
            assert websocket.receive_json()["type"] == "pong"
