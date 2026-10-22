# Safety hardening and release documentation

## Scope

Requester-approved grouped follow-up to merged #220 (`9c16adc4`), on
`codex/safety-release-completion`. INT-002's implementation is already merged;
do not rebuild its importer or confuse it with a deployed acceptance pass.

1. SAFE-001: replace the envelope check-then-insert race with an atomic
   conflict-ignore insert against its existing unique key. A retry reads the
   saved winner without overwriting its outcome or duplicating the request audit.
2. Require a persisted clinician profile as well as an active assignment for
   human clinical-action callers, including the proposer. Preserve independent
   review and the model-proposer restriction for clinician-originated actions.
3. Add disposable PostgreSQL tests for actual action-table permissions and
   envelope concurrency. Keep the existing clinical-action service unwired;
   this hardening does not introduce a new executor or alter care-plan publication.
4. REL-003: provide a runnable expo presentation script, an honest limitations
   brief and recovery instructions. Do not create accounts, fabricate history or
   claim a rehearsal occurred merely because the run sheet exists.
5. LOC-001: collect source-marked es-MX drafts into one English/Spanish review
   pack, with source/key/context and unresolved dynamic wording noted. A review
   list is not translation approval and does not alter clinical text.
6. Correct the historical direct clinician-email claim: addressed messages are
   in-app; opted-in generic notification emails are a separate delivery path.

## Excluded staging run

The requester removed `verify_authorization_denials.py` on staging from this
batch and the completion criteria. No credentials are requested and no staging
run will be made. Keep authorization controls, automated denial coverage and the
optional diagnostic script. Existing evidence remains historical; no pass is inferred.

## Acceptance and delivery

- Unit tests prove profile/assignment denial before writes, same-key replay,
  non-overwritten outcomes and a single execution-request audit.
- PostgreSQL tests exercise actual migration-led tables under hosted-style
  browser grants, concurrent inserts and browser denial of audit mutations.
- Run focused backend tests, Ruff/mypy and the documentation link checker.
- The Spanish pack identifies its exact source snapshot and remains repeatable.
- One follow-up PR; no remote migration, hosted SQL/configuration, deployment,
  patient/medication changes or account resets are authorized here.
- This completes the named hardening/docs slice, not every SAFE-001 executor,
  clinical validation, all release rehearsal or all bilingual wording approval.

## Verification recorded October 22

Run from `backend` with the four Supabase test variables set to synthetic test
values, never a live environment:

```sh
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/services/test_clinical_action_service.py \
  tests/unit/core/test_action_tiers.py \
  tests/unit/scripts/test_spanish_review_pack.py \
  tests/unit/services/test_authorization_audit_service.py \
  tests/unit/services/test_authorization_denial_classifier.py \
  tests/integration/test_authorization_denial_audit.py -q --no-cov
CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER=1 PYTHONPATH=src .venv/bin/python -m pytest \
  tests/integration/test_clinical_action_postgres.py -q --no-cov
.venv/bin/mypy src/ --ignore-missing-imports
```

Results: 45 focused tests passed; 14 real PostgreSQL tests passed against a
disposable local container and migration-led tables with hosted-style browser
grants. The container was removed after the run. Full backend mypy passed for
313 source files. Ruff and formatting passed for the changed Python files.
No hosted credentials, database or synthetic account was used.

From the repository root:

```sh
node --test scripts/extract-spanish-review.test.mjs
node --test scripts/tests/check-docs.test.mjs
python3 backend/scripts/build_spanish_review_pack.py --check
node scripts/check-docs.mjs --all
git diff --check
```

The static extractor's four tests and the link checker's three tests passed;
the 562-row pack matches its source snapshot. CI also runs the extraction tests,
freshness assertion and the new PostgreSQL module. No portal runtime component
changed, so no new UI screenshot or browser-build claim is made here.

The atomic insert fixes envelope-key races, not every future action lifecycle.
Envelope creation and audit insertion remain separate writes; a crash between
them is not made transactional by this change. Existing feature-specific
approval/publication APIs remain authoritative. Clinical safety and wording
qualification are not inferred from these infrastructure checks.
