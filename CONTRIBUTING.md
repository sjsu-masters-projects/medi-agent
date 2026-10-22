# Contributing to MediAgent

Developer guide for setup, architecture orientation, verification, and pull requests. This file is the **onboarding entry**; deeper product and design decisions live under `.agent/`.

---

## Read first

Before writing code, read in this order:

1. [AGENTS.md](AGENTS.md) — shared task routing, safety, and delivery contract
2. [TASKS.md](.agent/TASKS.md) — phase status and backlog
3. [PROJECT.md](.agent/PROJECT.md) — product context and decisions
4. [ARCHITECTURE.md](.agent/ARCHITECTURE.md) — system design and data model
5. [CODING_STANDARDS.md](.agent/CODING_STANDARDS.md) — how we write code
6. [TEAM.md](.agent/TEAM.md) — Git workflow and PR norms

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
| `GOOGLE_PROJECT_ID` | Vertex AI model calls |
| `VERTEX_AI_LOCATION` | MaaS endpoint location for the evaluation harness's open-weight models; no live route uses GPT OSS |
| `GEMINI_VERTEX_AI_LOCATION` | Gemini Vertex endpoint location; Gemini 3.8 Flash uses `global` |
| `GEMINI_FLASH_MODEL` | Gemini Flash model ID used by the agent runtime |
| `GEMINI_TRIAGE_MODEL` | Native Gemini classifier; separate from patient prose |
| `GEMINI_FALLBACK_MODEL` | Distinct full-Flash fallback for replies and explanation; intake has no qualified backup |
| `GEMINI_PRO_MODEL` | Pro compatibility/evaluation model, outside the interactive routing path |
| `CHAT_TURN_TIMEOUT_SECONDS` | Hard ceiling for the complete coordinator-and-responder chat turn |
| `MODEL_CIRCUIT_BREAKER_COOLDOWN_SECONDS` | How long MaaS is bypassed after a timeout or retriable provider failure |
| `MODEL_MAX_CONCURRENCY`, `MODEL_MIN_START_INTERVAL_SECONDS` | Per-process model-call concurrency and start spacing |
| `MODEL_ADMISSION_WAIT_SECONDS`, `REPLY_FALLBACK_MIN_SECONDS` | Longest an interactive model call waits for a slot before it is shed; minimum reply budget left to try the backup model after text was shown |
| `AI_AVAILABILITY_ENABLED`, `AI_AVAILABILITY_FLUSH_SECONDS` | Bounded model availability counters (migration 090) |
| `CRON_AUTH_TOKEN` | Shared token for Cloud Scheduler calls to the backend cron endpoints |
| `DEEPGRAM_API_KEY` | Voice STT/TTS |
| `RESEND_API_KEY` | Backend transactional email (addressed invitations, contact verification and opted-in event notices); Supabase Auth SMTP is configured separately |
| `RESEND_CLINICIAN_ONBOARDING_FROM_EMAIL` | From address for clinician invite mail (use a verified-domain sender in production) |
| `RESEND_FROM_EMAIL` | Verified-domain sender for contact verification and opted-in notices; no default testing sender |
| `EMAIL_CODE_HMAC_SECRET` | Optional dedicated key for hashing email verification codes; falls back to `SUPABASE_JWT_SECRET` |
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

SQL migrations live in `backend/src/app/db/migrations/`. Apply them with the ledger
script, which runs every not-yet-applied file in filename order, records a checksum per
file in `public.schema_migrations`, and refuses to re-run a file whose contents changed:

```bash
export MEDIAGENT_DB_URL="<Postgres connection string for the environment you may change>"
./scripts/apply-supabase-migrations.sh
```

Run it from the checkout whose migrations you mean to apply, and only against an
environment you are authorized to change.

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
3. Implement per [CODING_STANDARDS.md](.agent/CODING_STANDARDS.md).
4. Add or update tests.
5. Run checks below.
6. Open a PR using the [repo template](.github/pull_request_template.md).

### Adding a product worker

Follow [.agent/workflows/new-agent.md](.agent/workflows/new-agent.md). New model-backed work
belongs under `backend/src/app/adk/`; retain `backend/src/app/agents/` only for legacy
compatibility while it is still referenced.

- `adk/agents/<name>/agent.py` — ADK agent entry
- `adk/agents/<name>/prompts.py` — prompt templates
- `adk/registry.py` — reviewed model route, fallback, budget, and kill switch

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

### Automated-code safeguards

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
| `adk/` | Current model runtime, safety plugins, routes, and ADK agents |
| `agents/` | Legacy compatibility paths; do not start new work here |
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
| `adk/` | Current agent runtime and plugins |
| `agents/` | Legacy compatibility paths |
| `tools/` | FHIR builder and medication normalizer |
| `clients/` | External APIs |
| `db/` | Migrations, repositories, seed data |
| `workers/` | Cloud Run Job entry points (document ingestion, health-knowledge refresh) |
| `safety/` | Deterministic triage floor and escalation |
| `middleware/` | Rate limiting |

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

- CI: backend lint, typecheck, sharded tests and coverage, migration validation, secret scan, and portal lint/build (see `.github/workflows/ci.yml`); `.github/workflows/frontend.yml` also lints and builds the portals when `apps/**` or `packages/**` change  
- CI scope: the slow backend jobs (full-suite coverage and the Docker PostgreSQL contract matrix) run on pull requests, the merge queue, manual dispatch and a weekly Monday schedule, not on pushes to main, which would repeat the pull request run. On a pull request the PostgreSQL contracts run only when backend SQL, migrations, services, routers, agents, safety code, `backend/tests/integration`, backend dependencies or `ci.yml` change; otherwise that job is skipped and CI Summary still passes. Lint, typecheck, unit-test shards and portal builds run on every event. CI Summary requires lint, format and mypy to succeed, so a skip caused by an upstream failure cannot pass.
- PR policy job: required checklist items in PR body  
- Husky + lint-staged: pre-commit on staged files  

**Recommended (org/repo admin):** protect `main`, require green CI, require at least one approval.

---

## Code review checklist

Before requesting review, confirm:

- [ ] Matches [CODING_STANDARDS.md](.agent/CODING_STANDARDS.md)  
- [ ] No secrets or credentials in code or commits  
- [ ] No hardcoded URLs, keys or configuration values; settings come from `config.py`  
- [ ] Every import is a real dependency or local module, and table/column names match the migrations  
- [ ] New tables or queries consider RLS and least-privilege access  
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
| Shared task routing and safety rules | [AGENTS.md](AGENTS.md) |
| Supported coding-environment setup | [Contributor agent workflow](docs/contributor-agent-workflow.md) |
| System design | [ARCHITECTURE.md](.agent/ARCHITECTURE.md) |
| Code style | [CODING_STANDARDS.md](.agent/CODING_STANDARDS.md) |
| What to build next | [TASKS.md](.agent/TASKS.md) |
| Team process | [TEAM.md](.agent/TEAM.md) |
| DB / Supabase | [docs/supabase_setup_guide.md](docs/supabase_setup_guide.md) |

If it is not documented, ask the team and consider updating the docs in the same PR when you learn the answer.
