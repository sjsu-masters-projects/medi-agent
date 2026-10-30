# Confirmed symptom intake

A patient describes a symptom to Nora, answers approved questions in private, reviews
exactly what would be shared, and confirms. Only then does an assigned clinician see a
report. Patients use Nora and "My symptoms"; clinicians use the symptom report panel.

## What it does

- **Offer and questions.** After a first-person, non-emergency symptom, Nora asks whether to
  note it for the care team; nothing exists until yes (typed or spoken). Then one approved
  question at a time, "Private until you confirm", answered by typing, voice, "I don't
  know", "Prefer not to answer", or a quoted suggestion.
- **Review.** The preview separates what the patient reported (including unknown and
  declined), cited record context, and a summary. Confirming needs the consent checkbox and
  **Confirm and share with my care team**. Cancel creates no report.
- **After.** "My symptoms" lists confirmed reports. Assigned clinicians get an in-app
  notice, read the report and can "Mark reviewed" per care team. Emergency wording at any
  step interrupts the draft.

## Rules it must keep

1. The deterministic safety floor runs before any intake work on every patient text: the
   source message, each answer, reply and correction, and the whole ledger again at preview
   and confirm. A hit sets `interrupted_safety`, which cannot be resumed or confirmed.
2. Emergency direction never waits for storage, retrieval or a model. Its care-team alert is
   independent of any report, retained for retry, and never reported sent unless saved. "No
   rule matched" is not clearance: unanswered red flags show as unknown, never negative.
3. A structured "yes" escalates only through a question with a reviewed
   `positive_safety_rule`; an isolated "yes" is never keyword-matched. A patient severity
   of 8 or more raises one urgent notice to the care team even if never confirmed, with no
   private answers.
4. Nothing reaches `symptom_reports` without explicit confirmation: `consent` true, the
   exact current `preview_hash`, expected revision and a client `confirmation_id`. A chat
   message, transcript, spoken assent or model action never confirms.
5. Drafts are patient-only. Answers and previews never enter chat messages, shared
   conversation state, Redux persistence, localStorage or analytics, nor SOAP, risk, MCP,
   chat context, notifications or tasks. The initial Nora message stays in the transcript
   clinicians can read; never call it private.
6. Answer states are `answered`, `unknown`, `declined`. Unknown and declined hold no value
   and never become "no", empty text, zero or an estimate. Severity is a patient-chosen 1
   to 10 or null, never inferred from words, documents or a model; reports show "unknown".
7. Questions come only from the approved release pinned to the draft by version and hash:
   fixed order, at most 12 ids, resolved ids never re-asked. No model writes a question,
   picks a branch or answers for the patient. A new release never alters a draft or report.
8. Any answer change returns a ready draft to `collecting` and discards the preview.
   Terminal drafts (confirmed, cancelled, interrupted) accept no ordinary mutation.
9. Record context is evidence, not testimony, and never fills an answer. It is gathered
   only for a patient-named product matched by trimmed, case-insensitive name to active
   medications, capped at 4 medications, 5 approved facts and 2 cited excerpts of 500
   characters. Eligibility is rechecked at read, preview, confirm and commit; a withdrawn
   source hides the preview. Clinician reads drop `context`.
10. A patient-named product is labelled patient-reported and unverified. It links to a
    medication only on a unique exact active-list match, never creates or edits one, and an
    unlisted product raises a clinician review flag. Confirmation is testimony, not
    clinician approval of a diagnosis, medication link or ADR conclusion.
11. Identity comes from the authenticated patient session; request bodies reject unknown
    fields. The source must be the patient's own `user` message in the exact session. Any
    mismatch returns one non-enumerating "Intake unavailable" denial, and it is audited.
12. Browser roles cannot write reports, drafts or tasks; service RPCs recheck ownership,
    state and revision. A confirmed report is immutable except the operational
    `flagged_for_adr`. Old rows stay `legacy_unconfirmed` and are never promoted.
13. Each mutation has a `mutation_id`: same body replays the saved state, a different body
    or a stale `expected_revision` conflicts. One active draft per patient and session, one
    intake per source message, one report per intake; repeating confirm with the same
    preview returns the same report; confirm and cancel serialize on the draft row. No
    model or network call runs in a transaction. Report, audit row, ADR screen task and
    clinician notices commit together, so a later outage cannot lose the report or force
    re-confirmation. Audit rows are append-only.
14. The library fails closed: approved manifest entry, approval fields, file hash and a
    matching database eligibility row must all hold, and `SYMPTOM_INTAKE_ENABLED` (default
    off) must be on. A missing or revoked release blocks progress and confirmation, never
    safety. A disabled feature shows "unavailable" and never restores automatic saving.
15. Locales are `en-US` and `es-MX`. Each answer records its locale, patient wording is
    never translated, and a draft keeps its pinned wording when the interface language
    changes. Time zone comes from the patient profile with a labelled UTC fallback.
    Patient errors map stable codes to both locales, never raw server text.
16. "Sent to your care team" shows only when the hand-off audit counted an active clinician;
    zero shows "not sent"; an older report with no count shows neither. Review is per care
    team, repeat-safe, and records follow-up only. The review notice is History only.

## Why it was built this way

- Draft then confirm replaced saving a model-extracted report on the first message, which
  had no patient review and could start ADR work from a guess. Database guards hold the
  boundary because that direct insert was the bypass.
- Approved fixed questions replaced model-written follow-ups; suggestions are quoted text.
  Wording and releases live in the
  [release README](../../backend/src/app/intake/question_library/README.md). The offer
  replaced an always-visible "start a draft" panel.

## Excluded on purpose

- Symptom-specific clinical branches, new red-flag rules, diagnosis, causality, medication
  changes or MedWatch from intake.
- A full voice interface (VOI-001) or voice confirmation; voice is only an answer input.
- "Clinician viewed" or "replied" events, review email, silent draft expiry, a question
  authoring product.

## Where it lives

- Backend (`backend/src/app/`): `routers/symptom_intakes.py`,
  `services/symptom_intake_service.py`, `services/symptom_report_history_service.py`,
  `intake/`, `safety/intake_gate.py`, `safety/symptom_offer.py`, offer step in
  `routers/chat.py`. Scripts: `publish_symptom_questions.py`, `preflight_symptom_intake.py`.
- Migrations (`db/migrations/`): `060_confirmed_symptom_intake`,
  `071_confirmed_symptom_handoff`, `079_unlisted_product_review_alerts`,
  `091_symptom_report_history_and_review`, `095_symptom_review_notifications`.
- Portals: patient `components/features/symptom-intake-panel.tsx`, `symptom-history.tsx`;
  clinician `components/features/symptom-report-panel.tsx`.
- Tests (`backend/tests/`): `unit/intake/`, `integration/test_symptom_*_postgres.py`,
  `integration/routers/test_symptom_intake_api.py`.

## How to check it

Follow [QA handoff section 3.2](../qa-handoff-2026-10.md) in both locales at 390 px: accept
the offer, leave one answer unknown, refresh to recover the draft, change an answer and see
the preview rebuilt, confirm once, read the report as the assigned clinician; then try an
emergency phrase and a cancel. See the [rollout guide](../pat-002-b-rollout.md) and
[acceptance evidence](../evidence/pat-002-b-acceptance-2026-10-17.md).

```sh
cd backend && PYTHONPATH=src .venv/bin/pytest tests/unit/intake --no-cov -q
SYMPTOM_INTAKE_TEST_POSTGRES=1 PYTHONPATH=src .venv/bin/pytest \
  tests/integration/test_symptom_intake_postgres.py --no-cov -q  # needs local Postgres
```

## Still open

- A medication-error phrase typed mid-draft shows the reviewed same-day copy, but the
  interrupt RPC accepts only the two emergency rules, so the draft is not marked
  interrupted and persistence is reported uncertain. No test covers it.
- No question carries a reviewed `positive_safety_rule`, so a structured "yes" to a red
  flag escalates nothing by itself.
