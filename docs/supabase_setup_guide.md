# Supabase Recreation and Verification Guide

Use this guide to recreate the project after an inactive instance is removed. It is environment-neutral: do not copy credentials, project references, or synthetic seed data between environments.

## Create the project

1. Create a new development project in the required region and record its URL, anon key, service-role key, and JWT secret in the team secret store.
2. Copy `.env.example` to `.env` locally. Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_JWT_SECRET`; never commit that file.
3. Configure clinician and patient portal environment variables with the new public URL and anon key.
   Leave `NEXT_PUBLIC_ENABLE_DASHBOARD_REALTIME=false` until the Realtime publication,
   RLS behavior, and clinician JWT path have been verified end to end. The clinician
   dashboard remains functional through its authenticated backend API while it is disabled.
4. Enable email authentication and MFA for clinician accounts. After migrations complete, configure **Authentication → Auth Hooks → Customize Access Token (JWT) Claims hook** to use `public.custom_access_token_hook` and confirm it shows as enabled. This Auth control-plane setting is not recorded by a SQL migration.

## Apply migrations

Apply every SQL file through the repository migration ledger against an empty development database. The ledger records the complete filename and SHA-256 checksum, so a rerun skips unchanged files and stops if an applied migration was edited. Do not run a reset, seed, or migration command against a production database.

```bash
# In Dashboard → Connect, copy the Session pooler URI (port 5432) to the
# local secret store, then set MEDIAGENT_DB_URL from that value without
# echoing, committing, or reconstructing the password-bearing URI.
./scripts/apply-supabase-migrations.sh
./scripts/verify-supabase-schema.sh
```

Copy the URI rather than assembling it: the pooler tenant, host, and password encoding are project-specific. The Session Pooler supports IPv4 clients and is required here because the migration command maintains a session while applying each SQL file.

This integrated checkout contains 56 SQL migration files through prefix `047`.
The newer main files include care-plan publication review guards (`042`), incomplete
drafts (`043`), overlap publication guards (`044`), activity continuity (`045`), and
an independent auditable ADR assessment migration (`042`) and atomic clinician ADR
review actions (`046`). The patient-confirmed ADR information and deterministic
reassessment loop is migration `047`. Scheduling adds appointment
lifecycle/group/audit migrations `038`–`041`, expired status `042`, and booking/expiry
guards `043`. These coexist with the document/care-plan migrations sharing those
prefixes, just as the two `011` files coexist. The ledger identifies migrations by
full filename and checksum; preserve applied names and bytes. A local file count
does not establish remote application or authorize applying unrelated migrations.

### Appointment Slice 5 rollout

Before authorizing remote application, review this read-only preflight in the
synthetic development database:

```bash
psql "$MEDIAGENT_DB_URL" -v ON_ERROR_STOP=1 -f backend/scripts/appointment-booking-preflight.sql
```

It must return zero overlap pairs. Resolve existing bookings through a separately
reviewed workflow; migration 043 will stop rather than automatically cancel/delete
them. The exclusion constraint scans and locks the appointments table during setup.
The migration requires `btree_gist`; it creates the extension in `extensions` if absent.

Apply `042_appointment_expired_status.sql` and commit before applying
`043_appointment_booking_guards.sql`. Use the existing ledger command from the
scheduling integration checkout so each full filename/checksum is recorded and
each migration is transactional. Apply schema before starting the updated backend.
Existing proposed rows receive a deadline from their original creation time, so
old offers may appear expired on their first authorized read. Booked visits do not
expire. The client refreshes at pending deadlines; no new background Job is required.

Verify the valid `appointments_patient_no_overlap` exclusion constraint,
`proposal_expires_at`, and service-role-only `expire_appointment_proposals` and
`respond_to_appointment_offer` functions. Run the synthetic conflict and expiry
journey in [the scheduling design](../.agent/specs/sch-001-appointment-scheduling.md#14-slice-5--booking-conflicts-and-proposal-expiry).
On 2026-10-03, the requester authorized the migration-only rollout against the
selected synthetic Supabase project. Preflight returned zero overlap pairs; both
042/043 scheduling migrations committed through the ledger script. All 52 remote
ledger checksums matched their sources: 48 files in this checkout and four newer
independent care-plan migrations checked against `origin/main` at `019598b`.
The read-only Slice 5 verifier passed. Backend/portal activation and authenticated
live acceptance remain pending; no server restart or seed/reset accompanied this
operation. Do not compare this remote ledger to an older checkout's file count.

The read-only structural verification script checks the expiry enum/column, valid
overlap constraint, enabled booking/expiry/append-only triggers, RLS, and RPC grants:

```bash
psql "$MEDIAGENT_DB_URL" -v ON_ERROR_STOP=1 -f backend/scripts/verify-appointment-slice5.sql
```

It must print `Slice 5 schema and function permissions verified`. It does not mutate
or expire appointments and does not replace the ledger checksum comparison or live
patient/clinician acceptance steps.

After authorized migration application, stop the existing local backend and start
the integration code using the original virtual environment and configuration:

```bash
MEDIAGENT_ROOT=/path/to/medi-agent
cd "$MEDIAGENT_ROOT" # use "$MEDIAGENT_ROOT/backend" if the existing .env is there
PYTHONPATH="$MEDIAGENT_ROOT/.worktrees/clinician-scheduling/backend/src" \
  "$MEDIAGENT_ROOT/backend/.venv/bin/uvicorn" app.main:app --reload \
  --reload-dir "$MEDIAGENT_ROOT/.worktrees/clinician-scheduling/backend/src" \
  --host 127.0.0.1 --port 8000
```

The working directory lets settings load the existing `.env`; do not copy or edit it.
The original restart script points to the original checkout and will not activate
the integration code. Both updated portal servers use the existing configuration.

## Configure SMART staging

Cloud Run staging must expose a stable HTTPS backend URL. Set these server-side values there:

```bash
SMART_CLIENT_ID=<registered SMART sandbox client id>
SMART_CLIENT_SECRET=<only if the sandbox registration requires one>
SMART_REDIRECT_URI=https://YOUR_BACKEND/api/v1/smart/callback
SMART_STATE_ENCRYPTION_KEY=<a Fernet-compatible key generated in the secret store>
SMART_ALLOWED_ISSUERS=https://launch.smarthealthit.org/v/r4/fhir
SMART_STANDALONE_ISSUER=https://launch.smarthealthit.org/v/r4/sim/eyJsYXVuY2hfdHlwZSI6InBhdGllbnQtc3RhbmRhbG9uZSJ9/fhir
# The backend adds `launch` for EHR launch or `launch/patient launch/encounter`
# for standalone launch. Keep this value to least-privilege resource reads.
SMART_SCOPES="patient/Patient.read patient/Encounter.read patient/Condition.read patient/AllergyIntolerance.read patient/MedicationRequest.read patient/MedicationStatement.read patient/Observation.read patient/DiagnosticReport.read patient/Procedure.read patient/CarePlan.read patient/DocumentReference.read"
```

Register the exact `SMART_REDIRECT_URI` with the sandbox. For an EHR launch, separately
register the clinician portal's launch route (for example,
`https://clinician.mediagent.live/smart-import`) as the app launch URL. The portal receives
the EHR's `iss` and opaque `launch` handle, then requires local clinician sign-in and local
care-team/patient selection before the backend begins authorization. Tokens and authorization
codes remain server-side; the browser receives only a short-lived, single-use review handoff.

The SMART Health IT launcher has two distinct sandbox bases. EHR-initiated testing uses
`https://launch.smarthealthit.org/v/r4/fhir`; direct portal testing uses the configured
simulator issuer above. Do not replace the EHR issuer with the simulator issuer: the
simulator base is what enables its standalone synthetic-patient picker.

## Reconciliation and legacy-data review

Migration `029` keeps imported SMART and document data as candidates until a clinician
selects permitted medication, condition, or allergy fields in the reconciliation
workspace. Before any staging cleanup, produce and review the read-only legacy inventory:

```bash
./scripts/inventory-legacy-document-derived-records.sh
```

The script only reports rows created by the old document-derived canonical path. It never
deletes or rewrites records. A separately reviewed, explicitly authorized staging repair
is required before attaching those rows to legacy provenance or changing their status.

Migration `034_document_ingestion_safety.sql` adds `needs_ocr` and
`needs_evidence_review` document states. Its `claim_document_ingestion` RPC is
service-role-only: it locks one document, creates one ingestion run, and caps the
initial attempt plus clinician-requested retries at three total attempts. Do not expose
this RPC to browser roles. Provider diagnostics remain on the service-role run record;
clinician responses expose only stable failure codes and retry state.

Migration `035_model_invocation_telemetry.sql` records operational model metadata only;
it stores no patient identifier, prompt, or model response. Migration
`036_document_ingestion_worker.sql` adds the service-role-only batch claim RPC and the
care-team-authorized retry RPC used by the Cloud Run Job. The migration ledger, not an
individual SQL file, records applied filenames and checksums.

## Verification checklist

### Care-plan read-policy repair (047)

`047_care_plan_private_rls_helpers.sql` repairs policies introduced after migration
020's helper hardening. Apply it through the existing filename/checksum migration
ledger only after explicit environment authorization; do not edit or rerun 020/040.
The private helpers from 020 and tables/policies from 040 are prerequisites. No reset,
seed, account change or new helper RPC is required.

Policies are restricted to `authenticated`; clinician SELECT uses the existing private
helpers. RLS-filtered SELECT is granted, browser writes/anonymous access are revoked.
Patient reads still include only their approved/superseded plans and published
nonremoved items; generation requests/audit are assigned-clinician-only. Service-role
API authorization and publication guards remain mandatory because that role bypasses RLS.

Local tests run real 020 helpers, 040 policies and 047 with publication/continuity guards:

```bash
cd backend
CARE_PLAN_TEST_POSTGRES=1 PYTHONPATH=src .venv/bin/pytest tests/integration/test_care_plan_postgres.py --no-cov -q
```

Use normal test settings and local PostgreSQL, never a remote connection string.
After authorized rollout, verify ledger checksum, owner vs assigned/unassigned clinician
reads, and browser write/publication-RPC denial. Local tests do not prove remote application.

- [ ] Every committed migration is recorded with its exact filename and SHA-256 checksum in `public.schema_migrations`.
- [ ] Tables include `clinical_facts`, `source_provenances`, `fhir_imports`, `fhir_import_resources`, `external_patient_bindings`, `document_ingestion_runs`, and reconciliation-event tables.
- [ ] RLS is enabled for clinical facts and FHIR import tables.
- [ ] `public.custom_access_token_hook` is enabled in **Authentication → Auth Hooks**, not merely present in the database.
- [ ] A fresh password sign-in for a synthetic patient produces a JWT with `user_role=patient`, and the backend accepts that JWT. Repeat for a clinician before a clinician demo.
- [ ] Authentication → URL Configuration uses the intended portal site URL and includes the approved patient and clinician redirect URLs required for password-reset or email-link flows.
- [ ] A clinician has an active care-team assignment to a synthetic patient.
- [ ] Cloud Run staging callback is HTTPS and registered with the SMART sandbox.
- [ ] A sandbox import creates raw resource envelopes and pending facts only.
- [ ] A clinician can inspect lineage, confirm an external-patient binding, and reconcile selected medication, condition, or allergy fields without altering demographics.
- [ ] A synthetic text PDF produces only page-cited pending candidates; a scanned/image upload reaches `needs_ocr` without a model call or candidate.
- [ ] An assigned clinician can retry a retryable failed document, while a concurrent retry and a fourth total attempt are denied.

Use synthetic or deidentified sandbox records only. This project does not accept real patient data for this demo.
