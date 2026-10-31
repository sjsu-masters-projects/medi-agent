# Language and approved wording

MediAgent serves patients in American English (`en-US`) and Mexican Spanish (`es-MX`). The
patient portal follows one saved language; the clinician portal is English-only and shows
Spanish only where it is exactly what the patient sees or the original evidence.

## What it does

- **Patient.** `patients.preferred_language` drives the portal, Today, reminders, care-plan
  details, notifications and record titles. Switching changes approved wording at once,
  with no new review. A guest choice carries through sign-up and onboarding.
- **Clinician, care plan.** Every item shows English and Spanish side by side, marked
  "From source" or "AI translation", with an English back-translation of the Spanish, the
  guard results, and a phone-style preview of the patient's language. One check per item
  attests the wording; either language can be edited and re-translated.
- **Clinician, facts and evidence.** Extracted facts show English display fields, with the
  printed original one tap away. Source excerpts stay original with an English gloss
  beneath. The Nora transcript and care-team messages show stored English translations.
- **Care-team messages.** A reply to a Spanish-reading patient is previewed in Spanish with
  an English back-translation and confirmed before sending. The patient sees "Translated
  from English, show original".

## Rules it must keep

1. One setting. The server resolves the patient's language; clients do not pass ad hoc
   locales for patient content. First paint uses a hint (query on entry pages, then
   cookie, then `Accept-Language`); the cookie is presentation only, never identity, and it and
   the guest preference are cleared on every sign-out (manual, cross-tab, inactivity) so the
   next person on a shared device does not inherit them. While unresolved, show a locale-neutral skeleton.
2. Every patient-facing care-plan item carries both languages, approved together in the
   same review that approves the plan. A language change never alters approval,
   schedules, timezone or completion. Approved and superseded versions are never
   rewritten; the audit records which language was the source and whether the other was
   AI-drafted or clinician-edited. The refresh script only drafts; it never approves.
3. Translation never changes a clinical fact. Numbers with units, negations and medication
   names must survive; a failing draft is discarded and blocks approval until rewritten.
   "1,000" and "1.000" are not folded; a decimal comma equals a decimal point. Across
   languages only negation presence is compared (Spanish may double a negation); an English
   original versus its English back-translation also compares counts. These are
   heuristics, not proof of clinical meaning, and the preflight says so.
4. Medication, allergen and vaccine names are never sent to a model; the review screen
   keeps the printed name. A model can "correct" a drug name and the number guard cannot
   see it. Prompt text is data: wrapped in delimiters, with delimiter text removed.
5. Attestation needs a real check: it is enabled only when the back-translation of the
   SAVED wording has loaded, the guards pass and nothing is unsaved. The server re-runs
   the deterministic guards when verification is set and at the publication preflight,
   without a model call, and the database trigger requires the guard record. Editing
   either language clears the check and cached back-translation. The record is audit
   only; publication never trusts it.
6. Offline stub translation (`TRANSLATION_STUB_ENABLED`, ignored in production, model id
   `offline-translation-stub`) is never verifiable or publishable as patient wording.
7. Reminder scheduling keeps parsing the source-language frequency. A legacy
   single-language row shows recognised cadence phrases in either language and anything
   else as written, labelled "Written in Spanish (or English) by your care team".
8. Human messages keep their original language and are never relabelled. The original is
   the record; urgent-symptom checks and escalation read only the original; a translation
   never becomes a clinical fact.
9. A translation that fails its guard is never shown. Both portals show the original with
   a short unavailable note. A failure marker is retried after an hour.
10. Translation never runs in the send or read path. A read returns originals, stored
    translations and `translation_pending`; one explicit per-message request translates,
    is authorized like a read, and is idempotent. Portals request at most three at once.
    A patient sees a translation as main text only if its locale is theirs; the clinician
    portal only for `en-US`.
11. A reply preview returns the wording the patient will receive and its back-translation.
    The confirmed wording is what is stored and sent, and the server re-runs the guards
    on it. A guard-rejected translation is never offered: the reply goes in English with
    a short Spanish note. Nothing is stored for an unsent reply.
12. Fact display fields are written at ingestion for the document's own facts only (batches
    of 15), guarded; a rejected one shows "Not translated" with the reason. Evidence
    excerpts are never altered in storage or on screen; glosses are capped at ten per request.
    Batch failures log only count and exception type, with no traceback or model output.
    Record titles come from existing summaries, are rejected if they carry digits or run
    long, never send the patient's name to a model, and keep the file name as identity.
13. Every machine translation in the clinician portal shows an affordance naming the model
    and "may contain errors". The patient is told only on messages, never on approved Today
    wording (that would misdescribe clinician-approved text).
14. Spanish interface wording is accepted through model-assisted English/es-MX
    meaning-and-safety review on the requester's authority. Record it as that: it is not
    professional translation, human review or clinical validation. A changed source or pair
    fails CI (`--require-reviewed`); regenerating the inventory never renews acceptance.
    It does not approve stored care-plan wording, which a clinician approves in the app.
15. Spanish uses the tú register; clinician controls stay English. Today and notification
    errors render from stable codes, never backend prose.
16. Message translations are display state: deleting a message cascades, a purge job
    removes orphans and old failure markers, and a good translation lives with its message.

## Why it was built this way

- Approve both languages together: switching language then needs no re-review, and AI text
  is never marked approved by migration or script.
- English-first review: an English-only clinician verifies Spanish through a back-translation
  and deterministic guards. A bilingual reviewer is optional and never blocks publication.
- Translate at ingestion and per message, not on read: Cloud Run gives CPU only during a
  request, so no background translation, and reads stay fast and deterministic.

## Excluded on purpose

Professional translation or clinical validation claims; Spanish clinician controls;
translating human messages in storage; translation inside safety checks; auto-approving
legacy single-language plans.

## Where it lives

- Backend `backend/src/app/services/`: `patient_wording.py`, `care_plan_translation.py`,
  `translation_guards.py`, `translation_stub.py`, `message_translation.py`,
  `fact_display_translation.py`, `evidence_gloss.py`, `document_title_service.py`,
  `care_conversation_service.py`. Migrations `049`, `050`, `067`-`068`, `080`-`082`, `088`.
- Scripts: `backend/scripts/build_spanish_review_pack.py`, `preflight_loc003_translation.py`,
  `refresh_bilingual_care_plans.py`.
- Clinician `apps/clinician-portal/src/`: `components/features/care-plan-wording.tsx`,
  `components/ui/translation-note.tsx`. Patient `apps/patient-portal/src/`: `proxy.ts`,
  `content/patient-locale.ts`, `content/*-copy.ts`, `components/features/today-presentation.tsx`.
- Review artifacts: [review pack](../spanish-draft-review-pack.md),
  [dated review](../evidence/spanish-interface-wording-2026-10-22.md),
  [interface review record](../evidence/loc-001-interface-review.md).

## How to check it

Follow QA handoff [3.10](../qa-handoff-2026-10.md#310-sessions-and-operations) and
[3.11](../qa-handoff-2026-10.md#311-spanish-wording). From `backend`, with
`PYTHONPATH=src .venv/bin/`: `pytest tests/unit/scripts/test_spanish_review_pack.py
tests/unit/services/test_translation_guards_shared.py
tests/unit/services/test_care_plan_translation.py --no-cov`; `python
scripts/preflight_loc003_translation.py --self-check` (offline); `python
scripts/build_spanish_review_pack.py --check --require-reviewed`. Patient: `npx vitest run
interface-wording-review`. Clinician: `npx vitest run care-plan-wording`.

## Still open

- An optional "bilingual colleague reviewed the Spanish" mark is not built; the portal only
  suggests asking one.
- No patient-language chip in the clinician header or per-message language label (not found).
