# LOC-001 — One language setting, bilingual approved wording

**Status:** Proposed · **Owner:** Rajeev · **Supersedes:** the "one clinician-reviewed
locale per approved plan" rule in `pat-005-clinician-approved-today-feed-plan.md`
(§ locale attestation) and `docs/portal-ui-ux-review-2026-10-10.md` (language section).

## Problem

A patient's saved language (`patients.preferred_language`) controls the portal chrome,
but most patient-facing *content* is stored once, in whatever language it arrived in, and
rendered verbatim with no label. Observed in the synthetic environment on 2026-10-10:

- An `en-US` patient has an approved plan whose four items were reviewed in `es-MX` (the
  language changed after approval), and the open draft for the same patient is entirely
  Spanish. Today shows Spanish instructions inside an English app.
- Active frequencies mix languages (`twice daily`, `Dos veces al día`, `todos los días`).
  Frequency text is also scheduling input: reminder parsing maps a fixed list of Spanish
  phrases to English before it can schedule anything.
- Seeded medications for `es-MX` patients carry English frequencies; they were inserted
  directly and are not linked to any plan item.
- Changing the language has no side effect except that an open draft can no longer be
  approved until it is re-reviewed. Approved wording never follows the switch.
- Other surfaces are English-only or mislabelled: reminder guidance (translated on the
  client through a dictionary keyed by English sentences), in-app notifications, the
  provider label, raw backend error text on Today, server-rendered `lang="en-US"` with an
  English flash before the profile loads, clinician history messages labelled English,
  and three different label sets for the two locales.

## Principles

1. **One setting.** `patients.preferred_language` is the only source of the patient's
   language after sign-in. The server resolves it; clients do not pass ad hoc locales for
   patient content. Before sign-in the guest choice is used and is saved at sign-up.
2. **Clinical wording is approved in both languages, together.** Every patient-facing
   care-plan item carries `en-US` and `es-MX` wording. The model drafts the language the
   source was not written in; the clinician sees both side by side and approves both in
   the same review that approves the plan. Switching language then changes what the
   patient sees immediately, with no new review.
3. **Structured data is never machine-translated.** Drug names and doses stay as written.
   Frequency becomes a code (`once_daily`, `twice_daily`, `three_times_daily`,
   `four_times_daily`, `every_morning`, `at_bedtime`, `weekly`, `mon_wed_fri`,
   `as_needed`, `other`) rendered from code-owned dictionaries; reminders schedule from
   the code. Only `other` keeps free text, as bilingual wording.
4. **Server text is rendered from codes.** Guidance, notifications and error states return
   a code plus parameters; the reader's current locale renders them.
5. **Human messages keep their original language,** labelled with the language they were
   actually written in. They are never translated or relabelled.
6. **History is not rewritten.** Approved and superseded plan versions remain the record
   of what was approved, in the language it was approved.

## Design

### Data

- `care_plan_items`: `source_locale` (`en-US` | `es-MX`), `wording jsonb` —
  `{ "en-US": {title, instructions, frequency_text?}, "es-MX": {...} }` with a CHECK that
  both keys exist for active items in new versions — `wording_origin jsonb` per locale
  (`source` | `ai_draft` | `clinician_edited`), `wording_verified_at`, `frequency_code`.
  Existing `title / instructions / frequency` columns stay as the source-language copy
  for continuity matching and older readers.
- `medications`, `obligations`: `patient_wording jsonb` (same shape) and `frequency_code`,
  written only by `approve_care_plan_version` (and the legacy backfill below).

### Generation

After classification, a new `Workload.CARE_PLAN_TRANSLATION` drafts the other locale for
each item (Gemini Flash route, response schema, temperature 0). Deterministic validation
rejects a draft whose numbers, units, or drug names differ from the source; a rejected or
unavailable translation becomes a blocker ("Translation unavailable — retry or write it"),
never silent English. Diagnostics carry counts only, never text.

### Review (clinician portal)

The patient-facing wording pane shows **English (US)** and **Español (México)** side by
side. The source column is marked *From source*; the other *AI translation*. One check per
item — "I checked the wording in both languages" — records the verification. Editing
either language clears that check and offers **Re-translate** for the other. Clinicians
read and approve; typing is optional.

### Approval

`approve_care_plan_version` requires both locales present and verified for every active
item, projects `patient_wording` and `frequency_code` into medications and obligations,
and records per-locale origin (source / AI draft / edited) in the audit event. The
"Patient language changed; reload" guard is removed because both languages are reviewed.

### Read paths

`feed_service` and `reminder_schedule_service` read `preferred_language` with the patient
row and select `patient_wording[locale]`, falling back to the stored text with an
*original language* label when a legacy row has only one language. Reminders schedule from
`frequency_code`; guidance is returned as a code.

## Existing data

| Data | Treatment | Why |
| --- | --- | --- |
| Superseded and approved plan versions (history) | Unchanged | They are the approval record. |
| Currently active approved plans (2 synthetic patients) | A *bilingual refresh* draft is opened through the normal draft path, with AI translations filled in; the clinician approves it in one review. Today keeps the current wording, labelled, until then. | Marking AI text as clinician-approved by migration would fabricate an approval (`docs/demo-environment.md` forbids ad hoc approvals). |
| Open drafts (1, 5 items) | Regenerated with both languages; this is the end-to-end test of the new review. | Drafts are not patient-visible. |
| Legacy medications (23, not plan-linked) | Migration backfills `frequency_code` deterministically from known phrases; names and doses unchanged; unknown phrases become `other` with the original text. | No clinical content changes; labels then render in either language. |
| Legacy obligations (2) | Shown as stored with an *original language* label. | Free text with no approval path. |
| Seed fixture | Writes `frequency_code`; fixture checksum updated through the fixture process. | Keeps reset/seed consistent. |

The refresh is a script with a reviewed dry run and an apply step guarded by the dry-run
report hash (pattern: `backend/scripts/reproject_fhir_candidates.py`). Applying migration
049 or the refresh to any remote environment requires explicit authorization.

## Language uniformity fixes in the same change

- Guidance, notification and Today error text rendered from codes in the current locale.
- Sign-up saves the guest language; logout and session expiry keep `?lang=`; a cookie set
  on sign-in and on profile change lets the server render `lang` and initial copy without
  an English flash.
- One label set everywhere: *English (US)* / *Español (México)*.
- Patient language chip in the clinician patient header; message history labelled with the
  language each message was written in.
- Profile language help text updated to describe the new behaviour.

Follow-ups (separate tasks): chat session locale from the profile including mid-session
switches; cached per-locale document explanations; a single Spanish register (*tú*)
across records, reminders and symptoms copy.

## Acceptance

1. A draft generated from Spanish sources shows Spanish (*From source*) and English (*AI
   translation*) side by side; approval is blocked until each item's check is ticked.
2. After approval, switching the patient between `en-US` and `es-MX` changes Today,
   Reminders and care-plan details immediately, with no re-review and no mixed languages.
3. A translation that changes a number, unit or drug name is rejected and blocks approval.
4. Reminders schedule identically for `twice_daily` in either language.
5. Legacy single-language items show an *original language* label; no item shows text in
   the other language without one.
6. Audit events record which locale was the source and whether the other was AI-drafted
   or clinician-edited.
7. Backend pytest, Ruff, mypy; both portals' lint, typecheck, tests and build; migration
   validation; seed dry run and idempotency.
