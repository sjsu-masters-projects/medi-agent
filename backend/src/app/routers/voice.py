"""Patient voice websocket routes."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect, WebSocketException
from starlette import status

from app.config import settings
from app.core.exceptions import ValidationError
from app.models.enums import Language
from app.routers.chat import _authenticate_ws_patient
from app.services.voice_service import VoiceService

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

            if event_type == "tts_request":
                await _handle_tts_request(websocket, service, payload)
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
) -> None:
    try:
        audio = await service.synthesize_speech(
            text=str(payload.get("text", "")),
            language=payload.get("language", Language.EN),
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
