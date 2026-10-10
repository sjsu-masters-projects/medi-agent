# Patient-upload review and care-plan evidence

Parsing and source storage remain non-blocking. Patient-uploaded documents must
be approved before their evidence can supply a new care-plan proposal. Pending,
rejected, missing and withdrawn document sources fail closed. When a fact has
multiple document citations, every document citation must be eligible; an
accepted citation cannot silently override an unaccepted one.

Preview and publication recheck active items. Removed items do not block review.
Migration `048_patient_upload_care_plan_review_gate.sql` adds a publication trigger
which locks cited documents while checking acceptance. Document review uses a
pending-status compare-and-set, so concurrent decisions cannot overwrite one
another. Approval of an already-parsed eligible upload atomically requests a new
draft; parsing does not need to run again. Clinician-uploaded evidence and local
clinician entries retain their existing eligibility path.

The review queue links to the patient's Documents tab and anchors/highlights the
specific document. Care-plan citations expose the patient-upload review decision.

## Rollout boundary

Apply the migration only after explicit environment-specific authorization.
Existing approved versions, canonical activities, reminders and patient responses
are not rewritten or revoked. Before reusing historical evidence, clinicians must
review any pending uploads used by previously approved versions. An existing
approved plan is not retrospectively proven safe by installing this guard.

This change does not authorize remote repair, reseeding, deleting history or
automatically approving patient documents.

## Draft continuity and supported Spanish cadence

Opening a new draft carries forward exact-source exclusions from the last
approved version, preventing another document from reviving a previously removed
proposal. New source facts still require reconciliation. Preview also rejects
missing, foreign-patient and rejected facts before the publication RPC.

Supported Spanish frequency phrases and weekday lists normalize to the existing
deterministic cadence parser. Unknown or conditional phrases fail closed; this
is not free-form translation. Spanish weekday regression coverage checks both
scheduled inclusion and unscheduled absence for medications and obligations.

Expired-session return paths retain the exact document fragment as well as the
patient Documents tab. These changes do not grant additional access.

## Verification update

Backend service/router suite: `pytest tests/unit/services
tests/integration/routers --no-cov -q` — **1,034 passed**. Focused Spanish
cadence/feed suite: **98 passed**. Ruff passed for cadence source/tests; mypy
passed for four changed service files. Clinician suite: **223 passed**, with
typecheck, focused ESLint and webpack production build passing. All **65 real
PostgreSQL tests passed** against isolated PostgreSQL 16 containers; migration
validation accepted 56 SQL files. These local checks do not prove deployed
behavior. No remote migration or deployment performed.

Parallel database review finalized patient-scoped evidence fencing, atomic
generation/publication eligibility rechecks and serialized queue creation. It
filters null patient IDs inside every lineage-discovery loop and adds a bounded
insert/delete regression. Static validation passed for 56 migrations and seven
PL/pgSQL bodies; Ruff, formatting and diff checks passed. Native initdb failed
with macOS shared-memory exhaustion. The opt-in Docker fixture bypassed that
host limitation without changing kernel settings: **65 passed, 3 warnings in
227.76 seconds**. A fixture that accidentally created two open drafts for one
patient was corrected to use a second synthetic patient; the full suite then
passed. No product constraint was weakened.

Reproduce from `backend/` using synthetic CI settings:

```sh
CARE_PLAN_TEST_POSTGRES=1 CARE_PLAN_TEST_POSTGRES_DOCKER=1 PYTHONPATH=src \
  .venv/bin/pytest tests/integration/test_care_plan_postgres.py --no-cov -q -x
```

Docker mode requires an already available official `postgres:16` image. Each
test creates and removes its own network-isolated container, without host
ports, volumes or connection to Supabase.
