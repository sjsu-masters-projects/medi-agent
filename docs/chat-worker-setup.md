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
# The service account both Cloud Run services ran as before the least-privilege accounts
# below existed (see deploy-backend.yml). Steps 5 and 6 use whichever account the service runs as.
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
`--timeout 300`, `--min-instances 1`, `--cpu-boost`, then sets `CHAT_WORKER_URL` and `CHAT_WORKER_OIDC_AUDIENCE`
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

The workflow now sets this environment on every deploy from the repository variables in
"Repository variables" below, so the manual command here is only the first-time path or an
emergency edit; a later deploy overwrites it with the variable values.

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

## Repository variables

`.github/workflows/deploy-backend.yml` sets every non-secret runtime setting on the API and
worker services from repository variables (Settings, Secrets and variables, Actions, Variables).
The first workflow step fails the run, before anything is built, if a required variable is
missing, naming the variable and the command to set it. Secrets are never variables: the workflow
references Secret Manager secrets by name (`--update-secrets ENV=SECRET:VERSION`); their values are
managed only in Secret Manager. The workflow uses `--update-env-vars` and `--update-secrets`, so
settings it does not name (portal and callback URLs, SMART client settings, Sentry and Resend
options, `SYMPTOM_INTAKE_ENABLED`) stay as configured.

| Variable | Required | Service | Purpose | Example (non-secret) |
| --- | --- | --- | --- | --- |
| `CLOUD_TASKS_PROJECT` | yes | API | Project that owns the Nora queue | `medi-agent-490106` |
| `CLOUD_TASKS_LOCATION` | yes | API | Queue region | `us-central1` |
| `CLOUD_TASKS_QUEUE` | yes | API | Queue name | `nora-turns` |
| `CHAT_WORKER_URL` | yes | API (the deploy also sets it on the worker from its real URL) | Worker https URL, no path or trailing slash; also the OIDC audience by default | `https://mediagent-chat-worker-<hash>-uc.a.run.app` |
| `CHAT_WORKER_INVOKER_SA` | yes | API and worker | The only caller the worker accepts; the account the queue signs its token as | `nora-turn-invoker@medi-agent-490106.iam.gserviceaccount.com` |
| `CHAT_TURNS_VIA_WORKER` | yes, `true` or `false` | API | Feature flag: queue each turn instead of running it in the API | `false` |
| `DEPLOY_CHAT_WORKER` | no | worker deploy | `true` creates and updates the worker service | `true` |
| `CLOUD_RUN_API_RUNTIME_SA` | no | API | Runtime account for the API; unset keeps the current account | `mediagent-api-runtime@medi-agent-490106.iam.gserviceaccount.com` |
| `CLOUD_RUN_WORKER_RUNTIME_SA` | no | worker | Runtime account for the worker; unset keeps the current account | `mediagent-worker-runtime@medi-agent-490106.iam.gserviceaccount.com` |

Set them once (placeholders only; the requester runs these, nothing here has):

```bash
gh variable set CLOUD_TASKS_PROJECT --body <project-id>
gh variable set CLOUD_TASKS_LOCATION --body <region>
gh variable set CLOUD_TASKS_QUEUE --body <queue-name>
gh variable set CHAT_WORKER_URL --body <worker-https-url>
gh variable set CHAT_WORKER_INVOKER_SA --body <invoker-service-account-email>
gh variable set CHAT_TURNS_VIA_WORKER --body <true-or-false>   # match the value live today
gh variable set CLOUD_RUN_API_RUNTIME_SA --body <api-runtime-service-account-email>      # after the script
gh variable set CLOUD_RUN_WORKER_RUNTIME_SA --body <worker-runtime-service-account-email> # after the script
```

Read the current live values (names are safe to print; read the values yourself from the console
or `gcloud run services describe`, they are not secrets) so the variables match what is deployed
and the first workflow run changes nothing.

Secret references the workflow sets (names only):

- API: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`,
  `GOOGLE_API_KEY`, `DEEPGRAM_API_KEY`, `BACKEND_SENTRY_DSN`, `CRON_AUTH_TOKEN`, `RESEND_API_KEY`,
  `SMART_STATE_ENCRYPTION_KEY` (secret `MEDIAGENT_SMART_STATE_KEY`), and
  `NOTIFICATION_TOKEN_SIGNING_SECRET` (pinned to version `1`, as live today).
- Worker: the four Supabase secrets.

## Least-privilege runtime accounts

Both services used to run as `github-actions-deployer`, which also holds deploy, Artifact Registry,
`run.admin`, `ml.admin` and project-wide Secret Manager rights. A compromised request would have
inherited all of them. Two accounts replace it at runtime; the deployer keeps deploy rights and
only gains permission to act as them.

| Account | Role | Scope | Why (derived from the code) |
| --- | --- | --- | --- |
| `mediagent-api-runtime` | `roles/aiplatform.user` | project | Gemini on Vertex AI through Application Default Credentials (`clients/vertex_auth.py`, `adk/models`) |
| | `roles/cloudtasks.enqueuer` | queue `nora-turns` only | `create_task` in `services/chat_turn_queue.py`; nothing else on Tasks is called |
| | `roles/iam.serviceAccountUser` | `nora-turn-invoker` only | Attach the invoker's OIDC token to a task |
| | `roles/secretmanager.secretAccessor` | the 11 API secrets, each individually | Values injected as environment variables at start |
| `mediagent-worker-runtime` | `roles/aiplatform.user` | project | The worker runs the Nora pipeline |
| | `roles/secretmanager.secretAccessor` | the 4 Supabase secrets, each individually | Database access |
| `github-actions-deployer` (unchanged) | `roles/iam.serviceAccountUser` | on each new account | `gcloud run deploy --service-account` needs actAs on the target |

Not granted, deliberately: Cloud Storage (the code uses Supabase Storage over the Supabase
credentials, not Google storage), `run.invoker` (the API never calls the worker directly; the
queue does, as the invoker account), Artifact Registry (the platform pulls the image), and log or
metric writers (Cloud Run ships container stdout without them; Sentry uses its DSN). If you want
them explicit anyway, run the script with `--with-observability-writers`.

The two Cloud Run Jobs get their own account, `mediagent-jobs-runtime`, in the same script run:

| Account | Role | Scope | Why (derived from the code) |
| --- | --- | --- | --- |
| `mediagent-jobs-runtime` | `roles/aiplatform.user` | project | `document_ingestion` runs the Gemini extraction and summary services; `health_knowledge_refresh` does not call Vertex but shares the account |
| | `roles/secretmanager.secretAccessor` | the 4 Supabase secrets, each individually | Both jobs inject exactly `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET` |
| `github-actions-deployer` (unchanged) | `roles/iam.serviceAccountUser` | on `mediagent-jobs-runtime` | `gcloud run jobs deploy --service-account` needs actAs |

Cloud Scheduler needs no new account: the two job triggers already use dedicated invoker-only
accounts (`mediagent-doc-ingest-sched`, `mediagent-knowledge-sched`, each `run.invoker` on its
own job and nothing project-wide), and the reminder and Nora dispatch triggers authenticate with
the `X-Cron-Auth` secret. Deployment sets the job identity from the repository variable
`CLOUD_RUN_JOBS_RUNTIME_SA`; unset keeps the deployer.

The requester runs, in order:

```bash
scripts/setup-runtime-service-accounts.sh            # dry run: prints every command, changes nothing
scripts/setup-runtime-service-accounts.sh --apply    # creates the accounts and grants the roles above
gh variable set CLOUD_RUN_API_RUNTIME_SA --body mediagent-api-runtime@medi-agent-490106.iam.gserviceaccount.com
gh variable set CLOUD_RUN_WORKER_RUNTIME_SA --body mediagent-worker-runtime@medi-agent-490106.iam.gserviceaccount.com
gh variable set CLOUD_RUN_JOBS_RUNTIME_SA --body mediagent-jobs-runtime@medi-agent-490106.iam.gserviceaccount.com
```

The accounts and grants come first (they are inert); the variables are what switch the next deploy
over. Verify after that deploy (read-only):

```bash
for s in "$API_SERVICE" "$WORKER_SERVICE"; do
  gcloud run services describe "$s" --project "$PROJECT" --region "$REGION" \
    --format 'value(status.latestReadyRevisionName,spec.template.spec.serviceAccountName)'
done
```

For the jobs (read-only), after the deploy:

```bash
for j in mediagent-document-ingestion mediagent-health-knowledge-refresh; do
  gcloud run jobs describe "$j" --project "$PROJECT" --region "$REGION" \
    --format 'value(name,spec.template.spec.template.spec.serviceAccountName)'
done
```

Then run each job once from the Scheduler console (or wait for the next tick) and confirm
`status="success"` in Cloud Logging; `PERMISSION_DENIED` on a secret or on Vertex means a grant is
missing. Then send one synthetic Nora message in both portals and follow the turn in Cloud Logging. A
`PERMISSION_DENIED` naming a role means a grant is missing; for Vertex AI add
`roles/serviceusage.serviceUsageConsumer` to the affected account only if the error says so.

### Rollback of the runtime accounts

1. Fast: delete the two variables (`gh variable delete CLOUD_RUN_API_RUNTIME_SA`, same for the
   worker) and re-run the workflow. The next revision runs as `github-actions-deployer` again; no
   other change is needed because its bindings were never removed.
2. Immediate, without a deploy: `gcloud run services update <service> --service-account
   github-actions-deployer@medi-agent-490106.iam.gserviceaccount.com --project "$PROJECT" --region "$REGION"`.
3. Remove the new accounts only after step 1, when no revision uses them:
   `gcloud iam service-accounts delete <email> --project "$PROJECT"`. The bindings the script made
   on the queue, secrets and invoker account disappear with the account's principal (stale `deleted:`
   entries can be cleaned with `remove-iam-policy-binding`).
4. Jobs: delete `CLOUD_RUN_JOBS_RUNTIME_SA` and re-run the workflow, or immediately
   `gcloud run jobs update <job> --service-account github-actions-deployer@medi-agent-490106.iam.gserviceaccount.com --project "$PROJECT" --region "$REGION"`.
   The deployer's bindings are untouched until step 5.
5. Trimming the deployer, last and only with explicit authorization, after the three variables are
   set, a deploy succeeded, a Nora turn, an ingestion run and a knowledge refresh passed, and a
   week of clean traffic:

   ```bash
   scripts/setup-runtime-service-accounts.sh --trim-deployer           # dry run: preconditions, live identity check, removals
   scripts/setup-runtime-service-accounts.sh --trim-deployer --apply   # refuses while anything still runs as the deployer
   ```

   It removes project-wide `secretmanager.secretAccessor`, `aiplatform.user`, `ml.admin`,
   `run.developer` (subset of `run.admin`) and `artifactregistry.writer` (subset of
   `artifactregistry.admin`). Kept: `run.admin`, `artifactregistry.admin`/`repoAdmin`,
   `iam.serviceAccountUser` (actAs, and needed for rollback), `serviceusage.serviceUsageConsumer`
   and `iam.serviceAccountTokenCreator` (purpose not established; review separately). Each removal
   prints its own rollback, the matching `gcloud projects add-iam-policy-binding ... --role <role>
   --condition=None`. Re-run Deploy Backend once afterwards to prove deploying still works.

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

Repository variables that feed these settings are listed under "Repository variables".

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


## Latency and cost (October 22 measurements)

One patient message on a cold path measured (Cloud Run logs, no message text):

| Step | Measured | Cause |
| --- | --- | --- |
| `chat_turn.begin` to `chat_turn.dispatched` | 6.5 s (earlier turns: 2.1-3.0 s; warm: 0.14 s) | The first Cloud Tasks call on a new API process built the client, fetched credentials and opened the TLS channel inside the request. |
| `chat_turn.dispatched` to `chat_turn.worker_task` | 30 s (warm worker: 0.1 s) | The worker had scaled to zero. The container took about 30 s from "Starting new instance" to "Started server process" (image load plus importing the application). |
| Model | 11-24 s | Unchanged by this work. |

Changes:

- The API warms the Cloud Tasks client at startup (`warm_dispatcher`): client creation, credential
  fetch and gRPC channel connect run on the bounded dispatch pool, off the request path. The log
  event `chat_turn.dispatcher_warm` carries `duration_ms`. `chat_turn.dispatched` now carries
  `client_ms` (time to obtain the client; large only on a cold process) and the new
  `chat_turn.submit_timing` event carries `begin_ms`, `saved_notice_ms`, `dispatch_ms` and
  `begin_to_dispatch_ms`. None of them contains message text.
- The conversation title is saved after the enqueue, not before it.
- A failed enqueue on the send path is retried at once, up to three times with jitter and inside a
  20 s budget (`dispatch_with_retry`). Only if all fail does the turn wait for the sweep, which runs
  every minute, so a transient Cloud Tasks error no longer costs up to a minute.
- Both services deploy with `--min-instances 1` and `--cpu-boost` (startup CPU boost). The worker
  uses request-based CPU, so its idle warm instance is billed at the low idle rate (memory and a
  small CPU share), a few dollars a month. The API uses always-allocated CPU (a Nora reply keeps
  running after its socket closes), so its warm instance is billed continuously (about one vCPU and
  2 GiB, tens of dollars a month); that is the price of a warm API. Set `--min-instances 0` in the
  workflow to go back, accepting the cold starts above.
- The worker app imports only the task router instead of every user-API router, and the image
  byte-compiles the application at build time (`PYTHONDONTWRITEBYTECODE` is set, so otherwise each
  cold start recompiled it). Locally this removes about 300 of 2,160 imported modules; the large
  remaining cost is the model library stack the first turn needs, so a warm instance is the real
  fix.

Check after a deploy: send a message after 10 minutes idle and read `chat_turn.submit_timing`
(`begin_to_dispatch_ms` should be under about 1000) and the gap from `chat_turn.dispatched` to
`chat_turn.worker_task` (should be under about 1 s with a warm worker).
