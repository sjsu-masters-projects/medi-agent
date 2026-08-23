# MediAgent contributor contract

This is the repository's canonical instruction source for coding assistants and
human contributors. Keep it concise, durable, and version controlled. Put
feature-specific detail in the linked source documents rather than duplicating
it here.

## Start every task this way

1. Inspect the branch and working tree. Preserve unrelated user changes.
2. Read [`.agent/TASKS.md`](.agent/TASKS.md), then the active plan named at its
   top. Select an existing task or create a scoped task entry before expanding
   the product surface.
3. Read the relevant routing documents below and inspect adjacent code and
   tests before editing.
4. State the acceptance path, assumptions, and any missing decision. Implement
   and verify the smallest coherent change that satisfies that path.
5. Update the task tracker and affected product or operational documentation
   whenever behavior, contracts, rollout, or evidence changes.

## Product boundaries that are not optional

- MediAgent is supervised clinical decision support for California outpatient
  chronic-care and polypharmacy workflows. It is not an autonomous clinician.
- Use only synthetic or rigorously de-identified data. Do not claim HIPAA or
  production readiness without the required agreements and review.
- Supported patient-facing locales are American English (`en-US`) and Mexican
  Spanish (`es-MX`).
- Imported clinical data is a candidate with resource-level provenance. It
  cannot overwrite approved local clinical truth without the established
  review and approval path.
- Never expose private chain-of-thought, credentials, service-role keys, or
  real patient data in code, logs, fixtures, commits, pull requests, or docs.

## Route work to the right sources

| Change surface | Read before editing | Verify before review |
| --- | --- | --- |
| Any task | `.agent/TASKS.md`, `.agent/PROJECT.md`, `.agent/TEAM.md` | Scope, acceptance criteria, and tracker state are current |
| Backend/API | `backend/README.md`, `.agent/CODING_STANDARDS.md`, adjacent router/service/tests | Focused tests; Ruff and mypy for changed Python |
| Patient or clinician portal | Relevant app `README.md`, `.agent/DESIGN_SYSTEM.md`, adjacent UI/tests | Lint, typecheck, focused tests, and build when practical |
| Database, Auth, storage, or Supabase | `docs/supabase_setup_guide.md`, migrations, relevant RLS tests | Migration validation and the least-privilege/RLS path; never improvise remote SQL |
| Synthetic demo data | `docs/demo-environment.md`, `docs/synthetic-data-catalog.md`, fixture README | Fixture checksum, dry run, idempotency, and documented synthetic-only boundary |
| Clinical provenance, approvals, FHIR, or SMART | `docs/clinical-facts-provenance.md`, `.agent/specs/int-002-003-interoperability-plan.md` | Provenance, authorization, error, and review behavior—not only a happy path |
| Architecture or cross-cutting behavior | `.agent/ARCHITECTURE.md`, active specification | Update the decision record and integration tests as needed |
| CI or dependencies | `.github/workflows/ci.yml`, lockfiles, `.agent/TASKS.md` | Reproducible install and all relevant required checks |

## Safe delivery rules

- Do not edit, print, commit, or upload `.env`, `.env.local`, credentials,
  tokens, database dumps, or production-like data. Use `.env.example` for
  documented configuration changes.
- Do not discard, overwrite, or reformat unrelated work. Avoid destructive
  Git commands and never force-push shared history without explicit approval.
- Do not apply remote migrations, reset or seed a remote environment, deploy,
  merge a pull request, or change external service configuration without the
  requester explicitly authorizing that exact action.
- Keep routers thin; put business rules in services; validate at boundaries;
  add tests at the level where the behavior is owned.
- Prefer existing shared types, services, fixtures, and patterns over parallel
  implementations. Do not add schema solely to make a demo look richer.

## Branches, commits, reviews, and evidence

- Start short-lived branches from current `main`. Use product- and work-focused
  names such as `feature/import-review` or `fix/appointment-validation`.
- Branch names, commit messages, source comments, and product documentation
  must not identify an authoring tool, provider, or assistant. The compatibility
  files named below are the sole documentation exception.
- Use conventional, human-readable commit messages. Keep one coherent concern
  per pull request whenever possible.
- Before requesting review, run the relevant checks from `CONTRIBUTING.md`,
  record exact commands and outcomes, identify manual verification, and call
  out follow-up work honestly.
- Never describe a task as complete merely because a route, mock, or UI exists.
  Completion needs the agreed behavior, authorization, error handling, audit
  behavior where applicable, tests, and user-visible acceptance path.

## Supported coding environments

- **Codex:** reads this root `AGENTS.md` directly.
- **Claude Code:** reads root `CLAUDE.md`, which imports this file.
- **Cursor:** reads this file and `.cursor/rules/mediagent-workflow.mdc`, whose
  only job is to route work back here.

Maintain shared instructions in this file. Do not create `.cursorrules`, copy
the guidance into multiple files, or commit personal preferences. See
[`docs/contributor-agent-workflow.md`](docs/contributor-agent-workflow.md) for
the maintainer guide and first-task checklist.
