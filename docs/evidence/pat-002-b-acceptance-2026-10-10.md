# PAT-002-B local checkpoint evidence: October 10, 2026

Scope: B1 source audit and B2 safety-first chat/independent alerts. Owner: Tushar.
Branch: `feature/confirmed-symptom-intake`, based on local `main`/`origin/main`
`657602d28c8e8b6f954dee59203c7d25a7884225`. B2 is implemented locally;
peer/safety approval, merge and deployed acceptance are not claimed.

The authoritative contract, inventory, learning explanation and exact source
walkthrough are in [plan section 17](../../.agent/specs/pat-002-b-confirmed-symptom-intake-plan.md#17-b1--source-audit-and-interface-contract-october-10-2026)
and the [B2 demonstration](../../.agent/specs/pat-002-b-confirmed-symptom-intake-plan.md#18-b2--safety-takes-priority-october-10-2026).
TASKS.md remains the sole task tracker. This file records observed evidence.

## B1 verification

From `backend`:

```sh
PYTHONPATH=src .venv/bin/pytest tests/unit/followup tests/unit/safety tests/unit/adk/test_safety_floor_plugin.py tests/unit/services/test_chat_service.py tests/integration/routers/test_chat_emergency_copy.py tests/integration/routers/test_chat_websocket_stability.py --no-cov
```

Result: **304 passed, 31 warnings in 0.59s**, exit 0, Python 3.12.12.
Warnings concern existing Starlette/httpx and ADK deprecations. Provider calls,
database access and notification writes are stubbed by these tests. Passing
reviewed emergency-copy regressions does not establish that the router skips
retrieval/extraction, or that an alert has durable retry; source inspection found
those gaps. This run verifies existing behavior, not the proposed confirmation
boundary. No live paid model probe or remote database operation was run.

From the repository root:

```sh
backend/.venv/bin/python --version
node --version
npm --version
backend/.venv/bin/python -c 'from importlib.metadata import version; print("\n".join(f"{name}=={version(name)}" for name in ["fastapi", "pydantic", "supabase", "google-adk", "pytest", "ruff", "mypy", "pglast", "acquit"]))'
backend/.venv/bin/python -m pip check
git diff --check
```

Observed: Python 3.12.12; Node 22.17.1; npm 11.7.0. Inspected installed backend
versions match FastAPI 0.141.1, Pydantic 2.13.4, Supabase 2.31.0, ADK 2.9.1,
pytest 9.1.1, Ruff 0.9.10, mypy 1.15.0 and pglast 8.4. Installed `acquit` 0.2.0
differs from locked 0.3.0; this is not a reproducible full-lock installation claim.
`pip check` returned “No broken requirements found,” exit 0, with a sandbox cache
permission warning. No dependencies or locks were changed. `git diff --check`
passed, exit 0.

Read-only PR coordination check:

```sh
gh pr view 136 --json number,state,mergeable,headRefOid,headRefName
```

The initial sandbox network call failed; the permitted read-only retry succeeded.
Result: OPEN; head `b0532e846116cff956f138c3dc64f8d5f3c223d9`;
branch `feature/adr-patient-information-loop`; mergeability UNKNOWN. No author
contact, review, integration, cherry-pick or change to that PR is claimed.

Manual verification performed: inspected the saved-message UUID, missing session
binding, immediate report INSERT/ADR handoff, ordinary-chat clinician visibility,
source migration policies/grants, report consumers and numeric severity assumptions.
This was a source walkthrough, not an authenticated browser journey.

Ruff/mypy, portal lint/typecheck/tests/build, migration validation, full backend
pytest and disposable SQL were not run for this documentation-only checkpoint.
At B1, no source, schema, dependency or UI behavior changed; those checks become
required with their owning feature slices. No SQL permission/concurrency pass
was claimed at B1. B2 evidence follows.

## B2 verification

All evidence is local and synthetic. No live provider probe or authenticated
browser acceptance was performed. No question library/approval was created.

From `backend`, final focused and full runs:

```sh
PYTHONPATH=src .venv/bin/pytest tests/unit/followup tests/unit/safety tests/unit/adk/test_safety_floor_plugin.py tests/unit/services/test_chat_service.py tests/unit/services/test_chat_safety_service.py tests/unit/services/test_a2a_retry_worker_backoff.py tests/integration/routers/test_chat_emergency_copy.py tests/integration/routers/test_chat_websocket_stability.py --no-cov -q
PYTHONPATH=src .venv/bin/pytest tests/integration/routers/test_chat_emergency_copy.py --no-cov -q
PYTHONPATH=src .venv/bin/pytest tests/ -q
```

Results: **327 passed, 51 warnings in 0.43s**; the follow-along router command
alone gave **25 passed, 51 warnings in 0.19s**. Full backend: **2,074 passed,
137 skipped, 162 warnings in 20.33s**, coverage **86.53%** against the required
80%, exit 0. Skips are not passing evidence; the default run skips the eight
opt-in SQL checks. Warnings include existing dependency/ADK/Starlette deprecations.

Focused checks assert reviewed bilingual medical/self-harm responses, precedence,
existing negation/history behavior, document-catalog bypass, zero ordinary
retrieval/model/extraction/report/ADR calls for matched emergencies, failures
without false saved/sent claims, socket liveness and recording despite streaming
disconnect. Router persistence is mocked; SQL tests exercise actual transactions.

Disposable real PostgreSQL:

```sh
CHAT_SAFETY_TEST_POSTGRES=1 CHAT_SAFETY_TEST_POSTGRES_DOCKER=1 PYTHONPATH=src .venv/bin/pytest tests/integration/test_chat_safety_postgres.py --no-cov -q
```

Final result: **8 passed, 3 warnings in 8.94s**, exit 0. Checks cover atomic
record rollback, stable identity/conflict rejection, immutable safety/source rows,
dispatch failure retention/atomic retry, browser role denial, current assignment/
no-recipient outcome, duplicate dispatch and concurrent recording/delivery.
The fixture loads migrations 001, 002, 006, 007 and 049 with minimal local auth/
role/private-schema stubs. This is not full-chain or effective remote Supabase
policy evidence. SQL response fixtures are test-only, not approved clinical copy.

The first native attempt produced eight setup errors: installed `initdb` from
libpq 18.6 lacked its matching `postgres` server binary. Docker Desktop was started
locally; tests used cached official `postgres:16-alpine` with `--pull=never`,
`--network=none`, no exposed ports and no mounted data. Fixtures removed their own
test containers. Docker Desktop remains running. No image was fetched and no
configured database URL was read by this test.

Owning backend static checks:

```sh
.venv/bin/ruff check src/ scripts/ tests/unit/safety/test_intake_gate.py tests/unit/services/test_chat_safety_service.py tests/integration/test_chat_safety_postgres.py tests/integration/routers/test_chat_emergency_copy.py
.venv/bin/ruff format --check src/ scripts/ tests/unit/safety/test_intake_gate.py tests/unit/services/test_chat_safety_service.py tests/integration/test_chat_safety_postgres.py tests/integration/routers/test_chat_emergency_copy.py
.venv/bin/mypy src/ --ignore-missing-imports
.venv/bin/python scripts/validate_migrations.py
.venv/bin/python scripts/check_production_placeholders.py
```

All passed: **237 files already formatted**, mypy **216 source files**,
**58 migrations validated**, no production placeholders. Migration 049 SHA-256:
`b5c4d5083edf703e3605e89202b6d06666b326942f582e84a7a65792814f15d8`.

Broader `.venv/bin/ruff check src/ tests/` failed on five findings in unchanged
tests: `test_cron_api.py` (UP017), `test_security.py` (two SIM117),
`test_supabase_execute.py` (SIM117) and `test_drug_knowledge_service.py` (I001).
`.venv/bin/ruff format --check tests/` reports 12 unchanged files:
`test_auth_api.py`, `test_chat_voice_api.py`, `test_cron_api.py`,
`test_reminders_api.py`, `test_golden_set.py`, `test_ingestion_graph.py`,
`test_nvidia_nim_client.py`, `test_supabase_execute.py`,
`document_intelligence/test_pipeline.py`, `test_clinical_action_service.py`,
`test_provider_comparison.py` and `test_staff_service.py`. None were edited;
repository-wide lint/format gates are not claimed green.

From `apps/patient-portal`:

```sh
npm run lint
./node_modules/.bin/next typegen
npm run typecheck
npm run test -- src/__tests__/chat-page.test.tsx src/__tests__/chat-api.test.ts
npm run test
npm run build
npm run build -- --webpack
```

Lint and typecheck passed. Focused: **30 passed across 2 files in 2.56s**.
Full tests: **378 passed across 45 files in 22.81s**. Node emits a localStorage
experimental warning. Initial typecheck found stale generated route files.
`next typegen` alone retained `.next/types/app/symptoms/page.ts`, so generated
`.next/types` was moved to `/tmp/pat-b2-next-types-qytc45ky/types` before
regeneration. Typecheck then passed without a source workaround.

Default Turbopack production build and its outside-sandbox retry both failed at
temporary port binding (`Operation not permitted`). A documented local Webpack
build fallback **passed**, exit 0, producing all 12 route entries including
`/chat` and `/symptoms`. Default Turbopack is not claimed passing. Neither build
deploys. The completed Webpack build's generated types were followed by another
successful `npm run typecheck`.

Installed frontend: Next **16.3.4** (lock/manifest **16.3.6**), React **19.2.3**,
Vitest **4.1.11**, TypeScript **5.9.3**. Existing installed `acquit` **0.2.0**
versus locked **0.3.0** drift remains. Dependencies/locks were unchanged; these
checks are not a reproducible clean-lock installation claim. Required CI/review
must use a clean lock installation. Sentry reports an existing deprecated config
option; no external configuration was changed.

Exact demonstration commands and the conditional manual browser journey are in
[plan section 18](../../.agent/specs/pat-002-b-confirmed-symptom-intake-plan.md#18-b2--safety-takes-priority-october-10-2026).
No claim is made that the new code runs in the currently configured shared
environment. Persisted delivery does not imply clinician read/acknowledgment.

## Remaining prerequisites

- B3–B6: approved-library machinery, owned private-draft
  SQL/service/API and Nora start/answer/correct/cancel UI with paired-locale tests.
- B7–B11: bounded preview, atomic confirmation, confirmed-only clinical consumers,
  recovery matrix and integrated verification. B1–B6 alone is not full B delivery.
- Genuine question-bundle approval through the designated safety/clinical review
  process; synthetic approval fixtures cannot activate live intake.
- Disposable PostgreSQL private-draft role, ownership, revision, dedupe and race evidence;
  complete nullable-severity compatibility before confirmed reports are produced.
- B2 migration 049 in an explicitly authorized compatible synthetic target with
  the retry worker enabled; verify actual Supabase roles, RPC grants and alerts.
- Ganesh overlap/safety review, peer review, required CI and a separately authorized
  migration/backend/portal rollout with mixed-version writers drained.

PAT-002-C and #136's ADR follow-up implementation remain outside scope. No remote
migration, reset, seed, deployment, merge or external configuration was performed.

Next checkpoint: B3. The plan requires the requester to advance after the B2
walkthrough; no later slice work has begun.
