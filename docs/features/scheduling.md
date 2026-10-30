# Appointment scheduling

A clinician offers a patient two to four candidate visit times, the patient picks one,
and either side can later change or cancel the visit. Clinicians also get a schedule
across all their clinics. Both locales (`en-US`, `es-MX`); synthetic data only.

## What it does

- **Clinician, offer:** "My schedule" (`/appointments`) or a patient record's
  Appointments tab opens a "New offer" side panel: patient (clinic read-only), 2 to 4
  date/time choices, duration (5 to 480 minutes), type, location, reason. The patient's
  saved timezone is used, and the clinician's busy times that day, at every clinic, are
  listed beside the inputs.
- **Patient:** Visits shows the offer: pick one time (confirmed; the others are
  withdrawn), decline, or ask for different times, each with an optional note. A
  confirmed visit can be cancelled the same way.
- **Clinician follow-up:** history shows slot statuses and patient notes as written.
  "Offer new times" starts a fresh offer after a decline, change request or expiry (old
  rows stay). A booked visit can be edited (details), cancelled with a reason, or marked
  completed or no-show once it has ended.
- **Schedule:** Day or Week agenda, a clinic filter (hidden for single-clinic users) and
  a "Needs action" strip: offers awaiting an answer (highlighted within 48 hours of
  expiry), change requests, unanswered expired offers from the last 14 days. Cancelled
  visits show only under "Show cancelled". "Add to calendar" downloads a one-time `.ics`.

## Rules it must keep

1. **The clinician controls every time.** Only offered times can be booked, chosen from
   a structured picker. Free text is never parsed and the model never books, proposes
   or reads a time. The patient note is a message, not a scheduling input.
2. **Who may act.** Only the active care-team clinician proposes (service and RPC both
   check); only the owning patient responds. A clinician manages a visit if they are
   its own clinician or hold an active link to the patient at the visit's clinic. A
   link at another clinic grants nothing. Patients cannot cancel-as-clinician, complete,
   mark no-show or edit.
3. **Offers and responses are atomic and group-aware.** An offer is 2 to 4 distinct,
   future, timezone-aware slots sharing one `proposal_group_id`, one audit event per
   slot. Accept works only while a slot is `proposed`; it confirms that slot and
   withdraws its siblings. Decline and request-alternative change every proposed slot of
   the offer; a proposed grouped offer is declined, not cancelled. Locks go patient
   first, then offer rows, so competing responses yield one booking, not a deadlock. The
   offer RPCs and the audit table are backend-only, audit rows cannot be updated, and
   browser roles cannot write grouped rows.
4. **No double booking.** Pending options reserve nothing. Exclusion constraints stop
   overlapping `confirmed`/`scheduled` visits for one patient (migration 043) and for one
   clinician across all clinics (069), including direct writes. Intervals are
   `[start, end)` so back-to-back visits are allowed; minutes are UTC arithmetic, so
   DST cannot matter. An exclusion or deadlock failure rolls back the whole response,
   including sibling changes and audit rows. Any other database failure returns a
   sanitized error.
5. **Conflicts name no patient.** A refused offer returns `CLINICIAN_SCHEDULE_CONFLICT`
   with only the other visit's clinic name and interval; busy times are the same.
6. **Expiry.** A slot expires at `min(created_at + 168 hours, slot start)`. Editing
   cannot extend it and an expired row cannot reopen. Slots expire individually. Expiry
   is judged on the database clock after locks are held, so an earlier-started request
   cannot confirm a late slot. There is no background job: expiry is persisted on
   authorized list reads and responses, writing one `expire` audit event (null actor)
   once. Expired cards have no actions. Confirmed visits do not expire.
7. **Business errors** are HTTP 422 with codes `APPOINTMENT_CONFLICT`, `_EXPIRED`,
   `_UNAVAILABLE`, `_PAST`, `_NOT_ENDED`, `_TIME_CHANGE_VIA_OFFER` and
   `CLINICIAN_SCHEDULE_CONFLICT`. Portals pick localized copy by code, never raw text.
8. **Generic update is narrow.** `PUT /appointments/{id}` refuses patients and every
   status change. Details (type, location, reason, notes) may change on a proposed,
   confirmed or scheduled visit (on an open offer, for every open slot). The time of a
   booked visit is not editable: a new time is a new offer.
9. **Cancel, complete, no-show** (`/cancel`, `/complete`, `/no-show`). Cancel needs a
    reason code (`clinician_unavailable`, `clinic_closed`, `patient_request`,
    `scheduling_error`, `other`; text required for `other`). Complete and no-show need
    the visit to have ended. Each writes one `appointment_offer_events` row in the same
    transaction. A cancel frees the slot and notifies the patient (in app and email; no
    reason text or health detail). Complete and no-show notify nobody.
10. **Time display.** Patients see times in `patients.timezone` and their saved locale
    with the zone named, hidden while settings load; on failure or an invalid zone the
    portal shows labelled UTC with a retry. The clinician form converts in the patient's
    saved zone, not the browser's, and rejects past, duplicate, DST-gap and repeated-hour
    times; the server still validates.
11. **Calendar export.** `GET /appointments/{id}/calendar?locale=` is authenticated,
    `Cache-Control: private, no-store`, and re-checks access and status on every click:
    own patient or authorized clinician; `confirmed`, `scheduled` or `cancelled`
    (exported as `STATUS:CANCELLED` so re-import removes it). Other statuses are
    refused. RFC 5545 file: UTC `DTSTART`/`DTEND`, stable UID, TEXT escaping, CRLF,
    75-octet UTF-8-safe folding, `CLASS:PRIVATE`, a localized title naming the visit's own
    clinic (so a multi-clinic person can tell visits apart), location and a no-sync
    notice; no reasons, notes, clinician or patient identifiers. A snapshot: no URL
    credentials, public links or invitations.
12. **Reads are caller-scoped.** `/appointments/schedule` returns only the caller's own
    visits in `[from, to)` (45-day cap); `/busy` is capped at 48 hours; a clinic filter
    is honoured only for a clinic the caller belongs to. "Assigned" and roster counts
    both mean distinct patients with an active in-scope link. In the portal, changing
    range, clinic or filter shows loading until the matching response; stale ones drop.

## Why it was built this way

- Clinician offers, patient picks: fewer round trips than one time with accept/decline,
  and no self-booking, which needs real availability and drops clinician control. 2 to 4
  labelled options also suit older patients and screen readers.
- No availability engine: the clinician asserts times and database constraints catch
  conflicts. One `appointments` table with group and `withdrawn`/`expired` states keeps
  RLS and list code; expiry on read avoids another scheduled job.

## Excluded on purpose

Patient self-booking, free/busy or working hours, clinician-wide capacity, calendar sync
or invitations, SMS or push visit notices, any model step that picks a time.

## Where it lives

- Backend `backend/src/app/`: `routers/appointments.py`, `services/appointment_service.py`,
  `appointment_schedule_service.py`, `appointment_calendar.py`.
- Migrations `038` to `043` (groups, atomic RPC, audit, expiry, patient overlap), `069`
  (clinician overlap), `071` (visit management); read-only checks in `backend/scripts/`
  (`appointment-*-preflight.sql`, `verify-appointment-slice5.sql`).
- Patient portal `apps/patient-portal/src/`: `app/(app)/visits/page.tsx`,
  `hooks/use-visits-data.ts`, `components/features/visit-offer-card.tsx`.
- Clinician portal `apps/clinician-portal/src/`: `app/(dashboard)/appointments/page.tsx`,
  `components/features/` `new-offer-panel`, `schedule-agenda`, `schedule-needs-action`,
  `visit-detail-panel`, `visit-actions`, `patient-appointments-panel`.
- Tests: `backend/tests/integration/test_appointment_offer_transactions.py` (real
  PostgreSQL), `tests/integration/routers/test_appointment_*_api.py`,
  `tests/unit/services/test_appointment_*.py`, and portal `*appointment*`/`visits-*` tests.

## How to check it

1. [QA handoff](../qa-handoff-2026-10.md) section 3.7: two-clinic clinician, filters,
   cross-clinic conflict, calendar export, 390 and 1280 px.
2. Offer two future times, choose one as the patient: one Confirmed, its sibling
   Withdrawn, persisted on refresh. An overlapping time is refused naming only clinic and
   time; one starting exactly when a visit ends is allowed.
3. Offer a slot minutes ahead plus a later one: after the first starts it is Expired and
   the second stays selectable. Cancel a booked visit: the patient sees the reason in
   their language and one in-app notice. Repeat in `es-MX`.
4. `cd backend && PYTHONPATH=src python -m pytest tests -k appointment -q` (the
   transaction file needs PostgreSQL server binaries on PATH and must not skip); `npm run
   test` in each portal, with `TZ=Asia/Tokyo` for time-conversion tests.

## Still open

- Withdrawing an open offer before the patient answers (no endpoint or control).
- Editing a visit's details (`PUT /appointments/{id}`) writes no audit row of its own.
- A patient-visible no-show message (none exists).
- Undecided: one active offer per visit reason per patient.
- Offset choice for a repeated DST hour (the clinician picks another time today).
