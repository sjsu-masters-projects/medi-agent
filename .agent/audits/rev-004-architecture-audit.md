# REV-004 Architecture Audit

**Audited:** 2026-08-20
**Scope:** `backend/src/app` production Python modules and registered API routes.

## Findings and disposition

| Finding | Disposition |
| --- | --- |
| Five registered ADR route handlers raised `NotImplementedError` | Removed the router registration and module; no client or backend caller referenced the route |
| Four ADR service methods raised `NotImplementedError` | Removed with the unreachable router surface |
| Empty A2A package modules (`agent_card`, `router`, `task_manager`) | Removed; actual task lifecycle is `services/a2a_task_service.py` |
| Empty agent shells for pharmacovigilance, pre-visit, and scheduling | Removed; they had no imports or callers |
| Empty ingestion class module | Removed; the active ingestion graph remains |
| Empty seed, tool, and utility modules | Removed; none had imports or callers |
| Empty package markers | Retained where they establish Python package boundaries |
| `pass` in abstract `BaseAgent.process` and exception classes | Retained; these are valid abstract/type declarations |
| Empty-dictionary returns in feed and cron error/fallback paths | Retained; these are explicit failure/empty-result behavior, not mock success |

## Worker and service result

The supported boundaries are Care Coordinator, Document and Evidence, Medication
Safety, and Follow-up. The current non-empty implementation maps chat triage,
ingestion/explanation, symptom-to-ADR review lifecycle, and symptom/adherence/reminder
flows to those boundaries. Scheduling, notification delivery, authorization, database
access, retries, and idempotency remain deterministic services.

## Prevention

`backend/scripts/check_production_placeholders.py` now runs in CI. It rejects empty
production modules, non-abstract empty functions, and every production
`NotImplementedError`. The check intentionally permits package markers, abstract
methods, and explicit empty collection results where they implement a documented
failure or no-result condition.
