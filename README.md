# MediAgent

Dual-portal healthcare platform with AI-assisted patient support and clinician workflows.

- `apps/patient-portal`: patient-facing PWA
- `apps/clinician-portal`: clinician-facing PWA
- `backend`: FastAPI API + agents + integrations
- `packages/shared`: shared TypeScript types/utilities

## What It Does

- Patient document upload + AI explanation
- Medication/obligation tracking and adherence logging
- Real-time patient chat (WebSocket) with triage/symptom routing
- Voice transport foundation for chat/assistive workflows
- Clinician dashboard and clinic/team management flows
- Pharmacovigilance workflow foundations (ADR lifecycle tracking)

For exact phase-by-phase status and backlog, use `.agent/TASKS.md`.

## Monorepo Layout

```text
medi-agent/
├── .agent/                  # Product, architecture, tasks, standards
├── apps/
│   ├── patient-portal/      # Next.js patient app
│   └── clinician-portal/    # Next.js clinician app
├── backend/                 # FastAPI backend
├── packages/shared/         # Shared TS package
├── docs/                    # Setup guides and docs
└── scripts/                 # Repo utility scripts
```

## Quick Start

### Prerequisites

- Python `3.12+`
- Node `20+`
- npm `10+`

### 1) Clone + env setup

```bash
git clone <repo-url>
cd medi-agent

cp .env.example .env
cp apps/patient-portal/.env.example apps/patient-portal/.env.local
cp apps/clinician-portal/.env.example apps/clinician-portal/.env.local
```

Validate environment:

```bash
./scripts/preflight.sh
./scripts/check-env.sh
```

Clinician invite emails require `RESEND_API_KEY` (and a verified-domain `RESEND_CLINICIAN_ONBOARDING_FROM_EMAIL` in production); see `CONTRIBUTING.md` and root `.env.example`.

### 2) Run backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=src uvicorn app.main:app --reload
```

Backend docs: `http://localhost:8000/docs`

### 3) Run portals

Patient:

```bash
cd apps/patient-portal
npm ci
npm run dev
```

Clinician:

```bash
cd apps/clinician-portal
npm ci
npm run dev -- --port 3001
```

## Core Stack

- Backend: FastAPI, Pydantic, Supabase
- AI: Gemini (Flash/Pro), MedGemma routing foundations, LangGraph
- Voice: Deepgram
- Email: Resend
- Frontend: Next.js 16 + Redux Toolkit + Tailwind v4

## Documentation Map

Start here:

- `.agent/PROJECT.md`
- `.agent/ARCHITECTURE.md`
- `.agent/TASKS.md`
- `.agent/CODING_STANDARDS.md`
- `CONTRIBUTING.md`

Workflow docs:

- `.agent/workflows/new-feature.md`
- `.agent/workflows/new-agent.md`
- `.agent/workflows/ai-code-review.md`

Infra docs:

- `docs/supabase_setup_guide.md`

## Quality Gates

Repository checks include:

- CI lint/type/test/build workflows
- PR policy check for required checklist completion
- PR template with docs/test verification sections
- Husky/lint-staged local pre-commit checks

Recommended GitHub settings:

- Protect `main`
- Require all CI checks
- Require at least one PR approval

## API Overview

Base path: `/api/v1`

Primary route groups:

- `/auth`
- `/patients`
- `/clinicians`
- `/staff`
- `/documents`
- `/medications`
- `/obligations`
- `/adherence`
- `/chat` (REST + WebSocket)
- `/feed`
- `/adr`
- `/cron`

Health check: `GET /health`

## Security Notes

- Never commit `.env`, `.env.local`, keys, tokens, or service account files.
- Rotate any credential that is accidentally exposed in logs/chat/screenshots.

## License

Proprietary - all rights reserved.
