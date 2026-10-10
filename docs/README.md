# Documentation map

This directory holds durable operating and product documents. Git history retains retired
spikes, phase plans, market surveys, and meeting notes; do not use those as current
implementation guidance.

## Read by purpose

| Need | Source of truth |
| --- | --- |
| Product boundary, decisions, ownership, and active work | `../.agent/PROJECT.md`, `../.agent/TEAM.md`, and `../.agent/TASKS.md` |
| Detailed task acceptance (required before coding) | [Backlog requirements](../.agent/specs/project-backlog-acceptance.md), or the issue's dedicated spec below |
| Care-plan generation, review, approval and Today contract | [PAT-005 specification](../.agent/specs/pat-005-clinician-approved-today-feed-plan.md) and [patient-upload evidence gate](patient-upload-care-plan-review-gate.md) |
| Scheduling and addressed human messaging | [Scheduling specification](../.agent/specs/sch-001-appointment-scheduling.md) and [conversation specification](../.agent/specs/com-001-two-way-conversations.md) |
| Latest prototype acceptance and pending presentation checks | [PAT-005 acceptance](pat-005-final-acceptance-2026-10-10.md) and [portal UI/UX evidence](portal-ui-ux-review-2026-10-10.md) |
| Current implementation and delivery boundaries | `../.agent/ARCHITECTURE.md` |
| Model routing, safety controls, and evaluation limits | [AI runtime decision](decisions/ai-runtime-2026-09.md) |
| Document ingestion design and Cloud Run Job operation | [Document intelligence decision](document-intelligence-assessment.md) and [worker guide](document-ingestion-worker.md) |
| Database, RLS, migrations, and local setup | [Supabase setup](supabase_setup_guide.md) |
| Synthetic demonstration setup and fixture scope | [Demo environment](demo-environment.md) and [synthetic-data catalog](synthetic-data-catalog.md) |
| Auth-account QA, linking and recovery | [Demo auth checklist](demo-environment.md#auth-account-qa) |
| Deferred database advisor findings | [Database performance follow-up](deferred_database_performance_work.md); not an instruction to change staging |
| FHIR/SMART provenance and review behaviour | [Clinical-fact provenance](clinical-facts-provenance.md) and [SMART review mapping](smart-fhir-review-mapping.md) |

Only update a decision record when a reviewed implementation or an explicit team decision
changes it. Keep current status/owner/next step in `../.agent/TASKS.md`; keep detailed
requirements in linked specs and reproducible acceptance evidence in linked reports.
Do not create parallel trackers or append chronological work logs to the board.

## Retention rule

Keep a document when it defines an active contract, repeatable runbook, unresolved
decision, or acceptance evidence needed to judge a task. Being implemented does not
make a specification obsolete. Consolidate duplicate checklists and completed work
logs into their canonical guide/report, repair inbound links, and let Git preserve
the removed material. The start-of-task workflow requires the selected spec or
backlog acceptance section, so detailed requirements are not forgotten archives.
