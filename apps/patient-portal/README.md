# Patient Portal

Next.js PWA for MediAgent patients: Today, Records, Chat with Nora and the care team,
Visits, Reminders and Profile, in en-US and es-MX.

## Local development

From `apps/patient-portal`, install dependencies and run the portal on the default port
3000 (backend API at `http://127.0.0.1:8000`):

```bash
npm ci
npm run dev
```

Lint, typecheck, tests and build:

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

On Node 26, if auth-session tests fail because localStorage is unavailable, run
`NODE_OPTIONS=--no-experimental-webstorage npm run test` so jsdom supplies browser storage.

## Behaviour notes

Care-team roles are displayed as readable en-US/es-MX labels rather than raw stored
codes; unknown roles use generic care-team copy. API transport recovery retries GET/HEAD
once after 100–249 ms, honors cancellation, and never retries HTTP errors or writes.
Today localizes connection/save errors using the loaded profile language. An uncertain
save leaves the task pending; refresh to inspect persisted state before a manual retry.
Today also localizes its schedule, progress, task actions, approved-plan details,
and all barrier choices. Dates use the saved patient timezone; feed clock values
are already patient-local and are not shifted into the browser timezone. Clinical
titles, instructions and doses remain exactly as reviewed, not translated by UI copy.

Records distinguishes duplicate-skipped uploads from empty successful extraction.
The duplicate explanation is static en-US/es-MX copy; switching its language does
not invoke a model or carry that reason into Nora as a clinical summary.

The authenticated layout shares one patient profile across all screens. The saved
language selector is in Profile, not a repeated banner. Saving a language updates
navigation, controls and explanatory UI, and switches care-plan items to their wording
approved in that language (LOC-001); it never machine-translates clinical instructions or
historical messages. Failed saves
retain the prior preference. Guest entry screens carry a separate language choice
until a profile exists; chat has no competing persisted language setting.
Today's symptom shortcut opens Nora directly, without an intermediate timeline.
The existing Symptoms URL remains a compact mobile-friendly handoff and explicitly
says that patient symptom history is not connected; it must not display invented
example reports or imply that opening chat saves or escalates a report.
UI review evidence: `docs/portal-ui-ux-review-2026-10-10.md`.

The reference-led patient redesign is tracked in
[UX-002 verification](../../docs/ux-002-overhaul-verification.md) and the
[redesign spec](../../.agent/specs/ux-002-reference-redesign.md).
It keeps clinical wording and service contracts unchanged; a confirmed completion
may show brief visual feedback, while failed/uncertain saves and reduced motion
do not. Refresh buttons remain available alongside pull-to-refresh. Nora keeps
Enter-to-send and Shift+Enter for a new line; human conversation input retains its
existing multiline behavior.

## Care team conversations

In Chat, choose **Care team messages**, then explicitly select a linked clinician.
Each clinician has a separate thread labelled with their clinic. Nora remains a
separate AI conversation; operational alerts are not human replies. The chooser,
composer, notices and recovery states support en-US and es-MX.
Genuine older human messages remain in a separately labelled, read-only historical
archive. They are not migrated into addressed threads, attributed to the selected
clinician, or given a reply route. Operational alerts remain filtered out.

Conversation requests use the authenticated `/api/v1/care-conversations` contract.
Messages load in pages of 50 with server cursors. The visible inbox and selected
thread poll every 15 seconds. Inbox refresh updates recipients and removes revoked
choices while preserving selection and drafts; unread
counts come from the server. Read markers reference the last displayed message ID.
An uncertain send preserves its text and UUID for an explicit retry, including
thread/view switches. The pending body is locked until that retry resolves.
Definitive validation rejection preserves text for editing. An idempotency mismatch
warns that the prior message may exist and requires confirmation to prepare a new
send key; preparation does not send the message.
Drafts are held in memory; reloading or signing out clears them.
These messages are not continuously monitored; the screen carries a 911 notice.

Shipped in #139 (COM-001-B) with live bilingual persistence verified.

## Visits scheduling

Visits shows appointment times and response deadlines in the patient's saved
timezone and `en-US`/`es-MX` locale. Slice 5 adds expired history without response
controls and translated overlap/expiry/past-time messages. Failed actions keep the
list visible; a saved response followed by a failed refresh has a distinct notice.
Visits refreshes at pending deadlines and on browser focus. The server/database
remains authoritative for expiry and booking conflicts.

See [the scheduling design](../../.agent/specs/sch-001-appointment-scheduling.md#14-slice-5--booking-conflicts-and-proposal-expiry)
for the synthetic acceptance steps.

Confirmed/scheduled cards now include **Add to calendar / Agregar al calendario**.
Each click checks the current appointment and authorization before downloading an
`.ics` file. It contains a generic localized title, exact start/end and location;
clinical reasons and notes are omitted. It is a one-time copy: later changes and
cancellations do not sync, and the calendar app uses its own display timezone.
Failed downloads keep the visit list visible with a translated retry notice.
See [Slice 6 verification and click-through](../../.agent/specs/sch-001-appointment-scheduling.md#15-slice-6--one-time-calendar-export).

## In-app notifications

Authenticated headers include a compact bell and an accessible notification sheet;
`/notifications` provides the full All/Unread history. Notification copy and dates
follow the saved language and timezone. Human messages are not translated and
clinical instructions use only approved wording. Opening the sheet does not mark
everything read or approve care. Exact-resource links open Records, Visits, Today
or the addressed private care-team conversation.

One shared cache refreshes once a minute while visible and on focus, preserving
lists after network failure. Unavailable counts are not shown as zero. Each loaded
page retains a server-signed viewing cutoff; marking displayed items read excludes
concurrent arrivals. No new email, SMS or push delivery is introduced. See
[NOT-001](../../.agent/specs/not-001-notification-centre.md) for the contract and tests.

## ADR care-team follow-up

The chat page also hosts structured follow-up requests for an existing draft ADR assessment.
The patient may answer only retrospective questions about a prior clinician-directed dose change,
a prior restart, or a similar prior reaction. The form explicitly says not to restart, stop, or
change a medicine to answer, requires a description for known yes/no answers, and requires a final
confirmation before sending.

- `GET /api/v1/patients/me/adr-information-requests` loads pending patient-safe requests.
- `POST /api/v1/patients/me/adr-information-requests/{request_id}/respond` saves the confirmed
  answers and returns the deterministic Naranjo rescore.
- The browser never writes ADR assessment or audit tables directly; the backend owns the atomic
  response, reassessment, notification, and audit transaction.

### Confirmed symptom draft panel

Nora keeps its composer above the bottom navigation while the conversation and
intake content scroll within the available height. Initial draft-read failures
offer reload feedback; only an uncertain mutation uses the action/save recovery
message. Loading a draft does not imply that a report was submitted.

Nora mounts the private intake panel; human message threads do not. The panel recovers
the latest owned state by REST on authentication/reconnect signals, asks paired-locale
library questions, and supports unknown/declined, corrections, cancellation, review
and consent-based confirmation. It stores pending action identities only in memory;
clinical draft content is never written to browser storage or mirrored into chat.
A lost write response retains its exact identity for reload/retry. Account switches
abort pending reads and reject stale responses. Controls use localized labels,
44-pixel button targets and focus the next unanswered field without stealing chat focus.

A real approved library and authorized schema rollout are required to activate this
screen. With the current pending-review manifest, start fails closed without saving a
report. Follow [the synthetic journey and verification record](../../docs/pat-002-b-acceptance-2026-10-12.md).
The saved patient symptom timeline remains PAT-002-C.
