# Messaging, alerts and email

Three linked channels: two-way care-team conversations between one patient and one
linked clinician, a role-aware in-app notification centre (patient Notifications,
clinician Alerts), and selective email. Synthetic data only; `en-US` and `es-MX`.

## What it does

- **Conversations:** a patient picks one currently linked clinician and writes to them;
  the thread shows the clinic and the actual sender. A clinician sees an inbox of their
  own threads and replies. Two clinicians linked to one patient have separate threads.
  Nora (the AI assistant) and system alerts are separate surfaces. A clinician can preview
  a reply in the patient's language before sending; translations are stored once, never
  generated on read or send.
- **Notification centre:** a bell sheet and a full page (patient `/notifications`,
  clinician `/alerts`) with All or Unread, mark read and mark all read. Clinicians also
  get "Needs attention" (action items) and History with category filters. Items link to
  the exact visit, document, plan or conversation. Pre-conversation one-way messages sit
  in a collapsed "Earlier messages" section of clinician Messages.
- **Email:** account recovery and clinician invitations, plus opt-in notices for
  appointments, unread messages, published plans, records needing patient action and
  (clinicians only) grouped review reminders. The address, a verification code and the
  notice checkboxes live in patient Profile and clinician Settings.

## Rules it must keep

1. **Explicit routing.** A message goes to one chosen, currently linked counterpart,
   never to every linked team. A clinician's explicit send is their own approval; no
   AI-generated clinical message is ever sent automatically.
2. **Access follows the active assignment.** Read, send and recipient lists re-check the
   active patient/clinician link atomically in the database. A reassigned or revoked pair
   loses read and send; nothing transfers silently. Denials are neutral and reveal
   nothing about other people. Private threads follow only the addressed conversation.
3. **Send is idempotent.** Body trimmed, non-empty, at most 4000 characters, with a client
   `client_message_id`. The same sender and key returns the same saved message; a changed
   body or thread under that key is rejected. Sender identity is never client-supplied.
   Send and revoke are serialized. An uncertain send keeps its text and key for retry.
4. **Reads and paging.** A deterministic `(created_at, id)` cursor (default 50, maximum
   100). A read marker only moves forward, through the named message, and never consumes a
   newer unseen one. Message text is never rendered as HTML and never logged.
5. **Honest UI.** Polling (15 s) runs only while the view is visible. No fake online,
   delivered or read claims. Patient views show the not-continuously-monitored notice.
6. **Reading is not reviewing.** Opening a notification never completes review, approval
   or clinical resolution. An action item leaves Needs attention only when its source
   changes or a clinician acknowledges it. Acknowledgement is per clinician, audited, with
   an optional note (1000 characters), only for barrier and safety follow-up, and does not
   clear the item for other reviewers.
7. **Capture is atomic and idempotent.** The source change and its notification event
   commit together; unique source event keys and idempotent receipts make retries add
   nothing. History is append-only: no role may delete it, and it goes only with the
   patient or account. Browser roles cannot write events. Malformed source values make an
   item non-actionable, never fail the centre. A missing summary is "unavailable", not 0.
   Legacy urgent or message history is never replayed as fresh work, and a confirmed ADR is
   never inferred. Ending an assignment denies that item's details and target. The ledger
   helpers (`notification_source`, `_authorized`, `_actionable`, `_scope`, `_owner_sees`)
   are layered wrappers: a new event type wraps the current function and delegates, and a
   migration that replaces one outright silently drops the event types below it.
8. **Appointments are classified by transition.** A new offer reaches the patient once per
   offer group. A patient's accept, decline, change request, cancel or note reaches the
   responsible clinician. A time or location change to a booked visit, an offer's expiry
   and a clinician cancel reach the patient. Withdrawn siblings, completion and no-show
   create nothing. Reminders (24 h and 1 h) exist only for `confirmed` or `scheduled`
   visits, so a cancelled visit gets none. A confirmation is an ordinary notification; a
   decline, change request or cancel is an action item until acknowledged or a newer
   appointment exists. A multi-slot answer is one item.
9. **Other events.** An ADR information request is actionable only while pending; its
   answer is a History-only item for assigned clinicians. A reviewed symptom report and a
   medication-confirmation question go to the patient; the question's event holds no
   medicine, dose or answer and is actionable only while open and unexpired on the
   database clock. These three items map to no email category.
10. **Locale and links.** Patient copy follows the saved locale and timezone; clinician
    controls stay English. Notification copy never translates a human message or clinical
    instruction. Links are server-built local routes; private IDs never appear in copy.
11. **Signed snapshots.** Cursors and "read through" cutoffs are short-lived, signed and
    bound to actor and role. The signing key is derived per purpose from a secret, never
    the raw login key, and every API replica must share the same root. Mark all read
    touches only snapshot items still visible and returns `updated_count` and
    `skipped_count`, which both portals show.
12. **Bounded reads.** One shared poll (60 s visible, none hidden); focus events within 60
    s of the last refresh are ignored; failures back off (2, 4, then 5 minutes) and keep
    the last list. The server gives up after 6 s and shares identical concurrent reads.
13. **Account deletion.** Deleting a patient removes their conversations, markers and
    offer history. Deleting a clinician keeps the patient's thread, unlinked, with sender
    names kept (migration 053).
14. **Email is consent-gated.** A notice is queued only if the address is verified by a
    code, the category is on, and consent was stamped (when notices turn off to on) before
    the event. Verification alone opts in nothing; a complaint withdraws consent. Codes:
    one per 60 s, five per contact per day, five tries each.
15. **Email is rechecked at send.** Dispatch re-verifies assignment, consent, the address
    and that the work is still unread and current. One email per recipient and event;
    unread messages group per thread per 15 minutes, reviews per category per hour;
    retries stop at 5 attempts or 23 hours. Saved clinical actions never depend on email.
16. **Email content.** No Nora answers, unpublished drafts, diagnoses, per-dose reminders,
    attachments, health detail or IDs; one link to `/notifications` or `/alerts`. Dynamic
    values escaped; patient locale from preference, clinician English. Addresses ending
    `@accounts.mediagent.live` are never sent to, and a genuine verified mailbox or an Auth
    link is never diverted to a demo sink.
17. **Recovery and invitations.** Password reset answers neutrally whether or not the
    account exists, builds the destination from a fixed portal selector, and logs no
    email, token or provider body. The link needs a click on Continue before the token is
    used (scanners cannot burn it); the recovery session is isolated; a save signs out
    every session (minimum 8 characters) and the next sign-in still passes clinic and MFA
    checks. Invitations use hashed opaque tokens; only clinic
    admins invite; acceptance checks address, inviter authority, expiry and revocation.

## Why it was built this way

- Per-pair threads, not a team inbox, so private history never leaks to a colleague.
  Alerts and Nora stay apart from human messages.
- Fan-out on write with an indexed read path, so a read costs the page shown (about 54 ms
  at 10,000 items), and a timezone lookup table (075) replaced per-row catalogue scans.
- Email is a channel layered on saved events, never a source of truth. Supabase sends
  auth mail over SMTP; the backend sends invitations and notices through Resend.
  Signup confirmation stays off until signup supports pending verification.

## Excluded on purpose

SMS, push, inbound email, marketing, per-dose or completion email, email of Nora content,
automatic AI replies, broadcast to all linked clinicians, real-time presence.

## Where it lives

- Backend `backend/src/app/`: `routers/care_conversations.py`, `notification_centre.py`,
  `email_preferences.py`, `cron.py` (`POST /cron/emails/dispatch`), `auth.py`
  (`/password-reset`); `services/care_conversation_service.py`,
  `notification_centre_service.py`, `email_service.py`, `email_invitation_service.py`,
  `email_templates.py`; `clients/resend.py`.
- Migrations `048` (conversations), `051` to `056` and `075` (notification centre), `053`
  (deletion), `057`/`058` (email), `068`/`088` (translation).
- Both portals: `components/features/care-conversations.tsx`, `notification-centre.tsx`,
  `email-preferences.tsx`, `password-recovery-form.tsx`; clinician `email-invitations.tsx`.
- Email templates and installation: [email templates](../email-templates/README.md).
- Tests: `backend/tests/integration/test_care_conversation_postgres.py`,
  `test_notification_centre_postgres.py`, `test_email_postgres.py` (real PostgreSQL),
  `tests/integration/routers/test_{care_conversations,notification_centre,email}_api.py`,
  `tests/unit/services/test_{care_conversation,notification_centre,email}_service.py`.

## How to check it

1. [QA handoff](../qa-handoff-2026-10.md) section 3.6 (notifications). Conversations and
   email have no dedicated section; use steps 2 to 4.
2. As a patient message one clinician; as that clinician reply; reload both. A second
   linked clinician must not see the thread. Retry an uncertain send: one row.
3. Produce an offer, a decline and an unread message; check the bell, Needs attention and
   History; acknowledge one as a clinician and confirm a second reviewer still sees it.
4. Request a password reset for a dedicated test account whose mailbox you own. A demo
   `@accounts.mediagent.live` address must never receive mail.
5. `cd backend && PYTHONPATH=src python -m pytest tests -k "conversation or notification
   or email" -q` (PostgreSQL suites need Docker or server binaries and must not skip);
   `npm run test` in each portal.

## Still open

- A demo mailbox redirect is not built; synthetic addresses are skipped, not redirected.
- Provider delivery status needs a full-access Resend key; a sending-only key leaves rows
  at "accepted" and logs one warning.
- Not yet exercised: MFA at login after a reset, a mobile visual check of the EN/ES
  emails, and spam placement of invitations as the sending domain ages.
- Clinician account deletion is still blocked by document upload and review provenance
  and SOAP annotations.
