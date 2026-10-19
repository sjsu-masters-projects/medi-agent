# OPS-006 — Worker service, turn events and one live stream

Status: accepted October 19, 2026 ([decision record](../../docs/decisions/realtime-and-workers-2026-10.md)).
Owner: Rajeev. Supersedes the connection-bound parts of PAT-001-A and the read-time notification
computation in NOT-001. Each phase is one PR with a live production check before the next starts.

## Concurrency and distributed-systems rules (all phases)

These rules are acceptance criteria. Reviews check them.

**State and ownership**
1. The database is the only source of truth. No correctness depends on in-process memory (registries, caches or queues are optimisations only), because Cloud Run runs many instances and any instance can stop at any time.
2. Every state change is a guarded transition: `UPDATE … WHERE id=$1 AND status=$expected [AND lease=$lease]`, checked by row count or `RETURNING`. Never read-then-write without a lock or a conditional write. Terminal states (completed, failed, dismissed) are never left.
3. One owner per running unit of work: a turn or task is held by a lease (`lease` UUID plus `deadline_at`). Only the lease holder may write progress or a result. Ownership changes only through an explicit transition (retry, reconcile), never by overwriting.

**Idempotency and delivery**
4. Every externally triggered operation has an idempotency key (`client_message_id`, task name, event id). Repeating it returns the same result and never repeats a side effect.
5. Assume at-least-once delivery for queues, retries, sockets, SSE and HTTP retries. Consumers de-duplicate (unique keys, `ON CONFLICT DO NOTHING`, seq numbers). Clinical side effects run at most once (`actions_started`, guarded by the lease).
6. Use a transactional outbox for "write plus notify": the notification or event row is written in the same transaction as the state change, and delivery happens after commit. Never notify about uncommitted state.

**Locks**
7. Global lock order, always acquired in this sequence and never reversed: clinic → clinician(s) by id → patient-scoped advisory locks (evidence, conversation pair, notification prepare) → rows by primary key ascending. A new lock site must state where it fits.
8. Locks are short and transaction-scoped (`pg_advisory_xact_lock`, `SELECT … FOR UPDATE`). No lock is held across a network call, a model call, a sleep or a user wait.
9. Authorize before taking contended locks (lock-free pre-check), so an unauthorized caller cannot queue behind or delay others.
10. Use `NOWAIT` or `SKIP LOCKED` for work claiming. Set `lock_timeout` and `statement_timeout` on every database role and session the backend uses, so nothing waits forever.

**Timeouts, budgets and backpressure**
11. Every outbound call (database, model, email, HTTP) has a timeout, and the per-request budget is smaller than the caller's budget: client > API > queue task > worker step > database statement.
12. Retries use bounded exponential backoff with jitter, only for retryable errors, and are capped by the remaining budget. Never retry a non-idempotent call without its idempotency key.
13. Bulkheads: separate thread pools or connection pools per workload (chat turns, notifications, default), and separate queues per job type, so one slow dependency cannot starve another. Queue concurrency and rate limits are explicit config.
14. Load shedding: when a pool or queue is saturated, reject fast with a retryable error (429/503 with `Retry-After`) rather than queueing without bound. In-memory queues are bounded (for example, a viewer event queue drops the viewer, not memory).

**Async and threads**
15. Never block the event loop: synchronous database or SDK calls go through the designated pool (`asyncio.to_thread` with a named executor). CPU-heavy work goes to the worker service.
16. Tasks started outside a request are tracked (strong reference, registry), cancellation-safe (`try/finally` releases resources) and drained on shutdown. No fire-and-forget without supervision.
17. Shared in-process structures are touched only from the event loop thread, or protected by a lock. No mutable globals across threads.

**Time and ordering**
18. Deadlines and leases use the database clock (`clock_timestamp()`), never client or instance clocks. Durations inside the process use monotonic time.
19. Ordering comes from sequence numbers (per turn, per user stream), not timestamps. Consumers resume from the last seq (`Last-Event-ID`).

**Failure handling and recovery**
20. Every in-flight state has a recovery path: a deadline reconcile moves an abandoned `processing` turn to `interrupted`, a stuck task is retried by the queue, and a dead stream reconnects and resumes.
21. Partial failure is explicit: an operation that may or may not have happened (for example, a save timeout) is reconciled by reading the source of truth, never assumed.
22. Circuit breakers or fallbacks for the model provider (existing fallback routes). Deterministic safety floors never depend on the model or the queue being available.

**Security across boundaries**
23. Every service boundary authenticates: Cloud Tasks OIDC on the worker, user JWT on the API and the stream. The worker re-validates ownership from the database, never trusting task payload claims alone.

**Observability**
24. Every log line in a request, task or turn carries `request_id`, `turn_id` or `task_id`, as appropriate. State transitions, lock timeouts, retries, load shedding and rejections are logged with a reason. No PHI in logs.

## Phase 1 — Traceability and the current expiry (small)

**Status (branch `feature/ops-006-phase-1`, not merged or deployed):** implemented and locally
verified; the production check below is still required.

- Done: migration `077` (rejection `reason`, per-function `lock_timeout` 5 s and
  `statement_timeout` 8 s); structured JSON logging, request and websocket middleware; turn
  lifecycle log events with the `trigger` of every state change; bounded worker pools that shed
  load with `503` and `Retry-After`; one shared 60-second poller per data type per tab in both
  portals, with ADR requests on the same cadence.
- **Found and fixed:** `TurnExecution.finish` merged the staged reply into the completion
  payload after the turn identity, so the reply's own `id` replaced the turn id and the database
  looked up a turn that did not exist. Proven by a faithful stand-in of the 077 function
  (`tests/integration/routers/test_chat_turn_expiry_candidates.py`), not yet by a production
  log: the deployed `reason` (`not_found` on `complete`) will confirm it. The other candidates
  (second socket recover or dismiss, same-message begin, session normalization, provider
  fallback, a second begin after a lapsed lease) are tests that must not refuse a live lease,
  and they pass; only a replaced lease is refused, now logged as `lease_mismatch`.
- Apply order: `077` before or after the backend deploy (an old function returns no reason and
  the backend logs `unknown`). Apply `077` first to see reasons.


**Goal:** a single failing Nora turn can be explained from the logs alone, and the current
`CHAT_TURN_EXPIRED` is fixed.

- **Structured JSON logging** (Cloud Logging `jsonPayload`):
  - fields: `severity`, `message`, `request_id`, `turn_id`, `session_hash`, `actor_hash`
    (salted hash, never raw ids of patients in text), `event`, `outcome`, `duration_ms`;
  - no patient text;
  - request and socket middleware set `request_id`;
  - Cloud Trace context is propagated.
- **Turn rejections explain themselves.** When a turn operation is rejected (`accepted=false`),
  the database returns why: `not_found`, `status:<status>`, `lease_mismatch`, `session_mismatch`
  or `deadline_passed`. The service logs the reason with the operation name. The user-facing
  code stays generic.
- **Turn lifecycle log lines:** begin, model start and end (latency), actions, complete, fail,
  each with `turn_id`.
- **Fix:** identify the cause of the October 19 `CHAT_TURN_EXPIRED`, which occurred 2–8 s into
  replies with long-lived sockets, from the rejection reason. Fix it, with a regression test.
- **Polling interim fix:** confirm a single shared notification poll per tab, with no
  per-screen duplicates. ADR requests are fetched once per minute, not continuously.
- **Done when:** a production test turn completes, and every turn's outcome is visible in Cloud
  Logging by `turn_id`.

## Phase 2 — Worker service and turn events (large)

- **Turn event table** `chat_turn_events(turn_id, seq, type, payload, created_at)`, backend
  only. Draft checkpoints are coalesced to about one per second and pruned after completion.
- **The API `send`** validates, begins the turn (state `queued`), enqueues a Cloud Tasks task
  (named by turn id for de-duplication) and returns the turn id.
- **The worker** (a new Cloud Run service from the same image with a worker entrypoint):
  - its task endpoint verifies the Cloud Tasks OIDC token and the audience;
  - it marks the turn running, runs the existing turn pipeline (safety floors, tools, actions
    guard), appends events and completes;
  - retries are safe: a completed turn is a no-op, and once `actions_started` is set the
    clinical write never repeats.
- **Queue:** `nora-turns`, with max dispatch and concurrency limits, retry with backoff, and a
  max attempt age matched to the turn deadline.
- **API service** returns to request-based CPU (removes `--no-cpu-throttling`).
- **Flag:** `CHAT_TURNS_VIA_WORKER`. The existing in-process path is the fallback until
  verified.

## Phase 3 — One live stream (medium)

- **`GET /api/v1/events`** (SSE, authenticated):
  - multiplexes the user's turn events and, later, notification events;
  - resumes from `Last-Event-ID`;
  - heartbeat every 15 s;
  - server-side reads use bounded polling of the events tables, about 500 ms, with backoff
    when idle;
  - on Cloud Run, connections are capped and clients reconnect on timeout.
- **The patient portal** uses one stream per tab for chat (sending stays an HTTP POST). The
  websocket is retired once verified.

## Phase 4 — Notifications computed at write time (medium)

- **At write time:** triggers or an outbox create receipts and maintain per-user unread
  counters when events occur.
- **Reads:** fetch a page and a counter, with no per-row time-zone or state computation.
- **Delivery:** new items and counts are pushed on the stream. Both portals drop their polls;
  a 5-minute fallback poll remains only when the stream is unavailable.

## Phase 5 — Load test and cost reset (small)

- A k6 or Locust scenario in staging: N patients × 2 tabs chatting while clinicians use
  dashboards. Thresholds: p95 API < 500 ms, zero expired turns, and stable queue age.
- Confirm request-based CPU on the API, and document the measured costs.

## External configuration (requires explicit authorization per change)

- A Cloud Tasks queue, a worker Cloud Run service, a service account with `run.invoker`, and
  the OIDC audience.
- These are created through the deploy workflow or documented `gcloud` commands, never
  ad hoc. No `.env` secrets are added. Queue and worker names are config.

## Known rule violations

Phase 1 satisfies the rules for the chat turn path (see the rule-by-rule status in the pull
request). These remain, each with the phase that removes it.

| Rule | Violation | Removed by |
| --- | --- | --- |
| 1, 16 | The turn runs in an in-process task and registry; a stopped instance loses the running work until the deadline reconciles it | Phase 2 (worker and queue) |
| 19 | Websocket events have no sequence numbers; a late socket gets a draft snapshot | Phase 2 (turn events), phase 3 (resume) |
| 6 | Notifications are computed at read time, with no outbox | Phase 4 |
| 10 | `lock_timeout` and `statement_timeout` are set only inside `chat_turn_operation`; the other RPCs, `notification_centre_operation` and the care-conversation and clinic RPCs, rely on the client budget | Phase 2 sets them for every backend role; phase 4 for notifications |
| 9 | Authorization in `notification_centre_operation` runs inside the function after its per-user lock | Phase 4 |
| 7 | The global lock order is not enforced by a test; sites are reviewed by hand | Phase 2 (lock-order checklist in review) |
| 12 | Model-provider retries are the SDK's and are not capped by the remaining turn budget | Phase 2 (worker step budget) |
| 13 | The default `asyncio.to_thread` pool is still shared by translation, back-translation, SOAP drafts, document and auth-refresh calls | Phase 2 (worker service) |
| 14 | Model-call concurrency waits in `model_traffic` without a bound | Phase 2 (queue limits) |
| 15 | Some services call the synchronous Supabase client from `async` code through the default pool | Phase 2 (named pools or worker) |
| 24 | Background tasks (A2A retry worker, scheduled jobs) log without a `task_id` | Phase 2 |
| 5 | Care-conversation panels poll every 15 s while open (inbox and open thread), paused when hidden | Phase 3 (stream) |
