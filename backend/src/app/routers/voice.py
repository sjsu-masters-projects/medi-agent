"""Patient voice websocket routes."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect, WebSocketException
from starlette import status

from app.adk.grounding import without_source_lines
from app.clients.deepgram_client import STT_LANGUAGE, transcribe_audio_bytes_async
from app.config import settings
from app.core.exceptions import ValidationError
from app.models.enums import Language
from app.routers.chat import _authenticate_ws_patient, negotiated_subprotocol
from app.services.voice_connection import VoiceConnection, voice_limits
from app.services.voice_service import VoiceService, VoiceStreamTranscript
from app.utils.localization import written_language

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

    await websocket.accept(subprotocol=negotiated_subprotocol(websocket))
    service = VoiceService()
    await websocket.send_json(
        {
            "type": "voice_ready",
            "stt_supported": bool(settings.deepgram_api_key),
            "tts_supported": bool(settings.deepgram_api_key),
            "max_audio_bytes": settings.voice_max_audio_bytes,
            **voice_limits(),
        }
    )
    connection = VoiceConnection(websocket.send_json)

    stream_active = False
    stream_private = False
    stream_audio_chunks: list[bytes] = []
    stream_language: object = Language.EN
    stream_mime_type = "audio/webm"

    try:
        while True:
            received = await _receive_voice_message(websocket)
            if received is None:
                continue
            if isinstance(received, bytes):
                # A microphone frame (16-bit PCM) for the live session.
                await connection.frame(received)
                continue
            payload = received

            event_type = str(payload.get("type", "")).strip()
            if event_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if await connection.handle_event(event_type, payload):
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
                stream_private = payload.get("private_intake") is True
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
                            transcript_text = (
                                await transcribe_audio_bytes_async(
                                    audio,
                                    model=settings.deepgram_stt_model,
                                    language=STT_LANGUAGE,
                                    smart_format=True,
                                )
                            ).strip()
                            # The spoken language, whatever the app is set to.
                            locale = written_language(transcript_text, stream_language)
                            # Length only: what a patient said never goes to the logs.
                            logger.info("Voice batch transcribe: %d chars", len(transcript_text))
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

                        if stream_private:
                            # Intake transcripts travel through the private answer API.
                            # Do not create an orphaned chat-audio object for a draft.
                            await websocket.send_json({"type": "audio_stream_complete"})
                            continue
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
                            logger.warning("Voice audio persistence failed: %s", exc)
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
    finally:
        # Every exit path closes the provider connections the session opened.
        await connection.close()


async def _receive_voice_message(websocket: WebSocket) -> dict[str, Any] | bytes | None:
    """A binary frame is microphone audio; a text frame is a JSON event."""
    message = await websocket.receive()
    if message.get("type") == "websocket.disconnect":
        raise WebSocketDisconnect(code=int(message.get("code") or 1000))
    if message.get("bytes") is not None:
        return bytes(message["bytes"])
    try:
        payload = json.loads(message.get("text") or "")
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
            # The written sources line is for reading, not for listening.
            text=without_source_lines(str(payload.get("text", ""))),
            language=payload.get("language", Language.EN),
        )
        if not audio.audio:
            # The voice chain fell through to the deterministic text provider: the reply
            # exists, the sound does not. Storing or sending an empty payload would put a
            # silent clip in front of a patient who asked to hear it, so this stays the
            # same failure they already see until the transport carries a text-only turn.
            logger.warning("Voice TTS unavailable; fallback path was %s", list(audio.fallback_path))
            await _send_voice_error(
                websocket,
                code="voice_processing_failed",
                message="Voice processing failed. Please try again or use text chat.",
            )
            return
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
