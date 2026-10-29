# REC-001-UX — Patient record clarity

Requester-approved October 28, 2026; branch `fix/patient-records-clarity`.
Extends REC-001 presentation and LOC-001's saved-language contract.

## Behavior

- Replace Records' single-action overflow menu with an accessible direct Refresh
  control; retain pull-to-refresh, upload, loading and error recovery.
- Show recorded source-review status in words in each row and detail. Pending,
  approved and rejected refer to the uploaded source, never treatment approval.
  Clinician upload is an origin, not evidence of review; absent status stays unknown.
- Label explanations as AI-generated and preserve the existing care-plan boundary.
- Follow the saved en-US/es-MX preference without a second language selector.
  Do not assume the language of legacy cached summaries. Request a bounded,
  validated structured presentation in the selected locale. No source or stored
  summary is rewritten; no source backfill. Patient removal uses migration 101;
  saved explanation presentation uses migration 102 as described below.
- Organize source-supported overview, medicines, results, conditions, allergies,
  other instructions and existing suggested questions into semantic response sections.
  Render a short opening and readable detail bullets without repeated visible group
  headings; keep supplied questions separate from factual details. Omit
  empty sections. Do not invent instructions, questions, approval or clinical facts.
  Preserve number/unit counts and negation through the presentation/translation
  step; reject clear language mismatches, malformed or changed output rather than
  falling back to stale text. These checks do not establish clinical accuracy or
  guarantee complete semantic equivalence.
- Keep current content visible during audio playback; read only the displayed,
  available explanation. Stop playback on close, document, account or locale change.
- Reject late responses after document/locale/account changes. Pending and failed
  presentations cannot supply a previous explanation to speech or document chat.
- Review follow-up: watch both extraction and the explicit pending/processing
  stored-summary lifecycle, so a document is not left waiting forever after parsing
  completes. Reset the Records workspace on account changes and ignore superseded
  list refresh responses. Keep singular record counts grammatical in both locales.
- Keep the sticky top close icon, Escape, focus trap/return and backdrop dismissal. Remove
  the redundant footer Close button; retain other existing record actions.

## Record icon clarity — October 29 follow-up

Use neutral document-type tiles in both portals. Shape identifies document type;
unknown types use a file icon regardless of uploader. Keep type and uploader in
text. File-format chips are neutral too. Explicit source-review badges carry
approval meaning: Awaiting review, Source approved, Source not approved, or an
unavailable state. Completed parsing is neutral and never implies approval.
Preserve existing review permissions, metadata, actions and clinical gates.
Verify both portals' lint, typecheck, tests and production builds, plus record and
review-queue interactions. Visual and deployed acceptance remain separate.

## Acceptance

Automated: pending/approved/rejected/missing source status, direct Refresh,
readable semantic content without repeated headings, both locales, old Spanish summary requested in
English, missing/failed/duplicate states, changed-number/malformed output refusal,
authorization before presentation, rapid locale/document changes, close during a
request, available-text-only speech/chat, and unchanged source metadata.

Run patient lint/typecheck/tests/build, focused backend API/service tests, Ruff and
mypy. Inspect synthetic layouts at 360/390px and desktop, long Spanish wrapping,
keyboard close/focus and error recovery where local tooling permits. Record exact
results and distinguish local checks from deployed acceptance. Peer review and
deployment remain separate.

## Rollout and limits

The optional `structured: true` request on `POST /documents/{id}/explain` returns
localized `sections` plus their joined plain-text `summary`. Existing unstructured
callers retain their prior contract. Presentation reuses the registered explanation
workload, its kill switch, provider fallback and per-attempt budget; at most two
format-validation attempts. Review follow-up October 29: save validated presentations
in a service-only cache (migration 102), keyed by document, reader locale, exact
stored-summary fingerprint and presentation version. Reopening checks document
ownership and existence before reading the cache; deleted/foreign sources cannot
return cached content. Regenerate only on a miss, changed summary/version or invalid
saved output. Share an in-flight generation within an API process so closing and
reopening during generation does not restart it. Concurrent cold requests on separate
API replicas can still generate independently. Failed output is never cached.
The two locales replace their own cache entries, bounding storage per document;
document removal cascades the presentation cache. Missing cache schema fails visibly
without silently returning to per-view generation. Preserve loading/error/retry.
Apply migrations 101/102 with exact hosted-target authorization before releasing the
matching backend, then deploy the portal. Neither migration is hosted-applied here.
New Spanish interface wording is draft for
LOC-001 review. Automated provider tests are mocked; no live-model or deployed
acceptance is claimed. [Local evidence](../../docs/evidence/rec-001-ux-2026-10-28.md)
records checks and remaining manual acceptance.

## Patient removal and reading refinement

Requester-approved follow-up October 28, 2026 (REC-001-RM), on the same branch:

- Label origin as Uploaded by you / Uploaded by your care team. Other or missing
  uploader identity never grants removal permission.
- Only the signed-in patient's own upload with pending source review, no recorded
  clinician decisions, clinical/care-plan use, shared storage objects or active
  processing may be removed.
  Unknown permission or a failed permission read fails closed. The server rechecks
  under the established patient evidence fence and document lock, removes unused
  candidates and document metadata atomically, and retains a minimal removal audit.
  Storage cleanup is best-effort only after the successful transaction. Replays
  of successful owned removals are idempotent. A refused removal changes nothing.
- Reviewed, rejected, used and clinician-uploaded records offer a care-team request,
  not direct deletion or automatic withdrawal. Requests open the existing private
  human-message flow, recheck owned document metadata, require explicit recipient
  selection and Send, and preserve unrelated/uncertain message drafts. They do not
  automatically send, change the chart or imply a separate tracked request status.
- Use a short opening description and spaced, plain-language detail bullets without
  a heading before every group. Keep semantic data behind the presentation and
  preserve all supported important facts, uncertainty and source attribution. Keep
  suggested questions separate from factual details without adding new questions.
- Consolidate the explanation's visible introduction to a quiet AI label and
  read-aloud control; remove the Document explained title and redundant introductory
  prose. Retain the safety boundary once, after the content.

Acceptance covers forged/foreign/clinician/reviewed/used/processing removal attempts,
concurrent review and repeated removal, unchanged clinical truth on refusal, retained
removal audit, RPC least privilege, source ownership display, explicit message
handoff with protected drafts, and readable bilingual content without repeated
headings. Migration 101 is local-only until separately authorized for hosted use;
no remote SQL, actual patient deletion, message sending or deployment is authorized.

Implementation/local checks: [October 28 follow-up evidence](../../docs/evidence/rec-001-removal-2026-10-28.md).

## Records motion and state feedback — October 29 follow-up

Requester-approved October 29, 2026 (REC-001-MO), same branch. Scope is patient
Records and its components. Shared `Modal` and `PullToRefresh` gain opt-in props
only; other screens keep their behavior. Timings follow the UX-002 handoff motion
map (dots `ma-dot` 1.2s, enter 240ms, leave/exit 160ms, shimmer 1.6s) because the
animated reference renders client-side and could not be read. Loops run only while
work is actually in progress. Reduced motion disables every animation; status text
stays visible, and no clinical or safety wording is animation-gated.

- **Explanation pending:** animated dots beside "Preparing your explanation…", a
  row-shaped placeholder, and after 15 seconds (the chat slow-turn threshold) a
  note that the original document can be read meanwhile. The explanation enters
  with `ma-enter`. Pending and failed states still never supply text to speech or chat.
- **Document processing:** dots appear only while the page is checking. Polling
  starts for every processing document on load, not only new uploads, reuses the
  3s–30s backoff with the latest session token, pauses while the tab is hidden and
  stops after 10 minutes of visible checking. Stopped documents show a static
  "Still processing" chip, and the open record says checking stopped with a Refresh
  action. A successful Refresh resumes checking.
- **Finished processing:** a row that finishes while the page is open gets a brief
  neutral highlight (not brand green, so it cannot read as approval) and one polite
  announcement: ready, already on file, or could not be processed.
- **Upload:** "Getting your upload ready…" while care teams load, then "Uploading
  document…". Choosing a file from an open record closes it so progress is visible;
  the status area scrolls into view. New rows enter with `ma-enter`.
- **Errors:** upload validation, session and failure errors are separate from list
  loading errors. Validation offers Choose another file; an unconfirmed upload offers
  Refresh records. A failed list refresh with records shown says "Could not refresh
  records". The parse-failure action is labelled Upload another because patients
  have no processing-retry endpoint. New errors enter with `ma-enter` and are announced.
- **Removal:** while eligibility is checked, a placeholder replaces the request
  button so a removable upload cannot be routed to the request path by mistake.
  The confirmation enters, moves focus to Cancel and returns focus on cancel.
  After success the record closes, the row leaves (160ms), and a neutral notice
  "Your upload was removed." appears until the next action.
- **Layout stability:** the count line keeps the last successful count during a
  refresh; the first-load placeholder is row-shaped; the pull-to-refresh mark shows
  only for the gesture on Records.
- **Source viewer:** PDFs show a page-sized placeholder until the first page is
  drawn, then fade in; page changes dim the page and show dots until drawn. Images
  show a placeholder until loaded and the existing unavailable message on error.
- **Modal exit:** opt-in 160ms fade/slide out. The dialog role, focus trap and body
  scroll lock end immediately on close, and focus returns as before; playback stops
  on close. Reopening during the exit cancels it.

New es-MX interface strings are drafts for LOC review. No API, schema, permission,
review-gate or clinical-copy change. Acceptance: lint, typecheck, full patient
suite and production build; focused tests for resumed polling, hidden pause and
stall, upload error actions, removal gating/notice, modal exit focus, slow note and
reduced motion. Visual review at 360/390px and desktop and deployed acceptance remain.
