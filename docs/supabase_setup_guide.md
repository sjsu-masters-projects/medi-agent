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

`102_document_explanation_presentations.sql` adds the service-only validated
presentation cache for REC-001-UX. It retains one current entry per document/locale,
with a source fingerprint and format version, and cascades on document removal.
It changes no source summary, review or clinical truth. Apply it before the matching
backend release only after explicit authorization for that hosted target. It is
locally tested, not hosted-applied here; missing schema makes structured explanations
unavailable without falling back to an AI call on every view.

`101_patient_document_removal.sql` is required by REC-001-RM's restricted patient
removal route. It adds a minimal removal audit and service-role-only status/removal
functions using the existing evidence fence; no source backfill. Apply it before
the matching backend/portal release, only after explicit target authorization.
Without it the route fails closed and the portal offers the private care-team
request path. Local checks and rollout state belong to the
[record clarity contract](../.agent/specs/rec-001-patient-record-clarity.md#patient-removal-and-reading-refinement).

Apply every SQL file through the repository migration ledger against an empty development database. The ledger records the complete filename and SHA-256 checksum, so a rerun skips unchanged files and stops if an applied migration was edited. Do not run a reset, seed, or migration command against a production database.

```bash
# In Dashboard → Connect, copy the Session pooler URI (port 5432) to the
# local secret store, then set MEDIAGENT_DB_URL from that value without
# echoing, committing, or reconstructing the password-bearing URI.
./scripts/apply-supabase-migrations.sh
./scripts/verify-supabase-schema.sh
```

Copy the URI rather than assembling it: the pooler tenant, host, and password encoding are project-specific. The Session Pooler supports IPv4 clients and is required here because the migration command maintains a session while applying each SQL file.

Migration filenames use an ordered `NNN_descriptive_name.sql` convention. Historical
parallel branches produced a small set of already-applied shared prefixes (`011`,
`038`–`043`, `047`, `048`, `051`, and `067`); they coexist because the ledger identifies
migrations by complete filename and checksum. The migration validator preserves those
known historical sequences plus the exact applied 059, 060 and 071 pairs. Those exact
exceptions cover the confirmed-symptom files alongside the independently applied critical-result
and clinician-visit migrations; the validator rejects any other new shared prefix. Preserve
applied names and bytes. The ledger in
`public.schema_migrations` is authoritative: a local file count does not establish remote
application or authorize applying unrelated migrations. Migrations through
`075_notification_zone_lookup.sql` are recorded as applied by the requester (October 18,
2026). A read-only October 19 check also recorded the exact 071 symptom handoff and
`076_care_conversation_activity_review.sql`; application of 077/078 was not checked.
Browser session limits (AUTH-002) are portal
environment variables, not Supabase settings; no Auth configuration change is required.

Migration `047_adr_patient_information_loop.sql` adds the patient-confirmed ADR information
request, deterministic reassessment, notification closure, and patient-actor audit transaction.
It does not create a MedWatch draft or external submission.

Migration `048_medwatch_draft_lifecycle.sql` adds the assigned-clinician
draft/edit/approval/export lifecycle with immutable audit events and optimistic revision control.
It deliberately does not add an FDA submission operation.

### ADR loop and Form 3500 (063/064, PV-001-C) — applied October 13

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

Both files were applied to the hosted project by the requester on October 13, before the backend
that calls 064 objects deployed. Applying a migration needs the requester's explicit
authorization naming that action. **Order for a fresh environment:** 063, then 064, before that backend. Every 048
function keeps its signature, so the currently deployed backend keeps working once 064 is
applied. Rows written by that backend in the meantime are labelled `fda-3500-legacy-048` and
are upgraded on read. After applying, verify with the ledger and with the read-only checks the
fail-closed block already performs (it raises and rolls the migration back on any gap).

### Confirmed symptom ADR handoff (071, PAT-002-B) — recorded applied October 18

`071_confirmed_symptom_handoff.sql` requires the already-applied confirmed-intake
migration 060 and migration 065 clinic memberships. It normalizes exact active-medication
name matching, queues one report-keyed `retrying` ADR screen in the same confirmation
transaction and sends minimal notices to active assigned clinic members. An unlisted
patient-named product remains testimony and never receives a fabricated medication link.
The trigger does not assign causality or create an FDA submission.
`A2A_RETRY_WORKER_ENABLED=true` is required so interrupted work is recovered.

The exact file has SHA-256
`f690b788d5f29c3d7583f2fe8cc43b7a51a6af817c276d6839cc9c9ab2ded36b`. A read-only
October 19 ledger check recorded that identity as applied on October 18. Preserve the
filename and bytes: do not rename or replay it because it shares prefix 071 with
`071_clinician_visit_management.sql`. Only a fresh or explicitly verified missing
environment may apply the exact file, and applying it still requires explicit authorization.
Backend deployment and runtime feature activation remain separate gates.

### Clinic memberships (065, CLN-003 slice A) — applied October 16

`065_clinic_memberships.sql` adds `clinic_memberships` (one row per clinician and clinic,
with that clinic's role and an `active`/`inactive` status), backfilled from
`clinicians.clinic_id` and `clinicians.role`; clinicians without a clinic get no membership
and are counted in a `NOTICE`. It adds `care_teams.clinic_id`, backfilled from the link's
clinician, and replaces `UNIQUE (patient_id, clinician_id)` with
`UNIQUE (patient_id, clinician_id, clinic_id)` (a partial unique index keeps one link per pair
for clinicians without a clinic). Triggers mirror `clinicians.clinic_id`/`role` into
memberships during the compatibility period and give a new care-team row its clinician's clinic
when none is sent. RLS: a clinician reads only their own memberships; only `service_role`
writes them; nobody deletes them. It also revokes INSERT, UPDATE and DELETE on `clinicians`
from `anon` and `authenticated` (SELECT unchanged), so a signed-in clinician cannot change
their own role or clinic through the Data API. `private.is_clinic_member(uuid)` is added for later slices
and used by no policy; `is_assigned_clinician` and every existing policy are unchanged. It
ends with a fail-closed verification block.

Applied by the requester on October 16 before #176 merged (its invite-code paths read
`clinic_memberships` and write `care_teams.clinic_id`, so apply first, merge after). Applying
needs the requester's explicit authorization naming that action. After applying, confirm the
ledger row and read the `NOTICE` count of clinicians without a clinic.

### Sign in once (066, CLN-003 slice B) — applied October 16

`066_clinic_sign_in_once.sql` requires 065. It adds the append-only
`clinic_membership_audit_events` table (RLS on, no foreign keys, identifiers only; `service_role`
has SELECT and INSERT, nobody has UPDATE, DELETE or TRUNCATE, and triggers refuse them even for
the owner), `public.clinician_clinic_operation` (list memberships, join by open clinic code,
change a member's role, remove a member; callable by `service_role` only), membership-aware
`clinician_email_invitation_operation` (an address that belongs to another clinic can be invited;
admin rights are read from the membership at the invitation's clinic), and care-conversation and
notification checks that use the care-team link's clinic. `clinicians.clinic_id` stays the
clinician's default clinic for legacy readers. It ends with a fail-closed verification block.

Applied by the requester on October 16 before #178 merged, because the new routes call
`clinician_clinic_operation` (apply first, merge after). Every replaced function keeps its
signature. After applying, confirm the ledger row.

**Supabase Auth dashboard changes: none.** Sign-in, MFA and email settings are unchanged; the
service-role backend performs the membership operations.

### Clinic lists, scheduling and message translations (067–069) — applied October 17

Applied by the requester on October 17: `067_clinic_lists_and_roles.sql` (CLN-003 slices C and D),
`067_english_display_facts.sql` and `068_message_translations.sql` (LOC-003), and
`069_clinic_scheduling_and_tags.sql` (CLN-003 slices E and F). 068 is re-runnable, has RLS and is
backend-only (fixed in [#183](https://github.com/sjsu-masters-projects/medi-agent/pull/183)). 069 adds the
clinician overlap exclusion constraint and restores the intended grants on
`authorization_denial_events`; its backfill fails closed on an unmatched link or existing overlaps,
so run `backend/scripts/appointment-clinician-overlap-preflight.sql` (read-only) first. It tagged 38
appointments in the hosted project. A read-only audit on October 17 found no public table with RLS
off and no browser-role SELECT or INSERT on a public table.

### Message-translation integrity, wording verification and display provenance (080–082 and 088)

October 22 operator receipt: the requester supplied successful `COMMIT` and ledger inserts
for 080, 081, 082 and 088, followed by `Migration ledger is synchronized`. Care-team
083–087 were already applied and skipped. This records the supplied output, not an
independent hosted checksum/security audit. #203 merged as `dace6a8d` afterward.
For a new environment, apply in ledger order after 079 (including care-team 083–087
before 088), before deploying the backend that requires these contracts:

1. `080_message_translation_integrity.sql` — `AFTER DELETE` triggers on
   `care_conversation_messages` and `chat_messages` that remove a deleted message's stored
   translations (the cascade a polymorphic `source_table` cannot express as one foreign key),
   plus `public.purge_message_translations(interval)`, which removes orphans and expired
   failure markers. The function is `service_role`-only; the migration's verification block
   fails closed if either trigger is missing or a browser role can execute it.
2. `081_care_plan_wording_verification.sql` — `care_plan_items.back_translation` (the cached
   back-translation a clinician verifies against) and `care_plan_items.wording_verification`
   (the deterministic guard outcome recorded with `wording_verified`), plus a trigger
   requiring new or changed verified wording to carry its record. Legacy approved wording
   is not rewritten; cache-only updates remain possible without inventing verification. It also
   adds `care_plan_items.translation_model_id`, the model that drafted the second language.
3. `082_loc003_display_provenance.sql` — `clinical_facts.display_model_id` (the model that
   produced a fact's English display fields), and widens the `message_translations`
   `source_table` check to accept `evidence_excerpt`, so an English gloss of Spanish source
   evidence is stored in the table that already holds translations with their guard outcome
   and model, rather than in a second table with the same columns. Excerpt glosses are keyed
   by a UUIDv5 of the excerpt text, so 080's orphan sweep leaves them alone (it only looks
   under the two message labels). The migration finds 068's inline constraint by definition
   rather than assuming its generated name, and fails closed if either change is missing.

4. `088_confirmed_message_translation.sql` — backend-only atomic confirmed send: the
   existing clinic-authorized send and exact clinician-confirmed translation commit together.
   Duplicate retries cannot replace the approved text; translation failure or a changed patient
   locale rolls the send back. Original-only clinician sends atomically store a permanent
   non-display marker, so a later patient read cannot regenerate a rejected translation.
   The marker is kept until source deletion, not expired as a transient model failure.
   Browser roles cannot execute this function.

All four are re-runnable and add no table. New functions have explicit least-privilege grants
and final permission checks. 080 deletes only orphaned/expired translation display state,
never original messages. Applying hosted SQL requires separate explicit authorization.

The retention rule is a recorded cron job, `POST /api/v1/cron/message-translations/purge`
(internal, `CRON_AUTH_TOKEN`), intended for Cloud Scheduler about once a day. It is safe to
repeat and reports `orphans_removed` and `expired_failure_markers_removed`.

Verify with the contract suite before applying anywhere:

```bash
cd backend
LOC003_TEST_POSTGRES=1 PYTHONPATH=src pytest tests/integration/test_loc003_translation_postgres.py
```

It builds a disposable cluster and runs the real migration bytes (30 cases). On macOS with
PostgreSQL 18 the fixture pins `LC_ALL=C` and creates the `postgres` superuser itself, so no
local cluster configuration is needed. CI runs the same file in the PostgreSQL contract
matrix as `loc003-translation-schema`.

### Hosted default grants

New public tables and functions created through SQL receive platform default grants to `anon`,
`authenticated` and `service_role` on the hosted project, and a local or Docker PostgreSQL does not
reproduce that. Every migration that adds a table or function must therefore `ENABLE ROW LEVEL
SECURITY` and explicitly `REVOKE` what the object must not expose (`REVOKE ALL ... FROM PUBLIC, anon,
authenticated`, then grant only what is needed), and end with a fail-closed verification block that
checks `relrowsecurity` and `has_table_privilege` / `has_function_privilege` for the three roles.
Migration 033 created `authorization_denial_events` without revoking the defaults, so the
browser-role grants remained in production until 069 restored the intended ones.

### Renamed migration files

The migration ledger keys on the filename. A renumbered or renamed file is a new file to the ledger
and is applied again, so every migration must be idempotent (`IF NOT EXISTS`, `CREATE OR REPLACE`,
guarded constraint and policy creation). Example: LOC-003's migrations were first applied as
`065_english_display_facts` and `066_message_translations`, then renumbered to `067_english_display_facts`
and `068_message_translations`; the renumbered files reapplied cleanly because they are re-runnable.
Keep the applied `067_english_display_facts.sql` unchanged. PR #203's proposed 079/083
English-display copies were byte-identical and redundant, so they were removed rather than
creating another ledger identity. The validator permits only the exact historical 067 pair
with `067_clinic_lists_and_roles.sql`; any new 067 filename collision fails validation.
Main's 079 remains the applied unlisted-product migration. #203 reserves 080–082 and 088;
merged care-team PR #210 owns 083–087, not applied by this work.
Never edit an applied migration; renumber only a file that has not merged, and test it twice.

### Appointment booking guards (042/043)

Appointment Slice 5 is applied to the synthetic project. For a new environment, run the
read-only preflight (`backend/scripts/appointment-booking-preflight.sql`, must return zero
overlap pairs), apply `042_appointment_expired_status.sql` before
`043_appointment_booking_guards.sql`, then run the read-only verifier
`backend/scripts/verify-appointment-slice5.sql`, which must print
`Slice 5 schema and function permissions verified`. Rollout order and the synthetic
conflict/expiry journey are in
[the scheduling design §14](../.agent/specs/sch-001-appointment-scheduling.md#14-slice-5--booking-conflicts-and-proposal-expiry).

## PAT-002-B local safety checkpoint

B2 adds local migration `059_chat_safety_alerts.sql` (SHA-256
`9ce875b7d1fca79f687f83e6ea02d7b4b56273d5aba064c665591dc8a2ac56f5`).
It creates server-only safety evidence and the narrowly granted service RPCs
`record_chat_safety_turn` and `deliver_chat_safety_alerts`. Ordinary initial
emergency chat rows retain existing transcript visibility; this is not private
draft storage. Safety evidence and its source rows are immutable; pending alert
delivery uses current active care-team assignments and existing operational alerts.
No-recipient dispatch records that outcome without claiming a recipient was notified.

After separate authorization, the target must have the preceding schema and
private schema, migration 059 must precede this backend version, and
`A2A_RETRY_WORKER_ENABLED=true` is required for background redelivery. A backend
without 059 still shows direction but cannot guarantee saved evidence/delivery;
that mismatch is not accepted rollout. Pending delivery notices are not pushed
again when the worker later succeeds. Verify service-only RPC execution, browser
denial, assignment changes, rollback/retry and operational alert deduplication
on the authorized target. Disposable local SQL checks cover selected migrations
and platform stubs, not that target's complete Supabase setup or grants. See
[B2 evidence and reproduction commands](evidence/pat-002-b-acceptance-2026-10-10.md#b2-verification).

Private drafts, explicit report confirmation and revoked browser report writes
remain later work. Migration 027's service-role SELECT grant does not remove the
old owner INSERT policy. No remote migration, seed/reset, deployment, review or
PR #136 migration is authorized or claimed by this checkpoint.

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

## Session settings

The portals enforce their own sign-in limits in the browser (AUTH-002). They do not depend on any Supabase dashboard setting.

| Portal | Idle limit | Absolute limit | Warning |
| --- | --- | --- | --- |
| Clinician | 2 hours | 12 hours from sign-in | Modal 2 minutes before the idle limit, with a countdown and "Stay signed in" |
| Patient | 30 days | 90 days from sign-in | None; signed out silently with a login-page notice |

Activity in any tab counts (a shared `lastActivityAt`, written at most every 30 seconds). Defaults live in `packages/shared/src/utils/session-limits.ts`; optional overrides are `NEXT_PUBLIC_CLINICIAN_SESSION_IDLE_MINUTES`, `NEXT_PUBLIC_CLINICIAN_SESSION_MAX_HOURS`, `NEXT_PUBLIC_CLINICIAN_SESSION_WARNING_SECONDS`, `NEXT_PUBLIC_PATIENT_SESSION_IDLE_MINUTES` and `NEXT_PUBLIC_PATIENT_SESSION_MAX_HOURS`. No override is needed.

These limits are client-side. A user who bypasses the app can keep using a valid token until it expires and its refresh token stops working, so treat them as a usability and shared-device control, not a hard server guarantee.

Recommended Supabase values under **Authentication**, as an optional server-side backstop:

- JWT expiry: 3600 seconds (the current project value).
- Refresh token rotation: on, with reuse detection on (the current project state).
- Refresh token reuse interval: 10 to 30 seconds, which tolerates two tabs racing on one refresh token.
- Time-box user sessions (12 hours) and inactivity timeout: Pro plan only, and this project is on Free, so the app-enforced limits are the only limits. Even on Pro, a time-box is project-wide, so a 12-hour value would also cut patients short of their 90 days. Rely on the app limits for both portals.

The backend accepts access tokens up to 30 seconds past their `exp` (clock-skew leeway), and a session response never reports `expires_at` as 0.

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

## PAT-002-B confirmation rollout (local verification active)

Migrations 059/060 are versioned implementation artifacts. Applying them, publishing
question eligibility and changing deployed configuration are distinct rollout
actions. No bundle is seeded or approved by migration 060. On October 12 the requester
reported Ganesh approved the unchanged paired-locale candidate; the
[approval record](../backend/src/app/intake/question_library/candidate-1-review.md#requester-reported-approval)
states its provenance, date and canonical hash. This is not a formal PR approval.

October 12 requester rollout recheck: the requester reported applying the migrations.
Read-only `schema_migrations` queries confirmed both 059/060 ledger entries match the
versioned file checksums below. The confirmation column is available and the intake
RPC rejects an unknown patient with `42501`. After the dated approval report, the
manifest selected `candidate-1`, matching eligibility metadata were published via
`set_symptom_question_eligibility`, and the local backend was restarted with
`SYMPTOM_INTAKE_ENABLED=true`. An authenticated fictional patient confirmation and
assigned-clinician summary then passed locally, as recorded in the
[acceptance evidence](evidence/pat-002-b-acceptance-2026-10-12.md#approved-library-local-acceptance--october-12).
The deployed backend setting and deployed acceptance remain separate.

| Migration | SHA-256 |
| --- | --- |
| `059_chat_safety_alerts.sql` | `9ce875b7d1fca79f687f83e6ea02d7b4b56273d5aba064c665591dc8a2ac56f5` |
| `060_confirmed_symptom_intake.sql` | `3f6c9591fe41dab5bd476096174c5d69770be38dbeae8d5db82841f2a0361d42` |
| `071_confirmed_symptom_handoff.sql` | `f690b788d5f29c3d7583f2fe8cc43b7a51a6af817c276d6839cc9c9ab2ded36b` |

Before an authorized rollout, drain old direct symptom-report writers, including
old demo/import tooling that inserts unconfirmed reports. Migration 060 removes direct
browser report writes and requires new reports through confirmation. Historical rows
stay legacy and are not converted into fabricated patient consent. Deploy compatible
nullable-severity consumers with the schema before enabling new confirmation behavior.
Verify owner read, browser stored-context column denial, staff/unassigned denial,
service-RPC-only writes, append-only audit,
source/session binding, exact confirmation/retry and independent safety alert delivery.

Activation requires the reviewed immutable packaged version/hash, matching genuine
`set_symptom_question_eligibility` metadata and `SYMPTOM_INTAKE_ENABLED=true`. That
manifest RPC is deployment-only; runtime intake never calls it and browsers cannot.
Changed content requires a new version. Revocation blocks progression/confirmation;
owned recovery, cancellation and existing safety escalation remain available. Never
substitute the disposable SQL fixtures' approval reference into a runtime manifest.

Rollback disables intake and its ordinary writes while preserving drafts, confirmed
reports and durable safety-alert retry. It must not restore automatic unconfirmed
report insertion. See [the acceptance record](evidence/pat-002-b-acceptance-2026-10-12.md) for
local SQL constraints, manual acceptance, dependency reproducibility and the C handoff.


The October 17 handoff work uses the exact applied 071 identity described above. It
intentionally coexists with the clinician-visit 071 file because the ledger keys on the
full filename and checksum. Keep applied 059/060/071 names and checksums unchanged.
The exact prerequisites, authorization state and read-only
`preflight_symptom_intake.py` procedure are in the
[PAT-002-B rollout](pat-002-b-rollout.md). Do not run unrelated pending migrations as
part of this change. Candidate-2 remains pending genuine review; neither SQL nor a
passing test approves a question bundle.
