# Documentation

Start with the task you need to complete. Setup, operating procedures, product
requirements and verification evidence have separate homes.

## Start here

| Goal | Read |
| --- | --- |
| Understand the product | [Project README](../README.md) and [product scope](../.agent/PROJECT.md) |
| Run a local checkout | [Quick start](../README.md#run-locally) and [local development](development.md) |
| Make a contribution | [Contributor guide](../CONTRIBUTING.md) and [coding standards](../.agent/CODING_STANDARDS.md) |
| Find current work and acceptance gaps | [Task board](../.agent/TASKS.md) |
| Verify deployed work, log bugs and sign off | [QA handoff](qa-handoff-2026-10.md) |
| Understand service and data boundaries | [Architecture](../.agent/ARCHITECTURE.md) |
| Maintain these documents | [Documentation maintenance](maintaining-docs.md) |

## Set up and operate

| Guide | Covers |
| --- | --- |
| [Supabase setup and migrations](supabase_setup_guide.md) | Database recreation, ledger/checksum rules, RLS and Auth setup |
| [Cloud infrastructure](../.agent/CLOUD_INFRASTRUCTURE_GUIDE.md) | Cloud Run, Jobs, Scheduler, deployment and logs |
| [Nora worker setup](chat-worker-setup.md) | Queue, task authentication, runtime variables, least-privilege service accounts and rollback |
| [Document ingestion worker](document-ingestion-worker.md) | Ingestion job operation, recovery and service boundaries |
| [Symptom-intake rollout](pat-002-b-rollout.md) | Candidate eligibility, activation and safe rollout checks |
| [Synthetic environment](demo-environment.md) | Fictional accounts, auth QA, fixtures and reset boundaries |
| [Synthetic data catalog](synthetic-data-catalog.md) | Dataset scope, provenance and supported scenarios |
| [Expo presentation script](expo-demo-script.md) | Prepared history, live segment and rehearsal record |
| [Project limitations](project-limitations.md) | Architecture, supported scope and evidence boundaries |
| [Expo recovery](expo-recovery.md) | Safe fallback actions without unapproved resets or configuration changes |
| [Email templates](email-templates/README.md) | The installable reset template, reference designs and Auth email constraints |

Operating guides contain commands that may change external systems. Reading or
merging a guide is not permission to run those commands.

## Product and workflow contracts

Read the task's linked specification before implementing a change. Specifications
remain contracts after their implementation is merged.

| Area | Canonical requirements |
| --- | --- |
| Approved plans and Today | [PAT-005](../.agent/specs/pat-005-clinician-approved-today-feed-plan.md), [upload evidence gate](patient-upload-care-plan-review-gate.md) |
| Clinics and care-team plan ownership | [CLN-003](../.agent/specs/clin-003-multi-clinic-clinicians.md), [PLAN-002](../.agent/specs/plan-002-care-plans-per-care-team.md) |
| Bilingual review | [LOC-001](../.agent/specs/loc-001-bilingual-approved-wording.md), [interface wording review](../.agent/specs/loc-001-interface-review.md), [LOC-003](../.agent/specs/loc-003-english-first-clinician-review.md), [source-linked review pack](spanish-draft-review-pack.md) |
| Confirmed symptoms and follow-up | [PAT-002-B](../.agent/specs/pat-002-b-confirmed-symptom-intake-plan.md), [ADR loop](../.agent/specs/pv-001-c-adr-loop-gap-fixes/requirements.md), [Naranjo answer coverage](../.agent/specs/pv-001-d-naranjo-answer-coverage.md) |
| Nora and durable conversations | [Grounded answers](../.agent/specs/nora-002-grounded-answers.md), [recovery and document focus](../.agent/specs/pat-001-a-nora-turn-recovery.md), [voice](../.agent/specs/voice-001-voice-mode.md) |
| Private human messages and visits | [Conversations](../.agent/specs/com-001-two-way-conversations.md), [scheduling](../.agent/specs/sch-001-appointment-scheduling.md) |
| Alerts and selective email | [Notification centre](../.agent/specs/not-001-notification-centre.md), [email flows](../.agent/specs/email-001-email-flows.md) |
| Records and reconciliation | [Workflow completion](../.agent/specs/expo-workflow-completion.md), [record clarity](../.agent/specs/rec-001-patient-record-clarity.md), [FHIR/SMART plan](../.agent/specs/int-002-003-interoperability-plan.md) |
| Care handoff | [Handoff summary and sharing](../.agent/specs/con-001-care-handoff-summary.md) |
| Safety and dependency security | [Safety hardening](../.agent/specs/safety-release-completion.md), [COM and SAFE gap audit](../.agent/specs/com-safe-gap-audit-2026-10.md), [dependency audit](../.agent/specs/sec-004-dependency-audit.md) |
| Portal design changes | [Reference redesign](../.agent/specs/ux-002-reference-redesign.md), [ADR and MedWatch workspace](../.agent/specs/ux-005-adr-medwatch-workspace.md), [clinician schedule](../.agent/specs/ux-006-clinician-schedule.md) |
| Other task acceptance | [Backlog requirements](../.agent/specs/project-backlog-acceptance.md) |
| Synthetic care-plan rehearsal | [Scenario](pat-005-synthetic-scenario.md), [grouped acceptance contract](../.agent/specs/demo-care-loop-followups.md) |

## Technical reference and decisions

| Topic | Reference |
| --- | --- |
| Backend packages, endpoints and test commands | [Backend README](../backend/README.md) |
| Patient and clinician application setup | [Patient README](../apps/patient-portal/README.md), [clinician README](../apps/clinician-portal/README.md) |
| Clinical-fact provenance and import review | [Provenance](clinical-facts-provenance.md), [FHIR mapping](smart-fhir-review-mapping.md) |
| Upload types and safety | [Document format policy](document-format-policy.md) |
| Document processing architecture | [Document intelligence decision](decisions/document-intelligence.md) |
| Model routing, safety and evaluation limits | [Runtime decision](decisions/ai-runtime-2026-09.md), [quality requirements](../.agent/specs/ai-005-agent-quality.md), [repeatable evaluation](demo-ai-evaluation.md) |
| Chat transport and workers | [Runtime decision](decisions/realtime-and-workers-2026-10.md), [worker contract](../.agent/specs/ops-006-workers-and-event-stream.md) |
| Portal design and icons | [Design system](../.agent/DESIGN_SYSTEM.md), [icon integration](brand-icons.md) |
| Deferred database optimization | [Performance follow-up](deferred_database_performance_work.md) |

## Verification and history

[Evidence index](evidence/README.md) groups deployed rechecks, symptom-intake
acceptance, care-plan acceptance, record clarity, wording review and dated rollout
receipts. Each report states what was tested and what was not. The task board owns
the current verdict.

[Meeting records](../meetings/README.md) are historical context, not current
implementation instructions. Git history preserves removed duplicates and
completed session notes. There is no separate archive or status tracker.

## Directory layout

```text
docs/
  README.md                 Find a guide by purpose
  development.md            Configuration and local troubleshooting
  maintaining-docs.md       Documentation rules and review checklist
  decisions/                Architecture and runtime decisions
  evidence/                 Dated verification reports and their index
  email-templates/          Installable reset template and guidance
    reference/              Design references for future email work; nothing sends them
  *.md                      Established operating guides and references

.agent/
  TASKS.md                  Current work and remaining acceptance
  PROJECT.md                Product boundaries
  ARCHITECTURE.md           System design and contracts
  specs/                    Detailed feature requirements
```

Keep one source per subject. Link to it rather than copying its status, commands
or variable defaults into another guide.
