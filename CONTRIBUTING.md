# Contributing to MediAgent

Developer guide for setup, architecture orientation, verification, and pull requests. This file is the **onboarding entry**; deeper product and design decisions live under `.agent/`.

---

## Read first

Before writing code, read in this order:

1. [PROJECT.md](.agent/PROJECT.md) — product context and decisions  
2. [ARCHITECTURE.md](.agent/ARCHITECTURE.md) — system design and data model  
3. [CODING_STANDARDS.md](.agent/CODING_STANDARDS.md) — how we write code  
4. [TASKS.md](.agent/TASKS.md) — phase status and backlog  
5. [TEAM.md](.agent/TEAM.md) — Git workflow and PR norms  

For UI work, also use [DESIGN_SYSTEM.md](.agent/DESIGN_SYSTEM.md).

---

## Local setup

### Environment files

```bash
cp .env.example .env
cp apps/patient-portal/.env.example apps/patient-portal/.env.local
cp apps/clinician-portal/.env.example apps/clinician-portal/.env.local
```

Fill values from your team’s secret store or team lead. **Never commit** `.env` or `.env.local`.

Validate:

```bash
./scripts/preflight.sh
./scripts/check-env.sh
```

### Environment variables (reference)

| Variable | Purpose |
|----------|---------|
| `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET` | Supabase DB, Auth, RLS |
| `GOOGLE_API_KEY` | Gemini / AI Studio paths |
| `GOOGLE_PROJECT_ID` | Vertex AI when using project-backed models |
| `VERTEX_AI_*` | MedGemma / Vertex endpoints |
| `DEEPGRAM_API_KEY` | Voice STT/TTS |
| `RESEND_API_KEY` | Transactional email (clinician invites; extend for other mail later) |
| `RESEND_CLINICIAN_ONBOARDING_FROM_EMAIL` | From address for clinician invite mail (use a verified-domain sender in production) |
| `RESEND_FROM_EMAIL` | Optional fallback “From” when the clinician onboarding sender is unset (see `config.py`) |
| `BACKEND_URL`, `PATIENT_PORTAL_URL`, `CLINICIAN_PORTAL_URL` | App URLs (email links, CORS) |
| `*_SENTRY_*` | Error monitoring (optional in dev) |

See root [`.env.example`](.env.example) and each app’s `.env.example` for the full list and comments.

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
PYTHONPATH=src uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs`.

### Frontend (either portal)

```bash
cd apps/patient-portal   # or apps/clinician-portal
npm ci
npm run dev
```

Clinician app often uses port 3001: `npm run dev -- --port 3001`.

---

## Database setup

Full procedure, RLS, and Auth hooks: **[docs/supabase_setup_guide.md](docs/supabase_setup_guide.md)**.

SQL migrations live in `backend/src/app/db/migrations/`. Apply **in numeric/filename order** against your Supabase Postgres (or local DB). Example:

```bash
export DB_URL="postgresql://postgres:YOUR_PASSWORD@YOUR_HOST:5432/postgres"

psql "$DB_URL" -f backend/src/app/db/migrations/001_initial_schema.sql
psql "$DB_URL" -f backend/src/app/db/migrations/002_rls_policies.sql
psql "$DB_URL" -f backend/src/app/db/migrations/003_storage_and_auth.sql
psql "$DB_URL" -f backend/src/app/db/migrations/004_jwt_claims_hook.sql
psql "$DB_URL" -f backend/src/app/db/migrations/005_document_parse_tracking.sql
psql "$DB_URL" -f backend/src/app/db/migrations/006_care_team_invite_compat.sql
psql "$DB_URL" -f backend/src/app/db/migrations/007_clinic_identity_foundation.sql
psql "$DB_URL" -f backend/src/app/db/migrations/008_soap_notes.sql
psql "$DB_URL" -f backend/src/app/db/migrations/009_jwt_claims_hook_hardening.sql
psql "$DB_URL" -f backend/src/app/db/migrations/010_chat_state_and_a2a_tasks.sql
psql "$DB_URL" -f backend/src/app/db/migrations/011_enable_dashboard_realtime_publication.sql
psql "$DB_URL" -f backend/src/app/db/migrations/011_locale_contract_upgrade.sql
psql "$DB_URL" -f backend/src/app/db/migrations/012_document_review_queue.sql
psql "$DB_URL" -f backend/src/app/db/migrations/013_cron_scheduler_foundation.sql
psql "$DB_URL" -f backend/src/app/db/migrations/014_patient_timezones_and_reminder_schedules.sql
psql "$DB_URL" -f backend/src/app/db/migrations/015_drug_knowledge_rag.sql
psql "$DB_URL" -f backend/src/app/db/migrations/016_obligation_source_document.sql
```

After migrations, configure the JWT claims hook in Supabase Dashboard → Auth → Hooks per the setup guide.

Before applying a migration change, run the parser-backed validation from the backend virtual environment:

```bash
cd backend
python scripts/validate_migrations.py
```

---

## Development workflow

See [TEAM.md](.agent/TEAM.md) for sprint and review expectations.

### Starting a feature

1. Pick or create a task in [TASKS.md](.agent/TASKS.md) or a GitHub issue.  
2. Branch: `feature/short-description`, `fix/...`, or `hotfix/...`.  
3. Follow [.agent/workflows/new-feature.md](.agent/workflows/new-feature.md) for larger work.  
4. Implement per [CODING_STANDARDS.md](.agent/CODING_STANDARDS.md).  
5. Add or update tests.  
6. Run checks below.  
7. Open a PR using the repo template.

### Adding an AI agent

Follow [.agent/workflows/new-agent.md](.agent/workflows/new-agent.md). Typical layout under `backend/src/app/agents/<name>/`:

- `agent.py` — agent entry  
- `graph.py` — LangGraph workflow  
- `prompts.py` — prompt templates  

### Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add staff invite email
fix: handle empty medication list
docs: update CONTRIBUTING migration list
test: add staff service coverage
refactor: extract clinic lookup helper
```

### Branch naming

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feature/description` | `feature/feed-real-data` |
| Bugfix | `fix/description` | `fix/ws-disconnect` |
| Hotfix | `hotfix/description` | `hotfix/prod-auth` |

---

## Required checks before PR

### Backend

```bash
cd backend
source .venv/bin/activate
ruff check src/
ruff format --check src/
mypy src/ --ignore-missing-imports
PYTHONPATH=src pytest tests/ -v
```

Use a **focused** `pytest` path when appropriate; say so in the PR.

### Frontend

```bash
cd apps/patient-portal   # or apps/clinician-portal
npm run lint
npm run build
npm run test             # when tests cover your change
```

### AI-assisted / agent-generated code

- Routers stay thin; business logic lives in `services/`.  
- No secrets, API keys, or real `.env` contents in commits.  
- Match existing patterns; prefer `packages/shared` over duplicating types/utils.  
- Document behavior or scope changes (see **Documentation updates**).  
- List **manual** verification steps in the PR.

---

## Project architecture (quick reference)

```
Request → Router → Service → DB / external client / Agent → Response
```

| Layer | Responsibility |
|-------|----------------|
| `routers/` | HTTP validation, call services, map responses |
| `services/` | Business rules (avoid FastAPI imports here) |
| `agents/` | LangGraph flows, LLM/tool orchestration |
| `models/` | Pydantic request/response schemas |
| `clients/` | Third-party SDKs (Gemini, Deepgram, Resend, …) |
| `db/` | Migrations; repositories where used |

### Design choices (why things look this way)

| Decision | Rationale |
|----------|-----------|
| `backend/src/app/` layout | Clean package boundary; `PYTHONPATH=src` for runs |
| Pydantic + `StrEnum` | Validate at API boundary |
| UUID IDs | Align with Supabase defaults |
| Services separate from routers | Easier unit tests without ASGI |

### Backend package map

| Package | Role |
|---------|------|
| `core/` | Auth helpers, exceptions, shared constants |
| `models/` | API schemas |
| `routers/` | Routes |
| `services/` | Domain logic |
| `agents/` | LangGraph agents |
| `tools/` | Reusable agent tools |
| `mcp/` | MCP server adapters |
| `a2a/` | Agent-to-agent protocol pieces |
| `clients/` | External APIs |
| `db/` | Migrations / DB access |
| `middleware/` | CORS, logging, etc. |

---

## Frontend quick reference

Both portals: Next.js App Router, Redux Toolkit, Tailwind, shared types in `packages/shared`.

| Area | Location |
|------|----------|
| Pages | `src/app/` |
| State | `src/store/` |
| API | `src/services/` |
| UI | `src/components/` |

### Patient portal routes (typical)

| Group | Screens |
|-------|---------|
| `(auth)/` | login, signup, onboarding |
| `(app)/` or dashboard group | today (feed), records, chat, profile/settings |

### Clinician portal routes (typical)

| Group | Screens |
|-------|---------|
| `(auth)/` | login, signup, clinic admin bootstrap |
| `(dashboard)/` | dashboard, patients, settings, etc. |

Exact routes evolve; treat `src/app/` as source of truth.

---

## Documentation updates

When your change affects behavior, contracts, or rollout:

- [.agent/TASKS.md](.agent/TASKS.md) — checklist status  
- [.agent/specs/](.agent/specs/) — design notes for features/phases  
- [README.md](README.md) / this file — contributor-facing workflow or setup  

If you intentionally skip docs, say **why** in the PR.

---

## Pull requests

Every PR should make easy for a reviewer to trust the change:

- **What** changed and **why**  
- **Risk** / blast radius  
- Link to issue or TASKS item  
- **Tests**: commands + outcome  
- **Manual** steps to verify  

The GitHub PR template and CI policy check reinforce required checklist items.

---

## Repository enforcement

- CI: lint, typecheck, tests, portal builds (see `.github/workflows/ci.yml`)  
- PR policy job: required checklist items in PR body  
- Husky + lint-staged: pre-commit on staged files  

**Recommended (org/repo admin):** protect `main`, require green CI, require at least one approval.

---

## Code review checklist

Before requesting review, walk through [.agent/workflows/ai-code-review.md](.agent/workflows/ai-code-review.md) and confirm:

- [ ] Matches [CODING_STANDARDS.md](.agent/CODING_STANDARDS.md)  
- [ ] No secrets or credentials in code or commits  
- [ ] Pydantic models validate inputs appropriately  
- [ ] Services do not import FastAPI  
- [ ] Errors use `core/exceptions` patterns where applicable  
- [ ] UI matches [DESIGN_SYSTEM.md](.agent/DESIGN_SYSTEM.md) for touched screens  
- [ ] New logic has tests or a short justification if not testable  
- [ ] Linters and typecheck pass locally  

---

## Need help?

| Question | Doc |
|----------|-----|
| System design | [ARCHITECTURE.md](.agent/ARCHITECTURE.md) |
| Code style | [CODING_STANDARDS.md](.agent/CODING_STANDARDS.md) |
| What to build next | [TASKS.md](.agent/TASKS.md) |
| Team process | [TEAM.md](.agent/TEAM.md) |
| DB / Supabase | [docs/supabase_setup_guide.md](docs/supabase_setup_guide.md) |

If it is not documented, ask the team and consider updating the docs in the same PR when you learn the answer.
