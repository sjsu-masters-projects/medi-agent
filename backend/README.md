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

## Database Migrations

Migrations are plain SQL files in `src/app/db/migrations/`. The repository currently has
`001`–`039`, including provenance, SMART/FHIR review, authorization audit, model telemetry,
document-ingestion worker controls, private TIFF previews, and the independent patient-explanation
retry lifecycle. The migration ledger records full filenames and checksums, including the two
distinct `011` files; do not maintain a second migration inventory here.

Full setup guide: **[docs/supabase_setup_guide.md](../docs/supabase_setup_guide.md)**

Validate migration naming, sequence continuity, and PostgreSQL syntax before applying a change:

```bash
python scripts/validate_migrations.py
```

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
