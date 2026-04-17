"""Integration tests for chat history API and websocket endpoint."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import status
from starlette.websockets import WebSocketDisconnect

from app.agents.triage.agent import TriageOutput
from app.core.exceptions import ValidationError
from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser


@pytest.fixture
def patient_id():
    return uuid4()


@pytest.fixture
def mock_supabase_db():
    db = MagicMock()
    table = MagicMock()
    db.table.return_value = table

    for method in ["select", "eq", "single", "insert", "order", "limit", "lt"]:
        getattr(table, method).return_value = table

    return db


@pytest.fixture
def override_db(mock_supabase_db):
    def _get_db_override():
        return mock_supabase_db

    app.dependency_overrides[get_db] = _get_db_override
    yield
    app.dependency_overrides.clear()


class TestGetChatHistory:
    def test_patient_can_read_own_history(self, client, override_db, mock_supabase_db, patient_id):
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id=patient_id,
            email="patient@test.com",
            role="patient",
        )
        mock_supabase_db.table().select().eq().order().limit().execute.return_value = MagicMock(
            data=[
                {
                    "id": str(uuid4()),
                    "patient_id": str(patient_id),
                    "content": "hello",
                    "role": "user",
                    "intent": None,
                    "language": "en",
                    "audio_url": None,
                    "created_at": "2026-04-16T11:00:00Z",
                }
            ]
        )

        response = client.get(f"/api/v1/chat/history/{patient_id}")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()) == 1
        app.dependency_overrides.clear()

    def test_patient_cannot_read_other_patient_history(
        self,
        client,
        override_db,
        patient_id,
    ):
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id=uuid4(),
            email="patient@test.com",
            role="patient",
        )

        response = client.get(f"/api/v1/chat/history/{patient_id}")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        app.dependency_overrides.clear()

    def test_assigned_clinician_can_read_history(self, client, override_db, mock_supabase_db, patient_id):
        clinician_id = uuid4()
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id=clinician_id,
            email="clinician@test.com",
            role="clinician",
            aal="aal2",
        )
        mock_supabase_db.table().select().eq().eq().eq().limit().execute.side_effect = [
            MagicMock(data=[{"id": str(uuid4())}]),
            MagicMock(
                data=[
                    {
                        "id": str(uuid4()),
                        "patient_id": str(patient_id),
                        "content": "chat record",
                        "role": "assistant",
                        "intent": "general",
                        "language": "en",
                        "audio_url": None,
                        "created_at": "2026-04-16T11:00:00Z",
                    }
                ]
            ),
        ]

        response = client.get(f"/api/v1/chat/history/{patient_id}")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()[0]["role"] == "assistant"
        app.dependency_overrides.clear()


class TestChatWebSocket:
    def test_rejects_websocket_when_patient_id_mismatch(self, client, override_db, monkeypatch):
        token_user = CurrentUser(id=uuid4(), email="patient@test.com", role="patient")
        monkeypatch.setattr("app.routers.chat.decode_access_token", lambda _token: token_user)

        with pytest.raises(WebSocketDisconnect), client.websocket_connect(
            f"/ws/chat/{uuid4()}?token=test-token"
        ):
            pass

    def test_websocket_message_flow_persists_user_and_assistant_messages(
        self,
        client,
        override_db,
        mock_supabase_db,
        patient_id,
        monkeypatch,
    ):
        token_user = CurrentUser(id=patient_id, email="patient@test.com", role="patient")
        monkeypatch.setattr("app.routers.chat.decode_access_token", lambda _token: token_user)

        async def _mock_triage_process(_self, _agent_input):
            return TriageOutput(
                agent_id="triage-test",
                status="success",
                intent="general",
                urgency="routine",
                response_text="Please stay hydrated and monitor your symptoms.",
                escalation_required=False,
            )

        monkeypatch.setattr("app.routers.chat.TriageAgent.process", _mock_triage_process)

        user_row = {
            "id": str(uuid4()),
            "patient_id": str(patient_id),
            "content": "I feel dizzy",
            "role": "user",
            "intent": None,
            "language": "en",
            "audio_url": None,
            "created_at": "2026-04-16T12:00:00Z",
        }
        assistant_row = {
            "id": str(uuid4()),
            "patient_id": str(patient_id),
            "content": "Please stay hydrated and monitor your symptoms.",
            "role": "assistant",
            "intent": "general",
            "language": "en",
            "audio_url": None,
            "created_at": "2026-04-16T12:00:01Z",
        }

        mock_supabase_db.table().execute.side_effect = [
            MagicMock(data=[]),
            MagicMock(data=[user_row]),
            MagicMock(data=[assistant_row]),
        ]

        with client.websocket_connect(f"/ws/chat/{patient_id}?token=test-token") as websocket:
            history_event = websocket.receive_json()
            assert history_event["type"] == "chat_history"

            websocket.send_json({"type": "user_message", "content": "I feel dizzy", "language": "en"})

            user_saved = websocket.receive_json()
            assert user_saved["type"] == "user_message_saved"
            assert user_saved["message"]["content"] == "I feel dizzy"

            assistant_start = websocket.receive_json()
            assert assistant_start["type"] == "assistant_start"
            assert assistant_start["intent"] == "general"

            assistant_complete = None
            for _ in range(10):
                event = websocket.receive_json()
                if event["type"] == "assistant_complete":
                    assistant_complete = event
                    break
                assert event["type"] == "assistant_chunk"

            assert assistant_complete is not None
            assert assistant_complete["type"] == "assistant_complete"
            assert assistant_complete["message"]["role"] == "assistant"

    def test_websocket_returns_error_for_unsupported_event(
        self,
        client,
        override_db,
        mock_supabase_db,
        patient_id,
        monkeypatch,
    ):
        token_user = CurrentUser(id=patient_id, email="patient@test.com", role="patient")
        monkeypatch.setattr("app.routers.chat.decode_access_token", lambda _token: token_user)
        mock_supabase_db.table().execute.side_effect = [MagicMock(data=[])]

        with client.websocket_connect(f"/ws/chat/{patient_id}?token=test-token") as websocket:
            history_event = websocket.receive_json()
            assert history_event["type"] == "chat_history"

            websocket.send_json({"type": "unknown_event"})
            error_event = websocket.receive_json()

            assert error_event["type"] == "error"
            assert error_event["code"] == "unsupported_event"

    def test_websocket_returns_validation_error_for_empty_message(
        self,
        client,
        override_db,
        mock_supabase_db,
        patient_id,
        monkeypatch,
    ):
        token_user = CurrentUser(id=patient_id, email="patient@test.com", role="patient")
        monkeypatch.setattr("app.routers.chat.decode_access_token", lambda _token: token_user)
        mock_supabase_db.table().execute.side_effect = [MagicMock(data=[])]

        with client.websocket_connect(f"/ws/chat/{patient_id}?token=test-token") as websocket:
            history_event = websocket.receive_json()
            assert history_event["type"] == "chat_history"

            websocket.send_json({"type": "user_message", "content": "", "language": "en"})
            error_event = websocket.receive_json()

            assert error_event["type"] == "error"
            assert error_event["code"] == "validation_error"

    def test_websocket_returns_invalid_json_error_for_malformed_payload(
        self,
        client,
        override_db,
        mock_supabase_db,
        patient_id,
        monkeypatch,
    ):
        token_user = CurrentUser(id=patient_id, email="patient@test.com", role="patient")
        monkeypatch.setattr("app.routers.chat.decode_access_token", lambda _token: token_user)
        mock_supabase_db.table().execute.side_effect = [MagicMock(data=[])]

        with client.websocket_connect(f"/ws/chat/{patient_id}?token=test-token") as websocket:
            history_event = websocket.receive_json()
            assert history_event["type"] == "chat_history"

            websocket.send_text("not-json")
            error_event = websocket.receive_json()

            assert error_event["type"] == "error"
            assert error_event["code"] == "invalid_json"

            websocket.send_json({"type": "ping"})
            assert websocket.receive_json()["type"] == "pong"

    def test_websocket_returns_validation_error_for_non_object_payload(
        self,
        client,
        override_db,
        mock_supabase_db,
        patient_id,
        monkeypatch,
    ):
        token_user = CurrentUser(id=patient_id, email="patient@test.com", role="patient")
        monkeypatch.setattr("app.routers.chat.decode_access_token", lambda _token: token_user)
        mock_supabase_db.table().execute.side_effect = [MagicMock(data=[])]

        with client.websocket_connect(f"/ws/chat/{patient_id}?token=test-token") as websocket:
            assert websocket.receive_json()["type"] == "chat_history"

            websocket.send_json(["user_message", "hi"])
            error_event = websocket.receive_json()

            assert error_event["type"] == "error"
            assert error_event["code"] == "validation_error"
            assert "JSON object" in error_event["message"]

    def test_websocket_emits_escalation_recommended_event(
        self,
        client,
        override_db,
        mock_supabase_db,
        patient_id,
        monkeypatch,
    ):
        token_user = CurrentUser(id=patient_id, email="patient@test.com", role="patient")
        monkeypatch.setattr("app.routers.chat.decode_access_token", lambda _token: token_user)

        async def _mock_triage_process(_self, _agent_input):
            return TriageOutput(
                agent_id="triage-test",
                status="success",
                intent="symptom",
                urgency="urgent",
                response_text="Please contact your care team today for urgent review.",
                escalation_required=True,
            )

        monkeypatch.setattr("app.routers.chat.TriageAgent.process", _mock_triage_process)

        user_row = {
            "id": str(uuid4()),
            "patient_id": str(patient_id),
            "content": "I have severe dizziness",
            "role": "user",
            "intent": None,
            "language": "en",
            "audio_url": None,
            "created_at": "2026-04-16T12:00:00Z",
        }
        assistant_row = {
            "id": str(uuid4()),
            "patient_id": str(patient_id),
            "content": "Please contact your care team today for urgent review.",
            "role": "assistant",
            "intent": "symptom",
            "language": "en",
            "audio_url": None,
            "created_at": "2026-04-16T12:00:01Z",
        }
        mock_supabase_db.table().execute.side_effect = [
            MagicMock(data=[]),
            MagicMock(data=[user_row]),
            MagicMock(data=[assistant_row]),
        ]

        with client.websocket_connect(f"/ws/chat/{patient_id}?token=test-token") as websocket:
            history_event = websocket.receive_json()
            assert history_event["type"] == "chat_history"

            websocket.send_json(
                {
                    "type": "user_message",
                    "content": "I have severe dizziness",
                    "language": "en",
                }
            )

            assert websocket.receive_json()["type"] == "user_message_saved"

            assistant_start = websocket.receive_json()
            assert assistant_start["type"] == "assistant_start"
            assert assistant_start["urgency"] == "urgent"

            assistant_complete = None
            for _ in range(10):
                event = websocket.receive_json()
                if event["type"] == "assistant_complete":
                    assistant_complete = event
                    break
                assert event["type"] == "assistant_chunk"

            assert assistant_complete is not None
            assert assistant_complete["escalation_required"] is True
            assert assistant_complete["intent"] == "symptom"

            escalation_event = websocket.receive_json()
            assert escalation_event["type"] == "escalation_recommended"

    def test_websocket_returns_validation_error_when_service_raises(
        self,
        client,
        override_db,
        mock_supabase_db,
        patient_id,
        monkeypatch,
    ):
        token_user = CurrentUser(id=patient_id, email="patient@test.com", role="patient")
        monkeypatch.setattr("app.routers.chat.decode_access_token", lambda _token: token_user)
        mock_supabase_db.table().execute.side_effect = [MagicMock(data=[])]

        async def _raise_validation(_self, **_kwargs):
            raise ValidationError("Message rejected")

        monkeypatch.setattr("app.routers.chat.ChatService.save_message", _raise_validation)

        with client.websocket_connect(f"/ws/chat/{patient_id}?token=test-token") as websocket:
            assert websocket.receive_json()["type"] == "chat_history"

            websocket.send_json({"type": "user_message", "content": "hello", "language": "en"})
            error_event = websocket.receive_json()

            assert error_event["type"] == "error"
            assert error_event["code"] == "validation_error"
            assert error_event["message"] == "Message rejected"

    def test_websocket_returns_server_error_when_service_crashes(
        self,
        client,
        override_db,
        mock_supabase_db,
        patient_id,
        monkeypatch,
    ):
        token_user = CurrentUser(id=patient_id, email="patient@test.com", role="patient")
        monkeypatch.setattr("app.routers.chat.decode_access_token", lambda _token: token_user)
        mock_supabase_db.table().execute.side_effect = [MagicMock(data=[])]

        async def _raise_runtime(_self, **_kwargs):
            raise RuntimeError("Database offline")

        monkeypatch.setattr("app.routers.chat.ChatService.save_message", _raise_runtime)

        with client.websocket_connect(f"/ws/chat/{patient_id}?token=test-token") as websocket:
            assert websocket.receive_json()["type"] == "chat_history"

            websocket.send_json({"type": "user_message", "content": "hello", "language": "en"})
            error_event = websocket.receive_json()

            assert error_event["type"] == "error"
            assert error_event["code"] == "server_error"

            with pytest.raises(WebSocketDisconnect) as disconnect_info:
                websocket.receive_json()
            assert disconnect_info.value.code == status.WS_1011_INTERNAL_ERROR
