# AI runtime and workers

How MediAgent picks a model for each AI task, keeps a model failure from becoming a wrong
or missing answer, and runs Nora's chat turns in a separate worker service so they survive
reloads and instance restarts. Engineers and operators use it; patients and clinicians feel
it as replies that arrive once and failures that stay safe.

## What it does

Every AI task is a workload in `backend/src/app/adk/registry.py` with a model, fallback,
thinking level, output ceiling, deadline, kill switch and a named deterministic outcome.
Gemini is called through the Google Gen AI SDK on Vertex's global endpoint.

| Workload | Primary / fallback (thinking) | If the model cannot answer |
| --- | --- | --- |
| Triage | 3.5 Flash-Lite / 3.8 Flash (LOW) | Emergency floor, then unavailable copy |
| Patient reply | 3.8 Flash / 3.5 Flash (LOW) | Localized template |
| Explanation, record titles | 3.8 Flash / 3.5 Flash (MEDIUM) | Template; file name |
| Document extraction | 3.8 Flash (MEDIUM), none | No candidates; evidence review |
| Symptom intake | 3.8 Flash (LOW), none | No report written; patient told |
| Care-plan categorization, translation | 3.8 Flash (LOW), none | Keep approved plan; untranslated |
| Discrepancy, conversation summary | 3.8 Flash (MEDIUM / LOW), none | Deterministic engine; old summary |
| SOAP draft | configured Pro (LOW), none | Failure; no note unless all 4 sections valid |

- **Nora turns** run in the API process or, with `CHAT_TURNS_VIA_WORKER=true`, in a Cloud
  Run worker (same image, `WORKER_MODE=true`). The API saves the message and a `queued`
  turn in one transaction and creates a Cloud Tasks task; the worker claims the turn, runs
  the same pipeline and writes ordered `chat_turn_events` (draft, notices, final reply).
  Sockets and `GET /api/v1/chat/turns/{id}/events` read that log from any instance.
- **Operators** get `GET /api/v1/ops/ai-availability?hours=24` (clinic admins): attempts,
  outcomes, fallback use, success rate and p50/p95/p99 latency per workload and model.

## Rules it must keep

1. The emergency floor runs before any model. Safety, authorization, approval and
   provenance never depend on a model, the queue or a worker being up. Model output is a
   candidate and cannot approve a medication change, diagnosis or clinical action.
2. Tool access is deny-by-default per agent. Every route has a deterministic outcome and a
   kill switch (checked at import). Structured output is validated at the boundary.
   Care-plan categorization may only label the supplied source fact IDs, each exactly once;
   an unknown, missing or duplicate ID rejects the whole proposal. SOAP assessment and plan
   are considerations for clinician review, not a diagnosis, and patient chat and document
   text are fenced data, never instructions.
3. Telemetry records provider, model, outcome, finish reason, latency, retries and fallback
   path; never a patient identifier, prompt, response or raw exception.
4. Retriable failures (429, 5xx, timeout) move to the declared fallback before any response
   is emitted. One 429 retry (200 to 400 ms jitter, or `Retry-After` up to 1 s with 500 ms
   to spare); SDK retries off; no other status retried. Patient prose falls back to full
   Flash, never Lite. Symptom intake has no qualified backup.
5. Every interactive attempt has a registry deadline and the whole turn a 30 s ceiling, then
   reviewed localized unavailable copy. Tool rounds are buffered; reply text passes through
   after its first visible text. If the model then fails, the shown text is withdrawn and
   the backup runs once, only with 2 s or more of reply budget left. Partial answers of two
   models are never spliced. A missing triage decision is unavailable copy, never routine.
6. Admission is bounded per process: 2 in-flight calls per endpoint and model, 250 ms
   between starts, background calls limited to one slot. An interactive call waits at most
   5 s, then is shed with a retriable 503 so the fallback or unavailable copy takes over.
7. The database is the only source of truth; in-process memory is an optimization, since
   any Cloud Run instance can stop at any time.
8. Every state change is a guarded transition (`UPDATE ... WHERE status=$expected [AND
   lease=$lease]`) checked by row count; terminal states are never left. One owner per
   running unit: a lease (UUID plus `deadline_at`), changed only by an explicit transition.
   Deadlines and leases use the database clock; ordering uses `seq`, not timestamps.
9. Every external trigger has an idempotency key (`client_message_id`, task name
    `chat-turn-<turn>-a<attempt>`, event `seq`); delivery is at-least-once and consumers
    de-duplicate. A clinical side effect runs at most once (`actions_started`).
10. Write-plus-notify is a transactional outbox: the event commits with the state change,
    delivery follows. A queued turn with no created task (`dispatched_at` NULL) is
    re-enqueued by the sweep `POST /api/v1/cron/chat-turns/dispatch`.
11. Lock order: clinic, clinicians by id, patient advisory locks (evidence, conversation
    pair, notification prepare), rows by primary key ascending; a new lock site states where
    it fits. Locks are short, transaction-scoped, never held across a network call, model
    call, sleep or user wait; authorize before contended locks; claim with `NOWAIT` or `SKIP
    LOCKED`. Turn functions set `lock_timeout` 5 s and `statement_timeout` 8 s.
12. Budgets nest (client, API, queue task, worker step, database statement). Defaults:
    request 300 s, task dispatch 100 s, lease 70 s, processing 40 s, model 30 s, database
    call 8 to 10 s. Retries use bounded backoff with jitter, only for retryable errors,
    capped by remaining budget.
13. Bulkheads: bounded pools for chat-turn control (4), notifications (3), dispatch (2),
    event reads (3), telemetry (1). A saturated pool refuses fast with 503 and `Retry-After`.
    Queues are bounded: a viewer over 2,000 events behind is dropped and recovers from the
    saved turn. Blocking calls never run on the event loop. Background tasks are tracked,
    cancellation-safe and drained on shutdown (8 s).
14. Every in-flight state has a recovery path: an expired `processing` turn becomes
    `interrupted`, a queued turn nobody claims is interrupted at its deadline (120 s at
    most), and a possibly-done operation is reconciled by reading the source of truth.
15. The worker serves only `/health` and `POST /internal/tasks/chat-turn`. It accepts a task
    only with a Google-signed OIDC token for the configured audience from the configured
    service account with a verified email (401 invalid, 403 wrong caller, closed when
    unconfigured) and reads patient, conversation and text from the database, not the task.
16. Task replies: 200 (no retry) for finished, stale, unknown, expired, over-budget or
    `actions_started` turns; 503 (retry with backoff) for transient causes. A stopping
    instance hands a claimed turn back unless a clinical action started.
17. `chat_turn_events` has RLS on, no browser access and no UPDATE grant. Appends need the
    current unexpired lease, type `draft` or `notice`, no seq gap; a repeated seq is a no-op;
    the terminal event commits with the status change and drafts are pruned.
18. Every log line carries `request_id`, `turn_id` or `task_id`; actors and sessions are
    hashed; transitions, lock timeouts, retries, shedding and rejections log a reason
    (`not_found`, `status:<s>`, `lease_mismatch`, `session_mismatch`, `deadline_passed`)
    while the user-facing code stays generic. No patient text in logs.
19. Availability counters are bounded: hourly rows per workload, model, outcome and route,
    a closed outcome set, at most 200 rows per write, flushed every 30 s or more by one
    task, deleted after 14 days; no patient data; counts are approximate.
20. Remote changes (queue, worker service, service accounts, flags, migrations) need exact
    authorization. The worker flags default off; turning `CHAT_TURNS_VIA_WORKER` off is the
    rollback.
    Deploys set the API and worker services' variables and secrets with the update forms,
    never the set forms, so separately managed values and secret references survive.

## Why it was built this way

- **Gemini only in live routes.** GPT OSS 120B timed out on half of its pilot calls and is
  evaluation-only. Flash-Lite mis-explained a Spanish condition, so it only classifies. Pro
  was too slow for interactive fallback and stays on SOAP. Intake has no backup because the
  candidate changed a symptom timeline.
- **No medical-specific model** (MedGemma, Meditron, Med42, BioMistral): shortlisted only,
  no endpoint and no bilingual benchmark. Routing stays until clinician adjudication.
- **Worker plus Cloud Tasks** over a CPU-always API holding turns (costly, loses work when
  an instance stops), Supabase Realtime (needs browser read policies on backend-only
  tables), Pub/Sub (more parts) and faster polling (no streaming, high request volume).

## Excluded on purpose

The one-stream server-sent events replacement of the websocket, write-time notification
counters and the large load and cost exercise were ruled out. Do not change CPU, queue or
database settings to finish this. No medical-model deployment, automatic model promotion or
clinical-validation claim.

## Where it lives

- `backend/src/app/adk/` (`registry.py`, `models/resilient.py`, `chat_runtime.py`),
  `core/{model_traffic,db_pools,task_auth,structured_logging,ai_availability}.py`,
  `services/chat_turn_{service,queue,worker,runner,events,pipeline}.py`,
  `routers/{chat_turns,internal_tasks,ops,cron}.py`; migrations 072 to 078, 090, 094.
- Setup and rollback: [chat-worker-setup](../chat-worker-setup.md);
  `.github/workflows/deploy-backend.yml`.

## How to check it

[QA handoff 3.1 (OPS-006a, AI-003) and 3.9](../qa-handoff-2026-10.md): send after idle (no
hang, no duplicate, streamed text), reload mid-turn (one reply), read `chat_turn.*` logs by
`turn_id`. Evaluation: [demo AI evaluation](../demo-ai-evaluation.md),
`backend/scripts/check_gemini_workloads.py`. From `backend/`: `.venv/bin/pytest tests/unit/adk
tests/unit/core tests/unit/services/test_chat_turn_worker.py
tests/integration/routers/test_chat_worker_api.py --no-cov -q`; PostgreSQL tests
(`tests/integration/test_chat_turn_*_postgres.py`) need `CHAT_TURN_TEST_POSTGRES_DOCKER=1`.

## Still open

- Only Nora turns use the worker; translation, back-translation and SOAP drafts still run
  in the API on the default thread pool, and the in-process turn path remains with the
  flag off.
- Role-level timeouts cover chat-turn functions and a few later ones, not every RPC; no
  automated test enforces the global lock order across all sites.
- Notifications are computed at read time (no outbox), care-conversation panels poll every
  15 s, and background jobs log without `task_id`.
- Real-provider and deployed routing acceptance and fallback-rate evidence are not recorded;
  no reduction in fallback or 429 rates is claimed.
