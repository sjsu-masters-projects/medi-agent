# MediAgent — Architecture Truth Record

> **Updated:** 2026-08-20. This distinguishes code that exists today from the
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
                                                    └─ DailyMed/RxNorm and voice-provider adapters
```

The repository contains two Next.js applications (`apps/patient-portal` and
`apps/clinician-portal`), a FastAPI API (`backend/src/app`), and shared TypeScript
types (`packages/shared`). Supabase provides authentication, Postgres, storage,
realtime, and row-level access controls. The backend exposes versioned REST routes
and authenticated patient chat/voice WebSockets; it also has health and version
endpoints.

Implemented route groups include auth/MFA, clinics, patients, clinicians, documents,
medications, obligations, adherence, chat, feed, appointments, notifications,
reminders, staff, and cron. The previous ADR REST group was removed because every
handler was an unimplemented placeholder. A clinician-facing ADR workflow remains a
delivery target, not an available public API.

## Worker and service boundaries

Only these four work boundaries are supported by the product direction:

| Boundary | Current implementation anchor | Authority |
| --- | --- | --- |
| Care Coordinator | Chat triage and persisted conversation state | Guides and routes; cannot approve clinical action |
| Document and Evidence Worker | Document ingestion graph, extraction, explanation, DailyMed/RxNorm retrieval | Produces source-linked candidates |
| Medication Safety Worker | Rule-based symptom-to-ADR task lifecycle and clinician-review candidate | Produces review candidate; cannot submit or alter medication |
| Follow-up Worker | Symptom capture, adherence, reminders, and care-gap follow-up | Collects and schedules follow-up only |

The existing `triage`, `ingestion`, `symptom`, and clinician summarization modules
are implementation components of those boundaries, not a claim of additional
autonomous workers. The empty pre-visit, scheduling, pharmacovigilance, and A2A
shells were removed in REV-004.

Scheduling, notification delivery, authentication/authorization, database access,
retry/idempotency, and approval enforcement are deterministic services. Model output
may suggest or draft; it must not decide authority, bypass rules, or write an approved
clinical fact without review.

## Evidence, FHIR, and safety

The codebase validates a supported import subset with maintained FHIR R4B models and
emits R4-compatible payload fields. SMART authorization-code + PKCE handling stores
only encrypted transient verifier state, raw FHIR envelopes, and a short-lived local
review handoff; SMART identity never grants local clinical authority. Imported records
are bound to an assigned synthetic patient and become pending provenance-backed facts.
Canonical clinical-fact provenance retains citations, confidence/uncertainty, review
state, lineage queries, and lifecycle audit events. Exact public-sandbox and Inferno
conformance, FHIR export, CDS Hooks, and action-approval infrastructure remain
acceptance work rather than completed integrations.

Safety rules are deterministic before probabilistic routing for emergency signals,
authorization, malformed data, retries, and idempotency. The user-facing result must
include concise evidence and uncertainty; private model reasoning is neither exposed
nor relied on as an audit record.

## MCP and A2A status

`backend/src/app/mcp` currently contains in-process provider adapters; it is **not**
an official MCP server or a published `/mcp` endpoint. The backend also persists an
internal delegated-task lifecycle (`a2a_tasks`) with status, retry, idempotency, and
clinician timeline support for the symptom-to-medication-safety handoff. It is **not**
a published A2A Agent Card or externally conformant A2A service.

The target is one authenticated Care Coordinator → Medication Safety delegation with
request IDs, authorization, artifacts, cancellation, idempotency, failures, and
end-to-end tests. Add an official MCP surface and an A2A Agent Card only when that
conformance work is complete.

## Deployment and verification

The deployment structure is FastAPI on Cloud Run and the portals on Vercel. CI checks
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
