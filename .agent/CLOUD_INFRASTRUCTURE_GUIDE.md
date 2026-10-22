# Cloud infrastructure and operations

How the MediAgent backend, workers, scheduled jobs and portals are hosted, deployed and
observed. Google Cloud project `medi-agent-490106`, region `us-central1`.

## Cost posture

Everything scales to zero when nobody is developing or demonstrating, so idle cost is
close to nothing. Billing for the Google Cloud project is a team responsibility; record
any billing-account change in the team channel rather than in this file.

| Service | Platform | Cost posture |
|---------|----------|--------------|
| **Backend API** | Cloud Run service `mediagent-backend` | `min-instances 0`, `max-instances 2`; sleeps when idle |
| **Workers** | Cloud Run Jobs | Run only when triggered |
| **Frontend (Portals)** | Vercel Hobby | One person owns the projects; Vercel's GitHub integration posts preview links on every PR, so teammates need no Vercel account |
| **Database & Auth** | Supabase | Free projects pause after a week of inactivity; restore from the dashboard |
| **Scheduled jobs** | Cloud Scheduler | Three free jobs per billing account; three are in use (document ingestion, weekly reference refresh, reminders). See section 5. |
| **Error Tracking** | Sentry | Developer free tier |
| **AI** | Vertex AI Gemini | Billed per call to the project. The backend uses `GOOGLE_PROJECT_ID` and `VERTEX_AI_LOCATION=global`; the model IDs are set in `.github/workflows/deploy-backend.yml` |

---

## Execution steps

### 1. Google Cloud project
- The project is `medi-agent-490106`. Teammates are added under **IAM & Admin** (Owners or
  Billing Managers for billing, Editors for console and metrics).
- Enabled APIs include Cloud Run, Cloud Scheduler, Artifact Registry, Secret Manager and
  Vertex AI.

### 2. Backend deployment (Cloud Run service)
`.github/workflows/deploy-backend.yml` runs on every push to `main` that touches
`backend/**` (or the workflow itself). It builds `./backend`, pushes the image to the
Artifact Registry repository `cloud-run-source-deploy`, applies the repository cleanup
policy, deletes untagged old images, and deploys:

```bash
gcloud run deploy mediagent-backend \
  --image <region>-docker.pkg.dev/medi-agent-490106/cloud-run-source-deploy/mediagent-backend:latest \
  --region us-central1 \
  --cpu 1 --memory 2Gi \
  --min-instances 0 --max-instances 2 \
  --allow-unauthenticated \
  --service-account "${CLOUD_RUN_API_RUNTIME_SA:-github-actions-deployer@medi-agent-490106.iam.gserviceaccount.com}" \
  --update-env-vars VERTEX_AI_LOCATION=global,GEMINI_VERTEX_AI_LOCATION=global,GEMINI_*_MODEL=...,CHAT_TURN_TIMEOUT_SECONDS=30,MODEL_CIRCUIT_BREAKER_COOLDOWN_SECONDS=60,CLOUD_TASKS_*=...,CHAT_WORKER_*=...,CHAT_TURNS_VIA_WORKER=... \
  --update-secrets SUPABASE_*=...,GOOGLE_API_KEY=...,DEEPGRAM_API_KEY=...,... \
  --port 8080 --timeout 300
```

The Nora worker settings (`CLOUD_TASKS_*`, `CHAT_WORKER_*`, `CHAT_TURNS_VIA_WORKER`) come from
GitHub repository variables and the 11 secret references from Secret Manager; a first workflow
step fails the run if a required variable is missing. The runtime identity is the least-privilege
`mediagent-api-runtime` (worker: `mediagent-worker-runtime`) once the repository variables
`CLOUD_RUN_API_RUNTIME_SA` / `CLOUD_RUN_WORKER_RUNTIME_SA` are set; until then the services keep
`github-actions-deployer`. Variable table, per-account roles, setup script and rollback:
[`docs/chat-worker-setup.md`](../docs/chat-worker-setup.md).

The service uses `--update-env-vars` and `--update-secrets` and never `--set-env-vars` or `--set-secrets`: the
`--set-*` forms replace the whole set and would wipe the variables and secret references
(Supabase, Sentry, SMART, Deepgram, Resend, cron) configured out of band. Memory is pinned
in the workflow because a console change would revert on the next deploy.

`min-instances 0` means a short cold start on the first request after idle. About a week
before a live demo, temporarily set `--min-instances 1` and revert afterwards.

### 3. Worker deployment (Cloud Run Jobs)
The same workflow deploys two Jobs from the same image so worker code never drifts behind
the API:

- `mediagent-document-ingestion` — `python -m app.workers.document_ingestion`, 1 CPU,
  2Gi, task timeout 1800s, no retries.
- `mediagent-health-knowledge-refresh` — `python -m app.workers.health_knowledge_refresh`,
  1 CPU, 512Mi, task timeout 1800s, no retries.

Each Job declares its whole runtime contract with `--set-env-vars` and `--set-secrets`
(Supabase secrets come from Secret Manager), so redeploying it is also the creation path.
Their triggers are in section 5.

### 4. Frontend deployment (Vercel)
- One person owns the Vercel projects (Hobby plan): `mediagent-patient` and
  `mediagent-clinician`, linked to `apps/patient-portal` and `apps/clinician-portal`.
- Environment variables are set in the Vercel project settings.
- Teammates do not need Vercel accounts; the GitHub integration builds every push and
  posts a preview link on the PR.

### 5. Scheduled jobs (Cloud Scheduler) and run logs
Cloud Scheduler triggers a small set of backend jobs, and the backend fans out to the
correct patients and clinics by querying Supabase at runtime. Project `medi-agent-490106`,
Scheduler and Cloud Run region `us-central1`.

| Job (`jsonPayload.job`) | Trigger | Schedule (timezone) | Target | Auth | Run record | Healthy run |
| --- | --- | --- | --- | --- | --- | --- |
| `document_ingestion` | `mediagent-document-ingestion-every-5m` (enabled) | `*/5 * * * *` (America/Los_Angeles) | Cloud Run Job `mediagent-document-ingestion` (`python -m app.workers.document_ingestion`) | OAuth: service account `mediagent-doc-ingest-sched`, `roles/run.invoker` on the Job only | None at job level (state is kept per document); the two log lines are the run record | `status="success"`, `summary.failed=0`; `summary.claimed=0` is normal when nothing is pending. Exit code 1 when any document failed or the batch could not run. |
| `health_knowledge_refresh` | `mediagent-health-knowledge-refresh-weekly` (enabled) | `0 3 * * 0`, Sundays 03:00 (America/Los_Angeles) | Cloud Run Job `mediagent-health-knowledge-refresh` (`python -m app.workers.health_knowledge_refresh`) | OAuth: service account `mediagent-knowledge-sched`, `roles/run.invoker` on the Job only | `cron_job_runs`, `job_name='health_knowledge_refresh'` | `status="success"`, `summary.subjects_failed=0`. `subjects_checked=0` is correct only with `subjects_due=0` and no new subjects; `next_due_at` then says when the oldest cached subject becomes due. Exit code 1 when any subject raised. |
| `reminders_dispatch` | `medi-agent-reminders-dispatch-prod` (enabled; resumed October 11) | `*/15 * * * *` (UTC) | `POST https://api.mediagent.live/api/v1/cron/reminders/dispatch` on service `mediagent-backend` | Shared secret: `X-Cron-Auth` header equal to the backend's `CRON_AUTH_TOKEN` | `cron_job_runs`, `job_name='reminders_dispatch'` | `status="success"`, `summary.window_mode="contiguous"` and a small `catch_up_minutes`. `catch_up_capped` means the previous run ended over an hour earlier. |
| `email_dispatch` | Runs after every real `reminders_dispatch` (same trigger); also `POST https://api.mediagent.live/api/v1/cron/emails/dispatch` for a manual or dedicated trigger (none configured) | Each reminder run; on demand | Service `mediagent-backend` | Shared secret: `X-Cron-Auth` | `cron_job_runs`, `job_name='email_dispatch'` | `status="success"`, `summary.errors=0`. `claimed=0` is normal. `retry` counts provider refusals kept for a later run; `stopped` counts sends cancelled because access, consent or the address changed. A failure here never fails the reminder run. |
| `nightly_adr_scan` | `medi-agent-adr-nightly-scan-prod` (deleted October 11) | was `0 2 * * *` (UTC) | **Retired.** The `/api/v1/cron/adr/nightly-scan` route was removed. | was the shared-secret header | Earlier rows stay in `cron_job_runs` | Not applicable. |

**Why the ADR scan was retired.** Chat intake already sets `flagged_for_adr` under the
stricter AI-004 rule (an active medication match plus explicit Naranjo link evidence,
`followup/service.py::is_possible_adr_candidate`) and starts the pharmacovigilance review.
The scan flagged any medication-linked symptom without starting a review, which would have
put unreviewed ADR labels into the clinician symptom timeline and SOAP notes. The requester
deleted its Scheduler job `medi-agent-adr-nightly-scan-prod` on October 11.

**Auth.** The two Cloud Run Job triggers call each Job's `:run` endpoint with OAuth as a
dedicated, invoker-only service account, so no secret sits in a Scheduler payload. The
reminder trigger calls a public HTTPS route and is authorised only by the shared
`X-Cron-Auth` secret. Rotate `CRON_AUTH_TOKEN` in Secret Manager and in the Scheduler header
together.

**Reminder windows.** Each dispatch covers the range from the previous successful
(non-dry-run) window end, stored in `cron_job_runs.summary.window_end`, to now plus
`window_minutes`. A late or retried run therefore leaves no gap. After a pause of more than
60 minutes the next run starts at now. Dedupe keys stop overlaps from sending twice. The
Scheduler timezone does not matter for this job because due times come from the database.
Booked visits are `confirmed` or `scheduled`.

**Run log shape.** Every run writes exactly two JSON lines on stdout. Cloud Run parses
them into `jsonPayload` and reads `severity` and `message`:

- `scheduled_job.started`: `job`, `run_id` (the `cron_job_runs` id, or `null` for document
  ingestion), `dry_run`, `execution` (the Job execution name, or the service revision
  on the API service), `parameters` and `severity="INFO"`.
- `scheduled_job.finished`: the same fields, plus `status` (`success`, `failed` or
  `skipped`), `duration_ms` and `summary`, which is the same object stored in
  `cron_job_runs.summary`. Severity is `INFO`, or `WARNING` when skipped (another run is in
  progress) and `ERROR` when failed. A failed line carries `error_type`, `error_category`
  and, when it has the shape of a code, `error_code` (for example SQLSTATE `23505`). It may
  also carry a fixed `reason` (`documents_failed`, `run_not_recorded`, or
  `N reference subjects failed`). Exception text is never logged because it can quote
  patient data.

Example (synthetic):

```json
{"dry_run":false,"duration_ms":412,"event":"scheduled_job.finished","execution":"mediagent-backend-00123-abc","job":"reminders_dispatch","message":"Scheduled job reminders_dispatch finished: success","run_id":"2f0c…","severity":"INFO","status":"success","summary":{"appointment_1h_candidates":0,"appointment_1h_created":0,"appointment_1h_existing":0,"appointment_24h_candidates":0,"appointment_24h_created":0,"appointment_24h_existing":0,"catch_up_minutes":2.0,"medication_candidates":1,"medication_created":1,"medication_existing":0,"obligation_candidates":0,"obligation_created":0,"obligation_existing":0,"skipped_frequency_mismatch":0,"skipped_inactive_target":1,"window_end":"2026-10-12T08:12:00+00:00","window_mode":"contiguous","window_start":"2026-10-12T07:55:00+00:00"}}
```

Summary counts per job:

- **Document ingestion:** `claimed`, `completed`, `needs_review`, `failed`,
  `summaries_*`, `titles_*` and the care-plan generation counts.
- **Reference refresh:** `subjects_total`, `subjects_due`, `subjects_new_medications`,
  `subjects_new_conditions`, `subjects_new_locales` (cached conditions missing en-US or
  es-MX), `subjects_checked`, `subjects_updated`,
  `subjects_unavailable`, `subjects_failed`, `subjects_deferred` (over the limit of 150),
  `next_due_at`, and `sources.<medlineplus|dailymed>.<updated|unchanged|not_found|unavailable>`.
- **Email dispatch:** `claimed`, `accepted` (provider accepted, not inbox delivery),
  `retry`, `stopped`, `errors`, `status_checked`, `delivered`, `bounced`, `failed`,
  `complained`. A dry run reports only `due` and `awaiting_status`. Status checks need a
  full-access Resend key; with a sending-only key the service logs one warning and
  statuses stay "accepted". The failed `reason` is `N email rows deferred`.
- **Reminders:** `window_start`, `window_end`, `window_mode`, `catch_up_minutes`,
  `appointment_<24h|1h>_<candidates|created|existing>`,
  `<medication|obligation>_<candidates|created|existing>`, `skipped_inactive_target` and
  `skipped_frequency_mismatch`.

**Cloud Logging queries** (Logs Explorer, project `medi-agent-490106`):

```text
# Document ingestion: every finished run
resource.type="cloud_run_job" AND resource.labels.job_name="mediagent-document-ingestion"
jsonPayload.event="scheduled_job.finished" AND jsonPayload.job="document_ingestion"

# Reference refresh: every finished run
resource.type="cloud_run_job" AND resource.labels.job_name="mediagent-health-knowledge-refresh"
jsonPayload.event="scheduled_job.finished" AND jsonPayload.job="health_knowledge_refresh"

# Reminders: every finished run (API service)
resource.type="cloud_run_revision" AND resource.labels.service_name="mediagent-backend"
jsonPayload.event="scheduled_job.finished" AND jsonPayload.job="reminders_dispatch"

# Email dispatch: every finished run (API service)
resource.type="cloud_run_revision" AND resource.labels.service_name="mediagent-backend"
jsonPayload.event="scheduled_job.finished" AND jsonPayload.job="email_dispatch"

# Any job that failed or was skipped
jsonPayload.event="scheduled_job.finished" AND jsonPayload.status!="success"
```

Do not filter these lines with `severity>=INFO` alone when looking for older executions:
before this change the Jobs wrote lines without a severity, which Cloud Logging stores as
`DEFAULT`.

**Manual GCP setup for the reminder trigger** (already done; kept for rebuilding)
- **Step 1:** Create a strong random `CRON_AUTH_TOKEN` secret in GCP Secret Manager
- **Step 2:** Add `CRON_AUTH_TOKEN` to the Cloud Run backend service as a secret-backed env var
- **Step 3:** In Cloud Scheduler, create an HTTP job for the reminder endpoint
- **Step 4:** Set method to `POST` and target URL to the Cloud Run backend URL plus the cron path
- **Step 5:** Add custom header `X-Cron-Auth: <same token>`
- **Step 6:** Keep the reminder dispatcher in UTC and let the backend decide which records are due based on DB state

### 6. Managing Secrets (Environment Variables)
Since we have multiple cloud platforms, keeping `.env` files synced is critical.
- **Local Dev:** We maintain separate templates for backend and both portals. Teammates should duplicate:
  - `/.env.example` → `/.env`
  - `apps/patient-portal/.env.example` → `apps/patient-portal/.env.local`
  - `apps/clinician-portal/.env.example` → `apps/clinician-portal/.env.local`
- **Backend (GCP):** Secrets (Supabase, Sentry, SMART, Deepgram, Resend, `CRON_AUTH_TOKEN`) live in GCP Secret Manager and are referenced by the Cloud Run service and Jobs. Vertex AI uses the runtime service account, not an API key.
- **Frontend (Vercel):** Add them through the Vercel Project Settings -> Environment Variables.

### 7. Sentry Setup (Error Monitoring)
- **Step 1:** Go to Sentry.io and create a free Developer plan.
- **Step 2:** Create three projects:
  - `mediagent-backend`
  - `mediagent-patient-portal`
  - `mediagent-clinician-portal`
- **Step 3:** Invite teammates to the Sentry org.
- **Step 4:** Add DSNs to the correct runtime env files and hosting platforms:
  - backend → `BACKEND_SENTRY_DSN` in local `/.env` and Cloud Run secrets/env
  - patient portal → `PATIENT_PORTAL_SENTRY_DSN` and `NEXT_PUBLIC_PATIENT_PORTAL_SENTRY_DSN` in local `apps/patient-portal/.env.local` and Vercel
  - clinician portal → `CLINICIAN_PORTAL_SENTRY_DSN` and `NEXT_PUBLIC_CLINICIAN_PORTAL_SENTRY_DSN` in local `apps/clinician-portal/.env.local` and Vercel
- **Step 5:** Keep `sendDefaultPii` disabled and use selective error reporting so Sentry captures operational failures without leaking patient data or flooding the dashboard with expected 4xx errors.
