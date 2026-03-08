# MediAgent Backend

> FastAPI backend for the MediAgent multi-agent healthcare platform.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
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

## Package Layout

```
src/app/
├── main.py           # App factory — creates FastAPI, mounts routers
├── config.py         # Env vars → typed Settings object
├── core/             # Exceptions, auth helpers, constants
├── models/           # Pydantic schemas (Create/Read/Update per entity)
├── routers/          # HTTP endpoints — thin, delegate to services
├── services/         # Business logic — no FastAPI imports, testable
├── agents/           # LangGraph agents (base + 7 domain agents)
├── tools/            # Standalone tools agents can call
├── mcp/              # MCP servers (external API wrappers)
├── a2a/              # Agent-to-Agent protocol
├── clients/          # SDK wrappers (Gemini, Deepgram, etc.)
├── db/               # Queries, migrations, seed data
├── middleware/        # Request processing (auth, logging, etc.)
└── utils/            # Shared helpers
```

## Key Conventions

- **Routers are thin** — validate input, call service, return response
- **Services are pure** — no FastAPI imports, easy to unit test
- **Models use `Literal` types** — catches bad enum values at the API boundary
- **All IDs are `UUID`** — matches Supabase
- **Custom exceptions** — `core/exceptions.py`, not raw `HTTPException`

## Docs

| Doc | What it covers |
|-----|----------------|
| [PROJECT.md](../.agent/PROJECT.md) | Product context, decision log |
| [ARCHITECTURE.md](../.agent/ARCHITECTURE.md) | System design, data model, agent flow |
| [CODING_STANDARDS.md](../.agent/CODING_STANDARDS.md) | Code style rules |
| [workflows/new-agent.md](../.agent/workflows/new-agent.md) | How to add a new agent |
