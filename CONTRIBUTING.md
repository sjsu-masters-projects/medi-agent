# Contributing to MediAgent

Start with a task, its requirements and a reproducible acceptance path. Keep
clinical approval, source provenance and access controls intact.

## Before making a change

1. Inspect the branch and working tree. Preserve unrelated work.
2. Read the [contributor contract](AGENTS.md), [task board](.agent/TASKS.md) and
   the feature doc for the selected task's area.
3. Check [product scope](.agent/PROJECT.md), [architecture](.agent/ARCHITECTURE.md),
   [coding standards](.agent/CODING_STANDARDS.md) and [team responsibilities](.agent/TEAM.md).
4. State the user outcome, acceptance checks and decisions still needed.
5. Branch from current main. Keep one coherent change per pull request unless
   the requester explicitly groups related work.

For UI work, read the [design system](.agent/DESIGN_SYSTEM.md). For imported
records, read [clinical provenance](docs/clinical-facts-provenance.md).

## Set up development

The [README quick start](README.md#run-locally) covers installation and the three
local services. [Local development](docs/development.md) covers configuration,
integration prerequisites and troubleshooting. Variable definitions belong in the
committed environment templates, not another table here.

After filling local configuration, optional setup checks are:

```bash
./scripts/preflight.sh
./scripts/check-env.sh
```

These scripts inspect local configuration. Run them privately and review their
output for sensitive information before sharing it.

## Verify the surfaces you change

Run commands from the directories shown. Use locked dependency files.

### Backend

```bash
cd backend
.venv/bin/ruff check src/
.venv/bin/ruff format --check src/
.venv/bin/mypy src/ --ignore-missing-imports
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
```

Focused tests are useful during implementation. Before review, run the required
broader checks for the affected workflow and record exact commands and outcomes.
Skipped or mocked database tests do not establish actual permissions.

### Patient or clinician portal

```bash
cd apps/patient-portal
# Use apps/clinician-portal for clinician changes.
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

Review loading, empty, error, retry and keyboard states, long Spanish text and
relevant mobile or desktop widths. Physical microphone and device checks remain
separate from mocked voice tests.

### Database changes

```bash
cd backend
.venv/bin/python scripts/validate_migrations.py
```

Run the affected real PostgreSQL contracts using the opt-in variables documented
in [backend testing](backend/README.md). Hosted migrations need authorization for
the exact target and files. The [migration guide](docs/supabase_setup_guide.md)
owns the apply procedure.

The ledger script applies pending files in order, records checksums and stops on
a mismatch. Never edit an applied migration or bypass its receipt. Apply required
schema changes before merging dependent code when automatic deployment would
otherwise race the migration.

### Documentation

Follow [documentation maintenance](docs/maintaining-docs.md). Check relative
links, heading anchors, code-block balance and Mermaid syntax after moving files.
Keep historical evidence attributable. Cleanup must not turn an unverified flow
into Done.

## Implementation rules

- Keep routers thin. Put business rules in services and validate at boundaries.
- Reuse shared contracts and existing authorization paths.
- Imported facts remain candidates until the established review approves them.
- Do not log patient text, credentials or service-role keys.
- Hosted SQL, deployment, destructive actions and external configuration need
  explicitly scoped authorization. Permission to code is not permission to deploy.
- Put model-backed work in the existing registry and safety path. Follow the
  [workload guide](.agent/workflows/new-agent.md), not a parallel runtime.

## Pull requests

Use the [pull-request template](.github/pull_request_template.md) and conventional
commit messages such as `fix: preserve appointment timezone` or
`docs: simplify local setup`.

Include the user-facing change, task IDs, risks, migration/configuration needs,
verification results and manual acceptance steps. Name what remains unverified.
Keep checklist wording intact where CI checks it literally.

Required checks and peer review must pass before merge. Safety-sensitive changes
also need the applicable safety review. Do not merge or deploy without authorization.

## Update the right document

| Change | Update |
| --- | --- |
| Status, owner, remaining work | [Task board](.agent/TASKS.md) |
| Feature behavior and rules | [Feature doc](docs/features/) for that area |
| Requirements for work not yet built | Temporary specification under `.agent/specs/` ([rules](docs/maintaining-docs.md#retire-or-move-a-document)) |
| Cross-cutting design | [Architecture](.agent/ARCHITECTURE.md) or the feature doc |
| Commands and recovery procedures | Relevant operating guide under `docs/` |
| Test results, screenshots and observations | Linked report under [evidence](docs/evidence/README.md) |
| Setup or navigation | [README](README.md), [documentation index](docs/README.md) or app README |

A specification is temporary: when its feature ships, move the rules worth keeping into
the feature doc and delete it. See [retiring a document](docs/maintaining-docs.md#retire-or-move-a-document).
