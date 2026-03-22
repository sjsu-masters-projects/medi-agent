# MediAgent — System Architecture

> Last updated: 2026-03-21

---

## High-Level System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENTS                                   │
│  ┌──────────────────┐          ┌──────────────────────┐         │
│  │  Patient Portal   │          │  Clinician Portal     │         │
│  │  (Next.js PWA)    │          │  (Next.js PWA)        │         │
│  │  - Redux store    │          │  - Redux store        │         │
│  │  - Syncfusion PDF │          │  - Syncfusion PDF     │         │
│  │  - Deepgram SDK   │          │  - Recharts/Nivo      │         │
│  └────────┬─────────┘          └──────────┬───────────┘         │
│           │ HTTPS / WSS                    │ HTTPS / WSS         │
└───────────┼────────────────────────────────┼─────────────────────┘
            │                                │
            ▼                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API GATEWAY (FastAPI)                          │
│  ┌─────────────┐ ┌─────────────┐ ┌──────────────┐              │
│  │ REST Routes  │ │ WebSocket   │ │ Background   │              │
│  │ /api/v1/*    │ │ /ws/chat    │ │ Tasks (Cron) │              │
│  └──────┬──────┘ └──────┬──────┘ └──────┬───────┘              │
│         │               │               │                        │
│  ┌──────▼───────────────▼───────────────▼──────┐                │
│  │         Middleware Layer                      │                │
│  │  Auth (JWT) · CORS · Rate Limit · Logging    │                │
│  └──────────────────────┬──────────────────────┘                │
└─────────────────────────┼────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              AGENT LAYER (LangGraph + A2A Protocol)               │
│                                                                   │
│  ┌───────────┐ ──A2A──► ┌─────────┐ ──A2A──► ┌─────────────┐   │
│  │ Triage    │          │ Symptom │          │Pharmacovig. │   │
│  │ Agent     │          │ Agent   │          │Agent        │   │
│  └───────────┘          └─────────┘          └─────────────┘   │
│  ┌───────────┐ ┌─────────┐ ┌──────────┐ ┌───────────┐         │
│  │ Ingestion │ │Pre-Visit│ │Summary   │ │Scheduling │         │
│  │ Agent     │ │Prep     │ │Agent     │ │Agent      │         │
│  └─────┬─────┘ └────┬────┘ └────┬─────┘ └─────┬─────┘         │
│        │            │           │              │                │
│  ┌─────▼────────────▼───────────▼──────────────▼──────┐        │
│  │         MCP LAYER (Standardized Tool Access)        │        │
│  │  mcp-dailymed · mcp-rxnorm · mcp-supabase          │        │
│  │  mcp-deepgram · FHIR Builder · MedWatch Gen         │        │
│  │  Naranjo Calculator · Notification Sender           │        │
│  └────────────────────────┬───────────────────────────┘        │
│                           │                                     │
│  ┌────────────────────────▼───────────────────────────┐        │
│  │     Agent Cards (/.well-known/agent.json)           │        │
│  │     A2A endpoints for external agent discovery      │        │
│  └────────────────────────────────────────────────────┘        │
└───────────────────────────┼──────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    EXTERNAL SERVICES                              │
│  ┌─────────────────┐ ┌───────────────┐ ┌──────────────┐        │
│  │ Gemini 3.1      │ │ Deepgram      │ │ Resend       │        │
│  │ Flash Lite +    │ │ STT + TTS     │ │ (Email)      │        │
│  │ Pro (preview)   │ │               │ │              │        │
│  ├─────────────────┤ └───────────────┘ └──────────────┘        │
│  │ MedGemma 27B-it │                                            │
│  │(clinical tasks) │                                            │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DATA LAYER (Supabase)                          │
│  ┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐     │
│  │ PostgreSQL   │ │ pgvector │ │ Storage  │ │ Realtime  │     │
│  │ (relational) │ │ (RAG)    │ │ (files)  │ │ (live WS) │     │
│  └──────────────┘ └──────────┘ └──────────┘ └───────────┘     │
│  ┌──────────────┐                                               │
│  │ Auth (JWT,   │                                               │
│  │ MFA, magic)  │                                               │
│  └──────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Model

```
patients ──< care_teams >── clinicians
   │
   ├──< documents (source_clinic, uploaded_by, visibility)
   ├──< medications (prescribed_by_care_team_id)
   ├──< obligations (diet/exercise/custom, set_by_care_team_id)
   ├──< adherence_logs (for medications AND obligations)
   ├──< conditions (icd10_code)
   ├──< allergies
   ├──< symptom_reports (severity, related_med, ai_assessment)
   ├──< adr_assessments (naranjo_score, medwatch_draft, status)
   ├──< appointments
   ├──< chat_messages (role, intent, audio_url, language)
   ├──< notifications
   └──< clinician_messages (channel: in-app/email)
```

### Multi-Provider Care Model

- `care_teams` is a junction table linking patients to multiple clinicians
- Each relationship has: role, specialty_context, clinic_name, status (active/inactive/transferred)
- Documents tagged by source clinic + uploading provider
- Visibility: `all_providers` (default) or `specific_provider` (restricted)
- Today Feed aggregates tasks from ALL active providers, grouped by source

### Row-Level Security (RLS)

- Patients: own data only
- Clinicians: assigned patients only (via care_teams)
- Default-share with option to restrict specific documents
- All access logged for audit

---

## API Design Principles

1. **RESTful** for CRUD operations: `GET/POST/PUT/DELETE /api/v1/{resource}`
2. **WebSocket** for real-time chat: `/ws/chat/{patient_id}`
3. **Versioned API:** all routes prefixed with `/api/v1/`
4. **JWT auth** on every request (from Supabase Auth)
5. **Consistent error format:** `{ "error": { "code": "...", "message": "..." } }`
6. **Pagination:** cursor-based for lists
7. **OpenAPI auto-docs** at `/docs` (FastAPI built-in)

### Key API Groups

| Group | Base Path | Purpose |
|-------|-----------|---------|
| Auth | `/api/v1/auth` | Login, signup, token refresh |
| Patients | `/api/v1/patients` | Patient CRUD, profile |
| Documents | `/api/v1/documents` | Upload, parse, list, explain |
| Medications | `/api/v1/medications` | CRUD, adherence tracking |
| Obligations | `/api/v1/obligations` | CRUD, completion tracking |
| Chat | `/ws/chat/{id}` | Real-time chat (WebSocket) |
| Clinicians | `/api/v1/clinicians` | Dashboard data, patient lists |
| ADR | `/api/v1/adr` | Assessments, MedWatch forms |
| Appointments | `/api/v1/appointments` | CRUD, scheduling |

---

## Agent Flow (with A2A Communication)

```
User Input
    │
    ▼
Triage Agent ──────► Intent Classification
    │                    │
    ├── SYMPTOM ─(A2A)─► Symptom Agent ─(A2A)─► Pharmacovigilance Agent
    ├── MED_QUESTION ──► RAG Tool (via MCP) + LLM Response
    ├── SCHEDULE ─(A2A)► Scheduling Agent
    ├── GENERAL ───────► Direct LLM Response
    └── URGENT ────────► Escalation (clinician notification + 911 info)

Protocol Layers:
  A2A  = Agent ↔ Agent delegation (via Agent Cards + Task Objects)
  MCP  = Agent ↔ Tools/Data (DailyMed, RxNorm, Supabase, Deepgram)
```

### LLM Routing (Benchmark-Validated, 2026-03-21)

| Task Type | Model | Avg Latency | Completeness | Rationale |
|-----------|-------|-------------|--------------|----------|
| Document parsing | MedGemma 27B | 12.6s | 92% | Native clinical terminology, deepest extraction |
| ADR detection | MedGemma 27B | 20.6s | 80% | Naranjo 8-9, electrolyte monitoring, 5 action steps |
| Drug interaction check | MedGemma 27B | 8.0s | 100% | Both kidney + BP effects, most explicit |
| Triage classification | MedGemma 27B | 6.2s | 100% | Correct ESI, most concise emergency response |
| Patient-facing chat | Gemini 3.1 Flash Lite | 2.8s | 96% | Warmest tone, streaming, sub-3s |
| Voice pipeline | Gemini 3.1 Flash Lite | 2.8s | 96% | Low latency for STT→LLM→TTS chain |
| Lab/doc explanation | Gemini 3.1 Flash Lite | 2.8s | 100% | Best patient-friendly delivery |
| SOAP notes | Gemini 3.1 Pro | 17.5s | 88% | Deepest reasoning for clinician review |
| MedWatch drafting | Gemini 3.1 Pro | 21.5s | 80% | CYP3A4 reconciliation, FDA-grade |
| Nightly ADR scan | Gemini 3.1 Pro | batch | — | No latency constraint, deep analysis |

---

## Deployment

| Component | Platform | URL Pattern |
|-----------|----------|-------------|
| Patient Portal | Vercel | `patient.mediagent.app` |
| Clinician Portal | Vercel | `clinic.mediagent.app` |
| Backend API | Google Cloud Run | `api.mediagent.app` |
| Database | Supabase | Managed |
| Cron Jobs | Google Cloud Scheduler | Calls Cloud Run endpoints |

---

## Environment Variables (Template)

```bash
# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# Gemini
GOOGLE_API_KEY=
GOOGLE_PROJECT_ID=

# MedGemma (via Vertex AI MedGemma 27B endpoint)
VERTEX_AI_MEDGEMMA_ENDPOINT=projects/.../locations/.../endpoints/...
VERTEX_AI_ENDPOINT_TYPE=auto

# Model names
GEMINI_FLASH_MODEL=gemini-3.1-flash-lite-preview
GEMINI_PRO_MODEL=gemini-3.1-pro-preview
MEDGEMMA_MODEL=google/medgemma-27b-it

# Deepgram
DEEPGRAM_API_KEY=

# Resend
RESEND_API_KEY=

# Syncfusion
SYNCFUSION_LICENSE_KEY=

# App
BACKEND_URL=
PATIENT_PORTAL_URL=
CLINICIAN_PORTAL_URL=
ENVIRONMENT=development  # development | staging | production
```
