# Documentation map

This directory holds durable operating and product documents. Git history retains retired
spikes, phase plans, market surveys, and meeting notes; do not use those as current
implementation guidance.

## Read by purpose

| Need | Source of truth |
| --- | --- |
| Product boundary, decisions, ownership, and active work | `../.agent/PROJECT.md`, `../.agent/TEAM.md`, and `../.agent/TASKS.md` |
| Current implementation and delivery boundaries | `../.agent/ARCHITECTURE.md` |
| Model routing, safety controls, and evaluation limits | [AI runtime decision](decisions/ai-runtime-2026-09.md) |
| Document ingestion design and Cloud Run Job operation | [Document intelligence decision](document-intelligence-assessment.md) and [worker guide](document-ingestion-worker.md) |
| Database, RLS, migrations, and local setup | [Supabase setup](supabase_setup_guide.md) |
| Synthetic demonstration setup and fixture scope | [Demo environment](demo-environment.md) and [synthetic-data catalog](synthetic-data-catalog.md) |
| FHIR/SMART provenance and review behaviour | [Clinical-fact provenance](clinical-facts-provenance.md) and [SMART review mapping](smart-fhir-review-mapping.md) |

Only update a decision record when a reviewed implementation or an explicit team decision
changes it. Put work status and acceptance evidence in `../.agent/TASKS.md`, not in a second
tracker.
