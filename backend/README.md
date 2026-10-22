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
(`>=6.9.1`), [aiohttp request-processing advisories](https://github.com/advisories/GHSA-2g87-pp6c-29x5)
(`>=3.14.4`) and [LangGraph SDK resource authorization](https://github.com/langchain-ai/langgraph/security/advisories/GHSA-fvww-7h3r-vfhp)
(`>=0.4.4`), and [Vertex AI predictable bucket naming](https://github.com/advisories/GHSA-wh2j-26j7-9728)
(`google-cloud-aiplatform>=1.133.0`). Both locks retain these patched versions. Run the
CI audit with Python 3.12; system Python 3.14 cannot resolve all packages in this lock.
The universal lock omits the legacy `google-generativeai` SDK on Python 3.14: its
`protobuf<6` pin cannot coexist with a patched Vertex AI SDK there, and Docker and CI
run 3.12.

Pillow is floored at `>=13.0.0,<14.0.0` for the image-decoder/encoder security
fixes in [Pillow 13.0.0](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html).
Both generated locks retain the same patched version. Document preview, raster
preprocessing and OCR regression tests cover this upgrade; never bypass the
dependency audit to retain an affected image-processing library.

## FHIR import and export (INT-002)

SMART import retrieval is bounded before persistence: 20 pages per query,
50 requests and 8 MiB per import, 2 MiB per response, 1,000 resources including
Bundle envelopes and at most eight nested Bundle levels. Oversized input fails;
it is not silently truncated. Pagination cannot leave the trusted issuer base
or follow redirects with a bearer token. Source business identifiers remain
immutable metadata, visible through the existing authorized source-detail API.
Existing envelopes are read without backfill. Fetch errors omit upstream bodies
and credentials. These application limits do not establish FHIR conformance.

`GET /api/v1/smart/patients/{patient_id}/record-export` downloads the current
clinician-visible canonical core as an `application/fhir+json` collection.
It reuses shared-core authorization and condition privacy, validates the entire
file before returning it, and sets `Cache-Control: no-store`. It is a subset,
not an order, full chart or handoff approval. Re-import creates pending candidates.
No migration or additional environment variable is required. See the
[mapping and export guide](../docs/smart-fhir-review-mapping.md#identifier-fidelity-and-clinical-core-export).

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

### Notification snapshot signing (NOT-003)

`NOTIFICATION_TOKEN_SIGNING_SECRET` is an optional independent server-only root
of at least 32 random characters, consistent across API replicas. Set it through
the approved secret/configuration process, never a frontend variable or committed
file. Notification tokens always use an HMAC-SHA256 purpose-derived key, not the
raw root or Supabase authentication signing key. If the independent root is absent,
the purpose-derived rollout fallback uses the auth root; it separates token
protocols, but does not provide independent root-compromise protection.

Deploying this change or rotating the notification root invalidates earlier
15-minute notification snapshots/cursors: refresh the view and retry the read
action. Authentication sessions and stored read state are unchanged. There is no
legacy raw-auth-key verification fallback. During mixed-version rollout, an older
replica can reject a new snapshot or vice versa; refresh after rollout convergence.
Do not regenerate a clinical event. No remote secret/key/configuration change is
performed by this code.

October 21 authorized configuration: the backend references Secret Manager
`NOTIFICATION_TOKEN_SIGNING_SECRET:1`; the existing deployment workflow preserves
this reference with `--update-*`. This configuration-only revision keeps the
previous image and does not itself activate new code. Verify notification reads
after the signing implementation is merged/deployed. Do not rotate Supabase login
keys or add this server-only secret to either portal.

Clinician accounts referenced by clinical audit/provenance are retained. Permanent
clinician deletion is not an expo requirement; preserve attribution and existing
database restrictions instead of nulling or deleting clinical history.

### Source review and timeline (#208)

The clinician timeline endpoint is assignment-scoped, read-only and bounded to
40 dated rows per source bucket and ten own conversations. Message reads reuse
the exact-thread authorization RPC. Source failures and missing dates are explicit;
calculation/retrieval times are not clinical review dates or a full audit trail.

Migration `079_unlisted_product_review_alerts.sql` adds atomic forward-only review
capture for newly confirmed unlinked product concerns. It does not approve/add a
medicine, infer a medication FK from cached context, or create an ADR/Naranjo score.
Existing authorized notification acknowledgement records seen-for-follow-up only.
Review the checksum and apply through the ledger only with separate authorization;
no historical notification backfill is performed. Deploy reviewed code before
testing a new confirmation, then verify the exact report destination and read audit.

### Demo follow-ups: activity review and evaluation

COM-002 adds optional `care_plan_item_id` to private conversation sends. Only a
patient may attach an item from their current approved plan. The backend stores
the reference atomically with the message; retries compare body, thread and
activity identity. Reads include `activity_context` with approved wording and a
current/historical indicator. UUIDs remain link identities, not patient-facing copy.

`POST /api/v1/care-conversations/{conversation_id}/messages/{message_id}/activity-review`
is an explicit clinician action. It rechecks the exact private thread, active
assignment and approved source, then creates/reuses a draft and returns
`{patient_id, plan_id, item_id}` for the editor. It audits the message/source/target
link. Ambiguous or removed matches in an existing draft are rejected; no duplicate
activity is appended. Neither messaging nor opening review publishes or changes
medications, reminders or adherence history. All existing publication and bilingual
verification gates still apply. `ACTIVITY_CONTEXT_UNAVAILABLE` is a safe rejection,
not raw database text.

Apply reviewed `076_care_conversation_activity_review.sql` **before** deploying
this backend; application needs separate requester authorization. The migration is
rerunnable, retains prior data and verifies backend-only function access and RLS.
No remote application is recorded by this PR. The existing generic conversation
RPC remains compatible for older deployments during rollout.

SOAP uses the registry with `SOAP_AI_ENABLED=true` and an optional
`SOAP_GENERATION_TIMEOUT_SECONDS=90` operational ceiling. Defaults need no deployed
environment change. Failure or disabled generation writes no invented note.
Synthetic evaluation commands, paired cases and raw-final-response reporting are
documented in [the demo evaluation guide](../docs/demo-ai-evaluation.md).

### Environment ownership

Nora connection initialization tolerates only the specifically missing
`symptom_reports.confirmation_state` column during confirmed-intake rollout: it omits
symptom reports and exposes `recent_symptoms_available=false` to the patient-context
tool. It never reads legacy reports as a substitute. Other initialization errors
produce a generic `chat_initialization_failed` event and close with 1011; internal
error details are not sent to the patient. This compatibility path does not replace
authorized migration 060 rollout or enable intake.

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
[`src/app/assets/fda/README.md`](src/app/assets/fda/README.md). The fill uses `pypdf==6.21.1`
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

**Websocket lifetime.** The Cloud Run request `--timeout` of the API service bounds how long a
websocket can stay open (at 300 s every chat socket closed at about 300 s with code 1005). The API
service is deployed with `--timeout 3600`, the Cloud Run maximum; the worker keeps 300. The
portal renews its socket quietly at about 3500 s and reconnects on any close, keeping the draft,
and a tab the socket does not feed reads the draft from `GET /api/v1/chat/turns/{id}/events?after_seq=`
about once a second while visible.

The patient websocket opts into durable execution with `turn_protocol=1`.
`user_message` includes a UUID `client_message_id`, the exact text/language/audio,
and an explicit `document_id` (null for general questions). Retries reuse those
values. `chat_turn` and `chat_turns` carry processing/completed/failed/interrupted
status and safe retry eligibility. `recover_turns` refreshes saved status/history;
`dismiss_turn` hides only an interrupted/failed reply, never resolves clinical work.
Client requests stay in memory; saved turns recover from the server after refresh.

Migration `072_nora_turn_recovery.sql` is backend-only, with RLS and browser grants
revoked. Apply it **only with separate operator authorization**, before backend
and patient rollout. Older clients retain their existing contract, not durable
retry guarantees. An unavailable durable store must fail closed, not rerun through
the legacy path. Full contract and verification:
[PAT-001-A](../.agent/specs/pat-001-a-nora-turn-recovery.md).

Migration `074_nora_late_completion.sql` lets a finished reply be saved for its current lease
even just after the deadline, and `075_notification_zone_lookup.sql` makes notification reads
fast (see [NOT-001](../.agent/specs/not-001-notification-centre.md)). Both are re-runnable and
need the same separate authorization; the backend is compatible with the database before and
after (a missing `late` key means not late). Chat-turn and notification database calls use
their own bounded thread pools (`app/core/db_pools.py`).

072 is re-runnable and ends with RLS/table/function privilege assertions. Turn rows
retain document identity/version, not summary text. A fresh authorized summary is
returned only to execution and cleaned with `normalize_patient_summary`. A failed
startup handshake stops at an unavailable state with manual reconnect; a busy claim
recovers the existing turn without resending the new text.

### Server-owned turns

A Nora reply is owned by the server, not by the websocket that sent the message. When a turn
begins, `app/services/chat_turn_runner.py` runs it as a strongly referenced `asyncio` task in a
process-level registry keyed by turn id. The websocket handler never awaits, fails, interrupts
or cancels it: a reload, phone lock, app switch, re-mount or network drop leaves the turn
running to completion (saved with its lease) or to a real model or database error. Deadlines
and leases (072-074) stay the safety net, and `actions` stays strictly lease-checked.

Sockets are viewers. Each durable socket registers for its patient and session; the running
turn's events (status, chunks, `assistant_complete`) are queued per viewer, so a slow or dead
socket never delays the turn. A socket that connects mid-reply receives the status and the draft
so far, then live chunks. A socket on another instance, or after a restart, finds an empty
registry and reads the turn through `recover`, polling until the saved reply appears. The run
leaves the registry when its task ends and a viewer when its socket closes or a send fails.
The `document_focus` event attaches or dismisses a document over the open socket.

Shutdown: the app lifespan waits up to 8 seconds for running turns; any left are marked
interrupted best-effort and otherwise reconciled by the saved deadline.

Cost: the main backend service deploys with `--no-cpu-throttling` (CPU always allocated), so a
task keeps CPU after its socket closes. Cloud Run bills an instance for the whole time it exists
while CPU is always allocated, not only during requests. `--min-instances 0` is unchanged, so
an idle service still scales to zero, and the jobs are unchanged.

## Live voice mode (VOICE-001)

`/ws/voice/{patient_id}` carries binary 16-bit mono PCM microphone frames (default
16 kHz) to a Deepgram live session (`services/voice_live.py`, `voice_connection.py`) and
streams sentence-by-sentence Aura-2 speech back. The socket authenticates the same patient
the path names and never creates chat messages: the portal sends each `utterance_final`
through the normal chat turn. Bounds (all optional, defaults in `app/config.py`):
`VOICE_LIVE_ENABLED`, `VOICE_TTS_STREAM_ENABLED`, `VOICE_LIVE_MAX_SESSION_SECONDS` (900),
`VOICE_LIVE_IDLE_TIMEOUT_SECONDS` (60), `VOICE_LIVE_MAX_SESSIONS` (20 per process, one
per patient), plus frame, queue, utterance and speech-length limits. Only
`DEEPGRAM_API_KEY` is required, on the API service; the chat worker does not use it.
Voice logs carry lengths and ids, never transcript or reply text. Protocol, failure modes
and the acceptance path: [VOICE-001](../.agent/specs/voice-001-voice-mode.md).

## Package Layout

PAT-002-B B2 checks the shared deterministic safety floor before turn-specific
retrieval/model/symptom work. Emergency turns stream reviewed direction and retain
an independent pending care-team alert through migration 059's service-only RPCs.
The existing retry worker re-drives pending delivery; it must remain enabled
(`A2A_RETRY_WORKER_ENABLED=true`). No symptom report or ADR task is created for
these turns. Non-emergency reports still use the old flow; private intake APIs
and confirmation are not implemented. See the
[B2 walkthrough and exact local test steps](../.agent/specs/pat-002-b-confirmed-symptom-intake-plan.md#18-b2--safety-takes-priority-october-10-2026)
and [checkpoint evidence and limitations](../docs/evidence/pat-002-b-acceptance-2026-10-10.md).
Migration 059 requires separate authorization before any remote application.

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

### Structured logging and turn tracing (OPS-006 phase 1)

`app/core/structured_logging.py` writes one JSON object per line on Cloud Run (`K_SERVICE` set,
or `LOG_FORMAT=json`) and one readable line elsewhere (`LOG_FORMAT=text` forces it). Fields:
`severity`, `message`, `request_id`, `turn_id`, `session_hash`, `actor_hash` (salted SHA-256
prefix), `event`, `outcome`, `duration_ms`, `logging.googleapis.com/trace` (needs
`GOOGLE_PROJECT_ID`), plus the fixed lifecycle vocabulary in `EVENT_FIELDS`. The request id is
the `X-Cloud-Trace-Context` trace id or a generated one, set by `RequestContextMiddleware` for
HTTP and websockets; uvicorn's access log is unchanged. No patient text and no exception
message is logged: exceptions appear as type plus file and line frames.

Turn lines, all with `turn_id`: `chat_turn.begin` / `retry` (`execute`, `attempt`),
`chat_model.start` / `end` (`model`, `fallback_used`, `duration_ms`), `chat_turn.actions`,
`chat_turn.complete` (`accepted`, `late`), `chat_turn.failed` / `interrupted` (`category`),
`chat_turn.recover`, `chat_turn.dismiss`, `chat_turn.finished`. Every state change names its
`trigger` (`execution`, `execution_error`, `processing_timeout`, `shutdown_cancel`,
`socket_recover`, `socket_dismiss`, `socket_connect`, `failure_report`). A refused operation
logs `reason` from migration 077 (`not_found`, `session_mismatch`, `lease_mismatch`,
`deadline_passed`, `status:<status>`; `unknown` from an older function). Find a turn in Cloud
Logging with `jsonPayload.turn_id="<id>"`.

Apply order for **077**: after 074 and independent of the backend deploy (either order is safe).
It also sets `lock_timeout` 5 s and `statement_timeout` 8 s on `chat_turn_operation` itself.
Database worker pools are bounded (`app/core/db_pools.py`): a full pool answers `503` with
`Retry-After` instead of queueing.

### Nora turn worker and turn events (OPS-006 phase 2)

Off by default. `CHAT_TURNS_VIA_WORKER=true` on the API makes `send` queue a turn instead of
running it; `WORKER_MODE=true` makes a process the worker (the same image). Setup, rollout order
and rollback need per-step authorization: [docs/chat-worker-setup.md](../docs/chat-worker-setup.md).

- **Migration 078** (after 077): `chat_turn_events`, status `queued`, `chat_turns.via_worker` /
  `run_count` / `dispatched_at`, and `chat_turn_worker_operation` (`claim`, `append_event`,
  `requeue`, `prune_events`, `dispatched`, `undispatched`). Tested by
  `tests/integration/test_chat_turn_events_postgres.py` (Docker, hosted-style grants; run it with
  `CHAT_TURN_TEST_POSTGRES_DOCKER=1`).
- **Send:** `services/chat_turn_queue.submit_turn` begins the queued turn in one transaction and
  then creates the Cloud Tasks task (`chat-turn-<turn id>-a<attempt>`). Entry points: the websocket
  `user_message` and `POST /api/v1/chat/turns`; read with
  `GET /api/v1/chat/turns/{id}/events?after_seq=`. The outbox sweep is
  `POST /api/v1/cron/chat-turns/dispatch` (cron token) and one pass at API startup.
- **Worker:** `routers/internal_tasks.py` (`POST /internal/tasks/chat-turn`, mounted only when
  `WORKER_MODE`), `core/task_auth.py` (Cloud Tasks OIDC), `services/chat_turn_worker.py` (claim,
  draft checkpoints, retry mapping), `services/chat_turn_pipeline.execute_turn` (the pipeline shared
  with the in-process path). Response contract: 200 means do not retry; 503 means retry.
- **Viewing:** `services/chat_turn_events.py` reads the event log for sockets and the HTTP read.
- **Logs:** worker and queue lines add `task_id` (the Cloud Tasks name), `retry_count`, `queue`;
  the API forwards its trace id so a turn keeps one `request_id` across both services. Events:
  `chat_turn.dispatched` / `dispatch_failed` / `sweep`, `chat_turn.worker_task` / `worker_done` /
  `worker_noop` / `worker_retry` / `worker_shed`, `chat_turn.queue_claim`, `task_auth.refused`,
  `turn_watch.finished`.

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

Assigned clinicians may explicitly request
`GET /smart/patients/{patient_id}/facts/{fact_id}/medication-reference` under
`/api/v1`. It reuses this cache for the candidate's recorded drug name only, bounds
official links/excerpts, and returns source check/version/update/stale metadata.
The ingredient concept is informational and does not update candidate or canonical
RxNorm values. `GET /api/v1/clinicians/me/external-record-reviews` is a separate
current-assignment/clinic-scoped, paginated source-work summary, not a notification
count. Both endpoints preserve existing clinical decision APIs and permission gates.

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

### Patient-confirmed symptom intake

PAT-002-B replaces automatic symptom-report insertion in Nora with a private draft,
explicit preview and confirmation. Endpoints are under
`/api/v1/patients/me/symptom-intakes`; the actor comes from authentication, not the body.
`GET /active?session_id=default` returns the latest owned draft, including terminal
state for reconnect recovery. There is no staff draft endpoint. Writes require
revision plus stable mutation identity; confirm requires preview hash and explicit
consent. `GET /api/v1/patients/me/symptom-reports/{id}` reads an owned confirmed report.

PAT-002-C history (migration 091, `public.symptom_report_history`, backend role only): patients read
`GET /api/v1/patients/me/symptom-history[/{id}]` (own confirmed reports, newest first, events from
recorded rows only); assigned clinicians read
`GET /api/v1/clinicians/me/patients/{patient_id}/symptom-reports/{id}` and
`POST .../review`, which is idempotent, audited and shared by the care team. Drafts are never
reachable. No new configuration.

`SYMPTOM_INTAKE_ENABLED=false` is the default. Migration 060 does not approve a library.
The approved `candidate-1` is pinned in the manifest; revised `candidate-2` is pending
genuine paired-locale review. Matching immutable database eligibility is required. Unavailability
never restores automatic report insertion. Source binding requires a new backend-saved
Nora user turn with a session ID; old unbound transcript rows remain readable.

Run the [acceptance commands and synthetic journey](../docs/evidence/pat-002-b-acceptance-2026-10-12.md).
No model is needed for question selection or preview. Exact patient-named product
context is limited to 4 medications, 5 approved facts and 2 cited 500-character excerpts.
`POST /{intake_id}/reply` accepts a current question, revision, mutation identity,
locale and typed/voice text. It conservatively parses explicit values after the
safety gate; it cannot consent or confirm. Answers are not ordinary chat messages.
Source suggestions are quotes that require separate patient acceptance.

The exact checksum-pinned `071_confirmed_symptom_handoff.sql` migration keeps
confirmation, audit, the existing `symptom_adr_screen` queue and
active assigned-clinician notices in one transaction. Only an exact unique active
medication name supplies its FK; unlisted products stay unverified testimony. The
existing worker creates an ADR draft for eligible products; retries preserve
clinician review. High severity (the existing >=8 threshold) queues a separate
minimal urgent notice even for cancelled drafts. Emergency alerts remain separate.
Both require `A2A_RETRY_WORKER_ENABLED=true`. Clinician-authored ADR information
requests and patient replies stay in Care Team messages while Nora remains the AI chat.
The applied 071 filename and bytes are immutable and must not be renamed or replayed.
The post-confirmation service reuses the transaction's `confirmed_symptom:{report_id}`
task key, including queued tasks, rather than creating a second screening task.
An existing legacy `symptom_event:{report_id}` task is reused when no canonical
task exists. This compatibility fix changes no migration or clinical review decision.
See [October 17 acceptance](../docs/evidence/pat-002-b-acceptance-2026-10-17.md) and the
[read-only preflight/release procedure](../docs/pat-002-b-rollout.md).

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

## Care plans per care team and the shared clinical core (PLAN-002, CLN-003 G/H)

A care plan belongs to one care-team link (patient, clinician, clinic). Specification,
decisions, lock order, read-path audit and the API contract:
[PLAN-002](../.agent/specs/plan-002-care-plans-per-care-team.md).

- **Migrations 083-087** (unapplied; never apply remote SQL without explicit authorization):
  plan ownership and per-plan versions (083), owned records, routed documents and the shared
  core (084), cross-plan publication (085), notification scoping (086), record owners and care-team work items in the notification centre (087). Each ends with a
  verification block that fails if a grant or RLS setting is wrong.
- **Ownership is enforced in Python** because the backend uses the service role. The rules are
  in `services/care_team_access.py`; every clinician read of documents, facts, plans, SOAP
  notes, reviewed ADR work, MedWatch drafts and FHIR imports goes through them (and
  `clinician_record_gate.py`). A row that does not carry its owner columns is hidden. The same
  rules are in the database for direct sessions (RLS and the storage policy).
- **Publication** is `publish_care_plan_version`: one transaction under the patient-wide lock,
  the only cross-plan comparison in SQL, idempotent per key. Interaction severity is never
  asserted (`interaction_coverage: "not_checked"`, MED-001).
- **Postgres contract tests** (`tests/integration/test_care_team_*_postgres.py`, harness
  `care_team_plan_harness.py`, env `CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER=1`, CI shard
  `care-team-plans`) build template databases from the real ledger; run them with
  `-o timeout=1200` locally if Docker is busy.
- **Unit helpers**: `tests/unit/services/care_team_fake_db.py` is an in-memory client that
  applies filters as sent, so a forgotten owner filter fails a test.

## AI availability counters (AI-003)

`GET /api/v1/ops/ai-availability?hours=24` (clinic admins) returns per workload and model attempt
counts by outcome (success, timeout, 429, 5xx, circuit open, fallback) and p50/p95/p99 latency over
a rolling window, from `ai_availability_buckets` (migration 090). Counters hold no patient data or
text. Settings: `AI_AVAILABILITY_ENABLED`, `AI_AVAILABILITY_FLUSH_SECONDS`. See the AI runtime
decision record.

## Reviewed care-handoff summaries (CON-001)

A clinician drafts, edits, approves and exports a handoff summary for one of their
patients. Routes live under `/api/v1/care-team/clinician/patients/{patient_id}/handoff-summaries`
(`routers/handoff_summaries.py`); `HandoffSummaryBuilder` assembles the sections
deterministically (no model) from records the author may see and reuses the #208 timeline;
`HandoffSummaryService` owns create/save/approve/export; `handoff_fhir_export.py` renders the
approved version as a FHIR R4B document Bundle with Provenance. Storage is migration 089
(append-only versions and audit events, `SECURITY DEFINER` functions for `service_role`
only, optimistic versions, row locks). Only the approved current version exports, and every
export is an audit event. Contract and decisions:
[`.agent/specs/con-001-care-handoff-summary.md`](../.agent/specs/con-001-care-handoff-summary.md).
Tests: `tests/unit/services/test_handoff_summary.py`,
`tests/integration/routers/test_handoff_summaries_api.py`, and the opt-in Postgres contract
`tests/integration/test_care_handoff_summaries_postgres.py` (CI shard `care-handoff`).
