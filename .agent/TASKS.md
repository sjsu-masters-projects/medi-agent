# MediAgent — Master Task Breakdown

> This is the single source of truth for ALL tasks. Update status as you work.
> `[ ]` = Backlog · `[/]` = In Progress · `[x]` = Done

---

## Phase 0: Product & Design (Weeks 1–2)

### 0.1 Product Definition
- [x] Draft initial product concept
- [x] Define user personas (Sarah, Dr. Smith, Dr. Patel)
- [x] Create comprehensive PRD (features, priorities, architecture)
- [x] Design multi-provider care model (care_teams)
- [x] Finalize tech stack decisions
- [x] Document coding standards and team processes
- [x] Lock protocol decisions (MCP, A2A, MedGemma, thinking mode)
- [x] Get full team alignment on PRD

### 0.2 Design & UX
- [x] Create information architecture (sitemap) for Patient Portal
- [x] Create information architecture (sitemap) for Clinician Portal
- [x] Define user flows: patient onboarding
- [x] Define user flows: document upload → parse → Today Feed
- [x] Define user flows: chat + voice symptom reporting
- [x] Define user flows: clinician dashboard → patient deep dive → MedWatch
- [x] Create Figma wireframes for Patient Portal (all screens)
- [x] Create Figma wireframes for Clinician Portal (all screens)
- [x] Define design system: colors, typography, spacing, component library
- [x] Create high-fidelity mockups (Figma AI can accelerate this)

---

## Phase 1: Infrastructure & Setup (Weeks 3–4)

### 1.1 Repository Setup
- [x] Initialize monorepo structure
- [x] Set up `apps/patient-portal` (Next.js + PWA)
- [x] Set up `apps/clinician-portal` (Next.js + PWA)
- [x] Set up `packages/shared` (types, utils)
- [x] Set up `backend/` (FastAPI project)
- [x] Configure TailwindCSS for both portals
- [x] Configure Redux store for both portals
- [x] Create `docker-compose.yml` for local dev

### 1.2 Supabase Setup
- [x] Create Supabase project
- [x] Create all database tables (see ARCHITECTURE.md data model)
  - [x] `patients`
  - [x] `clinicians`
  - [x] `care_teams`
  - [x] `documents`
  - [x] `medications`
  - [x] `obligations`
  - [x] `adherence_logs`
  - [x] `conditions`
  - [x] `allergies`
  - [x] `symptom_reports`
  - [x] `adr_assessments`
  - [x] `appointments`
  - [x] `chat_messages`
  - [x] `notifications`
  - [x] `clinician_messages`
- [x] Configure Row-Level Security (RLS) policies for all tables
- [x] Set up Supabase Auth (magic link + email/password + MFA + JWT claims hook)
- [x] Set up Supabase Storage buckets (documents, avatars, voice-messages)
- [ ] Test RLS policies with different user roles — external/manual validation with real auth users

### 1.3 CI/CD
- [x] Set up GitHub Actions: lint on PR (Ruff + ESLint)
- [x] Set up GitHub Actions: test on PR (pytest + Vitest)
- [x] Set up GitHub Actions: build check on PR
- [x] Set up GitHub Actions: deploy backend to Cloud Run on merge to main
- [x] Set up GitHub Actions: deploy portals to Vercel on merge to main
- [x] Set up Husky pre-commit hooks (lint + format)

### 1.4 Cloud Infrastructure
- [x] Set up Google Cloud project / guide
- [x] Configure Cloud Run strategy for backend
- [ ] Configure Cloud Scheduler strategy for cron jobs — external/manual infrastructure dependency
  - [x] Define cron job inventory and owner per job
  - [x] Define schedule and timezone standards for production jobs
  - [x] Define retry/backoff policy and idempotency requirements for scheduled endpoints
  - [x] Define failure handling and replay expectations
  - [ ] Define monitoring and alert thresholds for scheduled jobs
  - [x] Document deployment and runbook requirements for Scheduler to Cloud Run
- [x] Set up Vercel strategy (patient-portal, clinician-portal)
- [x] Configure environment variables strategy
- [ ] Set up Sentry strategy for error monitoring — external/manual infrastructure dependency

### 1.5 External Service Setup
- [x] Get Gemini API key (Google AI Studio / Vertex AI)
- [x] Get Deepgram API key and configure SDK
- [x] Set up Resend for email
- [x] Test DailyMed API access  
- [x] Test RxNorm API access
- [ ] Obtain Syncfusion Community License key — external/manual license dependency
- [ ] Download and test MedGemma model access (Hugging Face / Vertex AI) — external/manual model-access dependency

### 1.6 Service Layer & MCP Servers (for AI Agents)
- [x] DailyMed service — drug labels, ADR profiles (`app/services/dailymed_service.py`)
- [x] RxNorm service — drug normalization (`app/services/rxnorm_service.py`)
- [x] Supabase MCP server — patient data queries, shared connection (`app/mcp/supabase_server.py`)
- [x] Deepgram MCP server — voice STT/TTS, shared client (`app/mcp/deepgram_server.py`)
- [x] MCP base class and module init (`app/mcp/base.py`)
- [x] Add comprehensive integration tests and strict type hints

### 1.7 A2A Protocol Setup
- [ ] Create Agent Card JSON schema for each agent
- [ ] Expose `/.well-known/agent.json` endpoint on backend
- [/] Implement A2A task management (submit, status, artifacts) — internal lifecycle persistence, retry/backoff, dead-letter, and clinician timeline landed in Phase 5; public A2A protocol exposure is still open
- [ ] Create mock "Hospital EHR Agent" for demo

---

## Phase 2: Backend Core (Weeks 5–8)

### 2.1 FastAPI Foundation
- [x] Set up FastAPI app with middleware (CORS, auth, logging)
- [x] Create Pydantic models for all entities (request/response schemas)
- [x] Create Supabase client service (connection, queries)
- [x] Create base error handling (custom exceptions, error responses)
- [x] Set up API versioning (`/api/v1/`)
- [x] Auto-generate OpenAPI docs

### 2.2 Authentication API
- [x] `POST /api/v1/auth/signup/patient` — patient signup
- [x] `POST /api/v1/auth/signup/clinician` — clinician signup
- [x] `POST /api/v1/auth/signup/clinic-admin` — bootstrap clinic + first clinic admin
- [x] `POST /api/v1/auth/login` — email/password login
- [x] `POST /api/v1/auth/refresh` — token refresh
- [x] `POST /api/v1/auth/password-reset` — password reset email
- [x] `GET /api/v1/auth/me` — current user from JWT
- [x] Validate clinician signup against active clinic codes + allowed roles
- [x] JWT middleware for route protection
- [x] Role-based access control (patient vs clinician)
- [x] Harden JWT claims parsing + role extraction fallback for auth sessions
- [x] Write auth integration tests

### 2.3 Patient API
- [x] `GET /api/v1/patients/me` — get own profile
- [x] `PUT /api/v1/patients/me` — update profile
- [x] `GET /api/v1/patients/me/care-team` — list patient's providers
- [x] `POST /api/v1/patients/me/care-team/join` — join clinic via code
- [x] Enforce invite lifecycle checks (invalid, expired, claimed, already linked)
- [x] Write patient API tests

### 2.4 Clinician API
- [x] `GET /api/v1/clinicians/me` — get own profile
- [x] `GET /api/v1/clinicians/me/patients` — list assigned patients
- [x] `GET /api/v1/clinicians/me/patients/{id}` — get patient detail
- [x] `POST /api/v1/clinicians/me/invite-code` — generate patient invite code
- [x] `GET /api/v1/clinicians/me/invite-code` — read latest pending invite code
- [x] `GET /api/v1/clinicians/me/invite-codes` — list invite lifecycle history
- [x] `POST /api/v1/clinicians/me/invite-codes/{care_team_id}/revoke` — revoke pending invite code
- [x] `POST /api/v1/clinics/resolve-code` — resolve clinic code pre-auth
- [x] Write clinician API tests

### 2.5 Document API
- [x] `POST /api/v1/documents/` — register uploaded document (metadata-only)
- [x] `GET /api/v1/documents` — list patient's documents
- [x] `GET /api/v1/documents/{id}` — get document detail + signed URL
- [x] `POST /api/v1/documents/{id}/explain` — 501 placeholder (Phase 4)
- [x] File validation + signed URL generation
- [x] Write document API tests

### 2.6 Medications & Obligations API
- [x] `GET /api/v1/medications` — list patient's active medications
- [x] `POST /api/v1/medications` — create medication
- [x] `PUT /api/v1/medications/{id}` — update medication
- [x] `GET /api/v1/obligations` — list patient's obligations
- [x] `POST /api/v1/obligations` — create obligation
- [x] `GET /api/v1/reminders/targets` — list reminder-eligible medications and obligations
- [x] `PUT /api/v1/reminders/{target_type}/{target_id}` — upsert patient-owned reminder schedule
- [x] `POST /api/v1/adherence` — log medication taken / obligation completed
- [x] `GET /api/v1/adherence/stats` — adherence score + streak calculation
- [x] Write medication and adherence tests

### 2.7 Today Feed API
- [x] `GET /api/v1/feed/today` — aggregated daily tasks (meds + obligations from all providers)
- [x] Include source provider info for each task
- [x] Calculate which tasks are pending/completed/missed
- [x] Generate per-occurrence tasks from patient reminder schedules when configured
- [x] Write feed tests

---

## Phase 3: Frontend Core (Weeks 5–8, parallel with Phase 2)

### 3.1 Design System
- [x] Set up TailwindCSS theme (colors, typography, spacing)
- [x] Create base UI components: Button, Input, Card, Badge, Modal, Dropdown
- [x] Create layout components: AppShell, Sidebar, TopBar, BottomNav
- [x] Create loading states (skeleton screens)
- [x] Create empty states
- [x] Create error states
- [x] Make all components responsive (mobile-first for patient, desktop-first for clinician)

### 3.2 Patient Portal — Auth
- [x] Sign-up page (email/password flow via Supabase Auth)
- [x] Onboarding flow (name, DOB, language, allergies)
- [x] Join clinic (enter code or use invite link)
- [x] Redirect patients without care team to profile join-clinic flow
- [x] Auth state management in Redux
- [x] Protected route wrapper

### 3.3 Patient Portal — Today Feed
- [x] Today Feed page layout
- [x] Medication task card component (name, dosage, time, instructions)
- [x] Obligation task card component (type badge, description)
- [x] Provider grouping (show which doctor set each task)
- [x] Tap to mark done (optimistic update + API call)
- [x] Missed task visual indicator
- [x] Adherence score display (percentage + streak)

### 3.4 Patient Portal — My Records
- [x] Document list view
- [x] Document upload button (file picker + camera capture)
- [x] Upload progress indicator
- [x] Research and configure Syncfusion PDF viewer integration
- [x] Syncfusion PDF viewer UI component (in-app viewing)
- [x] "Explain This to Me" button + summary display
- [x] Language selector for explanation

### 3.5 Clinician Portal — Auth
- [x] Login page (email + password)
- [x] MFA setup flow
- [x] Clinic setup page (name, NPI)
- [x] Role management (Admin, Provider, Nurse)
- [x] Clinic-code verification gate before clinician login/signup
- [x] Clinic-admin bootstrap signup page (`/signup/admin`)
- [x] Auth state in Redux
- [x] Protected routes

### 3.6 Clinician Portal — Dashboard Shell
- [x] Dashboard layout (sidebar + content area)
- [x] Navigation (Dashboard, Patients, MedWatch, Settings)
- [x] Patient list table component
- [x] Risk badge component (🟢🟡🔴)
- [x] Responsive layout

### 3.7 Phase 3 — Known Limitations & Tech Debt
- [x] Create generic error state component (`components/ui/error-state.tsx`)
- [x] Research and configure Syncfusion PDF viewer integration
- [x] Language selector for AI record explanations
- [x] Clinician MFA setup flow
- [x] Clinician role management (Admin, Provider, Nurse)
- [x] Clinician protected route wrapper
- [x] Refactor clinician patients page to use reusable `DataTable` component
- [x] Revert `--webpack` build flag to Turbopack once infra supports it
- [x] Fix vite path traversal vulnerability (upgrade to ≥7.3.2)

---

## Phase 4: Ingestion Agent (Weeks 9–12)

### 4.1 Agent Core
- [x] Create BaseAgent abstract class (SOLID compliant) — `agents/base.py`
- [x] Create Gemini client service (retry, timeout, structured output) — `clients/gemini.py`
- [x] Create MedGemma client service (Vertex AI + HF + fallback) — `clients/medgemma.py`
- [x] Fix MedGemma: Gemma chat template for vLLM endpoint
- [x] Fix MedGemma: prompt-echo stripping
- [x] Create LangGraph state schema for ingestion workflow — `agents/ingestion/graph.py`
- [x] Agent execution observability/tracing — `core/observability.py`
- [x] Create ModelRouter service (route tasks to correct model)
- [x] Implement Ingestion Agent graph nodes:
  - [x] Node: receive_document (validate input, set state)
  - [x] Node: extract_content (MedGemma 27B for clinical extraction)
  - [x] Node: validate_fhir (validate against FHIR schemas)
  - [x] Node: normalize_medications (RxNorm MCP lookup)
  - [x] Node: save_to_database (Supabase MCP upsert)
  - [x] Node: generate_summary (Flash Lite for patient-facing summary)
  - [x] Node: create_feed_tasks (extract meds + follow-ups → obligations)
- [x] Codebase cleanup (remove duplicates and unnecessary files)

### 4.2 Tools
- [x] FHIR Resource Builder (MedicationRequest, Condition, AllergyIntolerance, Appointment)
- [x] RxNorm API client (brand → generic → RxCUI normalization)
- [x] Medication normalizer (parse dosage strings, frequency extraction)

### 4.3 MedGemma Evaluation
- [x] Deploy MedGemma 27B on Vertex AI Model Garden
- [x] Create 5 clinical benchmark scenarios (lab, ADR, drug interaction, triage, discharge)
- [x] Run 4 benchmark iterations (fix prompt format, fix model names, fix chat template)
- [x] Compare accuracy: MedGemma 27B vs Gemini Flash Lite vs Gemini Pro
- [x] Decision: adopt MedGemma 27B for clinical tasks (parsing, ADR, interactions, triage)
- [x] Document results — `backend/reports/benchmark_27b_20260321_192905.md`
- [x] Add D17/D18 to PROJECT.md Decision Log

### 4.4 Testing
- [x] Create synthetic test documents (discharge summary, lab report, prescription, diagnostic report)
  - [x] `backend/tests/fixtures/discharge_summary.txt`
  - [x] `backend/tests/fixtures/lab_report.txt`
  - [x] `backend/tests/fixtures/prescription.txt`
  - [x] `backend/tests/fixtures/diagnostic_report.txt`
- [x] Golden-set evaluation: expected parsing output for each test document
  - [x] `backend/tests/fixtures/discharge_summary_expected.json`
  - [x] `backend/tests/fixtures/lab_report_expected.json`
  - [x] `backend/tests/fixtures/prescription_expected.json`
  - [x] `backend/tests/fixtures/diagnostic_report_expected.json`
- [x] Golden-set integration test: load fixture → run pipeline → assert against expected JSON
- [x] Unit tests for FHIR builder and normalizer
- [x] Integration test: upload → parse → database → Today Feed

### 4.5 Patient Portal Integration
- [x] Wire up document upload → API → Ingestion Agent → DB
- [x] Today Feed auto-populates after document parsing
- [x] "Explain This" calls AI and displays summary
- [x] Handle parsing errors gracefully (show status, allow retry)

---

## Phase 5: Chat & Voice — Triage + Symptom Agents (Weeks 13–16)

### 5.0 Implementation Plan
- [x] Audit current Phase 5 chat, voice, RAG, multilingual, and A2A implementation state
- [x] Define production architecture for chat, voice, model routing, RAG, safety, and multilingual behavior - `.agent/specs/phase-5-chat-voice-design.md`
- [ ] Ship Phase 5 as small reviewable PRs following the design plan

### 5.1 Chat Backend
- [x] WebSocket endpoint `/ws/chat/{patient_id}`
- [x] Message persistence to `chat_messages` table
- [x] Conversation history retrieval (sliding window + summary)
- [x] Patient context injection (active meds, recent symptoms, conditions)
- [x] Document context injection API: accept `document_id` / `context=doc:<id>` and fetch parsed summary for chat context
- [x] Chat pre-load behavior for "Ask about this document": initialize chat with fetched document summary context
- [x] Document context completion criteria: backend context fetch and patient chat prefill UX are independently tested

### 5.2 Triage Agent
- [x] Intent classification (symptom, medication_question, schedule, general, urgent)
- [x] Multi-turn conversation state management
- [/] Routing logic: intent → appropriate sub-agent/tool
- [x] Safety rails: detect urgent/emergency → escalation response + clinician notification
- [x] Bilingual response generation (auto-detect language, respond in same)

### 5.3 Symptom Analysis Agent
- [/] Follow-up question generation (severity, timing, related meds, recent changes)
- [/] Structured symptom report creation (symptom, severity 1-10, onset, related_med)
- [x] Save to `symptom_reports` table
- [/] Delegate to Pharmacovigilance Agent via A2A protocol (not direct function call)
- [x] Verify A2A task lifecycle: submitted → working → completed
- [x] Enforce per-symptom-event A2A idempotency keys for task creation
- [x] Add A2A retry/backoff policy with dead-letter terminal state
- [x] Add background retry worker: process `retrying` tasks where `next_retry_at <= now`

### 5.4 Medical RAG
- [/] Populate pgvector with drug information (from DailyMed)
  - [x] Add `drug_knowledge_chunks` pgvector schema and similarity-match RPC
  - [x] Add DailyMed label chunk builder/upsert service
  - [ ] Run migration and ingest the first curated production drug label set
- [x] Embedding generation for medication knowledge base
  - [x] Add Google Gen AI embedding client with configurable model and dimensions
  - [x] Keep embedding dependency injectable for offline tests
- [x] RAG retrieval pipeline: query → embed → similarity search → LLM response
  - [x] Retrieve medication chunks for likely medication questions using active medication names/RxCUIs
  - [x] Pass retrieved medication context into the triage response prompt
  - [x] Add safe fallback when retrieval is weak or unavailable
- [x] Citation inclusion (source of information)
  - [x] Preserve DailyMed source title, section, URL, and citation id in prompt context
  - [x] Instruct patient-facing medication answers to cite grounded chunks

### 5.5 Voice Integration
- [ ] Deepgram STT client (streaming WebSocket)
- [ ] Deepgram TTS client (text → audio stream)
- [ ] Voice-to-voice pipeline: mic → STT → Triage Agent → response → TTS → speaker
- [ ] Language detection from audio
- [ ] Audio message storage (Supabase Storage, URL in chat_messages)
- [ ] Voice readback of document summaries: 🔊 button on Records modal → TTS in selected language
- [ ] Multilingual TTS beyond EN/ES (Hindi, Chinese, Vietnamese, Tagalog — top US non-English medical populations)

### 5.6 Patient Portal — Chat UI
- [x] Chat page layout (WhatsApp-style)
- [x] Message bubble components (user, assistant)
- [x] Text input with send button
- [x] Voice input button (hold-to-record or tap-to-toggle)
- [x] Voice mode toggle (switch to full voice-to-voice)
- [x] Audio playback for TTS responses
- [x] Real-time message streaming (typing indicator, progressive display)
- [x] Language indicator

### 5.7 Records → Chat Bridge
- [x] "Ask about this document" button in Records modal
- [x] Navigate to `/chat?document={document_id}`
- [x] Chat page reads query param → loads document AI summary as system context
- [x] Triage Agent uses document data for medication_question intent responses

### 5.8 Testing
- [x] Golden-set for Triage Agent: 20+ test messages with expected intent + route
- [ ] Golden-set for Symptom Agent: 10+ symptom conversations with expected structured output
- [ ] Voice pipeline end-to-end test
- [x] Load test for WebSocket connections
- [x] Document→Chat context injection test: open chat from document → verify context available
- [x] Unit tests for A2A idempotency and retry/dead-letter transitions

### 5.9 Production Hardening Follow-ups
- [x] Remove same-session conversation state race under concurrent WebSocket writers (optimistic lock/version check or equivalent DB claim strategy)
- [ ] Enforce runtime topology for retry worker ownership as the default production model (single logical worker owner)
- [ ] Add conditional multi-worker safety for retry processing as defense in depth if multiple worker-enabled instances run (DB claim/update locking or Redis distributed lock)
- [ ] Add observability for A2A retry worker: dashboards/alerts for `retrying` and `dead_letter` counts, backlog age, and worker cycle failures

---

## Phase 6: Clinician Dashboard (Weeks 19–22)

### 6.1 Risk Radar
- [x] Risk score calculation service (adherence + symptoms + ADR flags)
- [x] `GET /api/v1/clinicians/me/dashboard` — aggregated risk data with sort/filter/pagination params
- [x] Risk Radar UI: patient cards with 🟢🟡🔴 badges (includes `unknown` for new patients)
- [x] Sortable/filterable (by risk, last activity, med count) — backend + frontend wired
- [x] Real-time updates via Supabase Realtime (subscription hook in dashboard page wired to `patchPatient`) — PR #36
- [x] Click-through to patient deep dive

### 6.2 Patient Deep Dive
- [x] Patient profile view (demographics, conditions, allergies)
- [x] Medications list with source provider (enriched via care_teams join)
- [x] Adherence chart (Recharts LineChart — 30-day daily series)
- [x] Symptom log with severity timeline (Recharts AreaChart) — snake/camel normalization at API boundary
- [x] Obligation compliance tracking (obligation count + completion rate displayed in adherence tab)
- [x] Chat transcript viewer (read-only ChatTranscript component)
- [x] SOAP note display (AI-generated, with Regenerate button + error display)

### 6.3 Summarization Agent
- [x] Aggregate patient data: adherence logs, symptoms, chats, labs
- [x] Generate SOAP note (Subjective, Objective, Assessment, Plan)
- [x] Update on-demand when clinician clicks "Generate SOAP Note"
- [x] Store in `soap_notes` table (migration 008 created)
- [x] Graph error handling: conditional edge skips store on LLM failure
- [x] Prompt injection mitigation: patient chat sanitized + delimited in prompt

### 6.4 Document Upload & Sync
- [x] Clinician document upload UI (drag-and-drop, multi-file — DocumentUploadZone, document type selector)
- [x] Set obligations form (type: diet/exercise/custom, description, frequency) — reusable after success
- [x] Bidirectional sync: clinician upload → patient sees in My Records
- [x] Patient upload → clinician review queue — dedicated clinician review queue with approve/reject workflow and deep dive review badges/actions
- [x] Trigger AI parsing on clinician uploads (backend background task)

### 6.5 Structured Document Summary UI
- [x] Parse AI summary into sections: Medications | Watch For | Follow-up Dates
- [x] Display as accordion/cards instead of plain text blob (DocumentSummary component)
- [x] Each medication links to patient adherence context (clickable link from document summary)
- [x] Clinician annotations: clinician adds notes that patient sees alongside AI summary

### 6.6 Phase 6 — Known Remaining Work & Tech Debt
- [x] Wire Supabase Realtime subscription on dashboard (hook → `patchPatient` dispatch)
- [x] Build patient upload review queue (filter by `uploaded_by_role === 'patient'`, approve/reject UI)
- [x] Split clinician document review/deep-dive document workflow into focused service + UI components (`ClinicianDocumentWorkflowService`, `PatientDocumentsPanel`)
- [x] Add integration tests for `get_dashboard_data` and `get_patient_deep_dive` async service methods
- [x] Add graph node unit tests for `gather_patient_data`, `generate_soap_note`, `store_soap_note`
- [x] Add realistic Recharts rendering tests (current tests mock all chart components to bare divs)
- [x] Enable Supabase Realtime publication for dashboard tables (`adherence_logs`, `symptom_reports`, `adr_assessments`)
- [x] Add rate limiting on SOAP note generation endpoint (expensive LLM call, 15-30s per request)

### 6.7 Session Management & Auth Hardening
- [x] **Token Refresh Before Expiry:** Implement proactive JWT refresh for logged-in users (before token expires)
  - [x] Backend: Refresh token endpoint already exists (`POST /api/v1/auth/refresh`)
  - [x] Frontend: `useAuthSessionRefresh` hook refreshes active sessions before expiry
  - [x] Edge case: User returns after browser sleep / tab backgrounded — force refresh on tab focus
  - [x] Silent refresh updates stored session without UI interruption unless refresh fails
  - [x] Add tests: verify refresh timing, focus refresh, no-op when not near expiry, and failed refresh logout
  - [x] Idle-timeout awareness reviewed; absolute inactivity timeout remains a future product/security policy decision
- [x] **Homepage & Protected Route Redirects:** Implement consistent redirect flow for production
  - [x] Unauthenticated users landing on `/dashboard`, `/patients`, etc. → redirect to `/login` + capture return path
  - [x] After successful login → redirect to captured path or default home
  - [x] Default home: Patient Portal → `/today` | Clinician Portal → `/dashboard`
  - [x] Add tests: verify redirect chain and state preservation
  - [x] Production config: Supabase redirect URLs and custom domains configured for patient + clinician portals
- [x] **Login/Logout UX:** Prevent stale session display
  - [x] Logout: Clear local session; backend refresh-token invalidation deferred because Supabase refresh expiry remains source of truth
  - [x] Login: Verify session + role before showing portal content (not just JWT presence)
  - [x] API 401 → clear session and redirect to login with "session expired" reason
  - [x] API client tests verify authenticated 401 redirect behavior

---

## Phase 7: Pharmacovigilance (Weeks 19–22, parallel with Phase 6)

### 7.1 Pharmacovigilance Agent
- [ ] DailyMed MCP server queries (drug labels, ADR profiles)
- [ ] Naranjo Algorithm calculator (automated scoring for 10 questions)
- [ ] Cross-reference symptom with all active medications (including cross-provider)
- [ ] Causality assessment using Gemini 3.0 Pro **thinking mode** (transparent reasoning chain)
- [ ] Log thinking chain for clinician review (show WHY, not just score)
- [ ] MedWatch 3500A form template (all required fields)
- [ ] Auto-populate form from patient data + ADR assessment
- [ ] De-identification pipeline (strip PHI for FDA submission)

### 7.2 Nightly Batch Job
- [ ] Cloud Scheduler cron: trigger nightly ADR scan
- [ ] Scan all patients: new symptoms since last scan
- [ ] Batch pharmacovigilance agent runs
- [ ] Generate new MedWatch drafts where appropriate

### 7.3 MedWatch Queue UI
- [ ] MedWatch inbox page (list of drafted reports)
- [ ] Draft card: risk badge, one-line summary, Naranjo score, suspect drug
- [ ] Detail view: full form preview in Syncfusion PDF Viewer
- [ ] Edit form inline
- [ ] Approve button → submit (or stage for submission)
- [ ] Dismiss button → reason required → logged for audit
- [ ] Status tracking: Draft → Reviewed → Submitted

### 7.4 Testing
- [ ] Golden-set: known drug-symptom pairs → expected Naranjo scores
- [ ] Test with synthetic patient data: patient on multiple meds reports dizziness
- [ ] Verify MedWatch form fields are correctly populated
- [ ] Test de-identification pipeline

---

## Phase 8: Communication & Scheduling (Weeks 23–26)

### 8.1 Patient Communication
- [ ] `POST /api/v1/clinicians/patients/{id}/message` — send in-app message
- [ ] `POST /api/v1/clinicians/patients/{id}/email` — send email
- [ ] `POST /api/v1/clinicians/bulk-message` — send to multiple patients
- [ ] Message appears in patient's chat as system message
- [ ] Email via Resend (templated + freeform)
- [ ] Clinician portal: message compose UI
- [ ] Patient portal: display clinician messages in chat + notification

### 8.2 Scheduling Agent
- [ ] Parse follow-up instructions from documents ("Return in 2 weeks")
- [ ] Propose appointments based on parsed instructions
- [ ] Patient confirmation via chat
- [ ] `POST /api/v1/appointments` — create appointment
- [ ] Calendar view for clinicians
- [ ] Reminder notifications (24hr and 1hr before)

### 8.3 Pre-Visit Prep Agent
- [ ] Cloud Scheduler: trigger 24hr before appointment
- [ ] Send questionnaire notification to patient
- [ ] Collect patient responses
- [ ] Generate visit prep summary: adherence, symptoms, med changes since last visit
- [ ] Display prep summary in clinician's Patient Deep Dive

### 8.4 Notification System
- [ ] Push notification service (via PWA Service Worker)
- [ ] Notification types: med reminder, missed dose, appointment, doctor message, obligation
- [ ] Quiet hours configuration
- [ ] `GET /api/v1/notifications` — list patient notifications
- [ ] Mark as read
- [ ] Notification bell UI in both portals

---

## Phase 9: Care Continuity (Weeks 27–30)

### 9.1 Medical Timeline
- [ ] Unified patient timeline: meds, symptoms, docs, appointments, notes
- [ ] Chronological view with filters (by type, by provider, by date range)
- [ ] Timeline UI component

### 9.2 Provider Transfer
- [ ] Transfer care team relationship (mark old as `transferred`, create new)
- [ ] Auto-generate Patient Handoff Summary (all active meds, conditions, adherence trends, key events)
- [ ] New provider sees handoff summary on first access

### 9.3 FHIR Export
- [ ] Convert patient data to FHIR Bundle (JSON)
- [ ] Export as downloadable PDF (formatted summary)
- [ ] Export UI in clinician portal

---

## Phase 10: Integration & QA (Weeks 31–33)

### 10.1 End-to-End Testing
- [ ] Full patient flow: signup → upload → feed → chat → voice → symptom
- [ ] Full clinician flow: login → dashboard → deep dive → MedWatch → message
- [ ] Cross-portal flow: patient reports symptom → clinician sees alert → messages patient
- [ ] Provider transfer flow: old doc → new doc handoff
- [ ] Playwright E2E test suite for all critical paths

### 10.2 Performance
- [ ] API response time audit (target: < 500ms for CRUD, < 3s for AI operations)
- [ ] Frontend bundle size optimization
- [ ] Lighthouse audit for both portals (target: > 90 performance)
- [ ] WebSocket connection stability testing
- [ ] LLM response latency measurement and optimization

### 10.3 Security Audit
- [ ] RLS policy review: verify no data leakage across patients/clinicians
- [/] Auth flow review: verify MFA, token expiry, session management
  - [x] Local auth regression verification: clinic-code gate, clinician login, MFA setup/login, protected-route access
  - [ ] Token/session expiry behavior validated end to end with explicit acceptance criteria
    - [ ] Access token expires at configured TTL and protected APIs return 401 after the expiry boundary
    - [ ] Refresh session expires at configured absolute timeout and requires re-authentication after timeout
    - [ ] Refresh token rotation verified: refresh issues a new refresh token and invalidates the old token
    - [ ] Reuse of an invalidated or rotated refresh token is rejected and logged
    - [ ] Client expiry UX verified: silent refresh while valid, forced login when expired
  - [ ] Deployed-environment parity validated
- [ ] Input validation: verify all user inputs are sanitized
- [ ] File upload validation: verify type/size restrictions
- [ ] OWASP Top 10 review
- [ ] Dependency vulnerability scan (`pip audit`, `npm audit`)

### 10.4 Accessibility
- [ ] Keyboard navigation for all interactive elements
- [ ] Screen reader compatibility (aria labels, roles)
- [ ] Color contrast compliance (WCAG AA)
- [ ] Font size scaling for elderly users

---

## Phase 11: Demo Prep (Weeks 34–35)

### 11.1 Synthetic Data
- [ ] Create realistic patient profiles (3-5 patients, diverse demographics)
- [ ] Generate synthetic medical documents (discharge summaries, lab reports, prescriptions)
- [ ] Pre-seed: medications, conditions, adherence history, symptom reports
- [ ] Pre-seed: clinician profiles (2 clinics, 3 doctors)
- [ ] Pre-seed: care_team relationships (multi-provider scenarios)
- [ ] Pre-seed: MedWatch drafts at various statuses
- [ ] Seeding script: `backend/app/db/seed/demo_data.py`

### 11.2 Demo Script
- [ ] Write minute-by-minute demo walkthrough
- [ ] Identify the "wow moments" for each feature
- [ ] Practice: patient onboarding flow
- [ ] Practice: voice symptom reporting (bilingual)
- [ ] Practice: clinician dashboard → MedWatch
- [ ] Practice: care continuity / provider handoff
- [ ] Backup plan: pre-recorded video of each flow in case of live failure

### 11.3 Presentation
- [ ] Create slide deck: problem → solution → demo → architecture → impact
- [ ] Architecture diagram (polished version)
- [ ] Metrics: response times, accuracy scores, adherence improvement potential
- [ ] Future roadmap slide (EHR integration, telehealth, FDA API submission)

### 11.4 Deployment Hardening
- [x] Production environment variables verified
- [x] DNS and custom domains configured (Vercel apps, Resend sending domain, Supabase auth URLs, Cloud Run custom domain)
- [x] SSL certificates confirmed (`api.mediagent.live`, `app.mediagent.live`, `clinician.mediagent.live`, `mail.mediagent.live`)
- [ ] Cloud Run auto-scaling tested
- [ ] Monitoring alerts configured
- [ ] Fallback responses for LLM rate limits
- [ ] Cache layer for common LLM responses (demo queries)

---

## Phase 12: Expo (Week 36) 🎉

- [ ] Final deployment check (all services green)
- [ ] Demo dry run (full walkthrough, time it)
- [ ] Expo presentation
- [ ] Collect feedback
- [ ] Post-expo retrospective
