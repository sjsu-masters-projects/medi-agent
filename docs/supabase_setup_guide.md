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

## Account email delivery (EMAIL-001)

See [the email contract](../.agent/specs/email-001-email-flows.md) before changing
Auth settings. Initial dashboard inspection on October 11 found Confirm email
**off** and custom SMTP **off** in the synthetic staging project. After operator
setup, a dashboard reload confirmed SMTP **on**, Resend host/port and a stored
hidden password. This verifies saved configuration, not delivery. With explicit
requester approval, Site URL was set to `https://app.mediagent.live` and the three
exact deployed reset destinations listed below were added. Reload confirmed they
persisted. No wildcard redirects or signup-confirmation changes were made.
Existing signup expects an
immediate session; do not enable confirmation until the pending-verification flow
is implemented and reviewed. SMTP delivery can be configured independently.

For the verified `mail.mediagent.live` domain, the proposed Auth identity is
`MediAgent Account Access <accounts@mail.mediagent.live>`. In Authentication →
Emails → SMTP Settings, use Resend's documented host `smtp.resend.com`, port `465`,
username `resend`; the operator enters a Resend API key as the SMTP password.
Never paste that key into a chat, source file or command. An exposed key must be
revoked and replaced, including any deployment that used it. Keep click tracking
off for recovery links. SMTP configuration does not require a schema migration.

The backend recovery API accepts `portal: patient|clinician` and `locale:
en-US|es-MX`, building the destination from `PATIENT_PORTAL_URL` or
`CLINICIAN_PORTAL_URL`. It never accepts an arbitrary return URL. Authorize these
exact deployed redirects in Authentication → URL Configuration:

- `https://app.mediagent.live/reset-password?lang=en-US`
- `https://app.mediagent.live/reset-password?lang=es-MX`
- `https://clinician.mediagent.live/reset-password?lang=en-US`

Add exact localhost/preview redirects only for an explicitly selected test target;
do not use broad wildcard redirects. Both portals already document the public
`NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` in their examples.
Recovery uses these public values, never a service-role key. The recovery session
stays in memory, its URL fragment is removed, and successful reset returns to
normal login (including clinician clinic/MFA checks). The operator must enter the
new password during live verification. Neutral API success does not prove delivery.

References: [Resend SMTP](https://resend.com/docs/send-with-supabase-smtp),
[Supabase password recovery](https://supabase.com/docs/guides/auth/passwords).

Application email uses separate verified opt-in contacts and server-only outbox
records from `057_email_delivery.sql` and `058_email_delivery_fixes.sql` (both applied
to the synthetic project). No email function reads the `auth` schema: a hosted migration
cannot grant `service_role` access there, so the backend reads account addresses through
the Auth Admin API with the service-role key. The notification and onboarding sender
identities are documented in `.env.example`; they are not Supabase SMTP configuration.
With no configured notification sender, verification is unavailable rather than sent
from a default testing identity.

The Reset password template is `docs/email-templates/supabase-password-recovery.html`,
installed October 12. Reinstall it in Authentication → Emails → Reset password after
every change to that file, with separate authorization; never enable confirmation as a
side effect of applying SQL. Its link opens the portal reset page, so both portals'
`NEXT_PUBLIC_SUPABASE_ANON_KEY` must be the project's exact public key: `/verify` does not
check the key, but saving the new password does. Periodic email delivery runs after each
reminder run. Configuration and production status:
[EMAIL-001](../.agent/specs/email-001-email-flows.md#operations-and-configuration).

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

The checkout contains 76 SQL migration files, prefixes `001`–`064`. Some prefixes are
shared by independent files (`011`, `038`–`043`, `047`, `048`, `051`) that came from parallel
branches; they coexist because the ledger identifies migrations by full filename and
checksum, not by prefix. Preserve applied names and bytes. The ledger in
`public.schema_migrations` is authoritative: a local file count does not establish remote
application or authorize applying unrelated migrations.

Migration `047_adr_patient_information_loop.sql` adds the patient-confirmed ADR information
request, deterministic reassessment, notification closure, and patient-actor audit transaction.
It does not create a MedWatch draft or external submission.

Migration `048_medwatch_draft_lifecycle.sql` adds the assigned-clinician
draft/edit/approval/export lifecycle with immutable audit events and optimistic revision control.
It deliberately does not add an FDA submission operation.

### ADR loop and Form 3500 (063/064, PV-001-C) — written, not applied

`063_adr_information_loop_lifecycle.sql` makes each ADR information request its own
notification source, adds the clinician "patient answered" alert and cascades ADR audit on
patient deletion. `064_medwatch_form_3500.sql` requires 063 and adds Form FDA 3500 drafts: the
discard columns and a partial unique index (one non-discarded draft per assessment), the
non-identifying `patient_reference`, the append-only `medwatch_external_submissions` table
(SELECT only for `authenticated` and `service_role`; no role may insert, update, delete or
truncate it directly), the `medwatch_drafts_submission_guard` trigger (`submitted` only after
approval and a submission record; submitted and discarded drafts frozen), the extended audit
types, and service-role-only RPCs: `create_medwatch_draft(uuid, uuid, jsonb, jsonb, text,
uuid)`, `approve_medwatch_draft(uuid, uuid, text, integer, jsonb)`,
`record_medwatch_draft_export(uuid, uuid, text, text, text)` (the 048 2-argument export
delegates with `'json'`), `discard_medwatch_draft`, `record_medwatch_external_submission` and
`amend_medwatch_external_submission`. It ends with a fail-closed verification block. No
function or table sends anything to FDA.

Neither file is applied to any hosted project. Applying either needs the requester's explicit
authorization naming that action. **Order:** apply 063, then 064, before the backend from
`fix/adr-information-loop-gaps` deploys (the branch ships as one pull request and its backend
calls 064 objects; merging deploys the backend, so apply first and merge after). Every 048
function keeps its signature, so the currently deployed backend keeps working once 064 is
applied. Rows written by that backend in the meantime are labelled `fda-3500-legacy-048` and
are upgraded on read. After applying, verify with the ledger and with the read-only checks the
fail-closed block already performs (it raises and rolls the migration back on any gap).

### Appointment booking guards (042/043)

Appointment Slice 5 is applied to the synthetic project. For a new environment, run the
read-only preflight (`backend/scripts/appointment-booking-preflight.sql`, must return zero
overlap pairs), apply `042_appointment_expired_status.sql` before
`043_appointment_booking_guards.sql`, then run the read-only verifier
`backend/scripts/verify-appointment-slice5.sql`, which must print
`Slice 5 schema and function permissions verified`. Rollout order and the synthetic
conflict/expiry journey are in
[the scheduling design §14](../.agent/specs/sch-001-appointment-scheduling.md#14-slice-5--booking-conflicts-and-proposal-expiry).

## Configure SMART staging

Cloud Run staging must expose a stable HTTPS backend URL. Set these server-side values there:

```bash
SMART_CLIENT_ID=<registered SMART sandbox client id>
SMART_CLIENT_SECRET=<only if the sandbox registration requires one>
SMART_REDIRECT_URI=https://YOUR_BACKEND/api/v1/smart/callback
SMART_STATE_ENCRYPTION_KEY=<a Fernet-compatible key generated in the secret store>
SMART_ALLOWED_ISSUERS=https://launch.smarthealthit.org/v/r4/fhir
SMART_STANDALONE_ISSUER=https://launch.smarthealthit.org/v/r4/sim/WzMsIiIsIiIsIkFVVE8iLDAsMCwwLCIiLCIiLCIiLCIiLCIiLCIiLCIiLDAsMSwiIl0/fhir
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
simulator base is what enables its standalone synthetic-patient picker. The `sim` segment
must be a launcher launch-options array; the value above decodes to
`[3,"","","AUTO",0,0,0,"","","","","","","",0,1,""]` (patient standalone). A JSON object
such as `{"launch_type":"patient-standalone"}` is read as a legacy code and silently runs
the provider EHR flow instead, and a standalone launch against the plain EHR base fails
with `Invalid launch options`. The portal does not hard-code this issuer; it omits the
issuer for standalone launch and the backend uses `SMART_STANDALONE_ISSUER`.

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

## Verification checklist

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
- [ ] A synthetic text PDF produces only page-cited pending candidates; a scanned/image upload is OCR'd (Tesseract, `eng`/`spa`) and reaches `needs_ocr` without a model call or candidate only when no usable page text is recovered.
- [ ] An assigned clinician can retry a retryable failed document, while a concurrent retry and a fourth total attempt are denied.

Use synthetic or deidentified sandbox records only. This project does not accept real patient data for this demo.
