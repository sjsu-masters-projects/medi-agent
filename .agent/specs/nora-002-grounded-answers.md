# NORA-002 — Grounded, plain-language answers from Nora

**Status:** In progress · **Owner:** Rajeev · **Branch:** `fix/nora-follow-up-turns` (PR #146)

## Goal

Nora helps patients understand their medications, conditions and documents in plain
American English or Mexican Spanish, by text or voice, grounded in their own record and
in current public sources, with citations. She is not a clinician: no diagnosis, no dose
changes, and the deterministic safety floor still runs first.

## Decisions (requester, 2026-10-10)

- Sources: **MedlinePlus Connect** and the MedlinePlus topic search (plain-language, English
  and Spanish), **DailyMed** (official label sections), **RxNorm** (identity).
- Refresh: **weekly**.
- Chats: a **new conversation each day** and a **New chat** button; patients can open
  **older conversations**.
- One PR. Safety-relevant prompt changes are reviewed by a separate reviewer agent.

## Design

### Knowledge (`health_knowledge`, migration 051)

One row per subject, source and locale: medication (keyed by RxNorm ingredient RxCUI) or
condition (normalised name). Stores title, URL, plain summary or label sections, the
source's own version and date (DailyMed SPL version and published date), and when we
fetched and last checked it. Public reference text only; no patient data.

- RxNorm resolves a name ("Metformina 500 mg") to an ingredient with exact, then
  approximate matching.
- DailyMed: the newest single-ingredient label for that ingredient; sections kept include
  indications, dosage, warnings, adverse reactions, drug interactions, contraindications and
  patient counselling.
- MedlinePlus Connect by RxCUI for medications and the topic search for conditions, in both
  languages.
- On a miss, a tool call fetches and caches with a short timeout. The weekly job re-checks
  every active medication and documented condition, refreshing only what changed.

### Nora's tools (coordinator)

- `get_medication_information(medication_name)`: plain summary in the patient's language
  plus key label sections, with sources and dates.
- `get_condition_information(condition_name)`: plain summary in the patient's language.
- `get_document_facts()`: the active document's extracted facts with source excerpts and
  pages.
- `search_my_records(query)`: the patient's own facts and summaries matching a query.

All patient-scoped tools take the patient from session state, never from the model. The
responder cites what it used ("Source: MedlinePlus, updated …"). The router's old per-turn
drug retrieval, whose output never reached the model, is removed.

### Conversations

Messages carry a `session_id`. The patient app opens today's conversation by default and
"New chat" starts another; a list shows earlier conversations, which can be reopened. The
model context comes from the stored messages of the current conversation (recap of recent
turns plus the rolling summary), so a backend restart loses nothing and long conversations
stay bounded.

### Documents

The explanation prompt is rewritten for plain language (what it is, what it says, what to
ask the care team), paraphrasing rather than quoting and translating; the Records disclaimer
follows the explanation language.

### Voice

One persona in both languages: Aura-2 Asteria (English) and Estrella (Mexican Spanish),
both female.

### Safety changes (reviewed by a separate agent)

Symptom-reply escalation for severity 9–10 or a named danger sign; SOAP assessment and plan
framed as considerations for clinician review; extraction document text fenced as data.

## Acceptance

1. "What is metformin for?" in English and Spanish returns a plain answer citing MedlinePlus
   with a date; label-only facts cite DailyMed.
2. "What does my hydration document say?" from Records answers from that document's facts
   with a page reference.
3. A new day or New chat starts a new conversation; earlier ones are listed and reopen with
   their messages; a backend restart keeps context.
4. The weekly job refreshes changed sources and records a run.
5. Safety review findings resolved or recorded; tests, lint, types and live checks pass.
