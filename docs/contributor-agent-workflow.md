# Contributor agent workflow

This guide gives every supported coding environment the same repository context
without maintaining three competing instruction sets. It is for contributors
who use Codex, Claude Code, or Cursor while working in MediAgent.

## One canonical source

`AGENTS.md` at the repository root is the shared contributor contract. It
contains the start-of-task sequence, product boundaries, task-routing table,
safety rules, and pull-request expectations.

| Environment | Repository file | How shared instructions arrive |
| --- | --- | --- |
| Codex | `AGENTS.md` | Root project instructions are loaded directly. |
| Claude Code | `CLAUDE.md` | The tracked file imports `AGENTS.md`. |
| Cursor | `AGENTS.md` and `.cursor/rules/mediagent-workflow.mdc` | The project rule directs every task to the canonical file. |

The compatibility files deliberately contain no copy of the instructions. When
the team changes a shared rule, edit `AGENTS.md` once and review the resulting
diff as an ordinary documentation change. Do not add the deprecated
`.cursorrules` file.

## First task checklist

Before asking an assistant to implement anything, make the task concrete:

1. Name the existing `.agent/TASKS.md` item or create a small, testable task.
2. State the user outcome and acceptance checks, not merely an implementation
   idea.
3. Point to the relevant screen, API, migration, or specification if one is
   known.
4. Say whether a remote action is authorized. Remote migrations, deployment,
   resets, seeds, merges, and service configuration changes require explicit
   confirmation.
5. Ask for a focused branch, tests, documentation updates, and a review-ready
   summary with exact verification results.

For example:

```text
Implement INT-002 mapping for <resource>. Preserve pending-review provenance.
Read the INT plan and adjacent tests first. Do not change the remote database.
Add focused tests, update TASKS.md and the relevant design doc, then prepare a
single focused PR with the verification commands and results.
```

## Maintaining useful instructions

Keep `AGENTS.md` under roughly 200 lines and include only stable facts that
apply to most tasks: hard product boundaries, required safety behavior, task
routing, and delivery rules. Put detail where it belongs:

| Need | Location |
| --- | --- |
| Current priority, owner, and acceptance evidence | `.agent/TASKS.md` |
| Product thesis and clinical boundaries | `.agent/PROJECT.md` |
| Architecture and cross-cutting decisions | `.agent/ARCHITECTURE.md` |
| Code conventions | `.agent/CODING_STANDARDS.md` |
| Team branching and review process | `.agent/TEAM.md` |
| Database, Auth, RLS, and environment recreation | `docs/supabase_setup_guide.md` |
| Fixture and staging-demo rules | `docs/demo-environment.md`, `docs/synthetic-data-catalog.md` |
| FHIR/SMART import boundary | `.agent/specs/int-002-003-interoperability-plan.md` |

Keep personal workflow preferences out of the repository. Use each product's
local, ignored settings mechanism for those instead.

## Review the workflow itself

Review these instructions when a repeated correction, a review finding, a
security incident, or a new mandatory delivery step exposes missing context.
Prefer a specific, testable instruction over a broad request to “be careful.”
Remove stale or conflicting rules rather than accumulating them.

The approach follows the current project-instruction patterns documented by
[Claude Code](https://code.claude.com/docs/en/memory),
[Cursor](https://cursor.com/docs/context/rules), and
[OpenAI](https://developers.openai.com/api/docs/guides/latest-model): maintain
concise shared instructions, scope detailed rules to the work that needs them,
and avoid repeating prompt material.
