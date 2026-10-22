# Project backlog — detailed acceptance requirements

This is the required scope reference for issues that do not yet have a dedicated
specification. Read the selected issue here **after TASKS.md and before editing**.
The task board alone supplies current status, owner and priority; bullets here
are requirements, not progress checkboxes. Existing implementations may satisfy
part of them. Inspect code/tests before assuming a missing implementation.

Dedicated specifications take precedence for PAT-005, SCH-001, COM-001-B,
INT-002/003, LOC-001, NORA-002, NOT-001 and UX-002. Clinical safety requirements are not relaxed by the demo scope.
The delivery target is a university expo with fictional patient and clinician
accounts. No real-patient recruitment, professional-clinician recruitment, VC
pitch or production certification is an acceptance gate. In-app clinician
approval means the demonstrator uses the authorized synthetic clinician role;
it does not establish independent clinical validation. Earlier research/release
targets listed under QUA-001 are optional extensions where they exceed this scope.
Do not execute historical migrations, seeds or remote actions merely because a
requirement mentions them; use the current operator guide and explicit approval.


## CI-001 — Selective backend execution evidence

October 21 reconciliation: the current workflow already runs Acquit in `enforce`
mode with fail-closed run-all and retained full coverage. The earlier canary and
ten-observation prerequisite describe a superseded rollout, not an instruction
to disable current enforcement.

- Record verified selection versus actually executed test files on an eligible
  narrow PR, alongside retained full coverage results.
- Classify expected run-all changes (migrations, dependencies, pytest/CI and broad
  backend foundations) separately from avoidable blockers.
- Keep run-all on policy findings, analysis errors or tree mismatches. Do not use
  blanket waivers or weaken safety/coverage gates to obtain a selective result.

## INT-002 — FHIR R4 validation and mapping

- Establish an R4-compatible validation boundary; the maintained dependency provides R4B while emitted payloads remain R4-compatible.
- Map Patient. Practitioner, Organization, and CareTeam are intentionally not mapped because the local clinician/care-team model remains authoritative.
- Map Condition, AllergyIntolerance, MedicationRequest, and MedicationStatement.
- Map Observation, DocumentReference, and CarePlan; Appointment and Communication are intentionally outside the committed import set.
- Generate validated, read-only Provenance and AuditEvent representations from local clinical-fact lineage and immutable audit records without external FHIR writes or private-reasoning disclosure.
- Validate supported resource shape before persistence; identifier-quality and export validation remain deferred.
- Handle missing, partial, duplicate, and unsupported resources safely.
- Add import fixture tests; FHIR export and round-trip fixtures remain deferred.
- Make SMART candidate review clinically legible: enrich mapped summaries, render FHIR instants in the selected patient's timezone, filter by mapped type, keep source-only candidates distinct from local facts, and replace whole-record JSON correction with field-level editing while preserving the review-only boundary.

## SAFE-001 — Approval and audit infrastructure

- Define `ClinicalRecommendation`, `ApprovalDecision`, `ActionEnvelope`, and `AuditRecord`.
- Enforce tiered action authority server-side. `app/core/action_tiers.py` classifies each
      action type and `propose` enforces it; the applied tier is recorded on the audit
      trail. Tiers only tighten — none waives review. Feature-specific executors will
      classify their actions as they are implemented, and an unclassified action fails
      closed to the most restricted tier rather than inheriting the default.
- Require idempotency keys for action envelopes.
- Record proposer, evidence, reviewer, edits, decision, executor, and outcome.
- Prevent approval by an unauthorized, unassigned, or proposing clinician.
- Add replay and duplicate-action tests.
- Record every authorization denial with a classified reason code, audited from the
      403 handler so every raise site is covered.
- Verify the fixture's declared denial expectations against a live environment. Resolve fixture actions/proxy actors that have no supported route; do not invent test endpoints.

## REC-002 — Safe external-record reconciliation

- Make document and SMART ingestion candidate-only; remove implicit demo extraction. Require page-grounded evidence and no implicit canonical writes.
- Bind an external FHIR patient to one local patient after clinician confirmation.
- Add conservative matching and transactional, field-level reconciliation.
- Show candidate-versus-local comparison, evidence, filters, and applied provenance.
- Inventory legacy document-derived rows without silently rewriting or deleting them.
- Verify the synthetic end-to-end SMART/document reconciliation journeys in staging.

## REC-001 — Complete record ingestion lifecycle

- Add content-derived document display titles after grounded extraction for future patient
      and clinician uploads. Use only sourced document type, subject and date; never infer
      missing diagnosis/date or rename the original file/storage key. Preserve the original
      filename, document ID and provenance; show a neutral fallback and the original name
      when uncertain. Reuse the display title consistently in document lists, chat catalog,
      citations and care-plan review. Existing-document backfill is a separate opt-in step.
      Scope with evidence/portal owners; no automatic existing-document backfill.
- Establish one safe document-format and viewer contract. The generic clinical-document
      path supports PDF, JPEG, PNG, WebP, and TIFF only; it must render every supported source
      for the patient and assigned clinician, preserve the original artifact, and keep FHIR,
      CDA, and DICOM on dedicated interoperability/imaging paths. See
      `docs/document-format-policy.md`.
- Replace the licensed Syncfusion stub with local PDF.js/native-image viewing, derive a
      bounded PDF preview for TIFF, and pass only a selected document's bounded summary to the
      care coordinator. Use current preview schema and verify protected viewing; do not reapply a historical migration solely from this requirement.
- Support patient and clinician PDF/image upload.
- Constrain both upload entry points to the private `documents` bucket's supported clinical formats (PDF, JPEG, PNG, WebP, TIFF), reject unsupported files locally before storage/API calls, and surface the validation error.
- Persist upload, extraction, review, correction, and failure states. Retain guarded attempts/runs, OCR/evidence-review states and safe failure codes.
- Show field-level provenance and confidence. Require page/excerpt/confidence evidence and readable source presentation.
- Route low-confidence and contradictory fields to review.
- Support approve, correct, reject, retry, and safe deletion. Assigned clinicians may retry retryable processing failures up to three total attempts; reconciliation choices remain separately governed.
- Reconcile derived data when a document is deleted.
- Cover duplicate upload, corrupt file, unsupported type, timeout, and expired-session cases.
- Reconcile approved FHIR candidates into existing authoritative records through explicit clinician choices to add, update, keep, defer, or reject; retain the candidate, source provenance, and audit history, and never mutate source data automatically.
- Provide audited re-projection/backfill for pending imported candidates when mapper versions add useful fields; never overwrite a clinician correction or final review decision. Dry-run and guarded staging application are implemented; production execution requires a reviewed report, an explicit candidate-type scope, and authorization. Legacy CarePlan display repair remains pending a scoped reviewed report.

## MED-001 — Multi-source medication reconciliation

Requester-approved October 21 expo scope: source-based review, not a
comprehensive drug–drug interaction or therapeutic-equivalence engine. Retain
unlisted patient-reported products as unreviewed evidence; never create an
approved medication merely to attach an ADR. Show coverage limitations explicitly.

- Normalize medication identity using RxNorm when possible.
- Combine patient, clinician, document, and FHIR medication sources.
- Flag supported possible duplicate identity, recorded dose/status differences,
  missing medication and exact recorded allergen-name matches for clinician review.
  Do not equate different text with a clinically confirmed dose conflict or claim
  unchecked interaction/allergy/therapeutic-equivalence coverage is safe.
- Attach DailyMed/RxNorm evidence and freshness.
- Display uncertainty instead of fabricating resolution.
- Require clinician approval for the canonical medication list.
- Preserve full reconciliation history.

## MED-002 — Clinician reconciliation experience

- Build side-by-side source comparison.
- Support accept, reject, edit, defer, and request-patient-confirmation actions.
- Display evidence, provenance, confidence, and last-updated time.
- Reflect approved changes in both portals and FHIR export.
- A clinician can turn an uploaded synthetic record into an approved medication list without hidden or fabricated data.

## PAT-001 — Reliable conversation lifecycle

- Persist sessions, messages, structured state, and tool outcomes. Conversation history and
      state are present, but document focus is still route/session scoped and is completed only
      through PAT-004's per-message contract.
- Recover after refresh, websocket reconnect, provider timeout, and quota exhaustion,
      including selected-document focus rather than only general chat connectivity.
- Add durable terminal handling for each saved chat turn: persist `processing`, `completed`,
      `failed`, or `interrupted`; enforce a bounded model deadline; reconcile unfinished turns on
      reconnect; and retry the saved turn without duplicating the patient's message. Record only
      safe outcome, duration, revision, and failure-category telemetry.
- Prevent duplicate messages and duplicate tool actions.
- Show when an answer is based on approved records, general evidence, or insufficient
      information. The general contract exists; source visibility and focused-document behavior
      remain open in PAT-004.

## PAT-004 — Document-focused conversations

- Define the focused-chat interaction: retain conversation history, collapse or label older
      conversation where useful, and show a persistent "Discussing: <document>" card before the
      patient sends a question. Prefill a suggested question but never send a model prompt or
      medical claim without an explicit patient action.
- Make document focus a per-message, server-authorized reference rather than conversation-
      wide state. At send time, authorize the document for the authenticated patient and attach
      only its bounded, patient-facing summary and provenance to that exchange. Persist the
      document reference and context version needed for audit; never persist a signed storage URL
      or let the model choose a document identifier.
- Define focus lifecycle and safety behavior: a patient may dismiss or replace the focus;
      later general questions have no document context; refresh, reconnect, route reuse, and a
      second browser tab preserve or restore only the selected focus for the intended message.
      A missing, deleted, unauthorized, or summary-less document must produce an explicit
      unavailable-context response, not a general-record answer or an invented interpretation.
- Keep medical communication source-bound: preserve exact medication names, doses,
      frequencies, and route wording when present; explain terminology in plain language only
      when helpful; do not diagnose, prescribe, infer indication, or turn a focused document
      into a chart-wide answer.
- Add browser and backend coverage for: navigation from an already-open chat, context-card
      rendering, draft-only suggested question, refresh/reconnect, dismiss/replace behavior,
      patient/clinic isolation, expired/deleted documents, and audit linkage from each focused
      user message to its authorized document context.
- Answer a clear catalog question (for example, “What documents do you have on me?”) from
      authenticated, patient-scoped portal metadata without invoking a model. The response lists
      only documents available in MediAgent, never a signed URL, raw source text, or records from
      another patient; it must not claim that the portal has no record access.
- Show the typing state immediately after a message is sent, rather than waiting for model
      classification. A terminal completion, error, or connection close clears it.
- Selecting **Ask about this document** visibly attaches the intended document before a
      patient sends anything, without erasing prior conversation.
- The first focused answer names or otherwise identifies its source document and is bounded
      to its authorized evidence; it never silently falls back to the general chart.
- A later non-focused turn cannot inherit a previous document's context, and an unassigned
      user cannot attach or infer another patient's document.

## PAT-002 — Adherence, symptom, and barrier collection

- Record medication adherence with patient confirmation.
- Collect onset, duration, severity, related medication, and red flags for symptoms through
      the sequenced tasks below. A raw chat utterance is not itself a clinician report.
- Capture barriers such as cost, side effects, access, confusion, and schedule.
- Create clinician-approved follow-up tasks and care-gap state through PAT-005; an AI or
      unreviewed document must not create a patient-facing obligation directly.
- Make structured reports visible in the clinician timeline.

## PAT-002-B — Guided chat symptom intake and patient-confirmed structured report

- Apply `SAFE-002` emergency/self-harm overrides before any symptom follow-up. The reviewed
      escalation copy and required care-team notification take precedence over conversational
      intake; do not ask questions that delay emergency direction.
- For non-emergency symptom turns, collect only relevant missing fields: onset, duration,
      severity, course, related medication or treatment when supplied by the patient, associated
      symptoms, and red-flag answers. Never diagnose, assign causality, invent a medication link,
      or tell the patient that an ADR has been established.
- Build a versioned, clinician-approved question library rather than allowing an LLM to
      improvise a medical interview. Its shared ADR fields cover event description and body
      location, onset/course/severity, suspected-product exposure (name, strength, dose, route,
      indication, start/stop/change dates), concomitant products, relevant history/tests, and
      patient-reported outcome. Symptom-specific branches may ask only approved follow-ups (for
      example skin, gastrointestinal, respiratory, neurologic, or medication-use-error details).
- Create an auditable retrieval snapshot for each intake: retrieved fact/citation identifiers,
      retrieval purpose, and rule/library version. The model receives the least context necessary;
      it must preserve unknown or declined answers rather than filling gaps from a document or
      model inference.
- Persist a draft intake separately from a confirmed report. The patient can correct,
      abandon, or confirm it; only confirmation creates the clinician-visible structured report.
- Record the source conversation/turn references, locale, deterministic safety result,
      patient-entered answers, confirmation actor/time, and safe report status needed for audit.
      Do not persist private model reasoning, prompts, or provider traces.
- Keep clinician notification and care-plan changes under existing review paths. The chat
      agent must not autonomously create a patient-facing task, clinical recommendation, ADR
      decision, or MedWatch record.
- Enforce patient ownership, care-team assignment, RLS/grants, and API authorization for
      drafts, confirmed reports, cancellation, and retrieval. Browser clients cannot directly
      mutate clinician-facing report state.
- A non-emergency patient can complete a bounded guided intake, see an accurate report
      preview, correct it, and explicitly confirm it.
- An emergency symptom follows the deterministic escalation path and is never obscured by a
      symptom-worker acknowledgement or an intake questionnaire.
- A confirmed report reconstructs the patient answers, source turns, safety result, and
      confirmation without representing model output as clinical fact.
- The patient-facing confirmation view identifies what they reported, what was retrieved from
      their record, and what the assistant summarized; correcting the report never edits source
      documents or prior confirmed reports.
- An unrelated patient or unassigned clinician cannot list, read, alter, or infer a report.

## PAT-002-C — Patient symptom timeline and clinician-visible report detail

- Show the patient a timeline of their confirmed reports, with timestamp, status, and the
      patient-confirmed fields. Keep unconfirmed drafts private to the patient and clearly
      distinguish them from reports shared with the care team.
- Give assigned clinicians a detail view containing the structured report, conversation
      provenance, patient confirmation, follow-up answers, safety result, retrieved
      document/medication citations, and later clinician actions. Render patient-reported facts,
      document-grounded context, AI summary, and clinician assessment as distinct sections; do
      not expose hidden prompts or chain-of-thought.
- Add report-status transitions for clinician review and information requests while retaining
      the original confirmed report immutably. A correction or new patient report must be linked,
      not silently overwrite history.
- Add timeline/audit events and assignment-denial coverage for patient, clinician, and
      cross-clinic access. Use the existing protected patient/document access patterns.
- A patient sees only their own confirmed reports and can distinguish a draft from a shared
      report.
- An assigned clinician can inspect a report's patient-confirmed content and provenance;
      an unassigned clinician receives a deny response and an audit event where applicable.
- A later report or clinician information request preserves the original report history.
- `PV-001` can consume this confirmed-report contract without scraping chat messages or
      deriving an ADR from an unconfirmed draft.

## PAT-003 — English and Spanish product parity

- Translate dynamic and static patient journeys.
- Preserve clinical terminology and evidence meaning across languages.
- Test that screens follow the saved language immediately; Nora replies in the language
  the patient writes or speaks (requester decision, October 11).
- Validate voice transcript, error, consent, and emergency flows in both languages.
- Peer-review high-risk bilingual demo wording against its sources and deterministic safety tests; disclose that it is not professionally validated. Do not require recruiting a clinician/pharmacist for expo acceptance.

## CLN-001 — Consolidated review workspace

- Alerts is the unified cross-workflow action inbox (requester approved October
  21); the Patient Upload Review Queue stays dedicated to source approval. Do not
  duplicate clinical approval controls: open the exact existing authorized review
  destination for document, medication, symptom, adherence, ADR or pending action.
- Add explainable priority, age, source, freshness, and assignment filters.
- Support approve, reject, amend, defer, dismiss, and request-information decisions.
- Update queue and patient deep dive without manual refresh.
- Prevent cross-clinic and unassigned-patient access.

## CLN-002 — Explainable Risk Radar and timeline

- Calculate risk from versioned, reproducible signals.
- Display contributing factors and freshness for every risk level.
- Show document, medication, symptom, adherence, message, appointment, approval, and action events chronologically.
- Link events to source evidence and reviewer outcomes.

## PV-001 — ADR and Naranjo workflow

- Consume the confirmed symptom-report contract with its patient answers, safety result, and
      provenance; preserve the separation between patient testimony, document context, and
      clinician assessment. Let a clinician request missing information without rewriting the
      original report.
- Use the approved intake library and patient-confirmed report to identify missing ADR facts:
      event/outcome, suspected product and therapy dates, concomitant products, relevant tests or
      history, and reportable seriousness indicators. The clinician decides relevance, causality,
      seriousness, and whether further information is needed.
- Calculate Naranjo assistance deterministically where possible.
- Keep model-generated classification separate from reviewer decision.
- Support reassessment when evidence changes.
- A clinician can review a confirmed report, document an ADR decision or uncertainty, and
      see the evidence/provenance used for each conclusion.
- Naranjo assistance exposes its inputs and is never presented as the clinician's final
      decision.
- An unassigned clinician cannot access the report or ADR review, and all reviewer actions
      are auditable.

## PV-002 — MedWatch draft lifecycle

- Generate an editable MedWatch-compatible draft only from patient-confirmed facts,
      document-grounded facts with citations, and clinician-approved assessments. Keep unknown,
      declined, or unsupported fields empty rather than inferred.
- Map populated patient, event/outcome, suspect-product/therapy-date, concomitant-product,
      test/history, and reporter fields to their source evidence. A patient statement must remain
      attributable to the patient; a document fact must retain its document citation.
- Require clinician/pharmacist approval.
- Export the approved draft without submitting it.
- Audit edits and reviewer sign-off.
- Every clinical recommendation has evidence, reviewer state, and an auditable outcome.

## COM-001 — Care-team communication and notifications

- Complete patient-to-care-team and clinician-to-patient message paths. Clinician-to-patient
      send (in-app and email) existed as backend-only endpoints with no frontend. Added: backend
      list endpoints (`GET /me/patients/{patient_id}/messages` and `GET /me/messages`), clinician
      inbox page replacing the static placeholder, compose form on the patient deep-dive Chat tab,
      and integration + component tests. Patient-to-clinician origination is addressed by the
      two-way threads shipped in COM-001-B (#139).
- Require approval for clinical outbound messages.
- Support opted-in administrative reminders.
- Add retry, deduplication, delivery state, and operations queue.
- Create care-gap tasks for missed follow-up.

## VOI-001 — Text-first voice experience

- Support streaming capture/playback when the configured provider is available.
- Persist the canonical transcript and structured state.
- Support interruption, reconnect, cancellation, and text fallback.
- Validate English and Spanish terminology and safety behavior.
- Never make audio the only way to complete a journey.

## CON-001 — Multi-provider continuity

- Build provenance-preserving longitudinal timeline.
- Generate an evidence-linked handoff summary for clinician review.
- Export a portable patient care summary.
- Respect care-team visibility and patient restrictions.
- The completed clinic care loop works through normal authorized application paths.

## EVA-001 — Internal model and safety evaluation

October 21 requester decision: this formal campaign is optional research, not a
completion gate. Retain the implemented harness; do not manufacture results or
require professional recruitment. Actual synthetic software journeys, automated
safety/access/approval tests and truthful failure states remain required under
their feature tasks, not a model benchmark or medical-validity claim.

- Define a repeatable rubric and synthetic cases covering the tasks actually shown: grounded extraction, simple explanations, symptom capture, unavailable responses and safety boundaries.
- Inspect raw model responses as well as structured output; compare English and Spanish, provenance, omitted/invented details and provider failures.
- Record results and limitations without claiming medical competence or clinical validation. A larger 120-case/40-professionally-adjudicated research study is optional, not required for the expo.


## QUA-001 — Optional broader qualification

These broader targets are not expo completion gates. Core authorization,
source integrity, approval, responsive usability and honest failure behavior
remain required for the demonstrated flows.

- Test RBAC, RLS, object ownership, clinic isolation, and privilege escalation.
- Test timeouts, quotas, network loss, duplicate requests, malformed FHIR, and provider outage.
- Meet WCAG 2.2 AA on core journeys.
- Meet responsive PWA requirements on supported mobile and desktop browsers.
- Add useful structured logs, traces, health checks, and alerting.
- Confirm no secret, PHI, hardcoded identity, or production mock state is exposed.
- Safety, interoperability, protocol, security, and product thresholds pass.

Historical research targets (optional, not expo gates): 100% recall on
deterministic emergency red-flag cases; zero unauthorized medication changes,
diagnoses or external clinical actions; 100% approval enforcement and audit
coverage for clinical recommendations and actions; at least 95% valid
evidence-to-source links; at least 90% required-field extraction accuracy and
medication-discrepancy precision/recall on the internal set; no material
English/Spanish safety disparity; browser-level end-to-end tests for the eight
critical journeys; full CI in 20 minutes or less; no critical dependency
vulnerabilities; and no empty functional modules, reachable
`NotImplementedError`, production mock success or hardcoded patient identity.

## REL-001 — Expo snapshot and rehearsal

- Freeze features on 2026-12-04.
- Run clean-install and migration rehearsal.
- Run relevant automated checks and rehearse selected demo flows on patient mobile and clinician desktop, including bilingual display, persistence and recovery.
- Resolve demo-blocking defects and explicitly record unavailable/optional capabilities.
- Tag the final expo snapshot; do not describe it as a production release or clinical qualification.

## REL-002 — Demonstration deployment

- Deploy backend and both portals using synthetic data.
- Verify domains, TLS, OAuth redirects, environment variables, scaling, and health checks.
- Validate demo accounts and reset workflow.
- Prepare a fallback recording for external-service outages.

## REL-003 — University-expo delivery package

- Prepare the complete clinic care-loop demonstration script.
- Prepare architecture, interoperability, safety, and operations briefs.
- Prepare installation, deployment, reset, and troubleshooting guides.
- Prepare an academic project explanation: problem, demonstrated workflow, architecture, results and limitations. Startup/VC pitch materials are out of scope.
- Record limitations honestly: synthetic data, supervised CDS, public sandbox, and no HIPAA-production claim.
- Selected demo journeys pass end to end; unsupported journeys are omitted or honestly labeled, never shown as fabricated success.
- Preserve authorization, clinical approval, attributable history and evidence-source links in every demonstrated clinical flow.
- Disclose observed model/translation limitations; professional adjudication, exhaustive benchmarks and production qualification are not expo requirements.

## DEMO-001 — Fresh synthetic expo scenario

- After selected features are implemented and verified, prepare one blank fictional patient and one blank fictional clinician with an explicit clinic/assignment.
- Build a coherent history through supported flows: appointments, clinician-authored synthetic documents, patient upload review, reviewed care-plan versions, reminders/adherence/barriers, confirmed symptom/ADR workflows where supported, and private human replies.
- Distinguish historical rehearsal data from events performed live. Use valid timestamps and real application audit actions; do not fabricate backdated approvals, signatures or reports through direct database edits.
- Preserve QA accounts and history. Provisioning/reset is a separately authorized, scoped operation; this specification does not authorize remote changes.
- Prepare a stable baseline, a bounded live segment, bilingual/mobile rehearsal, expected results, recovery instructions and outage recording in [the demo guide](../../docs/demo-environment.md#university-expo-scenario).
- The presenter operates both synthetic roles. No real patients, clinicians, medical records, recruitment or investor materials are required.
