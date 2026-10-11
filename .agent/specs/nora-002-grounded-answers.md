# NORA-002 — Grounded, plain-language answers from Nora

**Status:** Done — merged in #147 (`4c9de30`); deployed chat recheck October 11 (docs/deployed-recheck-2026-10-11.md); voice on a phone is VOI-001 · **Owner:** Rajeev · **Refresh:** Cloud Run Job
`mediagent-health-knowledge-refresh`, trigger `mediagent-health-knowledge-refresh-weekly`
(Sundays 03:00 America/Los_Angeles)

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
- **Language (2026-10-11):** Nora answers in the language the patient writes or speaks,
  English or Spanish, whatever the app is set to. The language setting controls the
  app's screens only. Speech is transcribed in multilingual mode for the same reason.

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
- Condition topics (fix, 2026-10-11; the weekly seed found 13 of 29 lookups missing or
  matched poorly):
  - The English index is searched first with the name as stored, the Spanish index only
    when English has no match (records can hold Spanish names such as "diabetes tipo 2").
  - Ten hits are scored by title and alternate titles: the same words, then every word
    asked about, then a broader topic named in at least half the name ("Cholesterol" for
    "high cholesterol"). A topic sharing only a word is never accepted, and a general topic
    beats one for a narrower audience or a how-to ("High Blood Pressure" over "How to
    Prevent High Blood Pressure").
  - With no acceptable general topic, the search is retried once without a short,
    documented list of severity, course, side and body-site qualifiers ("mild persistent
    asthma" → "asthma", "osteoarthritis of the knee" → "osteoarthritis").
  - The other language is MedlinePlus's own twin page at the same slug (`/<slug>.html` and
    `/spanish/<slug>.html`), never a translation. It is read from that language's index by
    URL, searching with the topic's title and then with the twin page's `<title>`, read from
    the page head only. No twin is `not_found`; English text is never stored as Spanish.
  - At most about seven requests per subject and language, within the existing budgets.
- On a miss, a tool call fetches and caches with a short timeout. The weekly job re-checks
  every cached subject last checked more than six days ago and seeds active medications and
  documented conditions with no cached text (conditions in en-US and es-MX), refreshing
  only what changed.

### Retrieval pipeline and its checks

Each stage has a check, and every failure has a defined outcome. A failure never becomes a
guess.

| # | Stage | Check | On failure |
| --- | --- | --- | --- |
| 1 | **Decide to retrieve** (coordinator) | Retrieve only for a medication, condition or document question. A symptom or side-effect message is triaged first; the safety floor runs before any model. | Without a retrieval Nora answers from the record only, or says she does not have the information. |
| 2 | **Resolve the subject** | Medication: match the patient's own active medications first (exact, then fuzzy name match). Otherwise RxNorm exact match, then approximate match, which is accepted only if the matched name shares a word (similarity ≥ 0.8) with what was asked ("hydration" must not become chloral hydrate). Combination products currently report no match (see the safety review below). Condition: patient's conditions first, then the best-scoring MedlinePlus topic by title and alternate titles (see Knowledge), and its twin page for the other language. | `not_found`: Nora says she could not find reliable information for that name and asks which medication was meant. |
| 3 | **Fetch from sources** | NLM HTTPS hosts only (allowlist). 6 s per request and 8 s total inline. Responses are size-capped, HTML is stripped, and the shape is validated. A DailyMed label must be single-ingredient, with the ingredient named in its title. Label sections are chosen by LOINC code. | A network or timeout error is `unavailable`, never cached as "not found". |
| 4 | **Cache and freshness** | Rows hold `checked_at`, the source version and date, and a content hash. A row checked within 7 days is served from the cache. A miss (`not_found`) is retried after 7 days. A source that does not answer leaves the old row in place. | If a cached row is older than 30 days and the source is down, it is served with its "as of" date and marked stale. |
| 5 | **Return to the model** | Each tool result shows provenance first: source, title, URL, date, language and `on_patient_list`. Excerpts are bounded (about 1,800 characters per section) and fenced as reference data, never instructions. **Label dosage sections are never returned**: a label's dose ranges are not this patient's prescription. | — |
| 6 | **Write the reply** (responder) | General reference is kept apart from the patient's own record ("in general…" versus "your list says…"). When they conflict, the record and care team win. The reply never gives a dose, start or stop advice. A known side effect is never presented as "nothing to worry about"; it routes to the care team, and to 911 when there are danger signs. In Spanish, an English-only source is explained in Spanish and the source is named as English. | — |
| 7 | **Check after generation** (deterministic, server-side) | The source line is attached by the server from the tool results that were actually used, never trusted to the model. A reply that cites a source no tool returned is stripped of that citation. Numbers that look like doses in the reply must appear in the patient record or the tool result; otherwise the reply is flagged in telemetry, and later blocked once measured. | — |
| 8 | **Observe** | Logged per turn: retrieval outcome (`found`, `cache`, `stale`, `not_found` or `unavailable`), latency and source. No medication names together with a patient identifier. | — |

**Language:** a MedlinePlus Spanish page when one exists, otherwise English explained in
Spanish. DailyMed exists only in English.

**Retired:** the pgvector drug chunk retrieval (`drug_knowledge_chunks`). It was queried on
every turn and its result never reached the model. The table is left in place and dropped
in a later migration once nothing reads it.

### Evaluation (before merge)

- Unit tests run on recorded source responses (no network in CI). They cover:
  - resolution accepts and rejects (brand name, Spanish name, dose text, non-drug word,
    combination product)
  - label choice
  - section parsing
  - failure outcomes (`unavailable` is never cached)
  - freshness
  - patient scoping
  - the server source line
- A golden set of about 30 English and Spanish questions, each with the expected source
  and the behaviors that must not happen:
  - what a drug is for
  - side effects
  - interactions with the patient's other medications
  - a drug that is not on the patient's list
  - a misspelled name
  - a non-drug word
  - a condition explanation
  - a document question
  - a danger-sign side effect, which must escalate
  - a dose-change request, which must refuse and route to the care team
- A live check script runs the same set against the real services and Nora.

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
4. The weekly job refreshes changed sources and records a run. Scheduled runs before the
   OPS-003 fix checked 0 subjects (a seven-day due cutoff skipped the previous run's rows
   and conditions were never seeded); OPS-003 moved the due cutoff to six days and seeds
   documented conditions.
5. Safety review findings resolved or recorded; tests, lint, types and live checks pass.

## Safety review and live evidence (2026-10-11)

A separate reviewer agent read the full diff against this plan. Its two blockers and ten
should-fix findings were addressed in the same branch:

- **Name matching.** It accepted look-alike and salt names (losartan/valsartan, "...
  hydrochloride"). List membership is now decided by RxNorm ingredient.
- **Combination products.** These resolved to one ingredient; they now report no match.
- **Condition topics.** The top search hit was not checked against the question; it now
  must match.
- **Malformed responses.** A badly formed source response could end a turn; it now
  counts as an outage.
- **Doses in reference text.** Medication Guide text could carry doses into a reply. That
  section and any sentence stating an amount are now removed.
- **Unreviewed items and side effects.** The reply prompt now covers both.
- **Session key.** Runtime sessions are now keyed by patient as well as conversation.
- **Excerpts.** Excerpts from other documents could appear; excerpts now come only from
  the selected document.
- **911 wording.** The new 911 sentence could be skipped or claim the care team was told;
  it is now always added and makes no such claim.
- **Evaluation fixture.** The question set's location broke the provider-evaluation
  loader; it has moved.

Recorded rather than changed:

- Severity 9–10 sets urgency to `urgent` plus the 911 sentence and a care-team alert. The
  `emergency` label stays reserved for the deterministic floor.
- Combination products are not yet covered.
- Label XML is parsed with the standard library from fixed NLM hosts, with a 3 MB
  response limit. `defusedxml` is not a dependency.

**Live check.** `backend/scripts/check_nora_answers.py` ran on the synthetic patient against the
real services:

- 18 of 22 passed on the first run. Three answers had no lookup and so no source, and the
  Spanish document search was accent-sensitive.
- After the fixes, 22 of 22 passed on two runs.
- Turns take 3–8 s, and up to 13 s when the symptom worker runs.

**Speech round trip.**

- With the language pinned to English, Spanish speech came back as an empty transcript;
  multilingual mode transcribed both languages.
- One synthetic phrase ("de la presión") was misheard in both multilingual and
  Spanish-only modes. That is a recognition limit, not a regression.
