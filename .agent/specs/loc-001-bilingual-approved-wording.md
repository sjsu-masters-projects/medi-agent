# LOC-001 — One language setting, bilingual approved wording

**Status:** Verify deployed — merged and deployed in #145 (`0cf4c93`); follow-ups are LOC-002 · **Owner:** Rajeev · **Supersedes:** the "one clinician-reviewed
locale per approved plan" rule in `pat-005-clinician-approved-today-feed-plan.md`
(§ locale attestation) and `docs/evidence/portal-ui-ux-review-2026-10-10.md` (language section).

## Pending interface wording review

[PAT-001-A recovery-copy drafts](pat-001-a-nora-turn-recovery.md#pending-es-mx-interface-wording-drafts--not-approved)
list the new recovery, busy/unavailable, retry-help and revised document-unavailable
wording. They are not yet reviewed/approved Spanish copy; existing clinical safety
resources are unchanged.

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
3. **Clinical facts are never changed by translation.** Drug names, doses and numbers
   stay as written; a draft that changes one is discarded. Reminder scheduling keeps
   parsing the source-language frequency exactly as before. Older single-language rows
   show recognised cadence phrases (the vocabulary reminder parsing already knows) in
   either language; anything else is shown as written.
4. **Server text follows the reader's language.** Reminder guidance is already localized
   on the client; notifications and Today error states move to codes (LOC-002).
5. **Human messages keep their original language,** labelled with the language they were
   actually written in. They are never translated or relabelled.
6. **History is not rewritten.** Approved and superseded plan versions remain the record
   of what was approved, in the language it was approved.

## Design

### Data

Migration `049_bilingual_care_plan_wording.sql`:

- `care_plan_items`: `source_locale` (`en-US` | `es-MX`), `wording jsonb` —
  `{ "en-US": {title, instructions, frequency}, "es-MX": {...} }`, shape-checked by the
  table — `wording_origin jsonb` per locale (`source` | `ai_draft` | `clinician_edited`)
  and `wording_verified`. Existing `title / instructions / frequency` columns stay as the
  source-language copy that medication reconciliation and continuity compare; the source
  wording must equal them.
- `medications`, `obligations`: `patient_wording jsonb` (same shape), written only by
  `approve_care_plan_version`. Empty means a legacy single-language row.

### Generation

After the atomic generation write, `Workload.CARE_PLAN_TRANSLATION` drafts the other
language for each item lacking one (Gemini Flash route, response schema, temperature 0).
The source language comes from a deterministic check of the wording, falling back to the
model's answer. Validation discards a draft whose numbers or medication name differ, or
that leaves a field empty. A discarded or unavailable translation leaves the item
untranslated, which blocks approval until the clinician re-translates or writes it; it
never fails or rolls back generation. Diagnostics carry counts only, never text.
`POST /care-plans/clinician/patients/{patient}/{plan}/items/{item}/translate` redrafts
one item from its source language.

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

`feed_service` (Today and the clinician preview) and `reminder_schedule_service` read
`preferred_language` with the patient row and select `patient_wording[locale]`. A legacy row
keeps its stored text, with recognised cadence phrases localized, and reports
`content_locale` when its language is evident; the portal then shows "Written in Spanish
by your care team" (or English). Scheduling is unchanged.

## Existing data

| Data | Treatment | Why |
| --- | --- | --- |
| Superseded and approved plan versions (history) | Unchanged | They are the approval record. |
| Currently active approved plans (2 synthetic patients) | A *bilingual refresh* draft is opened through the normal draft path, with AI translations filled in; the clinician approves it in one review. Today keeps the current wording, labelled, until then. | Marking AI text as clinician-approved by migration would fabricate an approval (`docs/demo-environment.md` forbids ad hoc approvals). |
| Open drafts (1, 5 items) | Regenerated with both languages; this is the end-to-end test of the new review. | Drafts are not patient-visible. |
| Legacy medications (23, not plan-linked) | No data change. Recognised cadence phrases render in either language at read time; names and doses unchanged. | No clinical content changes and no backfill to get wrong. |
| Legacy obligations (2) | Shown as stored with an *original language* label. | Free text with no approval path. |
| Seed fixture | Unchanged. | Seeded medications use the recognised cadence vocabulary. |

`backend/scripts/refresh_bilingual_care_plans.py` reports, then applies only a reviewed
report (guarded by its SHA-256): an open draft gets its missing language drafted, and an
approved single-language plan gets a normal generation request. Neither approves anything.
The 2026-10-10 dry run against the synthetic environment proposed exactly two actions
(one open draft with 5 items, one approved plan with 4). Applying migration 049 or the
refresh to any remote environment requires explicit authorization.

## Language uniformity fixes in the same change

- Done here: language-setting copy describes the new behaviour; Today and Reminders tag
  wording with its language and label older single-language items.

Also done here: record titles. Migration `050_document_display_titles.sql` adds
`documents.display_title` (`{"en-US", "es-MX"}`) and a bounded attempt counter. After
summaries, the worker drafts a short title in both languages from the document's existing
summary and extracted topics on the explanation route; titles with digits or more than a
few words are rejected and the patient's name is never sent. Records shows the title in the
reader's language and the clinician lists show the English title, both keeping the file name
as the source identity; a missing column before migration is tolerated. The clinician
patient detail shows approved English wording for medications and activities.

Follow-ups (tracked as LOC-002): notifications and Today error text from codes; sign-up saves
the guest language and the server renders `lang` without an English flash; one label set
for the two locales; a patient language chip in the clinician header and per-message
language on history; cached per-locale document explanations; one Spanish register (*tú*) across records,
reminders and symptoms copy.

## Acceptance

1. A draft generated from Spanish sources shows Spanish (*From source*) and English (*AI
   translation*) side by side; approval is blocked until each item's check is ticked.
2. After approval, switching the patient between `en-US` and `es-MX` changes Today,
   Reminders and care-plan details immediately, with no re-review and no mixed languages.
3. A translation that changes a number, unit or drug name is rejected and blocks approval.
4. Reminder scheduling is unchanged for existing frequency text in either language.
5. Legacy single-language items show an *original language* label; no item shows text in
   the other language without one.
6. Audit events record which locale was the source and whether the other was AI-drafted
   or clinician-edited.
7. Backend pytest, Ruff, mypy; both portals' lint, typecheck, tests and build; migration
   validation; seed dry run and idempotency.

## Verification — 2026-10-10 (synthetic environment)

Authorized by the requester: migration 049 applied through `scripts/apply-supabase-migrations.sh`
(only 049 was pending), the refresh applied with report hash `b710b06b…c92f`, and one local
run of the document-ingestion worker.

- Refresh: the open draft's 5 items received AI drafts that all passed validation; the second
  patient's approved plan produced a new bilingual draft (4 items) for review. No approved row
  changed.
- Review and approval: in the clinician portal, the duplicate hydration proposal from a repeat
  upload was removed in favour of the carried-forward item, each remaining item's English and
  Spanish wording was checked against its source, and version 4 was approved. Projections hold
  both languages; the audit event records Spanish as source and English as AI draft per item.
- Patient: Today and Reminders render the same activities in English and, read-only with the
  saved language overridden, in Spanish, with identical completion state. Before approval, the
  Spanish-only active plan showed "Written in Spanish by your care team" in the English app.
- Known: `verify-supabase-schema.sh` counts 59 ledger rows against this branch's 58 files; the
  extra row predates 049 (`047_adr_patient_information_loop.sql` from another branch).
- Record titles: migration 050 applied with authorization; three worker runs titled all 18
  eligible documents on the first attempt (for example "Hydration instructions" /
  "Indicaciones de hidratación"). Records and the clinician Documents list show them with
  the file name kept; the clinician patient detail shows English wording.
