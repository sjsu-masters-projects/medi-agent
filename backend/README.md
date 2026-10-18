# MediAgent Backend

> FastAPI backend for the MediAgent multi-agent healthcare platform.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

`requirements.in` and `requirements-dev.in` contain direct dependency intent;
the corresponding `.txt` files are exact, generated locks used by CI and
Docker. After changing an `.in` file, refresh both locks with the pinned CI
resolver:

```bash
uv pip compile requirements.in --universal --python-version 3.12 --output-file requirements.txt
uv pip compile requirements-dev.in --universal --python-version 3.12 --output-file requirements-dev.txt
```

Security floors also cover [multidict's items-view reference leak](https://github.com/aio-libs/multidict/security/advisories/GHSA-54p9-h82j-f925)
(`>=6.9.1`) and [LangGraph SDK resource authorization](https://github.com/langchain-ai/langgraph/security/advisories/GHSA-fvww-7h3r-vfhp)
(`>=0.4.4`), and [Vertex AI predictable bucket naming](https://github.com/advisories/GHSA-wh2j-26j7-9728)
(`google-cloud-aiplatform>=1.133.0`). Both locks retain these patched versions. Run the
CI audit with Python 3.12; system Python 3.14 cannot resolve all packages in this lock.
The universal lock omits the legacy `google-generativeai` SDK on Python 3.14: its
`protobuf<6` pin cannot coexist with a patched Vertex AI SDK there, and Docker and CI
run 3.12.

## Run

```bash
PYTHONPATH=src uvicorn app.main:app --reload
# API docs → http://localhost:8000/docs
```

## Lint & Test

```bash
ruff check src/                        # lint
ruff format --check src/               # format check
mypy src/ --ignore-missing-imports     # type check
PYTHONPATH=src pytest tests/ -v        # test
```

### Testing & Coverage

```bash
# Run all tests with terminal coverage summary (default in pyproject)
python -m pytest tests/ --cov=app --cov-report=term-missing

# Run specific test file
python -m pytest tests/unit/services/test_dailymed_service.py -v

# Run tests without coverage (faster for development)
python -m pytest tests/ --no-cov

# Generate HTML coverage report in a single fixed folder (backend/htmlcov)
./scripts/generate_html_coverage.sh

# View coverage report
open backend/htmlcov/index.html
```

**Coverage Requirements:**
- Minimum: 80% (`--cov-fail-under=80` in `pyproject.toml`, enforced in CI)
- All external APIs must be mocked in tests

See [tests/TESTING_GUIDE.md](tests/TESTING_GUIDE.md) for comprehensive testing documentation.

## Runtime configuration ownership

`app/config.py` supplies defaults; real process environment variables override
those defaults. Local startup may also load the repository-root `.env` (or CWD
`.env` if that file is absent). Never copy credentials into documentation or test
reports. `.env.example` documents intent, not proof of local overrides.

The Cloud Run service deploy in `.github/workflows/deploy-backend.yml` uses
`--update-env-vars`: unrelated settings and secret references survive deployment,
but the named model/location/timeout settings are re-pinned on every deploy.
Change those declarations together with defaults/examples when promoting a model;
a console-only model change is temporary. `GOOGLE_PROJECT_ID` is currently an
out-of-band service setting and must remain configured for Vertex routing.

The document-ingestion and health-knowledge jobs use `--set-env-vars` and
`--set-secrets`, declaring their entire environment. Manual additions to a job do
not survive its next deployment. Ingestion receives the Gemini settings and batch
size; the public-source health-knowledge job does not require Gemini settings.

Serving uses `GEMINI_VERTEX_AI_LOCATION` and Vertex credentials. The separate
`VERTEX_AI_LOCATION` is retained for managed open-weight evaluation, not current
chat routing. `GOOGLE_API_KEY` supports the legacy explicit AI Studio path, not
normal Vertex requests. Embedding/RAG settings currently have no runtime consumer;
do not infer an active embedding pipeline from their presence in the example.

October 11 read-only audit: main `8b93b48`, live service revision
`mediagent-backend-00126-c94` (100% traffic), service and ingestion model settings
match the workflow; knowledge job has only its declared public-source/DB settings.
Both live portal URLs and branded email From values are configured. The onboarding
From variable occurs twice with identical values in the service and needs a
separately authorized deduplication. No local credential file or secret value was
inspected, and no model call, deployment or remote change was performed by this
audit. Config/ADK/provider/client/worker focused tests: **54 passed**. Configuration
agreement and mocked tests do not establish current provider availability.

## MedWatch Form 3500 drafts (PV-001-C)

Assigned clinicians prepare an evidence-attributed **Form FDA 3500 (09/2025)** draft from a
draft ADR assessment, edit it with optimistic revision control, preview it laid out like the
form, approve it with a versioned attestation, download the official fillable PDF or a JSON
copy, record a submission they made to FDA themselves, and discard a mistaken draft. MediAgent
never submits anything to FDA; there is no network path to any FDA system. The workflow is
`app.services.medwatch_service` plus `app.services.medwatch_3500` (template, field map, PDF
fill, gate, identifier, 048 upgrade, preview). Form values and the PDF owner password are
never logged.

Routes (all `require_role("clinician")`, active care-team assignment re-checked; a missing
record is 404, an unassigned clinician 403):

| Route | Purpose |
| --- | --- |
| `POST /api/v1/clinicians/me/adr-assessments/{id}/medwatch-draft` | Prepare a v2 draft (`{decision: "prepare_draft", reportability_rationale}`) |
| `GET /api/v1/clinicians/me/adr-assessments?status=draft\|reviewed\|submitted\|dismissed\|all&patient_id=` | List assigned-patient assessments (`all` for every status, `patient_id` narrows to one assigned patient) |
| `GET /api/v1/clinicians/me/adr-assessments/{id}` | One assessment of any status; an unknown or unassigned id is the same 404 |
| `GET /api/v1/clinicians/me/medwatch-drafts?state=active\|draft\|approved\|submitted\|discarded` | List; each item has `missing_for_approval`, `name_warnings`, `pdf_available`, `current_submission`, `submission_history` (newest first), `attestation`, `template` |
| `GET .../medwatch-drafts/{id}` | One draft (same shape as a list item); an unknown or unassigned id is the same 404 |
| `GET .../medwatch-drafts/{id}/preview.pdf` | Filled Form 3500 stamped "DRAFT – not for submission" on every page, `Content-Disposition: inline`, `Cache-Control: no-store`. Not an export: no export record and no state change; one `preview_viewed` audit event with the actor |
| `GET .../medwatch-drafts/form-3500-options` | Option lists for the editor (units, routes, frequencies, occupations, countries, ...) |
| `PUT .../medwatch-drafts/{id}` | Save `{form_data (v2), expected_revision}` |
| `POST .../medwatch-drafts/{id}/approve` | `{approval_note, expected_revision, attested, attestation_version: "medwatch-3500-approval-v1", non_serious_attested, acknowledged_warnings}` |
| `GET .../medwatch-drafts/{id}/preview` | Read-only Form 3500 layout (sections A to G, C and E not completed by MediAgent) |
| `GET .../medwatch-drafts/{id}/export.pdf` | Official PDF, `Content-Disposition: attachment; filename="fda-3500-<first 8 of id>-not-submitted.pdf"`, `Cache-Control: no-store` |
| `GET .../medwatch-drafts/{id}/export` | JSON copy, `artifact_type: "fda_3500_draft"` |
| `POST .../medwatch-drafts/{id}/discard` | `{reason, expected_revision}`; the assessment returns to review |
| `POST .../medwatch-drafts/{id}/submission` | `{submitted_on, method, method_detail?, fda_reference?, attested: true, expected_revision}` |
| `POST .../medwatch-drafts/{id}/submission/amend` | `{amends_id, submitted_on, method, method_detail?, fda_reference?, reason}` |

Error codes (envelope `{"error": {"code", "message", "details"?}}`): 422
`MEDWATCH_APPROVAL_INCOMPLETE` (`details.missing_for_approval`),
`MEDWATCH_WARNINGS_NOT_ACKNOWLEDGED` (`details.name_warnings`),
`MEDWATCH_LEGACY_DRAFT_INCOMPLETE`, `MEDWATCH_NOT_APPROVED`, `MEDWATCH_NOT_SUBMITTED`,
`MEDWATCH_DRAFT_DISCARDED`, `MEDWATCH_DRAFT_SUBMITTED`, `MEDWATCH_DRAFT_NOT_EDITABLE`,
`MEDWATCH_DRAFT_EXISTS`, `ADR_REVIEW_ALREADY_COMPLETED`, `MEDWATCH_IDENTIFIER_IDENTIFIES`,
`MEDWATCH_REVIEW_FIELDS_LOCKED`, `MEDWATCH_SUBMISSION_INVALID`, `MEDWATCH_INVALID_STATE`,
`MEDWATCH_INVALID_REQUEST`; 409 `MEDWATCH_REVISION_CONFLICT`, `MEDWATCH_SUBMISSION_CONFLICT`;
503 `FORM_3500_TEMPLATE_MISMATCH` (no export recorded); 502 `FORM_3500_RENDER_FAILED` (no
export recorded) and `EXTERNAL_SERVICE_ERROR` (the export audit failed, so no bytes are
returned). PostgREST detail is never returned.

The official template is vendored at `src/app/assets/fda/form-3500-2025-09.pdf` with a
generated `TEMPLATE.json` record; it is loaded with `importlib.resources`, never downloaded at
runtime, and checked against its SHA-256, page and field inventory and every mapped field name
on every export. Re-pin steps (download into an empty directory outside the repository,
compare size and SHA-256 and stop on a difference, repeat the copyright check, regenerate the
record with `scripts/generate_form_3500_template_record.py`) are in
[`src/app/assets/fda/README.md`](src/app/assets/fda/README.md). The fill uses `pypdf==6.20.1`
(pinned in `requirements.in`; BSD), not PyMuPDF, writes the AcroForm fields and the XFA
`datasets` packet, keeps the form fillable and re-encrypts it with the template's
permissions.

Database: `048_medwatch_draft_lifecycle.sql` (applied to `mediagent-staging`) and
`064_medwatch_form_3500.sql`, which requires `063_adr_information_loop_lifecycle.sql`. **063 and
064 were applied to the hosted project by the requester on October 13** and the backend that
calls them (the 6-argument create, 5-argument approve and export, discard and submission RPCs,
the submission table and the discard columns) is deployed. In a fresh environment apply 063
then 064 before that backend. Verify with:

```bash
python scripts/validate_migrations.py
PYTHONPATH=src .venv/bin/pytest tests/unit/db/test_medwatch_form_3500_migration.py --no-cov -q
NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER=1 PYTHONPATH=src \
  .venv/bin/pytest tests/integration/test_medwatch_3500_postgres.py --no-cov -q
```

## Care-plan model preflight

Before deploying a change to care-plan classification or its provider route, validate the
exact worker contract against synthetic facts:

```bash
cd backend
PYTHONPATH=src .venv/bin/python scripts/preflight_care_plan_classification.py --dry-run
PYTHONPATH=src .venv/bin/python scripts/preflight_care_plan_classification.py
```

Run the live command locally with the normal backend configuration loaded (the
app settings import requires Supabase variables), Vertex credentials,
`GOOGLE_PROJECT_ID`, `GEMINI_VERTEX_AI_LOCATION=global`, and the configured
`GEMINI_FLASH_MODEL`. It classifies 12 fictional facts through the production
route and prints only counts and safe failure categories. It never reads the
database, prints model output, or publishes a plan. This credentialed model call
is an operator-run local check, not a CI or deployment gate. Deterministic
contract tests run in PR CI without cloud
credentials. Record the local preflight result with the PR verification evidence.

## Model capacity preflight

After offline tests, an operator may run this small paid, synthetic-only check:

```bash
VERTEX_AI_LOCATION=global GEMINI_VERTEX_AI_LOCATION=global PYTHONPATH=src \
  .venv/bin/python scripts/preflight_model_capacity.py --include-oss
```

Omit `--include-oss` to check only the current triage primary. The probe reports
per-attempt safe metadata, first-attempt success, retry recovery, fallback count,
total latency and synthetic answers for manual English/Spanish review. It does
not read/write the database, change routes or deploy. JSON/urgency checks must
pass independently of HTTP success. Four cases per primary cannot establish
clinical quality or availability under load. Offline tests simulate 429s;
live checks do not deliberately overload providers. Per-process concurrency
limits do not coordinate across Cloud Run replicas or Jobs.

## Nora turn recovery (PAT-001-A / PAT-004)

The patient websocket opts into durable execution with `turn_protocol=1`.
`user_message` includes a UUID `client_message_id`, the exact text/language/audio,
and an explicit `document_id` (null for general questions). Retries reuse those
values. `chat_turn` and `chat_turns` carry processing/completed/failed/interrupted
status and safe retry eligibility. `recover_turns` refreshes saved status/history;
`dismiss_turn` hides only an interrupted/failed reply, never resolves clinical work.
Client requests stay in memory; saved turns recover from the server after refresh.

Migration `071_nora_turn_recovery.sql` is backend-only, with RLS and browser grants
revoked. Apply it **only with separate operator authorization**, before backend
and patient rollout. Older clients retain their existing contract, not durable
retry guarantees. An unavailable durable store must fail closed, not rerun through
the legacy path. Full contract and verification:
[PAT-001-A](../.agent/specs/pat-001-a-nora-turn-recovery.md).

## Package Layout

```
src/app/
├── main.py           # App factory — creates FastAPI, mounts routers
├── config.py         # Env vars → typed Settings object
├── core/             # Exceptions, auth helpers, constants
├── models/           # Pydantic schemas (Create/Read/Update per entity)
├── routers/          # HTTP endpoints — thin, delegate to services
├── services/         # Business logic — no FastAPI imports, testable
├── adk/              # Current agent runtime, registry, and safety plugins
├── agents/           # Legacy compatibility paths; no new product work
├── tools/            # FHIR builder and medication normalizer
├── clients/          # SDK wrappers (Gemini, Deepgram, etc.)
├── db/               # Supabase connection helpers, repositories, migrations, seed data
│   └── migrations/   # SQL files — run in order (001_, 002_, ...)
├── workers/          # Cloud Run Job entry points (document ingestion, reference refresh)
├── safety/           # Deterministic triage floor and escalation
├── followup/         # Symptom follow-up and ADR candidate rules
├── pharmacovigilance/ # Naranjo scoring
├── mcp/              # In-process provider adapters (Supabase, Deepgram)
├── middleware/       # Shared middleware helpers such as endpoint rate limiting
└── utils/            # Shared helpers
```

## Appointment calendar export

`GET /api/v1/appointments/{id}/calendar?locale=en-US` (or `es-MX`) returns
`{ filename, content }` as authenticated JSON with `Cache-Control: private, no-store`.
Portals turn this into a local `text/calendar` download without placing tokens in
URLs. The service checks the owning patient or an actively assigned clinician and
fresh `confirmed`/`scheduled` status on every request. Other statuses return
`APPOINTMENT_UNAVAILABLE` (422); unauthorized users cannot export.

The RFC 5545 serializer uses UTC start/end instants, elapsed duration, a stable event
UID, localized generic title/one-time-copy notice, and safely escaped/folded location
text. It omits clinical reasons, notes, and attendee/invitation fields. No state
mutation, external calendar call, or migration is needed for this endpoint.

## Human care-team conversations

Authenticated `/api/v1/care-conversations` routes implement explicitly addressed
patient/linked-clinician threads, separately from Nora and operational alerts.
Migration `048_care_team_conversations.sql` backs these routes (merged in #139 and
deployed). No legacy notification is converted into
a human message. Existing assignment and current clinic authorization are checked
inside the same transaction as each read, send and audit operation.

Threads are unique to `(care_team_id, patient_id, clinician_id, clinic_id)`.
Reassigning a pair or clinic permits a fresh thread for the current binding;
historical threads, messages and audit remain stored but are inaccessible while
their binding differs from the active assignment. Inbox presentation uses latest
message time descending (NULL last), then conversation ID, independently of the
UUID-ordered assignment locks.

Message retries reuse a sender-scoped UUID key; a changed body or thread rejects
reuse. Pagination uses `(created_at, id)`, and read markers advance only through
the specified message. Browser database grants are intentionally absent; callers
use the API. Message bodies must not be logged. See
`../.agent/specs/com-001-two-way-conversations.md` for the full contract and rollout
boundary. This is not authorization for real-PHI use or a clinical-readiness claim.

Run the isolated database contract suite with synthetic CI settings and an
already available official `postgres:16` image:

```sh
CARE_CONVERSATION_TEST_POSTGRES_DOCKER=1 PYTHONPATH=src \
  .venv/bin/pytest tests/integration/test_care_conversation_postgres.py --no-cov -q
```

The disposable container has no network, published ports or host volumes and
is removed after the tests. The suite loads actual migrations 001, 002, 006, 007,
the private-helper bootstrap of 020, and full 022/048. This exercises real enum
types, profile/assignment RLS, pending-invite columns and service-role grants.
Auth is a minimal platform stub; unrelated storage/vector/Auth-hook portions of
020 and the remaining migration chain are not rehearsed. These tests do not prove
deployment, PostgREST integration or live acceptance.

Before a separately authorized rollout, run this read-only, count-only preflight
in the chosen environment. It prints no patient, clinician or assignment IDs:

```sql
SELECT count(*) AS active_assignments,
       count(*) FILTER (WHERE c.clinic_id IS NULL) AS active_assignments_without_clinic,
       count(*) FILTER (WHERE t.patient_id IS NULL) AS active_assignments_without_patient
FROM public.care_teams t
JOIN public.clinicians c ON c.id = t.clinician_id
WHERE t.status = 'active';
```

Review nonzero missing-binding counts before rollout. The conversation API
fails closed for those assignments; this preflight does not repair, backfill or
authorize changing them.

## In-app notification centre (NOT-001)

The role-scoped `/api/v1/notification-centre` API presents saved events and
current clinician work; its read operations never perform clinical approval.
See [the notification contract](../.agent/specs/not-001-notification-centre.md)
for recipient rules, endpoints, migration/acceptance boundaries and portal behaviour.
Short-lived actor-bound read snapshots contain exact receipt IDs, so a concurrent
arrival is not consumed by a bulk read. Human conversation read markers remain
authoritative. Events are captured atomically; browser event creation is denied.
The legacy patient `/notifications` endpoints remain compatible. No new push,
email or SMS channel is introduced. Merged in #148/#149 and deployed; migrations
`051_notification_centre.sql` and 052–056 are applied to the synthetic project.

## Clinic lists, roles and settings (CLN-003 slices C and D)

Every clinician list that returns patients or patient work takes an optional `clinic_id` query
parameter and tags each item with `clinic_id` and `clinic_name` (the clinic of that clinician's
care-team link, `care_teams.clinic_id`): `GET /clinicians/me/patients`, `.../dashboard`,
`.../document-review-queue`, `.../adr-assessments`, `.../medwatch-drafts`, `.../messages`,
`GET /care-conversations/` and `/recipients`, `GET /appointments/`, and the notification centre
list and action items (`/notification-centre`, `/notification-centre/action-items`). The patient
header (`GET /clinicians/me/patients/{id}`) and the patient deep dive carry the tags too. Without
`clinic_id` nothing is filtered. A clinic where the caller has no active membership returns an
empty result (never an error that distinguishes it from a clinic with no matches). The shared
logic is `ClinicMembershipService.link_scope` (`app/services/clinic_link_scope.py`).

New clinic-scoped writes, all through `clinician_clinic_operation` and all audited:
`PUT /clinicians/me/default-clinic`, `POST /clinicians/me/clinics/{clinic_id}/leave` (refused for
the last clinic, `LAST_CLINIC`, and the only admin, `SOLE_ADMIN`; ends the caller's own care-team
links and unused invite codes at that clinic), and `PUT /clinicians/me/clinics/{clinic_id}` (clinic
display name, admin at that clinic only, `CLINIC_NAME_TAKEN`). Migration
`067_clinic_lists_and_roles.sql` carries the SQL (applied October 17). See `.agent/specs/clin-003-multi-clinic-clinicians.md` for the design and decisions.

## Database Migrations

Migrations are plain SQL files in `src/app/db/migrations/`, currently `001`–`067`. Some
prefixes are shared by independent files; the migration ledger records full filenames and
checksums, so do not maintain a second migration inventory here. New-environment order for
the appointment booking guards (042/043) is in the setup guide.

Full setup guide: **[docs/supabase_setup_guide.md](../docs/supabase_setup_guide.md)**

Validate migration naming, sequence continuity, and PostgreSQL syntax before applying a change:

```bash
python scripts/validate_migrations.py
```

Care-plan drafts may retain missing instructions/frequency as review blockers
(`043_incomplete_care_plan_drafts.sql`); approval still requires complete active items and
completed generation. Run the deterministic local PostgreSQL check with `initdb`, `pg_ctl`, and `psql` installed:

```bash
CARE_PLAN_TEST_POSTGRES=1 PYTHONPATH=src .venv/bin/pytest tests/integration/test_care_plan_postgres.py --no-cov
```

This starts and stops disposable local clusters, never uses the configured remote
database or cloud credentials, and remains opt-in rather than a live CI preflight.

If macOS shared-memory limits prevent `initdb` from starting, a cached official
PostgreSQL 16 Docker image can run the same tests without changing kernel limits:

```bash
CARE_PLAN_TEST_POSTGRES=1 CARE_PLAN_TEST_POSTGRES_DOCKER=1 PYTHONPATH=src \
  .venv/bin/pytest tests/integration/test_care_plan_postgres.py --no-cov
```

Docker mode creates a uniquely named, disposable container per test, with no
network or published ports. It never pulls an image automatically and removes
only containers created by this fixture. Synthetic test database contents are
discarded afterward; no existing container or remote database is modified.

## Medication and condition reference (Nora)

Nora's general medical knowledge comes from public National Library of Medicine sources,
shared by every patient and cached in `health_knowledge` (migration 051): MedlinePlus
plain-language summaries in English and Spanish, DailyMed label sections (never dosage),
and RxNorm for name resolution. A chat lookup fetches on a miss within a short time budget;
the `mediagent-health-knowledge-refresh` Cloud Run Job re-checks the cache weekly and
records each run in `cron_job_runs`. A subject is due six days after its last check; active
medications and documented conditions with no cached text are added. Run it locally against
your configured project with:

```bash
cd backend
PYTHONPATH=src .venv/bin/python -m app.workers.health_knowledge_refresh
```

Design, checks and failure behaviour: `.agent/specs/nora-002-grounded-answers.md`.

## Scheduled jobs

Document ingestion (every 5 minutes), the reference refresh (Sundays 03:00
America/Los_Angeles) and reminder dispatch (every 15 minutes, via
`POST /api/v1/cron/reminders/dispatch` with `X-Cron-Auth`) each write one
`scheduled_job.started` and one `scheduled_job.finished` JSON line per run
(`app/core/job_logging.py`). The finished line carries `status`, `duration_ms` and the same
`summary` as `cron_job_runs`. Email delivery runs as its own `email_dispatch` job after
every real reminder run (a failure there never fails the reminder response) and on
`POST /api/v1/cron/emails/dispatch` (`X-Cron-Auth`, optional `{"dry_run": true}`), with the
same two log lines and a `cron_job_runs` record. New invitations and verification codes are
sent at once by their own request; the job retries, sends notices and reconciles provider
status (full-access Resend key needed for status). The nightly ADR scan is retired.
Triggers, auth, healthy-run signals and Cloud Logging queries:
`.agent/CLOUD_INFRASTRUCTURE_GUIDE.md`, section 5.

## Key Conventions

- **Routers are thin** — validate input, call service, return response
- **Services are pure** — no FastAPI imports, easy to unit test
- **Models use `StrEnum`** — catches bad values at the API boundary, serializes to plain strings
- **All IDs are `UUID`** — matches Supabase
- **Custom exceptions** — `core/exceptions.py`, not raw `HTTPException`

## Docs

| Doc | What it covers |
|-----|----------------|
| [PROJECT.md](../.agent/PROJECT.md) | Product context, decision log |
| [ARCHITECTURE.md](../.agent/ARCHITECTURE.md) | System design, data model, agent flow |
| [CODING_STANDARDS.md](../.agent/CODING_STANDARDS.md) | Code style rules |
| [Supabase Setup Guide](../docs/supabase_setup_guide.md) | DB schema, migrations, RLS, auth hooks |
| [workflows/new-agent.md](../.agent/workflows/new-agent.md) | How to add a new agent |

## Cross-clinic scheduling and clinic tags (CLN-003 slices E and F)

Every appointment and offer group carries `clinic_id` (and `clinician_id`) copied from its care-team
link by a database trigger, so it cannot disagree with the link. UX-006 adds
`GET /appointments/schedule?from&to[&clinic_id]` (the caller's own visits, open offers and change
requests, next visit; 45-day cap), `GET /appointments/busy?from&to` (own booked intervals with clinic
names, never patients; 48 h cap) and `GET /appointments/?patient_id=` (one linked patient's visits).
Visit management (migration 071): `POST /appointments/{id}/cancel` (`reason_code`, `reason`),
`/complete` and `/no-show`, all clinician-only for the appointment's own clinician or one linked at its
clinic and audited in `appointment_offer_events`; `PUT /appointments/{id}` edits type, location, reason
and notes but refuses a time change on a confirmed or scheduled visit (`APPOINTMENT_TIME_CHANGE_VIA_OFFER`);
`GET /appointments/schedule?include_cancelled=true` adds cancelled visits.
Message translation is never done on send or read: reads set `translation_pending` and
`POST /care-conversations/{id}/messages/{message_id}/translation` translates one message (same
authorization as reading the conversation, idempotent, honours a fresh failure marker).
 `GET /appointments/` rows and the
propose/respond/update responses carry `clinic_id` and `clinic_name` for both roles; a clinician's list
shows only visits at clinics where they hold a link. A clinician cannot hold overlapping
`confirmed`/`scheduled` visits across all their clinics (exclusion constraint
`appointments_clinician_no_overlap`, `[start, end)`). `POST /appointments/propose` (and a clinician's
single `POST /appointments/`) checks every slot against that whole schedule first and refuses the whole
offer with 422 `CLINICIAN_SCHEDULE_CONFLICT`, `details.conflicts[]` = `{slot, clinic_id, clinic_name,
starts_at, ends_at}`; the message is "You already have an appointment at <clinic> from <time> to <time>."
No patient of another clinic is read or returned, and the refusal is logged by count only. A patient's
accept or a patient self-booking that meets a busy clinician gets the existing generic
`APPOINTMENT_CONFLICT`. Calendar exports, appointment reminders (`cron_service`), the care-team list,
Today's provider card and Nora's care-team context name the link's or appointment's clinic, never
`clinicians.clinic_name`. Notice emails lead the subject with `<Clinic> · ` and add a header line for a
recipient who belongs to more than one clinic (`EmailDeliveryService._clinic_label`); staff invitations
name the invitation's clinic. `authorization_denial_events.clinic_id` and an `urn:mediagent:audit-clinic`
extension on FHIR audit events record the clinic when an event concerns a link. Migration
`069_clinic_scheduling_and_tags.sql` carries the SQL (applied October 17; the read-only
`scripts/appointment-clinician-overlap-preflight.sql` returned 0 rows first). In a fresh or other
environment run the preflight before applying if the migration reports overlaps.
