# MediAgent — August–December 2026 Execution Tracker

> **Active plan:** [`specs/mediagent-revival-aug-dec-2026.md`](specs/mediagent-revival-aug-dec-2026.md)
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

| Area | Status | Evidence / risk |
|---|---|---|
| Repository | Revival work committed locally | Local `main` contains reviewed revival commits atop `origin/main`; push is intentionally pending |
| Historical work | Needs reconciliation | Two remote branches and one April stash remain |
| Patient portal | Partial | Major screens exist; several workflows require real end-to-end completion |
| Clinician portal | Partial | Dashboard/deep dive exist; consolidated review and action lifecycle incomplete |
| Backend foundation | Partial | Broad API and test base; empty modules and reachable placeholders remain |
| Records ingestion | Functional foundation | Needs provenance, correction, FHIR validation, and reconciliation hardening |
| Chat and triage | Functional foundation | Needs provider abstraction, bilingual qualification, recovery, and full journey tests |
| Pharmacovigilance | Not complete | Empty agent/tool files and incomplete ADR service paths |
| Scheduling and communication | Not complete | Foundations exist; complete patient/clinician lifecycle does not |
| Interoperability | Not complete | FHIR-aligned only; no genuine SMART launch or CDS Hooks integration |
| MCP/A2A | Not complete | Existing MCP is custom; A2A implementation files are empty |
| CI | First PR run green; main confirmation pending | Run 32280310908 passed all required gates in 5m 46s; three green GitHub runs on `main` are still required |
| Dependency security | Local gate green; GitHub refresh pending | Exact Python locks and all three npm lockfiles report zero known vulnerabilities on 2026-08-19 |
| Demo data | Staging access verification pending | The canonical fixture is seeded and idempotency-verified in staging; RLS isolation and portal login journeys remain |

## Active task

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
- [ ] Validate Acquit across at least 10 selective PRs with zero canary alarms.
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
- [x] Document deterministic fixture accounts without embedding secrets in the repository.
- [x] Run the approved staging seed and verify table counts, source-specific mappings, ledger checksums, and idempotency.
- [/] Verify RLS isolation and clinician/patient login journeys against the seeded staging environment.

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

**R0 exit gate**

- [ ] REV-001 through REV-005 acceptance paths are green.
- [ ] Repository contains no ambiguous preserved work.
- [ ] Documentation reflects the intended product and actual implementation.
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
- [/] Map Patient; Practitioner, Organization, and CareTeam remain deferred because the local clinician/care-team model is authoritative.
- [x] Map Condition, AllergyIntolerance, MedicationRequest, and MedicationStatement.
- [/] Map Observation, DocumentReference, and CarePlan; Appointment and Communication remain deferred.
- [ ] Generate Provenance and AuditEvent resources.
- [/] Validate supported resource shape before persistence; identifier-quality and export validation remain deferred.
- [x] Handle missing, partial, duplicate, and unsupported resources safely.
- [/] Add import fixture tests; FHIR export and round-trip fixtures remain deferred.

**Plan:** `.agent/specs/int-002-003-interoperability-plan.md` defines the mapping
registry, import-envelope persistence, duplicate rules, and fixture evidence. Exact R4
sandbox conformance is an end-to-end acceptance test; the maintained runtime validator
uses the compatible R4B model.

### INT-003 — SMART-on-FHIR sandbox launch

- [x] Implement `/api/v1/smart/launch` and `/api/v1/smart/callback`.
- [/] Validate PKCE, OAuth state, issuer, and expiry; token audience/scope conformance awaits a live sandbox registration.
- [x] Consume patient and encounter launch context.
- [/] Import the supported patient bundle; live public-sandbox verification awaits the replacement Supabase project and Cloud Run callback.
- [/] Show import status, raw-resource warnings, and review handoff in the clinician portal; lineage inspection is exposed by API.
- [x] Document sandbox setup and reproducible conformance test.

**Plan:** Build SMART authorization-code + PKCE handling after the INT-002 import
registry, then bind the resulting imported-record session to a locally authenticated
clinician. The plan records sandbox, HTTPS callback, and replacement-Supabase
prerequisites; none of them block fixture or route-test work.

### SAFE-001 — Approval and audit infrastructure

- [x] Define `ClinicalRecommendation`, `ApprovalDecision`, `ActionEnvelope`, and `AuditRecord`.
- [/] Enforce tiered action authority server-side; feature-specific action executors will adopt the gate as they are implemented.
- [x] Require idempotency keys for action envelopes.
- [x] Record proposer, evidence, reviewer, edits, decision, executor, and outcome.
- [x] Prevent approval by an unauthorized, unassigned, or proposing clinician.
- [x] Add replay and duplicate-action tests.

### AI-001 — Provider-neutral AI and voice interfaces

- [x] Define model capabilities and structured error taxonomy.
- [/] Wrap existing text clients behind the interface; concrete provider registry migration remains next.
- [ ] Add optional MedGemma and NVIDIA NIM comparison adapters.
- [/] Define the voice-provider interface; live voice transport migration remains next.
- [x] Record latency, model/version, tool calls, token/usage data, and fallback path in the provider response contract.
- [x] Guarantee deterministic text fallback when audio is unavailable.

**R1 exit gate**

- [ ] A synthetic patient launches through SMART and imports a validated FHIR bundle.
- [ ] Every clinical fact can be traced to its source.
- [ ] Clinical actions cannot bypass approval policy.

---

## Milestone R2 — Records and medication safety · Weeks 5–6

### REC-001 — Complete record ingestion lifecycle

- [ ] Support patient and clinician PDF/image upload.
- [ ] Persist upload, extraction, review, correction, and failure states.
- [ ] Show field-level provenance and confidence.
- [ ] Route low-confidence and contradictory fields to review.
- [ ] Support approve, correct, reject, retry, and safe deletion.
- [ ] Reconcile derived data when a document is deleted.
- [ ] Cover duplicate upload, corrupt file, unsupported type, timeout, and expired-session cases.

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

- [ ] Persist sessions, messages, structured state, and tool outcomes.
- [ ] Recover after refresh, websocket reconnect, provider timeout, and quota exhaustion.
- [ ] Prevent duplicate messages and duplicate tool actions.
- [ ] Show when an answer is based on approved records, general evidence, or insufficient information.

### PAT-002 — Adherence, symptom, and barrier collection

- [ ] Record medication adherence with patient confirmation.
- [ ] Collect onset, duration, severity, related medication, and red flags for symptoms.
- [ ] Capture barriers such as cost, side effects, access, confusion, and schedule.
- [ ] Create follow-up tasks and care-gap state.
- [ ] Make structured reports visible in the clinician timeline.

### SAFE-002 — Deterministic triage overrides

- [ ] Finalize emergency, self-harm, severe allergy, and urgent medication rules in English and Spanish.
- [ ] Execute safety rules before model routing.
- [ ] Prevent model output from weakening required escalation language.
- [ ] Store the triggered rule and escalation result.
- [ ] Add adversarial and multilingual regression coverage.

### PAT-003 — English and Spanish product parity

- [ ] Translate dynamic and static patient journeys.
- [ ] Preserve clinical terminology and evidence meaning across languages.
- [ ] Test language switching mid-session.
- [ ] Validate voice transcript, error, consent, and emergency flows in both languages.
- [ ] Complete clinician/pharmacist review of high-risk bilingual content.

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

- [ ] Replace empty pharmacovigilance modules with tested implementation.
- [ ] Collect complete ADR evidence and missing-information requests.
- [ ] Calculate Naranjo assistance deterministically where possible.
- [ ] Keep model-generated classification separate from reviewer decision.
- [ ] Support reassessment when evidence changes.

### PV-002 — MedWatch draft lifecycle

- [ ] Generate an editable MedWatch-compatible draft.
- [ ] Link every populated field to source evidence.
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

- [ ] Complete patient-to-care-team and clinician-to-patient message paths.
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
- [ ] Compare providers on accuracy, safety, evidence, latency, reliability, and zero-cost feasibility.
- [ ] Select default and fallback providers from results.
- [ ] Store repeatable evaluation inputs, rubrics, results, and environment metadata.

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

| Role | Primary lane | Required secondary review |
|---|---|---|
| Engineer 1 | Platform, Supabase, security, FHIR, SMART, deployment | Clinician authorization |
| Engineer 2 | Agent runtime, model adapters, evidence, safety, evaluation | Voice and ADR |
| Engineer 3 | Patient portal, bilingual companion, adherence, voice | Scheduling |
| Engineer 4 | Clinician portal, review queues, PV, messaging, continuity | FHIR workflow UX |

- [ ] Replace Engineer 1–4 with team-member names.
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
