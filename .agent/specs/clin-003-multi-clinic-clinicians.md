# CLN-003 — Clinicians who work at more than one clinic

**Status:** Slice A in progress (see [Slice A design](#slice-a-design-memberships-clinic-tagged-links-no-visible-change)); decisions made October 13. Raised by the project advisor at the
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

## Shared clinical summary (decided October 13)

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

## Slice A design (memberships, clinic-tagged links, no visible change)

**Status:** in progress on `feature/clinic-memberships`. Migration
`065_clinic_memberships.sql` is written and tested in disposable PostgreSQL only; it is not
applied to any hosted project.

### Tables and constraints

- **`clinic_memberships`** — `id`, `clinician_id` (→ `clinicians`, cascade on delete),
  `clinic_id` (→ `clinics`, restrict), `role` (`clinician_role_enum`: provider, admin,
  nurse), `status` (`active` | `inactive`, text check), `created_at`, `updated_at`.
  Unique on (`clinician_id`, `clinic_id`); a partial index on active rows per clinic.
  Memberships are deactivated, never deleted.
- **`care_teams.clinic_id`** — `uuid REFERENCES clinics(id)`, nullable only for links whose
  clinician has no clinic. `UNIQUE (patient_id, clinician_id)` is replaced by
  `UNIQUE (patient_id, clinician_id, clinic_id)`, so one provider can hold one link per
  clinic for the same patient. A partial unique index on (`patient_id`, `clinician_id`)
  `WHERE clinic_id IS NULL` keeps the old one-link guarantee for clinic-less links. Pending
  invites (`patient_id` NULL) stay unconstrained, as today. No SQL function or service used
  `ON CONFLICT` on the old constraint; the demo seed looks rows up by (patient, clinician)
  and is unchanged.

### Backfill

- One `active` membership per clinician from `clinicians.clinic_id` and `clinicians.role`.
  Clinicians without a `clinic_id` get none; the migration reports their count in a
  `NOTICE` (no identifiers) instead of inventing a clinic.
- `care_teams.clinic_id` from the link's clinician's `clinic_id`. No record of the clinic a
  patient invite code was issued from exists before 065 (the code lives on the pending
  `care_teams` row, and the clinician had one clinic), so the clinician's clinic is the
  issuing clinic for every existing link.

### How an invite code's clinic tags the link

A patient invite code is a pending `care_teams` row. Generating a code stores the issuing
clinic on that row (`clinic_id` from the clinician's single active membership). Joining
claims the same row, so the link keeps the code's clinic. A `BEFORE INSERT OR UPDATE OF
clinic_id, clinician_id` trigger on `care_teams` fills a missing `clinic_id` from the
clinician's clinic (so the deployed backend and the seed keep working), rejects a clinic in
which the clinician has no active membership, and refuses to clear a link's clinic (a link
reassigned to another clinician without a clinic takes that clinician's clinic, as a new link
would).

The database allows one link per clinic for the same patient and clinician, but the join's
"already linked" check stays per clinician in slice A: SQL functions that pick "the" link for
a pair (listed below) must take an explicit care team before the app creates a second one.

### Access rules

- `is_assigned_clinician` is unchanged: access is still the active care-team link, and no
  policy reads memberships. Nothing is widened.
- `private.is_clinic_member(clinic_id)` returns whether the signed-in clinician has an active
  membership at an active clinic. It is granted to `authenticated` and used by no policy yet
  (later slices combine it with the care-team check).
- `clinic_memberships`: RLS on; a clinician reads only their own rows; `service_role` has
  SELECT, INSERT and UPDATE; no role has DELETE; `anon` has nothing.
- `clinicians`: 065 revokes INSERT, UPDATE and DELETE from `PUBLIC`, `anon` and
  `authenticated` before the compatibility trigger exists. `clinicians_own_insert` and
  `clinicians_own_update` (002) have no column restriction, so with hosted default grants a
  signed-in clinician could have set their own `role` or `clinic_id` through the Data API, and
  the trigger would have copied it into memberships. SELECT is unchanged. No portal writes the
  table, every backend write uses the service role, and the only SQL function that writes it
  (`clinician_email_invitation_operation`, 057/058, SECURITY INVOKER) is executable by
  `service_role` only. The verification block fails if `anon` or `authenticated` can insert,
  update or delete either table.

### Compatibility period

`clinicians.clinic_id` and `clinicians.role` stay. Until slice B, an `AFTER INSERT OR UPDATE
OF clinic_id, role` trigger on `clinicians` mirrors them into memberships: the current clinic
gets an active membership with the current role; a clinic the clinician leaves (profile
clinic change, staff removal, invitation acceptance) is marked inactive. So a clinician has
at most one active membership, equal to the legacy columns, and every existing write path
keeps memberships correct without code changes. Slice B replaces the mirror with explicit
membership writes and then stops reading the legacy columns.

**Deploy order:** the requester applies 065 before merging, because the backend reads
`clinic_memberships` and writes `care_teams.clinic_id`. The currently deployed backend keeps
working once 065 is applied (the trigger tags its new invite rows).

### Reads moved to memberships in slice A

- Patient invite codes: the issuing clinic (new) and the admin's clinic-wide invite list
  (admin role and clinic peers come from active memberships; a clinician with no membership
  falls back to the legacy row, and the `clinic_name` fallback is unchanged).

### Reads still on `clinicians.clinic_id` (later slices)

- Sign-in clinic check and registration (`auth_service`), profile clinic change
  (`clinician_service.update_profile`): slice B.
- Staff listing, role changes, invitations and removal (`staff_service`,
  `ClinicianRepository`), email invitations (`057`/`058` SQL functions, which also read
  `clinicians.role = 'admin'`): slice D.
- Care conversations (`048`: the thread's clinic and the active-clinic check), the
  notification centre (`051`/`052`/`054`/`061` clinic names and active-clinic checks),
  MedWatch clinic names (`medwatch_service`), the denial classifier's clinic comparison
  (`authorization_denial_classifier`): slices C and F, which should read
  `care_teams.clinic_id`.
- SQL functions that pick "the" active link for a (patient, clinician) pair with
  `ORDER BY created_at LIMIT 1` or a single-row `SELECT INTO` (care-plan approval in
  `040`/`042`/`045`/`049`, conversation `open` in `048`): correct while a pair has one link;
  they must take an explicit care team before a second clinic link can exist (slices C, H).

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
