# MediAgent Revival Plan — August to December 2026

**Status:** Approved for execution  
**Approved:** 2026-08-18  
**Feature freeze:** 2026-12-04  
**Primary outcome:** A working, startup-quality product prototype. Research and benchmarking support internal engineering decisions.

## Product thesis

MediAgent will become a supervised, evidence-backed, bilingual closed-loop care platform for outpatient clinics managing chronic-care and polypharmacy patients.

The complete care loop is:

1. Import clinical records with source provenance.
2. Reconcile medications and identify safety discrepancies.
3. Collect symptoms, adherence, and barriers through text or voice.
4. Route evidence-backed risks and proposed actions to a clinician.
5. Execute approved messages, appointments, reminders, or escalation.
6. Preserve the result in a longitudinal timeline across providers.

The platform—not a generic chatbot or the number of agents—is the product. Its differentiators are workflow closure, evidence provenance, clinical supervision, real interoperability, bilingual delivery, auditability, and measurable safety.

## Users and boundaries

- **Buyer:** Outpatient clinic or small clinic network.
- **Clinical focus:** Polypharmacy chronic care, demonstrated with diabetes, hypertension, hyperlipidemia, and related comorbidities.
- **Users:** Patients, clinicians, pharmacists/reviewers, and clinic staff.
- **Interfaces:** Patient PWA, clinician PWA, and SMART-on-FHIR launch.
- **Languages:** English and Spanish, tested end to end.
- **Data:** Synthetic or rigorously de-identified data only.
- **Safety model:** Supervised clinical decision support.
- **Cost:** Free developer tiers and open-source/local components for the capstone demonstration.

The system must not diagnose, prescribe, autonomously change medication, or directly submit regulatory reports. Real PHI and a HIPAA-production claim are out of scope without BAAs, paid compliant infrastructure, and legal review.

## Product journeys

### 1. Clinic and patient onboarding

- Provision clinics, clinicians, and staff.
- Invite patients and establish care-team relationships.
- Capture language, timezone, medications, allergies, and provider information.
- Enforce RBAC, RLS, MFA, session expiry, clinic isolation, and assignment checks.
- Audit access and care-team relationship changes.

### 2. Record ingestion

- Upload PDF and image records from either portal.
- Store the original artifact and compute source provenance.
- Extract medications, allergies, diagnoses, observations, appointments, and obligations.
- Map extracted data to validated FHIR R4 resources.
- Link every generated fact to its source document and location.
- Route low-confidence or contradictory fields to clinician review.
- Support correction, approval, rejection, and safe deletion of derived data.

### 3. Medication reconciliation

- Combine patient-reported, clinician-entered, document-extracted, and imported FHIR medication sources.
- Detect duplicate therapy, changed dose, missing medication, allergy conflict, and inconsistent status.
- Retrieve authoritative evidence from DailyMed and RxNorm.
- Display source, confidence, evidence, freshness, and uncertainty.
- Require clinician approval before altering the canonical medication list.

### 4. Patient companion

- Explain approved records in plain English or Spanish with evidence links.
- Collect medication adherence, symptoms, barriers, and follow-up answers.
- Support text and voice with transcript persistence and text fallback.
- Apply deterministic emergency and severe-risk rules before model reasoning.
- Recover safely from refresh, reconnect, quota exhaustion, and provider failure.

### 5. Symptom and adverse-drug-reaction workflow

- Capture onset, severity, duration, associated medication, red flags, and evidence.
- Generate Naranjo-assisted ADR assessments.
- Route assessments to clinician or pharmacist review.
- Generate MedWatch drafts without automatic submission.
- Immediately display appropriate safety guidance and escalation for urgent signals.
- Version and audit classifications, edits, and approvals.

### 6. Clinician workspace

- Prioritize patients using explainable, reproducible risk signals.
- Consolidate document, medication, symptom, adherence, ADR, and action review queues.
- Show a longitudinal patient timeline with source-backed evidence.
- Support approve, reject, amend, defer, and dismiss decisions.
- Update the dashboard after relevant patient actions.
- Never show a risk level without contributing factors and a freshness timestamp.

### 7. Scheduling, communication, and follow-up

- Propose appointment slots and let patients accept, decline, or request alternatives.
- Synchronize confirmed appointments across both portals.
- Export appointments to a standard calendar.
- Automatically send opted-in administrative reminders.
- Require clinician approval for clinical messages and escalation instructions.
- Create care-gap tasks for missed follow-up.
- Retry failed notifications and expose failures in an operations queue.

### 8. Continuity and interoperability

- Combine multi-provider history while preserving source provenance.
- Launch from a public SMART-on-FHIR sandbox with patient and encounter context.
- Import and export required FHIR R4 resources.
- Return evidence-backed CDS Hooks cards for patient review and medication prescribing.
- Generate clinician-reviewed handoff summaries and portable patient care summaries.

## Action authority

| Action | Required authority |
|---|---|
| Explain an approved record | Automatic with evidence |
| Ask follow-up questions | Automatic |
| Record patient-confirmed symptoms or adherence | Automatic |
| Send opted-in administrative reminders | Automatic |
| Propose appointment slots | Automatic |
| Confirm a patient-selected slot | Automatic |
| Draft a routine care message | Clinician approval |
| Change medication status or dosage | Clinician approval |
| Classify an ADR or issue a clinical escalation | Clinician approval |
| Generate a MedWatch report | Draft only |
| Diagnose, prescribe, or submit a regulatory report | Prohibited |

## Architecture

### Retained foundation

- Next.js/React patient and clinician portals
- FastAPI/Python backend
- Supabase/Postgres/pgvector/Auth/Storage/Realtime
- LangGraph for stateful clinical workflows
- DailyMed and RxNorm evidence
- Vercel and Cloud Run deployment structure

The project will be evolved, not rewritten. Weak abstractions will be replaced behind stable, versioned interfaces.

### Agent topology

Use four meaningful components:

1. **Care Coordinator:** owns conversation and workflow state; cannot approve clinical actions.
2. **Document and Evidence Worker:** extracts records, creates provenance, and retrieves authoritative evidence.
3. **Medication Safety Worker:** reconciles medication sources and produces discrepancy/ADR candidates.
4. **Follow-up Worker:** collects symptoms and adherence and manages follow-up tasks.

Scheduling, notifications, authentication, authorization, and database operations remain deterministic services rather than artificial agents.

### AI provider strategy

- Add a provider-neutral `ModelProvider` interface for structured generation, tool calling, streaming, multilingual text, audio capability, and telemetry.
- Use the current stable Gemini Flash free-tier model as the default for synthetic demonstrations.
- Evaluate MedGemma 1.5 4B for extraction and medical summarization where local or free hosted capacity permits.
- Evaluate NVIDIA NIM developer endpoints as an optional provider.
- Use NVIDIA NeMo Agent Toolkit for trace inspection, profiling, and internal evaluation when useful.
- Use Gemini Live as the primary zero-cost native-audio experiment, with text and transcript fallback.
- Keep Deepgram behind an adapter while existing credits remain available.
- Replace static model claims with repeatable task-specific benchmarks.

No free consumer endpoint may receive real PHI.

### Evidence and safety types

Every clinical output must carry:

- `EvidenceCitation`
- `SourceProvenance`
- `Confidence`
- `UncertaintyReason`
- `GeneratedAt`
- `ModelAndPromptVersion`
- `RequiredApproval`
- `ApprovalDecision`
- `ActionExecutionStatus`

Expose concise evidence-linked rationale and tool/action traces, not private model chain-of-thought.

Use deterministic logic for emergency symptoms, self-harm language, allergy conflicts, duplicate therapies, authorization, approval enforcement, malformed records, retries, and idempotency.

### Healthcare interoperability

Implement:

- SMART launch and OAuth callback
- Patient and encounter launch context
- FHIR R4 import/export for Patient, Practitioner, Organization, CareTeam, Condition, AllergyIntolerance, MedicationRequest, MedicationStatement, Observation, DocumentReference, Appointment, Communication, CarePlan, Provenance, and AuditEvent
- CDS Hooks `patient-view` and `medication-prescribe`
- Public-sandbox conformance tests
- Safe handling of missing and unsupported resources

### MCP and A2A

- Replace the custom MCP abstraction with an official MCP server.
- Expose structured document extraction, evidence lookup, medication reconciliation, follow-up, and appointment tools.
- Add authorization, request IDs, audit context, validation, and safe errors.
- Publish the A2A Agent Card at `/.well-known/agent-card.json`.
- Implement one genuine delegation: Care Coordinator to Medication Safety Worker.
- Support task submission, status, artifacts, cancellation, idempotency, and failure states.
- Do not claim protocol compatibility until conformance and end-to-end tests pass.

### Public interfaces

- `/api/v1/smart/launch`
- `/api/v1/smart/callback`
- `/api/v1/fhir/import`
- `/api/v1/fhir/export/{patient_id}`
- `/cds-services`
- `/cds-services/mediagent-patient-view`
- `/cds-services/mediagent-medication-safety`
- `/.well-known/agent-card.json`
- `/mcp`
- Versioned agent-task, clinician-review, and action-approval endpoints

Shared domain types will include `ClinicalFact`, `EvidenceCitation`, `SourceProvenance`, `MedicationDiscrepancy`, `RiskSignal`, `ClinicalRecommendation`, `ApprovalDecision`, `ActionEnvelope`, `AgentTask`, and `AuditRecord`.

## Delivery sequence

### Weeks 1–2: Revival and truth restoration

- Reconcile and remove preserved stale branches and stash.
- Replace stale documentation and backlog.
- Fix dependency security and the cancelled backend CI path.
- Lock dependencies and establish repeatable setup.
- Seed two synthetic clinics and longitudinal patients.

### Weeks 3–4: Data, provenance, and interoperability foundation

- Define canonical clinical facts and provenance.
- Implement FHIR validation and adapters.
- Complete SMART sandbox launch.
- Add approval and audit infrastructure.
- Establish model and voice provider adapters.

### Weeks 5–6: Records and medication safety

- Complete ingestion review, correction, and deletion.
- Add evidence-linked extraction provenance.
- Complete multi-source medication reconciliation.
- Build clinician reconciliation approval.

### Weeks 7–8: Patient companion and follow-up

- Complete conversation persistence and recovery.
- Complete adherence, symptom, and barrier collection.
- Deliver English and Spanish safety-tested flows.
- Complete deterministic urgent-risk overrides.

### Weeks 9–10: Clinician review and pharmacovigilance

- Consolidate review queues and patient timeline.
- Complete ADR/Naranjo and MedWatch draft workflows.
- Complete approvals, rejection, amendment, and escalation.

### Weeks 11–12: Scheduling, messaging, voice, and continuity

- Complete appointment lifecycle and calendar export.
- Complete care-team messaging and notification retries.
- Complete text-first voice and multilingual behavior.
- Complete multi-provider timeline and handoff.

### Weeks 13–14: Standards, evaluation, and hardening

- Complete CDS Hooks, MCP, and one A2A delegation.
- Run provider and architecture comparisons.
- Conduct clinician/pharmacist review.
- Complete security, accessibility, performance, and failure-mode testing.

### Weeks 15–16: Freeze and delivery

- Freeze features by 2026-12-04.
- Fix release-blocking defects only.
- Run full release qualification.
- Deploy a reproducible synthetic-data demonstration.
- Produce demo accounts, script, fallback recording, architecture/safety brief, operating guide, and startup presentation.

## Team ownership

| Lead | Primary ownership | Secondary review |
|---|---|---|
| Engineer 1 | Platform, Supabase, security, FHIR, SMART, deployment | Clinician authorization |
| Engineer 2 | Agent runtime, models, evidence, safety, evaluation | Voice and ADR |
| Engineer 3 | Patient portal, bilingual companion, adherence, voice | Scheduling |
| Engineer 4 | Clinician portal, review queues, PV, messaging, continuity | FHIR workflow UX |

Every sprint must deliver a vertical slice. Every pull request requires one peer reviewer. Safety-sensitive changes require AI/safety-owner review plus clinician or pharmacist validation. One engineer rotates as integration owner each sprint.

## Internal evaluation and release gates

Build 120 synthetic scenarios covering medication discrepancies, allergies, adherence, ADRs, urgent and non-urgent symptoms, incomplete records, provider contradictions, low-risk controls, and English/Spanish interactions. At least 40 high-risk cases receive clinician or pharmacist adjudication.

Release thresholds:

- 100% recall on deterministic emergency red-flag cases
- Zero unauthorized medication changes, diagnoses, or external clinical actions
- 100% approval enforcement for clinical actions
- 100% audit coverage for clinical recommendations and actions
- At least 95% valid evidence-to-source links
- At least 90% required-field extraction accuracy
- At least 90% medication-discrepancy precision and recall on the internal set
- No material English/Spanish safety disparity
- All eight critical journeys pass browser-level end-to-end tests
- Full CI completes in 20 minutes or less
- No critical dependency vulnerabilities
- WCAG 2.2 AA for core journeys
- Graceful behavior under timeout, quota exhaustion, network loss, duplicate requests, and malformed FHIR data
- No empty functional modules, reachable `NotImplementedError`, production mock success, or hardcoded patient identity

## Historical-work policy

Do not cherry-pick the preserved remote branches wholesale. First add regression coverage for real patient greeting, finite adherence percentage, missing task frequency, profile editing, non-hardcoded visits, document-type inference, upload-before-import, and expired import sessions. Reimplement only behaviors missing from current `main`, then delete the branches.

The April stash is based on an older snapshot and removes later reminder and clinician-review work. The refreshed tracker supersedes its checklist edits; discard it after the regression audit.

## References

- FDA Clinical Decision Support guidance: https://www.fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software
- ONC HTI-1: https://healthit.gov/regulations/hti-rules/hti-1-final-rule/
- SMART App Launch: https://hl7.org/fhir/smart-app-launch/
- CDS Hooks: https://cds-hooks.hl7.org/2.0/
- MCP 2026-07-28: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- A2A specification: https://a2a-protocol.org/latest/specification/
- MedGemma: https://developers.google.com/health-ai-developer-foundations/medgemma
- NVIDIA NeMo Agent Toolkit: https://developer.nvidia.com/agentiq
- HHS cloud guidance: https://www.hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing/index.html
