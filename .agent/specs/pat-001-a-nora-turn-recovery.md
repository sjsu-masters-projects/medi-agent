# PAT-001-A / PAT-004 — Durable Nora turns and document focus

Status: implemented and locally verified October 17, 2026; PR/CI and authorized rollout remain.

## Scope

One increment covers the saved chat-turn lifecycle and document focus. Human
care-team messaging, LOC-003 translations and PAT-002-B symptom intake remain
unchanged. Use synthetic tests only; preserve existing conversations and sources.

## Contract

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

## Local implementation and review checkpoint — October 17

Implemented on `codex/nora-turn-recovery`: server-owned turn claims, bounded leases,
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
management. No remote step has been run.

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

Still required before Done: PR review/CI, an authorized migration/rollout, and the
synthetic deployed acceptance path above. Actual authenticated mobile screenshots,
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
