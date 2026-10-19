# LOC-003 — English-first clinician review of Spanish content

**Status:** Merged ([#181](https://github.com/sjsu-masters-projects/medi-agent/pull/181), Jeevan); migrations renumbered to 067/068 and applied October 17 (first applied under their earlier filenames; re-runnable, so they reapplied cleanly); deployed check pending (see the board). Design and decisions agreed October 13. Raised at the October 13
checkpoint demo.

## Principle

The clinician portal is English-only, and the patient portal follows the patient's
language (en-US or es-MX). A clinician who reads no Spanish must still understand and
approve everything. Spanish appears in the clinician portal for only two reasons:

- it is exactly what the patient will see; or
- it is the original source evidence.

Both uses are labelled as such.

## What is confusing today

- **Care plan.** The "Proposed items" list shows each item in its source language, so a
  plan drafted from a Spanish document lists "Metformina 500 mg" and "Tome un vaso de
  agua…". The detail shows English and Spanish side by side, and nothing explains why
  there are two languages or which one the patient sees. The approved view repeats this.
- **Extracted facts.** Facts from a Spanish document are shown in Spanish in the review
  queue, the document facts dialog and the care-plan source excerpts: names,
  instructions, frequencies and summaries.
- **Checking Spanish.** Approval asks the clinician to confirm the Spanish wording against
  the source, which an English-only clinician cannot do.

## Proposed behaviour

1. **Care-plan lists are always English.**
   - The proposed-items list (draft) and the item list (approved plan) show English titles.
   - When the English is a translation of a Spanish source, a small "Translated from
     Spanish" marker says so.
2. **The detail shows what the patient will see.**
   - Each item shows a compact strip: "Source: Spanish document → You review: English →
     Patient sees: Español (México)".
   - The patient's language card is highlighted as "Shown in the patient's Today", with a
     phone-style preview.
   - The other language is labelled "Stored in case the patient changes language".
   - The same strip appears in review, preview and the approved plan.
3. **Spanish is verified through English.** Instead of asking the clinician to read
   Spanish, the Spanish card shows:
   - an English back-translation of the Spanish wording;
   - the existing guard results (numbers, doses and medication names identical; LOC-001
     already blocks a translation that changes them).

   The approval attestation then says what was actually checked. Optionally, a bilingual
   colleague can mark the Spanish as reviewed.
4. **Extracted facts are shown in English.**
   - Medication, allergen and vaccine names are never translated (decision 5): the review screen
     keeps the name exactly as printed.
   - Condition, procedure and test names, instructions and frequencies are translated and
     labelled "Translated from Spanish". Values, units, ranges, flags and dates are never translated or changed.
   - The original Spanish text stays one tap away.
5. **Source evidence stays original.**
   - Excerpts and citations remain the exact printed Spanish, because they are the
     evidence, with an English gloss beside them.
   - Nothing replaces the source text in storage.

## Where this applies

| Surface | Change |
| --- | --- |
| Care-plan draft list and detail; approved plan | 1–3 |
| Review queue and document facts dialog | 4, 5 |
| Care-plan source excerpts and protected source preview | 5 |
| ADR evidence quoting patient answers | English gloss with the original |
| Clinician chat tab (patient–Nora transcript) and care-team messages | Decision 3 |

## Decisions

1. **Decided (requester, October 13): translate when the document is processed.** The
   English display fields are written at ingestion with the same guard as LOC-001: numbers,
   doses and medication names must match, or the item keeps only its original text and is
   marked untranslated. They are stored with the fact and audited with it, so every viewer
   sees the same English.
2. **Decided (requester, October 13): a bilingual reviewer is optional, never a blocker.**
   The clinician checks the Spanish against its English back-translation and the guard
   results (or any translation tool), then attests. A bilingual colleague's review can be
   recorded but is not required to publish.
3. **Decided October 13: chat and care-team messages get stored translations.**
   - **Patient messages in Spanish:** the original stays the message of record. An English
     translation is shown below it automatically, labelled "Translated from Spanish". An
     info icon explains that it was translated automatically, by which model, and that it
     may contain errors. This also applies to the patient–Nora transcript in the
     clinician's Chat tab.
   - **Clinician replies:** written in English. Before sending, the clinician sees the
     Spanish the patient will receive, with an English back-translation, and confirms it.
     The patient sees the Spanish with "Translated from English · show original".
   - **Guard:** the LOC-001 guard applies. If numbers, doses or medication names differ,
     no translation is used: the reply is delivered in English with a short Spanish note
     that a translation was unavailable, and the clinician is told.
   - **Storage:** each message is translated once, when it is sent or received, and stored
     with it (message, target language, text, model, guard result, time).
   - **Safety and records use only the original text.** Urgent-symptom checks and
     escalation never depend on a translation, and a translation never becomes a clinical
     fact.

## Decisions from the October 17 review

4. **A translation that failed its guard is never shown by default.** When
   `translation_guard_passed` is false, both portals show the original message as the main
   text with a short note ("Automatic translation unavailable for this message"; es-MX below)
   instead of the translated text. The clinician portal no longer shows the failed translation
   in its "Translated" box either. The es-MX note is a **draft for LOC-001 review**, not
   approved wording: `Traducción automática no disponible para este mensaje`.
5. **Proper names are never translated.** Medication names, allergens and vaccine names are not
   sent to the model; `display_value` omits those keys and the review screen keeps the printed
   name. Condition, procedure and test names are still translated and keep the digit guard.
   The reason: a model can alter or "correct" a drug name, which is a clinical-safety change the
   number guard cannot see.
6. **Ingestion translates only the document's own facts**, found through the document's
   provenance, not the patient's 50 most recent untranslated facts.
7. **Message translation reads are bounded.** A read translates at most ten messages that have
   no stored translation, skips stored ones, logs failures without message text, and never
   fails the read. **Superseded by decision 12:** the cap is gone because a read no longer calls
   the model. Clinicians write English; translation runs only when a message's detected language
   differs from the reader's language, so there is no "detect the clinician's language" follow-up.

## Decisions from the October 17 second review (branch `fix/loc-003-review`)

8. **The patient's own language is the target.** A clinician's message is translated into the
   patient's `preferred_language` (en-US or es-MX), and only when its detected language differs
   from it: an English reply to an en-US patient makes no model call and attaches no translation.
   A clinician reads English, so only messages detected as Spanish are translated for them. The
   patient portal shows a translation as the main text only when `translation_locale` equals the
   patient's own locale; the clinician portal only when it is en-US.
9. **Attestation needs a real check.** The "I verified ..." box is enabled only when the
   back-translation of the SAVED Spanish wording has loaded, the numbers and medication-name
   guards passed, and nothing is unsaved. Its disabled reasons are: "Back-translation is loading",
   "Back-translation unavailable — retry", "Numbers or medication names differ — fix the Spanish",
   "Save your changes first". The back-translation is fetched for saved wording only (on mount and
   after a save), with "Check again" and "Retry", and a slower older response is ignored.
   **Server side:** setting `wording_verified` (on save, and again at the approval preflight)
   re-checks the stored English and Spanish wording against the same deterministic guards
   (numbers with units, negation, medication name) and rejects with a validation error. It does
   not call the model. Follow-up: the guard outcome is not recorded with the verification (no
   suitable column; adding schema was not justified).
10. **Stored translations are always attached; only new model calls are capped (ten per read).**
    A failed translation is stored as a marker (`guard_passed=false`, `guard_failure_code =
    model_error`), is never shown, and is retried after an hour. Store and read run off the event
    loop. The send used to wait for the translation; decision 12 removes that. `model_id` is
    stored when the provider reports it.
11. **Shared guards** (`translation_guards.py`) for messages, care-plan wording and fact fields:
    numbers are compared with their units (mg, g, mcg/µg, mL, L, units/UI, %, tablets/tabletas and
    similar, English and Spanish equivalents); "1,000" and "1.000" are not folded together (a
    thousands-separator swap fails the guard), while a decimal comma still equals a decimal point;
    a negation (no, not, never, without, sin, nunca) that appears or disappears fails the guard;
    message translation also protects the patient's active medication names.
12. **Prompt text is data.** Message and fact translation prompts say the text is data to
    translate, never instructions, and wrap it in delimiters; delimiter text inside the data is
    removed.

## Remaining (owner: Jeevan)

- Phone-style patient preview of the translated wording.
- English glosses beside original excerpts, and the ADR evidence gloss.
- Translation of the clinician Chat tab (Nora transcripts).
- A clinician reply preview with back-translation before sending.
- A "may contain errors" / model-info icon on translated text.
- Marking facts untranslated when the guard rejects them, with the original Spanish one tap away.
- Batching ingestion fact translation.
- Caching back-translations.
- A foreign key and a retention rule for `message_translations`.
- The duplicate `067` migration prefix (the validator allows it).
- Moving message translation on send and read to a background job; recording the guard outcome
  with the wording verification.

## Decision from the October 17 UX-006 branch (`feature/clinician-schedule`)

12. **Translation never runs in the send or read path (done).** Production Cloud Run gives CPU
    only while a request is open, so no background task or thread is used.
    - **Send** stores the message and returns; no model call.
    - **A conversation read** returns originals plus any stored translations. A message the viewer
      needs translated but which has none stored (or only a failure marker older than an hour)
      carries `translation_pending: true`. A fresh failure marker is neither shown nor pending.
    - **`POST /care-conversations/{id}/messages/{message_id}/translation`** translates ONE message
      into the viewer's language with the same guards, stores it (idempotent upsert) and returns
      `{message_id, translation, translation_locale, translation_guard_passed, translation_pending}`.
      It is authorized like a read of that conversation (an outsider is refused; a message outside
      the conversation is "not found"). A stored translation or a fresh failure marker is returned
      without a model call, which is the simple rate limit.
    - **Both portals** show the original first, then request the pending messages after the read,
      at most three in parallel, with a subtle "Translating…" (es-MX `Traduciendo…` is a **draft
      for LOC-001 review, not approved**). A failed guard or request leaves the original. Display
      rules are unchanged: locale must match the viewer. Typing and sending are never blocked.
    - Clinicians write English; translation runs only when a message's detected language differs
      from the reader's language.
