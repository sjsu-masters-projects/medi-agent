# MediAgent — August–December 2026 Execution Tracker

> **Active plan:** [`specs/pat-005-clinician-approved-today-feed-plan.md`](specs/pat-005-clinician-approved-today-feed-plan.md)
>
> **Baseline date:** 2026-08-18
>
> **Feature freeze:** 2026-12-04
>
> **Primary outcome:** A complete, deployed product prototype using synthetic or de-identified data.

This file is the execution source of truth. The previous semester tracker remains available in Git history at commit `1d06658` and is no longer an accurate measure of product readiness.

## Status rules

- `[ ]` Backlog
- `[/]` In progress
- `[x]` Done and verified
- `[!]` Blocked; the reason and owner must be written beside it

A task is done only when its implementation, authorization, error handling, audit behavior, tests, and user-visible acceptance path are complete. A route, mock, empty agent shell, or UI-only screen is not a finished feature.

## Current release status

**PAT-005 follow-through fixes — 2026-10-03 (ready for review).** Package the fresh
Morgan QA findings with the five-document worker batch: count medication `taken`
events, distinguish future doses, flag medication wording overlaps for review,
and keep document explanations separate from approved instructions. Verify with
focused backend and portal regressions; deployed acceptance remains a separate
post-merge check. No remote reset or migration application is part of this PR.
Verification: full backend `pytest --no-cov -q` passed 1,542 tests (20 opt-in
PostgreSQL tests skipped); `ruff check src scripts`, `ruff format --check src scripts`,
changed-test Ruff/format and `mypy src` passed. Patient `npm run test` passed 112
tests; clinician passed 128. Both portals passed lint, typecheck and
`npm run build -- --webpack`. Default Turbopack builds were blocked by local helper
port permissions, including the permitted retry. Broad test-directory Ruff found
pre-existing lint/format findings outside the changed files; these were not reformatted.
No new migration. Cached explanations are not automatically regenerated. Gender
discoverability, session-renewal diagnosis and barrier-note confirmation remain
separate tracked follow-ups, not completed by this PR.

PR #126 conflict resolution preserves main's global model routing and triage-model
configuration alongside the five-document batch and 1,800-second worker timeout.
The deployment contract test covers both settings; no remote deployment was performed.
Merged-main verification: backend 1,612 passed (20 opt-in PostgreSQL skips), patient
112 passed, clinician 131 passed; backend Ruff/format and both portal lint/typechecks
passed. This supersedes the earlier pre-merge test counts, not deployed acceptance.

| Area | Status | Evidence / risk |
|---|---|---|
| Repository | Main synchronized | Local `main` matches `origin/main`; current tracker verification is recorded on a separate documentation branch |
| Historical work | Needs reconciliation | One remote SMART work branch remains outside `main`; no local stashes or additional worktrees remain |
| Patient portal | Partial | Patients can view existing medications/obligations, documents, explanations, and basic feed/adherence statistics. The Today feed now guards plan-linked tasks by approved/effective plan state and shows plan provenance; live clinician-approved-plan acceptance remains unproven. |
| Clinician portal | Partial | Roster, patient deep dive, document source viewer, extracted-fact review, and Care Plan draft/review surfaces exist; the fresh synthetic approval journey, consolidated action queues, and a longitudinal decision timeline remain incomplete. |
| Backend foundation | Functional foundation | Versioned APIs, auth, RLS, audit, and worker services exist; several product lifecycles are not connected end to end |
| Records ingestion | Demonstration-ready candidate pipeline | Secure document intake, evidence-backed candidates, TIFF previews, and retryable explanation lifecycle work; clinician review, reconciliation, and downstream approved-action projection remain incomplete |
| Chat and triage | Partial | Deterministic emergency handling, the Care Coordinator, and WebSocket subprotocol authentication are live; document-focused chat, durable safety-rule audit, and terminal turn recovery remain open |
| Document intelligence | Demonstration-ready | Synthetic PDF, scanned-Spanish, and multi-frame TIFF paths completed with evidence-backed candidates, private preview, expiry, and cross-user denial checks; the five-minute Job trigger is enabled for the master's-project demonstration |
| Pharmacovigilance | Partial | Deterministic Naranjo scoring, auditable evidence, and an assigned-clinician read-only ADR queue work; clinician decisions, evidence requests, reassessment, and MedWatch drafting remain incomplete |
| Scheduling and communication | Partial | Document ingestion is scheduled; appointments, approved clinical messaging, notification delivery/retry, and care-gap closure are incomplete |
| Interoperability | Functional sandbox foundation | A deployed, EHR-initiated SMART Health IT R4 sandbox flow imports synthetic records as provenance-backed pending candidates; conformance and reconciliation remain |
| MCP/A2A | Partial | Existing MCP is custom. The A2A task service and retry worker are implemented and the worker starts with the application; `/.well-known/agent-card.json` and the delegation flow are still absent |
| CI | Green baseline; Acquit enforcement evidence in progress | Required CI is green on `main`; Acquit 0.3.0 remains a non-blocking canary until 10 selective observations are collected |
| Dependency security | Verified — PR #117 merged/deployed | urllib3 2.8.0 minimum and both locks merged at `e81c9c1`; main CI `36933661245` and deployment `36933661124` succeeded. Local audit found no known vulnerabilities. |
| Demo data | Functional baseline | Canonical fictional fixture and live patient/clinician isolation checks exist; the fresh end-to-end care-plan scenario is PAT-005 work |

**Tracker reconciliation — 2026-09-26.** Every named primary task was reviewed for status
consistency. Existing completion marks were preserved only where the tracker carries implementation
or verification evidence; unverified work remains open. This update separates the deployed
document worker's demonstration acceptance from the independently incomplete document-chat
product work, records the enabled five-minute scheduler, and selects the clinician-approved
care-plan/Today-feed journey as the next vertical slice.

## Product stage and functional gap map — 2026-09-26

**Current stage:** a deployed, synthetic-data prototype with secure document ingestion and
foundational patient/clinician surfaces. The controlled care-plan implementation now spans draft,
clinician review, approval, projection, patient completion/barrier, and clinician display, but the
fresh synthetic end-to-end proof is still blocked on diagnosing and retrying the observed draft
failure. It must not be presented as a completed closed-loop care product until that proof passes.

| Product journey | Demonstrably working now | Functional gap | Tracked work |
| --- | --- | --- | --- |
| Access and clinic boundaries | Synthetic patient/clinician login, assigned-care-team access, unassigned clinician denial, denial audit, private document URLs, and WebSocket subprotocol authentication | Broader release security qualification remains | SEC-001, QUA-001 |
| Document intake and understanding | PDF/image/TIFF ingestion, source provenance, evidence-backed pending candidates, private derived previews, plain-language explanation and retry lifecycle; clinician extracted-facts review | Fresh synthetic evidence-to-approved-plan proof and authorized reconciliation-to-action journey remain incomplete | REC-001, PAT-005 |
| Patient conversation and safety | Care Coordinator, persistence foundation, deterministic emergency response in English/Spanish, and immediate typing feedback | Document-focused conversation lifecycle, durable safety-audit persistence, terminal turn recovery, and a patient-confirmed guided symptom-report flow remain open | PAT-001, PAT-004, PAT-002-B, SAFE-002 |
| Today feed and adherence | Deterministic medication/obligation feed, adherence statistics, completion/barrier capture, and plan-linked approved/effective-task guard | No live proof of the clinician-approved item through patient and clinician follow-up | PAT-002, PAT-005 |
| Clinician action workspace | Roster, patient detail, source preview, extracted-facts review, care-plan draft/review, and basic document status | No consolidated queue, explainable risk, or unified timeline; live care-plan acceptance remains incomplete | PAT-005, CLN-001, CLN-002 |
| Care closure | Document Job runs every five minutes; manual summary retry exists | No approved clinical messaging, appointment completion, notifications/retry, or care-gap follow-up loop | SCH-001, COM-001 |
| Medication and safety workflow | Provenance model, candidate-only import boundary, DailyMed/RxNorm foundation, deterministic Naranjo assistance, and assigned-clinician ADR evidence queue | No completed multi-source reconciliation, patient-confirmed symptom-report flow, clinician ADR decision/reassessment flow, or MedWatch draft lifecycle | MED-001, MED-002, PAT-002-B/C, PV-001, PV-002 |
| Interoperability and continuity | Deployed SMART-on-FHIR sandbox import with candidate provenance | Export, CDS Hooks, official MCP/A2A, multi-provider timeline, and handoff remain incomplete | INT-002, STD-001–003, CON-001 |
| Bilingual and voice experience | `en-US`/`es-MX` safety-floor coverage and localized fallback exist | End-to-end language parity, clinician content review, and text-first voice lifecycle are incomplete | PAT-003, VOI-001 |

**Selected next product outcome:** PAT-005 proves the smallest meaningful closed loop with a
fresh fictional patient: clinician-authored source document → evidence-backed candidate →
assigned clinician approval → deterministic Today item → patient completion or barrier →
clinician-visible follow-up. The model may assist extraction and drafting but never publishes a
patient-facing clinical instruction itself.

### Product sequence from here

1. **Now — PAT-005, the controlled Today-feed loop.** Prove that an approved clinician
   instruction can become a safe, explainable daily item and return a patient response to the
   care team. This is the first feature that joins the working document pipeline to a patient
   outcome.
2. **After PAT-005 live proof — finish the patient companion loop.** Complete durable chat-turn
   recovery and the explicit symptom path: guided chat intake → patient confirmation of a
   structured report → patient timeline and clinician-visible detail (PAT-001-A, PAT-002-B,
   PAT-002-C). Document-focused conversations, adherence/barrier acceptance, and English/Spanish
   coverage continue alongside that work (PAT-002-A through PAT-004 and SAFE-002). This makes the
   patient response usable rather than a one-off demo interaction.
3. **Then — make clinician work actionable.** Consolidate document, medication, symptom,
   adherence, and proposed-action review with evidence and an explainable timeline (CLN-001,
   CLN-002, MED-001, and MED-002). Do not expand autonomous AI behavior to compensate for a
   missing clinical review surface.
4. **After the confirmed symptom-report model — add pharmacovigilance and other closure
   channels.** Clinician ADR/Naranjo review and the editable MedWatch export draft (PV-001,
   PV-002) consume the confirmed report; neither can begin as an autonomous report or submission.
   Appointment and approved-message workflows, notification recovery, voice, multi-provider
   continuity, FHIR export/CDS Hooks, and protocol conformance remain valuable later slices; they
   should extend the proven loop rather than precede it.

For the master's-project demonstration, prioritize this sequence over production-scale document
throughput work. The five-minute document Job is enabled to support the controlled scenario; it
does not turn a document-processing component into the product outcome.

## Work coordination board

Use this board before claiming work. It is the short operational view; the linked task section
remains the source for detailed requirements and acceptance criteria. A teammate may take a
**Ready** item without waiting for another task, but must create a branch, name themselves in the
task section, and update this row. Do not add work to an item marked **Claimed** unless its owner
explicitly asks for help. A **Blocked** row names the exact unblocker so it is not mistaken for
available work.

### Current delivery queue

**Current sprint goal:** turn the versioned clinician-approved care-plan implementation into one
recorded `PAT-005-SYN-001` journey. The evidence must run from upload through clinician approval,
patient completion or barrier, and clinician follow-up. A successful UI screen alone is not
completion; the proof needs the source, approval, projections, and audit evidence described in
PAT-005.

| Work item | State | Owner / working branch | Next concrete result | Dependency or handoff |
| --- | --- | --- | --- | --- |
| `PAT-005-A` — safe draft-failure diagnostics | **Done** | Rajeev — PR #114 | Local model preflight and credential-free CI contract tests now separate deployment validation from live provider calls. | The corrected backend and ingestion Job deployed on 2026-09-30; Maya's draft is visible. This closes the original generation-failure investigation, not PAT-005 acceptance. |
| `PAT-005-B` — verify the corrected draft request | **Done** | Rajeev + assigned synthetic clinician | Maya's existing synthetic evidence produced a version-1 draft shown in the clinician Care Plan tab on 2026-09-30. | Draft generation is demonstrated. Publication and the fresh scenario remain `PAT-005-C`; do not treat Maya's Spanish draft as safe for her `en-US` preference. |
| `PAT-005-C` — fresh `PAT-005-SYN-001` proof | **Blocked** | Rajeev + patient/clinician test accounts | Upload the catalogued synthetic documents, verify one quiet-window draft, resolve the planned conflict, approve, then record Today, completion/barrier, clinician follow-up, and audit evidence. | Existing Maya completion/barrier persistence is verified after PR #122. Fresh-patient proof, next-publication continuity, exact Today preview and unassigned-account denial/audit proof remain gates; Maya's already-approved V2 does not substitute for them. |
| `PAT-005-D` — safe plan revision review | **Done** | Rajeev — PR #115 | Active/proposed comparison, linked source documents, citation display, and unsaved-edit guard deployed; Maya's draft loads on 2026-09-30. | This is a review aid only. Exact Today preview, locale-safe publication, medication matching, and live v1→v2 proof remain `PAT-005-E/C` gates. |
| `PAT-005-E` — approval safety and citation clarity | **Done** | Rajeev — PR #116 | Migration 042 applied; live Maya review verified wording edits reset attestation, save/reload retained edits, explicit medication decisions blocked/enabled approval, and approved V1 became immutable. | Synthetic English wording was manually reviewed; this is not automatic translation. Full fresh scenario, rollback and denial proof remain C. |
| `PAT-005-F` — live QA and closed-loop defect repair | **Claimed** | Rajeev — `codex/care-plan-acceptance-checks` | Verify unchanged-activity continuity across a subsequent revision, then record the fresh scenario. | Browser access restored: V2 monitoring completion and a new walking barrier survive reload; clinician sees the correct activity and synthetic note. Walking reminder Mon/Wed/Fri 08:00 America/Los_Angeles also survives reload. These checks do not prove continuity across publication. Legacy PRN/unknown cadence, exact preview, full barrier-category and denial/audit acceptance remain open. Blocks C. |
| `PAT-005-G` — incomplete-evidence draft persistence | **Claimed** | Rajeev — `codex/care-plan-oversized-evidence` | Handle oversized source fields as cited, non-confirmable review blockers rather than failing the whole generation batch. | PR #119 merged/deployed and migration 043 applied. Maya's retry exposed a 338-character title against the 300-character draft limit. C still waits for the repaired deployed V2/reload/history proof. No additional migration planned. |
| `PAT-005-H` — patient reminder usability | **Done** | Rajeev — PR #124 | Compact schedule summaries, one editor with cancel, blank new times, patient-selected weekly days, contextual Today setup, and advanced timezone settings. | PR #124 backend deployment `37052584390` and frontend CI `37052584538` succeeded. Live QA on 2026-10-02 verified Mon/Wed/Fri 08:00, cadence-invalid Save disabled, Cancel preserved settings, and no routine reminder controls for albuterol/after-walking monitoring. No clinical timing was invented. Full fresh-scenario proof remains C. |
| `PAT-005-K` — proposed Today preview | **Claimed** | Rajeev — `codex/care-plan-publication-preview` | Assigned-clinician read-only preview using the Today renderer, saved draft, current canonical records, patient-local date and reminders. | Implemented locally from main `1731fdf`; backend 1,536 passed, 85.01% coverage (20 opt-in PostgreSQL tests skipped); clinician 127 passed; full Python Ruff/format/mypy and clinician lint/typecheck passed. Clinician webpack production build passed; Turbopack was blocked by local helper-port permissions. Browser access restored: approved V2, seven Today activities and named clinician barrier are visible. The new preview still needs deployed UI proof; it never publishes or guarantees unchanged state at later approval. No migration. |
| `AUTH-001` — resilient portal session renewal | **Ready** | Portal + backend lanes — unassigned | Diagnose the reported spontaneous logout; distinguish terminal refresh rejection from transient failure, coordinate refresh callers/rotated tokens, and recover expired authenticated requests before redirecting. | Refresh exists in both portals, but hook/storage catch-all paths clear sessions on any failure; base API clients redirect on authenticated 401 without renewal; backend refresh maps all provider exceptions to invalid-token authentication errors. Recent Cloud Run refresh requests succeeded (one took 36 seconds); no HTTP refresh failure found in the 24-hour check. The reported logout's exact cause is not yet reproduced. Can run parallel to K; do not relax MFA/session policy or replay clinical writes automatically. Verify transient outage, returning/sleeping tab, expiry, concurrent refresh, real revocation and role/MFA preservation. |
| `PAT-PROFILE-001` — optional gender discoverability | **Ready** | Patient-portal lane — next QA-fix PR | Always show the gender row in the read-only profile; display "Not provided" when unset. Remove duplicate "Prefer not to say" choices in onboarding and profile editing. | Reported during Morgan Ellis fresh-scenario preparation on 2026-10-02. Gender exists in onboarding/profile editing, not initial signup. Keep unset distinct from an explicit prefer-not-to-say response; verify selection, save/reload and validation with regression tests. No new schema or required signup field. Morgan's fixture has no gender; the requester chose female for this synthetic run and will set it manually. Independent of care-plan generation. |
| `PAT-005-I` — evidence applicability and overlap review | **Done** | Rajeev — PR #121 | Migration 044 applied and deployed controls verified: imported exclusions persist, overlap review soft-removes proposals without deleting evidence, and unresolved overlap blocks publication. | Synthetic Maya V2 approved on 2026-10-02 with four retained items and 49 excluded proposals. Fresh-scenario/denial proof remains C; review and continuity defects are J. |
| `PAT-005-J` — review persistence and revision continuity | **Claimed** | Rajeev — PR #122 / `codex/care-plan-review-follow-up` | Save incomplete medication reconciliation as a publication blocker; retain unchanged conflict resolutions; serialize clinician barrier detail; preserve unchanged activity identities across approval. Include clinician adherence usability: response-based metrics, unknown-day gaps, daily counts, named barriers, and current activity context. | Live QA found all four defects. V2 has one Metformin and new monitoring; monitoring completion survives reload. Migration 045 is required for future unchanged-activity continuity, not retroactive repair of V2. Deploy and repeat clinician barrier/revision checks before closing F/C. Do not treat recorded-response counts as scheduled doses or infer ADRs from patient barriers. |
| `PAT-002-B` — guided chat symptom intake | **Sequenced** | Patient + backend lanes — unassigned | Deliver an evidence-aware, deterministic-safe chat interview from an approved question library; require the patient to confirm the resulting structured report before it becomes clinician-visible. | Starts after `PAT-005-C` live proof. Retrieve only authorized grounded context; do not make document facts look like patient statements or autonomously diagnose, create a clinician task, decide an ADR, or start MedWatch. Blocks `PAT-002-C` and `PV-001`. |
| `PAT-002-C` — symptom timeline and clinician report detail | **Sequenced** | Patient + clinician portal lanes — unassigned | Show each confirmed report in the patient's timeline and an authorized clinician detail view with clearly separated patient answers, document-grounded context, and clinician decisions. | Starts after `PAT-002-B` establishes the confirmed-report contract. Blocks `PV-001`; preserve patient/clinic assignment isolation, source citations, and audit linkage. |
| `PAT-001-A` — durable chat-turn recovery | **Ready** | Patient + backend lanes — unassigned | Persist a per-turn state and bounded outcome so a provider stall, timeout, or Cloud Run revision replacement cannot leave a saved message permanently typing. | Retry the existing saved message without creating a duplicate; log only safe outcome, duration, and failure category. |
| `PAT-002-A` — adherence/barrier acceptance evidence | **Sequenced** | Patient + clinician portal lanes | Exercise each patient barrier category and completion against an approved effective plan item; verify clinician display and assignment denial. | Runs with `PAT-005-C`; do not create a parallel adherence data model or bypass the plan projection. |
| `PAT-004-A` — document-focused conversation | **Claimed** | Rajeev — `codex/pat-004-chat-document-catalog` | Answer clear document-catalog questions from the patient's authorized portal metadata and show typing immediately after send. | Keep catalog answers deterministic, metadata-only, and separate from selected-document interpretation. This is independent of PAT-005. |
| `AI-003-WS1-B` — central background-workload routing | **Done** | Rajeev — PR #112 | Active document extraction, document explanation, and evidence-only care-plan classification use the ADK registry executor with route-owned model, budget, thinking ceiling, kill switch, fallback rule, and telemetry path. | Merged infrastructure only; the care-plan structured-response repair and deployed proof remain `PAT-005-A/B`. |
| `CI-001-A` — selective-test evidence | **Ready** | CI-maintenance lane — unassigned | Collect one eligible Acquit selective-run observation and publish selected-test/full-suite evidence. | Keep Acquit in canary mode; enforcement waits for ten safe observations. |
| `SAFE-002-A` — language-gap safety rules | **Blocked** | Clinical reviewer + safety owner | Approve exact English and Mexican-Spanish wording/coverage for inflected self-harm, anaphylaxis, and stroke phrases; then add deterministic tests and rules. | Engineering must not invent clinical escalation wording. Clinical sign-off is the unblocker. |
| `CLN-001-A` — consolidated clinician queue | **Sequenced** | Clinician-portal lane — unassigned | Design the queue around demonstrated PAT-005 approval, adherence, and barrier artifacts. | Wait for `PAT-005-C`; that proof defines which records the queue must render. |
| `MED-001/002-A` — reconciliation scope | **Sequenced** | Platform + clinician-portal lanes — unassigned | Use PAT-005's medication-conflict scenario to scope reviewed candidate-versus-local comparison. | Reuse PAT-005 evidence/approval boundaries; do not duplicate a competing clinical-decision lifecycle. |
| `PV-001` — clinician ADR/Naranjo review | **Sequenced** | Ganesh — pharmacovigilance + clinician lanes | Review a confirmed symptom report, request missing information, and provide deterministic Naranjo assistance separate from clinician judgment. | Starts after `PAT-002-C`. It must not infer an ADR report from raw chat or submit anything externally. Blocks `PV-002`. |
| `PV-002` — clinician-approved MedWatch draft/export | **Sequenced** | Jeevan — clinician portal + pharmacovigilance lanes | Produce an editable, evidence-linked MedWatch-compatible draft from patient-confirmed and clinician-approved facts; export it only after clinician/pharmacist approval. | Starts after `PV-001`; export is not FDA submission. |
| `COM-001-A` — clinician message send + inbox | **Claimed** | Jeevan Kurian — `feature/com-001-clinician-messages` | Backend list endpoints, clinician inbox page, and compose form on patient deep-dive. Tests pass. | Patient-to-clinician direction and outbound approval gate remain as separate slices. |

**State meanings:** **Claimed** has one active owner and branch; **Ready** is safe to start in a
separate branch; **Blocked** needs the stated external decision or evidence; **Sequenced** is
intentionally deferred until its named predecessor finishes.

**PAT-005-F verification — 2026-10-02:** PR #122 merge `5ede2bd` passed main CI
(`37042676826`), frontend CI (`37042676824`), and backend/ingestion deployment
(`37042676735`). Migration 045 application was confirmed by the requester. On
`codex/care-plan-acceptance-checks`, the focused backend command
`PYTHONPATH=src .venv/bin/pytest tests/unit/services/test_care_plan_review_context.py tests/unit/services/test_care_plan_reconciliation.py tests/integration/routers/test_clinician_api.py --no-cov -q`
passed 61 tests. Clinician command
`npm test -- src/__tests__/patient-adherence-panel.test.tsx src/__tests__/patient-deep-dive.test.tsx`
passed 34 tests, including all six barrier labels, target attribution, literal-note rendering,
and reporting-timezone context; typecheck, changed-test ESLint and Prettier checks passed.
The opt-in local PostgreSQL rerun could not initialize a cluster: macOS shared-memory
allocation failed (`shmget`, no space available), before application assertions ran.
Do not count those 20 setup errors as passed contract tests. Live browser attachment also
timed out before page inspection. Remaining acceptance requires restored browser access and
a successful disposable PostgreSQL rerun; no remote data or configuration was changed.

**PAT-005-F live follow-up — 2026-10-02:** Browser access was subsequently restored.
The patient submitted an `other` barrier on approved V2's walking activity with the note
“Synthetic QA only: unable to complete the walking activity during this test session.”
After patient reload, Today retained `Barrier reported` and the existing monitoring completion
(1/7). Clinician refresh displayed the new report against “Walk for 20 minutes”, retained the
older V1 scheduling barrier separately, and showed 2 completed / 4 recorded responses (50%).
The patient and clinician percentages have different denominators; neither establishes
scheduled-dose adherence. ADR flag count stayed at the pre-test value of 2.
The synthetic walking reminder was saved for Monday/Wednesday/Friday at 08:00 in
America/Los_Angeles and retained those exact settings after reload. No medication schedule
or clinical instruction was changed. Publication-continuity proof remains open: no V3 was
generated or approved in this check. Reminder QA also confirmed that legacy “as recorded”
albuterol and the after-walking monitoring item still offer routine clock-time controls;
`PAT-005-H` must resolve unknown/PRN/event semantics without inferring clinical timing.
Full regression rerun: backend `PYTHONPATH=src .venv/bin/pytest tests/ -q --cov-report=term:skip-covered`
passed 1,466 tests with 84.55% coverage (20 opt-in PostgreSQL tests skipped); clinician
`npm test` passed 122 tests; patient `npm test` passed 103 tests. Both portals'
`npm run typecheck` passed. This does not supersede the unsuccessful opt-in PostgreSQL rerun.

**PAT-005-I local verification — 2026-10-02:** Backend `PYTHONPATH=src .venv/bin/pytest tests/ -q
--cov-report=term:skip-covered`: 1,456 passed, 84.53% coverage; 13 opt-in PostgreSQL cases
verified separately with `CARE_PLAN_TEST_POSTGRES=1` against a disposable local cluster.
Ruff, format, mypy and migration parsing passed. Clinician lint/typecheck, 111 Vitest cases
and `npm run build -- --webpack` passed. One unrelated review-queue test timed out in an
intermediate run; the complete rerun passed. Live verification is still pending migration,
merge/deployment and clinician review; no remote writes or automatic cleanup were performed.

**PAT-005-C restart and batching — 2026-10-02:** Claimed by Rajeev on
`codex/document-qa-batching`. The requester confirmed a scoped reset of Morgan's
three test-document records and generated candidates/drafts, preserving her account,
profile and care-team link. The normal application deletion returned HTTP 500:
`withdraw_unapplied_document_source` attempted to delete a fact still referenced by
`care_plan_items_source_fact_id_fkey`. The transaction rolled back; no document was
removed. Direct database access is not configured in this agent shell. A reviewed,
guarded reset is still required; do not upload the replacement bundle into the old draft.
Revised local PDFs contain one consistent established Metformin 500 mg twice-daily
regimen, no 1000 mg discrepancy and no application-workflow instructions. Missing
allergies/laboratory details remain explicitly undocumented, not inferred normal.
Deployment configuration changes the maximum document batch from one to five and
task timeout from 300 to 1,800 seconds, retaining sequential processing, isolated
failures and atomic claims. This change is local, not deployed; five-document live
latency and restart acceptance remain unverified. No remote SQL or configuration
change was performed. Verification: focused worker pytest passed 8 tests, including
five-claim failure isolation and the deployment batch/timeout contract; changed-test
Ruff/format/mypy and `git diff --check` passed. The three revised PDFs rendered as
four visually inspected pages (2 + 1 + 1); no clipping or overflow was found.

**Morgan reset prerequisite verification — 2026-10-03:** Both live portal sessions
were accessible. Morgan's Today showed zero tasks; the original eight-item draft
remained unpublished, with overlap and review blockers disabling publication.
The clinician-only reconciliation instruction was incorrectly proposed as an
`other` patient task; correcting the fixture alone does not resolve this extraction
boundary defect. Supabase SQL Editor confirmed all three documents completed,
their summaries ready, ten facts pending/unreconciled, and an unapproved draft with
no recommendation or human audit actor. A narrowly guarded operator transaction
removed the draft dependencies successfully in a rollback-only dry run, preserving
the patient, care-team link, documents and facts. A disposable local PostgreSQL
check could not initialize because the host exhausted shared-memory capacity;
no system setting was changed. Permanent reset and replacement uploads remain
pending; this is not end-to-end completion.

**Morgan scoped reset and revised uploads — 2026-10-03:** Requester confirmed
permanent removal immediately before execution. The guarded transaction committed
removal of Morgan's one unapproved draft, eight items, generated audit event and
completed request. All three original documents were then deleted successfully
through the patient app's normal Storage/API path. SQL and the empty Records UI
verified zero remaining documents, facts and plan versions, with the patient and
one care-team link preserved. The corrected discharge was uploaded by the patient
at `17:04:53Z`; the corrected medication order (Prescription) and care-transition
note were uploaded by the clinician at `17:07:56Z` and `17:08:25Z`. Exactly three
new IDs persisted with correct attribution. The discharge completed extraction
and explanation; the remaining two were pending at the first status check.
The new patient explanation still uses imperative medication wording before plan
approval, so the candidate-versus-approved explanation boundary remains a defect.
No plan was approved and no batch configuration was deployed during this reset.

**Morgan revised extraction verification — 2026-10-03:** All three replacement
documents reached `parse_status=completed` and `summary_status=ready`; the patient
Records surface showed three stored records and three available explanations.
Twelve pending-review facts preserve separate evidence across the three sources:
three condition, three medication and six obligation candidates. Medication
evidence consistently states 500 mg twice daily with meals; equivalent wording
and source-level repetition still require draft reconciliation, not automatic
publication. The protected follow-up PDF rendered correctly. Its explanation
incorrectly calls unreviewed information "your plan" and gives direct instructions,
confirming the explanation-boundary defect independently of the old discrepancy
fixture. The generation request was pending with zero attempts and no failure;
the final evidence timestamp was `17:17:08Z`, so the five-minute quiet window
had not expired at the `17:21:22Z` check. Worker tests were rerun: eight passed.
Publication and patient/clinician follow-through remain unverified.

**Morgan revised closed-loop browser run — 2026-10-03:** Scheduled generation
completed normally by `17:25:54Z`, producing nine draft proposals from the three
replacement sources. Whole-plan publication and Today preview were disabled
until review. Overlap selection staged duplicate removals; the medication-name
variant `Metformin 500 mg tablet` was not grouped with `Metformin` and required
explicit removal. Five proposals were removed with sources retained. The four
retained instructions were source-checked, language-reviewed, saved and previewed
through the clinician UI. Synthetic approval at `17:29:22Z` persisted one approved
version, one medication, three activities and three audit events. Patient Today
showed exactly four approved activities, matching the saved preview before reminders.
The twice-daily medication schedule saved `08:00` and `18:00` on all seven days in
`America/Los_Angeles` and survived reload; Today split the two scheduled doses.
Marking the morning dose taken persisted a `taken` event at `17:32:40Z` for
`15:00Z` (08:00 local), left the evening dose uncompleted, and showed 1/5 (20%).
An access barrier on glucose monitoring persisted a skipped response at
`17:33:26Z` and appeared in clinician follow-up. Selecting a predefined barrier
submits immediately; the attempted subsequent note was not persisted.

Remaining live defects: clinician completion reports 0/2 despite the persisted
medication `taken` response (`clinician_service.py` counts only `completed`);
the future 18:00 dose says `Due now` during the morning; explicit routine wording
(`Each day before breakfast`, named weekly days, breakfast/dinner) is classified
as unknown cadence and blocks routine reminders; medication-name variants can
escape overlap grouping; unreviewed explanations imply approved treatment; the
approved-plan UI still displays a medication-decision warning. Earlier unknown
allergy and clinician-only extraction defects remain open. This proves a fresh
synthetic happy-path loop, not complete acceptance or clinical readiness. No new
deployment, migration, PR merge or notification-delivery claim was made. The
five-document batching change remains local with eight passing worker tests.

**PAT-005-C fresh Morgan run — 2026-10-02 (in progress):** PR #125 merge
`0a7b302` passed backend deployment `37057321126`, frontend CI `37057321114`,
and CI `37057321111`. The synthetic Morgan Ellis account was verified in both
authenticated portals, linked to Elena Park, with female gender, `en-US`, UTC,
zero documents, medications, obligations, and no approved plan. The patient
uploaded the two-page synthetic discharge/after-visit PDF; the clinician uploaded
the medication-order PDF as Prescription and the medication-discrepancy PDF as
Clinical Note. All three persisted with correct uploader attribution. The
discharge parsed, five pending candidates were visible with source-page evidence,
and the protected two-page viewer rendered. Today remained empty before approval.
The remaining documents and quiet-window generation are still pending; publication,
preview, completion/barriers, revision continuity, and denial/audit are not yet proven.
The replacement bundle is a local synthetic variant, not the unchanged catalogued
manifest: discharge SHA-256 `ed9bf955c39e4b79bc0a07ed28b144d9cfa33a1e495463fe418062df3361234b`,
order `d8ada1314f702fb35ea7508b48aeb9fd88ecaeb40062bb94fc58b7be239a1366`,
discrepancy `ee7041327bd4047c2e6f934283801aeeeeb1359c6e25bdd65569d88099c3902a`.
Two live defects require follow-up: an empty allergy list renders as `NKDA` rather
than unknown/not documented; the unreviewed document explanation says "your current
care plan" and directs medication taking despite unresolved source discrepancy.
Do not treat that explanation as clinician-approved treatment or as acceptance success.

### Claim and handoff rules

**Consolidated F/H delivery — 2026-10-02:** The current acceptance branch implements
compact reminder summaries, a single open editor with cancel, blank new times and patient-selected
weekly days, advanced timezone settings, and save-error preservation. Existing schedule timezones
are not silently changed with the profile. Routine PRN/event/unknown schedules are rejected;
Today and notification dispatch ignore unsafe or cadence-mismatched legacy schedules, and inactive
targets do not receive these reminders. Unscheduled cards say `Available`, not `Due now`.
No schema migration, remote cleanup, deployment or clinical instruction change is included.
Verification: backend full suite passed 1,500 tests (20 opt-in PostgreSQL cases skipped),
84.80% coverage; changed Python Ruff/mypy passed. Patient lint/typecheck/build passed;
110 full patient tests and seven focused reminder/card cases passed. Clinician changed-test ESLint,
typecheck and nine adherence-panel cases passed. Existing live Maya V2 is still approved with
four retained items, four active medications and two pre-existing ADR flags.
This branch's new UI is not deployed or live-verified. Exact Today preview, fresh-scenario
denial/audit proof and a subsequent approval's identity/reminder/adherence continuity remain
explicitly open; do not mark PAT-005 complete or treat the 20 skipped database tests as passing.

1. Before editing, move the row to **Claimed**, add the owner and branch, and link the detailed
   task section that supplies acceptance criteria.
2. A PR may cover one row plus its direct verification/docs update. Split unrelated changes into
   another branch so parallel work does not create merge conflicts.
3. On handoff, replace “next concrete result” with the exact verification command, screenshot,
   synthetic fixture, or deployment evidence needed by the next owner.
4. Only mark a row **Done** after the detailed task's authorization, error, audit, tests, and
   visible acceptance path are all complete. Otherwise leave it **Claimed** or **Blocked** with
   the reason.

## Foundational and CI maintenance

### REV-001 — Restore a trustworthy green CI baseline

**Status:** `[/]` In progress

**Priority:** P0

**Milestone:** Revival Gate

**Owner:** Integration owner; assign a team member before implementation PR

**Why first:** No feature work can be measured safely while the primary backend test workflow hangs and dependency state is nondeterministic.

- [x] Reproduce the backend CI hang: a stale voice-websocket test waited forever for a retired streaming-transcript event.
- [x] Record the current baseline: 684 tests pass with coverage in 15.42–27.34 seconds across local runs; the prior websocket wait was the observed long-running path.
- [x] Prevent the test process from inheriting live Sentry, Deepgram, or retry-worker configuration from the repository `.env`.
- [x] Bound each test at 30 seconds, the pytest session at 20 minutes, and the GitHub backend-test job at 25 minutes.
- [x] Split backend tests into four bounded CI shards that run in parallel, retain a separate full-suite coverage gate, and publish JUnit artifacts on success or failure.
- [x] Add lock-keyed Python, uv, and npm dependency caching while verifying generated Python locks and installing JavaScript with `npm ci`.
- [x] Integrate Acquit 0.1.2 in fail-closed PR canary mode with explicit monorepo import roots.
- [x] Reproduce and document Acquit 0.1.1's unsafe nested-`src` selection; verify the published 0.1.2 fix against the minimal reproduction and historical MediAgent commit `089303d`.
- [/] Validate Acquit across at least 10 selective PRs with zero canary alarms. One of ten required selective observations is complete.
- [x] Verify Acquit 0.1.2 ships regression coverage for nested `backend/src` discovery, replay safety, and release-version synchronization.
- [ ] Promote Acquit from `canary` to `enforce` only after the validation gate passes.
- [x] Create deterministic Python and JavaScript lock/install paths.
- [x] Resolve all critical dependency vulnerabilities.
- [x] Triage high-severity findings: upgrade affected JavaScript packages, replace `python-jose`/unfixable `ecdsa` with PyJWT and maintained cryptography, and retain no exceptions.
- [x] Require backend Ruff, mypy, pytest, frontend lint, typecheck, tests, builds, PostgreSQL migration syntax validation, and secret scanning.
- [x] Publish CI duration and failure diagnostics in the workflow summary.

**Acceptance criteria**

- [x] A clean clone installs reproducibly using documented commands.
- [x] Full required CI passes on `main` three consecutive times.
- [x] Full CI completes in 20 minutes or less.
- [x] No critical dependency vulnerability remains.
- [x] The current backend suite completes with live Sentry and Deepgram initialization disabled at test startup.
- [x] Per-test, pytest-session, and workflow timeouts identify the responsible test or step instead of waiting indefinitely.

**Verification evidence — 2026-08-19**

- Python 3.12 clean environment: exact development lock installed successfully; Ruff and mypy passed; 684 tests passed with 81.71% coverage in 16.06 seconds.
- Python lock regeneration is deterministic: both lockfile SHA-256 values remained identical after recompilation with uv 0.9.24.
- `pip-audit` 2.10.1 found zero known vulnerabilities in the exact development lock.
- A generated ES256 token passed real PyJWT/JWK signature, audience, and issuer verification after the `python-jose` replacement.
- Fresh `npm ci` completed from the root, patient, and clinician lockfiles; each install and follow-up audit found zero vulnerabilities.
- Patient portal: ESLint completed with zero errors, 74 tests passed, and the Next 16.3.1 production build passed.
- Clinician portal: ESLint passed, 66 tests passed, and the Next 16.3.1 production build passed.
- The local sandbox blocks Turbopack's internal build port, so production-build verification used Next's webpack builder; the ordinary CI build command remains unchanged for GitHub runners.
- The parallel backend shards cover 158 router tests, 66 integration workflow tests, 241 unit-foundation tests, and 219 service tests; the full coverage gate passed all 684 tests in 14.64 seconds at 81.80% coverage.
- All 17 SQL migrations passed filename/order continuity and PostgreSQL syntax parsing with pglast 8.4.
- CI now uploads JUnit failure evidence, includes a required-check and duration summary, and runs TruffleHog 3.97.0 on each GitHub change. GitHub Actions run 32280310908 passed every required gate in 5m 46s; the three green `main` runs remain pending a reviewed merge.
- GitHub Actions confirmed the third green main observation on 2026-08-20: the restored baseline succeeded twice (run 32283434650, attempts 1 and 2) and the next merged main change succeeded (run 32407010020).
- Acquit remains in canary mode. PR #64 ran the full backend suite after CI, dependency, and test-configuration changes; PR #65 safely selected zero of 58 backend test files for a patient-portal-only change; PR #66 ran the full suite after workflow and resource changes. This is one selective observation, not the ten required before enforcement.
- Acquit audit, 2026-08-29: PRs #64–#78 all completed the Acquit 0.1.3 canary job successfully. PR #65 is the single verified selective observation: all 58 backend test files were proven unaffected and safely skipped. The other 14 PRs correctly ran the full suite because they changed backend code, migrations, dependency/workflow/configuration files, or reached the full test graph. No canary job failed or reported an unsafe selection; nine additional selective observations are still required before `enforce` is considered.
- Acquit 0.3.0, 2026-09-27: upgraded the canary and declared three verified standalone backend commands as `isolated_entrypoints`. Local selection accepted all three declarations with no R019 or R008 finding. This PR still runs the full suite because it changes a migration and dependency configuration; it does not count as another selective observation.

### CI-001 — Prove and enable selective backend test execution

**Status:** `[ ]` Backlog

**Priority:** P2

**Owner:** Unassigned; suitable bounded CI-maintenance task

**Goal:** Turn Acquit's fail-closed PR analysis into a measured reduction in redundant
backend test work without weakening the full-suite safety gate.

- [ ] Keep Acquit in `canary` mode and record nine additional eligible selective PR
  observations, including the report result, selected test files, and full-suite outcome.
- [ ] Classify expected run-all changes (migrations, dependency manifests, pytest/CI
  configuration, and broad backend foundations) separately from avoidable blockers.
- [ ] For each avoidable blocker, add only a policy-verified configuration declaration or
  remove the underlying import side effect; do not use blanket waivers for R008/R019.
- [ ] Add CI evidence that shows Acquit's candidate selection beside the test commands that
  actually ran, so a reviewer can distinguish canary analysis from the retained full coverage run.
- [ ] After ten safe selective observations, propose a reviewed enforcement design: use the
  selected tests for PR feedback while retaining full coverage on `main` and a scheduled run.

**Acceptance criteria**

- Ten documented selective observations have zero unsafe-skip alarms and are reproducible with
  Acquit replay evidence.
- A deliberately changed migration still selects the full backend suite.
- A frontend-only change and a narrowly scoped backend change demonstrate a smaller, auditable
  test selection.
- Any analysis error, unknown import behavior, or invalid declaration fails closed to the full
  suite and is visible in the PR report.

---

## Milestone R0 — Revival and truth restoration · Weeks 1–2

### REV-002 — Reconcile preserved historical work

- [x] Add regression tests for real patient greeting and avatar identity.
- [x] Add regression test ensuring adherence percentages never render `NaN`.
- [x] Add regression test for missing obligation frequency.
- [x] Verify patient profile editing persists through the API.
- [x] Verify visits contain no hardcoded fake appointment.
- [x] Verify document types are inferred from content/metadata rather than mapping every PDF to a lab report.
- [x] Verify upload completes before extraction/import begins.
- [x] Verify expired import sessions fail safely and visibly.
- [x] Reimplement only behavior that is still missing on current `main`.
- [x] Delete `origin/codex/patient-portal-audit-followup` after verification.
- [x] Delete `origin/fix/patient-portal-audit` after verification.
- [x] Drop the stale April stash after verification.

Verification evidence: the patient portal suite passed 79 tests, and the patient, document,
feed, and extraction-import backend suites passed 59 tests on 2026-08-20. Current `main`
already covered greeting/avatar, visits, document-type inference, and backend patient updates.
The reconciliation restored the missing patient-profile edit flow and added regression coverage
for non-finite adherence, missing obligation frequency, upload/import ordering, and expired
upload-session recovery.
The two obsolete audit branches and the April 29 stash were deleted on 2026-08-20.

### REV-003 — Make documentation truthful

- [x] Save the approved August–December revival plan.
- [x] Replace the stale semester checkbox inventory with this tracker.
- [x] Rewrite `PROJECT.md` with the approved clinic/polypharmacy thesis and clinical boundaries.
- [x] Rewrite `ARCHITECTURE.md` to match deployed code, FHIR, safety, MCP, and A2A decisions.
- [x] Replace placeholder names and obsolete `develop` workflow in `TEAM.md`.
- [x] Mark all superseded model and chain-of-thought decisions without deleting decision history.
- [x] Add a one-command setup and validation guide.

### REV-004 — Remove architecture theater

- [x] Inventory empty modules, placeholder returns, mock-success paths, and reachable `NotImplementedError` statements.
- [x] Delete unjustified agent shells.
- [x] Convert scheduling, notification, auth, and database work into deterministic services.
- [x] Keep only the four approved agent/worker boundaries.
- [x] Add a CI check preventing new empty production modules and reachable placeholders.

### REV-005 — Create deterministic synthetic environments

- [x] Add a canonical, checksum-locked eight-patient California synthetic fixture with five `en-US` and three `es-MX` scenarios.
- [x] Map supported source content into two clinics, sixteen synthetic accounts, care teams, conditions, allergies, medications, metadata-only documents, appointments, five reviewed portal messages, and in-portal notifications.
- [x] Keep unsupported preferences, proxies, accessibility data, non-portal concerns, adherence events, and care-team scopes unpersisted and documented rather than inventing schema or false records.
- [x] Make seed/reset idempotent and guarded by environment, explicit confirmation, exact fixture-account deletion, and a migration-checksum preflight.
- [x] Remove the six verified pre-canonical staging identities through the exact reset allowlist, then verify that only the sixteen current fixture accounts remain.
- [x] Document deterministic fixture accounts without embedding secrets in the repository.
- [x] Run the approved staging seed and verify table counts, source-specific mappings, ledger checksums, and idempotency.
- [x] Verify RLS isolation and clinician/patient login journeys against the seeded staging environment. Patient password login, role-claim validation, live feed, and live adherence statistics passed on 2026-08-27 after the guarded reset/reseed; the clinician roster, patient review, and SMART import journey passed live on 2026-08-29. The active-care-team RLS helper contract and an explicit cross-clinic service denial test now prove that an unassigned clinician is rejected before the patient query runs.

**Verification evidence — 2026-08-22**

- The canonical JSON fixture is SHA-256 locked and loaded through a typed adapter; its local
  mapping, checksum, language split, null-gender handling, event transport boundaries,
  idempotency, reset safety, and migration-ledger checks passed in seven focused tests.
- Ruff, formatting, mypy, and 21-migration parser validation passed. Dry run reports two
  clinics, sixteen synthetic accounts, and eight patient scenarios.
- Staging was seeded twice without reset on 2026-08-22 after the migration ledger and
  required-table preflight passed. The second run created no duplicates.
- The staging audit confirmed 16 Auth users; 2 clinics; 8 clinicians; 8 patients;
  9 care-team assignments; 16 conditions; 6 allergies; 26 medications; 16 documents;
  8 appointments; 5 portal messages; 1 notification; and zero obligations, adherence
  logs, or symptom reports. The source language split remains 5 `en-US` / 3 `es-MX`,
  and all 8 persisted patient gender values are null.
- The ledger contains the expected entries for migrations 021 and 022, which grant the
  server-only service role the least privileges required for the guarded seed preflight
  and fixture adapter. RLS and portal-login acceptance checks remain before marking
  REV-005 complete.
- On 2026-08-27, the authorized guarded staging reset/reseed completed with the eight
  named fictional patient accounts and eight named fictional staff accounts under the
  project-controlled `accounts.mediagent.live` namespace. The two fixture clinics are
  Cedar Grove Community Health and Willow Terrace Family Medicine; no legacy fixture
  patient account remained. Migration 024's service-role read grant and checksum were
  present, and a new patient login returned a `200` from the live feed endpoint.
- The same live verification discovered the next missing least-privilege dependency:
  `reminder_schedules` is read by both the feed and adherence-statistics services.
  Migration 025 was applied to staging and recorded in the ledger; `service_role` has
  `SELECT` on all three required tables while `anon` and `authenticated` do not gain
  access to `reminder_schedules`. A new patient login then returned `200` from both
  live endpoints, and Cloud Run had no fresh error log in the following five minutes.
- On 2026-08-27, a follow-up staging audit found six older named fixture identities
  under the invalid `.local` namespace. The reset allowlist now includes only those
  six verified addresses (not a broad domain match). The authorized reset/reseed
  completed successfully; Auth, patients, and clinicians now contain exactly 16,
  8, and 8 project-controlled `accounts.mediagent.live` addresses respectively,
  with no legacy address remaining.
- On 2026-09-04, a read-only staging probe selected a care-team assignment from a
  different clinic, set the requesting clinician's authenticated JWT subject, and
  verified that `private.is_assigned_clinician` returned false. Direct reads of the
  foreign patient row were also denied because `authenticated` has no `SELECT` grant
  on `patients`; the probe rolled back without changing staging data.

**R0 exit gate**

- [ ] REV-001 through REV-005 acceptance paths are green.
- [ ] Repository contains no ambiguous preserved work.
- [x] Documentation reflects the intended product and actual implementation.
- [ ] A clean environment can be created and validated reproducibly.

---

## Milestone R1 — Clinical data, provenance, and interoperability · Weeks 3–4

### INT-001 — Canonical clinical facts and provenance

- [x] Define shared `ClinicalFact`, `EvidenceCitation`, `SourceProvenance`, and confidence/uncertainty types.
- [x] Store original source, document location, extractor version, model version, timestamp, and reviewer state.
- [x] Prevent unreviewed facts from silently becoming approved clinical truth.
- [x] Add lineage queries from derived fact to original artifact and from artifact to all derived facts.
- [x] Audit creation, correction, approval, rejection, and deletion.

**Implemented:** The clinical-fact registry stores pending candidates, citations, source
provenance, and append-only audit events. Document-extraction imports enroll derived
records as pending candidates; `list_approved` is the clinical-display query. See
`docs/clinical-facts-provenance.md` for lifecycle and access boundaries.

### INT-002 — FHIR R4 validation and mapping

- [x] Establish an R4-compatible validation boundary; the maintained dependency provides R4B while emitted payloads remain R4-compatible.
- [x] Map Patient. Practitioner, Organization, and CareTeam are intentionally not mapped because the local clinician/care-team model remains authoritative.
- [x] Map Condition, AllergyIntolerance, MedicationRequest, and MedicationStatement.
- [x] Map Observation, DocumentReference, and CarePlan; Appointment and Communication are intentionally outside the committed import set.
- [x] Generate validated, read-only Provenance and AuditEvent representations from local clinical-fact lineage and immutable audit records without external FHIR writes or private-reasoning disclosure.
- [/] Validate supported resource shape before persistence; identifier-quality and export validation remain deferred.
- [x] Handle missing, partial, duplicate, and unsupported resources safely.
- [/] Add import fixture tests; FHIR export and round-trip fixtures remain deferred.
- [x] Make SMART candidate review clinically legible: enrich mapped summaries, render FHIR instants in the selected patient's timezone, filter by mapped type, keep source-only candidates distinct from local facts, and replace whole-record JSON correction with field-level editing while preserving the review-only boundary.

**Plan:** `.agent/specs/int-002-003-interoperability-plan.md` defines the mapping
registry, import-envelope persistence, duplicate rules, and fixture evidence. Exact R4
sandbox conformance is an end-to-end acceptance test; the maintained runtime validator
uses the compatible R4B model.

### INT-003 — SMART-on-FHIR sandbox launch

- [x] Implement `/api/v1/smart/launch` and `/api/v1/smart/callback`.
- [x] Grant the trusted backend only the SMART session, import, provenance, and handoff operations it needs; apply and verify the migration in staging.
- [x] Validate PKCE, OAuth state, issuer, expiry, and provider-supplied scope/audience metadata. Opaque sandbox tokens are not treated as JWTs; when scope or audience is supplied it must be a string and must match the requested patient access and issuer. The successful EHR-initiated sandbox flow is the live conformance evidence.
- [x] Bind EHR `iss` and opaque `launch` context to a locally authenticated, care-team-authorized clinician/patient selection.
- [x] Import the supported patient bundle through the public SMART Health IT sandbox and deployed Cloud Run callback.
- [x] Show import status, raw-resource warnings, and review handoff in the clinician portal; make idempotent no-new-resource outcomes and in-progress authorization status explicit. The patient-level SMART imports tab exposes mapped candidate fields, explicit original-resource inspection, and review actions.
- [x] Repair and verify the least-privilege backend read set for live clinician dashboard and patient-review routes.
- [x] Replace the clinician portal's mock roster with live care-team-authorized dashboard data and make SMART authorization progress explicit.
- [x] Document sandbox setup and reproducible conformance test.

**Plan:** Build SMART authorization-code + PKCE handling after the INT-002 import
registry, then bind the resulting imported-record session to a locally authenticated
clinician. The plan records sandbox, HTTPS callback, and replacement-Supabase
prerequisites; none of them block fixture or route-test work.

**Live verification — 2026-08-29:** An EHR-initiated SMART Health IT R4 sandbox
flow completed against the deployed domains for a locally authorized synthetic clinician
and Maya Patel. It persisted 214 provenance-backed pending candidates for the selected
local patient. Mapped-type filtering, explicit raw-source inspection, patient-timezone
rendering, and review-only messaging passed in the deployed clinician portal. GitHub
Actions run `33263615712` deployed Cloud Run successfully; both portal deployments and
all PR checks passed. Approval, rejection, and correction have route and UI test
coverage but were not clicked live, so no review state was changed. Some standalone
launcher runs still return the sandbox's `Invalid launch options` response and remain
open for sandbox-specific diagnosis.

### SAFE-001 — Approval and audit infrastructure

- [x] Define `ClinicalRecommendation`, `ApprovalDecision`, `ActionEnvelope`, and `AuditRecord`.
- [/] Enforce tiered action authority server-side. `app/core/action_tiers.py` classifies each
      action type and `propose` enforces it; the applied tier is recorded on the audit
      trail. Tiers only tighten — none waives review. Feature-specific executors will
      classify their actions as they are implemented, and an unclassified action fails
      closed to the most restricted tier rather than inheriting the default.
- [x] Require idempotency keys for action envelopes.
- [x] Record proposer, evidence, reviewer, edits, decision, executor, and outcome.
- [x] Prevent approval by an unauthorized, unassigned, or proposing clinician.
- [x] Add replay and duplicate-action tests.
- [x] Record every authorization denial with a classified reason code, audited from the
      403 handler so every raise site is covered.
- [/] Verify the fixture's declared denial expectations against a live environment. Four
      of eight cases are verified; the remaining four are blocked on decisions below.

**Verification evidence — 2026-09-09**

- `backend/scripts/verify_authorization_denials.py` drives `negative_access_cases`
  against a running API and reads `authorization_denial_events` with the service-role
  key, which is the only way to see the table: the API never exposes it and RLS grants
  no browser role access. Against staging: 4 passed, 0 failed, 4 skipped.
- Verified end to end, each returning HTTP 403 with no target disclosure and the exact
  reason code the fixture declares: SYN-NEG-001 `NO_CARE_TEAM_ASSIGNMENT_CROSS_CLINIC`,
  SYN-NEG-003 `SAME_CLINIC_BUT_NO_CARE_TEAM_ASSIGNMENT`, SYN-NEG-006
  `PATIENT_SCOPE_SELF_ONLY`, SYN-NEG-008 `ASSIGNMENT_EXISTS_FOR_DIFFERENT_PATIENT_ONLY`.
  The two care-team variants are produced by the classifier from live care-team rows.
- Four cases are unverified, not verified. Three declare an action no route owns:
  `list_patient_documents` (`/documents/patients/{id}` is POST and registers a clinician
  upload; `GET /documents/` is self-only and the review queue is not per-patient),
  `view_medication_timeline`, and `view_document_metadata`. SYN-NEG-007 declares a proxy
  actor, which is intentionally not persisted. Assigning those three actions to routes is
  an open product decision, not a test gap.
- Role-gate denials are raised from a dependency that never learns which patient was
  addressed, so they record the actor and `request_path` with a null `target_id` and are
  not reachable through `idx_authorization_denial_events_target`. Counting what an actor
  attempted requires reading `request_path` for that class.
- Migration `033_authorization_denial_audit.sql` applied to staging on 2026-09-09; the
  table carries its three indexes and RLS enabled with no policy.

### AI-001 — Provider-neutral AI and voice interfaces

- [x] Define model capabilities and structured error taxonomy.
- [x] Wrap all non-streaming text generation paths behind the provider registry, with normalized telemetry and Flash fallback for runtime or primary-client initialization failure. Structured output and streaming intentionally retain their capability-specific client contracts.
- [x] Add optional MedGemma and NVIDIA NIM comparison adapters. MedGemma needed none: the
      client is complete and already reaches the provider-neutral interface through
      `ClientTextProvider`. What was missing was the comparison itself, since
      `TASK_MODEL_MAP` binds each task to one model and cannot express "run this prompt on
      all three". `ModelRouter.get_text_provider_for_model`, `compare_text_providers`, and
      `scripts/compare_providers.py` close that. `NvidiaNimClient` adds NIM as a fourth
      comparable provider, reachable by model name and deliberately absent from
      `TASK_MODEL_MAP` because it exists to be evaluated, not to serve a task. It needs
      `NVIDIA_NIM_API_KEY` and is therefore opt-in on the comparison CLI.
- [x] Define the voice-provider interface. `VoiceProvider` was a declared protocol that
      nothing implemented and that only covered synthesis, so voice had no provider-neutral
      path at all. It now covers both directions (`transcribe`, `synthesize`) over
      `VoiceTranscriptionRequest`/`VoiceSynthesisRequest`, carries the locale on the request
      so a bilingual product can pick the right acoustic and voice model, and reports the
      same normalized telemetry and error taxonomy as text. `DeepgramVoiceProvider` adapts
      the existing client with its dependencies injected, so the contract is testable
      without a key or a network call; `VoiceFallbackProvider` records the selection path
      and steps over a provider that refuses a direction rather than recording it as an
      outage. `VoiceService` now calls the chain instead of the client. Two deliberate
      boundaries: synthesis degrades to `TextOnlyVoiceProvider` (the words survive, the
      audio does not) while transcription fails loudly, because there is no honest
      text-only answer to what a patient said; and the websocket refuses to deliver an
      empty payload as audio, which keeps today's patient-visible behavior until the
      transport can carry a text-only turn. Verified 2026-09-21: 1,352 backend tests pass
      at 83.74% coverage, with Ruff, Ruff format, and mypy clean.
- [/] Migrate live voice transport. The streaming session
      (`DeepgramLiveTranscriptionSession`) deliberately still holds the Deepgram client
      directly, mirroring the text decision to leave streaming on its capability-specific
      contract. Surfacing a text-only turn to the patient when speech is unavailable
      belongs to this step.
- [x] Record latency, model/version, tool calls, token/usage data, and fallback path in the provider response contract.
- [x] Guarantee deterministic text fallback when audio is unavailable.
- [x] Replace the retired `gemini-3.1-flash-lite-preview` fallback default with
      `gemini-3.1-flash-lite`, and route all Gemini 3.1 aliases through the Google Gen AI
      SDK's Vertex `global` endpoint. This restores the document-ingestion fallback without
      changing candidate-only reconciliation behavior.
- [/] Run a 2026 model-routing decision spike before changing any clinical AI workflow:
      benchmark synthetic, gold-labeled document extraction, structured candidate mapping,
      bilingual patient communication, and deterministic-safety escalation across current
      provider candidates. Compare quality, abstention, schema validity, latency, cost,
      data controls, SDK lifecycle, and failover behavior; record the selected providers and
      version-pinning policy in an ADR. The retired-model incident is the trigger, not proof
      that a provider should be replaced without this evaluation. Active runtime work is tracked
      in `AI-003`; later evaluation/adjudication work is tracked in `EVA-001`.

### REV-006 — Consolidate durable documentation

**Status:** `[x]` Merged and verified

**Owner:** Rajeev Chaurasia

- [x] Preserve the active execution plan, task tracker, product/architecture records, and
      operational guides as the sources contributors need to work safely.
- [x] Replace superseded phase plans, provider surveys, pricing snapshots, and preliminary
      evaluation narratives with concise AI and document-intelligence decision records.
- [x] Correct stale agent-runtime, MCP, workflow, and package-map guidance that still named
      retired implementation patterns.
- [x] Remove generated local evaluation reports from version control eligibility.
- [x] Merge and verify that internal documentation links resolve on `main`. PR #91 merged as
      `390f2ad`. Verified 2026-09-21 by resolving all 58 relative links across the 62 tracked
      markdown files, including heading anchors. Two were broken and are fixed here: the
      clinician portal README pointed one directory level up instead of two, and the backend
      testing guide linked a `MOCK_VALIDATION.md` that exists nowhere in the tree, so it now
      points at the mock-validation tests themselves.

---

### AI-003 — Agent runtime overhaul

**2026-10-03 capacity follow-up (implemented; not deployed):** One deadline-bounded
interactive 429 retry, process-local endpoint/model admission and start pacing,
background slot reservation, and sanitized per-attempt diagnostics are implemented.
The global preflight checked Flash-Lite and evaluation-only GPT OSS in English and
Spanish: initial run 7/8 first attempts, one deadline/fallback and one strict JSON-key
failure; corrected synthetic prompt run 8/8 first attempts and response contracts.
No live 429 occurred: recovery evidence comes from controlled regressions, not a
production availability claim. Model routing remains unchanged. Exact verification
and limits are in `docs/decisions/ai-runtime-2026-09.md`; deployment and sustained
production metrics remain acceptance work. No migration or remote config changes.
Verification from `backend/`: `PYTHONPATH=src .venv/bin/python -m pytest -q
--disable-warnings` passed 1,636 tests, skipped 20 opt-in PostgreSQL tests, and
reached 85.49% coverage. `.venv/bin/ruff check src scripts` and changed-test lint,
`.venv/bin/ruff format --check src scripts` and changed-test formatting, and
`.venv/bin/mypy src` passed. `git diff --check` passed. Paid operator check:
`VERTEX_AI_LOCATION=global GEMINI_VERTEX_AI_LOCATION=global PYTHONPATH=src
.venv/bin/python scripts/preflight_model_capacity.py --include-oss`; the final
eight-case run passed. The first run's failed format check remains documented;
no clinical-quality or deployed end-to-end acceptance claim follows from it.

**Status:** `[/]` In progress

**Priority:** P0 (contains the shipped SAFE-002 streaming fix)

**Owner:** Rajeev Chaurasia; safety review required before any workload defaults on

**Why:** The September evaluation ended with two finalists that cannot be separated on clinical accuracy, and
with four findings that are not model choices at all: the streaming chat path reached the
emergency floor only when the model failed, the document pipeline cannot produce the
page-anchored citations its release gate requires, a patient cannot ask a question about
their own records, and the Gemini client picked its SDK from the model name. Choosing a
model does not fix any of those. This task rebuilds the runtime around them.

**Workstreams**

- [x] **WS0 — Safety and truth.** The streaming triage path now runs the deterministic
      emergency floor before the model rather than only when the model fails; the floor,
      the bilingual copy, and escalation moved to `backend/src/app/safety/` so that
      removing the graph framework later cannot disturb them. Escalation is monotonic and
      can force `emergency`, which it previously could not. The English-only outer chat
      fallback is localized. `ingestion_service.py` wrote every extraction candidate with
      `confidence_score=None` because the keyword did not match the field name; fixed.
      Pinned by tests that fail if the model is consulted at all on an emergency message.
      **Correction, found while building WS2:** the extraction was incomplete. The plan
      recorded that WS0 moved the "bilingual `TRIAGE_COPY`" into `app/safety/`, and it did
      not — only the keyword sets, the verdict type and the escalation logic moved. The
      copy was still defined inside `agents/triage/graph.py`, the module WS8 deletes, so
      removing the agent runtime would have taken the emergency and self-harm responses
      with it. That is precisely the coupling the plan called "the load-bearing sequencing
      decision". `TRIAGE_COPY` now lives in `app/safety/copy.py` with its own tests,
      including that Spanish is genuinely translated rather than a copy of the English —
      a presence check alone would pass on a copy-paste and fail a patient.
- [/] **WS1 — Model layer.** `app/adk/registry.py` now records, per workload, a primary,
      a fallback, a latency budget, a named deterministic path, and a kill switch, with
      those invariants checked at import. The Gemini client selected its SDK from the
      model name (`startswith("gemini-3.1-")`), which sent every other model — including
      3.8 Flash — down the legacy `vertexai` path; Vertex now always uses the Gen AI SDK,
      and a failed Vertex init raises instead of silently downgrading to the consumer AI
      Studio API. MedGemma is removed: it was measured and dropped in AI-002, and its
      client already raised on the empty-endpoint default, so document parsing was
      served by Flash through the fallback while triage classification raised on every
      call and degraded to keyword rules without recording it.
- [/] **WS1 — gpt-oss transport.** `app/adk/models/vertex_maas.py` reaches managed
      open-weight models over Vertex's OpenAI-compatible surface, with an Application
      Default Credentials token resolved per request rather than frozen at construction,
      because a token lasts an hour and a long run does not. Verified live against both
      the global and regional endpoint forms. Two findings worth keeping: the publisher
      prefix (`openai/gpt-oss-120b-maas`) is part of the wire model id on that surface and
      is spelled exactly like a LiteLLM provider prefix, so it invites removal and is now
      pinned by a test; and the harness never recorded `base_url` in any report, so the
      endpoint behind our routing decision had to be reconstructed from a spec written
      weeks earlier. `run_ai_eval.py` now records it, and protocol §15 documents the
      verification. Earlier reports must be read as having an unrecorded endpoint.
- [x] **The Gen AI path overrode the caller's token budget, on a false premise.**
      `_generate_genai_sdk` raises every request to `max(max_tokens, 8192)`, justified by
      a comment claiming the SDK defaults to something lower. Measured on 2026-09-17
      (protocol §16): the SDK default is `None`, and an unset budget and 8192 produce
      byte-identical results. The floor was introduced in `1a5820e` on 2026-03-22 and
      never measured. It only affects the Vertex path, which makes it a migration hazard
      rather than a standing annoyance — setting `GOOGLE_PROJECT_ID` moves every caller
      onto it at once, at up to sixteen times the requested budget.
      **It cannot simply be deleted.** Thought tokens are billed against the same budget,
      so honouring the callers' current 384-to-2048 requests would truncate a thinking
      model on its reasoning before it writes anything — which is what the floor
      accidentally masks. Measured: thinking takes 45–73% of the budget, so the 384-token
      caller would spend all of it reasoning and emit nothing (protocol §17).
      The fix is a per-workload budget and an explicit `thinking_level`, adopted together.
      **Not** by disabling thinking: dynamic thinking cannot be switched off on Gemini
      3.x, and `thinking_budget` is deprecated there — `thinking_level` is the supported
      lever, with `MINIMAL` rejected outright by 3.8 Flash, so the usable range is `LOW`
      to `HIGH`. Google's own guidance is the same: never shrink `max_output_tokens` to
      control cost, lower `thinking_level` instead.
      `GOOGLE_PROJECT_ID` is now set in production, so the Vertex path is live and this is
      no longer a pre-migration gate — it is a live cost and latency issue.
- [x] **Truncated answers were returned as if complete.** `_generate_genai_sdk` logs a
      warning when `finish_reason` is not `STOP` and returns the partial text anyway, so a
      cut-off clinical answer reaches the patient looking finished. This is a correctness
      defect, not an efficiency one, and it is the reason to detect `MAX_TOKENS` and
      regenerate at a larger budget rather than stitch a continuation — stitching two
      generations of clinical text risks duplicated or contradictory advice across the
      seam. There is no resume endpoint; Google's sanctioned answers are sizing the
      budget, lowering `thinking_level`, and streaming.
- [x] **What landed for both of the above.** The 8192 floor is deleted and the caller's
      budget is honoured. `app/adk/registry.py` now carries `max_output_tokens` and
      `thinking_level` per workload, sized from measured answer lengths — triage 1024/LOW
      (answers 115-136 tokens), explanation 2048/LOW (answers 950-1166 and truncated at
      1024), extraction 8192/MEDIUM, discrepancy 4096/MEDIUM — and rejects `MINIMAL` at
      import, because 3.8 Flash answers it with an HTTP 400 at call time instead.
      A `MAX_TOKENS` finish now regenerates once at double the budget and then raises
      `AnswerTruncatedError` rather than returning a partial answer. **Regenerate, not
      continue:** stitching a second call onto a half sentence of clinical advice risks
      duplicated or contradictory instructions across the seam, and Google publishes no
      resume endpoint. The streaming path — the patient-facing one, which previously set
      no ceiling and never read `finish_reason` — now does both.
      One subtlety worth keeping: the truncation error is re-raised ahead of the generic
      retry handler. Left inside it, resending an identical request could never widen a
      budget, so truncation was retried three times with backoff and then reported as a
      provider outage, losing the distinction between "we cut it off" and "it failed".
- [ ] **Sampling parameters are sent but unsupported on 3.x.** Google says to drop
      `temperature`, `top_k` and `top_p` for Gemini 3.x; our call sites still send
      `temperature`. The API accepts them silently, so this is a quiet mismatch rather
      than a failure — but it means the values in our code are not doing what they read
      as doing.
- [ ] **`generate_structured` does not use structured output.** It appends the JSON
      schema to the prompt text and then string-splits markdown fences off the reply,
      never setting `response_mime_type` or `response_schema` on the Gen AI config even
      though the SDK supports both. That is the prompt-embedded-schema approach our own
      protocol (§3, §11) measured as the weaker one, and it is why schema failures here
      surface as unparseable text rather than as a refused request. It also inherits the
      8192 floor through `generate`, and defaults to `temperature=0.7` for what is by
      definition an extraction task.
- [x] **Candidates now record which model produced them.** An earlier note here called
      this latent, on the grounds that only `grounding.py` threads `model_version` and
      that prototype is wired to nothing. That was wrong: the **live** ingestion path
      (`ingestion_service.py`) also never supplied it, so every document candidate written
      in production carried `model_version = NULL` — provenance migration 017 has had room
      for since the table was created. It matters now precisely because the model was just
      swapped: without it there is no way to tell which candidates came from 3.1 Flash-Lite
      and which from 3.8 Flash, and therefore no way to re-review or retire them
      selectively.
      The fix threads the model that **actually answered** from the generation call
      through `IngestionState` to the candidate write, via a new
      `generate_text_with_telemetry`. Reading the configured model name at the write site
      would have been a one-line change and a lie — the router falls back, so the
      configured model is not necessarily the one that replied, and a confidently wrong
      provenance stamp is worse than an absent one. A test pins that an unknown model is
      recorded as `None` rather than guessed.
      Still outstanding for WS5: `grounding.py` must supply it too when the document
      pipeline is wired up.
- [x] **Structured output is now enforced, not requested.** `generate_structured` pasted
      the JSON schema into the prompt on every path and then string-split markdown fences
      off the reply — the weaker of the two approaches our own protocol measured (§3,
      §11), and why schema failures surfaced as unparseable prose rather than a refused
      request. Vertex now enforces the schema natively. Verified on the locked SDK that
      this coexists with `thinking_config`, which was the real risk: constrained decoding
      and reasoning collided on MedGemma, where the grammar applied from the first token
      and the model never got to think. AI Studio keeps the prompt-embedded path, having
      no native equivalent.
- [x] **Model telemetry is recorded instead of discarded.** `ModelRouter.generate_text`
      returned `response.text` and dropped the `GenerationTelemetry` beside it, so the
      figures the routing table was chosen on — latency per workload, which model actually
      served, truncation rate, cost — stopped being collected the moment the decision was
      made. Migration `035_model_invocation_telemetry.sql` (validated by `pglast`) plus
      `services/model_telemetry_service.py`. Deliberately **best-effort and scheduled**,
      unlike `authorization_audit_service`, which is awaited: a denial is a security
      record that must not be lost, whereas telemetry runs on every turn and awaiting a
      stalled database would spend a patient's latency budget on bookkeeping. No patient
      identifiers, prompts or response text are written, pinned by a test.
- [/] **WS1 remaining.** The production Cloud Run revision is configured with
      `GOOGLE_PROJECT_ID=medi-agent-490106`, `VERTEX_AI_LOCATION=us-central1` for MaaS,
      `GEMINI_VERTEX_AI_LOCATION=global` for Gemini 3.8 Flash, and
      `GEMINI_FLASH_MODEL=gemini-3.8-flash`; its runtime identity has Vertex AI User and
      a direct regional `openai/gpt-oss-120b-maas` request succeeded. The application
      keeps the AI Studio path only as an explicit local/evaluation compatibility path;
      it is not selected when the production project is configured. The two outstanding
      acceptance items are (1) impose the registry's wall-clock budget around the ADK
      runner and model transports, so an over-budget call deterministically reaches the
      named fallback, and (2) retain evidence from a deployed synthetic request that
      `model_invocation_events` records the actual provider and model.
- [/] **WS1-B — central background-workload routing.** The active legacy background
      callers (document extraction, patient explanation, and evidence-only care-plan
      classification) are being moved behind one registry-backed executor. It must enforce
      the route's token and reasoning ceilings, wall-clock limit where one exists, named
      distinct-model fallback, kill switch, and safe telemetry for every attempt. The
      owning service, not an agent, remains responsible for the deterministic clinical
      outcome: no extraction means evidence review, no explanation means its existing
      retry/fallback state, and no care-plan classification keeps the approved plan intact
      while the draft remains retryable. The work is claimed on
      `codex/centralize-background-ai-routing`; direct client construction remains only for
      evaluation or workloads that lack measured routing evidence.
- [/] **WS2 — Agent runtime skeleton**, replacing the graph framework: one runner
      construction path that refuses to start unless every safety plugin is attached.
      **Dependencies landed.** `google-adk` 2.9.1 and `litellm` 1.101.0 are in
      `requirements.in`, both locks recompiled with CI's exact `uv pip compile` commands,
      and `pip-audit` at CI's pinned 2.10.1 reports no known vulnerabilities — so the
      1.82.7/1.82.8 advisory the plan flagged is avoided by the `>=1.84` floor rather
      than merely assumed. The delta is additive: 35 packages added, none removed, and
      one existing pin changed (`google-genai` gains a 2.24.0 marker). Verified first
      that local `uv` reproduces the committed lock byte-for-byte, so any lock diff is
      genuinely ours and not a toolchain mismatch. 1171 tests pass on the new set.
      **The `openai/` prefix collision is real, and resolved.** The plan required this be
      spiked before anything depended on it. Measured against the live endpoint:
      `LiteLlm(model="openai/gpt-oss-120b-maas")` fails with
      `400 Malformed publisher model ('gpt-oss-120b-maas') ... expected
      '<publisher>/<model>'` — LiteLLM consumes the leading segment as *its own* provider
      prefix and forwards the bare id. `custom_llm_provider="openai"` does not fix it.
      **Doubling the prefix does**: `openai/openai/gpt-oss-120b-maas` succeeds and the
      response reports `openai/gpt-oss-120b-maas` back, confirming the real id arrived.
      So ADK's `LiteLlm` connector is usable and the planned fallback (a custom `BaseLlm`
      wrapping `openai_compatible.py`) is not needed.
      The doubling lives in `adk/models/vertex_maas.litellm_model_id`, **not** in the
      registry: `ModelSpec.model_id` stays the true wire id that the raw HTTP transport
      sends verbatim. It reads exactly like a typo, so it is pinned by a test that says
      why — an "obvious cleanup" here silently breaks a deployed, working model.
      **`google-genai` moved 2.18.1 → 2.24.0** with the install. WS1's thinking levels,
      native `response_schema`, `temperature` omission, config mutability and
      `finish_reason` handling were all re-verified live on 2.24.0 and hold. This matters
      because the unit tests mock the SDK and would not catch a signature change.
      **ADK's own documentation is wrong about the halt contract, and following it would
      have reintroduced the WS0 P0.** `BasePlugin.before_run_callback` is annotated
      `Optional[types.Content]` but its docstring prose says "An optional `Event`". Those
      are different types, and this is the emergency-halt path, so it was tested rather
      than read. Measured against a runner whose agent would fail loudly if reached:
      returning `types.Content` **halts** — one event, our copy returned, no model call;
      returning an `Event` **does not halt** — the run proceeded into the agent, behaving
      identically to the `None` control. So the annotation is correct and the prose is
      not. Had the floor returned an `Event`, an emergency message would have reached the
      model with no halt at all, which is precisely the defect WS0 fixed.
      Also confirmed on 2.9.1: `Runner(app_name=…, agent=…, session_service=…,
      plugins=[…])` is a valid construction, `session_service` is its only required
      argument, `before_tool_callback` returning a dict stops the tool (so deny-by-default
      tool policy works), and `LlmAgent.model` accepts a `LiteLlm` instance directly.
      **The safety floor is now a plugin** (`adk/plugins/safety_floor.py`), which is the
      whole point of doing it here rather than as an agent callback: registered once on
      the runner, it runs before any agent, so the guarantee cannot be lost by adding an
      agent later or forgetting to wire a callback onto one. That is the exact shape of
      the defect WS0 fixed, where the streaming path reached the floor only when the model
      happened to fail. It returns `types.Content` — never an `Event` — with the measured
      reason recorded beside it, and answers in the patient's locale from session state.
      Two worries checked rather than assumed, both fine: the floor's **Spanish** coverage
      is real (`dolor de pecho`, `no puedo respirar`, `infarto`, `suicidarme`, `matarme`,
      `quitarme la vida`, `hacerme daño`), so a Spanish speaker expressing suicidal intent
      does trip it; and `resolve_locale_resource` falls back cleanly on a `None`, empty or
      unknown locale, so a malformed context cannot make the floor fail open.
      **Tool policy is enforced, deny-by-default** (`adk/plugins/tool_policy.py`). A
      per-agent allowlist checked in `before_tool_callback`, which stops the call and
      returns the refusal to the model as an ordinary tool response rather than an
      exception. The negative properties are what the tests pin: an agent with no entry
      reaches nothing, a tool added later is not reachable for free, a malformed context
      fails closed, and the refusal neither echoes the tool arguments (which can carry
      clinical detail) nor enumerates the allowlist (which would hand the model a map of
      what to try next).
      Denials are deliberately **not** written to `authorization_denial_events`. That
      table records refused patient *access* and its reason codes are a closed set kept in
      step with the synthetic negative-access fixture; an agent reaching past its
      allowlist is a different fact, and folding it into a feed alerted on for care-team
      boundary probing would blunt that signal. It goes through a recorder seam that logs
      today and can gain a durable table later — deliberately not taking migration `036`,
      which the plan reserves for WS6's patient-document chunks.
      **Telemetry is collected from the agent runtime** (`adk/plugins/telemetry.py`),
      writing to the same `model_invocation_events` table through the same service WS1
      built, so the runtime and the legacy router report into one place. Two details
      decide whether the numbers mean anything, and both are pinned by tests: only the
      **final** response is recorded, because under SSE streaming `after_model_callback`
      fires per chunk and recording each would write a row per token-chunk and make
      latency meaningless; and the SDK's token fields are **mapped, not assumed** —
      `prompt_token_count`/`candidates_token_count`/`thoughts_token_count` are not the
      `input`/`output`/`reasoning` names the table stores, and assuming they matched would
      have written `NULL` into every token column without failing anything. A failed call
      is recorded with the exception's *type*, never its message, since an exception
      string can carry prompt fragments.
      Worth noting: `LlmResponse.finish_reason` sits directly on the response, not nested
      under `.candidates` as it is on the raw SDK response, so the client's helper of the
      same name cannot be reused here — doing so would have returned `None` for every call
      and quietly lost the truncation signal.
      **Provenance is carried to the write** (`adk/plugins/provenance.py`). It stamps the
      model that actually answered into session state for candidate-writing tools to read,
      which is the agent-runtime equivalent of what WS1 threaded through `IngestionState`.
      The keys are `temp:`-scoped deliberately: ADK's `append_event` applies temp state to
      the session *before* trimming the delta, explicitly so later tools in the same
      invocation can read it, then strips it before anything persists — so it reaches this
      turn's write and cannot linger as a stale "last model used" that a later turn stamps
      onto a candidate that model never produced. A missing model leaves the key **unset**
      rather than blank, because a tool cannot distinguish "recorded nothing" from an
      empty string, and a failed state write is swallowed: bookkeeping must not cost a
      patient their answer.
      All four plugins now exist and register as `safety_floor`, `tool_policy`,
      `telemetry`, `provenance`.
- [x] **One construction path, with a guarantee that cannot be optimised away**
      (`adk/runner.py`). A `Runner` assembled anywhere else has none of the four
      guarantees and nothing about the resulting object looks wrong, so construction goes
      through `build_runner` and `assert_guarantees` reads the plugins back off the
      **constructed runner** rather than the list handed to it — checking the list would
      be tautological, since `build_runner` builds that list itself. It raises
      `MissingRuntimeGuaranteeError` rather than using `assert`, because `assert` is
      stripped under `python -O` and a safety guarantee that disappears under an
      optimisation flag is not one. Tests cover the bare and the partially-equipped
      runner, since three plugins of four is the failure that looks normal.
      `tool_allowlist` is required rather than defaulted: an empty default reads as "not
      configured yet" and behaves as "this agent may call nothing", and that gap is the
      kind of thing discovered during a demo. Sessions default to in-memory for the
      strangler phase and are injectable for WS9; `chat_messages`, `conversation_states`
      and `clinical_facts` remain the system of record.
      Named `adk/runner.py` rather than the plan's `adk/app.py` — `app.adk.app` reads
      poorly inside a package already called `app`.
- [/] **Tools package: the patient-scoping contract first** (`adk/tools/scoping.py`).
      A finding worth recording plainly: **row-level security does not protect a tool.**
      Every policy in migration 002 is written against `auth.uid()`
      (`patients_own_select … USING (id = auth.uid())`), and tools run with the
      service-role client returned by `get_db()`, which has no `auth.uid()` and bypasses
      RLS by design. Routers are safe because FastAPI authenticates first and
      `_ensure_chat_access` refuses a patient reading another patient; a tool has no
      request, no `CurrentUser` and no dependency chain, and its caller is a model. So
      this wrapper is not a second line of defence — it is the only one.
      `require_patient_id(tool_context)` therefore takes **only** the context: the patient
      is read from authenticated session state and there is no argument a model could
      supply, override, or be prompt-injected into supplying. A signature test pins that,
      because an argument that does not exist is a stronger guarantee than a check that
      has to win every time. Absence raises rather than defaulting — reading "no patient"
      would either return nothing or, against a permissive query, return everyone — and a
      malformed identifier is refused rather than passed through, since that is how a
      filter silently stops filtering. The rejected value is never echoed into the error
      or the log.
      Verified alongside this: ADK strips framework-injected arguments from the
      declaration the model sees, so a tool can take `query` from the model and the
      patient from `tool_context` with the patient absent from the schema entirely. That
      is the mechanism the whole cross-tenant design in WS6 depends on.
      Still to do for WS2: the remaining tools, which are blocked on their backing
      services — `search_patient_documents` needs WS6's table and `find_evidence_on_page`
      needs WS5's anchoring. The placeholder checker forbids stubs, correctly.
- [/] **WS3 + WS8 combined, by extracting once instead of twice.** Building the Care
      Coordinator kept surfacing deterministic behaviour still living inside the LangGraph
      module WS8 deletes: after `TRIAGE_COPY`, also the emergency and fallback response
      selectors, intent→route mapping, the rule cascade, and seven classification keyword
      sets. Importing those from `graph.py` would bake in a dependency WS8 then has to
      unpick, so they move first and the Coordinator is built on the result.
      **A correction to an alarm raised earlier in this work:** the duplicated emergency
      keyword sets in `graph.py` and `app/safety/triage_floor.py` were reported as meaning
      "the floor no longer agrees with itself". Measured, all three sets are identical
      (28/28, 13/13, 9/9) and `graph.py:_deterministic_safety_floor` *delegates* to
      `app.safety`, so the 911/988 decision has one implementation. The real exposure is
      narrower: the leftover copies are read only by `_contains_adverse_effect_signal`,
      which affects urgency escalation on medication questions. Latent drift in a
      secondary path, not a live disagreement in the emergency decision.
      Scoping note: `app.safety` keeps the rules that decide *danger*; an `app/triage/`
      package was extracted alongside it for the rules that decide *what a message is
      about*, on the reasoning that routing is an architectural decision rather than a
      safety one.
      **That package has since been deleted, and the rule cascade with it.** The product
      rule that replaced it: when the model cannot answer, we say so. We do not infer a
      clinical topic from keywords and then answer in that topic's voice, because nothing
      in the reply distinguishes a guess from an answer — and the guess was thin enough to
      turn seven drug names into "medication question". `classify_intent` and
      `TriageAgent.process_stream` now branch on a null classification and return the
      localized `service_unavailable` copy, which names 911 and the care team so that
      someone who is genuinely unwell, but whose wording did not trip the floor, is still
      routed. The deterministic safety floor runs first and is untouched, so an explicit
      emergency still gets the 911/988 answer during a total outage.
      Deleted with the cascade: `_classify_with_rules`, `_has_document_signal`,
      `_contains_adverse_effect_signal`, `_matches_any`, `app/triage/keywords.py`, and the
      duplicate emergency/self-harm/adverse-effect frozensets in `graph.py` — the latent
      drift noted above is now closed by deletion rather than by reconciliation.
      `_is_non_clinical_math_query` survives: `_fallback_response` still calls it.
      `tests/unit/agents/test_triage_routing_golden.py` was the cascade's specification and
      is rewritten to pin the replacement: the floor still decides emergencies without a
      model, and every other message receives the outage copy rather than the intent
      fallback it used to get.
      **`registry.py` was describing the deleted cascade** as the triage deterministic
      path. `_validate` only checks that string is non-empty, so the table would have gone
      on documenting a path that no longer existed; it now names the floor and the outage
      message.
      **A second silent AI-Studio downgrade, found while building the model layer for the
      Coordinator.** ADK resolves a bare `model="gemini-3.8-flash"` to its `Gemini` class,
      which builds a `google.genai.Client` from `GOOGLE_GENAI_USE_VERTEXAI`,
      `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`. This application sets none of
      them and never writes to `os.environ`, so an `LlmAgent` given the plan's direct model
      string would have answered from AI Studio — different quota, different data handling,
      not the service the registry routes to. That is the defect WS1 deleted from
      `clients/gemini.py`, one layer up. `adk/models/adk_models.py` therefore injects an
      explicitly-built Vertex client (verified: ADK prefers an injected `client` over
      constructing its own) and refuses an unset project rather than falling through.
      The managed-model half has its own trap: `LiteLlm` merges constructor kwargs into
      each completion call, so an `api_key` passed at construction is frozen for the life
      of the process while a Google access token lasts an hour. `BearerLiteLlm` refreshes
      it inside `generate_content_async`, where `_additional_args` is read at call time.
      **An `adk_chat_enabled` rollout switch was added and then removed**, on the product
      owner's challenge that chat is not an optional feature. The reasoning holds: a
      runtime toggle is only worth carrying while two runtimes exist, and WS8 deletes the
      second one in this same piece of work — so the flag would have been dead config the
      day it shipped. The operational safety valve that actually survives the cutover is
      the per-workload kill switches, which route to the deterministic path (floor plus
      the localized `service_unavailable` copy) with no second runtime required. The
      decision is therefore a hard cutover to the agent runtime, with WS8's deletions in
      the same change rather than behind a flag nobody would flip.
      **The Care Coordinator itself is built** (`adk/agents/care_coordinator/`): a
      two-stage pipeline with the reasoning stage on gpt-oss holding the tools and the
      responding stage on Flash writing the patient-facing reply, each asking the registry
      for its own workload so neither model is chosen in the agent module.
      The property most worth a test here is a silent one: `ToolPolicyPlugin` keys its
      allowlist on `tool_context.agent_name` and denies by default, so renaming the
      tool-holding agent out of step with its allowlist entry raises nothing — every tool
      call is refused, the model answers without the record, and the reply degrades
      quietly. The names and the allowlist are defined in one module and a test pins that
      they agree. `search_patient_documents` is deliberately not granted ahead of WS6
      building it, or the allowlist would stop describing what is actually reachable.
      `temperature` is never set: Gemini 3.x accepts and ignores it, so passing it would
      read as a sampling control and be none. `ThinkingConfig` is a Gen AI shape and is
      applied only to the Gen AI transport — the managed model's ceiling is its
      `reasoning_effort`, set where the model is built.
      **Two ADK deprecations, handled differently because they are not alike.**
      `SequentialAgent` warns that it is superseded by `Workflow`, but `Workflow` is not
      exported by `google.adk.agents` in the pinned 2.9.1 at all, the warning names no
      removal release, and its own text says `Workflow` "cannot yet be used as an LlmAgent
      sub-agent" — which is exactly what WS4's Follow-up delegation needs. Kept, with the
      reasoning recorded in the module so it is not "cleaned up" later.
      `Runner(plugins=...)` is also deprecated, in favour of `Runner(app=App(...))`, and
      that successor *does* exist in 2.9.1. Not taken yet: it is the single construction
      path carrying every safety guarantee, `assert_guarantees` reads the plugins back off
      `runner.plugin_manager`, and passing both arguments raises — so it is an
      all-or-nothing change that must re-prove that read rather than a warning silenced in
      passing. **Scoped follow-up, before WS9.**
      **`submit_triage_decision` gives the turn its typed classification.** The websocket
      contract carries an `intent` and an `urgency` on every turn and the portal renders
      from them, which prose cannot supply and which must not be inferred from the reply
      afterwards. It is a tool rather than an `output_schema` because gpt-oss violated an
      accepted schema in 3 of 10 measured trials while listing function calling as
      supported. Nothing about it decides safety: the floor answered any emergency before
      an agent ran, and `apply_safety_override` is re-applied at the boundary, so a model
      that under-calls urgency cannot talk the turn down.
      Three findings from probing adk 2.9.1 directly, each of which would have been a live
      defect if taken from the documentation:
      (1) the reasoning stage's **internal working notes are emitted as ordinary events
      with `is_final_response()` true**, so streaming every event would have shown the
      patient the coordinator's notes;
      (2) the safety floor's halt arrives as a single event authored `model` rather than
      by an agent, so filtering *for* the responder would have **dropped the emergency
      message entirely** — the filter has to exclude the coordinator, not include the
      responder;
      (3) a `temp:`-scoped state key never appears in `event.actions.state_delta`, so the
      decision cannot be `temp:`-scoped; staleness is prevented instead by the caller
      reading only the current turn's delta and never session state, which makes a
      left-over value structurally unreadable rather than merely unlikely to be read.
      Still to do for WS3: wire the pipeline into `routers/chat.py` as a hard cutover,
      seeding `patient_id` and `locale` into session state (the tool scoping and the
      safety floor each read one), preserving the websocket event contract exactly.
      Also outstanding for WS8: `services/ai_evaluation.py:36` imports the **private**
      `_deterministic_safety_floor`, `IntentType` and `UrgencyType` from the doomed module.
- [/] **WS3–WS4 — Care Coordinator and Follow-up worker.** Both now serve the live
      websocket turn, and the event contract is unchanged — `chat.py` still emits a
      classification, its chunks and a completion in the same order, which is what the
      portal renders and what the integration tests pin.
      There is **no rollout flag**, on the product owner's challenge that chat is not an
      optional feature: a runtime toggle is only worth carrying while two runtimes exist,
      and this work removes the second one. The operational valve is the per-workload kill
      switches, which route to a deterministic path without needing a second runtime.
      **The follow-up worker stopped inventing symptoms.** Its rule-based extractor ran
      whenever the model was unavailable, inferring the symptom from substrings and making
      up a severity: "worst headache pain today" was recorded as severity 8, and "tengo
      dolor fuerte en el pecho" — severe chest pain — as `symptom="reported symptom"`,
      severity 4, unflagged. Unlike the triage cascade, those values did not merely shape a
      reply: they were written to `symptom_reports`, counted toward the adverse-event
      signal, and read afterwards by a clinician as the patient's own account. A guess that
      persists is worse than one that does not, so a failed extraction now writes no report
      at all and tells the patient so. `registry.py` no longer claims "rule-based symptom
      extraction" as the deterministic path for that workload.
      A reply the model could not write is still composed locally, because by that point
      the fields have been read from the patient's actual words — stating those back
      asserts nothing that was not extracted.
      `app/followup/` is framework-free for the same reason `app/safety/` is. The old
      `agents/symptom/` package is deleted.
- [/] **SOAP summarization demoted from an agent to a service**, as the plan requires:
      four database reads, one structured call and one insert, which is what the four-node
      graph and its conditional edge always were. `services/soap_note_service.py` plus
      `soap_note_prompts.py`, with the prompt text moved verbatim because it decides what a
      reviewed clinical note contains.
      Worth stating because the two workers before it needed correcting for the opposite:
      **this path never fabricated anything.** A failed generation already returned no note
      and stored no row, and it still does — the endpoint now answers 503 rather than
      surfacing an agent error, which is the honest code for "the model is unavailable".
      A note that was generated but could not be *stored* is now also reported as a
      failure rather than returned: a clinician shown a note assumes it was filed.
      **SOAP has no entry in the routing table.** The registry records a primary, a
      fallback, a measured budget and a deterministic path per workload, and none of those
      have been measured for this model on this task, so it keeps the configured Pro model
      it has always used. Adding a routed workload here should follow a measurement rather
      than precede one — recorded so the omission is a decision and not an oversight.
- [/] **WS5 — Document pipeline**: uploads queue work; the Cloud Run Job atomically claims a
      bounded batch with `FOR UPDATE SKIP LOCKED`. Candidate fields must have independent
      page/bounding-box evidence and retain source wording; unsupported or incomplete model
      output ends in `needs_evidence_review` without creating a candidate. The backend
      deployment workflow updates the Job image on every backend release. The Job is deployed,
      but scheduling is deliberately not enabled until the synthetic acceptance set passes.
      See `docs/document-ingestion-worker.md` for the operator checklist and evidence required
      to close WS5.
- [ ] **WS6 — Patient-document retrieval in chat.** A new patient-scoped table, not
      `drug_knowledge_chunks`, which has no patient or document column and a blanket
      authenticated-read policy. The search tool takes a query only; the patient is
      injected from the authenticated session, so the model cannot name whose records to
      search.
- [ ] **WS7 — Medication safety**: a deterministic discrepancy engine over RxNorm
      ingredients and a real ten-question Naranjo score, replacing a severity threshold
      currently mislabelled as a Naranjo pre-screen.
- [/] **WS8 — Remove the graph framework.** Measured rather than assumed before starting:
      only four modules ever imported it, and all four used the identical shape —
      `StateGraph`, `add_node`, `add_edge`, `compile`. They were linear pipelines, about
      1,231 lines of ceremony around what is plainly a sequence of awaits. No checkpointer
      existed and `add_messages` was used on a field nothing read, so nothing was lost by
      writing the sequences out. Removing it therefore did **not** require the OCR
      workstream, which is what the original ordering assumed.
      Triage, symptom and summarization are gone; **document ingestion is the last one**.
      A note on sequencing rather than a technical blocker: `services/ingestion_service.py`
      and `agents/ingestion/graph.py` are both being actively edited in another session
      (420 changed lines between them), and rewiring them mid-edit risks clobbering work
      that is not mine. It is a two-line change when that settles.
      **Deleting the triage tests needed a coverage comparison first, and it found two
      real gaps.** `categorize_llm_failure` was covered *only* by
      `test_triage_safety_overrides.py`, and the function had already moved to
      `app/core/llm_failures.py` — deleting that file would have dropped its coverage
      entirely. And Spanish self-harm reaching the 988 line was asserted nowhere: the
      runtime tests covered English self-harm and Spanish chest pain, which between them
      leave that exact combination untested, and it is the one where a missing translation
      costs the most. Both are now covered before anything was removed.
      Everything else mapped cleanly onto `tests/unit/safety/test_triage_floor.py` and
      `tests/unit/adk/test_chat_runtime.py`, which assert the same properties without a
      runtime behind them.
- [ ] **WS9–WS10 — Persistent sessions and full-flow testing**, including browser
      end-to-end coverage of the three demo journeys.

**Acceptance criteria**

- [x] No model decides a clinical fact. Models explain, summarize, reason, and draft
      candidates; approval, escalation, allergy and duplicate detection, Naranjo scoring,
      and patient scoping are code.
- [ ] Every workload has a deterministic path that renders in both supported locales, and
      a test proves it runs when the model is disabled or over budget.
- [ ] Time to first chunk is under three seconds, and budget expiry produces the
      deterministic answer rather than a hang.
- [ ] A scanned upload produces candidates carrying a page and bounding box, and a chat
      answer about that document cites them.
- [ ] A retrieval test proves the document search tool cannot be steered to another
      patient's records.

---

### SEC-001 — Session tokens must not travel in a URL

**Status:** `[ ]` Backlog

**Priority:** P0

**Owner:** Unassigned; assign before the next deploy that touches chat auth

**Found:** 2026-09-17, while reading Cloud Run logs for an unrelated reason.

`_extract_ws_token` (`backend/src/app/routers/chat.py:306-309`) reads the access token from
`websocket.query_params`, so the patient portal connects to `/ws/chat/{id}?token=<JWT>`.
The server's access log writes the full request path, so **every chat connection writes a
usable session token into Cloud Run logs in plaintext**, readable by anyone with log
access to the project and retained for the log bucket's lifetime. Query strings also reach
proxies, browser history, and any `Referer` header.

Nothing real has leaked: the tokens observed belong to a synthetic demo patient
(`user_metadata.synthetic = true`) and had already expired. The mechanism is live, so the
same connection made by a real account would leak a working credential.

**Scope correction:** this affects **two** routes, not one. `/ws/voice/{patient_id}` shares
chat's `_authenticate_ws_patient`, and the portal opens it with the same `?token=`, so
fixing chat alone would have left the credential in the logs anyway.

- [x] Move the token out of the URL, using `Sec-WebSocket-Protocol`. The client offers
      `["bearer", <jwt>]`; the server reads the token from the second entry and echoes
      back **only** the scheme name, since echoing the token would move the credential
      into a response header instead. The query parameter is no longer accepted at all —
      leaving it as a fallback would have preserved the leak for every client.
- [x] Both routes covered by one change: chat and voice share the auth helper, and each
      `accept()` now echoes the negotiated subprotocol.
- [x] Scrub sensitive query values from log records (`app/core/log_redaction.py`),
      installed in `create_app` before anything can serve a request. Defence in depth, not
      the fix: a credential in a URL still reaches proxies, browser history and `Referer`,
      none of which a log filter can reach.
- [x] Patient portal updated: the URL builders no longer take a token, and the hook
      supplies it via `socketAuthProtocols`. Builders build URLs; the caller supplies
      credentials.
- [ ] **Deploy ordering — this is a hard cutover.** The backend no longer accepts
      `?token=`, so a backend deployed ahead of the portal breaks chat and voice for
      anyone still on the old bundle. Ship both together, or temporarily re-accept the
      query parameter for one release and remove it after the portal has rolled out.
- [ ] Check whether any other route accepts a credential as a query parameter.
- [ ] Rotate nothing: the tokens already written to logs belong to a synthetic demo
      patient and have expired. Confirm that remains true before any real account is used.

**Acceptance criteria**

- [x] A token supplied in the query string is refused even when it is otherwise valid for
      that patient, pinned by an integration test that differs from the accepted case only
      in where the credential travels.
- [x] The handshake echoes the scheme name and never the token.
- [ ] No credential appears in any logged URL, proven end to end against a running server
      rather than only at the filter.

**R1 exit gate**

- [x] A synthetic patient launches through SMART and imports a validated FHIR bundle.
- [x] Every clinical fact can be traced to its source.
- [ ] Clinical actions cannot bypass approval policy.

---

## Milestone R2 — Records and medication safety · Weeks 5–6

### REC-002 — Safe external-record reconciliation

**Status:** `[/]` In progress

**Acceptance path:** A locally assigned clinician imports synthetic SMART or document
data, reviews an evidence-backed candidate, selects individual fields, and explicitly
adds or updates only a medication, condition, or allergy. The decision, source version,
before/after state, and destination record remain auditable. Unsupported external
resources remain evidence-only and do not create local truth.

- [/] Make document and SMART ingestion candidate-only; remove implicit demo extraction. Document ingestion now removes misleading canonical-write/feed stages and requires page-grounded candidate evidence; staging verification remains.
- [/] Bind an external FHIR patient to one local patient after clinician confirmation.
- [/] Add conservative matching and transactional, field-level reconciliation.
- [/] Show candidate-versus-local comparison, evidence, filters, and applied provenance.
- [/] Inventory legacy document-derived rows without silently rewriting or deleting them.
- [ ] Verify the synthetic end-to-end SMART/document reconciliation journeys in staging.

### REC-001 — Complete record ingestion lifecycle

- [ ] Add content-derived document display titles after grounded extraction for future patient
      and clinician uploads. Use only sourced document type, subject and date; never infer
      missing diagnosis/date or rename the original file/storage key. Preserve the original
      filename, document ID and provenance; show a neutral fallback and the original name
      when uncertain. Reuse the display title consistently in document lists, chat catalog,
      citations and care-plan review. Existing-document backfill is a separate opt-in step.
      Ready for scoping with the evidence/portal owners; not part of PAT-005-G's generation fix.
- [/] Establish one safe document-format and viewer contract. The generic clinical-document
      path supports PDF, JPEG, PNG, WebP, and TIFF only; it must render every supported source
      for the patient and assigned clinician, preserve the original artifact, and keep FHIR,
      CDA, and DICOM on dedicated interoperability/imaging paths. See
      `docs/document-format-policy.md`.
- [/] Replace the licensed Syncfusion stub with local PDF.js/native-image viewing, derive a
      bounded PDF preview for TIFF, and pass only a selected document's bounded summary to the
      care coordinator. Implementation and automated coverage are in review; applying migration
      `037_document_source_previews.sql` and completing the synthetic portal acceptance path are
      still required before this item can close.
- [ ] Support patient and clinician PDF/image upload.
- [x] Constrain both upload entry points to the private `documents` bucket's supported clinical formats (PDF, JPEG, PNG, WebP, TIFF), reject unsupported files locally before storage/API calls, and surface the validation error.
- [/] Persist upload, extraction, review, correction, and failure states. The guarded attempt/run lifecycle, OCR/evidence-review states, and safe failure codes are implemented; deployed verification remains.
- [/] Show field-level provenance and confidence. New document candidates require page/excerpt/confidence evidence; richer clinician source presentation remains.
- [ ] Route low-confidence and contradictory fields to review.
- [/] Support approve, correct, reject, retry, and safe deletion. Assigned clinicians may retry retryable processing failures up to three total attempts; reconciliation choices remain separately governed.
- [ ] Reconcile derived data when a document is deleted.
- [ ] Cover duplicate upload, corrupt file, unsupported type, timeout, and expired-session cases.
- [ ] Reconcile approved FHIR candidates into existing authoritative records through explicit clinician choices to add, update, keep, defer, or reject; retain the candidate, source provenance, and audit history, and never mutate source data automatically.
- [/] Provide audited re-projection/backfill for pending imported candidates when mapper versions add useful fields; never overwrite a clinician correction or final review decision. Dry-run and guarded staging application are implemented; production execution requires a reviewed report, an explicit candidate-type scope, and authorization. Legacy CarePlan display repair remains pending a scoped reviewed report.

**REC-001 verification state — 2026-09-20**

- [x] A synthetic born-digital prescription was claimed by the Job after retry and reached a
      terminal `completed` run on attempt 3 (`embedded_text`, one page, one candidate). This
      proves the deployed Job can claim and complete a bounded batch; it does not prove the
      full evidence or viewer acceptance path.
- [x] A synthetic scanned Spanish PNG was claimed and completed in 34.7 seconds on its first
      attempt (`ocr`, one page, one candidate). The candidate is `pending_review`; five retained
      page-1 bounding-box/excerpt records quote the scanned Spanish medication and instructions.
      This proves OCR and source anchoring for the raster path without promoting an unreviewed
      candidate to clinical truth.
- [/] Patient and assigned-clinician raster source viewers both rendered the synthetic Spanish
      document and the patient view displayed a source-grounded explanation. PDF, TIFF-derived
      preview, expired-URL, and unauthorized-access checks remain.
- [/] Document-focused chat did not meet acceptance: opening chat from an existing patient chat
      lost the visible selected-document context and later returned a generic chart answer.
      Product and implementation work is tracked by PAT-004; it is not a reason to weaken
      document authorization or silently pass the acceptance check.
- [/] Operational scheduling and its remaining acceptance gates are tracked explicitly in
      OPS-001 below; do not create the trigger from an incomplete viewer/access test.

**Implementation verification — local, 2026-09-19**

- [x] `scripts/validate_migrations.py`: 38 PostgreSQL migration files validated.
- [x] Backend focused document, chat, and API suite: 106 passed; Ruff and mypy passed.
- [x] Backend full suite: 1,314 passed at 83.46% coverage after the document/viewer changes.
- [x] Patient portal: lint, typecheck, 84 tests, and webpack production build passed.
- [x] Clinician portal: lint, typecheck, 83 tests, and webpack production build passed.
- [x] `npm audit --omit=dev --audit-level=high` reported zero vulnerabilities in both portals.

### OPS-001 — Operate the document-ingestion Job

**Status:** `[x]` Complete for the master's-project demonstration scope

- [x] Deploy `mediagent-document-ingestion` in `us-central1` with one task, parallelism one,
      2 GiB memory, a 300-second timeout, no platform retries, and the server-only worker
      command.
- [x] Apply migrations through `038_document_summary_lifecycle.sql`; the deployed migration
      ledger recorded it on 2026-09-24. The current verifier also found one historical
      `038_appointment_proposal_lifecycle.sql` entry absent from this checkout; reconcile that
      ledger drift before treating a raw migration-count check as release evidence.
- [x] Confirm the backend service and Job release configuration resolve to the same merged image
      digest, and that a manual born-digital PDF plus scanned-Spanish raster execution complete
      with source-backed pending candidates.
- [x] Process the demonstrated synthetic PDF and scanned Spanish raster inputs; their terminal
      runs, candidate evidence, and portal rendering were observed during the 2026-09-20 to
      2026-09-25 acceptance sequence. Additional input-type/load evidence is deferred from the
      master's-project scope.
- [x] Process the generated two-frame TIFF: the 2026-09-20 run reached `completed` with
      `preview_status = ready`; both pages rendered in the clinician viewer, the assigned
      clinician received the original TIFF download, and the patient viewer was manually
      confirmed. The optional patient explanation failed separately with `GenerationProviderError`.
      Bounded derived-preview storage is implemented; a preview failure remains safely
      reviewable rather than creating a fabricated clinical result. A later fresh synthetic
      TIFF reached `summary_status = ready` in both portals on 2026-09-25 UTC.
- [x] Verify access control for the original and TIFF preview. Live no-session requests to the
      deployed patient-document and clinician-source routes both returned `401` on 2026-09-20,
      and the predictable public-storage path was unavailable. Focused local checks passed for
      patient scoping, cross-clinic clinician denial, fresh private source/preview URLs, and
      denial audit events.
- [x] Confirm signed-URL expiry in the deployed environment. Fresh original-TIFF and
      derived-preview URLs were each retained through their one-hour lifetime and then denied
      with Supabase `InvalidJWT` / expired `exp` responses on 2026-09-26. Neither a refreshed
      URL nor an unauthenticated API response was used as substitute evidence.
- [x] Confirm a live cross-user denial with a different unassigned synthetic account. Avery's
      portal session could not discover Maya's documents or patient feed. On 2026-09-26, Jordan's
      unassigned synthetic clinician session called the guarded TIFF source route and received
      `403 AUTHORIZATION_ERROR` with no filename or signed URLs. The audit trail recorded the
      matching clinician/patient `GET` as `NO_CARE_TEAM_ASSIGNMENT_CROSS_CLINIC`. No signed URL,
      real patient data, or care-team assignment change was used for this check.
- [x] Record the available synthetic execution evidence for the demonstration. The observed
      Spanish raster duration (34.7 seconds) and successful TIFF lifecycle checks support the
      demonstration only; they are explicitly not a production throughput or cadence decision.
- [x] Split the optional patient-explanation lifecycle from document ingestion. Migration
      `038_document_summary_lifecycle.sql` adds `summary_status`, `summary_failure_code`,
      `summary_prompt_version`, `summary_attempts`, and `summary_last_attempt_at`, plus
      `claim_pending_document_summary` and a care-team-gated `enqueue_document_summary_retry`.
      Ingestion no longer calls the summary model: it records the clinical result and leaves the
      explanation `pending`, and the Job's second phase builds it from candidates that already
      exist, so a provider outage retries without re-OCRing the source or creating duplicate
      candidate facts. A provider failure stays `pending` with `provider_unavailable` and
      recovers automatically within three attempts; an empty response fails for explicit
      clinician retry. Both portals show the reason instead of an empty panel, and the clinician
      panel carries the retry action. Verified locally on 2026-09-21: 1,340 backend tests pass at
      83.65% coverage with Ruff, Ruff format, mypy, and migration validation clean; the patient
      portal passes 86 tests and the clinician portal 85, both with lint and typecheck. The 2026-09-20
      TIFF run is the case this addresses; re-running it in the deployed environment is part of
      the remaining acceptance steps below.
- [x] Make explanation retries fair and observable. The 2026-09-24 manual Job successfully
      extracted and previewed Maya's two-frame TIFF, but with `DOCUMENT_INGESTION_BATCH_SIZE=1`
      its single explanation claim selected an older provider-failed document first. Migration
      `039_document_summary_retry_schedule.sql` adds a durable next-attempt timestamp, delayed
      provider retries with a bounded anti-starvation lane, expired-claim lease recovery, and
      clinician-visible retry state. It preserves the existing care-team-gated retry action and
      never re-runs OCR or changes candidates. Migration 039 was applied and a subsequent
      synthetic TIFF explanation reached `ready`; forced provider-failure load testing is
      deferred from the master's-project scope.
- [x] Add non-PHI execution telemetry for the document Job. Each run must record its Cloud Run
      execution/task identity, configured batch size, claimed ingestion count and outcome counts,
      plus explanation claim/ready/retry/terminal-failure/not-required counts. This closes the
      2026-09-24 diagnostic blind spot where a successful Job logged a Gemini call but not which
      queue phase made progress. Per-document identity and source content must stay out of logs;
      operators reconcile a particular document through its durable lifecycle timestamps instead.
      The worker must also suppress HTTP-client INFO request lines, because Supabase request URLs
      can carry internal document and patient identifiers; warnings and errors remain observable.
      **Deployed verification — 2026-09-25 UTC:** Task 0 of synthetic execution
      `mediagent-document-ingestion-rd98g` emitted only the structured
      `document_ingestion_started` and `document_ingestion_finished` events (execution, task
      index, batch size, and aggregate outcome counters), then `Container called exit(0)`.
      The finish event recorded zero failures and no HTTP-client request line or source/document
      identifier appeared. It claimed no work, so this verifies the deployed telemetry and log
      privacy contract—not processing throughput.
- [x] **Scope decision — 2026-09-26:** production capacity modelling, sustained queue-age
      monitoring, paging, retry-exhaustion alerting, and load testing are intentionally deferred:
      this is a master's-project demonstration, not a production launch. The Job remains one
      task/parallelism one/batch one; a future production owner must restore these as release
      gates before raising concurrency or relying on this cadence.
- [x] Create `mediagent-document-ingestion-every-5m` in `us-central1` with `*/5 * * * *` and
      timezone `America/Los_Angeles`. On 2026-09-26 it was enabled with OAuth invocation of the
      Cloud Run Job's `:run` endpoint. Dedicated identity
      `mediagent-doc-ingest-sched@medi-agent-490106.iam.gserviceaccount.com` has only
      `roles/run.invoker` on `mediagent-document-ingestion`. Database claiming prevents
      duplicate document claims, but does not serialize separate Job executions. The first
      scheduled execution, `mediagent-document-ingestion-nnz6b`, started at 20:05 UTC and
      completed successfully at 20:07 UTC; the following execution, `...-pb7xt`, began at
      20:10 UTC, confirming the five-minute trigger cadence.

**Production hardening backlog — deliberately outside the master's-project acceptance scope**

1. Repeat PDF and multi-frame TIFF execution tests under representative queue load and record
   full end-to-end durations.
2. Force a provider-failure scenario and verify delayed retry priority, bounded automatic
   attempts, and the clinician retry action without changing source, preview, or candidates.
3. Before a production launch, establish independent bounded ingestion/summary budgets, gather
   at least ten representative runs, configure queue-age/provider/retry/overlap alerting, and
   reassess the five-minute cadence.

**Acceptance criteria**

- [x] Every demonstrated supported synthetic input has a safe terminal outcome and
      source/preview behavior matching its source type.
- [x] A missing patient explanation is visibly unavailable rather than blank, has a durable
      retry path, and cannot alter the immutable source or clinical candidate lifecycle.
- [x] Scheduler configuration is recorded with a dedicated least-privilege invoker and enabled
      for the master's-project demonstration. Production capacity validation remains deferred as
      recorded above.

### OPS-002 — Observe ten completed demonstration executions

**Status:** `[x]` Demonstration observation complete; not a production capacity gate

- [x] Record ten completed executions of `mediagent-document-ingestion`: start and completion
      time, Cloud Run outcome, and aggregate lifecycle telemetry where the deployed structured
      events exist. The first three scheduled executions (`...-nnz6b`, `...-pb7xt`, and
      `...-85x55`) completed after the 20:05, 20:10, and 20:15 UTC triggers; each claimed zero
      ingestion and summary work and finished with zero failures. Use non-PHI telemetry and
      durable lifecycle state only; do not export document names, storage URLs, source text,
      patient identifiers, or tokens into the tracker.
- [x] Summarize the ten-run demonstration observation: ten of ten completed successfully, with
      observed execution durations from about 131 seconds to 356 seconds (about 190 seconds
      average). This combines the earlier manual acceptance runs with the three empty-queue
      scheduled runs. It is demonstration evidence only—not a statistical capacity test,
      alerting design, or authorization to increase concurrency.

### MED-001 — Multi-source medication reconciliation

- [ ] Normalize medication identity using RxNorm when possible.
- [ ] Combine patient, clinician, document, and FHIR medication sources.
- [ ] Detect duplicate therapy, dose change, missing medication, status conflict, and allergy conflict.
- [ ] Attach DailyMed/RxNorm evidence and freshness.
- [ ] Display uncertainty instead of fabricating resolution.
- [ ] Require clinician approval for the canonical medication list.
- [ ] Preserve full reconciliation history.

### MED-002 — Clinician reconciliation experience

- [ ] Build side-by-side source comparison.
- [ ] Support accept, reject, edit, defer, and request-patient-confirmation actions.
- [ ] Display evidence, provenance, confidence, and last-updated time.
- [ ] Reflect approved changes in both portals and FHIR export.

**R2 exit gate**

- [ ] A clinician can turn an uploaded synthetic record into an approved medication list without hidden or fabricated data.

---

## Milestone R3 — Patient companion and follow-up · Weeks 7–8

### PAT-001 — Reliable conversation lifecycle

- [/] Persist sessions, messages, structured state, and tool outcomes. Conversation history and
      state are present, but document focus is still route/session scoped and is completed only
      through PAT-004's per-message contract.
- [/] Recover after refresh, websocket reconnect, provider timeout, and quota exhaustion.
      Existing chat reconnects, but the 2026-09-20 route-reuse defect proves that recovery is not
      complete for selected-document context.
- [ ] Add durable terminal handling for each saved chat turn: persist `processing`, `completed`,
      `failed`, or `interrupted`; enforce a bounded model deadline; reconcile unfinished turns on
      reconnect; and retry the saved turn without duplicating the patient's message. Record only
      safe outcome, duration, revision, and failure-category telemetry.
- [ ] Prevent duplicate messages and duplicate tool actions.
- [/] Show when an answer is based on approved records, general evidence, or insufficient
      information. The general contract exists; source visibility and focused-document behavior
      remain open in PAT-004.

### PAT-004 — Document-focused conversations

**Status:** `[/]` In progress

**Why:** A document must be an explicit, user-visible focus for a chat turn. It cannot be a
fragile route parameter, hidden session state, or an instruction for the model to search a
patient's wider chart. The 2026-09-20 synthetic Spanish-document check proved the current
worker and source viewers, but also exposed that a navigation from an already-open chat can
drop its selected-document context and yield a generic chart answer.

- [ ] Define the focused-chat interaction: retain conversation history, collapse or label older
      conversation where useful, and show a persistent "Discussing: <document>" card before the
      patient sends a question. Prefill a suggested question but never send a model prompt or
      medical claim without an explicit patient action.
- [ ] Make document focus a per-message, server-authorized reference rather than conversation-
      wide state. At send time, authorize the document for the authenticated patient and attach
      only its bounded, patient-facing summary and provenance to that exchange. Persist the
      document reference and context version needed for audit; never persist a signed storage URL
      or let the model choose a document identifier.
- [ ] Define focus lifecycle and safety behavior: a patient may dismiss or replace the focus;
      later general questions have no document context; refresh, reconnect, route reuse, and a
      second browser tab preserve or restore only the selected focus for the intended message.
      A missing, deleted, unauthorized, or summary-less document must produce an explicit
      unavailable-context response, not a general-record answer or an invented interpretation.
- [ ] Keep medical communication source-bound: preserve exact medication names, doses,
      frequencies, and route wording when present; explain terminology in plain language only
      when helpful; do not diagnose, prescribe, infer indication, or turn a focused document
      into a chart-wide answer.
- [ ] Add browser and backend coverage for: navigation from an already-open chat, context-card
      rendering, draft-only suggested question, refresh/reconnect, dismiss/replace behavior,
      patient/clinic isolation, expired/deleted documents, and audit linkage from each focused
      user message to its authorized document context.
- [/] Answer a clear catalog question (for example, “What documents do you have on me?”) from
      authenticated, patient-scoped portal metadata without invoking a model. The response lists
      only documents available in MediAgent, never a signed URL, raw source text, or records from
      another patient; it must not claim that the portal has no record access.
- [/] Show the typing state immediately after a message is sent, rather than waiting for model
      classification. A terminal completion, error, or connection close clears it.

**Acceptance criteria**

- [ ] Selecting **Ask about this document** visibly attaches the intended document before a
      patient sends anything, without erasing prior conversation.
- [ ] The first focused answer names or otherwise identifies its source document and is bounded
      to its authorized evidence; it never silently falls back to the general chart.
- [ ] A later non-focused turn cannot inherit a previous document's context, and an unassigned
      user cannot attach or infer another patient's document.

### PAT-002 — Adherence, symptom, and barrier collection

- [ ] Record medication adherence with patient confirmation.
- [ ] Collect onset, duration, severity, related medication, and red flags for symptoms through
      the sequenced tasks below. A raw chat utterance is not itself a clinician report.
- [ ] Capture barriers such as cost, side effects, access, confusion, and schedule.
- [ ] Create clinician-approved follow-up tasks and care-gap state through PAT-005; an AI or
      unreviewed document must not create a patient-facing obligation directly.
- [ ] Make structured reports visible in the clinician timeline.

#### PAT-002-B — Guided chat symptom intake and patient-confirmed structured report

**Status:** `[ ]` Backlog — sequenced after `PAT-005-C` live proof

**Owner:** Unassigned; patient + backend lanes

**Goal:** Make patient chat the intake surface for symptoms without treating free text as a
clinical conclusion. The Care Coordinator first applies the deterministic safety floor, then
uses bounded follow-up questions to collect only the details needed for a structured report. The
patient reviews and confirms that report before it is visible as a report to the care team.

**Evidence-aware interview contract:** The assistant may retrieve only the patient's authorized,
grounded clinical context—such as approved medication state, relevant document-derived facts and
their citations, and prior confirmed reports—to choose a useful next question. This is retrieval
support, not a source of patient testimony: the report must distinguish patient-entered answers,
document-grounded facts, AI-generated summary text, and later clinician decisions. Do not send an
entire document corpus by default, infer a symptom from a document, or turn a retrieved fact into
something the patient said.

- [ ] Apply `SAFE-002` emergency/self-harm overrides before any symptom follow-up. The reviewed
      escalation copy and required care-team notification take precedence over conversational
      intake; do not ask questions that delay emergency direction.
- [ ] For non-emergency symptom turns, collect only relevant missing fields: onset, duration,
      severity, course, related medication or treatment when supplied by the patient, associated
      symptoms, and red-flag answers. Never diagnose, assign causality, invent a medication link,
      or tell the patient that an ADR has been established.
- [ ] Build a versioned, clinician-approved question library rather than allowing an LLM to
      improvise a medical interview. Its shared ADR fields cover event description and body
      location, onset/course/severity, suspected-product exposure (name, strength, dose, route,
      indication, start/stop/change dates), concomitant products, relevant history/tests, and
      patient-reported outcome. Symptom-specific branches may ask only approved follow-ups (for
      example skin, gastrointestinal, respiratory, neurologic, or medication-use-error details).
- [ ] Create an auditable retrieval snapshot for each intake: retrieved fact/citation identifiers,
      retrieval purpose, and rule/library version. The model receives the least context necessary;
      it must preserve unknown or declined answers rather than filling gaps from a document or
      model inference.
- [ ] Persist a draft intake separately from a confirmed report. The patient can correct,
      abandon, or confirm it; only confirmation creates the clinician-visible structured report.
- [ ] Record the source conversation/turn references, locale, deterministic safety result,
      patient-entered answers, confirmation actor/time, and safe report status needed for audit.
      Do not persist private model reasoning, prompts, or provider traces.
- [ ] Keep clinician notification and care-plan changes under existing review paths. The chat
      agent must not autonomously create a patient-facing task, clinical recommendation, ADR
      decision, or MedWatch record.
- [ ] Enforce patient ownership, care-team assignment, RLS/grants, and API authorization for
      drafts, confirmed reports, cancellation, and retrieval. Browser clients cannot directly
      mutate clinician-facing report state.

**Acceptance criteria**

- [ ] A non-emergency patient can complete a bounded guided intake, see an accurate report
      preview, correct it, and explicitly confirm it.
- [ ] An emergency symptom follows the deterministic escalation path and is never obscured by a
      symptom-worker acknowledgement or an intake questionnaire.
- [ ] A confirmed report reconstructs the patient answers, source turns, safety result, and
      confirmation without representing model output as clinical fact.
- [ ] The patient-facing confirmation view identifies what they reported, what was retrieved from
      their record, and what the assistant summarized; correcting the report never edits source
      documents or prior confirmed reports.
- [ ] An unrelated patient or unassigned clinician cannot list, read, alter, or infer a report.

#### PAT-002-C — Patient symptom timeline and clinician-visible report detail

**Status:** `[ ]` Backlog — depends on `PAT-002-B`

**Owner:** Unassigned; patient + clinician portal lanes

**Goal:** Render confirmed symptom reports as an understandable patient timeline and an
authorized clinician detail record. This makes the report reviewable before pharmacovigilance
work begins; it is not an ADR verdict or a MedWatch submission surface.

- [ ] Show the patient a timeline of their confirmed reports, with timestamp, status, and the
      patient-confirmed fields. Keep unconfirmed drafts private to the patient and clearly
      distinguish them from reports shared with the care team.
- [ ] Give assigned clinicians a detail view containing the structured report, conversation
      provenance, patient confirmation, follow-up answers, safety result, retrieved
      document/medication citations, and later clinician actions. Render patient-reported facts,
      document-grounded context, AI summary, and clinician assessment as distinct sections; do
      not expose hidden prompts or chain-of-thought.
- [ ] Add report-status transitions for clinician review and information requests while retaining
      the original confirmed report immutably. A correction or new patient report must be linked,
      not silently overwrite history.
- [ ] Add timeline/audit events and assignment-denial coverage for patient, clinician, and
      cross-clinic access. Use the existing protected patient/document access patterns.

**Acceptance criteria**

- [ ] A patient sees only their own confirmed reports and can distinguish a draft from a shared
      report.
- [ ] An assigned clinician can inspect a report's patient-confirmed content and provenance;
      an unassigned clinician receives a deny response and an audit event where applicable.
- [ ] A later report or clinician information request preserves the original report history.
- [ ] `PV-001` can consume this confirmed-report contract without scraping chat messages or
      deriving an ADR from an unconfirmed draft.

### SAFE-002 — Deterministic triage overrides

- [/] Finalize emergency, self-harm, severe allergy, and urgent medication rules in English and
      Spanish. The keyword sets cover both locales including unaccented spellings, and carry
      anaphylaxis and the adverse-effect signal. "Finalize" still needs clinical sign-off on
      the wording and coverage, which is not an engineering step.
- [x] Execute safety rules before model routing. `_deterministic_safety_floor` decides self-harm
      and medical emergencies before the model is called and short-circuits the turn. These
      rules previously lived only inside the LLM-failure fallback, so a healthy model that
      misclassified an emergency had nothing behind it.
- [x] Prevent model output from weakening required escalation language. An emergency
      classification skips response generation entirely and returns the localized emergency
      template with escalation forced, so no model output can soften it.
- [x] **Stop the symptom worker replacing an emergency answer. This reached production and
      is a second, separate P0 from the streaming-floor defect fixed in `b72c07f`.**
      Measured end to end through the websocket, not inferred from reading: a patient
      typing "I have crushing chest pain" was classified correctly — the `assistant_start`
      event carried `urgency: emergency`, escalation fired and the care team was notified —
      and then read **"Thanks, I logged your symptom for follow-up."** with no mention of
      911 anywhere in the turn.
      The mechanism is the routing, not the floor. The floor labels a medical emergency
      `intent="symptom"`, `route_for_intent` sends that to the symptom branch, the branch
      aborts the stream before the emergency copy is chunked, and
      `routers/chat.py` then overwrote the buffered 911 template with the symptom worker's
      reply. Self-harm was never affected because it classifies as `mental_health` and
      never enters that branch — which is why the defect stayed invisible: the half of the
      safety copy that was covered by tests was the half that happened to be safe.
      The fix withholds only the *text* when urgency is `emergency`. The symptom report is
      still captured and the A2A delegation still runs, because losing those would trade
      one safety regression for another.
      Pinned by `tests/integration/routers/test_chat_emergency_copy.py`, which asserts on
      the words the patient receives rather than on the classification — the classification
      was already correct when this shipped, and being right there is what hid it.
- [/] Store the triggered rule and escalation result. The rule id is carried on the
      classification and in triage state and logged at WARNING; persisting it alongside the
      conversation turn remains open.
- [x] Add adversarial and multilingual regression coverage. 31 cases across English and Mexican
      Spanish, including a confidently wrong model, co-occurring self-harm and cardiac
      keywords, casing, and unaccented spellings.

- [x] Run the safety floor before the model on the websocket streaming path. Found by the
      September 2026 evaluation; P0. **Re-verified against the code on 2026-09-21, because
      this row described a runtime that no longer exists:** it named
      `TriageAgent.process_stream` and `routers/chat.py:523`, and AI-003 has since rebuilt the
      runtime on the ADK care coordinator.
      - [x] The floor runs before the model. `SafetyFloorPlugin.before_run_callback`
            (`adk/plugins/safety_floor.py`) returns fixed copy to halt the run before any
            agent executes, is registered at `adk/runner.py:95`, and every websocket turn
            reaches it through `routers/chat.py:578` → `chat_runtime.process_stream`. The
            floor consulted in `chat_runtime` is for the classification label only and does
            not re-decide the halt.
      - [x] The L3 outer fallback is localized. `OUTER_FALLBACK_COPY` in `routers/chat.py`
            answers a Spanish-speaking patient in Spanish at the moment the assistant is
            least useful.
      - [x] Added the missing `es-MX` websocket emergency regression test and, in writing
            it, found and fixed a live second P0 the English-only, substring-only test had
            been hiding. `routers/chat.py` closes the stream as soon as `route == "symptom"`
            — which is what the floor labels a medical emergency — to stop the symptom
            worker's reply replacing the coordinator's answer. That guard did not exempt an
            emergency: closing the stream discarded the floor's reviewed 911 copy along with
            it, leaving only the `service_unavailable` text seeded moments earlier
            ("I am having trouble answering right now... try again in a few minutes").
            Confirmed on both locales, reproduced from `main`, and confirmed present in
            English too — the old test's `assert "911" in content` could not catch it because
            `service_unavailable` also contains "911". The fix exempts `assistant_urgency ==
            "emergency"` from the early close and seeds the reviewed emergency copy instead
            of `service_unavailable` when a symptom-route turn produces no content before an
            emergency classification. All patient-facing assertions in
            `test_chat_emergency_copy.py` now check exact reviewed copy, not a substring;
            14 cases pass across both locales, self-harm, and medical emergency. Verified
            2026-09-22: 1,359 backend tests pass at 83.74% coverage, Ruff, Ruff format, mypy,
            and migration validation clean. This closes the original evaluation's P0 gate.
- [ ] Close the inflected-keyword gap in the floor. "I've been thinking about ending my life"
      does not match `end my life` (substring matching, no stemming) while its Spanish mirror
      matches `quitarme la vida`; evolving anaphylaxis ("lips swelling, throat tight") and
      stroke signs ("face droopy, words slurred") match nothing in either language. The September
      harness reports `floor_fires` per scenario so keyword changes can be checked against the
      paired `en-US`/`es-MX` cases (`backend/tests/fixtures/eval/triage_classification.json`).

### PAT-003 — English and Spanish product parity

- [ ] Translate dynamic and static patient journeys.
- [ ] Preserve clinical terminology and evidence meaning across languages.
- [ ] Test language switching mid-session.
- [ ] Validate voice transcript, error, consent, and emergency flows in both languages.
- [ ] Complete clinician/pharmacist review of high-risk bilingual content.

### PAT-005 — Clinician-approved care plans and Today feed

**Status:** `[/]` Claimed — controlled Today-feed loop

**Owner:** Rajeev Chaurasia (integration, Supabase, backend) with clinician-portal and
patient-portal review support.

**Active implementation plan:**
[`specs/pat-005-clinician-approved-today-feed-plan.md`](specs/pat-005-clinician-approved-today-feed-plan.md)

**Why:** The current Today feed deterministically aggregates medications and existing
obligations. It is not an AI-generated care plan, and FHIR `CarePlan` import remains a candidate
path. The product needs a deliberate lifecycle for clinician directions found in discharge
summaries, prescriptions, messages, appointments, or reviewed external records: useful
exercise, diet, monitoring, follow-up, and medication tasks must become patient-visible only
through an authorized clinical decision.

**First demonstration journey:** create one new, wholly synthetic patient and a small,
internally consistent clinical scenario. Upload synthetic clinician-authored source documents
that explicitly contain medication, diet/activity, monitoring, and follow-up directions. The
document worker may extract evidence-backed candidates and the AI may draft clinician-visible
plan suggestions, but neither may publish clinical truth or a patient task. An assigned clinician
must review the evidence and explicitly approve dated plan items. The patient portal then projects
only those approved items into the patient's local-time **Today** feed; the patient can confirm
completion or report an adherence barrier, and that response becomes visible to the clinician.

- [/] Persist the PAT-005 implementation specification and claim the staged backend, clinician,
      patient, and verification work in this tracker.
- [/] Create a fresh synthetic-patient scenario and catalog its fabricated source documents,
      intended clinician decisions, and expected patient-visible feed items. Keep it separate
      from existing fixture patients and use no real or production-like health data. The
      version-controlled `PAT-005-SYN-001` manifest, local PDF builder, and operator guide now
      define three upload-ready source documents and the deliberate Metformin conflict. The
      fresh synthetic account, assigned clinician, and live controlled-journey evidence remain
      open.
- [/] Add the clinician **Review extracted facts** panel for a document: pending candidate name,
      dose, route, instructions, confidence, excerpt/page, and adjacent authorized source
      preview. The first review-panel PR is read-only; it must label candidates `Pending clinician
      review` and expose no approve/reject/edit mutation. The initial refinement renders
      structured medication fields instead of raw JSON, loads the facts and protected source
      independently, and presents the selected candidate beside the authorized preview. Focused
      clinician-portal typecheck, lint, and eight panel tests passed on 2026-09-27; the fresh
      synthetic-scenario and live authorization acceptance remain open.
- [/] Define the source-to-plan drafting boundary: only clinician-authored directions and
      evidence-backed, reviewed candidates can become a suggestion; raw OCR, pending extraction,
      generic model knowledge, and a patient request cannot create a plan item.
- [/] Implement the controlled-loop contract: synthetic document → pending evidence candidate →
      clinician review and explicit plan approval → deterministic Today projection → patient
      completion or barrier → clinician-visible adherence/timeline result. The fresh synthetic
      proof, approval-rollback exercise, and clinician follow-up acceptance remain open.

- [/] Define the care-plan item contract: patient goal, action, schedule or due window, owner,
      start/end and retirement dates, patient completion state, and links to the clinician
      instruction plus source evidence. Preserve plan versions and replacements rather than
      mutating history.
- [/] Build a clinician-side drafting surface. AI may synthesize *suggestions* only from
      clinician-authored directions, approved recommendations, and evidence-backed reviewed
      candidates; pending document extraction, raw OCR, and generic medical knowledge cannot
      create a plan item or patient notification. The automatic-draft worker now accepts only
      an exact, once-only list of grounded fact IDs from the model and copies every
      patient-visible title, instruction, frequency, dose, and route from the candidate itself.
      It records a cross-document medication reconciliation conflict as an approval blocker,
      uses an approved version as the baseline for version `N+1`, and exposes durable
      pending/retry/failed state to the assigned clinician. Only transient provider failures
      retry with bounded backoff; invalid model structure and configuration failures terminate
      with a safe failure code rather than being mislabeled as an outage. The Care Plan panel now opens the
      existing protected document-preview route beside a selected evidence-backed item; a
      clinician-authored entry clearly reports that it has no source document. Migration 041
      backfills one pending request for eligible document-grounded facts completed before the
      lifecycle was deployed; it never republishes a plan or bypasses clinician review. Full
      live proof with the PAT-005 synthetic journey remains open.
- [/] Require an assigned clinician to create, edit, approve, defer, retire, or reject every
      patient-facing item. Record actor, rationale, evidence, effective date, and all review
      changes; determine which actions require a second reviewer under SAFE-001 rather than
      letting the model or a patient self-approve a clinical direction. The legacy clinician
      obligation endpoint now stages a clinician-authored, provenance-backed item in the current
      draft rather than inserting an active Today obligation; the upload UI directs clinicians to
      the Care Plan review tab. Focused authorization, audit, and live approval acceptance remain
      open.
- [/] Project only current approved items into the patient's Today feed by local timezone. Keep
      this projection deterministic: it combines approved care-plan items, prescribed medication
      schedules, appointments, and clinician-sent follow-up tasks, never an LLM response at page
      load. The feed now defensively excludes plan-linked projections unless their immutable item
      belongs to an approved plan and is effective on the patient's selected local date; it returns
      plan version, category, and effective dates for the patient-visible care-plan label. Full
      live approval and timezone acceptance remain open.
- [/] Present a plain-language patient view that identifies the care-team source, distinguishes
      a clinician instruction from an informational suggestion, supports confirmation/barrier
      reporting where appropriate, and directs patients to their care team for changes.
- [/] Handle plan changes safely: supersede or cancel stale tasks, avoid duplicate reminders,
      retain previously completed activity, update both portal views, and test concurrent edits,
      reassignment, patient/clinic isolation, and stale browser state. `PAT-005-D` adds an
      assigned-clinician read-only active-versus-proposed comparison with linked document names,
      all recorded citations, and an unsaved-edit approval guard. It does not yet reconcile a
      new medication fact with a canonical medication, enforce patient-locale wording, or render
      an exact Today preview; those remain required before the v1→v2 live acceptance test.
- [x] `PAT-005-E` harden publication after Maya's review revealed repeated same-source
      citations, Spanish draft wording for an `en-US` patient, and no visible canonical
      medication match. The implementation deduplicates citation presentation, shows active
      medication comparisons, requires a reviewed patient locale and explicit create/update
      decision, and checks both in the atomic publication function. A checkbox records a
      clinician's language verification; it does not machine-translate or prove that Spanish
      text is English. PR #116 merged, migration 042 applied, and authorized synthetic Maya
      review/save/reload/approval exercised on 2026-10-01. Whole PAT-005 acceptance is still open.
- [/] `PAT-005-F` repair live closed-loop defects and repeat the deployed acceptance path.
      Preserve the following acceptance gaps: legacy PRN/unknown cadence in daily totals,
      incomplete TIFF extraction, clinician hydration-warning diagnosis, exact Today preview,
      live isolation with separate accounts, and V1→V2 supersession/history proof.
      Also verify conflict-detail presentation, bilingual parity, effective-date/timezone
      edges, and rollback/audit reconstruction. For legacy PRN, inspect as-needed dosage
      as well as `as recorded` frequency before counting daily due occurrences.
      Do not treat optimistic UI state
      as persisted adherence or count this historical Maya run as the fresh scenario proof.
      Main repair implementation merged/deployed in PR #118; post-merge live acceptance
      still needs verification. Patient naming and the CodeQL empty-except fix merged in
      PR #119. Duplicate medication inputs are repaired with the oversized-evidence fix.
      Includes failure-state visibility,
      service/UI publication guards and pre-write field validation for partial generation.
- [/] `PAT-005-G` repair the incomplete-evidence draft persistence contract. Missing source
      wording must remain cited review blockers, not invented instructions or silently omitted
      facts. Allow clinician edits/removal while publication enforces complete active items;
      check generation state in the atomic SQL publication path. Test actual SQL constraints,
      retry after partial writes, candidate provenance, draft uniqueness, and V1/history
      preservation. Claimed by Rajeev on `codex/care-plan-oversized-evidence`. May start local
      design/tests alongside F, but deployed V2 acceptance in C depends on both. Remote schema
      changes require separate explicit authorization. Reproduction: Maya had 53 eligible
      facts; 42 lacked frequency, while migration 040 required nonempty draft fields.
      Keep those facts cited and blocked rather than filtering or fabricating instructions.
      PR #119 implements missing-field review, transactional evidence/completion writes,
      stale-claim guards and database publication/immutability checks. Seven disposable local
      PostgreSQL cases pass (real constraints and approval function, rollback, permission
      boundary and assignment denial). PR #119 merged/deployed and the user applied migration
      043. The next retry failed because a source-derived title was 338 characters (limit 300).
      Keep the complete fact/citation unchanged; abbreviate only the draft review heading,
      require a reviewed replacement or removal (confirmation alone cannot resolve it), and
      leave oversized instructions/frequency empty and blocked rather than truncating clinical
      wording. Add boundary and real-SQL regression coverage. Deployed V2/reload/history proof
      remains pending; do not mark G or PAT-005 complete from component tests.
      Current fix verification: 1,449 backend tests passed (84.35% coverage; ten opt-in SQL
      cases skipped in that run), all ten disposable SQL cases passed separately, and clinician
      lint/typecheck/build plus 106 tests passed. Read-only preparation of Maya's 53 facts kept
      all 53 items within storage bounds: one oversized heading and 42 review blockers; no model
      call or remote write. This does not prove deployed model generation or publication.
- [ ] `PAT-005-H` simplify patient reminder setup. Show a compact activity/saved-time summary,
      then edit one item in a focused accessible panel reached from Today or settings. Keep
      daily days implicit, show weekday choices only for a sourced weekly cadence, and show
      only the required number of time inputs for a recognized frequency. Explain reminders
      as optional preferences, not changes to instructions or delivered push notifications.
      Preserve meal/event-based wording; ask for the patient's choice instead of assigning
      clinical times. Keep timezone in an advanced control and surface unknown/PRN cadence
      honestly. Test saved/reloaded preferences, cancellation, validation, error retention,
      keyboard/mobile use and locale copy. Ready/unclaimed; design can run alongside G;
      implementation must retain F's server-side cadence safeguards.

**Acceptance criteria**

- [ ] A clinician can turn a reviewed, evidence-backed instruction into a dated plan item and
      see exactly why it appears in the patient's Today feed.
- [ ] The patient sees only effective approved items, can understand their source and next step,
      and never receives an AI-invented diet, exercise, medication, or follow-up task.
- [ ] An audit can reconstruct every published item, source, reviewer decision, revision, and
      feed appearance without relying on a model transcript.

**R3 exit gate**

- [ ] A patient completes record explanation, adherence, symptom reporting, and follow-up in English and Spanish.

---

## Milestone R4 — Clinician review and pharmacovigilance · Weeks 9–10

### CLN-001 — Consolidated review workspace

- [ ] Combine document, medication, symptom, adherence, ADR, and pending-action queues.
- [ ] Add explainable priority, age, source, freshness, and assignment filters.
- [ ] Support approve, reject, amend, defer, dismiss, and request-information decisions.
- [ ] Update queue and patient deep dive without manual refresh.
- [ ] Prevent cross-clinic and unassigned-patient access.

### CLN-002 — Explainable Risk Radar and timeline

- [ ] Calculate risk from versioned, reproducible signals.
- [ ] Display contributing factors and freshness for every risk level.
- [ ] Show document, medication, symptom, adherence, message, appointment, approval, and action events chronologically.
- [ ] Link events to source evidence and reviewer outcomes.

### PV-001 — ADR and Naranjo workflow

**Status:** `[/]` Partial — a read-only ADR evidence queue works, while the confirmed
symptom-report contract still depends on `PAT-002-B` and `PAT-002-C`.

**Owner:** Ganesh Thampi; pharmacovigilance + clinician lanes

**Boundary:** This work begins from a patient-confirmed, clinician-visible symptom report—not
from an unconfirmed chat message, model classification, or raw document text. It is clinician
decision support, never autonomous ADR determination or external reporting.

- [x] Replace empty pharmacovigilance modules with tested implementation.
- [/] Consume the confirmed symptom-report contract with its patient answers, safety result, and
      provenance; preserve the separation between patient testimony, document context, and
      clinician assessment. Let a clinician request missing information without rewriting the
      original report.
- [/] Use the approved intake library and patient-confirmed report to identify missing ADR facts:
      event/outcome, suspected product and therapy dates, concomitant products, relevant tests or
      history, and reportable seriousness indicators. The clinician decides relevance, causality,
      seriousness, and whether further information is needed.
- [x] Calculate Naranjo assistance deterministically where possible.
- [x] Keep model-generated classification separate from reviewer decision.
- [ ] Support reassessment when evidence changes.

**Acceptance criteria**

- [/] A clinician can review a confirmed report, document an ADR decision or uncertainty, and
      see the evidence/provenance used for each conclusion.
- [x] Naranjo assistance exposes its inputs and is never presented as the clinician's final
      decision.
- [/] An unassigned clinician cannot access the report or ADR review, and all reviewer actions
      are auditable.

Verification evidence — 2026-10-02: synthetic patient chat produced two persisted draft ADR
assessments with patient-grounded evidence and deterministic Naranjo score 3 (`Possible`). The
assigned clinician API and portal queue display the score inputs and missing questions without
private model reasoning. The queue is intentionally read-only until the confirmed-report,
reviewed-decision, evidence-request, audit, and reassessment behavior is implemented.

### PV-002 — MedWatch draft lifecycle

**Status:** `[ ]` Backlog — depends on clinician ADR review (`PV-001`)

**Owner:** Jeevan Kurian; clinician portal + pharmacovigilance lanes

**Boundary:** The outcome is an editable, clinician-approved export artifact. This slice must
never submit a report to FDA/MedWatch or portray a draft as filed.

- [ ] Generate an editable MedWatch-compatible draft only from patient-confirmed facts,
      document-grounded facts with citations, and clinician-approved assessments. Keep unknown,
      declined, or unsupported fields empty rather than inferred.
- [ ] Map populated patient, event/outcome, suspect-product/therapy-date, concomitant-product,
      test/history, and reporter fields to their source evidence. A patient statement must remain
      attributable to the patient; a document fact must retain its document citation.
- [ ] Require clinician/pharmacist approval.
- [ ] Export the approved draft without submitting it.
- [ ] Audit edits and reviewer sign-off.

**R4 exit gate**

- [ ] Every clinical recommendation has evidence, reviewer state, and an auditable outcome.

---

## Milestone R5 — Scheduling, messaging, voice, and continuity · Weeks 11–12

### SCH-001 — Appointment lifecycle

- [ ] Clinician or approved workflow proposes slots.
- [ ] Patient accepts, declines, or requests alternatives.
- [ ] Confirmed appointment appears in both portals.
- [ ] Support calendar export and timezone-safe rendering.
- [ ] Handle conflicts, cancellation, rescheduling, expiration, and duplicate confirmation.

### COM-001 — Care-team communication and notifications

- [/] Complete patient-to-care-team and clinician-to-patient message paths. Clinician-to-patient
      send (in-app and email) existed as backend-only endpoints with no frontend. Added: backend
      list endpoints (`GET /me/patients/{patient_id}/messages` and `GET /me/messages`), clinician
      inbox page replacing the static placeholder, compose form on the patient deep-dive Chat tab,
      and integration + component tests. Patient-to-clinician origination remains unbuilt.
- [ ] Require approval for clinical outbound messages.
- [ ] Support opted-in administrative reminders.
- [ ] Add retry, deduplication, delivery state, and operations queue.
- [ ] Create care-gap tasks for missed follow-up.

### VOI-001 — Text-first voice experience

- [ ] Support streaming capture/playback when the configured provider is available.
- [ ] Persist the canonical transcript and structured state.
- [ ] Support interruption, reconnect, cancellation, and text fallback.
- [ ] Validate English and Spanish terminology and safety behavior.
- [ ] Never make audio the only way to complete a journey.

### CON-001 — Multi-provider continuity

- [ ] Build provenance-preserving longitudinal timeline.
- [ ] Generate an evidence-linked handoff summary for clinician review.
- [ ] Export a portable patient care summary.
- [ ] Respect care-team visibility and patient restrictions.

**R5 exit gate**

- [ ] The full clinic care loop works without manual database intervention.

---

## Milestone R6 — Standards, evaluation, and hardening · Weeks 13–14

### STD-001 — CDS Hooks integration

- [ ] Implement service discovery.
- [ ] Implement `patient-view` risk/continuity cards.
- [ ] Implement `medication-prescribe` medication-safety cards.
- [ ] Include source links, evidence, and override-safe suggestions.
- [ ] Add conformance, malformed-context, timeout, and authorization tests.

### STD-002 — Real MCP server

- [ ] Replace the custom tool ABC with an official protocol server.
- [ ] Expose approved document, evidence, medication, follow-up, and scheduling tools.
- [ ] Enforce schemas, authorization, audit context, request IDs, and safe errors.
- [ ] Add protocol and security conformance tests.

### STD-003 — Focused A2A delegation

- [ ] Publish `/.well-known/agent-card.json`.
- [ ] Implement Care Coordinator to Medication Safety Worker delegation.
- [ ] Support submit, status, artifacts, cancellation, idempotency, and failure.
- [ ] Remove obsolete `/.well-known/agent.json` claims.
- [ ] Add end-to-end delegation and authorization tests.

### EVA-001 — Internal model and safety evaluation

- [ ] Create 120 synthetic scenarios across all required risk classes.
- [ ] Mirror high-risk scenarios in English and Spanish.
- [ ] Obtain clinician/pharmacist adjudication for at least 40 high-risk cases.
- [/] Compare providers on accuracy, safety, evidence, latency, reliability, and zero-cost
      feasibility. `scripts/compare_providers.py` runs one prompt across MedGemma, Flash, Pro
      and NIM and reports latency and outcome per provider. First measurement recorded below.
- [ ] Select default and fallback providers from results.
- [ ] Store repeatable evaluation inputs, rubrics, results, and environment metadata.

**Provider evidence — 2026-09-11 — `openai/gpt-oss-20b` via NVIDIA NIM**

Single-provider run, `--max-tokens 4096`, prompt "I've had a mild headache for two days, no
fever." No Gemini baseline was captured in the same run, so the comparison is one-sided and
the latency figure stands on its own rather than as a ratio.

A Flash baseline was not merely skipped — it was **unobtainable at the time**. The Flash slot
still defaulted to `gemini-3.1-flash-lite-preview`, which Google retired on 2026-05-25, so any
Flash run would have failed for reasons unrelated to the comparison. PR #90 restores that slot;
re-run this prompt with `--models flash,nim` once it lands to complete the pair.

- **34.0 s, 5,656 characters.** Disqualifying for the Flash slot on latency alone: that slot
  serves patient chat over a websocket, which has a ceiling in the low seconds.
- **The model volunteered dosed medication advice unprompted** — "ibuprofen 200–400 mg,
  acetaminophen 500–1000 mg" — to a patient, with no clinician in the loop. MediAgent is
  supervised decision support and not an autonomous clinician, so this is a product-boundary
  failure rather than a style preference. Any future use of this model in a patient-facing
  path needs a system instruction that forbids it, and a test that proves the constraint holds.
- Output length and markdown tables do not fit a chat bubble, and the reply closed with five
  multi-part questions, duplicating work `SymptomAgent` already owns.
- In its favour: the red-flag escalation checklist was clinically sound, and the deterministic
  safety floor correctly did not fire, since the prompt carries no emergency keyword.
- **Cost shape**, measured separately on a trivial prompt: 281 completion tokens for an answer
  worth roughly 38 of them. Close to seven eighths of the output budget went to the reasoning
  trace, which bears directly on zero-cost feasibility.

**Verdict:** rejected for the Flash slot. Worth a later look for the Pro slot, where batch
work tolerates the latency and long structured output is the intent — the dosing behaviour
would still have to be constrained and verified first.

### QUA-001 — Release hardening

- [ ] Test RBAC, RLS, object ownership, clinic isolation, and privilege escalation.
- [ ] Test timeouts, quotas, network loss, duplicate requests, malformed FHIR, and provider outage.
- [ ] Meet WCAG 2.2 AA on core journeys.
- [ ] Meet responsive PWA requirements on supported mobile and desktop browsers.
- [ ] Add useful structured logs, traces, health checks, and alerting.
- [ ] Confirm no secret, PHI, hardcoded identity, or production mock state is exposed.

**R6 exit gate**

- [ ] Safety, interoperability, protocol, security, and product thresholds pass.

---

## Milestone R7 — Freeze and delivery · Weeks 15–16

### REL-001 — Release qualification

- [ ] Freeze features on 2026-12-04.
- [ ] Run clean-install and migration rehearsal.
- [ ] Run full unit, integration, browser, voice, bilingual, security, and recovery suites.
- [ ] Resolve all release-blocking defects.
- [ ] Tag the final release candidate and production demonstration release.

### REL-002 — Demonstration deployment

- [ ] Deploy backend and both portals using synthetic data.
- [ ] Verify domains, TLS, OAuth redirects, environment variables, scaling, and health checks.
- [ ] Validate demo accounts and reset workflow.
- [ ] Prepare a fallback recording for external-service outages.

### REL-003 — Product delivery package

- [ ] Prepare the complete clinic care-loop demonstration script.
- [ ] Prepare architecture, interoperability, safety, and operations briefs.
- [ ] Prepare installation, deployment, reset, and troubleshooting guides.
- [ ] Prepare startup product narrative and concise pitch materials.
- [ ] Record limitations honestly: synthetic data, supervised CDS, public sandbox, and no HIPAA-production claim.

**Final acceptance gate**

- [ ] All eight product journeys pass end to end.
- [ ] Emergency red-flag recall is 100% on the deterministic suite.
- [ ] Unauthorized clinical actions are zero.
- [ ] Approval and audit coverage are 100% for clinical actions.
- [ ] Evidence-to-source validity is at least 95%.
- [ ] Required-field extraction accuracy is at least 90%.
- [ ] Medication-discrepancy precision and recall are each at least 90% on the internal set.
- [ ] No material English/Spanish safety disparity remains.
- [ ] Full CI completes in 20 minutes or less.
- [ ] No critical dependency vulnerability remains.
- [ ] No empty functional module, reachable `NotImplementedError`, production mock success, or hardcoded patient identity remains.

---

## Team allocation

`.agent/TEAM.md` is the authoritative roster. This table mirrors it; update both together.

| Member | Primary lane | Required secondary review |
|---|---|---|
| Rajeev Chaurasia | Platform, Supabase, security, FHIR, SMART, deployment | Clinician authorization |
| Ganesh Thampi | Worker runtime, provider adapters, evidence, safety, evaluation | Voice and ADR |
| Tushar Singh | Patient portal, bilingual companion, adherence, voice | Scheduling |
| Jeevan Kurian | Clinician portal, review queues, messaging, continuity | FHIR workflow UX |

- [x] Replace Engineer 1–4 with team-member names.
- [ ] Assign an owner for pharmacovigilance (`PV-001`, `PV-002`) before `PAT-002-C` hands off
      the confirmed symptom-report contract. The superseded placeholder table listed PV under
      the clinician-portal lane; `TEAM.md` does not, so this later sequenced work is currently
      unowned.
- [ ] Assign the first integration owner.
- [ ] Assign a clinician/pharmacist review schedule.
- [ ] Require one peer review for every PR.
- [ ] Require safety-owner and clinical review for safety-sensitive behavior.
- [ ] Demonstrate one integrated vertical increment every week.

## Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-08-18 | Product is a supervised closed-loop outpatient clinic platform | Generic multi-agent healthcare assistants are no longer differentiated |
| 2026-08-18 | Polypharmacy chronic care is the evaluated cohort | Strong clinical need and alignment with existing portals/data |
| 2026-08-18 | English and Spanish are committed | Depth and clinical validation over shallow language breadth |
| 2026-08-18 | Synthetic/de-identified data only | Zero-cost AI tiers are incompatible with a real-PHI production claim |
| 2026-08-18 | SMART/FHIR public sandbox is mandatory | Interoperability must be demonstrated, not described |
| 2026-08-18 | Clinical actions use tiered approval | Clinicians retain authority over clinical conclusions and actions |
| 2026-08-18 | Product delivery outranks research publication | Evaluation supports engineering and safety decisions |
| 2026-08-18 | REV-001 is the first engineering task | Trustworthy, bounded CI is required before feature delivery |
| 2026-09-09 | ~~NVIDIA NIM is out of scope for provider comparison~~ | Superseded on 2026-09-11. The entry assumed no endpoint was reachable; NIM's cloud API is, and the premise was wrong |
| 2026-09-10 | Provider routing is decided per workload from harness evidence, with a deterministic layer first and GA model IDs only in production defaults | The September evaluation found stale routing evidence, an unreachable medical-model endpoint, unsupported SDK paths, and missing telemetry/kill switches. Active runtime work is in `AI-003`; current controls and limits are in `docs/decisions/ai-runtime-2026-09.md`. |
| 2026-09-10 | Free-tier endpoints are for synthetic evaluation only and are not a deployment lane | AI Studio free-tier terms allow training and human review of inputs and carry no BAA; the project's key is also on depleted prepaid billing. Zero-cost serving means self-hosted open weights, which need a GPU host for anything beyond 4B-class models |
| 2026-09-11 | NVIDIA NIM is the third comparison provider | It is reachable through NVIDIA's hosted catalog over an OpenAI-compatible API. It is also the only candidate not hosted by Google, so its failures are the least likely to correlate with MedGemma's and Gemini's — which is what makes a reliability comparison mean anything |
