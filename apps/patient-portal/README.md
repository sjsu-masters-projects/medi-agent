# Patient Portal

Next.js PWA for MediAgent patients: Today, Records, Chat with Nora and the care team,
Visits, Reminders and Profile, in en-US and es-MX.

Symptom-intake region labels reflect the saved state (private draft, confirmed,
cancelled or safety-interrupted), matching the visible localized heading.

Chat preserves saved turns through offline/online reconnection without automatic
resends. Visible healthy sockets use the existing ping/pong protocol to detect
stale OPEN connections; hidden-page timer throttling is not treated as failure.
Records counts appear only after a successful read, not as an invented zero while
loading or unavailable. Agenda reminder links retain 44px touch height.

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

ADR care-team follow-ups label the symptom as quoted original wording and the
medicine name as recorded. Spanish interface text does not imply that a stored
English symptom or medicine name has been translated. The same copy applies to
pending forms and read-only answered/closed history; safety questions and answers
are unchanged. New Spanish labels await the tracked bilingual wording review.

- Sessions are shared across tabs (one refresh at a time, sign-out in any tab signs out all).
  Defaults: 30 days idle and 90 days absolute, silent with a login notice; override with
  `NEXT_PUBLIC_PATIENT_SESSION_IDLE_MINUTES` / `NEXT_PUBLIC_PATIENT_SESSION_MAX_HOURS`.
- Language: the proxy resolves entry query, then the `patient-portal.locale` cookie, then
  `Accept-Language`, so server rendering always knows en-US or es-MX (the root layout is
  dynamic on purpose). The saved Profile preference seeds the cookie; any sign-out clears it.
- Notification polling is throttled with backoff and keeps the last data when a read fails.

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

Records has a direct Refresh control. Rows and details label recorded source-review
status in words; absent status is unavailable, and clinician upload is not inferred
approval. Source approval never approves the AI explanation or changes treatment.
Document icons use one neutral tone, with different shapes for document types and
a file icon for unknown types regardless of uploader. Type, origin and review
status remain explicit text rather than meanings patients must infer from color.
The detail sheet keeps one sticky close control, with Escape and focus return.

Document explanations follow the saved Profile language and request a structured
presentation of the stored summary, including legacy summaries of unknown language.
The UI uses a short opening and spaced detail bullets without repeated group headings,
omitting unsupported sections. A quiet AI label and one safety notice identify its scope. Only
the current document/locale/account response may display or supply text to speech
and focused chat; failures offer Retry and never display the previous language.
Audio leaves the explanation visible and stops on context changes. This presentation
does not rewrite the source or stored summary. Deploy the matching backend before
the portal; an older server's unstructured response is treated as unavailable.
Validated presentations are saved per document, language, exact stored-summary
fingerprint and format version (migration 102). Reopening fetches authorized saved
content instead of another AI generation. A changed source/version or missing/invalid
presentation requires generation; failures remain retryable. Closing the modal does
not discard generation already running on the server. Apply 102 before releasing
this backend; missing schema fails visibly, without per-view generation fallback.
Processing polling follows an explicitly pending summary after extraction finishes.
Background polling keeps source preview URLs steady; explicit Refresh renews them.

Record origin is explicit. A patient may remove only their own pending, unused upload
after server eligibility and confirmation. Reviewed, used, rejected, processing and
clinician-uploaded sources cannot be removed through the patient route. The server
rechecks under the evidence fence, records a minimal removal audit and removes unused
metadata/candidates atomically before best-effort private storage cleanup. Unknown
permissions fail closed. A lost response can be retried safely for the same upload.

Records shows running work with motion (REC-001-MO). The explanation shows moving
dots, a row-shaped placeholder and, after 15 seconds, a note to read the original.
Every document still being read is checked, including ones already processing on
load: 3s→30s backoff with the current session, paused while the tab is hidden, and
stopped after 10 minutes of visible checking as a static **Still processing** with
Refresh. A document that finishes while the page is open gets a neutral highlight and
one polite announcement. Upload shows a preparing phase, then uploading; upload errors
are separate from list-loading errors and offer **Choose another file** or **Refresh
records**. Removal closes the record, the row leaves, and a neutral notice confirms
it; while removal eligibility is checked neither removal nor request is offered. The
record sheet uses `Modal`'s opt-in `animateExit`, and pull-to-refresh shows its mark
only for the gesture (`indicateBusy={false}`). Reduced motion disables the animation
but not the status text.

Other records offer **Report an issue** or **Request removal or correction**. This opens
`/chat?view=care-team&record_request=<id>` and requires recipient selection, an owned
document read, **Prepare request**, and the normal explicit **Send message**. Existing
or uncertain message drafts are preserved. This is an ordinary private care-team
message, not an automatic chart change or a separate tracked review request.
Migration `101_patient_document_removal.sql` must be applied before enabling direct
removal; unavailable or older backends retain the request path without a delete fallback.

An opened record shows **Test results / Resultados** from
`GET /api/v1/documents/{id}/results`, requested only for that opened document (not
for list rows, and not while it is still being read or is a duplicate). Lab results
are grouped by printed panel and measurements are listed separately. Names, values,
units, ranges and dates are shown exactly as printed. The only client logic is the
status chip: the report's own flag first (High, Low, Outside range, Critical), else
its own printed range; within range shows no chip. Critical adds "Contact your care
team today." Unreviewed rows are marked, and the section states that results were
read automatically and that the care team will review them. An empty response
renders nothing; a failed request shows a retry.

The authenticated layout shares one patient profile across all screens. The saved
language selector is in Profile, not a repeated banner. Saving a language updates
navigation, controls and explanatory UI, and switches care-plan items to their wording
approved in that language (LOC-001); it never machine-translates clinical instructions or
historical messages. Failed saves
retain the prior preference. Guest entry screens carry a separate language choice
until a profile exists; chat has no competing persisted language setting.
The locale-only `patient-portal.locale` cookie supplies the server document language.
The request proxy accepts supported `lang` queries on entry routes and carries that
locale into the same response, including `html lang`. Existing guest choices stored
only in local storage resolve before translated content is shown and then populate
the cookie. Authentication remains in local storage; authenticated screens wait for
the saved patient profile before rendering. A loaded profile and successful language
saves refresh the cookie; failed saves retain the existing preference. This cookie
is a presentation hint, never an identity or authorization source. First visits
without a hint briefly defer content until the browser locale is resolved.
Today stores stable failure keys and resolves feedback in the current language,
including after a language switch; backend error prose is not displayed. Notification
load/write feedback already follows the same localized-key pattern.
Today associates loaded feed data with the requested saved locale. A language change
holds activity content until that locale's response arrives; an older response or
failure cannot replace the current request. A failed language-specific load shows
retry feedback without displaying the previous locale's instructions. Refreshes in
the same locale retain their existing activities. This changes presentation only;
adherence writes, schedules and approved wording remain owned by existing APIs.
Today's symptom shortcut opens Nora directly, without an intermediate timeline.
The existing Symptoms URL remains a compact mobile-friendly handoff and explicitly
says that patient symptom history is not connected; it must not display invented
example reports or imply that opening chat saves or escalates a report.
UI review evidence: `docs/evidence/portal-ui-ux-review-2026-10-10.md`.

The reference-led patient redesign is tracked in
[UX-002 verification](../../docs/evidence/ux-002-overhaul-verification.md) and the
[portal design](../../docs/features/portal-design.md).
It keeps clinical wording and service contracts unchanged; a confirmed completion
may show brief visual feedback, while failed/uncertain saves and reduced motion
do not. Refresh buttons remain available alongside pull-to-refresh. Nora keeps
Enter-to-send and Shift+Enter for a new line; human conversation input retains its
existing multiline behavior.

Interface text avoids technical noise (UX-007). Records show who uploaded a document
once and a clinic name only when one is recorded; the original file name sits in
the Source document section. Record-correction requests name the document and date
added, never the database id. Chat times use the saved time zone, and the
"Original language" label appears only when a message is in the other language or
its language is unknown. Time zones read as names ("Pacific Time · Los Angeles"),
through `content/timezone-label.ts`. See the
[UX-007 spec](../../.agent/specs/ux-007-interface-noise.md).

## Care team conversations

**Ask about a plan activity** opens an optional approved-activity picker in the
private composer. It does not choose a clinician or send automatically. The
attachment stays bound to an uncertain-send retry; it clears after a confirmed
send. Saved messages show the referenced approved wording separately from human
text and label replaced activities as historical. Neither the question nor the
clinician's reply changes the plan or reminder schedule (COM-002).

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

See [the scheduling design](../../docs/features/scheduling.md)
for the synthetic acceptance steps.

Confirmed/scheduled cards now include **Add to calendar / Agregar al calendario**.
Each click checks the current appointment and authorization before downloading an
`.ics` file. It contains a generic localized title, exact start/end and location;
clinical reasons and notes are omitted. It is a one-time copy: later changes and
cancellations do not sync, and the calendar app uses its own display timezone.
Failed downloads keep the visit list visible with a translated retry notice.
See [Slice 6 verification and click-through](../../docs/features/scheduling.md).

## In-app notifications

Authenticated headers include a compact bell and an accessible notification sheet;
`/notifications` provides the full All/Unread history. Notification copy and dates
follow the saved language and timezone. A visit cancelled by the care team shows as Cancelled with the reason (draft Spanish wording pending review). Human messages are not translated and
clinical instructions use only approved wording. Opening the sheet does not mark
everything read or approve care. Exact-resource links open Records, Visits, Today
or the addressed private care-team conversation.

One shared cache refreshes once a minute while visible and on focus, preserving
lists after network failure. Unavailable counts are not shown as zero. Each loaded
page retains a server-signed viewing cutoff; marking displayed items read excludes
concurrent arrivals. No new email, SMS or push delivery is introduced. See
[NOT-001](../../docs/features/messaging-and-alerts.md) for the contract and tests.

## Clinic on visits and notifications

Appointment and offer rows carry `clinic_id`/`clinic_name` (the clinic of the
care-team link the visit was made under), mapped to `clinicId`/`clinicName` in
`src/services/appointments.ts`. Visit cards and offer cards show "at <Clinic>"
(en-US) or "en <Clinic>" (es-MX) as muted secondary text under the date/title,
and hide the line when the name is unknown. Notification items show their
`clinic_name` as small muted text under the title. All lines wrap on narrow
screens. The es-MX wording is a draft pending native review.

## ADR care-team follow-up

When an assigned clinician needs more detail on a draft ADR assessment, the patient answers up to
three retrospective questions about a prior clinician-directed dose change, a prior restart, or a
similar prior reaction. The form says not to restart, stop, or change a medicine to answer, asks for
a description of known yes/no answers, and requires a final confirmation before sending.

**Route.** `/chat?view=follow-up` opens the structured Care Team follow-up view without a thread or recipient step. The
optional `request` parameter opens one request in any state and wins over `assessment`, which opens
the newest request for that assessment. With neither, the view lists every pending request.
Notifications link here by assessment (or by request), and the entry rows link to the bare route.
Back returns to **Care team messages**. The view carries the human-message emergency and "not
continuously monitored" notice; it does not use Nora's AI warning. Signed-out
visits follow the normal sign-in redirect and return to the same URL.

**Entry rows.** A row appears under **Care team messages** in the chat inbox and on Today, only while
at least one request is pending. It is never rendered as Nora content. It is hidden while loading,
on a load error, or when nothing is pending, because the view itself reports errors. The count
refreshes on focus and does not poll.

**Endpoints.**
- `GET /api/v1/patients/me/adr-information-requests` lists pending requests (used by the entry rows).
- `GET /api/v1/patients/me/adr-information-requests/overview` returns `selected`, `pending` and
  `recent` for any state. It takes `request_id` or `assessment_id`; both together return 422, and a
  missing or another patient's ID returns the same 404.
- `POST /api/v1/patients/me/adr-information-requests/{request_id}/respond` saves the confirmed answers.

Patient responses carry no Naranjo score or causality.

**States.** Loading skeleton; error with retry; not found; pending form; answered, as a read-only
summary of the patient's own answers and date; closed, with a link to the newer request when one
exists; empty; and recent history (up to 5 answered or closed requests from the last 90 days).

**Localization.** All strings come from `src/content/adr-follow-up-copy.ts` in en-US and es-MX,
guarded by a key-parity test. The clinician's message, symptom and medication name are shown
verbatim. ADR Spanish wording received requester-authorized LLM-assisted demo
meaning-and-safety review on October 19; this is not professional translation validation.

**Errors and drafts.** The server error code is mapped to localized copy: `ADR_REQUEST_CLOSED`
shows the closed state, and server message text is never displayed. Unsent answers live only in
component state and are lost on reload; nothing is written to browser storage.

**UI standard.** Built from shared primitives and design tokens, with 44 px touch targets and a
visible focus ring on the label of each visually hidden radio and checkbox.

- The browser never writes ADR assessment or audit tables directly; the backend owns the atomic
  response, reassessment, notification, and audit transaction.

### Confirmed symptom draft panel

Nora keeps its composer visible while the conversation and intake content scroll
within the available height. The current portal hides bottom navigation while a
conversation is open. Reconnects retain the visible conversation while history
recovers. Streaming follows the latest reply without animated scrolling only
when the reader is near the bottom; scrolling up pauses following, and returning
to the bottom resumes it. Sending a typed message or selecting another conversation
resumes following. Short-lived reconnects retain their retry count; the count resets
only after a socket stays open for five seconds, so repeated initialization failures
stop after five retries. A database without migration 060 omits saved symptom context
and marks it unavailable to Nora's record tool; it never falls back to unconfirmed
reports. This does not activate guided intake. Initial draft-read failures
offer reload feedback; only an uncertain mutation uses the action/save recovery
message. Loading a draft does not imply that a report was submitted.

Nora places the private intake panel after the latest chat turn; human message threads do not mount it. The panel recovers
the latest owned state for the selected Nora conversation by REST on authentication/reconnect signals, asks paired-locale
library questions, and supports unknown/declined, corrections, cancellation, review
and consent-based confirmation. It stores pending action identities only in memory;
clinical draft content is never written to browser storage or mirrored into chat.
A lost write response retains its exact identity for reload/retry. Account switches
abort pending reads and reject stale responses. Controls use localized labels,
44-pixel button targets and focus the next unanswered field without stealing chat focus.

Answer the current question in Nora's main composer by typing or dictation. In
hands-free mode prompts are read aloud and listening resumes after playback;
local pause detection ends an answer after speech and 1.8 seconds of silence when
Web Audio is available (15 seconds of initial silence; 60-second recording limit).
The microphone button remains a manual stop. No analysis samples are stored;
the portal permits microphone access only for its own origin, and the browser's
microphone permission is still required. Camera and geolocation remain disabled.
Unknown/skip and explicitly accepting a source suggestion are supported. Ambiguous
numbers need clarification. Private STT recordings are not stored as chat audio;
private TTS has no chat message ID. Late recordings cannot answer a different
revision. Detailed fields remain available as a fallback. Read the preview, select
consent and press **Confirm and share**; spoken assent never submits it.

The backend chooses the active
[question release](../../backend/src/app/intake/question_library/README.md). The checksum-pinned, applied
`071_confirmed_symptom_handoff.sql` adds durable ADR and review notices; the existing
retry worker must run. Follow the
[October 17 verification record](../../docs/evidence/pat-002-b-acceptance-2026-10-17.md) and
[coordinated rollout](../../docs/pat-002-b-rollout.md).
The saved patient symptom timeline remains PAT-002-C.

Chat results card: an assistant message may carry `attachments` of type `document_results`, built by the server from the cited document's extracted results (never from the reply text). The chat shows them under the reply: critical results first with a contact-your-care-team line, out-of-range results with chips, the rest behind a toggle, and a link to the document in Records.


## Readability

Operational text, focus indicators and reading widths follow the
[portal design rules](../../docs/features/portal-design.md). Explanations keep paragraphs and bullets within a 65ch reading column while source previews keep their available width. Keyboard focus remains visible on fields and actions.
