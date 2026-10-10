# COM-001-B — Explicitly routed human conversations

Implement two-way in-app conversations between one patient and one currently
linked clinician. A patient explicitly chooses a recipient; never broadcast to
every linked team. Show clinic and actual sender. Nora and operational alerts
stay separate. A clinician's explicit send is their approval of that message;
no AI-generated clinical message is sent automatically.

## API contract

All routes are authenticated under `/api/v1/care-conversations`:

- GET `/recipients`: list of `{id, name, role, clinic_name}` for the caller's
  active counterparts, from current assignment (patient gets clinicians;
  clinician gets patients).
- GET `/`: list of `{id, patient_id, clinician_id, patient_name,
  clinician_name, clinic_name, last_message_at, last_message_preview,
  unread_count, writable}`. Lists are caller-scoped, no cross-team history.
- POST `/`: `{recipient_id: UUID}` resolves the caller and recipient into an
  active patient/clinician pair, idempotently returns its conversation.
- GET `/{id}/messages?before=<message UUID>&limit=50`: `{items, next_cursor}`,
  newest page selected by deterministic `(created_at,id)` cursor and displayed
  oldest first. Each message has `{id, conversation_id, sender_id, sender_role,
  sender_name, body, created_at}`. Maximum limit 100.
- POST `/{id}/messages`: `{body: string, client_message_id: UUID}`. Trimmed
  nonempty body, max 4000 characters. Atomic active-assignment authorization,
  insertion and audit; same sender/idempotency key returns same saved message,
  changed body/thread with that key rejects. No client controls sender identity.
- POST `/{id}/read`: `{last_message_id: UUID}` marks through that message only,
  monotonically. Returns `{read_at}`; never mark a newer unseen message read.

Denials are neutral and do not reveal another patient's or clinician's data.
Inactive/reassigned pairs lose conversation access and send permission; no
silent transfer to another clinician. Responses never include private UUIDs in
visible message copy. Historical notifications remain separate, not migrated
into human messages or treated as replies.

## Patient and clinician UI

Patient Care team view: explicit recipient chooser, thread list, actual sender
and clinic, message composer, unread badge, bounded pagination, loading/error/
retry states and stable client idempotency key for uncertain send retry. English
and Mexican Spanish copy, with emergency/not-continuously-monitored notice.
Clinician Messages: conversation inbox and compose/reply; operational alerts
are a separate view. Remove human composer from AI transcript. Refresh sends
and bounded inbox/thread polling only while the corresponding view is visible; no fake online,
delivered or read claims. Never render message text as HTML.

## Acceptance

Two assigned users send and receive through the same thread. Two clinicians
linked to one patient have distinct threads and cannot read each other's.
Patient cannot impersonate sender or address unassigned clinician. Revocation
blocks read/write. Duplicate sends do not duplicate rows/audit. Concurrent send
and revoke is serialized. Uncertain send retains content/key. Read marker does
not consume concurrent new arrivals. Pagination is stable, no body in logs.
Focused API, service, PostgreSQL and both portal component tests plus lint,
typecheck/build. Live acceptance only after authorized deployment/migration.

No remote migration, deployment, reset or clinical publication is authorized
by this local implementation task. Do not claim real-PHI production readiness.

## October 10 local verification

Focused backend/database checks: **72 passed**, including 33 real PostgreSQL
tests against isolated official PostgreSQL 16 containers and 39 service/API tests.
These cover duplicate/concurrent send, revoke/send serialization, stable pagination,
read races, browser-role denial and reassignment binding isolation. The fixture
uses the relevant repository schema migrations, not the complete migration chain;
PostgREST and deployed acceptance are not established by this test.

Patient portal: **289 passed**; clinician portal: **242 passed**. Both passed
typecheck, lint and `npm run build -- --webpack`. Tests cover explicit recipient
routing, stale polling protection, unread refresh, retained uncertain-send keys,
editable definitive failures and separately labeled legacy notifications.
CI now runs the opt-in PostgreSQL conversation suite in its full coverage job and
rejects skipped/absent/failing database cases. CI and live acceptance remain open.

Broader backend regressions: **2,010 passed, 58 opt-in skips** with
`pytest tests --ignore=tests/integration/test_appointment_offer_transactions.py
--no-cov -q` and synthetic settings. This is not a complete database-suite pass:
the native appointment fixture remains excluded for the known host shared-memory
limit, and the conversation database suite was run separately with Docker above.
