"""Voice transport service for patient chat STT/TTS operations."""

from __future__ import annotations

import asyncio
import base64
import binascii
import inspect
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from deepgram.core.events import EventType
from supabase import Client

from app.clients.deepgram_client import (
    generate_speech_async,
    get_async_deepgram_client,
    transcribe_audio_bytes_async,
)
from app.clients.supabase import get_admin_client
from app.config import settings
from app.core.exceptions import ValidationError
from app.models.enums import Language, coerce_locale

SUPPORTED_AUDIO_MIME_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/mpeg",
}
DEFAULT_TTS_ENCODING = "mp3"
VOICE_BUCKET = "voice-messages"


@dataclass(frozen=True)
class VoiceTranscript:
    transcript: str
    language: Language
    model: str


@dataclass(frozen=True)
class VoiceAudio:
    audio: bytes
    language: Language
    model: str
    mime_type: str
    encoding: str
    audio_url: str | None = None
    signed_url: str | None = None


@dataclass(frozen=True)
class VoiceStoredAudio:
    path: str
    signed_url: str | None = None


@dataclass(frozen=True)
class VoiceStreamTranscript:
    transcript: str
    language: Language
    model: str
    is_final: bool


class DeepgramLiveTranscriptionSession:
    """Thin adapter around Deepgram live STT for browser-streamed audio chunks."""

    def __init__(self, *, language: Language, model: str) -> None:
        self.language = language
        self.model = model
        self._client = get_async_deepgram_client()
        self._context: Any | None = None
        self._connection: Any | None = None
        self._events: list[VoiceStreamTranscript] = []

    async def __aenter__(self) -> DeepgramLiveTranscriptionSession:
        self._context = self._client.listen.v1.connect(
            model=self.model,
            language=self.language.value,
            interim_results="true",
            smart_format="true",
        )
        self._connection = await self._context.__aenter__()
        self._connection.on(EventType.MESSAGE, self._handle_message)
        await _maybe_await(self._connection.start_listening())
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self._close_stream()
        if self._context is not None:
            await self._context.__aexit__(exc_type, exc, traceback)
            self._context = None

    async def send_audio(self, audio: bytes) -> list[VoiceStreamTranscript]:
        if self._connection is None:
            raise ValidationError("Voice stream is not ready")
        await _maybe_await(self._connection.send_media(audio))
        return self.pop_events()

    async def finish(self) -> list[VoiceStreamTranscript]:
        await self._close_stream()
        return self.pop_events()

    async def _close_stream(self) -> None:
        connection = self._connection
        self._connection = None
        if connection is not None:
            await _maybe_await(connection.send_close_stream())

    def pop_events(self) -> list[VoiceStreamTranscript]:
        events = self._events
        self._events = []
        return events

    def _handle_message(self, message: Any) -> None:
        transcript = _extract_deepgram_transcript(message).strip()
        if not transcript:
            return
        self._events.append(
            VoiceStreamTranscript(
                transcript=transcript,
                language=self.language,
                model=self.model,
                is_final=bool(
                    getattr(message, "is_final", False) or getattr(message, "speech_final", False)
                ),
            )
        )


class VoiceService:
    """Coordinates backend-owned speech-to-text and text-to-speech boundaries."""

    def __init__(self, db: Client | None = None) -> None:
        self.db = db

    async def transcribe_audio(
        self,
        *,
        audio_base64: str,
        mime_type: str,
        language: object = Language.EN,
    ) -> VoiceTranscript:
        audio_bytes = self._decode_audio_payload(audio_base64, mime_type)
        locale = coerce_locale(language)
        transcript = (
            await transcribe_audio_bytes_async(
                audio_bytes,
                model=settings.deepgram_stt_model,
                language=locale.value,
                smart_format=True,
            )
        ).strip()

        return VoiceTranscript(
            transcript=transcript,
            language=locale,
            model=settings.deepgram_stt_model,
        )

    def decode_audio_chunk(self, *, audio_base64: str, mime_type: str) -> bytes:
        return self._decode_audio_payload(audio_base64, mime_type)

    def create_streaming_transcription(
        self,
        *,
        language: object = Language.EN,
    ) -> DeepgramLiveTranscriptionSession:
        return DeepgramLiveTranscriptionSession(
            language=coerce_locale(language),
            model=settings.deepgram_stt_model,
        )

    async def synthesize_speech(
        self,
        *,
        text: str,
        language: object = Language.EN,
    ) -> VoiceAudio:
        normalized_text = " ".join(text.split())
        if not normalized_text:
            raise ValidationError("Text is required for speech synthesis")

        locale = coerce_locale(language)
        model = self._select_tts_model(locale)
        audio = await generate_speech_async(
            normalized_text,
            model=model,
            encoding=DEFAULT_TTS_ENCODING,
        )
        return VoiceAudio(
            audio=audio,
            language=locale,
            model=model,
            mime_type="audio/mpeg",
            encoding=DEFAULT_TTS_ENCODING,
        )

    async def persist_audio(
        self,
        *,
        patient_id: UUID,
        audio: bytes,
        mime_type: str,
        purpose: str,
        message_id: str | None = None,
    ) -> VoiceStoredAudio:
        if not audio:
            raise ValidationError("Audio payload is empty")

        extension = _audio_extension(mime_type)
        safe_purpose = "".join(ch for ch in purpose.lower() if ch.isalnum() or ch == "-") or "voice"
        filename = f"{int(time.time() * 1000)}-{message_id or uuid4()}-{safe_purpose}.{extension}"
        path = f"{patient_id}/{filename}"
        bucket = self._db.storage.from_(VOICE_BUCKET)
        await self._execute(
            bucket.upload(
                path,
                audio,
                {
                    "content-type": mime_type,
                    "cache-control": "3600",
                    "upsert": "true",
                },
            )
        )

        signed_url = await self._create_signed_url(path)
        return VoiceStoredAudio(path=path, signed_url=signed_url)

    async def persist_assistant_audio_for_message(
        self,
        *,
        patient_id: UUID,
        message_id: str | None,
        audio: VoiceAudio,
    ) -> VoiceAudio:
        if not message_id:
            return audio

        stored = await self.persist_audio(
            patient_id=patient_id,
            audio=audio.audio,
            mime_type=audio.mime_type,
            purpose="assistant",
            message_id=message_id,
        )
        await self._execute(
            self._db.table("chat_messages")
            .update({"audio_url": stored.path})
            .eq("id", message_id)
            .eq("patient_id", str(patient_id))
        )
        return VoiceAudio(
            audio=audio.audio,
            language=audio.language,
            model=audio.model,
            mime_type=audio.mime_type,
            encoding=audio.encoding,
            audio_url=stored.path,
            signed_url=stored.signed_url,
        )

    @staticmethod
    def encode_audio_base64(audio: bytes) -> str:
        return base64.b64encode(audio).decode("ascii")

    @staticmethod
    def _select_tts_model(language: Language) -> str:
        if language is Language.ES and settings.deepgram_tts_model_es:
            return settings.deepgram_tts_model_es
        return settings.deepgram_tts_model_en

    @staticmethod
    def _decode_audio_payload(audio_base64: str, mime_type: str) -> bytes:
        normalized_mime_type = mime_type.split(";", maxsplit=1)[0].strip().lower()
        if normalized_mime_type not in SUPPORTED_AUDIO_MIME_TYPES:
            raise ValidationError("Unsupported audio format")

        try:
            audio = base64.b64decode(audio_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValidationError("Audio payload must be valid base64") from exc

        if not audio:
            raise ValidationError("Audio payload is empty")
        if len(audio) > settings.voice_max_audio_bytes:
            raise ValidationError("Audio payload is too large")

        return audio

    @property
    def _db(self) -> Client:
        if self.db is None:
            self.db = get_admin_client()
        return self.db

    async def _create_signed_url(self, path: str) -> str | None:
        try:
            response = await self._execute(
                self._db.storage.from_(VOICE_BUCKET).create_signed_url(path, 3600)
            )
        except Exception:
            return None
        if isinstance(response, dict):
            signed = (
                response.get("signedURL") or response.get("signedUrl") or response.get("signed_url")
            )
            return str(signed) if signed else None
        signed = getattr(response, "signed_url", None) or getattr(response, "signedURL", None)
        return str(signed) if signed else None

    @staticmethod
    async def _execute(query: Any) -> Any:
        result = query
        execute = getattr(result, "execute", None)
        if callable(execute):
            return await asyncio.to_thread(execute)
        if callable(result):
            result = result()
        if inspect.isawaitable(result):
            return await result
        return result


def _audio_extension(mime_type: str) -> str:
    normalized = mime_type.split(";", maxsplit=1)[0].strip().lower()
    if normalized == "audio/mpeg":
        return "mp3"
    if normalized in {"audio/wav", "audio/x-wav"}:
        return "wav"
    if normalized == "audio/ogg":
        return "ogg"
    if normalized == "audio/mp4":
        return "mp4"
    return "webm"


async def _maybe_await(value: Any) -> None:
    if inspect.isawaitable(value):
        await value


def _extract_deepgram_transcript(message: Any) -> str:
    channel = getattr(message, "channel", None)
    alternatives = getattr(channel, "alternatives", None) or []
    if not alternatives:
        return ""
    return str(getattr(alternatives[0], "transcript", "") or "")
