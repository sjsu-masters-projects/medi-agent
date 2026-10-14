# LOC-003 — English-first clinician review of Spanish content

**Status:** Backlog; design agreed in outline, decisions below. Raised at the October 13
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
| Clinician chat tab (patient–Nora transcript) and care-team messages | Open decision 3 |

## Decisions needed

1. Translate extracted facts once at ingestion, with the same number-equality guard as
   LOC-001 and stored as display fields? Or translate on read and cache? Ingestion is
   simpler to audit.
2. Is a bilingual reviewer optional or required for es-MX publication? The current rule
   is a clinician attestation of both languages.
3. Should clinicians get an English rendering of a Spanish-speaking patient's chat and
   messages, and should their replies be translated back to Spanish? This is a separate
   safety review, because a translated message is clinical communication.
