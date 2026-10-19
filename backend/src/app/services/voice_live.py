"""Live voice mode (VOICE-001): streaming speech to text and text to speech through Deepgram.

The pipeline is speech -> TEXT -> safety floors and Nora (the ordinary durable chat turn) ->
TEXT -> speech. Audio never reaches the model, the audit log or the records; the transcript
is a normal chat message and Nora's reply is read aloud from the same text the chat shows.

Two supervised sessions live here, both bounded and both closed on every path:

* ``LiveSttSession`` relays the browser's PCM frames to one Deepgram ``listen.v1`` websocket
  (nova-3 multilingual, interim results, endpointing, utterance-end and VAD events), folds the
  provider's results into one final utterance per end of speech and emits it exactly once.
* ``SpeechStream`` splits the reply into sentences as its text arrives, sends each to one
  Deepgram ``speak.v1`` websocket (Aura-2, linear16) and relays the audio in order.

Concurrency rules (OPS-006): nothing here is shared between connections; every queue is
bounded and sheds load instead of growing (14); every task is tracked, cancellation-safe and
drained (16); every provider call has a timeout (11); durations use the monotonic clock (18);
log lines carry the request id and never any transcript or reply text (24).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Any, Protocol, cast
from uuid import uuid4

from app.adk.grounding import without_source_lines
from app.config import settings
from app.core.structured_logging import log_event
from app.models.enums import Language, coerce_locale
from app.services.chat_turn_service import floor_guidance
from app.utils.localization import written_language

logger = logging.getLogger(__name__)

Emit = Callable[[dict[str, Any]], Awaitable[None]]
STOP_DRAIN_SECONDS = 3.0
WATCHDOG_TICK_SECONDS = 0.25
# Frames dropped in a row (queue full) before the session is shed rather than degraded.
OVERLOAD_DROPS = 50
# After asking Deepgram to finalize an over-long utterance, how long before it is closed here.
FORCE_FLUSH_GRACE_SECONDS = 1.0


class LiveConnection(Protocol):
    async def send_media(self, data: bytes) -> None: ...
    async def send_finalize(self) -> None: ...
    async def send_close_stream(self) -> None: ...
    def __aiter__(self) -> AsyncIterator[Any]: ...


class SpeakConnection(Protocol):
    async def send_text(self, text: str) -> None: ...
    async def send_flush(self) -> None: ...
    async def send_clear(self) -> None: ...
    async def send_close(self) -> None: ...
    def __aiter__(self) -> AsyncIterator[Any]: ...


Connector = Callable[[dict[str, Any]], AbstractAsyncContextManager[Any]]


def live_params() -> dict[str, Any]:
    """The Deepgram ``listen.v1`` parameters: every name here is verified against the SDK."""
    return {
        "model": settings.deepgram_stt_model,
        "language": settings.deepgram_live_language,
        "encoding": "linear16",
        "sample_rate": str(settings.voice_live_sample_rate),
        "channels": "1",
        "interim_results": "true",
        "smart_format": "true",
        "endpointing": str(settings.deepgram_endpointing_ms),
        "utterance_end_ms": str(settings.deepgram_utterance_end_ms),
        "vad_events": "true",
    }


def speak_params(language: object) -> dict[str, Any]:
    from app.services.voice_service import _tts_model_for

    return {
        "model": _tts_model_for(coerce_locale(language).value),
        "encoding": "linear16",
        "sample_rate": str(settings.voice_tts_sample_rate),
    }


def deepgram_live_connector(params: dict[str, Any]) -> AbstractAsyncContextManager[Any]:
    from app.clients.deepgram_client import get_async_deepgram_client

    return cast(
        AbstractAsyncContextManager[Any], get_async_deepgram_client().listen.v1.connect(**params)
    )


@contextlib.asynccontextmanager
async def deepgram_speak_connector(params: dict[str, Any]) -> AsyncIterator[Any]:
    from app.clients.deepgram_client import get_async_deepgram_client

    async with get_async_deepgram_client().speak.v1.connect(**params) as connection:
        yield _SpeakAdapter(connection)


class _SpeakAdapter:
    """Normalizes the SDK's typed speak messages to the tiny ``SpeakConnection`` surface."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    async def send_text(self, text: str) -> None:
        from deepgram.speak.v1.types import SpeakV1Text

        await self._connection.send_text(SpeakV1Text(text=text))

    async def send_flush(self) -> None:
        await self._connection.send_flush()

    async def send_clear(self) -> None:
        await self._connection.send_clear()

    async def send_close(self) -> None:
        await self._connection.send_close()

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._connection.__aiter__()  # type: ignore[no-any-return]


# -- end of speech: one final utterance per spoken turn ---------------------------------------


@dataclass
class Utterance:
    text: str
    language: str
    utterance_id: str = field(default_factory=lambda: str(uuid4()))


class UtteranceAssembler:
    """Folds Deepgram results into interim updates and one final utterance per end of speech.

    ``speech_final`` (endpointing) is the primary end of speech and ``UtteranceEnd`` the
    fallback, as Deepgram documents. Either may arrive for the same speech, so a flush
    empties the pending text and the second signal finds nothing to send: an utterance is
    emitted exactly once.
    """

    def __init__(self, *, max_chars: int, language_hint: object = Language.EN) -> None:
        self._max_chars = max_chars
        self._language_hint = language_hint
        self._finals: list[str] = []

    @property
    def pending(self) -> bool:
        return bool(self._finals)

    def _joined(self, tail: str = "") -> str:
        return " ".join(part for part in [*self._finals, tail.strip()] if part).strip()

    def on_result(self, text: str, *, is_final: bool, speech_final: bool) -> list[tuple[str, Any]]:
        text = text.strip()
        out: list[tuple[str, Any]] = []
        if is_final:
            if text:
                self._finals.append(text)
            if speech_final:
                utterance = self.flush()
                if utterance:
                    out.append(("final", utterance))
            elif self._finals:
                out.append(("interim", self._joined()[: self._max_chars]))
        elif text:
            out.append(("interim", self._joined(text)[: self._max_chars]))
        return out

    def flush(self) -> Utterance | None:
        text = self._joined()[: self._max_chars].strip()
        self._finals = []
        if not text:
            return None
        return Utterance(text=text, language=written_language(text, self._language_hint).value)


# -- live speech to text -----------------------------------------------------------------------


class LiveSttSession:
    """One browser microphone stream relayed to one Deepgram live connection."""

    def __init__(
        self,
        *,
        emit: Emit,
        connector: Connector = deepgram_live_connector,
        language_hint: object = Language.EN,
        on_speech_started: Callable[[], Awaitable[None]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._emit = emit
        self._connector = connector
        self._language_hint = language_hint
        self._on_speech_started = on_speech_started
        self._clock = clock
        self._assembler = UtteranceAssembler(
            max_chars=settings.voice_live_max_utterance_chars, language_hint=language_hint
        )
        self._audio: asyncio.Queue[bytes | None] = asyncio.Queue(
            maxsize=settings.voice_live_audio_queue_frames
        )
        self._stack = contextlib.AsyncExitStack()
        self._connection: Any = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._stopped = False
        self._consecutive_drops = 0
        self._started_at = 0.0
        self._last_activity = 0.0
        self._utterance_started: float | None = None
        self._force_flush_at: float | None = None
        self.client_state = "listening"
        self.frames_in = 0
        self.frames_dropped = 0
        self.utterances = 0
        self.end_reason: str | None = None

    @property
    def active(self) -> bool:
        return not self._stopped and self._connection is not None

    async def start(self) -> None:
        """Open the provider connection (bounded) and start the supervised tasks."""
        began = self._clock()
        try:
            async with asyncio.timeout(settings.voice_live_connect_timeout_seconds):
                self._connection = await self._stack.enter_async_context(
                    self._connector(live_params())
                )
        except BaseException:
            self._connection = None
            with contextlib.suppress(Exception):
                await self._stack.aclose()
            raise
        self._started_at = self._last_activity = self._clock()
        for name, coro in (
            ("send", self._pump_audio()),
            ("read", self._read_results()),
            ("watch", self._watchdog()),
        ):
            self._spawn(name, coro)
        log_event(
            logger,
            "voice.live_started",
            message="Live transcription connected",
            duration_ms=int((self._clock() - began) * 1000),
            model=settings.deepgram_stt_model,
        )

    def _spawn(self, name: str, coro: Awaitable[None]) -> None:
        async def run() -> None:
            try:
                await coro
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log_event(
                    logger,
                    "voice.live_task_failed",
                    level=logging.WARNING,
                    message="Live transcription task failed",
                    operation=name,
                    outcome=type(exc).__name__,
                )
                await self.stop("error")

        task = asyncio.get_running_loop().create_task(run(), name=f"voice-live-{name}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def feed(self, frame: bytes) -> bool:
        """Queue one microphone frame. False when it was shed (queue full): rule 14."""
        if self._stopped or self._connection is None:
            return False
        self.frames_in += 1
        try:
            self._audio.put_nowait(frame)
        except asyncio.QueueFull:
            self.frames_dropped += 1
            self._consecutive_drops += 1
            if self._consecutive_drops >= OVERLOAD_DROPS:
                self._spawn("overload", self.stop("overloaded"))
            return False
        self._consecutive_drops = 0
        return True

    def touch(self) -> None:
        self._last_activity = self._clock()

    async def _pump_audio(self) -> None:
        while True:
            frame = await self._audio.get()
            if frame is None:
                return
            async with asyncio.timeout(settings.voice_live_send_timeout_seconds):
                await self._connection.send_media(frame)

    async def _read_results(self) -> None:
        async for message in self._connection:
            if isinstance(message, bytes | bytearray):
                continue
            kind = getattr(message, "type", None)
            if kind == "SpeechStarted":
                self.touch()
                if self._utterance_started is None:
                    self._utterance_started = self._clock()
                if self._on_speech_started:
                    await self._on_speech_started()
                await self._emit({"type": "speech_started"})
            elif kind == "Results":
                await self._on_results(message)
            elif kind == "UtteranceEnd":
                await self._deliver(self._assembler.flush())
        # The provider closed the stream: a normal end after we asked, else a failure.
        if not self._stopped:
            await self.stop("provider_closed")

    async def _on_results(self, message: Any) -> None:
        try:
            transcript = str(message.channel.alternatives[0].transcript or "")
        except (AttributeError, IndexError):
            return
        self.touch()
        if transcript.strip() and self._utterance_started is None:
            self._utterance_started = self._clock()
        for kind, value in self._assembler.on_result(
            transcript,
            is_final=bool(getattr(message, "is_final", False)),
            speech_final=bool(getattr(message, "speech_final", False)),
        ):
            if kind == "interim":
                await self._emit(
                    {
                        "type": "transcript_partial",
                        "transcript": value,
                        "language": written_language(value, self._language_hint).value,
                    }
                )
            else:
                await self._deliver(value)

    async def _deliver(self, utterance: Utterance | None) -> None:
        self._utterance_started = None
        self._force_flush_at = None
        if utterance is None:
            return
        self.utterances += 1
        guidance = floor_guidance(utterance.text, utterance.language)
        log_event(
            logger,
            "voice.utterance",
            message="Utterance finalized",
            utterance_id=utterance.utterance_id,
            chars=len(utterance.text),
            outcome="safety_floor" if guidance else "final",
        )
        await self._emit(
            {
                "type": "utterance_final",
                "utterance_id": utterance.utterance_id,
                "transcript": utterance.text,
                "language": utterance.language,
                "model": settings.deepgram_stt_model,
                # The deterministic floor ran on this TEXT. The portal shows the guidance
                # and speaks it; the turn itself reaches the same floor again on the server.
                **({"safety_guidance": guidance} if guidance else {}),
            }
        )

    async def _watchdog(self) -> None:
        while not self._stopped:
            await asyncio.sleep(WATCHDOG_TICK_SECONDS)
            now = self._clock()
            if now - self._started_at >= settings.voice_live_max_session_seconds:
                await self.stop("max_session")
                return
            if (
                self.client_state == "listening"
                and self._utterance_started is None
                and now - self._last_activity >= settings.voice_live_idle_timeout_seconds
            ):
                await self.stop("idle_timeout")
                return
            if (
                self._utterance_started is not None
                and self._force_flush_at is None
                and now - self._utterance_started >= settings.voice_live_max_utterance_seconds
            ):
                # Someone is talking without a pause: ask the provider to finalize what it
                # has, then close the utterance ourselves shortly after.
                with contextlib.suppress(Exception):
                    async with asyncio.timeout(settings.voice_live_send_timeout_seconds):
                        await self._connection.send_finalize()
                self._force_flush_at = now + FORCE_FLUSH_GRACE_SECONDS
                log_event(
                    logger,
                    "voice.utterance_limit",
                    level=logging.WARNING,
                    message="Utterance reached the length limit",
                    outcome="forced_flush",
                )
            if self._force_flush_at is not None and now >= self._force_flush_at:
                await self._deliver(self._assembler.flush())

    async def stop(self, reason: str = "client") -> None:
        """Close the provider connection and drain every task. Idempotent; safe on any path."""
        if self._stopped:
            return
        self._stopped = True
        self.end_reason = reason
        current = asyncio.current_task()
        pending_utterance = self._assembler.flush() if reason == "client" else None
        for task in list(self._tasks):
            if task is not current:
                task.cancel()
        others = [task for task in self._tasks if task is not current]
        if others:
            with contextlib.suppress(Exception):
                async with asyncio.timeout(STOP_DRAIN_SECONDS):
                    await asyncio.gather(*others, return_exceptions=True)
        if self._connection is not None:
            with contextlib.suppress(Exception):
                async with asyncio.timeout(settings.voice_live_send_timeout_seconds):
                    await self._connection.send_close_stream()
        with contextlib.suppress(Exception):
            async with asyncio.timeout(STOP_DRAIN_SECONDS):
                await self._stack.aclose()
        self._connection = None
        log_event(
            logger,
            "voice.live_ended",
            message="Live transcription ended",
            outcome=reason,
            duration_ms=int((self._clock() - self._started_at) * 1000) if self._started_at else 0,
            frames=self.frames_in,
        )
        if pending_utterance:
            # Speech that had ended but not yet been reported when the patient stopped.
            with contextlib.suppress(Exception):
                await self._deliver(pending_utterance)
        with contextlib.suppress(Exception):
            await self._emit({"type": "voice_session_ended", "reason": reason})


# -- streaming text to speech ------------------------------------------------------------------

_ABBREVIATIONS = (
    "dr.",
    "dra.",
    "sr.",
    "sra.",
    "srta.",
    "mr.",
    "mrs.",
    "ms.",
    "vs.",
    "a.m.",
    "p.m.",
    "etc.",
    "ej.",
    "aprox.",
)
_BOUNDARY = re.compile(r"[.!?…]+[\"')\]]*\s+|\n+")
_LIST_NUMBER = re.compile(r"^\(?\d{1,2}[.)]$")
_SOURCE_START = re.compile(r"^\s*(sources?|fuentes?)\s*:", re.IGNORECASE)
_MARKUP = re.compile(r"[*_`#]+")


class SentenceChunker:
    """Turns streamed reply text into speakable sentences, in order.

    A sentence is held back until its end is seen, so the voice never starts a sentence it
    cannot finish. Abbreviations ("Dr.", "p.m.") and decimals ("98.6") do not end one.
    """

    def __init__(self, *, max_chars: int) -> None:
        self._max = max_chars
        self._buffer = ""

    def feed(self, delta: str) -> list[str]:
        self._buffer += delta
        return self._drain(final=False)

    def finish(self) -> list[str]:
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> list[str]:
        sentences: list[str] = []
        while True:
            end = self._next_end()
            if end is None:
                break
            sentences.append(self._buffer[:end])
            self._buffer = self._buffer[end:]
        if final:
            sentences.append(self._buffer)
            self._buffer = ""
        elif len(self._buffer) > self._max * 2:
            # A very long run with no sentence end: cut at the last comma or space.
            sentences.append(self._cut())
        spoken: list[str] = []
        for raw in sentences:
            for part in self._split_long(raw):
                cleaned = self._clean(part)
                if cleaned:
                    spoken.append(cleaned)
        return spoken

    def _next_end(self) -> int | None:
        for match in _BOUNDARY.finditer(self._buffer):
            head = self._buffer[: match.start() + 1].lower()
            token = head.rsplit(None, 1)[-1] if head.split() else head
            if match.group().strip().startswith(".") and (
                token in _ABBREVIATIONS or _LIST_NUMBER.match(token)
            ):
                continue
            return match.end()
        return None

    def _cut(self) -> str:
        window = self._buffer[: self._max]
        cut = max(window.rfind(", "), window.rfind("; "), window.rfind(" "))
        cut = cut + 1 if cut > 0 else self._max
        piece, self._buffer = self._buffer[:cut], self._buffer[cut:]
        return piece

    def _split_long(self, text: str) -> list[str]:
        if len(text) <= self._max:
            return [text]
        parts: list[str] = []
        rest = text
        while len(rest) > self._max:
            window = rest[: self._max]
            cut = max(window.rfind(", "), window.rfind("; "), window.rfind(" "))
            cut = cut + 1 if cut > 0 else self._max
            parts.append(rest[:cut])
            rest = rest[cut:]
        parts.append(rest)
        return parts

    @staticmethod
    def _clean(text: str) -> str:
        text = without_source_lines(text)
        if _SOURCE_START.match(text):
            return ""
        text = _MARKUP.sub("", text).replace("•", " ")
        return " ".join(text.split()).strip()


class SpeechStream:
    """One reply read aloud: sentences go to one Deepgram Speak connection, audio comes back."""

    def __init__(
        self,
        *,
        speech_id: str,
        language: object,
        emit: Emit,
        connector: Connector = deepgram_speak_connector,
        interruptible: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.speech_id = speech_id
        self.interruptible = interruptible
        self._language = coerce_locale(language)
        self._emit = emit
        self._connector = connector
        self._clock = clock
        self._chunker = SentenceChunker(max_chars=settings.voice_tts_sentence_max_chars)
        self._sentences: asyncio.Queue[str | None] = asyncio.Queue()
        self._stack = contextlib.AsyncExitStack()
        self._connection: Any = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._chars = 0
        self._seq = 0
        self._sentence_count = 0
        self._flushed = 0
        self._all_sent = asyncio.Event()
        self._done = asyncio.Event()
        self._closed = False
        self._truncated = False
        self._started_at = clock()
        self._first_audio_at: float | None = None
        self.language_decided = False

    @property
    def finished(self) -> bool:
        return self._closed

    async def start(self) -> None:
        began = self._clock()
        try:
            async with asyncio.timeout(settings.voice_tts_connect_timeout_seconds):
                raw = await self._stack.enter_async_context(
                    self._connector(speak_params(self._language))
                )
        except BaseException:
            with contextlib.suppress(Exception):
                await self._stack.aclose()
            self._closed = True
            raise
        self._connection = raw
        await self._emit(
            {
                "type": "tts_start",
                "speech_id": self.speech_id,
                "encoding": "linear16",
                "sample_rate": settings.voice_tts_sample_rate,
                "interruptible": self.interruptible,
            }
        )
        self._spawn("write", self._write())
        self._spawn("read", self._read())
        log_event(
            logger,
            "voice.tts_started",
            message="Speech stream connected",
            speech_id=self.speech_id,
            duration_ms=int((self._clock() - began) * 1000),
        )

    def _spawn(self, name: str, coro: Awaitable[None]) -> None:
        async def run() -> None:
            try:
                await coro
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._closed:
                    return  # the provider connection closing under a finished stream
                log_event(
                    logger,
                    "voice.tts_task_failed",
                    level=logging.WARNING,
                    message="Speech stream task failed",
                    speech_id=self.speech_id,
                    operation=name,
                    outcome=type(exc).__name__,
                )
                await self.fail("provider_error")

        task = asyncio.get_running_loop().create_task(run(), name=f"voice-tts-{name}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def add_text(self, delta: str) -> None:
        if self._closed or not delta:
            return
        budget = settings.voice_tts_max_chars_per_reply - self._chars
        if len(delta) > budget:
            delta, self._truncated = delta[: max(budget, 0)], True
        self._chars += len(delta)
        for sentence in self._chunker.feed(delta):
            self._sentences.put_nowait(sentence)

    def end_text(self) -> None:
        if self._closed:
            return
        for sentence in self._chunker.finish():
            self._sentences.put_nowait(sentence)
        self._sentences.put_nowait(None)

    async def _write(self) -> None:
        while True:
            sentence = await self._sentences.get()
            if sentence is None:
                self._all_sent.set()
                await self._maybe_finish()
                return
            async with asyncio.timeout(settings.voice_tts_connect_timeout_seconds):
                await self._connection.send_text(sentence)
                await self._connection.send_flush()
            self._sentence_count += 1

    async def _maybe_finish(self) -> None:
        if self._all_sent.is_set() and self._flushed >= self._sentence_count:
            await self._finish("complete")

    async def _next_message(self, iterator: AsyncIterator[Any]) -> Any:
        # Wait without a limit for the next message unless a flushed sentence is owed audio:
        # the reply text itself may take a while to arrive.
        if self._flushed < self._sentence_count:
            try:
                async with asyncio.timeout(settings.voice_tts_idle_timeout_seconds):
                    return await iterator.__anext__()
            except TimeoutError:
                raise RuntimeError("speech provider timed out") from None
        return await iterator.__anext__()

    async def _read(self) -> None:
        iterator = self._connection.__aiter__()
        while True:
            try:
                message = await self._next_message(iterator)
            except StopAsyncIteration:
                break
            if isinstance(message, bytes | bytearray):
                if self._first_audio_at is None:
                    self._first_audio_at = self._clock()
                    log_event(
                        logger,
                        "voice.tts_first_audio",
                        message="First speech audio",
                        speech_id=self.speech_id,
                        duration_ms=int((self._first_audio_at - self._started_at) * 1000),
                    )
                self._seq += 1
                await self._emit(
                    {
                        "type": "tts_audio",
                        "speech_id": self.speech_id,
                        "seq": self._seq,
                        "audio_base64": base64.b64encode(bytes(message)).decode("ascii"),
                    }
                )
            elif getattr(message, "type", None) == "Flushed":
                self._flushed += 1
            await self._maybe_finish()
            if self._closed:
                return
        if not self._closed:
            await self._finish("complete" if self._all_sent.is_set() else "provider_closed")

    async def _finish(self, outcome: str) -> None:
        if self._closed:
            return
        self._closed = True
        await self._close_provider(graceful=True)
        log_event(
            logger,
            "voice.tts_ended",
            message="Speech stream ended",
            speech_id=self.speech_id,
            outcome=outcome,
            chars=self._chars,
            frames=self._seq,
            duration_ms=int((self._clock() - self._started_at) * 1000),
        )
        with contextlib.suppress(Exception):
            await self._emit(
                {
                    "type": "tts_end",
                    "speech_id": self.speech_id,
                    "truncated": self._truncated,
                }
            )
        self._done.set()

    async def _close_provider(self, *, graceful: bool) -> None:
        if self._connection is not None:
            with contextlib.suppress(Exception):
                async with asyncio.timeout(settings.voice_live_send_timeout_seconds):
                    if not graceful:
                        await self._connection.send_clear()
                    await self._connection.send_close()
        with contextlib.suppress(Exception):
            async with asyncio.timeout(STOP_DRAIN_SECONDS):
                await self._stack.aclose()
        self._connection = None

    async def _drain_tasks(self) -> None:
        current = asyncio.current_task()
        others = [task for task in self._tasks if task is not current]
        for task in others:
            task.cancel()
        if others:
            with contextlib.suppress(Exception):
                async with asyncio.timeout(STOP_DRAIN_SECONDS):
                    await asyncio.gather(*others, return_exceptions=True)

    async def cancel(self, reason: str = "cancelled") -> None:
        """Barge-in or a new reply: tell the client first, then clear the provider's buffer."""
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(Exception):
            await self._emit(
                {"type": "tts_cancelled", "speech_id": self.speech_id, "reason": reason}
            )
        while not self._sentences.empty():
            self._sentences.get_nowait()
        await self._drain_tasks()
        await self._close_provider(graceful=False)
        log_event(
            logger,
            "voice.tts_cancelled",
            message="Speech stream cancelled",
            speech_id=self.speech_id,
            outcome=reason,
            frames=self._seq,
        )
        self._done.set()

    async def fail(self, reason: str) -> None:
        if self._closed:
            return
        self._closed = True
        await self._drain_tasks()
        await self._close_provider(graceful=False)
        with contextlib.suppress(Exception):
            await self._emit({"type": "tts_error", "speech_id": self.speech_id, "reason": reason})
        self._done.set()

    async def wait_done(self) -> None:
        await self._done.wait()

    async def close(self) -> None:
        """Release everything (connection close). Used when the socket goes away."""
        if not self._closed:
            self._closed = True
            await self._drain_tasks()
            await self._close_provider(graceful=False)
            self._done.set()
        else:
            await self._drain_tasks()
