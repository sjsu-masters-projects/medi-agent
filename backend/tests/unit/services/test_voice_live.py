"""Live voice mode: streaming speech to text and text to speech, with fake Deepgram clients."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from types import SimpleNamespace
from typing import Any

import pytest

from app.config import settings
from app.services import voice_live
from app.services.voice_connection import VoiceConnection
from app.services.voice_live import (
    LiveSttSession,
    SentenceChunker,
    SpeechStream,
    UtteranceAssembler,
    live_params,
    speak_params,
)

# -- fakes: no real Deepgram call is ever made -----------------------------------------------------


def result(text: str, *, is_final: bool = True, speech_final: bool = False) -> Any:
    return SimpleNamespace(
        type="Results",
        is_final=is_final,
        speech_final=speech_final,
        channel=SimpleNamespace(alternatives=[SimpleNamespace(transcript=text)]),
    )


SPEECH_STARTED = SimpleNamespace(type="SpeechStarted")
UTTERANCE_END = SimpleNamespace(type="UtteranceEnd")
FLUSHED = SimpleNamespace(type="Flushed")


class FakeConnection:
    """A Deepgram connection driven by the test through ``push``."""

    def __init__(self) -> None:
        self.media: list[bytes] = []
        self.calls: list[str] = []
        self.texts: list[str] = []
        self.inbox: asyncio.Queue[Any] = asyncio.Queue()
        self.exited = False
        self.block_media: asyncio.Event | None = None
        self.fail_iteration: Exception | None = None

    def push(self, message: Any) -> None:
        self.inbox.put_nowait(message)

    def end(self) -> None:
        self.inbox.put_nowait(StopAsyncIteration)

    async def send_media(self, data: bytes) -> None:
        if self.block_media is not None:
            await self.block_media.wait()
        self.media.append(data)

    async def send_finalize(self) -> None:
        self.calls.append("finalize")

    async def send_close_stream(self) -> None:
        self.calls.append("close_stream")

    async def send_text(self, text: str) -> None:
        self.texts.append(text)
        self.calls.append("text")

    async def send_flush(self) -> None:
        self.calls.append("flush")

    async def send_clear(self) -> None:
        self.calls.append("clear")

    async def send_close(self) -> None:
        self.calls.append("close")

    def __aiter__(self) -> FakeConnection:
        return self

    async def __anext__(self) -> Any:
        item = await self.inbox.get()
        if item is StopAsyncIteration:
            raise StopAsyncIteration
        if isinstance(item, Exception):
            raise item
        return item


class FakeConnector:
    def __init__(self, fail: Exception | None = None, delay: float = 0) -> None:
        self.connection = FakeConnection()
        self.params: dict[str, Any] | None = None
        self.fail = fail
        self.delay = delay

    def __call__(self, params: dict[str, Any]) -> Any:
        self.params = params
        connector = self

        @contextlib.asynccontextmanager
        async def manager() -> Any:
            if connector.delay:
                await asyncio.sleep(connector.delay)
            if connector.fail:
                raise connector.fail
            try:
                yield connector.connection
            finally:
                connector.connection.exited = True

        return manager()


class Sink:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def __call__(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    def types(self) -> list[str]:
        return [event["type"] for event in self.events]

    def of(self, kind: str) -> list[dict[str, Any]]:
        return [event for event in self.events if event["type"] == kind]


async def settle(times: int = 6) -> None:
    for _ in range(times):
        await asyncio.sleep(0)


@pytest.fixture(autouse=True)
def _voice_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "deepgram_api_key", "test-key")
    monkeypatch.setattr(settings, "voice_live_enabled", True)
    monkeypatch.setattr(settings, "voice_tts_stream_enabled", True)


async def live(
    connector: FakeConnector | None = None, sink: Sink | None = None, **kwargs: Any
) -> tuple[LiveSttSession, FakeConnector, Sink]:
    connector = connector or FakeConnector()
    sink = sink or Sink()
    session = LiveSttSession(emit=sink, connector=connector, **kwargs)
    await session.start()
    return session, connector, sink


# -- speech to text -----------------------------------------------------------------------------


def test_the_deepgram_live_parameters_are_the_verified_ones() -> None:
    params = live_params()
    assert params["model"] == "nova-3" and params["language"] == "multi"
    assert params["interim_results"] == "true" and params["smart_format"] == "true"
    assert params["vad_events"] == "true" and params["encoding"] == "linear16"
    assert params["endpointing"] == str(settings.deepgram_endpointing_ms)
    assert int(params["utterance_end_ms"]) >= 1000  # Deepgram's documented minimum
    assert params["sample_rate"] == "16000" and params["channels"] == "1"


@pytest.mark.asyncio
async def test_microphone_frames_are_relayed_in_order() -> None:
    session, connector, _ = await live()
    for index in range(5):
        assert session.feed(bytes([index]) * 10)
    await settle()
    assert connector.connection.media == [bytes([i]) * 10 for i in range(5)]
    await session.stop("client")


@pytest.mark.asyncio
async def test_interim_text_is_shown_then_end_of_speech_sends_one_final_utterance() -> None:
    session, connector, sink = await live()
    conn = connector.connection
    conn.push(SPEECH_STARTED)
    conn.push(result("I have", is_final=False))
    conn.push(result("I have a headache", is_final=True))
    conn.push(result("since this morning", is_final=True, speech_final=True))
    conn.push(UTTERANCE_END)  # the fallback signal for the same speech: must not repeat it
    await settle(12)
    assert sink.types().count("speech_started") == 1
    partials = [e["transcript"] for e in sink.of("transcript_partial")]
    assert partials[0] == "I have" and partials[-1] == "I have a headache"
    [final] = sink.of("utterance_final")
    assert final["transcript"] == "I have a headache since this morning"
    assert final["utterance_id"] and "safety_guidance" not in final
    assert session.utterances == 1
    await session.stop("client")


@pytest.mark.asyncio
async def test_utterance_end_closes_speech_when_endpointing_did_not() -> None:
    session, connector, sink = await live(language_hint="es-MX")
    connector.connection.push(result("Necesito mi receta", is_final=True))
    connector.connection.push(UTTERANCE_END)
    await settle(12)
    [final] = sink.of("utterance_final")
    assert final["transcript"] == "Necesito mi receta" and final["language"] == "es-MX"
    await session.stop("client")


@pytest.mark.asyncio
async def test_each_utterance_has_its_own_id_so_a_resend_is_idempotent_by_id() -> None:
    session, connector, sink = await live()
    for text in ("first thing", "second thing"):
        connector.connection.push(result(text, speech_final=True))
    await settle(12)
    ids = [e["utterance_id"] for e in sink.of("utterance_final")]
    assert len(ids) == 2 and ids[0] != ids[1]
    await session.stop("client")


@pytest.mark.parametrize(
    ("text", "language"),
    [("I have chest pain and I am sweating", "en-US"), ("tengo dolor de pecho fuerte", "es-MX")],
)
@pytest.mark.asyncio
async def test_the_safety_floor_runs_on_the_transcript_text(text: str, language: str) -> None:
    session, connector, sink = await live(language_hint=language)
    connector.connection.push(result(text, speech_final=True))
    await settle(12)
    [final] = sink.of("utterance_final")
    assert final["safety_guidance"]
    assert ("911" in final["safety_guidance"]) or ("emergencia" in final["safety_guidance"].lower())
    await session.stop("client")


@pytest.mark.asyncio
async def test_a_spoken_floor_hit_reports_rule_urgency_and_id_but_not_the_transcript() -> None:
    seen: list[tuple[str, str, str]] = []
    session, connector, sink = await live(
        language_hint="en-US", on_safety_floor=lambda *args: seen.append(args)
    )
    connector.connection.push(result("I have chest pain and I am sweating", speech_final=True))
    await settle(12)
    [final] = sink.of("utterance_final")
    assert seen == [("emergency_symptom_keyword", "emergency", final["utterance_id"])]
    assert "chest" not in str(seen)
    await session.stop("client")


@pytest.mark.asyncio
async def test_a_failing_audit_hook_never_blocks_the_utterance() -> None:
    def boom(*_args: str) -> None:
        raise RuntimeError("synthetic")

    session, connector, sink = await live(language_hint="en-US", on_safety_floor=boom)
    connector.connection.push(result("I have chest pain and I am sweating", speech_final=True))
    await settle(12)
    [final] = sink.of("utterance_final")
    assert final["safety_guidance"]
    await session.stop("client")


@pytest.mark.asyncio
async def test_an_ordinary_utterance_reports_nothing_to_audit() -> None:
    seen: list[tuple[str, str, str]] = []
    session, connector, _sink = await live(on_safety_floor=lambda *args: seen.append(args))
    connector.connection.push(result("What time is my appointment", speech_final=True))
    await settle(12)
    assert seen == []
    await session.stop("client")


@pytest.mark.asyncio
async def test_stop_closes_the_provider_drains_tasks_and_is_idempotent() -> None:
    session, connector, sink = await live()
    await session.stop("client")
    await session.stop("client")
    assert connector.connection.exited and "close_stream" in connector.connection.calls
    assert connector.connection.calls.count("close_stream") == 1
    assert sink.of("voice_session_ended") == [{"type": "voice_session_ended", "reason": "client"}]
    assert not session._tasks
    assert not session.feed(b"late")


@pytest.mark.asyncio
async def test_speech_said_just_before_stop_is_not_lost() -> None:
    session, connector, sink = await live()
    connector.connection.push(result("pending words", is_final=True))
    await settle(8)
    await session.stop("client")
    assert [e["transcript"] for e in sink.of("utterance_final")] == ["pending words"]


@pytest.mark.asyncio
async def test_a_provider_failure_ends_the_session_and_closes_the_connection() -> None:
    session, connector, sink = await live()
    connector.connection.push(RuntimeError("provider exploded"))
    await settle(12)
    assert connector.connection.exited
    assert sink.of("voice_session_ended")[0]["reason"] == "error"
    assert not session._tasks


@pytest.mark.asyncio
async def test_the_provider_closing_ends_the_session() -> None:
    session, connector, sink = await live()
    connector.connection.end()
    await settle(12)
    assert sink.of("voice_session_ended")[0]["reason"] == "provider_closed"
    assert connector.connection.exited


@pytest.mark.asyncio
async def test_connect_failure_and_connect_timeout_leave_nothing_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failing = FakeConnector(fail=RuntimeError("refused"))
    with pytest.raises(RuntimeError):
        await LiveSttSession(emit=Sink(), connector=failing).start()
    monkeypatch.setattr(settings, "voice_live_connect_timeout_seconds", 0.05)
    slow = FakeConnector(delay=1)
    with pytest.raises(TimeoutError):
        await LiveSttSession(emit=Sink(), connector=slow).start()
    assert not slow.connection.exited  # never connected, so nothing to close


@pytest.mark.asyncio
async def test_a_full_queue_sheds_frames_and_sustained_overload_ends_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "voice_live_audio_queue_frames", 4)
    session, connector, sink = await live()
    connector.connection.block_media = asyncio.Event()  # the provider stops taking audio
    results = [session.feed(b"x" * 100) for _ in range(4 + voice_live.OVERLOAD_DROPS + 2)]
    assert results[:5].count(True) >= 4 and results[-1] is False
    assert session.frames_dropped >= voice_live.OVERLOAD_DROPS
    await settle(20)
    assert sink.of("voice_session_ended")[0]["reason"] == "overloaded"
    assert connector.connection.exited


@pytest.mark.asyncio
async def test_the_session_has_a_maximum_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "voice_live_max_session_seconds", 0.3)
    session, connector, sink = await live()
    await asyncio.sleep(0.8)
    assert sink.of("voice_session_ended")[0]["reason"] == "max_session"
    assert connector.connection.exited


@pytest.mark.asyncio
async def test_silence_times_out_only_while_listening(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "voice_live_idle_timeout_seconds", 0.3)
    session, connector, sink = await live()
    session.client_state = "thinking"  # Nora is working: that is not idle
    await asyncio.sleep(0.7)
    assert not sink.of("voice_session_ended")
    session.client_state = "listening"
    session.touch()
    await asyncio.sleep(0.8)
    assert sink.of("voice_session_ended")[0]["reason"] == "idle_timeout"


@pytest.mark.asyncio
async def test_an_utterance_that_never_pauses_is_finalized_at_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "voice_live_max_utterance_seconds", 0.3)
    monkeypatch.setattr(voice_live, "FORCE_FLUSH_GRACE_SECONDS", 0.1)
    session, connector, sink = await live()
    connector.connection.push(result("talking and talking", is_final=True))
    await asyncio.sleep(1.0)
    assert "finalize" in connector.connection.calls
    assert [e["transcript"] for e in sink.of("utterance_final")] == ["talking and talking"]
    await session.stop("client")


def test_the_utterance_text_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    assembler = UtteranceAssembler(max_chars=50)
    [(kind, utterance)] = assembler.on_result("word " * 40, is_final=True, speech_final=True)
    assert kind == "final" and len(utterance.text) <= 50


@pytest.mark.asyncio
async def test_no_transcript_text_reaches_the_logs(caplog: pytest.LogCaptureFixture) -> None:
    secret = "my private words about rosuvastatin"
    with caplog.at_level(logging.DEBUG):
        session, connector, sink = await live()
        connector.connection.push(result(secret, is_final=False))
        connector.connection.push(result(secret, speech_final=True))
        await settle(12)
        await session.stop("client")
    assert sink.of("utterance_final")
    rendered = json.dumps(
        [
            {
                "message": record.getMessage(),
                **{k: str(v) for k, v in record.__dict__.items() if k != "args"},
            }
            for record in caplog.records
        ]
    )
    assert "private words" not in rendered and "rosuvastatin" not in rendered


# -- text to speech -----------------------------------------------------------------------------


def test_the_chunker_speaks_whole_sentences_in_order() -> None:
    chunker = SentenceChunker(max_chars=240)
    spoken: list[str] = []
    for delta in [
        "Hello th",
        "ere. I am Nora",
        " and I can help. Dr. Park s",
        "ees you at 9 a.m. today.",
    ]:
        spoken += chunker.feed(delta)
    assert spoken == ["Hello there.", "I am Nora and I can help."]  # held until the end is seen
    assert chunker.finish() == ["Dr. Park sees you at 9 a.m. today."]


def test_the_chunker_keeps_decimals_and_list_numbers_together_and_drops_markup_and_sources() -> (
    None
):
    chunker = SentenceChunker(max_chars=240)
    out = chunker.feed(
        "Your temperature was 98.6 degrees. 1. Drink water.\n\n**Sources:** MedlinePlus\n"
    )
    out += chunker.finish()
    assert out == ["Your temperature was 98.6 degrees.", "1. Drink water."]


def test_a_very_long_sentence_is_split_below_the_limit() -> None:
    chunker = SentenceChunker(max_chars=60)
    out = chunker.feed("word, " * 60) + chunker.finish()
    assert out and all(len(part) <= 60 for part in out)
    assert " ".join(out).replace(",", "").split() == ["word"] * 60


def test_the_voice_names_are_the_verified_aura_2_models() -> None:
    assert speak_params("en-US")["model"] == "aura-2-asteria-en"
    assert speak_params("es-MX")["model"] == "aura-2-estrella-es"
    assert speak_params("es-MX")["encoding"] == "linear16"


def stream(connector: FakeConnector, sink: Sink, **kwargs: Any) -> SpeechStream:
    return SpeechStream(
        speech_id="speech-1", language="en-US", emit=sink, connector=connector, **kwargs
    )


@pytest.mark.asyncio
async def test_sentences_are_spoken_as_text_arrives_and_audio_is_relayed_in_order() -> None:
    connector, sink = FakeConnector(), Sink()
    speech = stream(connector, sink)
    await speech.start()
    conn = connector.connection
    speech.add_text("First sentence. Second sen")
    await settle()
    # The first sentence is already with the provider before the second one exists.
    assert conn.texts == ["First sentence."] and conn.calls == ["text", "flush"]
    conn.push(b"\x01\x02")
    conn.push(FLUSHED)
    await settle()
    assert [e["seq"] for e in sink.of("tts_audio")] == [1]
    speech.add_text("tence. Third one.")
    speech.end_text()
    await settle()
    conn.push(b"\x03")
    conn.push(FLUSHED)
    conn.push(b"\x04")
    conn.push(FLUSHED)
    await asyncio.wait_for(speech.wait_done(), 2)
    assert conn.texts == ["First sentence.", "Second sentence.", "Third one."]
    audio = sink.of("tts_audio")
    assert [e["seq"] for e in audio] == [1, 2, 3]
    assert sink.types()[0] == "tts_start" and sink.types()[-1] == "tts_end"
    assert conn.exited and "close" in conn.calls


@pytest.mark.asyncio
async def test_an_empty_reply_ends_cleanly() -> None:
    connector, sink = FakeConnector(), Sink()
    speech = stream(connector, sink)
    await speech.start()
    speech.end_text()
    await asyncio.wait_for(speech.wait_done(), 2)
    assert sink.types() == ["tts_start", "tts_end"] and connector.connection.exited


@pytest.mark.asyncio
async def test_cancel_stops_playback_clears_the_provider_and_drops_late_audio() -> None:
    connector, sink = FakeConnector(), Sink()
    speech = stream(connector, sink)
    await speech.start()
    speech.add_text("A long answer. Another sentence. ")
    await settle()
    await speech.cancel("barge_in")
    connector.connection.push(b"late-audio")
    await settle()
    assert sink.of("tts_cancelled") == [
        {"type": "tts_cancelled", "speech_id": "speech-1", "reason": "barge_in"}
    ]
    assert "clear" in connector.connection.calls and connector.connection.exited
    assert not sink.of("tts_audio") and not sink.of("tts_end")
    assert not speech._tasks


@pytest.mark.asyncio
async def test_text_beyond_the_per_reply_budget_is_not_spoken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "voice_tts_max_chars_per_reply", 30)
    connector, sink = FakeConnector(), Sink()
    speech = stream(connector, sink)
    await speech.start()
    speech.add_text("Short one. " + "Never spoken. " * 20)
    speech.end_text()
    await settle()
    assert sum(len(t) for t in connector.connection.texts) <= 30
    for _ in connector.connection.texts:
        connector.connection.push(FLUSHED)
    await asyncio.wait_for(speech.wait_done(), 2)
    assert sink.of("tts_end")[0]["truncated"] is True


@pytest.mark.asyncio
async def test_a_provider_error_mid_speech_is_reported_and_closes_the_connection() -> None:
    connector, sink = FakeConnector(), Sink()
    speech = stream(connector, sink)
    await speech.start()
    speech.add_text("One sentence. ")
    await settle()
    connector.connection.push(RuntimeError("boom"))
    await asyncio.wait_for(speech.wait_done(), 2)
    await settle()
    assert sink.of("tts_error") and connector.connection.exited
    assert not speech._tasks


@pytest.mark.asyncio
async def test_a_speech_connect_failure_cleans_up() -> None:
    speech = stream(FakeConnector(fail=RuntimeError("refused")), Sink())
    with pytest.raises(RuntimeError):
        await speech.start()
    assert speech.finished


# -- the connection: barge-in, replacement and cleanup -------------------------------------------


async def connection() -> tuple[VoiceConnection, FakeConnector, FakeConnector, Sink]:
    live_connector, speak_connector, sink = FakeConnector(), FakeConnector(), Sink()
    conn = VoiceConnection(sink, live_connector=live_connector, speak_connector=speak_connector)
    return conn, live_connector, speak_connector, sink


@pytest.mark.asyncio
async def test_speaking_over_nora_stops_her_at_once() -> None:
    conn, live_c, speak_c, sink = await connection()
    await conn.handle_event("voice_session_start", {"language": "en-US"})
    await conn.handle_event("tts_stream_start", {"speech_id": "r1", "language": "en-US"})
    await conn.handle_event("tts_text", {"speech_id": "r1", "text": "Here is a long reply. "})
    await settle(10)
    live_c.connection.push(SPEECH_STARTED)  # the patient starts talking
    await settle(10)
    assert sink.of("tts_cancelled")[0]["reason"] == "barge_in"
    assert sink.of("speech_started") and speak_c.connection.exited
    await conn.close()


@pytest.mark.asyncio
async def test_a_safety_floor_reply_cannot_be_cut_off_by_noise() -> None:
    conn, live_c, speak_c, sink = await connection()
    await conn.handle_event("voice_session_start", {})
    await conn.handle_event(
        "tts_stream_start", {"speech_id": "floor", "language": "en-US", "interruptible": False}
    )
    await conn.handle_event("tts_text", {"speech_id": "floor", "text": "Call 911 now. "})
    await settle(10)
    live_c.connection.push(SPEECH_STARTED)
    await settle(10)
    assert not sink.of("tts_cancelled") and not speak_c.connection.exited
    await conn.close()


@pytest.mark.asyncio
async def test_a_new_reply_replaces_the_old_one_and_stale_ids_are_ignored() -> None:
    conn, _, speak_c, sink = await connection()
    await conn.handle_event("tts_stream_start", {"speech_id": "old"})
    await settle(10)
    await conn.handle_event("tts_stream_start", {"speech_id": "new"})
    await settle(10)
    assert sink.of("tts_cancelled")[0]["speech_id"] == "old"
    await conn.handle_event("tts_text", {"speech_id": "old", "text": "ignored. "})
    assert speak_c.connection.texts == []
    await conn.close()


@pytest.mark.asyncio
async def test_closing_the_connection_closes_every_provider_connection() -> None:
    conn, live_c, speak_c, _ = await connection()
    await conn.handle_event("voice_session_start", {})
    await conn.handle_event("tts_stream_start", {"speech_id": "r1"})
    await settle(10)
    await conn.close()
    assert live_c.connection.exited and speak_c.connection.exited
    assert not conn._tasks


@pytest.mark.asyncio
async def test_voice_is_refused_without_a_key_or_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "deepgram_api_key", "")
    conn, live_c, _, sink = await connection()
    await conn.handle_event("voice_session_start", {})
    assert sink.of("voice_error")[0]["code"] == "voice_live_unavailable"
    assert live_c.params is None


@pytest.mark.asyncio
async def test_a_second_session_is_refused_and_an_oversized_frame_is_dropped() -> None:
    conn, live_c, _, sink = await connection()
    await conn.handle_event("voice_session_start", {})
    await conn.handle_event("voice_session_start", {})
    assert sink.of("voice_error")[0]["code"] == "voice_stream_active"
    await conn.frame(b"x" * (settings.voice_live_max_frame_bytes + 1))
    assert sink.of("voice_error")[-1]["code"] == "voice_frame_too_large"
    await conn.frame(b"ok")
    await settle(10)
    assert live_c.connection.media == [b"ok"]
    await conn.close()


@pytest.mark.asyncio
async def test_one_patient_cannot_stream_two_sessions_and_the_process_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_sink, second_sink, other_sink = Sink(), Sink(), Sink()
    first = VoiceConnection(first_sink, live_connector=FakeConnector(), owner="patient-a")
    second = VoiceConnection(second_sink, live_connector=FakeConnector(), owner="patient-a")
    other = VoiceConnection(other_sink, live_connector=FakeConnector(), owner="patient-b")
    await first.handle_event("voice_session_start", {})
    await second.handle_event("voice_session_start", {})
    assert second_sink.of("voice_error")[0]["code"] == "voice_live_busy"
    # A different patient is unaffected until the process-wide bound is reached.
    monkeypatch.setattr(settings, "voice_live_max_sessions", 1)
    await other.handle_event("voice_session_start", {})
    assert other_sink.of("voice_error")[0]["code"] == "voice_live_busy"
    await first.close()
    await other.handle_event("voice_session_start", {})
    assert other_sink.of("voice_session_started")
    await other.close()
    await second.close()
