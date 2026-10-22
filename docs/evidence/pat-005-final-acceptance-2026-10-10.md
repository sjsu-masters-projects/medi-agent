# PAT-005 final acceptance follow-up: October 10, 2026

Synthetic Morgan Ellis / Elena Park only. This is prototype acceptance evidence,
not a clinical, compliance, or production-readiness certification.

## Deployed evidence

- Spanish V3 was reviewed and published; V2 was superseded. Existing medication,
  reminders and completion history were preserved. No duplicate Metformin created.
- On Saturday, the Monday/Wednesday/Friday walking activity was absent from Today.
- Earlier acceptance covered V2 continuity, all six barriers, audit reconstruction,
  access isolation and the five-document ingestion run. These are not rerun here.
- Two-way human messaging was verified in English/Spanish with persisted replies,
  actual sender/clinic, unread counts and separate Nora/human conversations.
- Pending and rejected patient-upload evidence was ineligible. Approving the
  distinct hydration fixture queued an eligible generation request. The exact
  document deep link opened Morgan's document, rather than the roster.
- The queued request completed on its first attempt at **18:33:16 UTC**. V4 is a
  draft and **V3 remains active**. V4 carries four existing items forward and stages
  the repeated hydration instruction as an explicit overlap. Preview and approval
  controls are disabled while review/overlap/locale attestations are outstanding.
  No V4 edit, approval or publication was performed during this follow-up.

## Acceptance detail and evidence boundaries

- The five-document run claimed/completed 5/5, failed 0; a subsequent quiet-window
  execution produced one consolidated draft, not separate patient plans.
- V2 retained unchanged medication/movement/monitoring identities and historical
  responses/reminders; changed hydration received a new identity without inherited
  history. All six barriers were clinician-visible. Access-isolation closure is
  requester-confirmed and supported by recorded denial/regression checks; the
  October 10 run did not repeat the entire cross-account write matrix.
- Human messaging: one explicitly addressed Morgan/Elena thread, four messages
  (two per role), four sent audit events and two reader markers; full reloads
  preserved messages. Concurrency, reassignment and multiple-team isolation were
  verified separately in isolated PostgreSQL, not by this short live exchange.
- The patient-upload gate retained rejected source/facts while excluding eligibility.
  A distinct pending upload had one extracted/zero eligible facts; clinician approval
  made it eligible and queued the request. Exact-document navigation passed. V4
  generation subsequently completed, but no duplicate activity was published.
- Direct negative preview/publication checks have API/PostgreSQL coverage, not a
  newly exercised live blocked-publication attempt. Intermediate edit wording
  snapshots are not individually reconstructable from the current audit payload.
- Earlier unconfirmed fetch/save failures did not establish a backend root cause.
  Read retry/recovery is mitigation; uncertain writes require refresh before retry.

## Presentation fixes — merged and deployed in #140

1. Today had English interface labels despite a reviewed Spanish plan. Interface
   copy now follows saved en-US/es-MX preference, dates follow saved timezone, and
   all six barrier choices/actions are localized. Reviewed clinical wording is
   preserved. The existing shared modal accepts an optional localized close label.
2. Byte-identical uploads showed “Parse completed” with no facts. Authenticated
   reads now derive a duplicate-skipped display state from the latest ingestion
   attempt. Stored source, review state, facts and plan are unchanged. The source
   remains accessible; no hash or original-document identity is exposed. Both
   portals explain why extraction was skipped. The explanation endpoint returns
   static English/Spanish copy without a model or stale cached summary.

The duplicate check is batched over already-authorized document IDs. A newer
successful attempt wins; pending/failed document states are not overwritten.
The implementation required no migration/backfill. PR #140 merged; main `ce3799a`
CI/backend deployment and both portal commit statuses succeeded October 10.
Deployment is distinct from the pending authenticated presentation rechecks below.

## Verification

Run from the relevant app/backend directory with installed dependencies:

```sh
# Both portals
NODE_OPTIONS=--no-experimental-webstorage npm test
npm run lint
npm run typecheck -- --incremental false
npm run build -- --webpack

# Backend, synthetic environment variables only
SUPABASE_URL=https://example.supabase.co SUPABASE_ANON_KEY=synthetic \
SUPABASE_SERVICE_ROLE_KEY=synthetic SUPABASE_JWT_SECRET=synthetic \
PYTHONPATH=src pytest tests/ \
  --ignore=tests/integration/test_appointment_offer_transactions.py --no-cov -q --tb=short
mypy src/
```

- Backend: **2,056 passed, 98 skipped**. The skipped cases are opt-in care-plan and
  conversation PostgreSQL tests, not proof of new live behavior.
- Separate appointment transaction run: **31 setup errors**. `initdb` fails with
  `could not create shared memory segment: No space left on device` / `shmget`.
  PostgreSQL explicitly identifies a kernel shared-memory limit, not disk space.
  A run outside the sandbox failed identically. No external database was used.
- Patient: **322 tests passed**, plus 55 focused tests passed again after final
  shared-modal reuse and duplicate cache/language-switch coverage.
- Clinician: **247 tests passed**, plus 9 document-panel tests passed again after
  final duplicate summary rendering guard.
- Full portal lint, typecheck and webpack builds passed. Ruff on touched Python
  and mypy over all 214 source files passed. Existing SDK/build deprecation warnings
  remain; they are not hidden or represented as newly solved.

## Remaining presentation acceptance (PAT-005-L)

1. #140 is merged and its main CI/deployment succeeded; retain the local test
   limitations above as historical evidence, not a current merge blocker.
2. Verify deployed Today is fully Spanish, while
   reviewed clinical wording and reminder times stay unchanged.
3. Verify the existing duplicate fixture shows skipped extraction in patient
   Records and clinician Documents/Review Queue; source remains accessible and
   there is no empty-facts review or duplicate clinical proposal.
4. Keep V3 active. Resolve the staged V4 overlap only through clinician review;
   V4 publication is not necessary to close these presentation defects.

No new login, migration or patient data change is needed to prepare this review.
