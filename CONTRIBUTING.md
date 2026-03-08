# Contributing to MediAgent

> Developer guide — how to set up, develop, test, and submit code.

---

## Before You Start

Read these docs (in order):

1. **[PROJECT.md](.agent/PROJECT.md)** — what MediAgent is, decision log
2. **[ARCHITECTURE.md](.agent/ARCHITECTURE.md)** — system design, data model
3. **[CODING_STANDARDS.md](.agent/CODING_STANDARDS.md)** — how we write code
4. **[DESIGN_SYSTEM.md](.agent/DESIGN_SYSTEM.md)** — UI guidelines (if doing frontend)
5. **[TEAM.md](.agent/TEAM.md)** — sprints, Git workflow, PR process

---

## Development Setup

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # includes production + test/lint deps
```

Verify it works:
```bash
PYTHONPATH=src uvicorn app.main:app --reload
# open http://localhost:8000/docs
```

### Frontend (either portal)

```bash
cd apps/patient-portal   # or apps/clinician-portal
npm install
npm run dev
```

### Environment Variables

Copy `.env.example` → `.env` and fill in your keys. Never commit `.env`.

| Variable | Where to get it |
|----------|-----------------|
| `SUPABASE_URL` | Supabase dashboard → Settings → API |
| `SUPABASE_ANON_KEY` | Same place |
| `GOOGLE_API_KEY` | Google AI Studio |
| `DEEPGRAM_API_KEY` | Deepgram console |
| `RESEND_API_KEY` | Resend dashboard |

---

## Development Workflow

We follow a structured workflow. See [TEAM.md](.agent/TEAM.md) for full details.

### Starting a New Feature

Follow **[.agent/workflows/new-feature.md](.agent/workflows/new-feature.md)**. The short version:

1. Pick a task from [TASKS.md](.agent/TASKS.md)
2. Create a branch: `feature/short-description`
3. Read the relevant project docs before coding
4. Write code following [CODING_STANDARDS.md](.agent/CODING_STANDARDS.md)
5. Write tests
6. Run linters (see below)
7. Open a PR

### Adding a New AI Agent

Follow **[.agent/workflows/new-agent.md](.agent/workflows/new-agent.md)**. Each agent gets its own sub-package under `backend/src/app/agents/` with:
- `agent.py` — the agent class (extends `BaseAgent`)
- `graph.py` — the LangGraph state graph
- `prompts.py` — system/user prompt templates

### Git Branch Naming

| Type | Format | Example |
|------|--------|---------|
| Feature | `feature/description` | `feature/document-parsing` |
| Bugfix | `fix/description` | `fix/login-redirect` |
| Hotfix | `hotfix/description` | `hotfix/prod-crash` |

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add document upload endpoint
fix: handle empty medication list
docs: update API examples in README
test: add adherence scoring unit tests
refactor: extract PDF parsing into tool
```

---

## Running Linters & Tests

### Backend

```bash
cd backend
source .venv/bin/activate

# Lint
ruff check src/
ruff format --check src/

# Type check
mypy src/ --ignore-missing-imports

# Test
PYTHONPATH=src pytest tests/ -v

# All at once
ruff check src/ && ruff format --check src/ && mypy src/ --ignore-missing-imports && PYTHONPATH=src pytest tests/ -v
```

### Frontend

```bash
cd apps/patient-portal   # or apps/clinician-portal

# Lint
npm run lint

# Build (catches type errors)
npm run build

# Test (when tests are added)
npm run test
```

---

## Project Architecture (Quick Reference)

```
Request → Router → Service → DB / Agent → Response
```

- **Routers** are thin — validate input, call services, return responses
- **Services** hold all business logic — no FastAPI imports, easy to test
- **Agents** are LangGraph state machines that use tools and LLMs
- **Models** are Pydantic schemas — separate Create/Read/Update per entity
- **Tools** are standalone functions agents can call (RxNorm, Naranjo, etc.)

### Key Design Decisions

| Decision | Why |
|----------|-----|
| `src/app/` layout | Production packaging — avoids import conflicts |
| Pydantic `Literal` types | Catches invalid enum values at the API boundary |
| `UUID` for all IDs | Matches Supabase's default primary keys |
| `BaseAgent` ABC | SOLID — all agents are interchangeable |
| Separate `services/` from `routers/` | Testable business logic without spinning up FastAPI |
| Separate `tools/` from `agents/` | Tools are reusable across multiple agents |

---

## Backend Package Map

| Package | Purpose | Example |
|---------|---------|---------|
| `core/` | Exceptions, auth, constants | `NotFoundError`, `get_current_user` |
| `models/` | Pydantic schemas | `PatientCreate`, `MedicationRead` |
| `routers/` | HTTP endpoints | `POST /api/v1/documents/upload` |
| `services/` | Business logic | `DocumentService.explain()` |
| `agents/` | LangGraph agents | `IngestionAgent`, `TriageAgent` |
| `tools/` | Agent tools | `naranjo.score()`, `rxnorm.lookup()` |
| `mcp/` | MCP servers | External API wrappers for agents |
| `a2a/` | Agent-to-Agent protocol | Agent cards, task routing |
| `clients/` | SDK wrappers | `GeminiClient`, `DeepgramClient` |
| `db/` | Database layer | Queries, migrations, seed data |
| `middleware/` | Request processing | Auth, CORS, rate limiting, logging |

---

## Frontend Quick Reference

Both portals use the same stack and structure:

| Layer | Tech | Location |
|-------|------|----------|
| Pages | Next.js App Router | `src/app/` |
| State | Redux Toolkit | `src/store/` |
| API | Fetch wrapper | `src/services/api.ts` |
| Types | TypeScript | `src/types/` |
| Components | React + Tailwind | `src/components/` |
| Shared code | `@mediagent/shared` | `packages/shared/src/` |

### Patient Portal Routes

| Route Group | Pages |
|-------------|-------|
| `(auth)/` | login, signup, onboarding |
| `(dashboard)/` | today (feed), records, chat, settings |

### Clinician Portal Routes

| Route Group | Pages |
|-------------|-------|
| `(auth)/` | login, setup |
| `(dashboard)/` | Risk Radar, patients/[id], medwatch, messages, settings |

---

## Code Review Checklist

Before opening a PR, run through **[.agent/workflows/ai-code-review.md](.agent/workflows/ai-code-review.md)**:

- [ ] Follows [CODING_STANDARDS.md](.agent/CODING_STANDARDS.md)
- [ ] No hardcoded secrets or API keys
- [ ] Pydantic models have proper field validation
- [ ] Services don't import from FastAPI
- [ ] Error handling uses custom exceptions from `core/exceptions.py`
- [ ] Frontend follows [DESIGN_SYSTEM.md](.agent/DESIGN_SYSTEM.md)
- [ ] Tests exist for new business logic
- [ ] Linter and type checker pass

---

## Questions?

Check the docs first:
- Architecture question → [ARCHITECTURE.md](.agent/ARCHITECTURE.md)
- "How should I structure this?" → [CODING_STANDARDS.md](.agent/CODING_STANDARDS.md)
- "What's the task priority?" → [TASKS.md](.agent/TASKS.md)
- "How does the team work?" → [TEAM.md](.agent/TEAM.md)

If it's not in the docs, ask the team.
