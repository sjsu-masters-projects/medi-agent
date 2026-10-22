# Records, medication and clinician-workflow completion

Scope: REC-001/002, NOT-003, OPS-006, MED-001, CLN-001/002.
Delivery: [PR #208](https://github.com/sjsu-masters-projects/medi-agent/pull/208),
branch `codex/expo-workflow-completion`, based on merged #207 (`977cf8c`).
This is the current contract/checkpoint, not a chronological status log.
Detailed requirements remain in [backlog acceptance](project-backlog-acceptance.md).

## Post-merge acceptance

#208 merged as `f235c278`; main CI, frontend CI and backend deployment succeeded.
Backend `00177-xgh` serves 100% traffic. The new Timeline tab and both portal
notification counts load after refresh. Follow-up branch
`codex/post-208-acceptance` records the [grouped live campaign](../../docs/evidence/deployed-recheck-2026-10-11.md#post-208-grouped-acceptance).
Do not repeat PR-review gates or infer migration 079 from a successful image
deployment. Formal provider evaluation is optional; functional/safety checks remain.

## Approved boundaries

Requester decisions, October 21, 2026:

- Synthetic university-expo workflows, not commercial production certification.
- OPS-006 retains durable worker/recovery. SSE replacement, counter/stream rewrite
  and large load/cost reset are excluded. Historical OPS-005 RCA is separate.
- Alerts is the common action inbox. Patient Upload Review Queue stays source
  approval only; existing clinical approval screens remain authoritative.
- Retain audited clinician accounts; permanent deletion is excluded. No FK weakening.
- MED-001 is source-based review, not comprehensive drug interaction/equivalence
  checking. Unlisted testimony is not approved medication; flags are not confirmed ADRs.
- No backfill, active chart write, SQL application, code deployment or merge is
  authorized by this document. The separately authorized secret configuration below
  is completed. Requester authorized two implementation/review agents for this PR.

## Task implementation and release acceptance

| Task | Implementation / local acceptance | Release acceptance still required |
| --- | --- | --- |
| REC-001 | Grounded titles in catalog, existing citations and care-plan evidence; original filenames/IDs/pages preserved. Correction, bounded retries and source withdrawal/provenance contracts tested. | Deployed source-title and correction/retry/retained-source UI recheck. |
| REC-002 | Actual 029–032 RPC contracts for add/update selected fields/keep/defer/reject, binding, replay, stale/foreign sources and unchanged reminders/history. Lost-response retry and exact NKDA absence handling fixed. | Complete October 21: authorized Keep existing → reload → one matching immutable decision/audit; approved medicines/reminders unchanged. See grouped evidence. |
| NOT-003 | Purpose-derived signing and independent-root option; actor/role/purpose/expiry/rotation/auth-token isolation tests. Independent root configured. | New-code activation, both portals' notification reads/read-through and stale-cursor refresh. |
| OPS-006 | Amended worker slice accepted: real outage/long-session delivery, 35 PostgreSQL contracts and bounded runtime/IAM checks. | Already Done for this slice, not blanket inherited-IAM/hosted-checksum or OPS-005 closure. |
| MED-001 | Source conflict flags, explicit-click public references with source/cache dates, unchecked coverage, conservative matching, preserved testimony and atomic forward-only review capture. No invented medication/ADR/Naranjo for unlinked products. | Complete October 21: authorized 079 plus new synthetic confirmation → exact report alert → one audited acknowledgement; reload/History persist, medication/plan/activity/ADR fingerprints unchanged. See grouped evidence. |
| CLN-001 | Scoped inbox/review links, current external-candidate pages and exact counts, source/age/snapshot context, visible-only refresh and stale-clinic isolation. Existing decision APIs unchanged. | Two-reviewer shared state, clinic/access scope, failure/retry and acknowledgement UI. |
| CLN-002 | Versioned risk rationale, actual source dates and bounded cross-domain source-linked timeline with explicit unavailable coverage. | Deployed timeline/freshness/links, own-private-thread isolation and keyboard/narrow-layout acceptance. |

Implementation/CI review readiness is not deployed acceptance. Do not mark task
rows Done from local tests, preview deployment or a health check alone.

## Records and medication contracts

Original artifacts, storage keys, source IDs, exact excerpts/pages and audit history
remain intact. Clinician care-plan labels prefer grounded English plus original
filename; missing wording falls back, never translated or inferred. No backfill.

Reconciliation changes only explicitly selected nonempty fields through the atomic
RPC. Existing medication IDs, unrelated rows, reminders, adherence and ADR references
persist. Imports never create reminders. Lost-response replay is actor/patient/fact/
decision/target/field/note-bound and rechecks assignment before returning snapshots.
A replay cannot execute another canonical mutation.

Exact NKDA/NKA/known absence statements are evidence, not positive allergens.
Mixed/unknown narrative is not reclassified by substring inference. Possible-name
matching ignores strength/form text only to offer comparison; ER/IR, salts and
combinations remain significant. Source dose/frequency/route/status/RxNorm/allergen
differences are review flags, not equivalence or safety conclusions. Coverage for
drug interactions/therapeutic equivalence is explicitly unchecked.

An optional explicit-click Medication reference panel reuses the existing public
reference cache. Only the recorded drug name is looked up. Assignment, patient and
fact identity are checked before lookup. Up to three official DailyMed/MedlinePlus
references expose bounded excerpts, source version/update/check dates and stale
state; unresolved and unavailable are distinct. Date-only updates keep their date.
The RxNorm ingredient concept is informational, never an automatically applied
candidate value or proof of formulation equivalence. Source clinical evidence,
canonical medication decisions and public reference material remain separate.

Pre-208 read-only baseline: Elena's assigned synthetic Rajeev chart had 39 pending
facts, four medication candidates and three active medicines. Lisinopril strength/
form matching failed in the deployed preview; local regression fixes this. Preview
was cancelled; glucose activity and unconfigured reminders stayed unchanged.
Proof: `/private/tmp/rec-lisinopril-unmatched-before-fix.png` and
`/private/tmp/rec-unchanged-approved-profile.png`. That earlier inspection made no
decision. Post-208 authorized Keep existing and its exact audit are now accepted
in the grouped live evidence; pending candidates are 38 and medicines unchanged.

## Unlisted-product review and migration 079

`079_unlisted_product_review_alerts.sql` captures a shared safety-review event
atomically with a newly confirmed report only for an explicitly answered true
product concern, nonempty name and no unique canonical medication link. Drafts,
unknown/declined/false concerns and linked products do not create this item.
No historical notifications are regenerated.

Only source identifiers/review kind enter event metadata. Existing current
assignment/clinic authorization, open-work delivery, per-recipient acknowledgement
and immutable audit are reused. No human message is impersonated. The alert opens
and focuses the exact report, including outside the ten-row preview; the clinician
can compare the recorded medication list. Acknowledge means seen for follow-up,
not resolved, approved medication or confirmed ADR. Cached context cannot replace
a missing canonical medication FK.

The worker completes an unlinked-product screen with a reconciliation requirement,
not repeated ADR creation failures or an invented Naranjo score. Linked-product
ADR processing and urgent/emergency guidance are unchanged.

079 is re-runnable and ends with RLS/browser-access checks, preserving existing
clinic authorization functions. With explicit requester approval, applied alone
on October 21 Pacific (receipt 2026-10-22 03:40:37.892769 UTC); checksum, trigger,
RLS and browser-write/capture denial verified. SHA-256:
`6b781b77e48d41f618d131d33fd0a710af5cd585a6172fdd42eb56bee92a947e`.
The local Supabase CLI is unavailable: use this repository's filename/checksum
ledger, parser and real PostgreSQL contracts, not improvised hosted SQL.

## Inbox, timeline and freshness

Upload review refreshes every 15 seconds while visible and on focus, retaining
rows on background failure. Refresh pauses during decisions; old reads cannot
restore completed rows, old-clinic responses are ignored and timers are removed
on unmount. Source-state retrieval time is not the last clinical review. Reading
a notification never completes its underlying work.

External record review work is read directly from currently assigned patients'
pending imported candidates, not regenerated as notifications. Each clinic-scoped
page examines ten assigned patients; exact per-patient counts are separate from
unread counts. At most 200 candidates and 20 citations per candidate contribute
source capture-time coverage. Incomplete coverage is labelled; capture time is not
clinical event time or last review. Rejected, withdrawn, uncited and private-report
sources do not enter this queue. Rows open existing External Records controls.

`GET /api/v1/clinicians/me/patients/{patient_id}/timeline` checks assignment before
reads. Twelve buckets cover uploads/reviews, medication recording, confirmed
symptoms, adherence, own private messages, appointment recording/actions and
care-plan/clinical-fact/ADR/clinical-action events. At most 40 newest dated rows
per bucket, with deterministic ordering, lookahead and explicit invalid/failure
coverage. Undated records do not receive invented dates.

Messages are restricted to the actor's ten most recently active patient threads;
the existing RPC verifies each exact conversation's clinic, assignment and active
membership. Other clinicians' private history, bodies, raw audit payloads and
private reasoning are excluded. Exact source links expose selected record fields;
supported source workspaces get exact IDs. Missing bounded results are explained.
This is not a full audit trail: current fields are not historical snapshots,
medication recording is not a dose change and appointment creation is not visit time.

Risk thresholds are unchanged. Explanations include rule version/calculation time,
recorded-response versus expected-dose adherence, unknown inputs and latest source
dates. Freshness reads are bounded but not an atomic scoring snapshot or proof of
clinical currency. Missing dates remain unknown; failed reads are unavailable.

Timeline schema/privacy follow-up: sender names/text and related-record ID detail
fields are excluded; only each patient-authorized event identity and exact local
navigation links remain. An available source date means a dated record was read,
not that it is clinically fresh or reviewed. In offline PostgreSQL 16,
`tests/integration/test_patient_timeline_postgres.py` executes selected columns,
filters, actual FK joins, ordering and limits as `service_role`; every one of the
twelve source buckets returns real events and all four freshness probes return
dated sources. It also runs the actual conversation RPC to exclude another
clinician's thread and deny stale membership, suspended clinic, mismatched
conversation clinic and revoked exact assignment despite another patient assignment.
Synthetic symptoms use the real preview/confirmation path, retaining its guards.

No new migration/configuration is needed for the timeline; deploy its backend
endpoint before the UI on the existing confirmed-symptom/clinic-conversation
migration baseline. The SQL transport does not exercise hosted PostgREST HTTP
or schema-cache behavior. Its six cases run in CI's explicit no-skip Docker group.
External record query embedding/counts are additionally exercised against actual
PostgREST v14.1 over migration-led PostgreSQL, in an isolated local network namespace.

## Authorized notification-secret configuration

Independent root generated directly into Secret Manager, never printed/written
locally. Enabled `NOTIFICATION_TOKEN_SIGNING_SECRET:1` is bound to backend
`mediagent-backend-00176-8zk`, healthy at 100% traffic. Existing runtime identity
has secret-level accessor access. Same immutable image:
`57b5e3216793822fd48cf0cd84b6a8263e50b8fac9716d774dc395c594e9f354`.
Timeout 3600s, concurrency 80, max 2 and CPU/identity settings retained. Deployment
uses preserving `--update-*` forms. Login keys, worker and SQL were not changed.

This configuration revision does not deploy #208's new signing code. New code
derives a notification-specific key, never uses the raw login key. Without an
independent root, the domain-derived fallback does not protect against compromise
of the shared root. Deployment/rotation invalidates old 15-minute snapshots/cursors:
refresh after replicas converge, never recreate clinical events or change sessions.

## MED-002 — Clinician reconciliation experience and patient confirmation

Requester un-deferred MED-002 on October 22. It reuses the shipped REC-002 reconciliation
decision path (`apply_clinical_fact_reconciliation`, migrations 029–032); nothing there is
rebuilt.

### Gap analysis

| MED-002 requirement | Already shipped | Gap closed here |
| --- | --- | --- |
| Side-by-side source comparison | Reconcile modal: imported candidate beside the matched local record, per-field selection, selected-field preview, conservative review flags, DailyMed/MedlinePlus reference (MED-001/REC-002). | None for candidate versus approved list. Comparison is candidate against local matches, not every source at once; a simultaneous patient/clinician/document/FHIR matrix stays out of scope. The patient's answer now appears as an extra evidence row. |
| Accept, reject, edit | Add, update selected fields, keep existing, reject, correct (REC-002, 44 PostgreSQL cases). | None. |
| Defer | `defer` decision with required note; filter by deferred state. | None. |
| Request patient confirmation | Absent. | Clinician "Ask the patient to confirm"; patient question; patient testimony returned as evidence (below). |
| Evidence, provenance, confidence, time | Source identifiers, uncertainty, lineage, timestamps in the review panel. | Answer shown with time and "not verified". |
| Approved changes reach both portals and FHIR export | Approved medications drive Today/Records; the audit and handoff FHIR bundles read the shared record. | Unchanged. No new export is claimed; deployed export recheck remains open. |

### Patient confirmation contract (migration 094)

- A clinician on an active care-team link asks one plain question about one pending medication
  fact: about the imported version, or about a matched approved medication of the same patient.
  The request belongs to that link (`care_team_id`); a clinician who cannot see the fact, holds
  no active link, or names another link is refused and the API answers not found.
- The patient sees it on Today: "Are you still taking Metformin 500 mg twice daily?" with Yes,
  No I stopped, It changed (a note of up to 500 characters is required) and Not sure, in en-US
  and es-MX. The es-MX wording is a **draft pending LOC-001**. The cadence uses the reviewed
  phrase table when it recognises the text and is otherwise shown as written. The card says
  the answer changes no medicine or reminder.
- The answer is **patient testimony**. Nothing writes to `medications`, `clinical_facts`, plans
  or reminders. The clinician sees it in the reconcile modal as unverified evidence and decides
  through the existing decision.
- Idempotent: the client request id is the primary key; a repeat returns the stored request, and
  a second ask for the same fact and link while one is open returns it. One answer per request;
  the same answer again is a replay, a different one is a 409. Ten open requests per patient.
- Expires after 14 days on the database clock; an expired request is hidden from the patient,
  not answerable (422) and shown to the clinician as expired. A fresh ask retires it. Answered
  requests leave the patient's list after seven days.
- Audited by append-only events (ids and types only). Requests are immutable except the single
  open to answered or open to expired transition. Data API roles reach nothing.
- Lock order: lock-free authorization, patient advisory lock, request row. No locks across calls.

Not built: a notification-centre or email alert for the question (the patient finds it on Today
within a minute; a push is a follow-up), clinician cancel, and a clinician list of all open
questions (they are read per fact in the reconcile modal).

Evidence: 21 router/service tests, 17 PostgreSQL contract cases (CI shard
`medication-confirmations`), 5 clinician and 7 patient component tests. Screenshots (API mocked)
were reviewed at 390 and 1280 px in both locales with no horizontal scroll.

## Verification and CI

October 21 combined runs:

- Backend unit/router sweep: **4,030 passed** with `PYTHONPATH=src .venv/bin/pytest tests/unit tests/integration/routers --no-cov -q --tb=short`.
- Clinician full suite: **675 tests / 76 files passed** with `npm run test`.
- Previously failed email/scheduling/grants PostgreSQL group: **60 passed**.
- New unlisted-product PostgreSQL suite: **10 passed**, no skips: atomic capture
  rollback/retry, new-reviewer shared access, revocation, audited acknowledgement,
  duplicate confirmation, unchanged canonical truth, rerun and browser denials.
- Combined unlisted-product/timeline PostgreSQL lane: **16 passed**, no skips,
  including **6 timeline** source/RPC cases; the earlier one-case projection check
  was expanded, not counted as a separate final test. Command:
  `NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER=1 PYTHONPATH=src .venv/bin/pytest tests/integration/test_unlisted_product_review_postgres.py tests/integration/test_patient_timeline_postgres.py --no-cov -q --tb=short -x`.
- Actual external-review PostgREST contract: **1 passed**, zero skips with
  `EXTERNAL_REVIEW_TEST_POSTGREST_DOCKER=1 PYTHONPATH=src .venv/bin/pytest tests/integration/test_external_record_reviews_postgrest.py --no-cov -q`.
  Exact count 39 survives duplicate citations and excludes rejected, withdrawn,
  private-report, foreign-patient and uncited candidates.
- Timeline/risk follow-up: **68 passed** with `PYTHONPATH=src .venv/bin/pytest tests/unit/services/test_patient_timeline_service.py tests/unit/test_risk_score_service.py --no-cov -q`, including two explicit API role/assignment denial tests. These overlap the prior broad run.
- Timeline/risk UI follow-up: **8 passed** with `DEBUG_PRINT_LIMIT=300 npm run test -- src/__tests__/patient-timeline.test.tsx src/__tests__/risk-explanation.test.tsx`; clinician lint/typecheck, focused Ruff/format, source mypy and whitespace checks pass.
- Reconciliation: **44 real PostgreSQL contracts** passed, including replay after
  revocation being denied without returning snapshots; **41 focused service checks** pass.
- Migration parser: **95 files valid**; required source Ruff/format, changed-test
  Ruff/format and source mypy **283 files** pass. A wider optional all-tests Ruff
  scan found five pre-existing findings in untouched files; none are new-file findings.
- Unchanged patient portal prior run: **834 passed**. Final-head CI remains required.
- Clinician lint/typecheck and webpack production build pass; local default Turbopack had
  subprocess-port restrictions earlier. Default CI/preview builds are not bypassed.

The failed CI job on `f96514a` had two Docker subprocess setup timeouts (18s
migration command; 10s database creation) and 58 passed assertions. Process/setup
budgets are now 60s, retaining PostgreSQL's 12s statement limit, race assertions
and no-skip requirements. This adds host scheduling headroom; it is not a wider
infrastructure RCA. New contract suites have explicit CI minimum counts.

CI on the superseded `1b306c4`: all 38 non-summary/scanner checks passed, including
new PostgreSQL/timeline, reconciliation, actual PostgREST, coverage and frontend
checks. Secret scanning flagged the
deliberately invalid URL-userinfo fixture in the reference rejection test (not a
live credential). A runtime-constructed synthetic fixture passes all 29 reference
tests locally, without changing scanner rules. The requester authorized replacing
only that latest commit using an explicit expected-commit lease; earlier commits
are retained. The replacement head still requires its own CI results.

The replacement passed secret scanning. Its dependency audit then reported newly
published CVE-2026-113786 in locked `pypdf==6.20.1`. The narrow follow-up pins
`6.21.1` and regenerates both locks with CI's uv 0.9.24; no unrelated dependency
versions changed. The repeated compile is stable and pip-audit 2.10.1 reports no
known vulnerabilities. This matches the [upstream security release](https://github.com/py-pdf/pypdf/releases/tag/6.21.1)
and [advisory](https://github.com/advisories/GHSA-5hx5-vpf9-5wcv). The backend
unit/router sweep, including MedWatch PDF regressions, passes **4,030 tests** on
installed pypdf 6.21.1. Final-head CI remains distinct from deployed acceptance.

## Release checklist (separate remote authority)

1. Merge/deploy reviewed code. Verify independent-root notification reads and
   read-through in both portals; refresh old snapshots without changing sessions.
2. Apply exact reviewed 079 only after explicit authorization and verify checksum,
   RLS and grants. Capture is forward-only; use a new synthetic confirmation.
3. Demonstrate report → assigned alert → exact report → audited acknowledgement,
   with no medication, ADR, reminder or clinical approval mutation.
4. Recheck record lifecycle and explicit reconciliation on an authorized synthetic
   fixture, preserving active demo history.
5. Verify timeline/freshness, private-thread isolation, shared reviewer refresh,
   source failures, keyboard focus and narrow layout in deployed UI.
6. Record actual evidence, then move eligible Verify deployed rows to Done.
