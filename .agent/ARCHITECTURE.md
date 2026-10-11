# MediAgent — Architecture Truth Record

> **Updated:** 2026-10-11. This distinguishes code that exists today from the
> approved delivery target. Do not present a planned interface as deployed.

## Current implementation

```text
Patient portal (Next.js) ─┐
                           ├─ HTTPS / WebSocket ─ FastAPI `/api/v1` ─ Supabase
Clinician portal (Next.js)┘                         │
                                                    ├─ document ingestion and explanation
                                                    ├─ chat, triage, symptom capture
                                                    ├─ medication/adherence/feed/reminder services
                                                    ├─ internal delegated-task lifecycle and retry worker
                                                    ├─ shared medication/condition reference cache
                                                    │   (MedlinePlus, DailyMed, RxNorm; weekly refresh)
                                                    └─ voice-provider adapters
```

The repository contains two Next.js applications (`apps/patient-portal` and
`apps/clinician-portal`), a FastAPI API (`backend/src/app`), and shared TypeScript
types (`packages/shared`). Supabase provides authentication, Postgres, storage,
realtime, and row-level access controls. The backend exposes versioned REST routes
and authenticated patient chat/voice WebSockets; it also has health and version
endpoints.

Implemented route groups include auth/MFA, clinics, patients, clinicians, documents,
medications, obligations, adherence, chat, care plans, care conversations, feed,
appointments, notifications, the notification centre, reminders, staff, SMART, and cron;
chat and voice also have patient WebSockets. The previous standalone ADR REST group was removed because every
handler was an unimplemented placeholder. Assigned clinicians can now inspect deterministic
Naranjo evidence and atomically mark a draft reviewed, dismiss it, or request information. Every
review action writes an immutable ADR audit event. Confirmed-report intake, evidence-driven
reassessment, and MedWatch drafting remain delivery targets.

## Worker and service boundaries

Only these four work boundaries are supported by the product direction:

| Boundary | Current implementation anchor | Authority |
| --- | --- | --- |
| Care Coordinator | Chat triage, per-conversation stored history, and read-only tools over the patient's record, documents and the shared reference cache | Guides, explains and routes; cannot approve clinical action |
| Document and Evidence Worker | Document ingestion graph, extraction and explanation | Produces source-linked candidates |
| Medication Safety Worker | Rule-based symptom-to-ADR task lifecycle and clinician-review candidate | Produces review candidate; cannot submit or alter medication |
| Follow-up Worker | Symptom capture, adherence, reminders, and care-gap follow-up | Collects and schedules follow-up only |

The current chat runtime is implemented under `backend/src/app/adk/`: a Care Coordinator
uses a registry with explicit model transports, budgets, fallback, deterministic outcomes,
and safety/tool-policy plugins. The older `app/agents` modules are compatibility paths,
not the starting point for new agent work. The empty pre-visit, scheduling,
pharmacovigilance, and unused delegation shells were removed in REV-004.

Scheduling, notification delivery, authentication/authorization, database access,
retry/idempotency, and approval enforcement are deterministic services. Model output
may suggest or draft; it must not decide authority, bypass rules, or write an approved
clinical fact without review.

## Nora's knowledge and conversations (NORA-002)

General medication and condition information is public reference text shared by every
patient: MedlinePlus plain-language summaries (English and Spanish), DailyMed label
sections (dosage excluded) and RxNorm name resolution, cached in `health_knowledge` and
re-checked weekly by the `mediagent-health-knowledge-refresh` Cloud Run Job. What is
specific to one patient (their medications, conditions, documents and care plan) is read
by patient-scoped tools whose patient comes from session state, never from the model. The
reply's source line is written by the server from the tool results. Chat messages belong
to a conversation (`session_id`): one per day by default, plus any the patient starts; the
model's recap is built from stored messages, so a restart loses nothing. Design and
checks: [NORA-002](specs/nora-002-grounded-answers.md).

## Human conversations (COM-001-B)

COM-001-B adds deterministic in-app conversations partitioned by patient and
individual linked clinician, not by AI session. Explicit recipient selection
prevents broadcast across multiple care teams. Sender identity comes from the
authenticated actor; clinic labels and permissions come from current assignment.
Message writes, idempotency and audit commit atomically, and assignment revocation
blocks further access. Nora transcripts and legacy operational notifications are
separate stores and UI views. A clinician explicitly sending their own text is the
approval action; the model does not generate or send human conversation messages.

The contract is `.agent/specs/com-001-two-way-conversations.md`. Merged in #139 and
deployed; live acceptance is recorded in TASKS (COM-001-B Done). No real-PHI production
readiness is claimed.

## Notifications (NOT-001/NOT-002)

NOT-001 extends deterministic notifications with role-scoped event receipts and
current clinician work. Source transitions capture events in the source transaction;
recipient delivery is retryable and duplicate-safe. Notification reads are personal
presentation state, not approval or clinical resolution. Private-message events stay
bound to the addressed patient/clinician thread; shared work follows current clinical
assignment and source state. Signed bulk-read snapshots exclude later arrivals.
Merged in #148 and #149 and deployed; `051_notification_centre.sql` and 052–056 were
applied October 11. See `.agent/specs/not-001-notification-centre.md` for the contract.

## Evidence, FHIR, and safety

The codebase validates a supported import subset with maintained FHIR R4B models and
emits R4-compatible payload fields. SMART authorization-code + PKCE handling stores
only encrypted transient verifier state, raw FHIR envelopes, and a short-lived local
review handoff; SMART identity never grants local clinical authority. Imported records
are bound to an assigned synthetic patient and become pending provenance-backed facts.
Canonical clinical-fact provenance retains citations, confidence/uncertainty, review
state, lineage queries, and lifecycle audit events. Exact public-sandbox and Inferno
conformance, FHIR export, and action-approval infrastructure remain
acceptance work rather than completed integrations.

Safety rules are deterministic before probabilistic routing for emergency signals,
authorization, malformed data, retries, and idempotency. The user-facing result must
include concise evidence and uncertainty; private model reasoning is neither exposed
nor relied on as an audit record.

Generic document intake is deliberately narrower than "any medical file": PDF, JPEG,
PNG, WebP, and TIFF are the supported evidence artifacts. Both portals render private,
short-lived source URLs with local PDF.js or native image rendering; TIFF retains its
original source and receives a bounded derived PDF preview. FHIR, CDA, and DICOM require
their dedicated review paths. The coordinator receives only a server-authorized selected
document's bounded summary for that chat turn, never a model-selected document identifier,
private source URL, or the original file. See
[`docs/document-format-policy.md`](../docs/document-format-policy.md).

The current model decision is recorded in
[`docs/decisions/ai-runtime-2026-09.md`](../docs/decisions/ai-runtime-2026-09.md).

## Internal tools and worker delegation

In-process provider adapters expose validated tools to MediAgent's runtime. The
backend persists delegated-task status, retries, duplicate protection and clinician
timeline support for the symptom-to-medication-safety handoff. These are internal
application capabilities, not externally published agent services.

Care Coordinator → Medication Safety work retains request identity, authorization,
evidence/results, bounded failures and audit. External discovery or protocol servers
are not required by the product and are not planned delivery work.

## Deployment and verification

The deployment structure is FastAPI on Cloud Run and the portals on Vercel. Two Cloud
Run Jobs share the backend image: `mediagent-document-ingestion` (triggered every 5
minutes) and `mediagent-health-knowledge-refresh` (weekly). Cloud Scheduler also calls
the backend's reminder dispatch route. Triggers, auth and run logs are in
[CLOUD_INFRASTRUCTURE_GUIDE.md §5](CLOUD_INFRASTRUCTURE_GUIDE.md#5-scheduled-jobs-cloud-scheduler-and-run-logs). CI checks
dependency locks/audit, backend lint/format/type/tests/coverage, migrations, secrets,
portal lint/type/tests/build, and production placeholder protection. CI configuration
is the authoritative source for exact jobs.

For a clean local setup and full validation use:

```bash
./scripts/bootstrap-and-validate.sh
```

The command creates the backend virtual environment, installs locked dependencies,
installs both portal dependencies, and runs the local quality gates. It does not create
credentials or contact a clinical system.
