# Background work and live updates decision record — October 2026

**Status:** Accepted October 19, 2026. Delivery is phased; see
[OPS-006 specification](../../.agent/specs/ops-006-workers-and-event-stream.md).

## Context

Production checks from October 16 to 19 showed that the backend's structure, not one defect,
caused the chat and notification failures.

- **One process for everything.** Nora replies, message translation, back-translation and SOAP
  drafts run inside the API process that also serves every screen. The default thread pool,
  shared by every request, was saturated by slow notification reads. Chat turns queued behind
  them and expired (#192).
- **Work tied to a connection.** A Nora reply lived only as long as the websocket that started
  it. Reloads, a phone lock, tab switches and component re-mounts killed replies (#189, #191).
  Making the server own the turn (#191) required Cloud Run "CPU always allocated", which costs
  more and still loses work when an instance stops.
- **Three channels per tab.** Each tab held a chat websocket and polled the notification list,
  the summary, action items and ADR requests every few seconds. After #191, about 75
  notification requests arrived in seven minutes from one user's tabs.
- **Read-time computation.** Notification reads recomputed state, time zones and counts under a
  per-user lock, so reads got slower as history grew.
- **No traceability.** Logs are unstructured text. The failure cause of a single turn had to be
  inferred from timestamps, and some exception detail was dropped.

## Decision

1. **A separate worker service with a queue.** The API validates, writes the request and enqueues
   a **Cloud Tasks** task, then returns. A separate Cloud Run **worker** service runs model and
   tool work: Nora turns, message translation, back-translation, SOAP drafts and later document
   work. Cloud Tasks provides retries, backoff and per-queue rate and concurrency limits. The
   worker has CPU while a task request is running, so the API service returns to request-based
   CPU.
2. **The database is the only source of truth.** A turn is a state machine (queued → running →
   completed / failed / interrupted). The worker appends ordered **turn events** (started, draft
   checkpoints about once a second, completed or failed) to a table. Nothing outside the worker
   changes a running turn. Retries are idempotent, keyed by the client message id, and a
   clinical write still runs at most once (the existing `actions_started` rule).
3. **One live stream per tab.** The browser opens one **server-sent events** stream
   (`GET /api/v1/events`, resumable through `Last-Event-ID`). It carries the user's turn events,
   new notifications, unread counts and ADR requests. It reads from the database, so it works
   across instances and after reconnects. Polling remains only as a slow fallback (5 minutes).
   The chat websocket and the per-screen polls are retired.
4. **Notifications are computed when they are written.** Triggers or an outbox create per-user
   receipts and maintain unread counters when an event happens. Reads fetch a page and a
   counter. New items are pushed on the stream.
5. **Observability is part of the product.**
   - Structured JSON logs carry `request_id`, `turn_id`, `task_id` and a hashed actor id; there
     is no patient text in logs.
   - Cloud Trace links the API, the queue and the worker.
   - Metrics and alerts cover turn failure and expiry rates, model latency and errors, queue
     depth and age, and stream connections.
6. **Staging load test before production** for chat plus notifications with many concurrent users
   and tabs, using the existing staging Supabase project.

## Alternatives considered

- **Keep the websocket with server-owned turns and CPU always allocated (current).** Simpler, but
  costs more, loses running work when an instance stops, keeps a single process for all work,
  and leaves polling in place.
- **Supabase Realtime from the browser.** Needs browser read policies on chat and notification
  tables. Today these tables are backend-only by design. Rejected to keep the browser off the
  database.
- **Pub/Sub plus a worker pool.** More moving parts than Cloud Tasks for HTTP-triggered,
  per-request work at this scale.
- **Faster polling only.** Cheaper to build, but cannot give live chat streaming and keeps request
  volume high.

## Consequences

- There is a new Cloud Run service (worker), a Cloud Tasks queue and a service account with the
  invoker role. These are external configuration changes and need explicit authorization when
  rolled out.
- The worker's task handler must authenticate the Cloud Tasks OIDC token and reject everything
  else.
- Draft checkpoints add writes. They are bounded at about one per second per active turn and
  pruned after completion.
- Cost: the worker bills only while running tasks, so the API returns to request-based CPU.
- During migration the websocket and the stream coexist behind a flag. Each phase ships with a
  live check and a rollback path.
