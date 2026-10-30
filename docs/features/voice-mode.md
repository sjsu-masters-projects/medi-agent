# Voice mode

Voice mode lets a patient talk to Nora hands-free in the patient portal: live speech to
text while they speak, the same chat turn as typed text, and a spoken reply that starts
after the first sentence and can be interrupted. It is for patients who cannot comfortably
type. Everything is synthetic data; nothing here is a production or HIPAA claim.

## What it does

- **Patient.** Taps "Voice conversation", allows the microphone, speaks in English or
  Spanish. Partial words appear live; each finished utterance becomes a normal chat
  message; Nora's reply appears as text and is spoken; the panel returns to listening. The
  patient can pause, resume, end, talk over Nora to interrupt, or fall back to typing.
- **Spoken reply.** Routine replies start speaking while still being written. Urgent,
  emergency and guided symptom replies are spoken once, whole, from the saved message and
  cannot be interrupted.
- **Typed chats** keep the per-message Listen button and the symptom-intake dictation
  button; those use the older record-then-transcribe flow, which still exists.
- **Care team and operators** see nothing new: a transcript is an ordinary chat message.

## Rules it must keep

1. The transcript is text and takes the same durable chat turn as a typed message, so the
   safety floors, turn queue, recovery, audit and authorization all apply. Voice has no
   private path around them. The live session never reads or writes chat messages and
   authenticates only the patient the path names.
2. The speech provider key stays on the server. The browser talks only to our websocket
   (`/ws/voice/{patient_id}`), with the token in the subprotocol, never the URL.
3. `utterance_final` carries the floor's guidance computed on the transcript; the panel
   shows it as a persistent alert. A spoken floor hit is audited without waiting for the
   typed turn. An urgent reply keeps its banner and is sent with `interruptible: false`.
4. A reply is spoken early only while every check that applies to the final reply has
   already run on the text: routine urgency, not the symptom route, model-written source
   lines and Markdown already removed (the voice chunker also drops source lines by line).
   The server-written source line is never spoken.
5. The saved reply wins. If the draft stops being an extension (a withdrawn or restarted
   draft, a fallback model, a replaced text), audio stops at once and the saved reply is
   spoken whole. If it starts with what was already spoken, in the same language and not
   urgent, the same stream is finished with the remainder.
6. Barge-in works twice: the backend cancels speech on the provider's `speech_started`, and
   the browser stops playback on `speech_started` or sustained loud input (about 240 ms)
   and sends `tts_cancel`. Non-interruptible speech is never cut off. A patient who talks
   over early speech is not talked over by the saved reply.
7. Every bound is enforced by the session, not the browser: 900 s session, 60 s idle while
   listening, 45 s or 2,000 characters per utterance, 64 queued 32 KB frames (shed, never
   buffered without limit), 20 live sessions per process and one per patient, 2,500
   characters per spoken reply and 240 per sentence. Limits are in `app/config.py`.
8. Every exit path stops all tracks, closes the AudioContext and the sockets: end, error,
   unmount, sign-out, conversation change, tab hidden over 60 s, page hide. Ending keeps the
   socket up for up to 1.5 s so a finished utterance still reaches the chat. A reload ends
   voice mode; the chat replays the draft from the event log and shows one bubble.
9. Words are never dropped. If the chat socket is not ready when an utterance finalizes, the
   text goes to the composer with a notice. The patient's own message shows at once as
   pending, with Retry and Remove if the connection drops.
10. Failure never blocks text. Denied microphone, unsupported browser, provider failure,
    capacity, speech that does not start in 12 s, or no reply within 2 minutes each show an
    inline message and leave typing working. One automatic reconnect keeps the microphone
    open; a second drop exits voice mode cleanly.
11. No transcript or reply text is logged. Voice logs carry lengths, `utterance_id`,
    `speech_id` and outcomes only.
12. Speech is transcribed in multilingual mode and labelled with the language heard, so
    Spanish under an English app setting works. Spoken voices are Aura-2 Asteria (en) and
    Estrella (es-MX), chosen by the reply's language.
13. Draft checkpoints are repeat-safe and bounded: at most one write per 0.4 s, 120 per
    turn, ordered by `seq`, a reset bumps `epoch`, and they never block the model stream.
    If the unsupported-dose check ever becomes blocking, early speech must be turned off
    for those turns.

## Why it was built this way

- Transcribe in the browser session, send text through the normal turn, speak the saved
  reply: what is heard equals what is saved, and safety logic exists once.
- Early speech was added because replies took 7 to 22 s to start. It needed the reply model
  route to pass text through after its first visible text instead of buffering the whole
  attempt; tool rounds stay buffered so a timeout can still fall back cleanly.
- A fallback after text was shown withdraws that text and reruns the backup model once,
  only if at least `REPLY_FALLBACK_MIN_SECONDS` (2) of the reply budget is left.
- Rejected: a voice-only path around chat turns, which would need its own safety, retry
  and audit logic.

## Excluded on purpose

- A clinical report submitted by voice alone; the symptom flow keeps its confirmation.
- Any provider key, audio or transcript stored in the browser or logged.
- Physical-device acceptance is not claimed by automated tests; it stays a manual check.

## Where it lives

- Backend: `backend/src/app/routers/voice.py`, `services/voice_connection.py`,
  `services/voice_live.py`, `services/voice_service.py`; draft checkpointing in
  `services/chat_turn_worker.py` (`DraftCheckpointer`); reply route in
  `adk/models/resilient.py` (`ReplyRoute`); text filter in `adk/grounding.py`.
- Portal: `apps/patient-portal/src/services/pcm-audio.ts`, `live-voice.ts`,
  `hooks/use-voice-mode.ts`, `components/features/voice-mode-panel.tsx`, copy in
  `content/chat-copy.ts` (`getVoiceModeCopy`); wording evidence in
  [Spanish interface wording review](../evidence/spanish-interface-wording-2026-10-22.md).
- Protocol: client sends binary 16 kHz mono PCM frames plus `voice_session_start`,
  `voice_session_stop`, `voice_state`, `tts_stream_start`, `tts_text`, `tts_end`,
  `tts_cancel`, `ping`; server sends `voice_ready`, `voice_session_started`,
  `speech_started`, `transcript_partial`, `utterance_final`, `tts_start`, `tts_audio`,
  `tts_end`, `tts_cancelled`, `tts_error`, `voice_session_ended`, `voice_error`.
- Deploy: the backend service needs `DEEPGRAM_API_KEY` (secret); no other variable. The chat
  worker does not use voice. The backend request timeout (3600 s) exceeds the 900 s limit.

## How to check it

[QA handoff 3.1, VOICE-001 and VOI-001-M](../qa-handoff-2026-10.md). On a phone and a
desktop browser, as the synthetic patient, in en-US and es-MX: speak a question and see
partial words, a final message, a spoken reply, then listening again; speak over Nora and
hear audio stop; say an emergency phrase and see the banner with the reply spoken in full;
deny the microphone and type; pause, resume and end (the browser microphone indicator goes
off); reload mid-turn in a second tab (one reply). Latency: compare `voice.tts_first_audio`
and the browser gap from `utterance_final` to first `tts_audio`.
From `backend/`: `.venv/bin/pytest tests/unit/services/test_voice_live.py
tests/integration/routers/test_chat_voice_api.py --no-cov -q`. Portal: `npm run test --
voice` in `apps/patient-portal` (mocked audio and sockets; they do not prove real audio).

## Still open

- Physical phone acceptance (VOI-001-M) has not been recorded.
- Time to first audio on a deployed routine question has not been measured against the
  earlier final-only baseline.
