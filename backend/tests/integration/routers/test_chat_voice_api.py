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
from app.services.voice_service import (
    VoiceAudio,
    VoiceStoredAudio,
    VoiceStreamTranscript,
    VoiceTranscript,
)


@pytest.fixture
def patient_id():
    return uuid4()


@pytest.fixture(autouse=True)
def _override_db():
    app.dependency_overrides[get_db] = object
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

    async def _mock_persist_assistant(self, *, patient_id, message_id, audio):
        assert message_id == "assistant-1"
        return VoiceAudio(
            audio=audio.audio,
            language=audio.language,
            model=audio.model,
            mime_type=audio.mime_type,
            encoding=audio.encoding,
            audio_url=f"{patient_id}/assistant-1-assistant.mp3",
            signed_url="https://storage.example.com/assistant-1.mp3",
        )

    monkeypatch.setattr("app.routers.voice.VoiceService.synthesize_speech", _mock_synthesize)
    monkeypatch.setattr(
        "app.routers.voice.VoiceService.persist_assistant_audio_for_message",
        _mock_persist_assistant,
    )

    with client.websocket_connect(f"/ws/voice/{patient_id}?token=test-token") as websocket:
        assert websocket.receive_json()["type"] == "voice_ready"
        websocket.send_json(
            {
                "type": "tts_request",
                "message_id": "assistant-1",
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
            "audio_url": f"{patient_id}/assistant-1-assistant.mp3",
            "signed_url": "https://storage.example.com/assistant-1.mp3",
        }


def test_voice_websocket_streams_audio_chunks_and_persists_user_audio(
    client, monkeypatch, patient_id
):
    token_user = CurrentUser(id=patient_id, email="patient@test.com", role="patient")
    monkeypatch.setattr("app.routers.chat.decode_access_token", lambda _token: token_user)

    class FakeStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def send_audio(self, audio):
            assert audio == b"chunk"
            return [
                VoiceStreamTranscript(
                    transcript="I feel dizzy",
                    language=Language.EN,
                    model="nova-3",
                    is_final=False,
                )
            ]

        async def finish(self):
            return [
                VoiceStreamTranscript(
                    transcript="I feel dizzy",
                    language=Language.EN,
                    model="nova-3",
                    is_final=True,
                )
            ]

    def _mock_stream(self, *, language):
        assert language == "en-US"
        return FakeStream()

    async def _mock_persist(self, *, patient_id, audio, mime_type, purpose, message_id=None):
        assert audio == b"chunk"
        assert mime_type == "audio/webm"
        assert purpose == "user"
        assert message_id is None
        return VoiceStoredAudio(
            path=f"{patient_id}/voice-user.webm",
            signed_url="https://storage.example.com/voice-user.webm",
        )

    monkeypatch.setattr(
        "app.routers.voice.VoiceService.create_streaming_transcription",
        _mock_stream,
    )
    monkeypatch.setattr("app.routers.voice.VoiceService.persist_audio", _mock_persist)

    with client.websocket_connect(f"/ws/voice/{patient_id}?token=test-token") as websocket:
        assert websocket.receive_json()["type"] == "voice_ready"
        websocket.send_json(
            {
                "type": "audio_start",
                "mime_type": "audio/webm",
                "language": "en-US",
            }
        )
        assert websocket.receive_json() == {"type": "audio_stream_started"}

        websocket.send_json(
            {
                "type": "audio_chunk",
                "audio_base64": base64.b64encode(b"chunk").decode("ascii"),
            }
        )
        assert websocket.receive_json() == {
            "type": "transcript_partial",
            "transcript": "I feel dizzy",
            "language": "en-US",
            "model": "nova-3",
        }

        websocket.send_json({"type": "audio_stop"})
        assert websocket.receive_json() == {
            "type": "transcript_final",
            "transcript": "I feel dizzy",
            "language": "en-US",
            "model": "nova-3",
        }
        assert websocket.receive_json() == {
            "type": "audio_stream_complete",
            "audio_url": f"{patient_id}/voice-user.webm",
            "signed_url": "https://storage.example.com/voice-user.webm",
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
