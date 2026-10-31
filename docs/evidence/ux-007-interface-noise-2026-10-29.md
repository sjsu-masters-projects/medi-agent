# UX-007 — Interface noise removal

Local implementation on `fix/patient-records-clarity`, October 29, 2026.
[Spec](../../.agent/specs/ux-007-interface-noise.md). Presentation only: no API,
schema, permission, review-gate or clinical-wording change; no commit, push,
merge, deployment or database change.

## How the findings were gathered

Three read-only code audits covered the clinician review surfaces, the remaining
clinician screens (ADR, MedWatch, scheduling, messages, settings) and every patient
screen. They looked for rendered ids, raw codes, version strings, JSON, raw server
errors, jargon, unformatted time zones and repeated labels. Findings that need new
backend fields are listed as deferred in the spec rather than approximated.

## Deliberately kept

- LOC-003's "which model translated this" in the translation note (decisions 23, 25).
- PLAN-002's "Version N" plan labels on Today and plan details.
- Records safety and AI-explanation notices, source-review labels, approval seals.
- FDA section letters, clinic join and invite codes, the MFA manual key.
- 401 error text, which sign-in screens map themselves.

## Local checks

From `apps/patient-portal`:

- `npm run lint`: passed.
- `npm run typecheck`: passed.
- `NODE_OPTIONS=--no-experimental-webstorage npm test -- --run`: **97 files,
  1,077 tests passed**.
- `npm run build -- --webpack`: passed.

From `apps/clinician-portal`:

- `npm run lint`: passed.
- `npm run typecheck`: passed.
- `NODE_OPTIONS=--no-experimental-webstorage npm test -- --run`: **88 files,
  849 tests passed** (includes the new `error-text.test.ts`).
- `npm run build -- --webpack`: passed.

From the repository root: `git diff --check` passed, and
`node scripts/check-docs.mjs` on the five changed documentation files reported no
link or fence errors.

## Tests changed or added

Updated because they asserted the old noisy text: clinician
`patient-documents-panel`, `smart-import-review-panel`, `patient-timeline`,
`risk-explanation`, `dashboard-presentation`, `adr-review-card`, `adr-case-page`,
`medwatch-draft-card`, `form-3500-preview`, `email-invitations`,
`appointments-page`, `care-conversations`; patient `records-page`,
`record-request-composer`, `care-conversations`, `explanation-reading`,
`chat-page`, `chat-results-card`, `symptom-intake`, `reminder-settings`.

New assertions:

- Clinician API errors: 5xx details, framework phrases, bare codes and empty bodies
  become plain status copy; a readable 403 message is kept.
- `readableError`: code errors and non-errors fall back to the screen's sentence.
- External records: the FHIR type chip is gone; ids and the extractor version sit in
  a closed Technical details; a document source names its cited page and links to
  the document row; the raw record is in a closed disclosure.
- Timeline: no record ids in accessible names; source and field names in words.
- Risk explanation and MedWatch: rule version, save counter and draft id are in
  closed Technical details; "Last saved" is visible.
- Invitations: delivery states no longer say "Provider".
- Records: the uploader appears once; no placeholder clinic; the original file
  name is in the Source document section.
- Correction requests: the database id is not written into the patient's message.
- Chat: today and yesterday are judged in the saved time zone; no language label
  under a message already in the patient's language.
- Symptom intake: record details are labelled in words without internal keys.

## Remaining acceptance

No browser was available. Still required: visual review at patient 360/390px and
clinician 1280px with long Spanish text, screen-reader wording, LOC-001 review of
the new es-MX strings (records-copy "Original file", duplicate/no-details copy,
symptom-intake time zone, fallback and record-detail labels, "Tú"), peer review and
deployed acceptance. Automated tests use mocked APIs and do not establish how the
screens look or behave live.

October 30 follow-up: [local review corrections and final verification](ux-007-review-2026-10-30.md)
on the separate `fix/portal-interface-clarity` branch supersede the implementation
checkpoint above. Visual, Spanish-copy and deployed acceptance remain separate.
