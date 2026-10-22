# VOICE-001 — Live voice mode

Status: **In review** (branches `feature/voice-mode-and-chat-polish`, then `feature/nora-recovery-and-early-speech` for early speech). Builds on VOI-001
(transcription language, Spanish voice) and PAT-001-A (durable chat turns). Physical
phone acceptance stays under VOI-001-M; nothing here is verified on a real device yet.

## Problem

Voice used to be record, stop, wait for a batch transcript, then press send, with the reply
fetched as one audio clip afterwards. That is slow and not hands-free. Patients with
chronic conditions and polypharmacy often cannot comfortably type, and long silent waits
read as a broken app. The goal is a conversation: the patient speaks, sees the words appear,
Nora answers in text and in a voice that starts after the first sentence, and the patient can
interrupt her.

Two chat defects found while testing voice are fixed in the same branch because voice made
them obvious: a patient's own message appeared late, and Nora said she saw no appointment
while the Visits screen showed a confirmed one (see "Related chat fixes").

## Architecture

```
browser mic (echo cancellation, noise suppression, AGC)
  -> AudioWorklet (ScriptProcessor only if worklets are missing)
  -> downsample to 16 kHz, 16-bit mono PCM, 40 ms binary frames
  -> /ws/voice/{patient_id}   (token in the subprotocol, never the URL)
  -> VoiceConnection -> LiveSttSession -> Deepgram listen.v1 (nova-3, multi, interim results,
     endpointing, utterance end, VAD)
  <- speech_started / transcript_partial / utterance_final (+ safety_guidance)
  -> portal sends utterance_final through the normal chat send path
     (optimistic message, retry, recovery, durable turn, safety floors all apply)
  <- Nora's reply text arrives on the chat socket and appears in the thread
  -> portal sends tts_stream_start / tts_text / tts_end on the voice socket
  -> SpeechStream -> Deepgram speak.v1 (Aura-2, linear16, sentence by sentence)
  <- tts_start / tts_audio (base64 PCM, in order) / tts_end
  -> Web Audio, gapless scheduling, then back to listening
```

Key decisions:

- The transcript is **text** and takes the same durable chat turn as a typed message. Voice
  has no private path around the safety floors, the turn queue, recovery or the audit trail.
  The voice socket never creates, reads or writes chat messages, so it cannot act for another
  patient; it only authenticates the same patient the path names.
- The Deepgram key stays on the server. The browser talks to our websocket only.
- The reply is spoken as it is written (see "Early speech" below) only when every check that
  applies to the final reply has already run on the text, and is corrected from the saved
  message whenever the two differ. Otherwise it is spoken from the **final** chat message, so
  what is heard equals what is saved. The backend splits text into sentences and starts audio
  after the first.
- Barge-in works in two places: the backend cancels the speech stream when the provider
  reports `speech_started`, and the browser stops playback at once on `speech_started` or
  after sustained loud input (about 240 ms above a level floor) and sends `tts_cancel`.
  An emergency reply is sent with `interruptible: false` and is not cut off.
- Each exit path (end, error, unmount, sign-out, conversation change, tab hidden over 60 s,
  page hide) stops every track, closes the AudioContext and the sockets. Ending keeps the
  socket up for up to 1.5 s so an utterance the provider had finished but not yet reported
  still reaches the chat.

Code map: `backend/src/app/routers/voice.py`, `services/voice_connection.py`,
`services/voice_live.py`; portal `services/pcm-audio.ts`, `services/live-voice.ts`,
`hooks/use-voice-mode.ts`, `components/features/voice-mode-panel.tsx`, copy in
`content/chat-copy.ts` (`getVoiceModeCopy`).

## Early speech (starts before the whole reply exists)

Before: audio began after the entire reply was saved (7 to 22 s). Cause found on the way:
`ResilientLlm` buffered each model attempt to the end (so a timeout could fall back cleanly), so
the responder's text reached the draft checkpointer in one burst just before completion and no
production turn wrote a useful draft.

Now: the patient-reply model route (`stream_text`, responder only) holds the response only until
its first visible text, then passes text through; tool rounds are still held and can still fall
back. If the model fails after text was shown, `ReplyRoute` withdraws that text (a reset marker,
`chunk_reset` then `assistant_reset`, a new draft `epoch`) and runs the backup model once, from the
same request, as a new draft, only if at least `REPLY_FALLBACK_MIN_SECONDS` (2) of the reply budget
(both attempts' budgets together, always under the turn ceiling) is left. Only if the backup also
fails, or the budget is spent, is the reviewed localized unavailable message used. Voice treats a
reset like any mismatch: audio stops and the saved reply is spoken whole.

Post-model checks, and where each runs:

| Check | Where it runs | Early speech |
| --- | --- | --- |
| Emergency/crisis floor, urgency escalation | Before the model (floor) and on the triage decision, which is made before any reply text exists; monotonic | Urgent or emergency turns, and the guided symptom flow, are **never** spoken early: the saved reply is spoken once, whole, not interruptible |
| Model-written `Source:`/`Fuente:` lines | `StreamingReplyFilter` (line-aware; a line that may become a source line is held back) | Yes: already removed from the draft; the voice chunker drops them by line too (a title with a full stop is not read out) |
| Markdown marks, headings, bullets (`plain_reply`) | Same filter | Yes: draft is a prefix of the saved reply (property test over random chunkings) |
| Server-written source line | Appended after the reply | Not spoken; it arrives only in the saved message |
| Unsupported-dose check | Full reply, **log only** today | Does not block. If it ever becomes blocking, early speech must be disabled for those turns |
| Symptom route / outer fallback / model failure replacing the text | Router and runtime | The replacement is a different text: audio stops and the saved reply is spoken |

Browser rules (`LiveVoiceController.speakDraft` / `speakReply`): speech starts at the first draft
text of a routine, non-symptom reply; only text beyond what was already handed on is sent
(idempotent for repeated or re-ordered drafts); a draft that stops being an extension or restarts
(generation changed) stops audio and disables early speech for the turn; when the saved reply
arrives, if it starts with what was handed on (and is not urgent and is in the same language) the
same stream is finished with the remainder, otherwise audio stops at once and the saved reply is
spoken from the start. A patient who talks over early speech is not talked over by the saved
reply. If the saved reply does not arrive in 120 s, speech stops with the usual "reply failed"
notice. A reload ends voice mode; the chat replays the draft from the event log and shows one
bubble, ending with the saved message.

Server side: `DraftCheckpointer` writes the whole draft so far at most every 0.4 s (first one
within 0.1 s), at most 120 draft writes per turn, ordered by `seq`, repeat-safe (`append_event`
treats a repeated seq as a no-op), never blocking the model stream. A reset bumps `epoch`; a
re-claimed turn (`run`) restarts the viewer's draft. Viewers poll every 0.3 s while events flow
(1 s idle ceiling). No new tables.

Measure (manual, deployed): time from the end of the patient's utterance to the first audio, in
`voice.tts_first_audio` plus the browser's `utterance_final` to first `tts_audio`; compare a
routine question before (final-only: expect the 7 to 22 s above) and after this change.

## Protocol

Client to server (`/ws/voice/{patient_id}`):

| Message | Fields | Meaning |
| --- | --- | --- |
| binary frame | 16-bit little-endian mono PCM at `sample_rate`, at most `max_frame_bytes` | Microphone audio; ignored unless a live session is active |
| `voice_session_start` | `language` (hint) | Open the Deepgram live session |
| `voice_session_stop` | none | Close it; a pending utterance is still delivered |
| `voice_state` | `state`: listening, thinking, speaking, paused | Lets the idle timer run only while listening |
| `tts_stream_start` | `speech_id`, `language`, `interruptible` | Open a speech stream; a new one replaces the old |
| `tts_text` | `speech_id`, `text` | Reply text (source lines are stripped; capped at `VOICE_TTS_MAX_CHARS_PER_REPLY`) |
| `tts_end` | `speech_id` | No more text |
| `tts_cancel` | `speech_id` | Stop speaking now; stale ids are ignored |
| `ping` | none | Keep-alive, answered with `pong` |

Server to client:

| Event | Fields | Meaning |
| --- | --- | --- |
| `voice_ready` | `live_stt_supported`, `tts_stream_supported`, `sample_rate`, `tts_sample_rate`, `max_frame_bytes`, `max_session_seconds`, `idle_timeout_seconds`, `max_utterance_seconds` | Capabilities and bounds |
| `voice_session_started` | `model`, `sample_rate` | Frames are now accepted |
| `speech_started` | none | The patient began speaking |
| `transcript_partial` | `transcript`, `language` | Live words, replaced by each update |
| `utterance_final` | `utterance_id`, `transcript`, `language`, optional `safety_guidance` | One finished utterance |
| `tts_start` | `speech_id`, `encoding` linear16, `sample_rate`, `interruptible` | Audio follows |
| `tts_audio` | `speech_id`, `seq`, `audio_base64` | PCM chunk; may split a sample, so the player carries the odd byte |
| `tts_end` | `speech_id`, `truncated` | All audio sent |
| `tts_cancelled` | `speech_id`, `reason` | Barge-in, client cancel or replacement |
| `tts_error` | `speech_id`, `reason` | Provider failed; reply stays text |
| `voice_session_ended` | `reason`: client, max_session, idle_timeout, provider_closed, socket_closed | Session over |
| `voice_error` | `code`, `message` | `voice_live_unavailable` and `voice_live_busy` are fatal for voice mode; frame, validation and duplicate-start errors are not |

The legacy `audio_start` / `audio_chunk` / `audio_stop` / `audio_final` / `tts_request` flow
remains for the per-message "Listen" button and private symptom-intake dictation.

## Limits and configuration

All values have defaults in `backend/src/app/config.py`; every one is a bound.

| Setting | Default | Meaning |
| --- | --- | --- |
| `VOICE_LIVE_ENABLED` | true | Master switch for live STT |
| `VOICE_TTS_STREAM_ENABLED` | true | Streaming speech |
| `VOICE_LIVE_SAMPLE_RATE` / `VOICE_TTS_SAMPLE_RATE` | 16000 / 24000 | Wire rates |
| `VOICE_LIVE_MAX_SESSION_SECONDS` | 900 | Hard session limit; portal shows a countdown in the last 2 minutes |
| `VOICE_LIVE_IDLE_TIMEOUT_SECONDS` | 60 | Silence while listening ends the session |
| `VOICE_LIVE_MAX_UTTERANCE_SECONDS` / `_CHARS` | 45 / 2000 | A very long utterance is flushed |
| `VOICE_LIVE_AUDIO_QUEUE_FRAMES` / `_MAX_FRAME_BYTES` | 64 / 32768 | Bounded queue; frames are shed, never buffered without limit |
| `VOICE_LIVE_MAX_SESSIONS` | 20 | Streaming sessions per process (bulkhead); also one per patient |
| `VOICE_TTS_MAX_CHARS_PER_REPLY` / `_SENTENCE_MAX_CHARS` | 2500 / 240 | Speech bounds |
| `DEEPGRAM_ENDPOINTING_MS` / `DEEPGRAM_UTTERANCE_END_MS` | 500 / 1200 | End-of-speech tuning |

Cloud Run environment:

- `mediagent-backend`: **`DEEPGRAM_API_KEY` must be set** (it already is for the existing
  voice features; it is configured out of band, not in the deploy workflow). The Spanish and
  English voices default to `aura-2-estrella-es` and `aura-2-asteria-en`. **No new variable
  is required: the defaults above suffice.** `VOICE_LIVE_MAX_SESSIONS` is optional.
- `mediagent-chat-worker`: **nothing**. The worker only runs chat turns; the voice websocket
  is served by the backend service, and the worker never calls Deepgram.
- Portal (Vercel): nothing new; it uses `NEXT_PUBLIC_BACKEND_URL` as before. The websocket
  must be reachable on that origin. The backend service request timeout is already 3600 s in
  `deploy-backend.yml`, which exceeds the 900 s session limit.

## Failure modes

| Condition | Behaviour |
| --- | --- |
| Microphone permission denied, no microphone, unsupported browser | Inline sentence with "Try again" and "Use text instead"; no tracks left open |
| Live STT disabled, key missing, provider connect failure, capacity reached | `provider_unavailable` message; chat keeps working by text |
| Speech stream fails or never starts (12 s) | Notice that the reply is in the chat; back to listening |
| Chat turn fails or no reply within 2 minutes | Notice; back to listening; the chat shows the failure and retry |
| Chat socket not ready when an utterance finalizes | Words are placed in the composer, never dropped; notice |
| Voice socket drops | One automatic reconnect with the microphone kept open; a second drop exits voice mode cleanly with a message |
| Session limit or idle timeout | Message and exit; the thread is unchanged |
| Tab hidden over 60 s, conversation changed, sign-out, unmount | Voice mode ends and releases the microphone |
| Typed chats | The per-message Listen button and dictation button are unchanged |

## Safety

Transcripts are ordinary chat messages: the deterministic emergency/crisis floors and the
model path run exactly as for typed text. `utterance_final` also carries the floor's guidance
computed on the transcript; the panel shows it as a persistent alert. An urgent reply keeps
the existing banner and is spoken in full without interruption. No transcript or reply text is
logged: voice logs carry lengths, `utterance_id`, `speech_id` and outcomes only. The
session, not the browser, enforces the length, idle and concurrency bounds. Synthetic data
only; this is not a statement of HIPAA or production readiness.

## Related chat fixes in this branch

- **Message delay:** the backend saves the patient message and sends `user_message_saved`
  and the turn snapshot before enqueueing the worker task; the portal shows the message
  immediately as pending with a Retry/Remove state if the connection drops.
- **Visit-aware Nora:** the context Nora reads (`get_patient_context`, fresh on each call, on
  both the in-process and worker turn paths since it is an agent tool) now includes upcoming
  visits (confirmed, scheduled, open offers and change requests, from now on, rendered in
  the patient's saved time zone, for example America/Los_Angeles), allergies and today's care-plan
  activities. The production defect: Visits showed a confirmed 9:00 AM visit tomorrow while
  Nora said there were none. Covered by `test_chat_context_appointments.py`.

## es-MX wording drafts — not approved

Source: `getVoiceModeCopy` in `apps/patient-portal/src/content/chat-copy.ts`. Every row is
**Draft; pending LOC-001 bilingual review**, to be approved with the English together.

| Key / English | es-MX draft |
| --- | --- |
| start / Voice conversation | Conversación por voz |
| panel / Voice conversation with Nora | Conversación por voz con Nora |
| connecting / Connecting voice… | Conectando la voz… |
| listening / Listening. Speak whenever you are ready. | Te escucho. Habla cuando quieras. |
| hearing / Hearing you… | Te estoy escuchando… |
| thinking / Nora is thinking | Nora está pensando |
| speaking / Nora is speaking. Talk to interrupt. | Nora está hablando. Habla para interrumpir. |
| paused / Microphone paused | Micrófono en pausa |
| pause, resume, end / Pause, Resume, End voice mode | Pausar, Reanudar, Terminar modo de voz |
| remaining / m:ss left in this voice session | Quedan m:ss en esta sesión de voz |
| permission_denied | El acceso al micrófono está bloqueado. Permítelo en la configuración del navegador o usa texto. |
| no_microphone | No encontramos un micrófono. Conecta uno o usa texto. |
| unsupported | Este navegador no permite la conversación por voz. Puedes usar texto. |
| provider_unavailable | La voz no está disponible en este momento. Puedes seguir por texto. |
| network | Se perdió la conexión de voz. Revisa tu conexión o usa texto. |
| session_limit | La sesión de voz llegó a su límite de tiempo. Puedes iniciar otra o usar texto. |
| idle_timeout | Cerramos la voz porque no se oyó nada por un rato. Puedes iniciarla de nuevo o usar texto. |
| failed | No se pudo iniciar la voz. Inténtalo de nuevo o usa texto. |
| speech_unavailable | La respuesta de Nora está en el chat. El audio no está disponible ahora. |
| not_sent | No se pudo enviar ese mensaje. Quedó en el cuadro de mensaje para que lo envíes. |
| reply_failed | Nora no pudo responder a eso. Tu mensaje quedó guardado en el chat. |
| tryAgain, useText | Intentar de nuevo, Usar texto |

## Acceptance path

Automated (recorded in the pull request): backend lint, format, mypy, focused and full unit
tests; portal lint, typecheck, vitest and `next build`. The controller, audio port, panel and
hook tests use mocked `getUserMedia`, `AudioContext` and `WebSocket`; they do not prove real
audio.

Deployed live check, synthetic patient, both locales, on a phone and a desktop browser:

1. Typed message appears instantly; then ask "when is my next appointment" with a confirmed
   visit tomorrow: Nora names the visit, date and time in the patient's time zone.
2. Open voice mode (en-US): allow the microphone, speak a question. Partial words appear,
   the final words become a normal message, Nora is thinking, the reply text appears and is
   spoken, then it returns to listening on its own. Repeat in es-MX (Spanish speech under
   either app language).
3. Speak while Nora is talking: audio stops at once and the new question is heard.
4. Emergency phrase: banner and guidance stay visible and the reply is spoken in full.
5. Deny the microphone: inline message, typing still works. Unplug or disable audio provider
   (not in production): text fallback notice.
6. Pause and Resume; End voice mode releases the microphone (browser indicator goes off).
7. Second tab and reload mid-turn: the thread recovers; no duplicate message.
8. Session limit hint appears in the last two minutes, if testable with a lowered limit.
