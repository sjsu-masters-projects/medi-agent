# UX-007 — Remove technical noise from portal text

Requester-approved October 29, 2026. Scope: user-visible text in both portals that
a patient or clinician cannot act on: internal ids, raw enum codes, version
strings, JSON dumps, raw server errors, developer jargon, unformatted time zones
and labels that repeat the same fact. Presentation only. No API, schema,
permission, review-gate or clinical-wording change.

## Rules

- Lead with what the reader needs to decide or act. Keep audit and support data
  (ids, versions, raw source records) behind a collapsed **Technical details**
  disclosure with plain labels. Do not delete stored provenance.
- Map codes to labels; an unknown code falls back to a humanized phrase, never
  `snake_case`, `null` or `undefined`.
- Name time zones (for example "Pacific Time"), not IANA ids.
- Show a server message only when it is written for people. Status-only and
  framework errors (`HTTP 409`, `Internal Server Error`) get plain copy that
  says what to do next.
- Keep required wording: safety and emergency copy, AI labels, approval seals,
  source-review labels, LOC-003's "which model translated this" (one tap away,
  decisions 23 and 25), PLAN-002's plan version labels, FDA section letters,
  clinic join/invite codes and the MFA key.

## Clinician portal changes

- API errors: plain status-based copy replaces `HTTP nnn`, 5xx details and
  framework phrases (`services/api.ts`).
- Document badges: "Processed", "Waiting to process", "Processing failed",
  "Duplicate — already on file", "Scan not readable — review needed",
  "Couldn't verify — check source". Uploader shown as "Uploaded by the patient"
  or "Uploaded by a clinician". "Candidate" jargon replaced in explanation copy.
- External records review: reconciliation states use the filter's labels; the
  FHIR resource-type chip is removed (it repeated the heading); "Source
  identifiers" becomes **Technical details** with labelled id/version lines. The
  source modal leads with readable source facts (system, record type, page) and
  keeps the raw record under Technical details. Field keys use the field labels;
  coded values without text show "code (system)"; other objects show labelled
  pairs instead of JSON. "View applied local medication" becomes "Open in chart".
- Symptom report: "Report details" keeps confirmed time, language name and
  consent; report/message ids and schema, library and rule versions move to
  Technical details. Safety result and alert values use labels.
- Timeline: plain intro, source names, labelled "Record details" rows (record id as
  the last row), no ids in accessible names, clinician date format.
- Patient header DOB and risk "Rule version" (moved to Technical details) use
  readable formats.
- ADR: answer labels ("Yes", "No", "Not known"); "Severity not reported" instead
  of `null/10`; follow-up linkage in words; "Calculated Naranjo score".
- MedWatch: "Last saved {time}" replaces "Revision N · Draft ID {uuid}" (draft id
  under Technical details); evidence field paths and earlier-draft keys use field
  labels; the approval dialog says "the version you last saved".
- Invitations: role labels; delivery states no longer say "Provider" (the email
  service), which read as the invited clinician.
- Scheduling: "Pacific Time" (form) and "PT" (history) instead of
  `America/Los_Angeles`; the id stays as a tooltip.
- Messages: one short timestamp, "You" for the clinician's own messages, no
  repeated clinic name per message (the thread header names it).
- Error text: screens that previously showed any thrown `Error.message` now show
  only API, transport and MedWatch error text (`services/error-text.ts`), else their
  own fallback, so a code bug never reaches the screen as text.

## Patient portal changes

- Records: the subtitle shows type, a real clinic name when there is one, and
  date; the origin line says who uploaded it once; no "Care team" placeholder and
  no "Uploader unavailable" line. The original filename moves from a mono line
  under the title into the Source document section ("Original file"). The count
  line drops "· 0 processing". Duplicate and "nothing to explain" copy is plainer.
- Correction requests: the prepared message names the document, the date it was
  added (in the saved time zone, omitted when unknown) and the original file name.
  The database id is no longer written into the patient's message (nothing parses
  it; it is not in the patient's words).
- Chat: times use the saved time zone, including which day counts as today. The
  LOC-001 language label appears when a message's language differs from the
  patient's or is not recorded; a message already in the patient's language has
  none. The record card shows a clinic name or "Uploaded by you" in the patient's
  language, not an internal provider string. Sources and result cards use cleaned
  titles or a reference's publisher, never raw file names or internal keys.
  Care-team messages drop the repeated clinic name and label the patient's own
  messages "You".
- Symptom intake: the consent preview names record details in the patient's
  language without raw keys; medication lines skip missing parts; the time zone
  line says "Times use Pacific Time".
- Reminders and Profile: one shared time-zone label ("Pacific Time · Los Angeles").
  Reminder clock times are unchanged (24-hour) and remain a follow-up.

## Deferred (needs backend data or a contract decision)

- Open the cited page itself. The source modal now links to the document's row in
  Documents and names the cited page, using ids already in the response; the
  Documents viewer does not yet take a page from the link.
- Coded mapping/validation warnings with a field name; display text for codings;
  RxNorm names.
- Stable error codes on endpoints that only return `detail` text.
- Uploader display names, a readable timeline event summary, structured
  `match_reason`.
- Structured editors in "Correct imported fact" instead of JSON text areas.
- A structured link from a correction-request message to its document.

## Acceptance

Both portals: lint, typecheck, full unit suites and webpack production builds.
Tests that asserted the old noisy text are updated to the new copy; new tests
cover the error mapping, label maps, Technical details placement and saved-time-
zone chat times. New es-MX strings are drafts for LOC-001 review. Visual review at
patient 360px and clinician 1280px and deployed acceptance remain.

## October 30 local review

Reviewed on `fix/portal-interface-clarity`, isolated from current main after #230
merged. Preserve source uncertainty as well as the simpler wording:

- Missing ADR follow-up metadata says the link is not recorded. A differing request
  id says another follow-up, without inferring its age or whether it happened outside
  a request. A matching id says this follow-up, not an inferred latest one.
- Timeline formatting humanizes known code fields only; filenames, medicine names
  and other source values remain exact, including dots and underscores.
- Duplicate record wording does not assume who uploaded it. Missing extracted details
  do not imply the original document has no content.
- Multi-value symptom context keeps localized labels for results, units, ranges,
  doses and dates. A single amount remains concise under its fact-type label.
- A generic conflict response does not claim another person changed the record.
- All server-failure payload shapes, including validation arrays, use the safe
  general message rather than displaying internal error details.
- The source link is labelled Open the document; the cited page is displayed
  separately because the link cannot yet open that page directly.

No backend, migration, access or approval behavior is added by this review. Existing
Spanish wording and the added field labels remain drafts for LOC-001 review.
