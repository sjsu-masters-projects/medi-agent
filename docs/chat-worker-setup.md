# Nora turn worker: one-time setup and rollout (OPS-006 phase 2)

Nothing here is applied by merging. Every command below changes external configuration, so
each needs the requester's explicit authorization **before it runs**. Until
`CHAT_TURNS_VIA_WORKER=true` is set on the API service, Nora turns run in the API process
exactly as today; every step below is reversible by turning that flag off.

Design in one paragraph: the API saves the patient's message and a `queued` turn in one
database transaction, then creates a Cloud Tasks HTTP task named from the turn id and attempt
(a repeat creates nothing new). A separate Cloud Run **worker** service (the same image,
`WORKER_MODE=true`) receives the task, verifies the queue's OIDC token, claims the turn from the
database, runs the normal Nora pipeline and writes ordered `chat_turn_events` (a draft about once
a second, then the final reply). Browsers still use the websocket (or `GET /api/v1/chat/turns/{id}/events`);
it now reads those events from the database, so any API instance can serve it. A sweep
re-creates tasks that failed to enqueue.

Names used below (change them in one place if you prefer others):

```bash
export PROJECT=medi-agent-490106
export REGION=us-central1
export API_SERVICE=mediagent-backend
export WORKER_SERVICE=mediagent-chat-worker
export QUEUE=nora-turns
export INVOKER_SA_NAME=nora-turn-invoker
export INVOKER_SA="${INVOKER_SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
# The service account both Cloud Run services already run as (see deploy-backend.yml).
export RUNTIME_SA="github-actions-deployer@${PROJECT}.iam.gserviceaccount.com"
```

## 0. Read-only checks (no authorization needed)

```bash
gcloud services list --enabled --project "$PROJECT" --filter="name:cloudtasks.googleapis.com"
gcloud run services list --project "$PROJECT" --region "$REGION"
gcloud tasks queues list --project "$PROJECT" --location "$REGION"   # fails until the API is enabled
```

## 1. Database

Apply `backend/src/app/db/migrations/078_chat_turn_events.sql` through the reviewed migration
path (`docs/supabase_setup_guide.md`). It is re-runnable and ends with a verification block that
fails the migration if browser roles gained access or a 077 behavior is missing. It is safe before
the backend deploy: without the flag nothing uses its tables or columns. The old unique index
`chat_turns_one_processing` is replaced by `chat_turns_one_active` (processing or queued).

## 2. Enable Cloud Tasks (changes the project)

```bash
gcloud services enable cloudtasks.googleapis.com --project "$PROJECT"
```

## 3. Service account that invokes the worker (creates a resource)

```bash
gcloud iam service-accounts create "$INVOKER_SA_NAME" \
  --project "$PROJECT" --display-name "Nora turn task invoker"
```

This account has **no keys and no roles except** `run.invoker` on the worker (step 6). Cloud Tasks
signs its OIDC token as this account; the worker accepts only a Google-signed token for this
account's email and for its own URL as the audience (`app/core/task_auth.py`).

## 4. The queue (creates a resource)

```bash
gcloud tasks queues create "$QUEUE" --project "$PROJECT" --location "$REGION" \
  --max-dispatches-per-second 5 \
  --max-concurrent-dispatches 8 \
  --max-attempts 5 \
  --min-backoff 2s --max-backoff 30s --max-doublings 3 \
  --max-retry-duration 300s
```

Why these values (all explicit config, rule 13):

- `max-concurrent-dispatches 8` stays below the worker's capacity (3 instances x 4 requests = 12),
  so the queue, not an overloaded instance, absorbs a burst. Raise both together.
- `max-retry-duration 300s` matches the turn: a queued turn waits at most 120 s for a worker
  (`CHAT_TURN_QUEUE_SECONDS`), a claimed turn holds a 70 s lease, plus margin. A task still
  failing after 300 s is dropped and the turn is reconciled to `interrupted` by its deadline,
  which the patient sees as the existing retry card.
- `max-attempts 5` with 2 s to 30 s backoff covers a database or model blip without hammering it.
- The task's own dispatch deadline is the lease plus 30 s (100 s); the worker's Cloud Run request
  timeout is 300 s. Nesting: Cloud Run timeout (300) > task deadline (100) > lease (70) >
  processing budget (40) > model call (30) > database statement (8 to 10).

## 5. Permissions for the API service account (changes IAM)

```bash
# Create tasks in this queue only.
gcloud tasks queues add-iam-policy-binding "$QUEUE" --project "$PROJECT" --location "$REGION" \
  --member "serviceAccount:${RUNTIME_SA}" --role roles/cloudtasks.enqueuer

# Attach the invoker account's OIDC token to a task ("act as" that account, only).
gcloud iam service-accounts add-iam-policy-binding "$INVOKER_SA" --project "$PROJECT" \
  --member "serviceAccount:${RUNTIME_SA}" --role roles/iam.serviceAccountUser
```

## 6. Repository variables and the worker deploy (changes GitHub and Cloud Run)

The worker is deployed by `.github/workflows/deploy-backend.yml`, but only when the repository
variable `DEPLOY_CHAT_WORKER` is `true`.

```bash
gh variable set CHAT_WORKER_INVOKER_SA --body "$INVOKER_SA"
gh variable set DEPLOY_CHAT_WORKER --body true
```

The next deploy of `main` (or a manual run of the workflow) creates `$WORKER_SERVICE` with
`WORKER_MODE=true`, `--no-allow-unauthenticated`, request-based CPU, `--concurrency 4`,
`--timeout 300`, `--min-instances 0`, then sets `CHAT_WORKER_URL` and `CHAT_WORKER_OIDC_AUDIENCE`
on the worker to its own URL and prints it. The worker uses the same four Supabase secrets as the
ingestion job; if the API reports errors to Sentry and you want the worker to as well, add
`BACKEND_SENTRY_DSN` to the `--update-secrets` list in the workflow step.

Then let the invoker account call it (the service must exist first):

```bash
gcloud run services add-iam-policy-binding "$WORKER_SERVICE" --project "$PROJECT" --region "$REGION" \
  --member "serviceAccount:${INVOKER_SA}" --role roles/run.invoker
export WORKER_URL="$(gcloud run services describe "$WORKER_SERVICE" --project "$PROJECT" \
  --region "$REGION" --format 'value(status.url)')"
```

## 7. API service environment (changes Cloud Run; the flag stays off)

```bash
gcloud run services update "$API_SERVICE" --project "$PROJECT" --region "$REGION" \
  --update-env-vars "CLOUD_TASKS_PROJECT=${PROJECT},CLOUD_TASKS_LOCATION=${REGION},CLOUD_TASKS_QUEUE=${QUEUE},CHAT_WORKER_URL=${WORKER_URL},CHAT_WORKER_INVOKER_SA=${INVOKER_SA}"
```

`--update-env-vars` merges; nothing else on the service changes. These values are not secrets.

## 8. The outbox sweep (creates a Cloud Scheduler job)

The sweep creates tasks for queued turns whose enqueue failed. It also runs once at API startup.
Create the schedule the same way the existing reminder job was created (copy its auth header
setup from `gcloud scheduler jobs describe <reminder job> --location "$REGION"`; read the cron
token from Secret Manager at run time, never paste it into a shell):

```bash
gcloud scheduler jobs create http nora-turn-dispatch-sweep --project "$PROJECT" --location "$REGION" \
  --schedule "* * * * *" --time-zone "Etc/UTC" \
  --uri "https://<api service url>/api/v1/cron/chat-turns/dispatch" --http-method POST \
  --headers "X-Cron-Auth=${CRON_AUTH_TOKEN}"
```

## 9. Rollout order (each step needs authorization)

1. Merge the phase 2 pull request. With both flags off the backend behaves as before.
2. Apply migration **078** (step 1). Check the deployed API still sends and recovers a turn.
3. Enable the Cloud Tasks API (step 2).
4. Create the invoker account and the queue; grant the permissions (steps 3 to 5).
5. Set `CHAT_WORKER_INVOKER_SA` and `DEPLOY_CHAT_WORKER=true`, run the deploy (step 6), then grant
   `run.invoker`.
6. Verify the worker before any traffic uses it:
   ```bash
   # Cloud Run refuses an unauthenticated call before the app sees it: expect 403.
   curl -s -o /dev/null -w '%{http_code}\n' -X POST "$WORKER_URL/internal/tasks/chat-turn"
   gcloud run services describe "$WORKER_SERVICE" --project "$PROJECT" --region "$REGION" \
     --format 'value(spec.template.metadata.annotations)'   # request-based CPU, no always-on CPU
   gcloud tasks queues describe "$QUEUE" --project "$PROJECT" --location "$REGION"
   ```
7. Set the API environment (step 7) and the sweep schedule (step 8).
8. Turn the feature on for a synthetic patient first: set `CHAT_TURNS_VIA_WORKER=true` on the API
   service.
   ```bash
   gcloud run services update "$API_SERVICE" --project "$PROJECT" --region "$REGION" \
     --update-env-vars CHAT_TURNS_VIA_WORKER=true
   ```
9. Production check, both portals: sign in as a synthetic patient, send a message and watch the
   reply stream in; reload mid-reply and confirm the draft returns; send the same message id twice
   and confirm one reply. In Cloud Logging, follow one turn by `jsonPayload.turn_id`:
   `chat_turn.begin`, `chat_turn.dispatched`, `chat_turn.worker_task`, `chat_turn.queue_claim`,
   `chat_turn.complete`, `chat_turn.worker_done`. The API passes its trace id to the task, so these lines
   normally share one `request_id`; every worker line also carries `task_id`.
   ```bash
   gcloud logging read 'jsonPayload.event=~"chat_turn\.(dispatch|worker|queue)"' \
     --project "$PROJECT" --freshness 15m --limit 30 --format 'value(jsonPayload.event,jsonPayload.turn_id,jsonPayload.outcome,jsonPayload.reason)'
   ```
10. Only after step 9 passes: phase 2 is verified. The API keeps `--no-cpu-throttling` until phase 5.

## Rollback

- **Fast, no deploy:** set `CHAT_TURNS_VIA_WORKER=false` on the API service. New turns run
  in-process again at once. Turns already queued or running finish in the worker or are reconciled
  by their deadline; sockets keep showing them from the event log.
- **Stop the worker taking work:** `gcloud tasks queues pause "$QUEUE" --project "$PROJECT" --location "$REGION"`
  (resume with `queues resume`). Queued turns expire to `interrupted` after 120 s and offer the
  patient a retry.
- **Remove everything:** set `DEPLOY_CHAT_WORKER` to anything but `true`, delete the worker service,
  the queue and the invoker account. Migration 078 is inert and needs no rollback.

## Settings reference

| Setting | Where | Default | Meaning |
| --- | --- | --- | --- |
| `CHAT_TURNS_VIA_WORKER` | API | `false` | Queue each Nora turn; the API never runs model work |
| `WORKER_MODE` | worker | `false` | Serve only `/health` and `POST /internal/tasks/chat-turn` |
| `CLOUD_TASKS_PROJECT` | API | `GOOGLE_PROJECT_ID` | Queue project |
| `CLOUD_TASKS_LOCATION` | API | `us-central1` | Queue region |
| `CLOUD_TASKS_QUEUE` | API | `nora-turns` | Queue name |
| `CHAT_WORKER_URL` | API, worker | none | Worker https URL, no trailing slash |
| `CHAT_WORKER_INVOKER_SA` | API, worker | none | The only caller the worker accepts |
| `CHAT_WORKER_OIDC_AUDIENCE` | API, worker | `CHAT_WORKER_URL` | Token audience |
| `CHAT_TURN_QUEUE_SECONDS` | API | `120` | How long a queued turn waits before it is interrupted |
| `CHAT_WORKER_MAX_CONCURRENCY` | worker | `4` | Tasks one worker instance runs at once (more get 503) |

A required status check for the new `Backend PostgreSQL contracts (chat-turns)` CI job must be
added in the repository's branch protection by the requester if the previous
`care-conversations` check was required to cover the Nora turn suite.
