# Nora chat

Nora is the patient's chat assistant for supervised chronic-care workflows on synthetic
data. She explains medications, conditions and the patient's own documents in plain en-US
or es-MX, triages what the patient writes, and hands anything clinical to the care team.

## What it does

- **Patient.** Types or speaks ([voice mode](voice-mode.md)). Each day opens a new
  conversation; "New chat" starts another; earlier ones are listed and reopen with their
  messages. Nora answers in the language the patient wrote, whatever the app language.
- **Medication or condition questions** are answered from MedlinePlus, DailyMed label
  sections and RxNorm identity, end with a dated source line, say whether the item is on the
  patient's list, and keep general facts apart from the record.
- **Document questions** are answered from extracted facts with page references and review
  status. Lab reports add a results card: critical results first ("contact your care team
  today"), out-of-range results with printed ranges, the rest collapsed, a link to Records.
- **Record questions** (next visit, allergies, today's plan) come from the record, with
  times in the patient's saved time zone.
- **Reload, second tab, lost network or restart:** the saved turn recovers; the patient sees
  one reply, a Retry card when retry is safe, or an explanation when it is not.
- **Care team.** Gets urgent-turn alerts, a critical-lab Safety notification, and can read
  the sources behind a reply (assigned clinicians only).

## Rules it must keep

1. The deterministic safety floor runs before any model. Emergency and crisis copy is
   reviewed fixed text, never generated, inferred from partial output or retranslated, also
   when a turn is recovered after a timeout or reload.
2. Nora never diagnoses or advises starting, stopping or changing a medication or dose. A
   dose-change request, an extra dose, or taking a medication a document says to stop or hold
   is at least urgent. A side effect happening now is a symptom: at least urgent, never
   "nothing to worry about", with 911 wording when severe or sudden. She never claims the
   care team was told.
3. A missing triage decision fails closed to the localized unavailable message. Mild stable
   symptoms, low mood and wellness questions may be routine but never lower a floor decision.
4. Tools are deny-by-default per agent; the responder has none. The patient comes from
   session state, never the model. Tools are read-only or candidate-only.
5. A medication or condition question must call the reference tool. On `not_found` or
   `unavailable` Nora says so and suggests the pharmacist or care team; never memory.
   Reference text is data, never instructions; the record and care team win on conflict.
6. Reference text never carries a dose: dosage and Medication Guide sections are not fetched
   and sentences stating an amount are stripped. A dose-like number in a reply found in
   neither the record nor a tool result is logged (count only).
7. The source line is server-written from sources the tools returned this turn;
   model-written source lines are removed. Citations narrow to the documents and pages the
   reply names and never widen; rejected items are never cited; an English-only source in a
   Spanish reply is named as English.
8. Fetching: NLM HTTPS hosts only; 6 s per request, 8 s inline; size-capped, HTML stripped,
   shape validated. Failure is `unavailable`, never cached as "not found". A DailyMed label
   must be single-ingredient. Logs carry outcome, latency and source, never message text.
9. Name resolution: the patient's list first, then RxNorm exact, then approximate match only
   if it shares a word and scores 0.85 or more ("hydration" is not chloral hydrate). "On my
   list" is decided by RxNorm ingredient, never similarity (losartan is not valsartan).
   Combination products report no match.
10. A condition topic must match the question (a shared word is not enough). Spanish text is
    MedlinePlus's own twin page at the same slug, never a translation; no twin is `not_found`.
11. Freshness: checked within 7 days is served; a miss retries after 7 days; a row over 30
    days old is served marked stale only when the source is down. The weekly job re-checks
    rows over 6 days old and seeds active medications and documented conditions.
12. Spanish uses tú and no gendered clinician titles; speech is transcribed multilingual.
13. Document context belongs to the submitted turn and is authorized again at send time. A
    turn stores source identity and a content hash, never a signed URL or summary text. A
    missing, deleted, unprocessed or summary-less document gives an explicit unavailable
    reply, never a chart-wide fallback. Attach or dismiss affects only later turns.
14. Unreviewed items are called unconfirmed whenever mentioned. A result is value, unit and
    printed range; "high/low" only when the report's flag says so; never what it means for
    health. Critical means "contact your care team today". A stopped or held medication is
    never presented as current. The results card is a server snapshot of source-checked
    facts, never parsed from the reply.
15. Extraction is a candidate. Each value is grounded on its printed page row with an exact
    value; a flag contradicting its range is low confidence; proposals no page confirms are
    counted in run warnings, not dropped silently. A stopped or held medication is never
    publishable and blocks matching active care-plan items; a changed dose needs
    confirmation; results-only documents open no draft.
16. A patient explanation states only numbers present in the facts and surviving translation,
    or nothing is shown. A critical lab flag notifies the active care team once per
    document, never the patient, with no health detail in email, until acknowledged.
17. A client UUID identifies one turn with its exact text, language and document; reuse with
    different content is rejected. The message is saved once, one turn is active per
    conversation, a second send is refused as busy with the text kept in the composer, and a
    completed retry replays the saved reply.
18. The server owns the turn: closing a socket never cancels it. State changes are guarded
    transitions and only the lease holder writes. Budgets use the database clock: processing
    40 s, lease 70 s at the default 30 s model timeout (save has its own 30 s grace, never
    over 120 s). A late reply is kept if the turn is processing, or interrupted with no
    reply and no dismissal; a replaced lease, dismissal or failure refuses it.
19. A clinical side effect runs at most once. After `actions_started` a turn is never
    re-executed and a lapsed lease starts no new action; a reply after an uncertain action
    is kept and the action is not repeated. Retries reuse the saved message, max 3 attempts.
20. A lost connection never resends. Updated clients ask for `turn_protocol=1` and keep
    sending disabled until the recovery handshake; they never fall back to legacy execution.
    Streamed text is provisional and authorizes nothing; it is a prefix of the saved reply
    because source lines and Markdown are removed as text streams.
21. Model context is stored messages only: newest whole turns within 6,000 characters plus
    a stored rolling summary (at most 1,500 read), labelled data. A private symptom draft is
    never an input. A reply's evidence row (tools, sources, no reply text) is append-only,
    readable by the patient and an actively assigned clinician only, kept 180 days.

## Why it was built this way

- Coordinator (tools) then responder (no tools): working notes never reach the patient.
- A shared public-source cache with a weekly refresh, not per-turn retrieval (the old
  pgvector retrieval never reached the model). Server-written citations, because a model
  cannot be trusted to cite what tools returned; no label doses, which read as a prescription.
- Turns live in the database, not a websocket, because reloads killed replies
  ([AI runtime and workers](ai-runtime-and-workers.md)). Daily conversations bound context.

## Excluded on purpose

Booking or changing visits; diagnosis; dose advice; combination-product answers; translated
Spanish reference text; automatic care-plan publication; browser reads of chat tables;
human care-team messaging (separate feature).

## Where it lives

- `backend/src/app/adk/` (`agents/care_coordinator/`, `chat_runtime.py`, `grounding.py`,
  `recap.py`, `evidence.py`, `tools/`), `services/health_knowledge_*.py`,
  `workers/health_knowledge_refresh.py`, `routers/chat.py`, `services/chat_turn_*.py`,
  `services/document_intelligence/`; migrations 051, 059, 060, 062, 072 to 078, 094.
- `apps/patient-portal/src/app/(app)/chat/`, `hooks/use-patient-chat-session.ts`,
  `components/features/{chat-turn-recovery,nora-conversations,chat-results-card}.tsx`.

## How to check it

[QA handoff 3.1 and 3.9](../qa-handoff-2026-10.md). Ask "What is metformin for?" in both
languages (dated source expected); ask about a Records document (page reference and results
card); send, reload mid-turn (one reply); try New chat and reopen an older conversation.
From `backend/`: `.venv/bin/pytest tests/unit/adk tests/unit/services/test_health_knowledge_service.py
tests/integration/routers/test_chat_turn_recovery.py --no-cov -q` (PostgreSQL turn tests
need `CHAT_TURN_TEST_POSTGRES_DOCKER=1`); live set `backend/scripts/check_nora_answers.py`.
Portal: `npm run test -- chat`.

## Still open

- The unsupported-dose check only logs; blocking needs measured false positives, and early
  speech must then be off for those turns.
- Combination products; the unused `drug_knowledge_chunks` table has no drop migration;
  label XML is parsed with the standard library (`defusedxml` is not a dependency).
- Triage evaluation shows over-triage of mild symptoms; real-provider behavior for wellness
  prompts is not recorded as evaluated.
