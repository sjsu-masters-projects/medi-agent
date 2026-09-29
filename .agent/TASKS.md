# MediAgent — Active Delivery Tracker

> **Active plan:** [PAT-005 — Clinician-Approved Care Plan to Today Feed](specs/pat-005-clinician-approved-today-feed-plan.md)
>
> This is the live team board. It contains only current work, sequenced backlog, owners, dependencies, and acceptance gates. Completed implementation evidence belongs in PRs, decision documents, release notes, and Git history.

## Working rules

- **Ready** — one teammate may claim it on a new branch.
- **Claimed** — has an owner/branch; do not overlap without coordination.
- **Blocked** — name the exact unblocker.
- **Sequenced** — do not claim until the predecessor is complete.
- **Deferred** — outside the master's-project proof.

A task is done only with authorization, error/safety behavior, tests, audit behavior where relevant, and visible acceptance evidence.

## Product snapshot

MediAgent is a synthetic-data, supervised clinical decision-support prototype for outpatient chronic care and polypharmacy. It does not diagnose, prescribe, autonomously change medication, or submit regulatory reports.

| Journey | Working now | Next product gap |
| --- | --- | --- |
| Access | Login, assignment checks, denial audit, private source/preview routes, protected WebSocket auth | Broader security qualification |
| Documents | PDF/image/TIFF ingestion; embedded-text/OCR reading; evidence anchors/candidates; private previews; explanation retry | Review/reconciliation acceptance and care-plan live proof |
| Care plan / Today | Versioned draft/review/approval/projection implementation; deterministic Today; completion/barriers | One fresh synthetic closed loop |
| Chat | Care Coordinator, emergency floor, persistence, immediate typing | Durable interrupted-turn recovery and selected-document conversations |
| Symptoms | Emergency floor and basic routing | Patient-confirmed report, timeline/detail, clinician ADR review |
| Interoperability | SMART-on-FHIR R4 candidate import | Reconciliation/export/conformance |
| Operations | Five-minute synthetic document Job, safe aggregate logs | Production capacity/alerting deferred |

## Delivery order

PAT-005-A diagnostics → PAT-005-B diagnose failed request → PAT-005-C live proof
→ PAT-002-B guided symptom intake / patient confirmation → PAT-002-C timeline/detail
→ PV-001 clinician ADR/Naranjo review → PV-002 approved MedWatch draft/export

Independent work: PAT-001-A chat recovery; PAT-004 document chat; SAFE-002-A safety language; CI-001 Acquit evidence.

## Current queue

| ID | State | Owner / branch | Next result | Dependency |
| --- | --- | --- | --- | --- |
| PAT-005-A Safe draft-failure diagnostics | Claimed | Rajeev — codex/pat-005-care-plan-observability | Safe worker event: request ID, attempt, outcome, failure code only. | No patient IDs, clinical text, prompts, source facts, or provider exception content in logs. |
| PAT-005-B Diagnose existing failed draft | Blocked | Rajeev + synthetic clinician | Retry through clinician UI; record safe failure code from scheduled Job. | PAT-005-A deployed. Do not re-upload or manually run Job. |
| PAT-005-C PAT-005-SYN-001 proof | Blocked | Rajeev + test accounts | Draft consolidation, blocker resolution, approval, Today, completion/barrier, clinician/audit proof. | PAT-005-B resolved; current product completion gate. |
| PAT-001-A Durable chat-turn recovery | Ready | Unassigned — patient/backend | Persist terminal state, deadline, reconnect reconciliation, and no-duplicate retry. | Safe outcome/duration/failure telemetry only. |
| PAT-004-A Document catalog chat | Claimed | Rajeev — codex/pat-004-chat-document-catalog | Merge PR #109 and manually verify catalog/typing behavior. | Metadata only; no signed URLs, raw source, or model call. |
| PAT-002-A Adherence/barrier evidence | Sequenced | Unassigned — patient/clinician | Exercise completion and all barriers on approved effective plan item. | Runs with PAT-005-C; reuse current model. |
| PAT-002-B Guided symptom intake | Sequenced | Unassigned — patient/backend | Bounded safe chat intake and patient confirmation of structured report. | After PAT-005-C; blocks PAT-002-C/PV-001. |
| PAT-002-C Timeline/report detail | Sequenced | Unassigned — patient/clinician | Patient timeline plus assigned-clinician report detail. | After PAT-002-B; blocks PV-001. |
| SAFE-002-A Safety-language coverage | Blocked | Clinical reviewer + safety owner | Approve EN-US/es-MX inflection, anaphylaxis, and stroke wording. | Clinical sign-off before engineering wording change. |
| CI-001-A Acquit evidence | Ready | Unassigned — CI | One eligible selective observation with replay/full-suite evidence. | Canary until ten safe observations. |

## Active task acceptance

### PAT-005 — Clinician-approved care plan to Today feed

- [ ] Fresh synthetic en-US scenario has clinician/patient uploads and source-backed candidates.
- [ ] Quiet-window documents create one draft; clinician can inspect source, resolve conflict, and approve.
- [ ] Approval atomically projects items; failed publication retains prior approved plan.
- [ ] Only approved/effective projections appear in patient-local Today.
- [ ] Completion and every barrier become clinician-visible.
- [ ] Version, citations, decision, projections, and outcome reconstruct from audit records.
- [ ] Unassigned users cannot read, preview, edit, approve, or report.

### PAT-001-A — Durable chat-turn recovery

- [ ] Persist pending, processing, completed, failed, and interrupted turn states.
- [ ] Reconcile refresh, reconnect, provider timeout, and Cloud Run revision replacement.
- [ ] Retry saved failed/interrupted message once without creating a duplicate.
- [ ] Clear typing on every terminal/reconciled state; log safe outcome only.
- [ ] Cover authorization and duplicate-retry denial.

### PAT-004 — Document-focused conversations

- [/] Clear catalog questions return only the authenticated patient's document names/types.
- [/] Typing begins on send.
- [ ] Add Ask about this document context, protected preview, refresh/reconnect, dismiss/replace.
- [ ] Keep responses source-bound; test expired/deleted document and patient/clinic isolation.

### PAT-002-B — Guided symptom intake and confirmed report

- [ ] Run emergency/self-harm floor before follow-up questions.
- [ ] For non-emergency turns collect bounded onset, duration, severity, course, red flags, and patient-supplied medication context.
- [ ] Keep draft intake separate from patient-confirmed clinician-visible report.
- [ ] Preserve source turns, locale, safety result, answers, confirmation, and status.
- [ ] No diagnosis, causality, care task, ADR decision, or MedWatch output.
- [ ] Enforce RLS/grants, assignment, backend-only mutation, and denial tests.

### PAT-002-C — Symptom timeline and clinician detail

- [ ] Patient sees only confirmed reports; drafts stay private.
- [ ] Assigned clinician sees confirmed content, provenance, safety result, and later actions.
- [ ] Information requests/later reports link to original; never overwrite it.
- [ ] Timeline/audit and cross-user/cross-clinic denial tests pass.
- [ ] Provide the confirmed-report contract for PV-001.

### SAFE-002 — Deterministic triage

- [x] Emergency/self-harm floor runs before model work and cannot be overwritten by symptom routing.
- [x] Emergency copy is localized in EN-US/es-MX.
- [ ] Clinically approve and test remaining inflection, anaphylaxis, and stroke coverage.
- [ ] Persist triggered rule and escalation result in turn audit.

### REC-001 — Document ingestion lifecycle

OCR is already implemented: embedded text is recovered where available; scans, raster images, and TIFF frames use OCR before model structuring creates pending evidence-backed candidates. OCR and AI never create clinical truth.

- [x] Synthetic PDF, scanned Spanish raster, and multi-frame TIFF ingestion with private previews/source anchors.
- [x] Source/preview expiry and unassigned-user denial.
- [ ] Clinician review/correction/rejection/retry and low-confidence/conflict routing acceptance.
- [ ] Full viewer acceptance including expired/deleted source behavior.
- [ ] Explicit clinician reconciliation of approved FHIR/document candidates.

### AI-003 — Runtime/provider contract

- [x] Safety floor, registry, fallback, safe outcomes, and native structured output are implemented.
- [ ] Verify deployed model pins, transport, budgets, kill switches, and safe failure behavior.
- [ ] Complete Care Coordinator/follow-up/document-tool authorization and delegation tests.
- [ ] Treat format/schema failure as runtime failure with fallback/safe outcome, never clinical quality.

### CI-001 — Selective backend tests

- [ ] Record nine additional eligible selective observations.
- [ ] Fail closed to full suite for migrations, dependencies, broad foundations, unknown imports, and analysis errors.
- [ ] Enforce only after ten safe observations and reviewed design.

## Sequenced backlog

| ID | Outcome | Predecessor | Boundary |
| --- | --- | --- | --- |
| CLN-001 | Consolidated clinician queue | PAT-005-C | Render proven artifacts; no competing decision lifecycle. |
| CLN-002 | Explainable risk/timeline | CLN-001 + PAT-002-C | Every signal links to provenance/reviewer outcome. |
| MED-001/002 | Medication reconciliation + clinician review | PAT-005-C | Explicit clinician decisions, no automatic truth overwrite. |
| PV-001 | Clinician ADR/Naranjo review | PAT-002-C | Starts from confirmed report; no autonomous ADR decision. |
| PV-002 | Clinician-approved MedWatch draft/export | PV-001 | Editable evidence-linked export; never FDA submission. |
| PAT-003 | EN-US/es-MX end-to-end parity | PAT-005-C | Bilingual clinical review required. |
| SCH-001 / COM-001 | Appointments / approved communication | Proven care-plan loop | No autonomous booking or clinical messaging. |
| VOI-001 | Text-first voice | PAT-003 | Text/transcript fallback and safety parity. |
| CON-001 | Multi-provider continuity | CLN-002 | Assignment, provenance, and handoff first. |
| INT-002/003 | FHIR reconciliation/export and SMART maturity | MED-001 | Imports remain candidates until reviewed. |
| STD-001–003 | CDS Hooks, official MCP, focused A2A | Proven internal flows | No compatibility claim without conformance. |
| EVA-001 | Synthetic evaluation and adjudication | Stable AI-003 contract | Evidence only; not a substitute for safety/review. |

## Deferred hardening

Not PAT-005 blockers for this master's-project demonstration:

- Production queue-age/retry/latency alerts, load testing, capacity planning, and higher Job concurrency.
- Broad release hardening: RBAC/RLS/privilege drills, WCAG/PWA qualification, observability, and external-service failure exercises.
- Release package: demo script, deployment/reset guide, architecture/safety/interoperability brief, and explicit synthetic-data limits.
- Final production qualification or production-readiness claims.

## Verified foundation

- Private storage, signed-URL expiry, protected source/preview routes, and cross-user denial/audit.
- Five-minute synthetic document Job: one task, parallelism one, batch one.
- Evidence-backed candidate ingestion for PDF, scanned Spanish raster, and multi-frame TIFF.
- SMART-on-FHIR sandbox import as pending candidates.
- Deterministic emergency floor in EN-US/es-MX.
- Care-plan lifecycle, review surface, protected preview, deterministic Today projection, completion/barrier model.
- Required CI, migration syntax, dependency/secret scanning; Acquit remains canary.

## Ownership and safety boundaries

.agent/TEAM.md is the roster. Update the queue owner/branch before starting. Assign pharmacovigilance ownership before PAT-002-C hands off its report contract. Safety-sensitive wording and clinical decisions require clinician/pharmacist review.

- Synthetic or rigorously de-identified data only.
- Patient-facing clinical instructions require clinician approval.
- Imported/FHIR/document data stays provenance-backed until reviewed.
- Never expose credentials, signed URLs, raw private sources, prompts, provider traces, or private chain-of-thought.
- No autonomous medication changes, diagnosis, regulatory submission, or production-readiness claim.
