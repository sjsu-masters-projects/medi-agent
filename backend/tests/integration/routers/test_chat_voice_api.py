"""Integration tests for patient voice websocket contract."""

import base64
from uuid import uuid4

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser
from app.models.enums import Language
from app.services.voice_service import VoiceAudio, VoiceTranscript


@pytest.fixture
def patient_id():
    return uuid4()


@pytest.fixture(autouse=True)
def _override_db():
    app.dependency_overrides[get_db] = lambda: object()
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clear_current_user_override():
    yield
    app.dependency_overrides.pop(get_current_user, None)


def test_voice_websocket_rejects_patient_id_mismatch(client, monkeypatch):
    token_user = CurrentUser(id=uuid4(), email="patient@test.com", role="patient")
    monkeypatch.setattr("app.routers.chat.decode_access_token", lambda _token: token_user)

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(f"/ws/voice/{uuid4()}?token=test-token"),
    ):
        pass


def test_voice_websocket_transcribes_final_audio(client, monkeypatch, patient_id):
    token_user = CurrentUser(id=patient_id, email="patient@test.com", role="patient")
    monkeypatch.setattr("app.routers.chat.decode_access_token", lambda _token: token_user)

    async def _mock_transcribe(self, *, audio_base64, mime_type, language):
        assert base64.b64decode(audio_base64) == b"audio"
        assert mime_type == "audio/webm"
        assert language == "es-MX"
        return VoiceTranscript(
            transcript="Me siento mareado",
            language=Language.ES,
            model="nova-3",
        )

    monkeypatch.setattr("app.routers.voice.VoiceService.transcribe_audio", _mock_transcribe)

    with client.websocket_connect(f"/ws/voice/{patient_id}?token=test-token") as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "voice_ready"

        websocket.send_json(
            {
                "type": "audio_final",
                "audio_base64": base64.b64encode(b"audio").decode("ascii"),
                "mime_type": "audio/webm",
                "language": "es-MX",
            }
        )

        response = websocket.receive_json()
        assert response == {
            "type": "transcript_final",
            "transcript": "Me siento mareado",
            "language": "es-MX",
            "model": "nova-3",
        }


def test_voice_websocket_generates_assistant_audio(client, monkeypatch, patient_id):
    token_user = CurrentUser(id=patient_id, email="patient@test.com", role="patient")
    monkeypatch.setattr("app.routers.chat.decode_access_token", lambda _token: token_user)

    async def _mock_synthesize(self, *, text, language):
        assert text == "Hydrate and call your care team if symptoms worsen."
        assert language == "en-US"
        return VoiceAudio(
            audio=b"mp3-bytes",
            language=Language.EN,
            model="aura-2-asteria-en",
            mime_type="audio/mpeg",
            encoding="mp3",
        )

    monkeypatch.setattr("app.routers.voice.VoiceService.synthesize_speech", _mock_synthesize)

    with client.websocket_connect(f"/ws/voice/{patient_id}?token=test-token") as websocket:
        assert websocket.receive_json()["type"] == "voice_ready"
        websocket.send_json(
            {
                "type": "tts_request",
                "text": "Hydrate and call your care team if symptoms worsen.",
                "language": "en-US",
            }
        )

        response = websocket.receive_json()
        assert response == {
            "type": "assistant_audio_ready",
            "audio_base64": base64.b64encode(b"mp3-bytes").decode("ascii"),
            "mime_type": "audio/mpeg",
            "encoding": "mp3",
            "language": "en-US",
            "model": "aura-2-asteria-en",
        }


def test_voice_websocket_returns_validation_errors(client, monkeypatch, patient_id):
    token_user = CurrentUser(id=patient_id, email="patient@test.com", role="patient")
    monkeypatch.setattr("app.routers.chat.decode_access_token", lambda _token: token_user)

    with client.websocket_connect(f"/ws/voice/{patient_id}?token=test-token") as websocket:
        assert websocket.receive_json()["type"] == "voice_ready"
        websocket.send_json(
            {
                "type": "audio_final",
                "audio_base64": "not-base64",
                "mime_type": "audio/webm",
            }
        )

        response = websocket.receive_json()
        assert response["type"] == "voice_error"
        assert response["code"] == "validation_error"
