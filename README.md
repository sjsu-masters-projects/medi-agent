# MediAgent

> A dual-portal healthcare platform powered by multi-agent AI — Patient Portal + Clinician Portal.

**Patients** get a bilingual health companion that parses medical documents, manages medication schedules, explains reports in plain language, and supports voice-to-voice conversations.

**Clinicians** get real-time patient monitoring, automated pharmacovigilance (ADR detection → FDA MedWatch reporting), bidirectional document sync, and care continuity across providers.

---

## Monorepo Structure

```
medi-agent/
├── .agent/                          # 📚 Project brain — start here
│   ├── PROJECT.md                   #    What MediAgent is, decision log
│   ├── ARCHITECTURE.md              #    System design, data model, agent flow
│   ├── CODING_STANDARDS.md          #    Code style, SOLID, naming, testing
│   ├── DESIGN_SYSTEM.md             #    Colors, typography, components (from Figma)
│   ├── TASKS.md                     #    Full task breakdown by phase
│   ├── TEAM.md                      #    Team structure, sprints, Git workflow
│   └── workflows/                   #    Step-by-step guides
│       ├── new-feature.md           #    How to start a new feature
│       ├── new-agent.md             #    How to add a new AI agent
│       └── ai-code-review.md        #    AI code review checklist
│
├── backend/                         # 🐍 Python FastAPI backend
│   ├── src/app/
│   │   ├── main.py                  #    App factory, middleware, routers
│   │   ├── config.py                #    Env vars via pydantic-settings
│   │   ├── core/                    #    Exceptions, auth, constants
│   │   ├── models/                  #    Pydantic schemas (15 files, 32 schemas)
│   │   ├── routers/                 #    API routes — thin handlers
│   │   ├── services/                #    Business logic — framework-independent
│   │   ├── agents/                  #    LangGraph agents (7 sub-packages)
│   │   ├── tools/                   #    Agent tools (FHIR, RxNorm, Naranjo, etc.)
│   │   ├── mcp/                     #    MCP servers (Supabase, DailyMed, etc.)
│   │   ├── a2a/                     #    Agent-to-Agent protocol
│   │   ├── clients/                 #    SDK wrappers (Gemini, Deepgram, Resend)
│   │   ├── db/                      #    Database queries, migrations, seed
│   │   │   └── migrations/          #    SQL schema files (run in order)
│   │   ├── middleware/              #    Auth, CORS, rate limiting, logging
│   │   └── utils/                   #    Shared helpers
│   ├── tests/                       #    pytest test suite
│   ├── requirements.txt             #    Production deps (pinned)
│   ├── requirements-dev.txt         #    Dev/test deps
│   ├── pyproject.toml               #    Ruff, mypy, pytest config
│   └── Dockerfile
│
├── apps/
│   ├── patient-portal/              # 💊 Next.js PWA — patient-facing
│   │   └── src/
│   │       ├── app/                 #    App Router pages
│   │       ├── components/          #    UI, features, layouts
│   │       ├── store/               #    Redux Toolkit (auth, feed, chat, records)
│   │       ├── services/            #    API client
│   │       ├── hooks/               #    Custom React hooks
│   │       └── types/               #    TypeScript types
│   │
│   └── clinician-portal/            # 🩺 Next.js PWA — clinician-facing
│       └── src/
│           ├── app/                 #    App Router pages
│           ├── components/          #    UI, features, layouts
│           ├── store/               #    Redux Toolkit (auth, dashboard, patients, medwatch)
│           ├── services/            #    API client
│           ├── hooks/               #    Custom React hooks
│           └── types/               #    TypeScript types
│
├── packages/
│   └── shared/                      # 📦 Shared TypeScript types, utils, constants
│       └── src/
│           ├── types/               #    12 domain interfaces (single source of truth)
│           ├── utils/               #    formatDate, formatRelativeTime, clamp
│           └── constants/           #    API_ROUTES, NARANJO_THRESHOLD, RISK_LEVELS
│
├── docs/                            # 📄 Team-facing guides
│   └── supabase_setup_guide.md      #    DB setup, migrations, RLS, auth hooks
│
├── .github/workflows/ci.yml        # CI — lint + test + build
├── docker-compose.yml               # Local dev (backend, both portals)
├── .env.example                     # All required env var keys
├── CONTRIBUTING.md                  # Developer guide (you're reading it here ↓)
└── README.md                        # This file
```

---

## Quick Start

### Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.12+ | `python3 --version` |
| Node.js | 20.9+ | `node --version` |
| npm | 10+ | `npm --version` |

### 1. Clone & configure

```bash
git clone <repo-url> && cd medi-agent
cp .env.example .env
# Fill in API keys — see .env.example for where to get each one
```

Verify your setup:
```bash
./scripts/preflight.sh       # checks tools, .env, deps
./scripts/check-env.sh       # validates .env against .env.example
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
PYTHONPATH=src uvicorn app.main:app --reload
# API docs → http://localhost:8000/docs
```

### 3. Patient Portal

```bash
cd apps/patient-portal
npm install
npm run dev
# → http://localhost:3000
```

### 4. Clinician Portal

```bash
cd apps/clinician-portal
npm install
npm run dev -- --port 3001
# → http://localhost:3001
```

### 5. All at once (Docker)

```bash
docker compose up
# Backend → :8000  |  Patient → :3000  |  Clinician → :3001
```

---

## Tech Stack

| Layer | Tech | Version |
|-------|------|---------|
| Backend | FastAPI + Pydantic | 0.135.1 / 2.12.5 |
| Database | Supabase (Postgres + Auth + Storage) | 2.28.0 |
| AI / LLM | Gemini 2.0 (Flash + Pro) via google-genai | 1.66.0 |
| Agent Framework | LangGraph | 1.0.10 |
| Voice | Deepgram SDK | 6.0.1 |
| Frontend | Next.js 16 (App Router, Turbopack) | 16.1.6 |
| State | Redux Toolkit | 2.11.2 |
| Styling | Tailwind CSS v4 | 4.2.1 |
| Charts | Recharts | 3.7.0 |
| Email | Resend | 2.23.0 |

---

## Documentation

> **Start here → `.agent/PROJECT.md`** — explains what MediAgent is, the business thesis, and all architecture decisions.

### For Everyone

| Doc | What it covers |
|-----|----------------|
| [PROJECT.md](.agent/PROJECT.md) | Product context, decision log, tech stack, user personas |
| [ARCHITECTURE.md](.agent/ARCHITECTURE.md) | System design, data model, agent flow, API design, deployment |
| [TASKS.md](.agent/TASKS.md) | Full task breakdown by phase — what's done, what's next |
| [TEAM.md](.agent/TEAM.md) | Team structure, sprint process, Git workflow, PR conventions |

### For Developers

| Doc | What it covers |
|-----|----------------|
| [CODING_STANDARDS.md](.agent/CODING_STANDARDS.md) | SOLID principles, naming, error handling, file structure, testing |
| [DESIGN_SYSTEM.md](.agent/DESIGN_SYSTEM.md) | Colors, typography, components, layout (from Figma designs) |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to set up, develop, test, and submit code |
| [Supabase Setup Guide](docs/supabase_setup_guide.md) | Database schema, migrations, RLS policies, auth hooks, storage |

### Workflows (step-by-step guides)

| Workflow | When to use |
|----------|-------------|
| [new-feature.md](.agent/workflows/new-feature.md) | Starting any new feature |
| [new-agent.md](.agent/workflows/new-agent.md) | Adding a new AI agent to the LangGraph system |
| [ai-code-review.md](.agent/workflows/ai-code-review.md) | Reviewing AI-generated code before committing |

---

## For AI Agents

If you're an AI coding assistant working on this repo:

1. **Always read first:** `.agent/PROJECT.md` → `.agent/ARCHITECTURE.md` → `.agent/CODING_STANDARDS.md`
2. **Before any feature:** Follow `.agent/workflows/new-feature.md`
3. **Before any new agent:** Follow `.agent/workflows/new-agent.md`
4. **Before committing:** Run through `.agent/workflows/ai-code-review.md`
5. **UI work:** Reference `.agent/DESIGN_SYSTEM.md` for colors, fonts, and components
6. **Task context:** Check `.agent/TASKS.md` for what phase we're in

These docs are your ground truth. Don't guess — read them.

---

## API Overview

All endpoints live under `/api/v1/`. Full interactive docs at `/docs` (Swagger) or `/redoc`.

| Resource | Prefix | Key Endpoints |
|----------|--------|---------------|
| Auth | `/auth` | signup, login, refresh |
| Patients | `/patients` | profile, care team, join clinic |
| Clinicians | `/clinicians` | profile, patient list, invite codes |
| Documents | `/documents` | upload, list, explain (AI) |
| Medications | `/medications` | CRUD, active/inactive |
| Obligations | `/obligations` | CRUD (diet, exercise, custom) |
| Adherence | `/adherence` | log events, get scores |
| Chat | `/chat` | history, WebSocket (Phase 5) |
| Feed | `/feed` | aggregated daily tasks |
| ADR | `/adr` | assessments, MedWatch queue |
| Appointments | `/appointments` | CRUD, status tracking |
| Notifications | `/notifications` | list, mark read |

Health check: `GET /health`

---

## License

Proprietary — all rights reserved.
