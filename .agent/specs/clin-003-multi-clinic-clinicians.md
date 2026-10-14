# CLN-003 — Clinicians who work at more than one clinic

**Status:** Backlog; decisions made October 13, the shared clinical summary awaits confirmation. Raised by the project advisor at the
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

## Decisions (requester, October 13)

1. **A patient belongs to care teams, and each care-team link belongs to a clinic.** The
   link takes the clinic of the invite code the patient used. The same provider can work
   at several clinics, so a patient seen by that provider at two clinics has two links,
   one per clinic. `care_teams` becomes unique on (patient, clinician, clinic) instead of
   (patient, clinician).
2. **Care plans are per care team, not per patient.** A cardiologist, an ENT specialist
   and an orthopaedic provider each write and approve their own plan. Today one plan per
   patient combines everything. The design is in
   [PLAN-002](plan-002-care-plans-per-care-team.md).
3. **No feature-freeze constraint:** design and build the complete version.

## Shared clinical summary (recommended October 13, pending confirmation)

Every clinician on a patient's care teams sees one **shared clinical summary**, so each
has the overall picture needed to treat safely.

- **Always shared:**
  - **Active medications and allergies**, each tagged with the care team and clinic that
    recorded them. A hidden medication or allergy is how interactions and allergic
    reactions get missed, so the patient cannot hide these.
  - **Critical-result alerts.**
  - **The patient's other care teams:** specialty, clinician and clinic, so a clinician
    knows who else to coordinate with.
- **Shared, but the patient can mark sensitive:** active conditions. A condition the
  patient marks sensitive (for example mental health, HIV, reproductive or substance-use
  care, which California treats as sensitive services) is visible only to the care team
  that recorded it. Other clinicians see "Some conditions are kept private by the patient"
  instead of a silently partial list. This is a product rule, not a legal opinion; it
  should be confirmed before real use.
- **Owned by one care team and not shared:** documents, that team's care-plan detail,
  chat and messages, SOAP notes, ADR reviews and visit details. Other teams see only that
  a plan exists (specialty, clinician, clinic, approval date) and its medications, through
  the shared list.
- **Scheduling:** other clinics see only "busy" blocks on a shared clinician's calendar.
- **Default view:** "All clinics", remembering the last filter per page.

## Out of scope

- **Covering for a colleague.** MediAgent has no coverage or delegation feature. The rule
  stays that a clinician sees a patient only through their own care-team link. If coverage
  is ever needed, it would be an explicit, time-limited, audited link and its own task.

## Suggested slices

| Slice | Scope |
| --- | --- |
| A | Memberships, backfill and RLS (no visible change) |
| B | Sign-in once and add a clinic to an existing account |
| C | "All clinics" lists with clinic chips and filters |
| D | Per-clinic roles, settings and invitations |
| E | Cross-clinic scheduling and conflict checks |
| F | Clinic tags in notifications, email and audit |
| G | Shared clinical core (medications, allergies, conditions, critical alerts) with per-team ownership of everything else, and the patient's visibility control |
| H | Care plans per care team (PLAN-002) |
