# CLN-003 — Clinicians who work at more than one clinic

**Status:** Backlog; decisions needed before design. Raised by the project advisor at the
October 13 checkpoint demo.

## Why

In practice a provider or nurse often works at several clinics. They expect to sign in
once, see every clinic they belong to, work with the patients they care for at each one,
and keep one schedule across all of them. MediAgent models one clinic per clinician.

## How it works today

- **One clinic per clinician.** `clinicians.clinic_id` (migration 007) and a single
  `clinicians.role` (`provider`, `admin`, `nurse`) hold one clinic and one role. Being an
  admin at one clinic and a provider at another cannot be expressed.
- **Sign-in starts with a clinic code.** Step 1 of 3 is "Enter clinic code", and joining
  creates an account inside that clinic. An invitation from a second clinic cannot attach
  an existing account.
- **Patients are linked to clinicians, not clinics.** Access is the `care_teams` link
  (patient ↔ clinician, `is_assigned_clinician`). `care_teams.clinic_name` is
  denormalised text, not a clinic reference.
- **Appointments carry no clinic.** They reference a `care_team` and a free-text
  `location`. Availability and double-booking checks have no clinic dimension.
- **Mixed clinic scoping elsewhere.** Notifications, invitations (057) and care
  conversations (048) carry a `clinic_id`; Risk Radar, the roster, alerts and the review
  queue are per clinician.

## Product shape (proposal)

1. **One account, many memberships.** A clinician signs in once with email, password and
   MFA. Each membership has its own clinic, role and status. A clinic code or invitation
   adds a membership to the existing account instead of creating a new one.
2. **"All clinics" by default, with a switcher.**
   - The header shows the clinician's clinics. Today, Risk Radar, Patient Roster, Alerts,
     Review Queue, Messages and Appointments open on "All clinics".
   - Each patient row, visit and alert shows a clinic chip, and every list can be filtered
     to one clinic.
3. **Clinic context for actions.**
   - Some actions belong to one clinic: inviting staff, Team & Roles, clinic settings,
     offering a visit, and opening a patient's record at a site.
   - They run in an explicit clinic context, and the audit records the acting clinic.
   - Admin rights apply only to the clinic where the clinician is an admin.
4. **One schedule across clinics.**
   - A clinician has one calendar. Each visit is booked at a clinic, with that clinic's
     address and timezone.
   - Offering a time checks for conflicts across every clinic the clinician works at.
     Other clinics see only a "busy" block, not patient details.
   - Patients see the clinic and address on offers, visits and reminders.
5. **Access is still the care-team link.**
   - Membership in clinic A never grants access to clinic B's patients, and does not grant
     access to clinic A's patients without a care-team link.
   - A patient seen at two clinics has two links, each tagged with its clinic.
6. **Patient view.** Care-team members are listed with their clinic. Messages and visit
   offers name the clinic.

## Likely changes

- **Schema:**
  - add `clinic_memberships (clinician_id, clinic_id, role, status, timestamps)`,
    backfilled from `clinicians.clinic_id`/`role`;
  - add `care_teams.clinic_id` and `appointments.clinic_id`;
  - add per-clinic availability;
  - update the RLS helpers for membership plus care-team checks;
  - keep `clinicians.clinic_id` for a transition period.
- **Backend:** clinic-scoped services and routes, invitation acceptance onto an existing
  account, cross-clinic conflict checks, and a clinic tag on notifications, email and audit.
- **Clinician portal:** sign-in without a mandatory clinic code, the switcher and filters,
  clinic chips, per-clinic settings and team pages, and a combined calendar.
- **Patient portal:** clinic names on the care team, offers and visits.

## Decisions needed

1. Does a patient belong to a clinic, or only to clinicians through clinic-tagged
   care-team links?
2. Can staff at clinic B see that a shared patient has visits or plans at clinic A? Or do
   they only see busy blocks on the shared clinician's calendar?
3. Should the default view be "All clinics" or the last clinic used?
4. Is there one care plan per patient or one per clinic? Who approves when two clinics
   both treat the patient?
5. Expo scope before the December 4 feature freeze: which slices (data model and sign-in,
   unified lists, scheduling) are in, and which are shown as design only?

## Suggested slices

| Slice | Scope |
| --- | --- |
| A | Memberships, backfill and RLS (no visible change) |
| B | Sign-in once and add a clinic to an existing account |
| C | "All clinics" lists with clinic chips and filters |
| D | Per-clinic roles, settings and invitations |
| E | Cross-clinic scheduling and conflict checks |
| F | Clinic tags in notifications, email and audit |
