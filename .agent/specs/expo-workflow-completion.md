# Records, medication and clinician-workflow completion

Requested October 21, 2026 (Pacific). Scope: REC-001, REC-002, NOT-003,
OPS-006, MED-001, CLN-001 and CLN-002. This plan is linked from TASKS so future
work does not depend on chat history. Branch: `codex/expo-workflow-completion`.

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
| NOT-003 | Actor/role/purpose/audience-bound 15-minute notification snapshots; currently signed using the Supabase JWT secret | Separate token key/domain, test tampering/cross-purpose/actor/expiry behavior and document rollout. Clinician permanent deletion conflicts with retained review/ADR/MedWatch provenance: requester decision pending. No account deletion or FK weakening. |
| OPS-006 | Durable queue/worker, ordered persisted events, private invoker, recovery/long-session acceptance | Complete bounded permission/configuration/worker tests. Requester decision pending on replacing working sockets with SSE and on large load/cost work; no silent scope removal or unapproved configuration reset. |
| MED-001 | Canonical medication CRUD, conservative candidate matching and clinician-selected updates; RxNorm normalizer exists but no live callers found | Patient-reported unlisted products must remain evidence, not disappear or become approved medication automatically. Add explicit identity/source/conflict review, uncertainty, preserved history. A comprehensive interaction/allergy/duplicate-therapy engine is not already implemented; evidence coverage and clinical-review labeling must be explicit. No model-only assertion that a combination is safe. |
| CLN-001 | Patient Upload Review Queue with approve/reject and exact-document routes; Alerts has broader action items | Requester decision pending: use Alerts as unified work inbox and keep document approval separate, or build a new combined workspace. Preserve each existing authorized action and approval gate, avoid duplicate inbox items/controls. Verify assigned clinic, priority/age/source/freshness and cross-reviewer refresh. |
| CLN-002 | Deterministic threshold-based Risk Radar; adherence/open ADR/recent severity inputs and dashboard explanation; symptom timeline | Add explicit rule version, calculation time/data freshness, reason contributions and a source-linked cross-domain timeline. Unknown/missing data must not mean low risk or missed medication; automation is not a diagnosis. |

## Requested product decisions (not yet approved)

1. OPS-006: retain worker reliability/security; remove SSE rewrite and large
   load/cost exercise from required expo scope, rather than rewriting a working
   transport for its own sake. Existing safety/authorization/backpressure remain.
2. CLN-001: make Alerts the common action inbox, with exact links into the existing
   document, ADR, care-plan and patient review destinations. Keep patient-upload
   approval clearly separate from clinical plan publication.
3. NOT-003: retain accounts referenced by clinical audit history; do not add
   permanent clinician deletion for the expo. Implement token-signing separation.

These recommendations are not implemented scope changes. Record the requester's
decision here and update the original specifications/board together if accepted.

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

Next checkpoint: record requester scope decisions before implementing a new inbox
or changing OPS-006 scope, then execute the agreed synthetic acceptance matrix.
