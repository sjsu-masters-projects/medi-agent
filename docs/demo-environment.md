# Synthetic demonstration environment

This environment is for local, demo, or staging use only. It contains no real patient
data and must never be pointed at a production project. The canonical source is
[synthetic_ca_portal_demo_2026_08.json](../backend/src/app/db/seed/fixtures/synthetic_ca_portal_demo_2026_08.json);
its source IDs and display labels replace the previous hand-authored demo personas.

## University-expo scenario

Use the [presentation script](expo-demo-script.md),
[limitations brief](project-limitations.md) and [recovery notes](expo-recovery.md)
to prepare the run. These documents do not establish that provisioning or a
rehearsal has happened.

The current delivery is a master's-project expo, not a commercial pilot. The
presenter operates both fictional roles; no real patients, healthcare-professional
recruitment, real medical records or investor materials are required. See
[DEMO-001 requirements](../.agent/specs/project-backlog-acceptance.md#demo-001--fresh-synthetic-expo-scenario)
and [the task board](../.agent/TASKS.md) before provisioning.

Prepare this scenario **after the selected features work**, separately from the
existing Morgan/Elena QA history:

1. Start with a blank synthetic patient and clinician, a named fictional clinic
   and a verified assignment. Scope and authorize account creation beforehand;
   do not reset the shared fixture to obtain blank accounts.
2. Build a coherent historical baseline through normal supported application
   flows: appointment offers/responses, synthetic clinician documents, patient
   upload review, plan approval/revision, Today reminders and completion/barriers.
3. Add confirmed symptom reporting, clinician ADR review, and private two-way
   messages only when those implementations have passed their acceptance checks.
   A Nora conversation alone is not a confirmed report or an ADR diagnosis.
4. Keep source previews, attribution, plan continuity and audit evidence intact.
   Let timestamps reflect actual rehearsal actions. Do not forge professional
   signatures or invent backdated clinical approvals/history with ad hoc SQL.
5. Reuse the same accounts for the expo: show the prepared history, then perform
   a small live segment. Document its expected results and avoid accumulating
   duplicate plans/medications while rehearsing.
6. Rehearse English/Spanish patient UI, reviewed clinical wording, mobile patient
   and desktop clinician layouts, refresh/persistence and an unavailable-service
   response. Keep a fallback recording and concise recovery instructions.

The eventual run sheet must identify the accounts by fictional display name,
baseline documents/approved plan, appointments, adherence/barriers, supported
symptom/ADR state, human conversation, live actions and expected screen states.
Never store passwords in it. Clearly distinguish prepared history, live actions
and unavailable features. This plan is not evidence that the scenario is already
provisioned or rehearsed, and it does not authorize remote creation or deletion.

## Provision

Apply migrations before changing fixture data. The adapter verifies every committed
migration checksum before a real reset or seed:

    export MEDIAGENT_DB_URL='postgresql://…'
    scripts/apply-supabase-migrations.sh

    export DEMO_ACCOUNT_PASSWORD='choose-a-local-password'
    PYTHONPATH=backend/src backend/.venv/bin/python backend/scripts/seed_demo_environment.py

The command is idempotent. It maps only canonical source content supported by current
production tables: clinics, staff/patient accounts, care teams, conditions, allergies,
medications, metadata-only documents, patient-reported concerns, appointments, and
in-portal notifications. It never creates generic obligations or copies external
notification delivery state.

Preview without connecting to Supabase:

    PYTHONPATH=backend/src backend/.venv/bin/python backend/scripts/seed_demo_environment.py --dry-run

## Required Auth control-plane check

The migrations create `public.custom_access_token_hook`, but they cannot enable it in
Supabase Auth. After applying migrations, open **Authentication → Auth Hooks** and
enable **Customize Access Token (JWT) Claims hook** with
`public.custom_access_token_hook`. Then perform a new patient password sign-in through
the backend and verify the returned role is `patient`. A successful password exchange
alone is not sufficient: a missing `user_role` claim causes the portals to reject the
session.

## Synthetic accounts

The adapter uses named fictional accounts in the project-controlled
`accounts.mediagent.live` namespace. The source IDs remain internal provenance
identifiers; the account emails and persisted display labels are coherent fictional
names. The reset recognizes the two prior source-ID email namespaces only so it can
remove the exact old fixture accounts safely. It also recognizes the six verified
named accounts from the pre-canonical fixture; this remains an explicit allowlist,
not a domain-wide deletion rule. After a reset, verify that the Auth user inventory
and the `patients` and `clinicians` profiles contain only the sixteen current
`accounts.mediagent.live` fixture addresses.

## Auth-account QA

Use fictional patient, clinic-admin and non-admin clinician accounts in the
intended local/demo/staging environment. Existing fixture accounts are preferred
for ongoing tests; use normal signup flows for an explicitly scoped new scenario.
Never commit passwords or live credentials; share them out of band only.

- Patient: verify signup/onboarding/login, document upload and invite-code join.
- Clinic admin: verify clinic bootstrap `/signup/admin`, clinic profile, MFA
  enrollment/login where required, clinic-wide invite history and code provenance.
- Non-admin clinician: verify signup/login, clinic profile, required MFA, dashboard,
  personal-only invite history and patient linking without admin visibility.
- Linking: issue a code from the intended clinician/admin, join from patient
  onboarding/profile, then verify actual assignment and the admin/non-admin
  visibility distinction. A clinic affiliation is not proof of assignment.
- Recovery: inspect the session/profile/assignment problem first. Do not recreate
  accounts or reset the shared fixture merely because an account drifts. Any
  reset/recreation needs explicit authorization and the audit-retention checks below.

This incorporates the retired `qa-auth-accounts.md` checklist. It is a repeatable
QA contract, not permission to create accounts, enroll MFA or reset remotely.

## Reset

Reset is guarded: it refuses environments outside development, demo, or staging;
requires --confirm-demo-reset; and deletes only exact canonical-fixture account
emails (including the previous `.local` fixture aliases) plus the two canonical
fixture clinics.

    export ENVIRONMENT=staging
    export DEMO_ACCOUNT_PASSWORD='choose-a-local-password'
    PYTHONPATH=backend/src backend/.venv/bin/python backend/scripts/seed_demo_environment.py \
      --reset --confirm-demo-reset

Use reset only for an approved synthetic environment. Do not use a production database
URL or environment value.

## Appointment offer audit retention

After migrations `040` and `041`, grouped appointment offers create append-only
`appointment_offer_events`. These retain their appointment and patient references.
The existing reset script cannot delete fixture patients with offer events; do not run
that reset after exercising grouped offers in a shared environment. Use the existing
fixture without resetting, or a fresh isolated demo database. A purge/reset path for
this audit history requires a separate retention review. Single-slot fixtures remain
unchanged. See the scheduling design in `docs/features/scheduling.md`
for the grouped-offer API and manual acceptance steps.
