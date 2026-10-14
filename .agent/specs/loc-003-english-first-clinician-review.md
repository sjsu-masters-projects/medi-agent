# LOC-003 — English-first clinician review of Spanish content

**Status:** Backlog; design and decisions agreed October 13. Raised at the October 13
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
   - Medication names come from the RxNorm normalisation already used by Nora (for example
     metformina → metformin).
   - Test names, instructions and frequencies are translated and labelled "Translated from
     Spanish". Values, units, ranges, flags and dates are never translated or changed.
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
