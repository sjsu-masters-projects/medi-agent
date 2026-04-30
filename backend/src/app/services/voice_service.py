"""Voice transport service for patient chat STT/TTS operations."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass

from app.clients.deepgram_client import generate_speech_async, transcribe_audio_bytes_async
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


class VoiceService:
    """Coordinates backend-owned speech-to-text and text-to-speech boundaries."""

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
