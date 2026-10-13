# MediAgent

Dual-portal healthcare platform with AI-assisted patient support and clinician workflows.

- `apps/patient-portal`: patient-facing PWA
- `apps/clinician-portal`: clinician-facing PWA
- `backend`: FastAPI API + agents + integrations
- `packages/shared`: shared TypeScript types/utilities

## What It Does

- Patient document upload with OCR, source-cited extraction and a plain-language explanation
- Nora, the patient assistant: text and voice in en-US and es-MX, grounded in the patient's
  record and citing MedlinePlus, DailyMed and RxNorm, with deterministic triage first
- Clinician-approved care plans (wording approved in both languages) projected into Today,
  with adherence and barrier logging
- Appointment offers, patient responses and one-time calendar export
- Two-way patient/care-team messaging and an in-app notification centre in both portals
- SMART on FHIR sandbox import into provenance-backed review candidates
- Clinician dashboard, clinic/team management and audited ADR (Naranjo) review

For exact phase-by-phase status and backlog, use `.agent/TASKS.md`.

For the deterministic synthetic demonstration environment, see
[`docs/demo-environment.md`](docs/demo-environment.md) and its
[`synthetic data catalog`](docs/synthetic-data-catalog.md).

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

### 1) One-command setup and validation

For a clean local checkout, create the development dependencies and run the quality
gates with:

```bash
./scripts/bootstrap-and-validate.sh
```

The command uses the locked backend and portal dependencies, creates `backend/.venv`
when needed, and runs the local lint, format, type, migration, test, and build checks.
It does not create credentials or contact a clinical system.

### 2) Clone + env setup

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

### 3) Run backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=src uvicorn app.main:app --reload
```

Backend docs: `http://localhost:8000/docs`

### 4) Run portals

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
- AI: ADK workload runtime on Vertex AI Gemini (managed open-weight models only in the evaluation harness)
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

- `.agent/workflows/new-agent.md`
- `.github/pull_request_template.md`

Documentation map and infrastructure:

- `docs/README.md` — routes every need to its source document
- `.agent/CLOUD_INFRASTRUCTURE_GUIDE.md` — Cloud Run, Jobs, Cloud Scheduler and run logs

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

- `/auth`, `/auth/mfa`
- `/clinics`
- `/patients`
- `/clinicians`
- `/staff`
- `/documents`
- `/medications`
- `/obligations`
- `/adherence`
- `/chat` (REST)
- `/care-plans`
- `/care-conversations`
- `/feed`
- `/appointments`
- `/notifications`, `/notification-centre`
- `/reminders`
- `/smart`
- `/cron` (Cloud Scheduler only)

WebSockets: `/ws/chat/{patient_id}` and `/ws/voice/{patient_id}`.

Health check: `GET /health`

## Security Notes

- Never commit `.env`, `.env.local`, keys, tokens, or service account files.
- Rotate any credential that is accidentally exposed in logs/chat/screenshots.

## License

Proprietary - all rights reserved.
