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

## Features

Each feature doc says what the feature does, the rules it must keep, why it was built that way
and where the code is. Read the one for your area before changing it. Status lives in the
[task board](../.agent/TASKS.md), and proof of what was tested lives in [evidence](evidence/README.md).

| Feature | Reference |
| --- | --- |
| Nora chat and grounded answers | [Nora chat](features/nora-chat.md) |
| Voice | [Voice mode](features/voice-mode.md) |
| Confirmed symptoms | [Symptom intake](features/symptom-intake.md), [question releases](../backend/src/app/intake/question_library/README.md) |
| Adverse events, Naranjo and MedWatch | [Adverse events](features/adverse-events.md) |
| Approved plans and Today | [Care plans and Today](features/care-plans-and-today.md), [upload evidence gate](patient-upload-care-plan-review-gate.md), [synthetic scenario](pat-005-synthetic-scenario.md) |
| Clinics, care teams and handoff | [Clinics and care teams](features/clinics-and-care-teams.md) |
| Bilingual wording | [Language](features/language.md), [source-linked review pack](spanish-draft-review-pack.md) |
| Private messages, alerts and email | [Messaging and alerts](features/messaging-and-alerts.md) |
| Visits | [Scheduling](features/scheduling.md) |
| Records, reconciliation and FHIR/SMART | [Patient records](features/patient-records.md), [provenance](clinical-facts-provenance.md), [FHIR mapping](smart-fhir-review-mapping.md) |
| Safety floor and clinical actions | [Safety](features/safety.md) |
| Models, workers and realtime | [AI runtime and workers](features/ai-runtime-and-workers.md) |
| Portal layout and motion | [Portal design](features/portal-design.md), [design system](../.agent/DESIGN_SYSTEM.md) |
| Work not yet built | [Backlog requirements](../.agent/specs/project-backlog-acceptance.md) |

## Technical reference

| Topic | Reference |
| --- | --- |
| Backend packages, endpoints and test commands | [Backend README](../backend/README.md) |
| Patient and clinician application setup | [Patient README](../apps/patient-portal/README.md), [clinician README](../apps/clinician-portal/README.md) |
| Clinical-fact provenance and import review | [Provenance](clinical-facts-provenance.md), [FHIR mapping](smart-fhir-review-mapping.md) |
| Upload types and safety | [Document format policy](document-format-policy.md) |
| Document processing architecture | [Patient records](features/patient-records.md) |
| Model routing, safety and evaluation limits | [AI runtime](features/ai-runtime-and-workers.md), [Nora chat](features/nora-chat.md), [repeatable evaluation](demo-ai-evaluation.md) |
| Chat transport and workers | [AI runtime and workers](features/ai-runtime-and-workers.md) |
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
  features/                 What each feature does and the rules it must keep
  evidence/                 Dated verification reports and their index
  email-templates/          Installable reset template and guidance
    reference/              Design references for future email work; nothing sends them
  *.md                      Established operating guides and references

.agent/
  TASKS.md                  Current work and remaining acceptance
  PROJECT.md                Product boundaries
  ARCHITECTURE.md           System design and contracts
  specs/                    Requirements for work not yet built
```

Keep one source per subject. Link to it rather than copying its status, commands
or variable defaults into another guide.
