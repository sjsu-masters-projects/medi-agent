# OPS-006 — Worker service, turn events and one live stream

Status: accepted October 19, 2026 ([decision record](../../docs/decisions/realtime-and-workers-2026-10.md)).
Owner: Rajeev. Supersedes the connection-bound parts of PAT-001-A and the read-time notification
computation in NOT-001. Each phase is one PR with a live production check before the next starts.

## Phase 1 — Traceability and the current expiry (small)

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
