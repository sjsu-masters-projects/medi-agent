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
| Repository | Main synchronized | Local `main` matches `origin/main`; current tracker verification is recorded on a separate documentation branch |
| Historical work | Needs reconciliation | One remote SMART work branch remains outside `main`; no local stashes or additional worktrees remain |
| Patient portal | Partial | Major screens exist; several workflows require real end-to-end completion |
| Clinician portal | Partial | Dashboard/deep dive exist; consolidated review and action lifecycle incomplete |
| Backend foundation | Partial | Broad API and test base; empty modules and reachable placeholders remain |
| Records ingestion | Functional foundation | Needs provenance, correction, FHIR validation, and reconciliation hardening |
| Chat and triage | Functional foundation | Needs provider abstraction, bilingual qualification, recovery, and full journey tests |
| Pharmacovigilance | Not complete | Empty agent/tool files and incomplete ADR service paths |
| Scheduling and communication | Not complete | Foundations exist; complete patient/clinician lifecycle does not |
| Interoperability | Functional sandbox foundation | A deployed, EHR-initiated SMART Health IT R4 sandbox flow imports synthetic records as provenance-backed pending candidates; conformance and reconciliation remain |
| MCP/A2A | Partial | Existing MCP is custom. The A2A task service and retry worker are implemented and the worker starts with the application; `/.well-known/agent-card.json` and the delegation flow are still absent |
| CI | Green baseline; Acquit enforcement evidence in progress | Required CI is green on `main`; Acquit 0.1.3 remains a non-blocking canary until 10 selective observations are collected |
| Dependency security | Clear as of 2026-09-09 | `next` 16.3.4 is on `main` and deployed, closing two critical unauthenticated-RCE advisories (GHSA-p293-qw3h-jr36, GHSA-2xp9-vwfh-vxw4) that were live on both portals; a fresh `npm ci` reports zero vulnerabilities on both lockfiles. Advisories published after the 2026-08-19 evidence invalidated it, so re-run `npm audit` at the start of each session rather than trusting this row |
| Demo data | Staging fixture refreshed; access verification in progress | The canonical fixture was reset/reseeded with fictional names on 2026-08-27; patient login, feed, and adherence statistics work, while clinician/RLS checks remain |

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
      `scripts/compare_providers.py` close that across MedGemma, Flash, and Pro. NVIDIA NIM
      is out of scope per the 2026-09-09 decision; the comparison accepts any
      `TextProvider`, so adding it later needs no rework here.
- [/] Define the voice-provider interface; live voice transport migration remains next.
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
      that a provider should be replaced without this evaluation. Tracked as `AI-002`.

### AI-002 — Model-routing decision spike (September 2026)

**Status:** `[/]` Spike delivered; team decisions and follow-up PRs pending

**Priority:** P1 (contains one P0 safety finding routed to SAFE-002)

**Owner:** Ganesh Thampi (provider adapters, evaluation); safety review required

**Spec:** [`specs/ai-model-routing-spike-2026-09.md`](specs/ai-model-routing-spike-2026-09.md)

- [x] Map every model call site, prompt, schema, fallback, telemetry field, and persisted
      version field for the nine AI workloads against the spike requirements (spec §3).
- [x] Snapshot the September 2026 market for paid, free-tier, and open-weight candidates,
      including SDK lifecycle, data handling, and BAA posture (spec §4).
- [x] Build a provider-neutral evaluation harness: scenario schema, per-workload scoring
      against the release thresholds, an OpenAI-compatible `TextProvider` adapter
      (`backend/src/app/clients/openai_compatible.py`), an optional `response_schema` on
      `GenerationRequest`, and `backend/scripts/run_ai_eval.py` (spec §6).
- [x] Author 70 synthetic gold-labeled seed scenarios in `backend/tests/fixtures/eval/`
      (28 triage, 10 document, 14 discrepancy, 10 ADR, 8 explanation), every high-risk case
      mirrored in `en-US` and `es-MX`, with CI tests for validity, mirroring, and
      synthetic-only content. All adjudication is `pending`.
- [x] Run the harness against every provider reachable with existing credentials and record
      the reports (`backend/reports/ai_eval_20260910_065321`, `_173527`, `_173605`; spec §7).
      Measured: `gemini-3.1-flash-lite`, `gemini-3.1-pro-preview` (router, Vertex),
      `gemini-3.5-flash-lite` and `gemini-3.8-flash` (Vertex OpenAI-compatible endpoint through
      the new adapter). Unreachable providers were recorded as reliability results: the
      MedGemma 27B Vertex endpoint fails DNS on every call, and the AI Studio key returns 429
      (prepaid credits depleted) for all models. Headline: `gemini-3.5-flash-lite` led every
      interactive workload (triage 28/28 with zero under-triage at p50 0.8 s; explanation 8/8
      in both locales; documents 87% with 100% verifiable evidence); Pro was most accurate on
      discrepancies but 5–19 s at p50; `gemini-3.8-flash` could not be judged (project quota,
      reasoning tokens truncating output). No scenario is adjudicated, so no threshold is met
      for release.
- [x] Write the ADR (exact model IDs, pinning policy, retirement monitoring, data controls,
      kill switch, rollback) and the migration plan that preserves `TextProvider`,
      `ModelRouter`, and reconciliation authorization (spec §9, §10).
- [x] Research medical-specialised models per use case (open medical LLMs and their licences,
      clinical NER and SNOMED linking incl. Spanish resources, medical speech, medical
      embeddings, safety classifiers, drug-knowledge data sources after the NLM interaction
      API retirement, and the physician-rubric benchmarks) and record the eight decisions in
      [`specs/medical-models-landscape-2026-09.md`](specs/medical-models-landscape-2026-09.md).
      Finding: no medical fine-tune outranks current general models on MedHELM or HealthBench;
      the medical-specific investments that pay off are terminology, Spanish clinical NLP,
      medical STT, and a self-harm classifier layer.
- [x] Consolidate solution, measured quality, and cost per use case, including an assessment
      of the OCR and document-intelligence document, in
      [`specs/ai-use-case-decision-sheet-2026-09.md`](specs/ai-use-case-decision-sheet-2026-09.md).
      Key point: reading quality (97.8% fields found, assessment) and structuring quality
      (87% fields, 100% evidence, spike) are different steps; end to end is unmeasured.
- [x] Broad inference and hosting research (NVIDIA hosted and self-hosted NIM, token-priced
      open-model providers, GPU-hour and serverless GPU hosting, hyperscaler managed APIs
      with BAA, startup and education credit programs, speech providers), with monthly costs
      for the expo, one-clinic, and ten-clinic scenarios. Decision document:
      [`specs/inference-hosting-options-2026-09.md`](specs/inference-hosting-options-2026-09.md);
      five sourced reports under `docs/research/hosting-2026-09/`. Finding: managed per-token
      APIs are 5–100× cheaper than owned GPUs below ten-clinic scale; only a scale-to-zero L4
      (≈ $46/month) breaks even at one clinic; NVIDIA's hosted catalogue has no price, SLA, or
      BAA and prohibits personal data, so it is an evaluation source only; the cheaper managed
      lanes (`gpt-oss-120b` on Bedrock, `gpt-5-nano` on Azure) are unmeasured on our harness.
- [x] Verify model lifecycle, prices, capacity rules, and partner-model access against Google's
      documentation (2026-09-15; hosting spec §9). Material corrections: Gemini 3.1 Flash-Lite
      is $0.25 / $1.50 interactive, not the $0.125 / $0.75 batch price the earlier cost tables
      used; Qwen3-Next, GLM 4.7, DeepSeek, and gpt-oss-20b managed endpoints retire on
      2026-10-21, before the expo; Gemini 3.6 to 3.8 Flash are short-term-availability models;
      Claude on Vertex is quota-restricted for this project.
- [x] Expo model comparison on the Vertex models that survive past December (3.1 Flash-Lite,
      3.5 Flash-Lite, 3.5 Flash, 3.7 Flash, 3.8 Flash, 3.1 Pro, gpt-oss-120b, Gemma 4 managed)
      across the 70 scenarios, with thinking models at low effort. The harness gained a
      per-provider reasoning-effort option and bounded exponential backoff for 429 and
      transient 5xx responses, with retries recorded in telemetry.
      Report `backend/reports/ai_eval_20260915_194824` (560 of 560 scored); decision in
      `.agent/specs/inference-hosting-options-2026-09.md` §10: 3.5 Flash-Lite for triage,
      explanations, and documents; 3.7 Flash at low effort for discrepancy and symptom
      extraction; 3.5 Flash-Lite or 3.1 Flash-Lite as fallbacks; about $3.90 for expo volume.
- [ ] Switch the model routing to the §10 expo decision with a per-workload fallback, and
      replace the retired `gemini-3.1-flash-lite-preview` in local and Cloud Run configuration.
- [ ] Document reading is an OCR decision, not a model decision: the OCR spike
      (`docs/document-intelligence-assessment.md`) recommends pypdfium2 plus PaddleOCR
      PP-OCRv5 through RapidOCR with deterministic anchoring, and its prototype already
      exists uncommitted under `backend/src/app/services/document_intelligence/`. The
      routing evaluation only measures structuring of page-marked text; it must not be
      used to pick a reader.
- [x] Rebuild the evaluation harness so it measures models rather than the harness
      (protocol: `.agent/specs/eval-harness-protocol-2026-09.md`). Every call now ends in
      one recorded disposition (answered / infra_error / truncated / unparseable /
      refused); `finish_reason` and reasoning tokens are captured, so truncation is no
      longer read as a wrong answer; HTTP 400 is `invalid_request`, not an outage;
      providers run sequentially because firing eight at one project's quota made them
      throttle each other; the schema is emitted in the one dialect all three serving
      stacks accept, with evidence required and reasoning fields generated before verdict
      fields; drug names match strictly (`insulin glargine` no longer matches `insulin
      aspart`) with bilingual and brand synonyms and OCR-digit folding; negated safety
      advice is no longer scored as a safety violation; abstention is read per workload;
      a call that never answered no longer carries a safety verdict; precision and recall
      are micro-averaged; documents are presented with `[Page N]` markers as production
      does; and accuracy is reported on answered calls with a bootstrap interval beside
      the answered rate. Statistics in `backend/src/app/services/eval_statistics.py`
      (Wilson, bootstrap, paired McNemar; six one-sided disagreements are needed for
      significance at this n). 1036 tests pass; the 3 failures in
      `tests/unit/services/document_intelligence/` predate this work and are recorded in
      `docs/document-intelligence-assessment.md` §13.
- [x] Correct fixture ground truth that demanded forbidden inference: `lab_report`
      required a "Hyperlipidemia" diagnosis the source never states, and
      `diagnostic_report` required a route and two frequencies a CT report never gives.
- [/] Cloud leg of the re-run is done: `backend/reports/ai_eval_20260917_172344.json`,
      gpt-oss-120b and Gemini 3.8 Flash over all 70 scenarios, sequential, low effort.
      Both answered 65 of 70 (3.8 Flash lost 5 calls to capacity, all in triage; gpt-oss
      lost 3 and returned 2 replies that failed the schema). **Paired item-by-item, no
      workload shows a measurable difference** — the closest is triage at p=0.07 — so at 8
      to 28 scenarios these two cannot be ranked on clinical accuracy, and September's
      confident ordering of nine models was noise plus harness defects. What does separate
      them: gpt-oss costs roughly a tenth as much and answers triage in 2.2 s against
      6.2 s, but breaks the output schema occasionally where Gemini never did. Details in
      `.agent/specs/eval-harness-protocol-2026-09.md` §12. MedGemma's leg is outstanding.
- [x] Re-ran the expo comparison under the new protocol on all three finalists
      (`ai_eval_20260917_172344`, `_183906`, `_192522`; 70 scenarios each, sequential).
      Verdict: **MedGemma is out**, though not for the reason first written here. It
      under-triaged urgent cases (79% and 75% against 100% for both cloud models) and
      could not hold the output contract. The claim that it "missed every allergy
      conflict" was wrong: unconstrained it found both and lost the points to our own
      prompt template, copying the literal enum menu into a `type` field in 4 of 14
      answers. Constrained, it genuinely produced neither. Its September "90% document field accuracy" was an artefact of the
      lenient matcher and does not reproduce (75% unconstrained, 49% constrained). Its
      endpoint cost about $3 of GPU for 91 minutes against 7 cents of tokens for the whole
      cloud leg; endpoint deleted and independently verified gone. **gpt-oss-120b and
      Gemini 3.8 Flash cannot be separated on clinical accuracy** at this sample size, so
      choose on deployment properties: gpt-oss is ~10x cheaper, faster on triage, and
      occasionally violates the output schema; 3.8 Flash never violated it, passes the 90%
      recall bar on reconciliation where gpt-oss fails at 71%, and loses more calls to
      shared capacity. Full detail in `.agent/specs/eval-harness-protocol-2026-09.md` §14.
- [ ] Re-run the expo comparison under the new protocol on the three finalists
      with the rigour still missing: three trials per scenario for run-to-run variance,
      the no-document and example-perturbation controls in protocol §5, per-class safety
      recall with intervals, and a real language identifier for the es-MX scoring.
- [ ] Treat gpt-oss-120b's format conformance as a deployment property, not a quality
      score: on Vertex it honours a JSON schema only sometimes, measured at 3 schema
      violations in 10 trials against Gemini 3.8 Flash's 0 in 10 (protocol §11), including
      one on a real scenario that never asked for a different shape. If it is chosen for a
      workload the caller must validate and retry. An earlier claim that `minLength` caused
      this was written up after a single trial and is wrong; the repeat test refuted it.
- [ ] Every number in `inference-hosting-options-2026-09.md` §10 and
      `ai-model-routing-spike-2026-09.md` §7 predates these fixes and must not be quoted
      until the re-run replaces it.
- [x] MedGemma 1.5 4B measurement on a temporary Vertex endpoint (two L4 GPUs, us-central1,
      authorized 2026-09-15 as test-then-undeploy; report `backend/reports/ai_eval_20260915_201947`).
      Endpoint existed about 17 minutes, about $0.60 of GPU time at the estimated rate; undeployed
      and deleted, zero endpoints remain. Results with the schema in the prompt, because the
      container rejects nullable JSON-schema types: symptom extraction 55% with red flags caught
      6 of 10, documents 49% with 60% schema-valid output, explanations 89%; p50 7–14 s. It writes
      its reasoning inline between `<unused94>` and `<unused95>`, which the adapter now strips.
      `backend/scripts/model_garden_endpoint.py` adds `up`, `status`, and `down` so self-hosted
      models are deployed only for a working session; `down` removes only endpoints the script
      created unless an endpoint ID is given.
- [ ] Team decision on the five open items in spec §11 (budget lane, non-Google evaluation
      credentials, GPU host for the self-hosted lane, adjudication schedule, P0 ordering).
- [ ] Execute migration steps 1–6 as separate PRs after the SAFE-002 P0 fix ships.
- [ ] Hand the harness and seed set to `EVA-001` for the remaining 50 scenarios and the 40
      adjudications.

**Acceptance criteria**

- [x] Workload matrix, benchmark protocol and fixtures, results, primary/fallback
      recommendation, ADR, and migration plan exist in one reviewed document.
- [x] The harness runs offline in CI (`--dry-run` and unit tests) and live with credentials,
      and never writes prompts to its reports.
- [ ] The routing pins in the ADR are confirmed by a harness run that meets the thresholds
      on adjudicated scenarios before any production re-route.

---

### AI-003 — Agent runtime overhaul

**Status:** `[/]` In progress

**Priority:** P0 (contains the shipped SAFE-002 streaming fix)

**Owner:** Rajeev Chaurasia; safety review required before any workload defaults on

**Why:** AI-002 ended with two finalists that cannot be separated on clinical accuracy, and
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
- [ ] **WS1 remainder.** Set `GOOGLE_PROJECT_ID` and the Flash model id on Cloud Run, then
      remove the AI Studio path. Production runs on AI Studio today because
      `GOOGLE_PROJECT_ID` is unset, so this is a first move to Vertex rather than a model
      swap, and the order matters: changing the model default first would break the live
      path, since 3.8 Flash is not served on AI Studio. Then promote
      `clients/openai_compatible.py` to production for the gpt-oss transport, populate
      `GenerationRequest.response_schema`, and stop discarding model telemetry.
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
- [ ] **WS5 — Document pipeline**: OCR with page and bounding-box anchoring, moved to a
      durable claimed job. The portal's fixed-attempt polling must be fixed *before* OCR
      lands, or the first scanned upload exhausts the poll and looks permanently stuck.
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

- [ ] Run the safety floor before the model on the websocket streaming path.
      `TriageAgent.process_stream` (`backend/src/app/agents/triage/agent.py:152-155`) calls
      `_classify_with_llm` first and only reaches `_deterministic_safety_floor` through the
      rules fallback when the model returns nothing, while `routers/chat.py:523` uses
      `process_stream` for every websocket turn. The `b72c07f` fix covered `classify_intent`
      only. Add a websocket-level emergency regression test in both locales and localize the
      L3 fallback string in `routers/chat.py`. Found by the AI-002 spike on 2026-09-10; P0.
- [ ] Close the inflected-keyword gap in the floor. "I've been thinking about ending my life"
      does not match `end my life` (substring matching, no stemming) while its Spanish mirror
      matches `quitarme la vida`; evolving anaphylaxis ("lips swelling, throat tight") and
      stroke signs ("face droopy, words slurred") match nothing in either language. The AI-002
      harness reports `floor_fires` per scenario so keyword changes can be checked against the
      paired `en-US`/`es-MX` cases (`backend/tests/fixtures/eval/triage_classification.json`).

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

`.agent/TEAM.md` is the authoritative roster. This table mirrors it; update both together.

| Member | Primary lane | Required secondary review |
|---|---|---|
| Rajeev Chaurasia | Platform, Supabase, security, FHIR, SMART, deployment | Clinician authorization |
| Ganesh Thampi | Worker runtime, provider adapters, evidence, safety, evaluation | Voice and ADR |
| Tushar Singh | Patient portal, bilingual companion, adherence, voice | Scheduling |
| Jeevan Kurian | Clinician portal, review queues, messaging, continuity | FHIR workflow UX |

- [x] Replace Engineer 1–4 with team-member names.
- [ ] Assign an owner for pharmacovigilance (PV-001, PV-002). The superseded
      placeholder table listed PV under the clinician-portal lane; `TEAM.md` does not,
      so the whole R4 pharmacovigilance milestone is currently unowned.
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
| 2026-09-09 | NVIDIA NIM is out of scope for provider comparison | No endpoint or credential is available to the team, and an adapter that cannot be run produces no evaluation evidence. Comparison runs across MedGemma, Flash, and Pro. `compare_text_providers` accepts any `TextProvider`, so NIM can be added later without reworking the comparison |
| 2026-09-10 | Provider routing is decided per workload from harness evidence, with a deterministic layer first and GA model IDs only in production defaults | The AI-002 spike found the routing evidence stale (measured Gemini 2.5, configured 3.1), the MedGemma 27B endpoint unreachable, both legacy Google SDK paths past end of support, and no telemetry or kill switch. Details and the proposed pins are in `specs/ai-model-routing-spike-2026-09.md` §9; the pins stay proposed until the team resolves §11 |
| 2026-09-10 | Free-tier endpoints are for synthetic evaluation only and are not a deployment lane | AI Studio free-tier terms allow training and human review of inputs and carry no BAA; the project's key is also on depleted prepaid billing. Zero-cost serving means self-hosted open weights, which need a GPU host for anything beyond 4B-class models |
