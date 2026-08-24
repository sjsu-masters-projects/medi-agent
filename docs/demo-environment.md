# Synthetic demonstration environment

This environment is for local, demo, or staging use only. It contains no real patient
data and must never be pointed at a production project. The canonical source is
[synthetic_ca_portal_demo_2026_08.json](../backend/src/app/db/seed/fixtures/synthetic_ca_portal_demo_2026_08.json);
its source IDs and display labels replace the previous hand-authored demo personas.

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

The adapter derives non-clinical Auth emails from canonical source IDs rather than
inventing people: SYN-PT-001 becomes syn-pt-001@demo.mediagent.live. Staff use the
same source-ID convention. These identifiers are adapter plumbing, not fixture
demographics; source display labels remain the persisted name-like values.

## Reset

Reset is guarded: it refuses environments outside development, demo, or staging;
requires --confirm-demo-reset; and deletes only exact canonical-fixture account
emails (including the previous `.local` fixture aliases) plus the two canonical
synthetic clinics.

    export ENVIRONMENT=staging
    export DEMO_ACCOUNT_PASSWORD='choose-a-local-password'
    PYTHONPATH=backend/src backend/.venv/bin/python backend/scripts/seed_demo_environment.py \
      --reset --confirm-demo-reset

Use reset only for an approved synthetic environment. Do not use a production database
URL or environment value.
