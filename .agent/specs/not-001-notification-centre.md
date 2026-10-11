# NOT-001 — Role-aware in-app notifications and clinician work

## Authority and delivery

University-expo synthetic workflows only. In-app first; no new email/SMS/push,
clinical decisions, automatic approval or changes to reminder timing. Preserve
Nora work on other branches. Read is not review, approval or clinical resolution.
Shared tasks follow current assignment; private messages follow their addressed
conversation only. Clinician controls are English; patient copy follows saved
en-US/es-MX preference, never translating human messages or clinical instructions.

## Portal contract

Authenticated `/api/v1/notification-centre`:

- GET root: `locale=en-US|es-MX`, `unread=false`, optional opaque `cursor`,
  `limit=50` (1–100). Returns `{items, next_cursor, read_through}`.
- GET `/summary`: `{unread_count, action_item_count}`.
- PUT `/{id}/read`: idempotent own-notification read.
- POST `/read-through`: `{read_through: string}`; marks only the authorized
  receipt IDs in the signed snapshot, never concurrently arriving notifications.
- GET `/action-items`: same item envelope, clinician only; optional `category`
  in documents/care_plans/appointments/follow_up/safety, opaque `cursor` and
  `limit` (1–100).
- POST `/action-items/{id}/acknowledge`: `{note?: string}` (max 1000);
  only barrier/safety follow-up, writes audit; not clinical resolution.

Each display item is `{id, event_type, category, title, body, created_at, is_read,
action_url: string|null, action_label, actionable, can_acknowledge,
patient_name?: string|null, clinic_name?: string|null}`. Links are server-built
local routes with authorized resource identity; private IDs are never copy.
Patient dates use saved timezone. A missing summary is unavailable, not zero.

One portal-level cache polls once a minute while visible, refreshes on focus,
stops on teardown, preserves lists on failure and rejects stale responses. Bell
opens accessible sheet/panel with All/Unread, mark read/all read and full screen.
Patient `/notifications`; clinician `/alerts` Needs attention/History with
category filters. Human Messages stays conversations; legacy alerts remain a
labelled history. Exact-resource navigation preserves existing clinical gates.

## Persistence and events

Atomic source-change event capture, durable pending delivery, unique source event
keys and idempotent recipient receipts. Sources: addressed messages, appointment
offers/responses/changes, existing reminders, care-plan draft/publication,
patient-upload review/processing, saved barriers, ADR review/information requests,
and existing persisted safety flags. Never infer confirmed ADR or replay legacy
urgent history as fresh work. Group unread message/reminder previews, preserve
events/history. Conversation read markers clear corresponding message unread.
Current source state removes resolved review tasks; newly assigned reviewers see
current shared work without private conversation-history transfer.

Appointments are classified by transition, not by the resulting status alone:
- A new offer reaches the patient once per offer group, however many slots it has.
- A patient's accept, decline, request for another time, cancel or note reaches the
  responsible clinician.
- A time or location change to a confirmed visit, and an offer's expiry, reach the
  patient.
- Siblings withdrawn when one slot is accepted, completion and no-show create
  nothing.
- An offer stops asking for a response once it is answered.
- A slot that is still proposed creates no event if its time changes; the app offers
  no way to edit a pending offer, so a new offer is the supported path.

History items keep their exact-source link (labelled "View") after they stop being
actionable, and following a link marks the item read.

Acknowledgement is per clinician: it records that this reviewer saw the item. It is not
clinical resolution and does not clear the item for other reviewers.

Appointment responses in Needs attention (requester decision, October 11):
- A confirmation is an ordinary notification and is never an action item.
- A decline, a request for another time or a cancellation is an action item for the
  responsible clinician until they acknowledge it, or until a newer appointment for that
  patient and care team exists.
- A multi-slot offer contributes one item, however many slots it had. From migration 055 the
  answer is also one notification in History and one unread; responses captured before 055
  keep one History row per slot (append only).

"Mark all read" marks every item in the signed snapshot that the reader may still see. It
skips the rest and returns `{"updated_count", "skipped_count"}`; both portals show how
many were skipped, so a revoked item no longer fails the batch.

Reads are proportional to the page shown, as in fan-out-on-write systems:
- Prepare touches only the reader's active patients. A request that finds one already
  running for that person waits for it, so the summary and lists of one refresh agree
  (migration 056).
- Lists walk the reader's receipts from the cursor in bounded windows.
- Unread and action counts come from indexes.
- Conversation read markers and legacy read flags keep `read_at` current.
- Measured at 10,000 history items: about 54 ms for a list page, against about 2 s before
  (migration 054).

Account deletion (requester decision): a deleted patient's conversations, messages,
read markers and appointment-offer history are removed with them. When a clinician is
deleted, the patient's thread is kept but unlinked, and their sent messages keep the
sender name (migration 053). Clinician deletion is still blocked by document upload and
review provenance and by SOAP annotations; that is recorded as a follow-up.

Clinician one-way messages and saved escalation notices from before conversations appear
in Messages, in a collapsed Earlier messages section. They are history only. Alerts holds
notifications only.

Notification history is never updated. It is removed only together with the patient or
account it belongs to, so account deletion and the synthetic demo reset keep working.
No role is granted DELETE. Malformed source values, such as an unparseable date or an
unknown patient time zone, make an item non-actionable; they never fail the centre.

Browser writes/event creation are denied; server API and database access both
enforce ownership/assignment. Revocation denies notification details and targets.
Existing patient notification endpoints and reminder rows remain compatible.

## Acceptance and rollout

- Atomic capture, delivery retry, duplicate and concurrent read tests.
- Patient/clinician isolation, private thread partition, revocation, browser-role denial.
- Shared review completion, pending/rejected evidence gates, unpublished drafts.
- Exact visit/document/conversation/activity destinations; stale actions suppressed.
- EN/ES, saved timezone, approved wording, non-scheduled/completed reminders.
- Barrier/safety acknowledgment audit without clinical decision; legacy separation.
- Both portal lint/type/tests/build, backend Ruff/mypy/tests, real local PostgreSQL.
- Patient 360/390/430 and clinician desktop/narrow widths; keyboard/reduced motion,
  safe area, long Spanish, loading/empty/unavailable/retry.

Remote migration/deployment require separate authorization. Local success is not
deployed acceptance. Record exact checks and remaining boundaries before review.

### Rollout dependency

Migration `051_notification_centre.sql` must be reviewed and applied before the
new API/UI deployment. Its full filename is distinct from Nora's
`051_health_knowledge_and_chat_sessions.sql` (merged in #147 and already applied); the
ledger keys on full filenames, and the two touch no shared objects. The two were
verified together in disposable PostgreSQL 16. No remote application is authorized
by this specification. Until the
database is available, the UI shows unavailable/retry rather than fabricated
counts. Existing patient notification endpoints remain compatible.

Pagination and viewing cutoffs are signed, short-lived, actor/role-bound tokens;
the client cannot manufacture a bulk-read cutoff. Each loaded page retains its
own cutoff. Bulk reads stop if the account changes; JWT renewal does not remount
child workflows or discard message drafts.
