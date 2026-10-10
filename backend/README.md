# MediAgent Backend

> FastAPI backend for the MediAgent multi-agent healthcare platform.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

`requirements.in` and `requirements-dev.in` contain direct dependency intent;
the corresponding `.txt` files are exact, generated locks used by CI and
Docker. After changing an `.in` file, refresh both locks with the pinned CI
resolver:

```bash
uv pip compile requirements.in --universal --python-version 3.12 --output-file requirements.txt
uv pip compile requirements-dev.in --universal --python-version 3.12 --output-file requirements-dev.txt
```

Security floors also cover [multidict's items-view reference leak](https://github.com/aio-libs/multidict/security/advisories/GHSA-54p9-h82j-f925)
(`>=6.9.1`) and [LangGraph SDK resource authorization](https://github.com/langchain-ai/langgraph/security/advisories/GHSA-fvww-7h3r-vfhp)
(`>=0.4.4`). Both locks retain these patched versions. Run the CI audit with Python
3.12; system Python 3.14 cannot resolve all packages in this lock.

## Run

```bash
PYTHONPATH=src uvicorn app.main:app --reload
# API docs → http://localhost:8000/docs
```

## Lint & Test

```bash
ruff check src/                        # lint
ruff format --check src/               # format check
mypy src/ --ignore-missing-imports     # type check
PYTHONPATH=src pytest tests/ -v        # test
```

### Testing & Coverage

```bash
# Run all tests with terminal coverage summary (default in pyproject)
python -m pytest tests/ --cov=app --cov-report=term-missing

# Run specific test file
python -m pytest tests/unit/services/test_dailymed_service.py -v

# Run tests without coverage (faster for development)
python -m pytest tests/ --no-cov

# Generate HTML coverage report in a single fixed folder (backend/htmlcov)
./scripts/generate_html_coverage.sh

# View coverage report
open backend/htmlcov/index.html
```

**Coverage Requirements:**
- Minimum: 80% (enforced in CI/CD)
- Current: 89.62%
- All external APIs must be mocked in tests

See [tests/TESTING_GUIDE.md](tests/TESTING_GUIDE.md) for comprehensive testing documentation.

## Care-plan model preflight

Before deploying a change to care-plan classification or its provider route, validate the
exact worker contract against synthetic facts:

```bash
cd backend
PYTHONPATH=src .venv/bin/python scripts/preflight_care_plan_classification.py --dry-run
PYTHONPATH=src .venv/bin/python scripts/preflight_care_plan_classification.py
```

Run the live command locally with the normal backend configuration loaded (the
app settings import requires Supabase variables), Vertex credentials,
`GOOGLE_PROJECT_ID`, `GEMINI_VERTEX_AI_LOCATION=global`, and the configured
`GEMINI_FLASH_MODEL`. It classifies 12 fictional facts through the production
route and prints only counts and safe failure categories. It never reads the
database, prints model output, or publishes a plan. This credentialed model call
is an operator-run local check, not a CI or deployment gate. Deterministic
contract tests run in PR CI without cloud
credentials. Record the local preflight result with the PR verification evidence.

## Model capacity preflight

After offline tests, an operator may run this small paid, synthetic-only check:

```bash
VERTEX_AI_LOCATION=global GEMINI_VERTEX_AI_LOCATION=global PYTHONPATH=src \
  .venv/bin/python scripts/preflight_model_capacity.py --include-oss
```

Omit `--include-oss` to check only the current triage primary. The probe reports
per-attempt safe metadata, first-attempt success, retry recovery, fallback count,
total latency and synthetic answers for manual English/Spanish review. It does
not read/write the database, change routes or deploy. JSON/urgency checks must
pass independently of HTTP success. Four cases per primary cannot establish
clinical quality or availability under load. Offline tests simulate 429s;
live checks do not deliberately overload providers. Per-process concurrency
limits do not coordinate across Cloud Run replicas or Jobs.

## Package Layout

```
src/app/
├── main.py           # App factory — creates FastAPI, mounts routers
├── config.py         # Env vars → typed Settings object
├── core/             # Exceptions, auth helpers, constants
├── models/           # Pydantic schemas (Create/Read/Update per entity)
├── routers/          # HTTP endpoints — thin, delegate to services
├── services/         # Business logic — no FastAPI imports, testable
├── adk/              # Current agent runtime, registry, and safety plugins
├── agents/           # Legacy compatibility paths; no new product work
├── tools/            # Standalone tools agents can call
├── mcp/              # In-process adapters; not a published MCP endpoint
├── a2a/              # Internal delegated-task lifecycle; not an external A2A service
├── clients/          # SDK wrappers (Gemini, Deepgram, etc.)
├── db/               # Supabase connection helpers, repositories, migrations, seed data
│   └── migrations/   # SQL files — run in order (001_, 002_, ...)
├── middleware/        # Shared middleware helpers such as endpoint rate limiting
└── utils/            # Shared helpers
```

## Appointment calendar export

`GET /api/v1/appointments/{id}/calendar?locale=en-US` (or `es-MX`) returns
`{ filename, content }` as authenticated JSON with `Cache-Control: private, no-store`.
Portals turn this into a local `text/calendar` download without placing tokens in
URLs. The service checks the owning patient or an actively assigned clinician and
fresh `confirmed`/`scheduled` status on every request. Other statuses return
`APPOINTMENT_UNAVAILABLE` (422); unauthorized users cannot export.

The RFC 5545 serializer uses UTC start/end instants, elapsed duration, a stable event
UID, localized generic title/one-time-copy notice, and safely escaped/folded location
text. It omits clinical reasons, notes, and attendee/invitation fields. No state
mutation, external calendar call, or migration is needed for this endpoint.

## Human care-team conversations

Authenticated `/api/v1/care-conversations` routes implement explicitly addressed
patient/linked-clinician threads, separately from Nora and operational alerts.
Apply `048_care_team_conversations.sql` only with environment-specific approval
before deploying the API and portals. No legacy notification is converted into
a human message. Existing assignment and current clinic authorization are checked
inside the same transaction as each read, send and audit operation.

Threads are unique to `(care_team_id, patient_id, clinician_id, clinic_id)`.
Reassigning a pair or clinic permits a fresh thread for the current binding;
historical threads, messages and audit remain stored but are inaccessible while
their binding differs from the active assignment. Inbox presentation uses latest
message time descending (NULL last), then conversation ID, independently of the
UUID-ordered assignment locks.

Message retries reuse a sender-scoped UUID key; a changed body or thread rejects
reuse. Pagination uses `(created_at, id)`, and read markers advance only through
the specified message. Browser database grants are intentionally absent; callers
use the API. Message bodies must not be logged. See
`../.agent/specs/com-001-two-way-conversations.md` for the full contract and rollout
boundary. This is not authorization for real-PHI use or a clinical-readiness claim.

Run the isolated database contract suite with synthetic CI settings and an
already available official `postgres:16` image:

```sh
CARE_CONVERSATION_TEST_POSTGRES_DOCKER=1 PYTHONPATH=src \
  .venv/bin/pytest tests/integration/test_care_conversation_postgres.py --no-cov -q
```

The disposable container has no network, published ports or host volumes and
is removed after the tests. The suite loads actual migrations 001, 002, 006, 007,
the private-helper bootstrap of 020, and full 022/048. This exercises real enum
types, profile/assignment RLS, pending-invite columns and service-role grants.
Auth is a minimal platform stub; unrelated storage/vector/Auth-hook portions of
020 and the remaining migration chain are not rehearsed. These tests do not prove
deployment, PostgREST integration or live acceptance.

Before a separately authorized rollout, run this read-only, count-only preflight
in the chosen environment. It prints no patient, clinician or assignment IDs:

```sql
SELECT count(*) AS active_assignments,
       count(*) FILTER (WHERE c.clinic_id IS NULL) AS active_assignments_without_clinic,
       count(*) FILTER (WHERE t.patient_id IS NULL) AS active_assignments_without_patient
FROM public.care_teams t
JOIN public.clinicians c ON c.id = t.clinician_id
WHERE t.status = 'active';
```

Review nonzero missing-binding counts before rollout. The conversation API
fails closed for those assignments; this preflight does not repair, backfill or
authorize changing them.

## Database Migrations

Migrations are plain SQL files in `src/app/db/migrations/`. The repository currently has
`001`–`045`, including provenance, SMART/FHIR review, authorization audit, model telemetry,
document-ingestion worker controls, private TIFF previews, the independent patient-explanation
retry lifecycle, and the clinician-approved care-plan lifecycle with its one-time historical
document-fact request backfill and care-plan publication review guards. The migration ledger records full filenames and checksums,
including the two distinct `011` files; do not maintain a second migration inventory here.

Scheduling Slice 5 requires `042_appointment_expired_status.sql` to commit before
`043_appointment_booking_guards.sql`. Run the read-only
`scripts/appointment-booking-preflight.sql` first and review any existing overlap
pairs. The migration does not repair them automatically. Apply schema before
activating the new appointment service. It enforces patient booking overlaps and
expires proposals on authorized reads/responses, with atomic audit events.

Full setup guide: **[docs/supabase_setup_guide.md](../docs/supabase_setup_guide.md)**

Validate migration naming, sequence continuity, and PostgreSQL syntax before applying a change:

```bash
python scripts/validate_migrations.py
```

Before deploying the incomplete-evidence care-plan contract, apply migration
`043_incomplete_care_plan_drafts.sql` using the repository migration procedure.
Drafts may retain missing instructions/frequency as review blockers; approval still
requires complete active items and completed generation. Run the deterministic local
PostgreSQL check with `initdb`, `pg_ctl`, and `psql` installed:

```bash
CARE_PLAN_TEST_POSTGRES=1 PYTHONPATH=src .venv/bin/pytest tests/integration/test_care_plan_postgres.py --no-cov
```

This starts and stops disposable local clusters, never uses the configured remote
database or cloud credentials, and remains opt-in rather than a live CI preflight.

## DailyMed Medication RAG Ingestion

Run migration `015_drug_knowledge_rag.sql` before ingesting labels. The migration creates
`drug_knowledge_chunks`, indexes, RLS, and the `match_drug_knowledge_chunks` RPC.

Dry-run the first curated set:

```bash
cd backend
PYTHONPATH=src .venv/bin/python scripts/ingest_dailymed_rag.py --default-curated --dry-run
```

Ingest into the configured Supabase project:

```bash
cd backend
PYTHONPATH=src .venv/bin/python scripts/ingest_dailymed_rag.py --default-curated
```

For repeatable production ingestion, pin reviewed DailyMed SET IDs:

```bash
PYTHONPATH=src .venv/bin/python scripts/ingest_dailymed_rag.py \
  --label metformin=<SETID> \
  --label lisinopril=<SETID>
```

The script uses the service-role Supabase client and requires `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, and Google embedding configuration.

## Key Conventions

- **Routers are thin** — validate input, call service, return response
- **Services are pure** — no FastAPI imports, easy to unit test
- **Models use `StrEnum`** — catches bad values at the API boundary, serializes to plain strings
- **All IDs are `UUID`** — matches Supabase
- **Custom exceptions** — `core/exceptions.py`, not raw `HTTPException`

## Docs

| Doc | What it covers |
|-----|----------------|
| [PROJECT.md](../.agent/PROJECT.md) | Product context, decision log |
| [ARCHITECTURE.md](../.agent/ARCHITECTURE.md) | System design, data model, agent flow |
| [CODING_STANDARDS.md](../.agent/CODING_STANDARDS.md) | Code style rules |
| [Supabase Setup Guide](../docs/supabase_setup_guide.md) | DB schema, migrations, RLS, auth hooks |
| [workflows/new-agent.md](../.agent/workflows/new-agent.md) | How to add a new agent |
