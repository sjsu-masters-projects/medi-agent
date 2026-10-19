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

**Status (branch `feature/ops-006-phase-2`, based on the phase 1 branch; not merged, not
deployed, nothing external created):** implemented and locally verified behind
`CHAT_TURNS_VIA_WORKER` (default false) and `WORKER_MODE`. Rollout needs the requester's
authorization step by step: [docs/chat-worker-setup.md](../../docs/chat-worker-setup.md).

As built:

- **Migration `078_chat_turn_events.sql`** (apply after 077; inert without the flag):
  - `chat_turn_events(turn_id, seq, type, payload, created_at)`, primary key `(turn_id, seq)`,
    cascade delete, row level security on, no browser access, `UPDATE` not granted. Types:
    `started`, `draft`, `notice`, `completed`, `failed`, `interrupted`.
  - `chat_turns.status` allows `queued`; new columns `via_worker`, `run_count` (worker claims;
    `attempt` stays the user-visible retry count of at most 3 because the task is named from the
    turn id and `attempt`) and `dispatched_at` (the outbox marker). One active turn per
    conversation now covers `processing` and `queued` (`chat_turns_one_active`).
  - `chat_turn_operation` keeps everything 072 to 077 added and additionally: `begin` can create
    the turn `queued` (`queued: true`; a retry re-queues with `attempt + 1`); a queued turn
    reconciles to `interrupted` at its deadline; a worker turn writes its terminal event in the same
    transaction as `complete`, `failed`, `interrupted` and the reconcile, and drops its drafts.
  - `chat_turn_worker_operation(turn, action, payload)`: `claim` (queued, or processing with an
    expired lease and no `actions_started`; new lease and deadline; `run_count + 1`; `started`
    event; every refusal has a reason and only `lease_active` is retryable), `append_event`
    (current lease only, unexpired, `draft`/`notice` only, seq gap guard, repeated seq is a no-op),
    `requeue` (hand a claimed turn back before any clinical action), `prune_events`, and the
    queue-side `undispatched` (outbox listing with `SKIP LOCKED`) and `dispatched`.
  - Lock order (rule 7): lock-free existence check, then the conversation advisory lock (the same
    key as `chat_turn_operation`), then the `chat_turns` row, then the `documents` row
    (`KEY SHARE`), then event inserts. `append_event` takes only the turn row. Both functions set
    `lock_timeout` 5 s and `statement_timeout` 8 s.
- **API send** (flag on; websocket `user_message` and `POST /api/v1/chat/turns`): one `begin`
  transaction writes the user message and the queued turn, then (after commit) a Cloud Tasks
  HTTP task named `chat-turn-<turn id>-a<attempt>` is created (`ALREADY_EXISTS` counts as
  created). A failed enqueue leaves `dispatched_at` NULL; the sweep
  (`POST /api/v1/cron/chat-turns/dispatch`, and one supervised pass at API startup) creates it
  again. The API never runs model work while the flag is on; a legacy socket without the durable
  protocol is told to reload.
- **Worker** (`WORKER_MODE=true`, same image; serves `/health` and
  `POST /internal/tasks/chat-turn` only, absent on the API service): verifies the Cloud Tasks
  OIDC token (Google signature and issuer, audience, expected service account, verified email;
  401 or 403 otherwise, fail closed when unconfigured), claims the turn (patient, conversation and
  text come from the database, not the task), runs the extracted pipeline
  (`services/chat_turn_pipeline.execute_turn`: the same safety floors, tools, `actions` guard,
  model fallback and budgets), checkpoints the draft at most once a second from a supervised
  task, completes with the lease and prunes drafts.
- **Retry semantics:** finished, stale, unknown, expired, over-budget (marked `interrupted`) or
  `actions_started` turns answer 200 (no retry); anything transient (claim unreachable, live lease,
  failure not recordable, context unreadable, saturated) answers 503 so the queue retries with
  backoff; a stopping instance hands the turn back (`requeue`) unless a clinical action started.
- **Viewing without the stream:** sockets and recover read `chat_turn_events` from the database
  (`services/chat_turn_events.py`): the draft so far, notices, the final reply, resumable by seq,
  from any instance. `GET /api/v1/chat/turns/{id}/events?after_seq=` returns the same log.
  Phase 3 replaces the poll with one stream.
- **Timeouts nest (rule 11):** Cloud Run request 300 s > task dispatch deadline 100 s (lease + 30)
  > database lease 70 s > processing budget 40 s > model 30 s > database call 8 to 10 s.

Not done in phase 2 (kept for the phase named): request-based CPU on the API
(`--no-cpu-throttling` stays until phase 5), the SSE stream and websocket retirement (phase 3),
moving translation, back-translation and SOAP drafts to the worker, and role-level timeouts for
every other backend RPC.

Original scope, for reference:

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
request). Phase 2 satisfies them for the worker turn path, with the exceptions below (status after
phase 2, branch `feature/ops-006-phase-2`; they apply once the flag is on and verified).

| Rule | Violation | Removed by |
| --- | --- | --- |
| 1, 16 | With the flag **off** the turn still runs in an in-process task and registry (the fallback); with it on, no state or work lives in an API process | Retire the fallback after verification |
| 19 | Websocket messages carry no seq of their own; the event log is ordered by seq and viewers resume by it | Phase 3 (stream with `Last-Event-ID`) |
| 6 | Notifications are computed at read time, with no outbox (the Nora turn path has one) | Phase 4 |
| 10 | `lock_timeout` and `statement_timeout` are set inside `chat_turn_operation` and `chat_turn_worker_operation` only; `notification_centre_operation`, the care-conversation and clinic RPCs rely on the client budget. Claiming waits on the conversation lock up to the 5 s `lock_timeout` rather than using `NOWAIT` | Phase 4 for notifications; a role-level default is a separate, authorized database change |
| 9 | Authorization in `notification_centre_operation` runs inside the function after its per-user lock (the worker function pre-checks without a lock) | Phase 4 |
| 7 | The global lock order is documented for every new site and followed, but no automated test enforces it | Lock-order checklist in review; a test is a follow-up |
| 13, 15 | Translation, back-translation, SOAP drafts, documents and auth refresh still use the default `asyncio.to_thread` pool in the API, and the pipeline's `ChatService` calls use it inside the worker; named pools exist for chat control, notifications, enqueue and event reads | Move those workloads to the worker or named pools (after phase 2 verification) |
| 14 | Model-call concurrency waits in `model_traffic` without its own bound; the turn budget cancels the wait, and the queue limits bound how many turns run | Per-workload queue limits when more workloads move |
| 24 | Background tasks (A2A retry worker, scheduled jobs) log without a `task_id`; worker turns and the sweep carry `task_id`, `turn_id` and `request_id` | Remaining background jobs |
| 5 | Care-conversation panels poll every 15 s while open (inbox and open thread), paused when hidden | Phase 3 (stream) |

**Worker-mode portal and socket close log (October 19):** the patient portal now treats `queued` as in progress (a queued turn had been drawn as interrupted); the chat socket logs `chat_ws.closed` with `initiator` (client or server), `close_code` and `reason` so the cause of any close is visible in Cloud Logging; the conversation list counts queued turns as a reply in progress.
