# Phase 1.4: Cloud Infrastructure & Cost-Saving Strategy

This guide outlines exactly how we will deploy the MediAgent infrastructure and, more importantly, **how we will stretch our $300 Google Cloud credit across the next 10 months** leading up to the December demo.

## The "Scale-to-Zero" Cost Strategy

To survive 10 months on a fixed budget, our golden rule is **Scale-to-Zero**. We will rely heavily on generous free tiers across all platforms, ensuring that when the app is not actively being developed or demoed, it costs exactly $0.00.

| Service | Platform | Cost Strategy | Expected Monthly Cost |
|---------|----------|---------------|------------------------|
| **Backend API** | GCP Cloud Run | Set `min-instances: 0` and `max-instances: 2`. Cloud Run's free tier gives 2M requests/month free. It will spin down completely when not in use. | $0.00 |
| **Frontend (Portals)** | Vercel | Use a **Hobby** account. Do NOT create a Vercel "Team" ($20/mo/user). Have one person link the GitHub repo; PRs will still auto-deploy preview links for everyone via GitHub integrations. | $0.00 |
| **Database & Auth** | Supabase | Free tier. Note: Free projects pause after 1 week of inactivity. Just go to the Supabase dashboard and click "Restore" when returning to work. | $0.00 |
| **Scheduled jobs** | GCP Cloud Scheduler | GCP gives 3 free Scheduler jobs per month per billing account. Three are active (document ingestion, weekly reference refresh, reminders); the retired ADR scan trigger should be deleted. See section 5. | $0.00 |
| **Error Tracking** | Sentry | Developer Free Tier gives 5,000 errors/month. | $0.00 |
| **AI Subsystems** | Gemini API | Use the free tier (15 Requests Per Minute). Perfect for development. | $0.00 |

*With this setup, your $300 credit is purely a safety net for unexpected spikes, data egress overages, or heavy load-testing near demo day.*

---

## Execution Steps for the Team

### 1. Google Cloud Platform (GCP) Setup
We will host our backend on GCP. 

> [!CAUTION]
> **The 90-Day Credit Expiration Trap!**
> The $300 free trial credit on Google Cloud **expires exactly 90 days after activation**, regardless of how much you have spent. Since our demo is in 10 months (December), **DO NOT ACTIVATE THIS CREDIT YET.**

**The Team Account Strategy:**
If you activate the $300 credit right now, it will expire in June. Instead, use a "Relay" approach across your teammates. **You do NOT need to recreate the project or database.** Google Cloud decouples "Projects" from "Billing Accounts". You simply change which billing account powers the project.

- **Phase 1 (March – May):** Rely purely on the "Always Free" tier (`min-instances: 0` on Cloud Run). This requires a billing account, but no trial credits need to be active if we stay under limits. Alternatively, Teammate A activates their 90-day trial.
- **Phase 2 (June – August):** Teammate B activates their 90-day trial. The Project Admin goes to `GCP Console -> Billing -> Change Billing Account` and links Teammate B's new trial to the existing project.
- **Phase 3 (Sept – Demo Day):** Teammate C activates their 90-day trial, and the Project Admin links it. This credit covers the massive traffic spike, load testing, and keeping the server "warm" (`min-instances: 1`) for the live December demo.

**Setup Steps:**
- **Step 1:** Choose *one* team member's Google account to act as the current host. They create the project `mediagent-dev`.
- **Step 2:** Go to **IAM & Admin** and add all other teammates as "Project Owners" or "Billing Managers" so everyone has access to manage billing later.
- **Step 3:** Go to **IAM & Admin** and add all teammates as "Editors" so everyone has access to the console and metrics.
- **Step 4:** Enable the following APIs:
  - Cloud Run API
  - Cloud Scheduler API
  - Artifact Registry API
  - Secret Manager API

### 2. Backend Deployment (Cloud Run)
Instead of a rented server (VPS/EC2) that runs 24/7 and drains the $300 quickly, we use serverless containers.
- **Step 1:** We will create a GitHub Action (`.github/workflows/deploy-backend.yml`).
- **Step 2:** When a PR merges to `main`, the Action builds the Docker container and pushes it to GCP Artifact Registry.
- **Step 3:** The Action deploys to Cloud Run with these strict cost-saving flags:
  ```bash
  gcloud run deploy mediagent-backend \
    --image <image-url> \
    --min-instances 0 \     # <-- THIS IS THE COST SAVER
    --max-instances 2 \     # Prevents massive runaway scaling costs
    --cpu 1 \
    --memory 512Mi \
    --allow-unauthenticated
  ```
- **Why this matters:** `min-instances 0` is the secret sauce. The server sleeps when we sleep. The only downside is a slight 2-second "cold start" delay on the very first API request of the day.

### 4. Frontend Deployment (Vercel)
Vercel is unbeatable for Next.js, but team plans are expensive. We will bypass this.
- **Step 1:** One person logs into Vercel using their personal GitHub account (Hobby plan).
- **Step 2:** Create two new Vercel projects: `mediagent-patient` and `mediagent-clinician`.
- **Step 3:** Link them to the `apps/patient-portal` and `apps/clinician-portal` directories in our monorepo.
- **Step 4:** Set up Environment Variables in the Vercel UI.
- **Teammate workflow:** Teammates do NOT need Vercel accounts. When they push a commit or open a Pull Request on GitHub, Vercel's GitHub Bot will automatically build it and post a preview link directly in the PR comments!

### 5. Scheduled jobs (Cloud Scheduler) and run logs
Cloud Scheduler triggers a small set of backend jobs, and the backend fans out to the
correct patients and clinics by querying Supabase at runtime. Project `medi-agent-490106`,
Scheduler and Cloud Run region `us-central1`.

| Job (`jsonPayload.job`) | Trigger | Schedule (timezone) | Target | Auth | Run record | Healthy run |
| --- | --- | --- | --- | --- | --- | --- |
| `document_ingestion` | `mediagent-document-ingestion-every-5m` (enabled) | `*/5 * * * *` (America/Los_Angeles) | Cloud Run Job `mediagent-document-ingestion` (`python -m app.workers.document_ingestion`) | OAuth: service account `mediagent-doc-ingest-sched`, `roles/run.invoker` on the Job only | None at job level (state is kept per document); the two log lines are the run record | `status="success"`, `summary.failed=0`; `summary.claimed=0` is normal when nothing is pending. Exit code 1 when any document failed or the batch could not run. |
| `health_knowledge_refresh` | `mediagent-health-knowledge-refresh-weekly` (enabled) | `0 3 * * 0`, Sundays 03:00 (America/Los_Angeles) | Cloud Run Job `mediagent-health-knowledge-refresh` (`python -m app.workers.health_knowledge_refresh`) | OAuth: service account `mediagent-knowledge-sched`, `roles/run.invoker` on the Job only | `cron_job_runs`, `job_name='health_knowledge_refresh'` | `status="success"`, `summary.subjects_failed=0`. `subjects_checked=0` is correct only with `subjects_due=0` and no new subjects; `next_due_at` then says when the oldest cached subject becomes due. Exit code 1 when any subject raised. |
| `reminders_dispatch` | `medi-agent-reminders-dispatch-prod` (**paused since April**) | `*/15 * * * *` (UTC) | `POST https://api.mediagent.live/api/v1/cron/reminders/dispatch` on service `mediagent-backend` | Shared secret: `X-Cron-Auth` header equal to the backend's `CRON_AUTH_TOKEN` | `cron_job_runs`, `job_name='reminders_dispatch'` | `status="success"`, `summary.window_mode="contiguous"` and a small `catch_up_minutes`. `catch_up_capped` means the previous run ended over an hour earlier. |
| `nightly_adr_scan` | `medi-agent-adr-nightly-scan-prod` (paused since April) | was `0 2 * * *` (UTC) | **Retired.** The `/api/v1/cron/adr/nightly-scan` route was removed. | was the shared-secret header | Earlier rows stay in `cron_job_runs` | Not applicable. |

**Why the ADR scan was retired.** Chat intake already sets `flagged_for_adr` under the
stricter AI-004 rule (an active medication match plus explicit Naranjo link evidence,
`followup/service.py::is_possible_adr_candidate`) and starts the pharmacovigilance review.
The scan flagged any medication-linked symptom without starting a review, which would have
put unreviewed ADR labels into the clinician symptom timeline and SOAP notes. **Requester
action:** delete the paused Scheduler job `medi-agent-adr-nightly-scan-prod`. If it were
resumed it would only receive `404`.

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
  `subjects_new_conditions`, `subjects_checked`, `subjects_updated`,
  `subjects_unavailable`, `subjects_failed`, `subjects_deferred` (over the limit of 150),
  `next_due_at`, and `sources.<medlineplus|dailymed>.<updated|unchanged|not_found|unavailable>`.
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
- **Backend (GCP):** Store secrets (Supabase keys, Gemini keys) in GCP Secret Manager. We will grant the Cloud Run service account access to read them at runtime.
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

---

## 🎯 Summary for Demo Day (December)
By strictly following the `min-instances: 0` rule and leveraging free tiers, the $300 credit will remain largely untouched by December. 

**Demo Preparation:**
About one week before the live demo, we will temporarily update our Cloud Run deployment to `min-instances: 1`. This stops the container from sleeping, ensuring there is absolutely zero "cold start" delay when presenting to the judges/audience. This will finally start burning a few dollars of the $300 credit, but you will have plenty of budget left to easily cover it!
