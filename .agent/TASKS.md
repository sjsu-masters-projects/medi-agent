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
- [ ] Test RLS policies with different user roles — needs real auth users

### 1.3 CI/CD
- [ ] Set up GitHub Actions: lint on PR (Ruff + ESLint)
- [ ] Set up GitHub Actions: test on PR (pytest + Vitest)
- [ ] Set up GitHub Actions: build check on PR
- [ ] Set up GitHub Actions: deploy backend to Cloud Run on merge to main
- [ ] Set up GitHub Actions: deploy portals to Vercel on merge to main
- [ ] Set up Husky pre-commit hooks (lint + format)

### 1.4 Cloud Infrastructure
- [ ] Set up Google Cloud project
- [ ] Configure Cloud Run for backend
- [ ] Configure Cloud Scheduler for cron jobs
- [ ] Set up Vercel projects (patient-portal, clinician-portal)
- [ ] Configure environment variables in all platforms
- [ ] Set up Sentry for error monitoring

### 1.5 External Service Setup
- [ ] Get Gemini API key (Google AI Studio / Vertex AI)
- [ ] Get Deepgram API key and configure SDK
- [ ] Set up Resend for email
- [ ] Test DailyMed API access  
- [ ] Test RxNorm API access
- [ ] Obtain Syncfusion Community License key
- [ ] Download and test MedGemma model access (Hugging Face / Vertex AI)

### 1.6 MCP Server Scaffolding
- [ ] Create MCP server base structure (`backend/app/mcp/`)
- [ ] Implement `mcp-supabase` server (patient data queries)
- [ ] Implement `mcp-dailymed` server (drug labels, ADR profiles)
- [ ] Implement `mcp-rxnorm` server (drug normalization)
- [ ] Implement `mcp-deepgram` server (STT/TTS access)
- [ ] Test MCP servers with standalone MCP client

### 1.7 A2A Protocol Setup
- [ ] Create Agent Card JSON schema for each agent
- [ ] Expose `/.well-known/agent.json` endpoint on backend
- [ ] Implement A2A task management (submit, status, artifacts)
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
- [x] `POST /api/v1/auth/login` — email/password login
- [x] `POST /api/v1/auth/refresh` — token refresh
- [x] `POST /api/v1/auth/password-reset` — password reset email
- [x] `GET /api/v1/auth/me` — current user from JWT
- [x] JWT middleware for route protection
- [x] Role-based access control (patient vs clinician)
- [ ] Write auth integration tests

### 2.3 Patient API
- [x] `GET /api/v1/patients/me` — get own profile
- [x] `PUT /api/v1/patients/me` — update profile
- [x] `GET /api/v1/patients/me/care-team` — list patient's providers
- [x] `POST /api/v1/patients/me/care-team/join` — join clinic via code
- [ ] Write patient API tests

### 2.4 Clinician API
- [x] `GET /api/v1/clinicians/me` — get own profile
- [x] `GET /api/v1/clinicians/me/patients` — list assigned patients
- [x] `GET /api/v1/clinicians/me/patients/{id}` — get patient detail
- [x] `POST /api/v1/clinicians/me/invite-code` — generate patient invite code
- [ ] Write clinician API tests

### 2.5 Document API
- [x] `POST /api/v1/documents/` — register uploaded document (metadata-only)
- [x] `GET /api/v1/documents` — list patient's documents
- [x] `GET /api/v1/documents/{id}` — get document detail + signed URL
- [x] `POST /api/v1/documents/{id}/explain` — 501 placeholder (Phase 4)
- [x] File validation + signed URL generation
- [ ] Write document API tests

### 2.6 Medications & Obligations API
- [x] `GET /api/v1/medications` — list patient's active medications
- [x] `POST /api/v1/medications` — create medication
- [x] `PUT /api/v1/medications/{id}` — update medication
- [x] `GET /api/v1/obligations` — list patient's obligations
- [x] `POST /api/v1/obligations` — create obligation
- [x] `POST /api/v1/adherence` — log medication taken / obligation completed
- [x] `GET /api/v1/adherence/stats` — adherence score + streak calculation
- [ ] Write medication and adherence tests

### 2.7 Today Feed API
- [ ] `GET /api/v1/feed/today` — aggregated daily tasks (meds + obligations from all providers)
- [ ] Include source provider info for each task
- [ ] Calculate which tasks are pending/completed/missed
- [ ] Write feed tests

---

## Phase 3: Frontend Core (Weeks 5–8, parallel with Phase 2)

### 3.1 Design System
- [ ] Set up TailwindCSS theme (colors, typography, spacing)
- [ ] Create base UI components: Button, Input, Card, Badge, Modal, Dropdown
- [ ] Create layout components: AppShell, Sidebar, TopBar, BottomNav
- [ ] Create loading states (skeleton screens)
- [ ] Create empty states
- [ ] Create error states
- [ ] Make all components responsive (mobile-first for patient, desktop-first for clinician)

### 3.2 Patient Portal — Auth
- [ ] Sign-up page (magic link flow)
- [ ] Onboarding flow (name, DOB, language, allergies)
- [ ] Join clinic (enter code or use invite link)
- [ ] Auth state management in Redux
- [ ] Protected route wrapper

### 3.3 Patient Portal — Today Feed
- [ ] Today Feed page layout
- [ ] Medication task card component (name, dosage, time, instructions)
- [ ] Obligation task card component (type badge, description)
- [ ] Provider grouping (show which doctor set each task)
- [ ] Tap to mark done (optimistic update + API call)
- [ ] Missed task visual indicator
- [ ] Adherence score display (percentage + streak)

### 3.4 Patient Portal — My Records
- [ ] Document list view
- [ ] Document upload button (file picker + camera capture)
- [ ] Upload progress indicator
- [ ] Research and configure Syncfusion PDF viewer integration
- [ ] Syncfusion PDF viewer UI component (in-app viewing)
- [ ] "Explain This to Me" button + summary display
- [ ] Language selector for explanation

### 3.5 Clinician Portal — Auth
- [ ] Login page (email + password)
- [ ] MFA setup flow
- [ ] Clinic setup page (name, NPI)
- [ ] Role management (Admin, Provider, Nurse)
- [ ] Auth state in Redux
- [ ] Protected routes

### 3.6 Clinician Portal — Dashboard Shell
- [ ] Dashboard layout (sidebar + content area)
- [ ] Navigation (Dashboard, Patients, MedWatch, Settings)
- [ ] Patient list table component
- [ ] Risk badge component (🟢🟡🔴)
- [ ] Responsive layout

---

## Phase 4: Ingestion Agent (Weeks 9–12)

### 4.1 Agent Core
- [ ] Create BaseAgent abstract class (SOLID compliant)
- [ ] Create Gemini client service (with retry, timeout, structured output)
- [ ] Create MedGemma client service (for evaluation comparisons)
- [ ] Create LangGraph state schema for ingestion workflow
- [ ] Implement Ingestion Agent graph:
  - [ ] Node: receive document
  - [ ] Node: call Gemini vision to extract structured data
  - [ ] Node: validate extracted data against FHIR schemas
  - [ ] Node: normalize medications via RxNorm MCP server
  - [ ] Node: save to database (via Supabase MCP server)
  - [ ] Node: generate plain-language summary
  - [ ] Node: create Today Feed tasks from medications + follow-up instructions

### 4.2 Tools
- [ ] FHIR Resource Builder (MedicationRequest, Condition, AllergyIntolerance, Appointment)
- [ ] RxNorm API client (brand → generic → RxCUI normalization)
- [ ] Medication normalizer (parse dosage strings, frequency extraction)

### 4.3 MedGemma Evaluation
- [ ] Create 20 medical test cases (doc parsing, FHIR extraction, symptom classification)
- [ ] Run identical tests through Gemini Flash vs MedGemma
- [ ] Compare accuracy: FHIR fields, ADR detection, clinical summary quality
- [ ] Decision: adopt MedGemma for specific agents if it wins
- [ ] Document results in PROJECT.md Decision Log

### 4.4 Testing
- [ ] Create synthetic test documents (discharge summary, lab report, prescription, diagnostic report)
- [ ] Golden-set evaluation: expected parsing output for each test document
- [ ] Unit tests for FHIR builder and normalizer
- [ ] Integration test: upload → parse → database → Today Feed

### 4.4 Patient Portal Integration
- [ ] Wire up document upload → API → Ingestion Agent → DB
- [ ] Today Feed auto-populates after document parsing
- [ ] "Explain This" calls AI and displays summary
- [ ] Handle parsing errors gracefully (show status, allow retry)

---

## Phase 5: Chat & Voice — Triage + Symptom Agents (Weeks 13–16)

### 5.1 Chat Backend
- [ ] WebSocket endpoint `/ws/chat/{patient_id}`
- [ ] Message persistence to `chat_messages` table
- [ ] Conversation history retrieval (sliding window + summary)
- [ ] Patient context injection (active meds, recent symptoms, conditions)

### 5.2 Triage Agent
- [ ] Intent classification (symptom, medication_question, schedule, general, urgent)
- [ ] Multi-turn conversation state management
- [ ] Routing logic: intent → appropriate sub-agent/tool
- [ ] Safety rails: detect urgent/emergency → escalation response + clinician notification
- [ ] Bilingual response generation (auto-detect language, respond in same)

### 5.3 Symptom Analysis Agent
- [ ] Follow-up question generation (severity, timing, related meds, recent changes)
- [ ] Structured symptom report creation (symptom, severity 1-10, onset, related_med)
- [ ] Save to `symptom_reports` table
- [ ] Delegate to Pharmacovigilance Agent via A2A protocol (not direct function call)
- [ ] Verify A2A task lifecycle: submitted → working → completed

### 5.4 Medical RAG
- [ ] Populate pgvector with drug information (from DailyMed)
- [ ] Embedding generation for medication knowledge base
- [ ] RAG retrieval pipeline: query → embed → similarity search → LLM response
- [ ] Citation inclusion (source of information)

### 5.5 Voice Integration
- [ ] Deepgram STT client (streaming WebSocket)
- [ ] Deepgram TTS client (text → audio stream)
- [ ] Voice-to-voice pipeline: mic → STT → Triage Agent → response → TTS → speaker
- [ ] Language detection from audio
- [ ] Audio message storage (Supabase Storage, URL in chat_messages)

### 5.6 Patient Portal — Chat UI
- [ ] Chat page layout (WhatsApp-style)
- [ ] Message bubble components (user, assistant)
- [ ] Text input with send button
- [ ] Voice input button (hold-to-record or tap-to-toggle)
- [ ] Voice mode toggle (switch to full voice-to-voice)
- [ ] Audio playback for TTS responses
- [ ] Real-time message streaming (typing indicator, progressive display)
- [ ] Language indicator

### 5.7 Testing
- [ ] Golden-set for Triage Agent: 20+ test messages with expected intent + route
- [ ] Golden-set for Symptom Agent: 10+ symptom conversations with expected structured output
- [ ] Voice pipeline end-to-end test
- [ ] Load test for WebSocket connections

---

## Phase 6: Clinician Dashboard (Weeks 19–22)

### 6.1 Risk Radar
- [ ] Risk score calculation service (adherence + symptoms + ADR flags)
- [ ] `GET /api/v1/clinicians/me/dashboard` — aggregated risk data
- [ ] Risk Radar UI: patient cards with 🟢🟡🔴 badges
- [ ] Sortable/filterable (by risk, last activity, med count)
- [ ] Real-time updates via Supabase Realtime
- [ ] Click-through to patient deep dive

### 6.2 Patient Deep Dive
- [ ] Patient profile view (demographics, conditions, allergies)
- [ ] Medications list with source provider
- [ ] Adherence chart (daily/weekly/monthly — use Recharts or Nivo)
- [ ] Symptom log with severity timeline
- [ ] Obligation compliance tracking
- [ ] Chat transcript viewer (read-only)
- [ ] SOAP note display (AI-generated)

### 6.3 Summarization Agent
- [ ] Aggregate patient data: adherence logs, symptoms, chats, labs
- [ ] Generate SOAP note (Subjective, Objective, Assessment, Plan)
- [ ] Update on-demand when clinician views patient
- [ ] Store in `patients.soap_note` (or separate table)

### 6.4 Document Upload & Sync
- [ ] Clinician document upload UI (drag-and-drop, multi-file)
- [ ] Set obligations form (type: diet/exercise/custom, description, frequency)
- [ ] Bidirectional sync: clinician upload → patient sees in My Records
- [ ] Patient upload → clinician review queue
- [ ] Trigger AI parsing on clinician uploads

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
- [ ] Auth flow review: verify MFA, token expiry, session management
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
- [ ] Production environment variables verified
- [ ] DNS and custom domains configured
- [ ] SSL certificates confirmed
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
