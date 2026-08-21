# MediAgent — Product Context

> **Current direction:** August–December 2026 revival. This file records the
> product decision and boundaries; `.agent/TASKS.md` is the execution tracker.

## Product thesis

MediAgent is a supervised, evidence-backed, bilingual closed-loop care platform for
outpatient clinics managing chronic-care and polypharmacy patients. It is not a
generic chat product and it is not an autonomous clinician.

The demonstrated loop is: import a record with provenance; reconcile medication and
surface a safety discrepancy; collect symptoms, adherence, or barriers; route an
evidence-backed candidate action to a clinician; execute an approved follow-up; and
retain the result in the patient's longitudinal timeline.

## Focus and boundaries

| Area | Decision |
| --- | --- |
| Buyer and setting | Outpatient clinic or small clinic network |
| Evaluated cohort | Polypharmacy chronic care: diabetes, hypertension, hyperlipidemia, and related comorbidities |
| Users | Patients, clinicians, pharmacists/reviewers, and clinic staff |
| Languages | American English (`en-US`) and Mexican Spanish (`es-MX`) |
| Data | Synthetic or rigorously de-identified data only |
| Clinical posture | Supervised clinical decision support |

MediAgent must not diagnose, prescribe, autonomously modify medication, or submit a
regulatory report. A real-PHI or HIPAA-production claim is out of scope without the
required agreements, compliant infrastructure, and legal review.

## Action authority

| Action | Authority |
| --- | --- |
| Explain an approved record with evidence | Automatic |
| Ask follow-up questions; record patient-confirmed symptoms or adherence | Automatic |
| Send opted-in administrative reminders; propose or confirm a patient-selected slot | Automatic |
| Draft routine care message | Clinician approval |
| Change medication status or dosage | Clinician approval |
| Classify an ADR or issue a clinical escalation | Clinician approval |
| Generate a MedWatch report | Draft only |
| Diagnose, prescribe, submit a regulatory report | Prohibited |

Every clinical output must ultimately carry its source, confidence, uncertainty,
generation timestamp/version, required approval, approval decision, and action
execution status. Show concise evidence-linked rationale and action traces; do not
store or present private chain-of-thought.

## Operating decisions

1. Evolve the current Next.js, FastAPI, Supabase, LangGraph, DailyMed, RxNorm, Vercel,
   and Cloud Run foundation rather than rewriting it.
2. Use four meaningful worker boundaries: Care Coordinator, Document and Evidence,
   Medication Safety, and Follow-up. Scheduling, notifications, authentication,
   authorization, and database operations are deterministic services.
3. Demonstrate FHIR R4 and SMART-on-FHIR with a public sandbox, not merely docs.
4. Treat MCP and A2A as interoperability commitments, not labels. Claim compatibility
   only after an official endpoint, conformance coverage, and end-to-end flow exist.
5. Keep provider choices replaceable and task-benchmarked. No free consumer endpoint
   receives real PHI.

## Decision history

The March 2026 decisions below are retained as history. They are **superseded where
they conflict with the August 2026 revival plan**, not deleted.

| Ref | Historical decision | Current status |
| --- | --- | --- |
| D1 | PWA portals | Retained |
| D2 | Multi-provider care model | Retained, subject to provenance and authorization work |
| D3, D14, D17, D18 | Fixed model choices and model-specific reasoning claims | Superseded by provider-neutral, repeatably benchmarked routing; no chain-of-thought claims |
| D4 | Deepgram voice | Retained behind an adapter; transcript/text fallback required |
| D5 | Supabase platform | Retained |
| D6 | Syncfusion viewer | Retained only where licensed and actually used |
| D7 | Next.js, Redux, Tailwind | Retained foundation |
| D8 | LangGraph orchestration | Retained only for the four approved worker boundaries |
| D9 | Monorepo | Retained |
| D10 | FHIR-aligned model | Strengthened to validated FHIR R4 import/export and provenance |
| D11 | In-app and email messaging | Retained; clinical content requires approval |
| D12 | MCP for tool access | Superseded by official MCP server and conformance proof |
| D13 | A2A Agent Cards and external discovery | Superseded by one authenticated, tested internal delegation first |
| D15 | Native-audio exploration | Optional experiment with text/transcript fallback |
| D16 | Medical-model evaluation | Retained as task-specific evaluation, not a dependency |

## References

- `.agent/ARCHITECTURE.md` — verified implementation shape and target boundaries
- `.agent/TASKS.md` — status, owners, and acceptance checklist
- `.agent/specs/mediagent-revival-aug-dec-2026.md` — approved revival plan
- `CONTRIBUTING.md` — contribution and review expectations
