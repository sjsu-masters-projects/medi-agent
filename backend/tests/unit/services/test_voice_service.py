"""Unit tests for backend voice transport service."""

import base64
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.models.enums import Language
from app.services.voice_service import VoiceAudio, VoiceService


@pytest.mark.asyncio
async def test_transcribe_audio_validates_and_calls_deepgram(monkeypatch):
    captured: dict[str, object] = {}

    async def _mock_transcribe(audio_data, model, language, smart_format):
        captured.update(
            {
                "audio_data": audio_data,
                "model": model,
                "language": language,
                "smart_format": smart_format,
            }
        )
        return "  hello care team  "

    monkeypatch.setattr(
        "app.services.voice_service.transcribe_audio_bytes_async",
        _mock_transcribe,
    )

    service = VoiceService()
    result = await service.transcribe_audio(
        audio_base64=base64.b64encode(b"audio").decode("ascii"),
        mime_type="audio/webm;codecs=opus",
        language="es",
    )

    assert result.transcript == "hello care team"
    assert result.language is Language.ES
    assert captured == {
        "audio_data": b"audio",
        "model": "nova-3",
        "language": "es-MX",
        "smart_format": True,
    }


@pytest.mark.asyncio
async def test_synthesize_speech_returns_encoded_audio_metadata(monkeypatch):
    captured: dict[str, object] = {}

    async def _mock_generate(text, model, encoding):
        captured.update({"text": text, "model": model, "encoding": encoding})
        return b"mp3-bytes"

    monkeypatch.setattr("app.services.voice_service.generate_speech_async", _mock_generate)

    result = await VoiceService().synthesize_speech(
        text="  Please take your medication.  ",
        language=Language.EN,
    )

    assert result.audio == b"mp3-bytes"
    assert result.mime_type == "audio/mpeg"
    assert result.encoding == "mp3"
    assert captured == {
        "text": "Please take your medication.",
        "model": "aura-2-asteria-en",
        "encoding": "mp3",
    }


def test_encode_audio_base64_is_ascii_safe():
    assert VoiceService.encode_audio_base64(b"abc") == "YWJj"


@pytest.mark.asyncio
async def test_persist_assistant_audio_uploads_and_updates_chat_message():
    patient_id = uuid4()
    calls: list[tuple[str, object]] = []

    class FakeTable:
        def update(self, payload):
            calls.append(("update", payload))
            return self

        def eq(self, key, value):
            calls.append((key, value))
            return self

        def execute(self):
            calls.append(("execute_table", None))
            return SimpleNamespace(data=[{"id": "message-1"}])

    class FakeBucket:
        def upload(self, path, audio, options):
            calls.append(("upload", (path, audio, options)))
            return SimpleNamespace(path=path)

        def create_signed_url(self, path, expires_in):
            calls.append(("signed_url", (path, expires_in)))
            return {"signedURL": f"https://storage.example.com/{path}"}

    class FakeStorage:
        def from_(self, bucket):
            calls.append(("bucket", bucket))
            return FakeBucket()

    class FakeDb:
        storage = FakeStorage()

        def table(self, name):
            calls.append(("table", name))
            return FakeTable()

    audio = await VoiceService(FakeDb()).persist_assistant_audio_for_message(
        patient_id=patient_id,
        message_id="message-1",
        audio=VoiceAudio(
            audio=b"mp3",
            language=Language.EN,
            model="aura-2-asteria-en",
            mime_type="audio/mpeg",
            encoding="mp3",
        ),
    )

    assert audio.audio_url is not None
    assert audio.signed_url is not None
    assert ("bucket", "voice-messages") in calls
    assert ("table", "chat_messages") in calls
    assert ("id", "message-1") in calls
    assert ("patient_id", str(patient_id)) in calls


@pytest.mark.asyncio
async def test_rejects_unsupported_audio_mime_type():
    with pytest.raises(ValidationError, match="Unsupported audio format"):
        await VoiceService().transcribe_audio(
            audio_base64=base64.b64encode(b"audio").decode("ascii"),
            mime_type="application/octet-stream",
            language="en-US",
        )


@pytest.mark.asyncio
async def test_rejects_invalid_audio_base64():
    with pytest.raises(ValidationError, match="valid base64"):
        await VoiceService().transcribe_audio(
            audio_base64="not-base64",
            mime_type="audio/webm",
            language="en-US",
        )


@pytest.mark.asyncio
async def test_rejects_empty_tts_text():
    with pytest.raises(ValidationError, match="Text is required"):
        await VoiceService().synthesize_speech(text="   ", language="en-US")
