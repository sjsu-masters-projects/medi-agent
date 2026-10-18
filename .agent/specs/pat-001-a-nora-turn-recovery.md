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
  time. Store its source identity/version, never a private/signed source URL.
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

Compatibility: updated clients explicitly request `turn_protocol=1`. Legacy sockets
keep their old behavior, without a durable-retry guarantee. New sockets do not fall
back to legacy execution if the migration/store is unavailable. Rollout order is
reviewed migration 071 → backend → patient portal. No remote step has been run.

Local checks:

- Patient `npm run lint`, `npm run typecheck`: pass.
- Patient `npm run test -- --reporter=json`: 695 passed; focused chat suite: 71 passed.
- Backend dummy-config `PYTHONPATH=src .venv/bin/pytest` on `test_chat_turn_recovery`,
  `test_chat_api`, `test_chat_document_focus`, `test_chat_websocket_stability` and
  `test_chat_emergency_copy` under `tests/integration/routers`, `--no-cov -q`: 45 passed.
- `CHAT_TURN_TEST_POSTGRES_DOCKER=1` with the same dummy config, isolated
  `tests/integration/test_chat_turn_postgres.py --no-cov -q`: 12 passed. Includes
  duplicate/concurrent claims, stale leases, action uncertainty, ownership, foreign,
  unprocessed and deleted documents, dismissal and completed-reply discovery.
- Ruff check/format on changed Python: pass; focused mypy on the router and two
  services: pass. `backend/scripts/validate_migrations.py`: 84 migration files pass.
- Patient default Turbopack build is blocked by a worker-port restriction in this
  environment. `SENTRY_AUTH_TOKEN='' npm run build -- --webpack`: passes, with no
  application configuration change or deployment.

Still required before Done: PR review/CI, an authorized migration/rollout, and the
synthetic deployed acceptance path above. Actual authenticated mobile screenshots,
keyboard/reduced-motion review, and a browser-disconnect check have not been recorded
locally. Human messaging, LOC-003 and PAT-002-B are untouched.
