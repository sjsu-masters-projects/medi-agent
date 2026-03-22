# MediAgent — Project Context

> **Read this first.** This is the single source of truth for what MediAgent is, what we're building, and all decisions made. Every team member and AI coding assistant should have context from this file.

---

## What Is MediAgent?

A dual-portal healthcare platform powered by multi-agent AI:
- **Patient Portal (PWA):** Bilingual health companion — parses medical documents, creates medication & obligation schedules, explains reports in plain language, voice-to-voice conversations, agentic appointment management.
- **Clinician Portal (PWA):** Real-time patient monitoring, automated pharmacovigilance (ADR detection → FDA MedWatch reporting), bidirectional document sync, patient communication, care continuity across providers.

## Why Does It Matter?

| Problem | Impact |
|---------|--------|
| Patients can't understand medical documents | 50% medication non-adherence |
| ADR reporting is manual (30 min/form) | 95% of ADRs go unreported to FDA |
| Records don't transfer between providers | Fragmented care, missed drug interactions |

## Startup Thesis

B2B2C SaaS — sold to clinics/health systems, deployed to their patients.

---

## Key Architecture Decisions (Decision Log)

| # | Decision | Date | Rationale |
|---|----------|------|-----------|
| D1 | **PWA for both portals** (not native mobile) | 2026-03-02 | Camera, mic, push notifications, installable — covers all needs. No App Store approval. One codebase per portal. |
| D2 | **Multi-provider care model** (care_teams junction) | 2026-03-02 | Patients see multiple doctors. Single profile, unified record, multiple care relationships. Default-share visibility with restrict option. |
| D3 | **Gemini 3.0 Flash/Pro as primary LLMs** | 2026-03-02 | Free tier through Google Cloud. Flash for speed, Pro for complex reasoning (pharmacovigilance). |
| D4 | **Deepgram for STT/TTS** | 2026-03-02 | Team has credits. Excellent medical vocab. Streaming support. |
| D5 | **Supabase as all-in-one data platform** | 2026-03-02 | PostgreSQL + pgvector + Auth + Storage + Realtime in one platform. Free tier sufficient for dev. |
| D6 | **Syncfusion PDF Viewer from day one** | 2026-03-02 | Free community license. Viewing + annotation + form filling + redaction. Upgrade path to Apryse if academic license available. |
| D7 | **Next.js + Redux + TailwindCSS** | 2026-03-02 | SSR, PWA support, strong ecosystem. Redux for complex state. Tailwind for rapid styling. |
| D8 | **LangGraph for agent orchestration** | 2026-03-02 | Stateful multi-agent workflows, conditional routing, retries, human-in-the-loop. |
| D9 | **Monorepo** | 2026-03-02 | Team of 4, shared types/utils, easier CI/CD, single PR per feature. |
| D10 | **FHIR-aligned data model** | 2026-03-02 | Interoperability. Data exportable as FHIR Bundles. Major selling point for startup viability. |
| D11 | **In-app messaging + email only** (no SMS for now) | 2026-03-02 | Simplicity. Email via Resend (free tier). SMS can be added later with Twilio. |
| D12 | **MCP (Model Context Protocol) for tool access** | 2026-03-03 | Agents access tools (DailyMed, RxNorm, Supabase, Deepgram) via MCP servers. Vendor-independent — swap LLM providers without changing tools. |
| D13 | **A2A Protocol for inter-agent communication** | 2026-03-03 | Expose Agent Cards (`.well-known/agent.json`). Internal demo: Triage→Pharma via A2A. Future-proofs for EHR/pharmacy integration. NOT connecting to real external hospital agents — our own agents speak A2A to each other. |
| D14 | **Gemini 3.0 Pro thinking mode for pharmacovigilance** | 2026-03-03 | Transparent chain-of-thought reasoning for Naranjo scoring. Clinicians see WHY the AI scored an ADR, not just the score. |
| D15 | **Explore Gemini Multimodal Live API** | 2026-03-03 | Could collapse STT→LLM→TTS into one WebSocket. Deepgram is primary pipeline; Gemini Live is stretch goal. |
| D16 | **Evaluate MedGemma for medical tasks** | 2026-03-03 | Google's open healthcare model (based on Gemma 3). Benchmark against Gemini 3.0 Flash/Pro for: doc parsing, symptom triage, FHIR extraction. Use if quality is better for specific tasks. |
| D17 | **Hybrid model routing: MedGemma 27B + Gemini Flash Lite + Pro** | 2026-03-21 | Benchmarked 5 clinical scenarios (4 runs). MedGemma wins clinical extraction (92% completeness, Naranjo 8-9). Flash Lite wins patient-facing UX (2.8s, 96%). Pro wins deep reasoning (SOAP/MedWatch). See `backend/reports/benchmark_27b_20260321_192905.md`. |
| D18 | **Gemma chat template required for MedGemma vLLM endpoints** | 2026-03-21 | MedGemma-it expects `<start_of_turn>user\n...` format. Without it, model does text completion instead of instruction following. |

> **Adding a decision?** Append to this table with date and rationale. Never delete entries — only mark as superseded if changed.

---

## User Personas

| Persona | Who | Core Need |
|---------|-----|-----------|
| **Sarah** | 65, Spanish-speaking, diabetes + hypertension, sees multiple doctors | Understand her health, stay on track |
| **Dr. Smith** | PCP, 200+ patients, City Health | Spot problems early, reduce ADR paperwork |
| **Dr. Patel** | Cardiologist, Heart Center, receives referrals | Get up to speed with complete patient context |

---

## Tech Stack (Final)

| Layer | Technology |
|-------|----------|
| Both Portals | Next.js (PWA) + Redux + TailwindCSS |
| Document Viewer | Syncfusion PDF Viewer |
| Backend API | Python FastAPI |
| AI Orchestration | LangGraph |
| Agent Tools | MCP Servers (standardized tool access) |
| Agent Communication | A2A Protocol (inter-agent messaging) |
| Clinical LLM | MedGemma 27B-it (Vertex AI — document parsing, ADR, interactions, triage) |
| Patient-facing LLM | Gemini 3.1 Flash Lite Preview (chat, voice, explanations) |
| Reasoning LLM | Gemini 3.1 Pro Preview (SOAP notes, MedWatch, batch analysis) |
| STT | Deepgram Nova-2 |
| TTS | Deepgram Aura |
| Voice (explore) | Gemini Multimodal Live API (stretch goal) |
| DB + Vectors | Supabase (PostgreSQL + pgvector) |
| Auth | Supabase Auth |
| Storage | Supabase Storage |
| Realtime | Supabase Realtime |
| Drug APIs | DailyMed + RxNorm (NLM) |
| Email | Resend |
| Backend Host | Google Cloud Run |
| Frontend Host | Vercel |
| CI/CD | GitHub Actions |

---

## Feature Overview

### Patient Portal (PWA)

| ID | Feature | Priority |
|----|---------|----------|
| F-P1 | Onboarding (magic link, health profile, clinic join) | P0 |
| F-P2 | Document Upload & AI Parsing (all doc types → FHIR) | P0 |
| F-P3 | "Explain This to Me" (plain-language, bilingual) | P0 |
| F-P4 | "Today" Feed (meds + obligations, aggregated across providers) | P0 |
| F-P5 | Health Companion Chat (text + voice, bilingual, symptom triage) | P0 |
| F-P6 | Voice-to-Voice Mode (hands-free, STT→LLM→TTS) | P0 |
| F-P7 | Agentic Scheduling (AI-suggested appointments) | P1 |
| F-P8 | Symptom Timeline (visual, pattern detection) | P1 |
| F-P9 | Notifications (push, configurable) | P0 |

### Clinician Portal (PWA)

| ID | Feature | Priority |
|----|---------|----------|
| F-C1 | Auth & Clinic Setup (MFA, roles) | P0 |
| F-C2 | Risk Radar Dashboard (traffic light, real-time) | P0 |
| F-C3 | Patient Deep Dive (charts, SOAP notes) | P0 |
| F-C4 | Document Upload & Sync (bidirectional) | P0 |
| F-C5 | Patient Communication (in-app + email) | P0 |
| F-C6 | Scheduling & Follow-ups | P1 |
| F-C7 | MedWatch Queue (auto-drafted FDA 3500A) | P0 |
| F-C8 | Care Continuity (timeline, handoff summary) | P1 |
| F-C9 | Analytics | P2 |

### AI Agents

| Agent | Trigger | LLM |
|-------|---------|-----|
| Ingestion | Document upload | MedGemma 27B (extraction) + Flash Lite (summary) |
| Triage | Chat message | MedGemma 27B (classification) + Flash Lite (response) |
| Symptom Analysis | Routed from Triage | Flash Lite (follow-up) + MedGemma 27B (assessment) |
| Pharmacovigilance | After symptom / nightly batch | MedGemma 27B (ADR) + Pro (MedWatch) |
| Pre-Visit Prep | 24hr before appointment | Flash Lite |
| Summarization / SOAP | On-demand / daily | Pro |
| Scheduling | Triage / proactive | Flash Lite |

---

## Links

- **Full PRD:** See `implementation_plan.md` in the brain directory
- **Coding Standards:** `.agent/CODING_STANDARDS.md`
- **Architecture:** `.agent/ARCHITECTURE.md`
- **Design System:** `.agent/DESIGN_SYSTEM.md`
- **Task Breakdown:** `.agent/TASKS.md`
- **Team & Process:** `.agent/TEAM.md`
