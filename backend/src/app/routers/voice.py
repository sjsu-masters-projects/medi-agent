"""Patient voice websocket routes."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect, WebSocketException
from starlette import status

from app.clients.deepgram_client import transcribe_audio_bytes_async
from app.config import settings
from app.core.exceptions import ValidationError
from app.models.enums import Language, coerce_locale
from app.routers.chat import _authenticate_ws_patient
from app.services.voice_service import VoiceService, VoiceStreamTranscript

logger = logging.getLogger(__name__)


async def voice_websocket_endpoint(
    websocket: WebSocket,
    patient_id: UUID,
) -> None:
    try:
        _authenticate_ws_patient(websocket, patient_id)
    except Exception as exc:
        if isinstance(exc, WebSocketException):
            raise
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=str(exc),
        ) from None

    await websocket.accept()
    service = VoiceService()
    await websocket.send_json(
        {
            "type": "voice_ready",
            "stt_supported": bool(settings.deepgram_api_key),
            "tts_supported": bool(settings.deepgram_api_key),
            "max_audio_bytes": settings.voice_max_audio_bytes,
        }
    )

    stream_active = False
    stream_audio_chunks: list[bytes] = []
    stream_language: object = Language.EN
    stream_mime_type = "audio/webm"

    try:
        while True:
            payload = await _receive_voice_payload(websocket)
            if payload is None:
                continue

            event_type = str(payload.get("type", "")).strip()
            if event_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if event_type == "audio_final":
                await _handle_audio_final(websocket, service, payload)
                continue

            if event_type == "audio_start":
                if stream_active:
                    await _send_voice_error(
                        websocket,
                        code="voice_stream_active",
                        message="A voice stream is already active",
                    )
                    continue
                stream_language = payload.get("language", Language.EN)
                stream_mime_type = str(payload.get("mime_type") or "audio/webm")
                stream_audio_chunks = []
                stream_active = True
                # Note: we deliberately skip Deepgram live streaming. Browser
                # MediaRecorder produces WebM-Opus fragments that the live API
                # can't decode (subsequent chunks lack the container header).
                # Buffering and batch-transcribing at audio_stop is reliable.
                await websocket.send_json({"type": "audio_stream_started"})
                continue

            if event_type == "audio_chunk":
                if not stream_active:
                    await _send_voice_error(
                        websocket,
                        code="voice_stream_inactive",
                        message="Start a voice stream before sending audio chunks",
                    )
                    continue
                try:
                    chunk = service.decode_audio_chunk(
                        audio_base64=str(payload.get("audio_base64", "")),
                        mime_type=stream_mime_type,
                    )
                    stream_audio_chunks.append(chunk)
                except ValidationError as exc:
                    await _send_voice_error(websocket, code="validation_error", message=exc.message)
                continue

            if event_type == "audio_stop":
                if not stream_active:
                    await _send_voice_error(
                        websocket,
                        code="voice_stream_inactive",
                        message="No active voice stream to stop",
                    )
                    continue
                try:
                    audio = b"".join(stream_audio_chunks)
                    logger.info(
                        "Voice audio_stop: chunks=%d, audio_bytes=%d, mime=%s",
                        len(stream_audio_chunks),
                        len(audio),
                        stream_mime_type,
                    )

                    if audio:
                        try:
                            locale = coerce_locale(stream_language)
                            transcript_text = (
                                await transcribe_audio_bytes_async(
                                    audio,
                                    model=settings.deepgram_stt_model,
                                    language=locale.value,
                                    smart_format=True,
                                )
                            ).strip()
                            logger.info(
                                "Voice batch transcribe: %r", transcript_text or "<empty>"
                            )
                            if transcript_text:
                                await websocket.send_json(
                                    {
                                        "type": "transcript_final",
                                        "transcript": transcript_text,
                                        "language": locale.value,
                                        "model": settings.deepgram_stt_model,
                                    }
                                )
                        except Exception as exc:
                            logger.warning(
                                "Voice batch transcription failed: %s", exc, exc_info=True
                            )

                        try:
                            stored = await service.persist_audio(
                                patient_id=patient_id,
                                audio=audio,
                                mime_type=stream_mime_type,
                                purpose="user",
                            )
                            await websocket.send_json(
                                {
                                    "type": "audio_stream_complete",
                                    "audio_url": stored.path,
                                    "signed_url": stored.signed_url,
                                }
                            )
                        except Exception as exc:
                            logger.warning(
                                "Voice audio persistence failed: %s", exc
                            )
                            await websocket.send_json({"type": "audio_stream_complete"})
                    else:
                        await websocket.send_json({"type": "audio_stream_complete"})
                finally:
                    stream_active = False
                    stream_audio_chunks = []
                continue

            if event_type == "tts_request":
                await _handle_tts_request(websocket, service, payload, patient_id=patient_id)
                continue

            await _send_voice_error(
                websocket,
                code="unsupported_event",
                message="Unsupported voice event type",
            )
    except WebSocketDisconnect:
        logger.info("Voice websocket disconnected")


async def _receive_voice_payload(websocket: WebSocket) -> dict[str, Any] | None:
    try:
        payload = await websocket.receive_json()
    except json.JSONDecodeError:
        await _send_voice_error(
            websocket,
            code="invalid_json",
            message="Malformed JSON payload",
        )
        return None

    if not isinstance(payload, dict):
        await _send_voice_error(
            websocket,
            code="validation_error",
            message="Voice payload must be a JSON object",
        )
        return None

    return payload


async def _handle_audio_final(
    websocket: WebSocket,
    service: VoiceService,
    payload: dict[str, Any],
) -> None:
    try:
        transcript = await service.transcribe_audio(
            audio_base64=str(payload.get("audio_base64", "")),
            mime_type=str(payload.get("mime_type", "")),
            language=payload.get("language", Language.EN),
        )
    except ValidationError as exc:
        await _send_voice_error(websocket, code="validation_error", message=exc.message)
        return
    except Exception as exc:
        logger.warning("Voice STT failed: %s", exc)
        await _send_voice_error(
            websocket,
            code="voice_processing_failed",
            message="Voice processing failed. Please try again or use text chat.",
        )
        return

    await websocket.send_json(
        {
            "type": "transcript_final",
            "transcript": transcript.transcript,
            "language": transcript.language.value,
            "model": transcript.model,
        }
    )


async def _handle_tts_request(
    websocket: WebSocket,
    service: VoiceService,
    payload: dict[str, Any],
    *,
    patient_id: UUID,
) -> None:
    try:
        audio = await service.synthesize_speech(
            text=str(payload.get("text", "")),
            language=payload.get("language", Language.EN),
        )
        audio = await service.persist_assistant_audio_for_message(
            patient_id=patient_id,
            message_id=str(payload.get("message_id") or "").strip() or None,
            audio=audio,
        )
    except ValidationError as exc:
        await _send_voice_error(websocket, code="validation_error", message=exc.message)
        return
    except Exception as exc:
        logger.warning("Voice TTS failed: %s", exc)
        await _send_voice_error(
            websocket,
            code="voice_processing_failed",
            message="Voice processing failed. Please try again or use text chat.",
        )
        return

    await websocket.send_json(
        {
            "type": "assistant_audio_ready",
            "audio_base64": service.encode_audio_base64(audio.audio),
            "mime_type": audio.mime_type,
            "encoding": audio.encoding,
            "language": audio.language.value,
            "model": audio.model,
            "audio_url": audio.audio_url,
            "signed_url": audio.signed_url,
        }
    )


async def _emit_stream_transcripts(
    websocket: WebSocket,
    transcripts: list[VoiceStreamTranscript],
) -> None:
    for transcript in transcripts:
        await websocket.send_json(
            {
                "type": "transcript_final" if transcript.is_final else "transcript_partial",
                "transcript": transcript.transcript,
                "language": transcript.language.value,
                "model": transcript.model,
            }
        )


async def _send_voice_error(websocket: WebSocket, *, code: str, message: str) -> None:
    await websocket.send_json(
        {
            "type": "voice_error",
            "code": code,
            "message": message,
        }
    )
