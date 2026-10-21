# Records, medication and clinician-workflow completion

Requested October 21, 2026 (Pacific). Scope: REC-001, REC-002, NOT-003,
OPS-006, MED-001, CLN-001 and CLN-002. This plan is linked from TASKS so future
work does not depend on chat history. Branch: `codex/expo-workflow-completion`.
Delivery: [draft PR #208](https://github.com/sjsu-masters-projects/medi-agent/pull/208),
implementation checkpoint `aec00e2`. Do not merge while its explicit workflow
checklist is incomplete; continue changes on this branch, not merged #207.

## Rules and current position

Start from merged #207 (`977cf8c`), inspect existing implementation and acceptance
before adding replacements. Its main CI, frontend CI, quality checks and backend
deployment succeeded. No remote write, migration, deployment or load generation
is authorized by this plan. Do not overwrite teammate #203 translation or #193
confirmed-intake work. No existing task is removed or declared Done by this audit.

## Initial evidence and remaining scope

| Task | Existing implementation | Completion work / decision |
| --- | --- | --- |
| REC-001 | Grounded document titles; format/viewer contract; guarded extraction/retry; candidate correction/review; applied-source withdrawal preserves clinical truth/audit | Verify correction, retry, duplicate/error and withdrawal behavior end to end; inspect title reuse in citations/care-plan review; fix demonstrated gaps. No backfill or deletion of existing cited records without specific authorization. |
| REC-002 | ClinicalReconciliationService previews matches and explicitly applies add/update/keep/defer/reject via one audited database transaction; source identity binding; dedicated review UI | Verify candidate → selected-field decision → unchanged unrelated medication/reminders → persistent provenance, plus stale/foreign/duplicate negatives. Do not rebuild this service or claim local tests are a deployed journey. |
| NOT-003 | Actor/role/purpose/audience-bound 15-minute snapshots, now locally domain-key separated | Independent root configuration and deployed acceptance remain. Permanent deletion excluded by accepted retention decision; preserve all audit references. |
| OPS-006 | Durable queue/worker and recovery accepted, plus 35 isolated PostgreSQL checks and live read-only configuration/IAM evidence | Amended worker slice complete; no SSE, counter rewrite or load/cost reset required. Historical failure RCA stays OPS-005. |
| MED-001 | Canonical medication CRUD, conservative candidate matching and clinician-selected updates; RxNorm normalizer exists but no live callers found | Patient-reported unlisted products must remain evidence, not disappear or become approved medication automatically. Add explicit identity/source/conflict review, uncertainty, preserved history. A comprehensive interaction/allergy/duplicate-therapy engine is not already implemented; evidence coverage and clinical-review labeling must be explicit. No model-only assertion that a combination is safe. |
| CLN-001 | Alerts is the accepted action inbox; local cross-links preserve clinic; queue ignores stale responses | Finish age/source/freshness, supported work coverage and shared-review updates; existing authorized review controls stay separate. |
| CLN-002 | Deterministic threshold-based Risk Radar; adherence/open ADR/recent severity inputs and dashboard explanation; symptom timeline | Add explicit rule version, calculation time/data freshness, reason contributions and a source-linked cross-domain timeline. Unknown/missing data must not mean low risk or missed medication; automation is not a diagnosis. |

## Product decisions — approved October 21

1. OPS-006: retain worker reliability/security; remove SSE rewrite and large
   load/cost exercise from required expo scope, rather than rewriting a working
   transport for its own sake. Existing safety/authorization/backpressure remain.
2. CLN-001: make Alerts the common action inbox, with exact links into the existing
   document, ADR, care-plan and patient review destinations. Keep patient-upload
   approval clearly separate from clinical plan publication.
3. NOT-003: retain accounts referenced by clinical audit history; do not add
   permanent clinician deletion for the expo. Implement token-signing separation.
4. MED-001: source-based review only; comprehensive interaction/therapeutic-
   equivalence engine removed from expo scope. Retain unlisted testimony and
   explicit unknown coverage; no automatic medication approval or safety verdict.

The requester accepted all four decisions. Retain existing authorization, audit
and clinical review safeguards. OPS-006 closure is bounded worker reliability,
configuration and security acceptance, not a new transport/counter architecture
or a commercial-scale performance certification. Historical design details remain
identified as superseded rather than silently asserted implemented.

## Delivery order and acceptance

1. Record existing behavior/tests/live evidence and scope decisions first.
2. Finish records/reconciliation gaps as one vertical journey; use isolated
   database fixtures for destructive, ownership and race negatives.
3. Complete medication candidate handling and source-linked conflict review
   without changing approved clinical truth or reminders automatically.
4. Integrate the agreed action inbox, then versioned risk rationale/timeline.
5. Finish token separation and bounded worker acceptance; request exact remote
   authorization separately if new secret/configuration or SQL is needed.
6. Focused tests and permission/concurrency tests, lint/typecheck/build for changed
   surfaces, then synthetic two-portal acceptance after deployment. Mark Done only
   for agreed scope with evidence; distinguish implementation from rollout.

## Audit performed October 21

- Eight focused backend suites: **127 passed**, 3 existing dependency
  deprecation warnings. Suites: clinical reconciliation, document workflow,
  document titles, document service, risk score, notification centre, task OIDC
  auth and chat worker. Mocks/unit tests do not prove hosted permissions or UI.
- Four focused clinician suites: **36 passed** (SMART import review, patient
  upload Review Queue, Risk Radar presentation, notification centre). Existing
  Vite warning retained. Component tests do not prove live clinical decisions.
- Both patient and clinician Vercel statuses for merged #207 are success.
- Read-only Cloud Tasks: `nora-turns` RUNNING, 5 dispatches/s, concurrency 8,
  5 attempts, 2–30s backoff, 300s retry duration, matching setup documentation.
- Worker IAM: only the named task-invoker service account has `roles/run.invoker`
  in the returned service policy; no public invoker binding observed there.
- Backend revision `00175-7lt`, 100% traffic, timeout 3600s, concurrency 80,
  max instances 2, CPU throttling disabled. Worker `00021-s9w`, 100% traffic,
  timeout 300s, concurrency 4, max instances 3, request-based CPU.
  This is metadata evidence, not exhaustive effective/inherited IAM, exact hosted
  migration checksums, OIDC audience/environment verification or load acceptance.
- No cloud configuration, queue, SQL, identity, clinical record or secret changed.

## Implementation checkpoint

NOT-003 now has an optional independent `NOTIFICATION_TOKEN_SIGNING_SECRET`
(minimum 32 characters). A domain-derived key is used in either configuration,
never the raw Supabase login-signing secret. Without a separately configured root,
the domain-separated rollout fallback uses the existing auth root; this separates
token protocols but is not independent root-secret compromise protection.
Old raw-auth-signed snapshots are rejected; refresh the view after rollout or key
rotation. No login/session change or remote secret/configuration change occurred.

Medication reconciliation preview now surfaces recorded dosage/frequency/route/
active-status differences, ambiguous matches and exact recorded allergen-name
matches as review flags. It explicitly says interactions and therapeutic
equivalence are not checked. This is a read-only comparison, not clinical advice
or an automatic approved-list update. The confirmed-report → unlisted-product
review integration is still unfinished; this preview alone does not close MED-001.

Alerts and patient-upload review link to one another with the current clinic
filter. The upload queue ignores late responses from previous clinic scopes.
Risk Radar now offers a versioned explanation with calculation time, data windows
and unknown-adherence handling. Calculation time is explicitly not source freshness
or last clinical review. The chronological cross-domain timeline is unfinished.

Verification checkpoint: 57 token/service/API tests; 124 risk/clinician API tests;
29 existing records/binding/reprojection checks; 19 updated reconciliation/SMART
checks (batches overlap, not an additive unique count). Clinician full suite 631
passed; final expanded-suite rerun pending. Ruff and source mypy passed. Production
build passed with `npm run build -- --webpack`; normal Turbopack compilation was
blocked by local subprocess/port permission, even on elevated retry. No project
build script was changed; record default build CI separately.

OPS-006 bounded acceptance: 35 real isolated-PostgreSQL worker-event tests pass
without skips, covering backend-only permissions, leases, concurrency, attempt/
event sequencing, outbox/requeue recovery and terminal transitions. The live API
has CHAT_TURNS_VIA_WORKER=true; worker WORKER_MODE=true. Worker URL and OIDC
audience match; both use the named task-invoker account. API audience defaults to
that worker URL in source. Queue enqueue and invoker act-as bindings name the
runtime service account, and the worker's service policy grants run.invoker only
to the task invoker. Prior deployed outage/long-session execution passed. These
checks complete the requester-amended worker slice, not inherited-project IAM,
hosted checksum reconciliation, a scale certification or historical OPS-005 RCA.

## Live records checkpoint and remaining work

Elena signed in; Rajeev patient `c102f321-a2b6-40e4-95f4-f21390b18e57` has three
active medicines (atorvastatin, lisinopril 20 mg daily, metformin) and one glucose
activity, all without configured reminders. The External Records workspace
loaded 39 pending candidates, four medication candidates; its source/type filters
and separate preview/decision controls work. Read-only Lisinopril preview exposed
an actual defect: imported `Lisinopril 10 mg tablet` did not match local
`Lisinopril`, offering Add rather than side-by-side comparison. Screenshot
`/private/tmp/rec-lisinopril-unmatched-before-fix.png`. Cancelled; no decision,
medication edit or publication. Profile remained unchanged afterward; screenshot
`/private/tmp/rec-unchanged-approved-profile.png`.

Local fix adds a clearly labelled **possible** name match ignoring strength/form
text, never an equivalence claim; ER/IR/salt/combination words are retained. Seven
positive/negative regressions accompany it. Source difference and distinct
recorded RxNorm concepts remain review flags, not automatic reconciliation.
Deployed recheck still required.

Confirmed unlisted products now survive normalization and appear explicitly as
patient-reported testimony in the Symptoms view, without an invented medication
ID or confirmed ADR. Eleven parser tests and a patient-screen test cover malformed,
unknown/declined/legacy inputs and unlisted product display. Automated ADR creation
still requires a recorded medication ID; the unlisted-product review/handoff path
needs completion, so MED-001 is not Done from merely exposing the saved testimony.

Grounded localized display titles now flow into the deterministic chat catalog,
retaining the original filename and falling back without cross-locale invention.
43 focused catalog/chat-service/citation tests pass. Citation title reuse was
already implemented on main and is verified, not rebuilt. Care-plan source-title
reuse and the full correction/retry/withdrawal acceptance remain REC-001 work.

Completed checks: final backend unit/router sweep **3939 passed**; clinician
**643**, patient **834**, worker PostgreSQL **35**. Both portals passed lint,
typecheck and production builds with the supported webpack backend; default
Turbopack remains locally blocked by subprocess-port permissions, not silently
reported passing. Final source mypy passed 278 files. Ruff check/format and diff
whitespace passed on changed Python/files; commit hooks repeated source checks.
Installed only the already-locked local missing `google-cloud-tasks==2.23.0`
with `--no-deps` to collect queue tests; no lockfile change. Fixed logging test
isolation from LOG_FORMAT/CLOUD_RUN_JOB overrides (test only), then its 13 tests
and the broad sweep passed. Expected deprecation warnings remain.

Continue in order:

1. Review the saved implementation diff and default-build CI before merge.
2. Complete REC-001 source-title/retry/correction/withdrawal matrix and REC-002
   all-decision/replay/permission proof; use isolated fixtures rather than changing
   Rajeev's active medicines for an unapproved live test.
3. Complete unlisted product review routing (not automatic ADR/canonical creation)
   and source freshness/normalization under MED-001's accepted boundaries.
4. Finish CLN-001 source/age/freshness/shared-review behavior and CLN-002's
   source-linked cross-domain timeline. Versioned risk modal alone is not closure.
5. Open/review the completion PR with precise pending deploy/secret/acceptance
   notes. No deployment, migration, secret configuration or clinical decision has
   been performed or authorized by this checkpoint.

The `NKDA` absence-of-allergy candidate observed in existing pending source data
is not a positive-allergen assessment. Do not add it to the canonical allergy
list as an allergen merely to exercise a test; review its mapping/decision behavior
in the remaining record lifecycle acceptance.

## Source labels and shared queue follow-up — October 21

Care-plan hydration now includes each linked document's existing grounded
`display_title`, without renaming `file_name`, changing document IDs or rewriting
historical evidence. Clinician review shows the English title plus original
filename in the item list, citation excerpts, source action's accessible name and
linked-document summary. Missing English wording falls back to the original
filename, never an invented translation. File-type icons and protected preview
requests still use the original filename/ID; page navigation is unchanged.

The Patient Upload Review Queue now re-reads authoritative source state every
15 seconds while visible and on focus/visibility return. Background refresh
retains prior rows on failure instead of replacing them with a spinner. Polling
pauses during an open rejection dialog or decision submission; an outstanding
read is invalidated before a decision so it cannot restore a completed row.
Timers/listeners are removed on unmount and old-clinic responses remain ignored.
This is bounded polling, not instantaneous cross-client delivery or a new clinical
approval workflow. Full action-inbox coverage/source freshness remains open.

Follow-up verification: **48 backend care-plan context/evidence-gate tests** and
**38 clinician source-label/care-plan/shared-queue tests** pass. Clinician lint
and typecheck, focused source mypy, Ruff and whitespace checks pass. These counts
are focused follow-up runs, not additions to the earlier full-suite totals.

The requester separately authorized backend notification-secret configuration.
This overrides the earlier checkpoint's no-remote-change statement **only** for
that secret and its runtime binding; it does not authorize a new code image,
worker change, SQL, clinical action or Supabase login-key change. Deployment uses
the currently running immutable image digest, not the mutable `latest` tag.

Authorized configuration completed: Secret Manager
`NOTIFICATION_TOKEN_SIGNING_SECRET`, enabled version **1**, generated directly
into the service without printing or writing the value locally. Secret-level
`roles/secretmanager.secretAccessor` was granted to the existing backend runtime
identity. Backend revision **`mediagent-backend-00176-8zk`** is ready with 100%
traffic and the version-1 reference. Immutable image SHA-256 remains
`57b5e3216793822fd48cf0cd84b6a8263e50b8fac9716d774dc395c594e9f354`.
Timeout 3600s, concurrency 80, maximum 2 instances, CPU settings and service
identity remain unchanged. Public `/health` returned healthy. The deployment
workflow's existing `--update-*` forms preserve this reference on later code
deployments. Supabase login keys, worker and SQL were not changed.

**This prepares configuration; it does not deploy #208's new signing code.**
Independent-root activation and notification read/cursor acceptance must be checked
after the reviewed PR is merged/deployed. NOT-003 remains In progress until then.
