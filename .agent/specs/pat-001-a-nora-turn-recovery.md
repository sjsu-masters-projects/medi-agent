# PAT-001-A / PAT-004 — Durable Nora turns and document focus

Status: **Verify deployed**. [#188](https://github.com/sjsu-masters-projects/medi-agent/pull/188)
merged as `6026647` on October 17, 2026 (Pacific); PR checks passed. The requester
confirmed migrations **072**, **073** (#189) and **074** (#192) applied. Backend deployment and both Vercel deployment
statuses and main CI succeeded for the merge commit.
Live acceptance and bilingual wording review below remain unrecorded. Current release
status belongs in [TASKS.md](../TASKS.md), not a duplicate rollout log here.

OPS-006 phase 1 (branch, not deployed): completion payloads no longer let the reply's `id`
replace the turn id, refusals carry a `reason` (migration 077), and every turn transition is
logged by `turn_id`; see [OPS-006](ops-006-workers-and-event-stream.md).

OPS-006 phase 2 (branch `feature/ops-006-phase-2`, not deployed, behind `CHAT_TURNS_VIA_WORKER`): a
turn can be `queued` (migration 078) and executed by a worker service instead of an API instance.
The contract above is unchanged: the same client message id, request hash, lease, deadline,
`actions_started` rule, three-attempt limit, document snapshot and completed-reply replay apply.
What differs: the API saves the message and the queued turn in one transaction and enqueues a
task after commit (a sweep re-enqueues a missed one); the worker claims the turn (a live lease or
a started clinical action is never re-run), runs the same pipeline and completes with its lease;
a queued turn nobody claims is interrupted at its deadline and offers the usual retry. Sockets and
recovery show the draft and the final reply from `chat_turn_events` on any instance. Emergency and
crisis guidance still comes from the deterministic safety floor, shown from the turn's own status
event whether or not a worker is available. Setup and rollback: [chat-worker-setup](../../docs/chat-worker-setup.md).

## Scope

One increment covers the saved chat-turn lifecycle and document focus. Human
care-team messaging, LOC-003 translations and PAT-002-B symptom intake remain
unchanged. Use synthetic tests only; preserve existing conversations and sources.

## Contract

- Network loss closes the stale view, pauses reconnection attempts while offline
  and preserves the saved turn. Connectivity restoration re-subscribes with the
  current token; it never resends a user message automatically. A visible,
  handshaken socket uses the existing ping/pong protocol every 15 seconds; a
  missed response closes it for normal bounded recovery. Hidden tabs do not
  fail heartbeat checks merely because their timers were throttled.

- A client-generated UUID identifies one patient/session turn and its exact text,
  language and selected document. Reusing it with different content is rejected.
- Save the user message once and persist processing/completed/failed/interrupted
  state. Concurrent sends cannot execute the same turn twice or interleave turns
  in the same conversation. A completed retry replays the saved answer.
- Generation has a bounded deadline. Expired processing is reconciled on recovery.
  A retry resumes the same saved message, not a new user message.
- A turn which may already have executed a clinical side effect is not blindly
  re-executed. Preserve the uncertainty and direct follow-up rather than creating
  another symptom report, delegation or clinical alert. Read-only turns are retryable.
- Document context belongs to the submitted turn and is authorized again at send
  time. Store its source identity/version, never a private/signed source URL or
  duplicate summary text. Return the authorized summary only to execution.
  Missing, deleted, unprocessed or summary-less documents produce an explicit
  unavailable-context response, never silent chart-wide fallback.
- Attach/dismiss/replace changes only the intended future turn. Refresh/reconnect
  restores the selected conversation; stale socket events cannot overwrite it.
- Retry and recovery states use en-US/es-MX UI copy. Emergency guidance, recorded
  messages, clinical approval and safety rules are not weakened or retranslated.

## Verification and rollout

Test duplicate/concurrent sends, retry after timeout/disconnect, process restart,
changed-payload conflicts, action uncertainty, completed-answer replay, patient and
document isolation, expired documents, focus replacement/dismissal, cross-tab state,
and English/Spanish feedback. Run focused backend tests, PostgreSQL permission/race
tests with hosted-style default grants, Ruff/mypy, portal tests/lint/typecheck/build.
Record exact outcomes here, not claimed live acceptance.

Any new migration must be reviewed and separately authorized before remote
application; deployment and merge are not authorized by this document. Compatibility
for older clients must be explicit, not an implicit fallback after a failed write.

## Acceptance path

Send once → interrupt/reload → recover saved turn → retry when safe → one saved
answer and no duplicate action. Repeat with a document, then switch/dismiss it and
confirm a later general question cannot inherit the previous document.

## Implementation and verification evidence — October 17

Implemented in #188: server-owned turn claims, bounded leases,
safe duplicate replay, per-turn document snapshots, patient recovery controls and
conversation URLs. An interrupted reply may be left unfinished; that dismissal does
not complete clinical work. Recovery refreshes every five seconds while there is
unfinished work and the page is visible, and on focus. Unacknowledged requests remain
retryable under the same identity; rejected claims restore the editable text. Pending
text/audio stays in memory, not localStorage/sessionStorage. Existing saved voice
attachments remain supported.

Compatibility: updated clients explicitly request `turn_protocol=1` and keep sending
disabled until the server's recovery handshake arrives. A 15-second handshake timeout
stops in an explicit unavailable state with manual reconnect, without submitting
work to an older backend. Legacy sockets
keep their old behavior, without a durable-retry guarantee. New sockets do not fall
back to legacy execution if the migration/store is unavailable. Rollout order is
reviewed migration **072** → merge/backend → patient portal. 071 belongs to visit
management. Application of 072 is requester-confirmed; no independent remote ledger
audit was performed for this reconciliation.

Local checks:

- Patient `npm run lint`, `npm run typecheck`: pass.
- Patient `npm run test -- --reporter=json`: 710 passed on current main plus review
  fixes; focused chat suite: 79 passed.
- Backend dummy-config `PYTHONPATH=src .venv/bin/pytest` on `test_chat_turn_recovery`,
  `test_chat_api`, `test_chat_document_focus`, `test_chat_websocket_stability` and
  `test_chat_emergency_copy` under `tests/integration/routers`, `--no-cov -q`: 56 passed.
- `CHAT_TURN_TEST_POSTGRES_DOCKER=1` with the same dummy config, isolated
  `tests/integration/test_chat_turn_postgres.py --no-cov -q`: 18 passed, including
  duplicate/concurrent claims, stale leases, action uncertainty, ownership, foreign,
  unprocessed and deleted documents, dismissal, completed-reply discovery, reruns,
  security postconditions, malformed privileged sources and the three-attempt limit.
- Ruff check/format on changed Python: pass; focused mypy on the router and two
  services: pass. `backend/scripts/validate_migrations.py`: 85 migration files pass.
- Patient default Turbopack build is blocked by a worker-port restriction in this
  environment. `SENTRY_AUTH_TOKEN='' npm run build -- --webpack`: passes, with no
  application configuration change or deployment.

Still required before Done: the synthetic deployed acceptance path above, including
two-tab busy recovery, plus bilingual review of the Spanish drafts below.
Actual authenticated mobile screenshots,
keyboard/reduced-motion review, and a browser-disconnect check have not been recorded
locally. Human messaging, LOC-003 and PAT-002-B are untouched.

Recovery preserves the existing deterministic, reviewed emergency and crisis guidance
for processing/interrupted turns, including after a timeout or reload. It is never
inferred from model fragments or newly translated. Completion returns to the saved
answer; clinical actions and escalation remain the existing workflow.

## Review decisions and known boundaries

- 072 re-runs table/index/function creation and permissions safely, preserves turns,
  and ends with assertions against browser access and disabled RLS.
- Summary retention in `chat_turns` is **zero**. Only source identity, display metadata
  and content-version hash persist. Retry re-reads the authorized matching source;
  execution uses the existing plain-text cleanup. Re-running 072 removes any old
  duplicate `summary` key. Document deletion leaves no summary text in a turn.
  Metadata remains with the conversation until message/patient deletion. Existing
  transcript, conversation-focus and provider-processing retention are not changed
  or claimed erased here.
- Busy claims preserve the new text in the composer, explain the existing reply and
  recover saved history/status. They never resubmit the new question automatically.
  Disabled Retry controls explain connection/in-progress blocking.
- Privileged direct inserts are unsupported: use the RPC. Ownership/session/role
  mismatches in linked messages fail closed. Corrupt privileged data, including a
  deleted reply behind a completed marker, can require operator repair; it must not
  regenerate an already-completed turn. Browser privileges remain revoked.
- Conversation summary/count metadata is best effort and can lag after an optimistic
  conflict. Saved messages/turns remain authoritative.
- Streamed text is provisional (the existing Live response label). Text received
  before timeout can briefly appear and later be discarded. No late reply commits;
  partial text authorizes no clinical actions. Reviewed safety guidance is independent.
  No client/server clock-synchronization guarantee is claimed.
- Phone screenshots, deployed disconnect/reload and Spanish review remain unrecorded.
  Local or reviewer-reported passing suites do not satisfy those live checks.

## Pending es-MX interface wording drafts — not approved

Source: `apps/patient-portal/src/content/chat-copy.ts` (`getChatRecoveryCopy` and
`getChatControlsCopy.documentUnavailable`). Every row is **Draft; pending LOC-001
bilingual review**, not clinician-approved clinical instructions. Emergency/crisis
copy is reused unchanged from the existing reviewed resources.

| Copy key / English intent | es-MX draft |
| --- | --- |
| preparing / Preparing reply | Nora está preparando tu respuesta |
| checking / Checking message | Comprobando el estado de tu mensaje |
| interrupted / Interrupted reply | La respuesta quedó incompleta |
| uncertain / Action may be recorded | Es posible que se haya registrado una acción. No la repetiremos automáticamente. Si necesitas ayuda, contacta a tu equipo de atención. |
| returnLater / Return to conversation | Puedes volver a esta conversación. La respuesta se mostrará cuando esté guardada. |
| safeRetry / Retry same message | Puedes reintentar el mismo mensaje sin enviarlo dos veces. |
| noRetry / Continue with new question | No volveremos a ejecutar este mensaje. Puedes continuar con una pregunta nueva. |
| retry / Retry message | Reintentar mensaje |
| leaveUnfinished / Leave reply unfinished | Dejar esta respuesta incompleta |
| reconnectBeforeRetry / Reconnect first | Vuelve a conectar el chat para reintentar este mensaje. |
| waitBeforeRetry / Wait for current reply | Espera a que termine la respuesta en curso antes de reintentar este mensaje. |
| busy / Existing reply, draft preserved | Ya hay una respuesta en curso en esta conversación, posiblemente en otra pestaña. Estamos recuperándola. Tu nuevo mensaje sigue en el cuadro de texto. |
| unavailable / Chat unavailable | Nora no está disponible en este momento. No se enviará ningún mensaje hasta que el chat vuelva a conectarse. Puedes reintentar la conexión. |
| reconnect / Reconnect chat | Volver a conectar |
| replyUnavailable / Completed reply no longer saved | La respuesta de esta conversación ya no está disponible. No la volveremos a ejecutar. Puedes continuar con una pregunta nueva. |
| documentUnavailable / Dismiss unavailable context | Este documento no está disponible o cambió. Desvincúlalo antes de hacer una pregunta sobre el resto de tu expediente. |

### Past-conversations list wording drafts — not approved

Source: `apps/patient-portal/src/components/features/nora-conversations.tsx`. Draft; pending LOC-001 bilingual review.

| Copy key / English intent | es-MX draft |
| --- | --- |
| unfinished / Reply unfinished | Respuesta incompleta |
| replying / Nora is replying… | Nora está respondiendo… |

## Cross-tab discovery

`GET /chat/conversations/{patient_id}` merges `chat_conversation_states` with the patient's
`chat_turns` sessions (two patient-scoped queries, merged by session id, ordered by latest
activity). A session whose latest, non-dismissed turn is processing, failed or interrupted
returns `status: "needs_attention"` (`reply_in_progress` while still within its deadline).
The title falls back to the first user message and is also set at turn begin.

## Production recovery fixes (#189, merged)

- Logs: the turn failure category (exception type, safe code, cause type) is in the message text,
  and every turn RPC failure logs its action and Postgres code; no patient text.
- Reconnect churn: the chat socket depended on the access-token and user objects, so every silent
  session refresh rebuilt it, and a token inside the 30-minute refresh window re-triggered the
  refresh at once. The socket now keys on user id only; refreshes are floored at 5 minutes apart.
  The server never cancels a turn when its socket closes, so a reconnecting client reattaches to
  the processing turn through `recover_turns` and spends no attempt.
- State refresh after commit retries on conflict (never lowering `turn_count`) and logs its category.
- `public_turn` serializes `user_message` like history. Migration 073 rejects NULL
  content/language/client id explicitly and replays a completed turn whose reply row is gone as
  `reply_unavailable`. Socket startup and recovery failures send explicit errors instead of raising.
- Lost completion confirmation: after a failed turn the server sends saved history when the turn
  turned out completed. Another tab's processing turn is polled (5 s, at most 60 times, only
  while in flight). Streamed drafts clear on interruption and on socket close.
- Not a defect: the retry never re-feeds its failed attempt; the turn's own user message is
  excluded from history (covered by `test_disconnected_socket_does_not_discard_reply...`).

## Production fix: expired turns and starved saves (#192, merged; migrations 074 and 075 applied)

Evidence (October 18, 06:40-06:46 UTC, one synthetic patient): every turn logged
`ValidationError/CHAT_TURN_EXPIRED` one to four seconds after its socket opened, far inside the 45
second lease, and the patient saw the generic "Could not load or complete the conversation". The
same minutes held 2.5 to 8.6 second notification reads on a five-thread worker pool.

- Cause 1, shared threads: every blocking database call used `asyncio.to_thread`, whose default
  pool is `min(32, cpu + 4)` = 5 threads on the one-vCPU backend. Overlapping notification reads
  (see NOT-001) held all five, so a turn's begin, history, actions and save queued behind them.
  Chat-turn RPCs now run on their own four-thread pool and notification reads on a three-thread
  pool (`app/core/db_pools.py`); neither can starve the other or the default pool.
- Cause 2, a lease with no room to save: the lease was `timeout + 5` = 45 s while the processing
  budget (`asyncio.timeout`) was 40 s and wrapped the save call too. A reply finishing near the end
  had five seconds for a call that may itself wait ten. The lease is now the processing budget plus
  a 30 s save grace (`turn_budget`: 40 s and 70 s with the default `CHAT_TURN_TIMEOUT_SECONDS=30`,
  never above the 120 s database limit) and the save runs outside the processing budget.
- Cause 3, a finished reply was thrown away: `complete` required `status='processing'`, so a lease
  that lapsed (deadline, or a lost socket marking the turn interrupted) rejected a good reply.
  Migration 074 accepts `complete` for the current lease while the turn is processing, or
  interrupted with no reply and no dismissal, and returns `late: true`; the service logs it
  (turn id only). A lease replaced by a retry, a dismissed turn and a failed turn are still
  refused, so a turn never gets two replies. `actions` stays strict: no new clinical action starts
  on a lapsed lease. A reply after an uncertain action is kept; the action is never repeated.
- Cause 4, wording: `CHAT_TURN_EXPIRED` now sends its own fixed message and the portal shows
  "That reply took too long and was not kept. Your message is saved: use Retry message below."
  (en-US and es-MX) while the server's turn list supplies the retry card. A retry reuses the saved
  message and the same turn row (attempt plus one, at most three; never after an action started).
- Not fully proven from the logs: which exact overlap replaced or lapsed the lease within seconds.
  The fixes above remove each plausible path (starved calls, short lease, strict completion); the
  deployed recheck should look for `after its turn lease lapsed` and for any remaining
  `CHAT_TURN_EXPIRED`.
- Tests: `test_chat_turn_postgres.py` (deadline maths and clamps, late completion once, refusal
  after retry/dismissal/failure, actions stay strict, 074 re-run and grants), router tests with a
  slow model and a slow save, and pool-isolation unit tests.

## Server-owned turns (branch `feature/server-owned-chat-turns`)

Evidence (October 18, revision 00159-46c, which includes #192): four sockets for one session
opened within 14 seconds, each after fresh history and profile reads; the model started at
08:34:29.8 and `CHAT_TURN_EXPIRED` was logged 1 s after a new socket opened and again 12 s later.
Cause: the turn lived inside the websocket handler, so a closed socket marked it interrupted and
the next lease-checked step (`actions`) was refused.

Decision (requester): a reply is owned by the server and can never be killed by the browser
connection.

Design:

- `TurnRunner` (`app/services/chat_turn_runner.py`) holds each turn as an `asyncio` task keyed by
  turn id. The handler begins the turn, starts the task and returns to its receive loop. It never
  fails, interrupts or cancels the turn on close or error. The task completes with its lease, or
  fails on a real model or database error. Deadlines and leases are the safety net if an instance dies;
  reconciliation (072-074) and retry are unchanged. No SQL changed.
- Sockets are viewers: per-viewer queues, the draft so far for a late subscriber, then live
  events. Errors go to the requesting socket only; history and turn status go to every viewer.
  Other instances or a restart use `recover` and the existing bounded poll.
- Shutdown drains running turns for 8 seconds (lifespan). Leftovers are marked interrupted
  best-effort, else reconciled by the deadline.
- `deploy-backend.yml`: `--no-cpu-throttling` on the main service only (requester decision).
  Cost: CPU is billed whenever an instance exists, not only while serving requests. Instances
  still scale to zero (`--min-instances 0`); the jobs are untouched.
- Client: the socket depends on patient and conversation (plus an explicit reconnect after a
  real close). Document attach/dismiss and URL search-param changes no longer rebuild it; focus
  changes use a `document_focus` event, and the focus is read once per connection. A reconnect
  to the same conversation keeps the screen, never reports a closed socket as a failed reply,
  and re-subscribes to the draft. The tab receiving the stream shows only "Nora is typing";
  the "Nora is preparing your reply" card shows only in a tab not receiving the stream.

Failure modes: instance death mid-turn (deadline reconciliation, then Retry); an instance stuck
with CPU throttled (mitigated by the flag); a viewer more than 2000 events behind is dropped and
recovers from the saved turn; a second message while a reply runs is refused as busy; a draft is
provisional until `assistant_complete`. The exact production re-mount trigger is not proven: the
socket effect rebuilt on document focus changes and on every reconnect (clearing state and
refetching history), which matches the repeated history reads; neither can now stop a reply.

Tests: `test_chat_server_owned_turns.py` (close mid-reply completes with no expiry, second viewer
gets draft then rest, empty registry on another instance, registry cleanup, dead viewer dropped,
shutdown drain and leftover, real model error fails, lapsed-lease actions already covered in
`test_chat_turn_recovery.py`), and portal tests for one socket across search-param changes, the
typing-only streaming tab, the recovery card in a non-receiving tab, and reconnect.

**Queued turns and calm status (October 19):** `queued` is a first-class turn status (shared with processing as "in progress": send disabled, no retry; any unrecognised status is also treated as in progress, never as interrupted). Exactly one element shows a turn's progress: the typing indicator in the tab that sent it, the draft once streaming, or the "Nora is preparing your reply" card in a reloaded or second tab (and in any tab offline for more than 3 s); "interrupted" appears only for a turn saved as failed or interrupted. A socket drop keeps the screen, shows nothing for 3 s, then a subtle "Reconnecting…" (es-MX draft: "Reconectando…") beside the connection label; a token refresh no longer remounts the page.

**Inline progress in every tab (October 19):** a turn in progress renders one element, inline below its user message at the bottom of the thread (the "Nora is typing…" bubble, replaced by the draft; after about 15 s with no draft a small note "You can leave; the reply will appear here.", es-MX draft "Puedes salir; la respuesta aparecerá aquí."); the top-of-thread "preparing" card is removed, failed and interrupted cards render inline too, and a tab the socket does not feed polls the turn events about every second while visible, stopping on a terminal status or the turn deadline.
