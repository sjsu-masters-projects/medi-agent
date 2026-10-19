"""One patient voice websocket: live speech to text, streaming text to speech, barge-in.

The router receives frames and events and hands them here. Everything this connection
starts (the Deepgram live session, speech streams, their start-up tasks) is tracked and is
closed by ``close()``, which the router calls on every exit path, so a dropped socket or an
error can never leave a provider connection streaming (OPS-006 rules 11, 16).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from app.config import settings
from app.core.structured_logging import log_event
from app.models.enums import Language
from app.services.voice_live import (
    STOP_DRAIN_SECONDS,
    Connector,
    LiveSttSession,
    SpeechStream,
    deepgram_live_connector,
    deepgram_speak_connector,
)

logger = logging.getLogger(__name__)

_SPEECH_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CLIENT_STATES = {"listening", "thinking", "speaking", "paused"}
Send = Callable[[dict[str, Any]], Awaitable[None]]


def live_voice_available() -> bool:
    return bool(settings.deepgram_api_key and settings.voice_live_enabled)


def stream_speech_available() -> bool:
    return bool(settings.deepgram_api_key and settings.voice_tts_stream_enabled)


def voice_limits() -> dict[str, Any]:
    """What the portal needs to know about the bounds, so it can explain them."""
    return {
        "live_stt_supported": live_voice_available(),
        "tts_stream_supported": stream_speech_available(),
        "sample_rate": settings.voice_live_sample_rate,
        "tts_sample_rate": settings.voice_tts_sample_rate,
        "max_frame_bytes": settings.voice_live_max_frame_bytes,
        "max_session_seconds": settings.voice_live_max_session_seconds,
        "idle_timeout_seconds": settings.voice_live_idle_timeout_seconds,
        "max_utterance_seconds": settings.voice_live_max_utterance_seconds,
    }


class VoiceConnection:
    def __init__(
        self,
        send: Send,
        *,
        live_connector: Connector = deepgram_live_connector,
        speak_connector: Connector = deepgram_speak_connector,
    ) -> None:
        self._send = send
        self._live_connector = live_connector
        self._speak_connector = speak_connector
        self._send_lock = asyncio.Lock()
        self._live: LiveSttSession | None = None
        self._starting_live = False
        self._speech: SpeechStream | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._closed = False
        self.socket_gone = False

    async def emit(self, event: dict[str, Any]) -> None:
        """Serialized sends: the live relay, speech streams and the router share one socket."""
        if self._closed or self.socket_gone:
            return
        async with self._send_lock:
            try:
                await self._send(event)
            except Exception:
                self.socket_gone = True

    def _spawn(self, name: str, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.get_running_loop().create_task(coro, name=f"voice-{name}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # -- the microphone ------------------------------------------------------------------

    async def start_live(self, payload: dict[str, Any]) -> None:
        if not live_voice_available():
            await self._error("voice_live_unavailable", "Voice mode is not available right now.")
            return
        if self._live is not None and self._live.active or self._starting_live:
            await self._error("voice_stream_active", "A voice session is already active")
            return
        self._starting_live = True
        session = LiveSttSession(
            emit=self.emit,
            connector=self._live_connector,
            language_hint=payload.get("language") or Language.EN,
            on_speech_started=self._barge_in,
        )
        try:
            await session.start()
        except Exception as exc:
            log_event(
                logger,
                "voice.live_unavailable",
                level=logging.WARNING,
                message="Live transcription could not start",
                outcome=type(exc).__name__,
            )
            await self._error("voice_live_unavailable", "Voice mode is not available right now.")
            return
        finally:
            self._starting_live = False
        if self._closed:
            await session.stop("socket_closed")
            return
        self._live = session
        await self.emit(
            {
                "type": "voice_session_started",
                "model": settings.deepgram_stt_model,
                "sample_rate": settings.voice_live_sample_rate,
            }
        )

    async def stop_live(self, reason: str = "client") -> None:
        live, self._live = self._live, None
        if live is not None:
            await live.stop(reason)

    async def _barge_in(self) -> None:
        speech = self._speech
        if speech is not None and not speech.finished and speech.interruptible:
            await speech.cancel("barge_in")

    async def frame(self, data: bytes) -> None:
        if len(data) > settings.voice_live_max_frame_bytes:
            await self._error("voice_frame_too_large", "Audio frame too large")
            return
        live = self._live
        if live is None or not live.active:
            return
        if not live.feed(data) and live.frames_dropped == 1:
            log_event(
                logger,
                "voice.backpressure",
                level=logging.WARNING,
                message="Audio frames are being shed",
                outcome="queue_full",
            )

    # -- speech --------------------------------------------------------------------------

    async def start_speech(self, payload: dict[str, Any]) -> None:
        speech_id = str(payload.get("speech_id") or "")
        if not _SPEECH_ID.fullmatch(speech_id):
            await self._error("validation_error", "A speech id is required")
            return
        if not stream_speech_available():
            await self.emit({"type": "tts_error", "speech_id": speech_id, "reason": "unavailable"})
            return
        previous, self._speech = self._speech, None
        if previous is not None and not previous.finished:
            await previous.cancel("replaced")
        stream = SpeechStream(
            speech_id=speech_id,
            language=payload.get("language") or Language.EN,
            emit=self.emit,
            connector=self._speak_connector,
            interruptible=payload.get("interruptible") is not False,
        )
        self._speech = stream

        async def open_stream() -> None:
            try:
                await stream.start()
            except Exception as exc:
                log_event(
                    logger,
                    "voice.tts_unavailable",
                    level=logging.WARNING,
                    message="Speech stream could not start",
                    speech_id=speech_id,
                    outcome=type(exc).__name__,
                )
                await self.emit({"type": "tts_error", "speech_id": speech_id, "reason": "connect"})

        self._spawn("tts-open", open_stream())

    def _current(self, payload: dict[str, Any]) -> SpeechStream | None:
        speech = self._speech
        if speech is None or speech.speech_id != str(payload.get("speech_id") or ""):
            return None  # a stale id (an old reply, already replaced) is ignored
        return speech

    async def speech_text(self, payload: dict[str, Any]) -> None:
        speech = self._current(payload)
        if speech is not None:
            speech.add_text(str(payload.get("text") or ""))

    async def speech_end(self, payload: dict[str, Any]) -> None:
        speech = self._current(payload)
        if speech is not None:
            speech.end_text()

    async def speech_cancel(self, payload: dict[str, Any]) -> None:
        speech = self._current(payload)
        if speech is not None:
            await speech.cancel("client")

    # -- events --------------------------------------------------------------------------

    async def handle_event(self, event_type: str, payload: dict[str, Any]) -> bool:
        """True when this connection owns the event type."""
        if event_type == "voice_session_start":
            await self.start_live(payload)
        elif event_type == "voice_session_stop":
            await self.stop_live("client")
        elif event_type == "voice_state":
            state = str(payload.get("state") or "")
            if state in _CLIENT_STATES and self._live is not None:
                self._live.client_state = state
                self._live.touch()
        elif event_type == "tts_stream_start":
            await self.start_speech(payload)
        elif event_type == "tts_text":
            await self.speech_text(payload)
        elif event_type == "tts_end":
            await self.speech_end(payload)
        elif event_type == "tts_cancel":
            await self.speech_cancel(payload)
        else:
            return False
        return True

    async def _error(self, code: str, message: str) -> None:
        await self.emit({"type": "voice_error", "code": code, "message": message})

    async def close(self) -> None:
        """Every exit path: stop the microphone relay, cancel speech, drain what was started."""
        if self._closed:
            return
        live, self._live = self._live, None
        speech, self._speech = self._speech, None
        # Stop emitting first: the client is gone or going, and no task may block on it.
        self._closed = True
        if live is not None:
            await live.stop("socket_closed")
        if speech is not None:
            await speech.close()
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            with contextlib.suppress(Exception):
                async with asyncio.timeout(STOP_DRAIN_SECONDS):
                    await asyncio.gather(*tasks, return_exceptions=True)
