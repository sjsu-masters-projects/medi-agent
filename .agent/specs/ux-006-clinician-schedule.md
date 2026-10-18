# UX-006 — Clinician schedule and multi-clinic consistency

Status: built on `feature/clinician-schedule` (October 17, 2026), deployed check pending. Accepted design October 17, 2026. Owner: Rajeev. Builds on SCH-001 (appointment
offers), CLN-003 slices A–F (unified multi-clinic view) and UX-005 (queue + detail pattern).

## Problem

Production review on October 17 with a two-clinic clinician (Elena Park: Cedar Grove + Willow
Terrace) showed the unified view works but reads as messy:

- Appointments is patient-first: pick a patient, then an offer form and that patient's history.
  There is no view of the clinician's own day or week across clinics, so a clash is discovered
  only when the server refuses a slot.
- Page headers name one arbitrary clinic (Risk Radar showed Willow Terrace for a Cedar Grove
  default). Settings shows the clinic twice, a default-clinic "Role", and sits under
  "Administration" for every role.
- Counts disagree (Appointments "5 assigned" vs Roster 4 patients).

## Decisions

1. **Appointments becomes "My schedule"** (`/appointments`):
   - Agenda as the default view: Today and This week (Day / Week toggle), grouped by day; each row
     shows time (bold), patient, clinic chip, visit type, status chip; whole row opens the visit.
   - "Needs action" strip above the agenda: offers awaiting the patient's answer (expiring within
     48 h highlighted), patient change requests, and expired-unanswered offers. Each item links to
     its visit or offer.
   - Clinic filter (`?clinic=`), hidden for single-clinic users, same placement as other lists.
   - Empty states: "No visits today" with the next upcoming visit, and a "New offer" action.
2. **New offer is a side panel** opened by a primary "New offer" button (and from a patient
   record): patient picker (clinic shown read-only, derived from the link), 2–4 slots, duration,
   type, location, reason. When a date is chosen, the clinician's existing confirmed/scheduled
   visits that day (all clinics) are listed as busy times beside the slot inputs, so clashes are
   avoided before sending. The server conflict check stays as the authority.
3. **A visit detail** (drawer or page) shows the patient, clinic, time, status, history of the
   offer and responses, and the existing actions (edit, cancel, calendar export) with today's
   authorization rules.
4. **Per-patient appointment history moves to the patient record** as an "Appointments" tab, which
   also offers "New offer" for that patient.
5. **Consistent multi-clinic chrome** on every clinician page: header shows "All clinics" or the
   filtered clinic, never an arbitrary one; one filter placement; chips never truncate (own line
   under the name when space is short); single-clinic users see no clinic chrome.
6. **Counts agree**: "assigned" and roster counts use the same definition (active care-team links,
   distinct patients); fix whichever differs.

## Backend

- A clinician schedule read: the caller's own confirmed/scheduled visits in a date range across
  all their clinics, plus open offers and change requests, each with clinic tag; scoped to the
  caller's own appointments or links per the October 17 access rule. Reuse existing list
  endpoints with date-range parameters if they can express this; add one endpoint only if not.
- A "busy times" read for a date (the caller's own visits that day, all clinics) returning only
  intervals and clinic names — never other patients' names.

## Must not change

- Offer, respond, expiry, reminders, ICS, the cross-clinic exclusion constraint and conflict
  messages; authorization; audit; patient-portal visit flows.

## Acceptance

- A two-clinic clinician sees today's and this week's visits from both clinics on one agenda,
  with a "Needs action" strip, and can create an offer from a side panel that shows busy times.
- Patient record shows its Appointments tab; the old patient-first page is gone.
- Headers, filters and chips are consistent on every list; Settings is consolidated.
- 390 px and 1280 px without horizontal scroll; tests for agenda, needs-action, side panel with
  busy times, patient tab and counts; deployed check with Elena Park.

## Build notes (October 17)

- **Backend:** `GET /appointments/schedule?from&to&clinic_id` (own visits in [from, to), needs-action
  items grouped per offer, next visit; 45-day cap), `GET /appointments/busy?from&to` (own intervals and
  clinic names only; 48 h cap), and `GET /appointments/?patient_id=` for the patient tab. All are scoped
  to the caller's own appointments (`clinician_id`) or, for the patient filter, to an active link.
- **Counts:** `GET /clinicians/me/patients` returns one row per care-team link, so a patient shared by two
  of the caller's clinics appeared twice (Appointments "5" against 4 distinct patients on the Roster), and
  a clinic filter still listed the other clinic's link. It now lists only in-scope links and tags each with
  its own clinic. The distinct-patient definition is the Roster's.
- **Portal:** `/appointments` is "My schedule" (sidebar label too). Edit and cancel do not exist in the
  clinician portal today; the visit detail offers the existing calendar export and "Offer new times".
- **Consistency fixes:** the header scope text is "All clinics" or the filtered clinic for multi-clinic
  users and nothing otherwise (it no longer falls back to a stored or single clinic); every list header
  carries it; the filter sits in the list toolbar where there is one (dashboard, ADR, MedWatch) and at the
  top right of the header elsewhere (roster, upload queue, alerts, messages, schedule); the ADR and
  MedWatch headers use the same title size and subtitle tone as the other pages.
- **Not done:** the Settings consolidation (duplicate clinic, default-clinic "Role", placement under
  "Administration") from decision 5 is not part of this change.
