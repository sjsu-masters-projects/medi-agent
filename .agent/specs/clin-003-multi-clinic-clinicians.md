# CLN-003 — Clinicians who work at more than one clinic

**Status:** Slice A merged ([#176](https://github.com/sjsu-masters-projects/medi-agent/pull/176)); slice B in progress on `feature/clinic-sign-in-once` (see [Slice B design](#slice-b-design-sign-in-once-and-add-a-clinic-to-an-existing-account)); decisions made October 13. Raised by the project advisor at the
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
2. **"All clinics" by default.** (Agreed October 16: there is no header switcher and no
   global active clinic; a clinic is chosen only inside an action that belongs to one clinic,
   see slice B.)
   - Today, Risk Radar, Patient Roster, Alerts,
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
- **Clinician portal:** sign-in without a mandatory clinic code, filters,
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

**Status:** merged in #176. Migration `065_clinic_memberships.sql` was written and tested in
disposable PostgreSQL; applying it to a hosted project is the requester's action.

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
- Care conversations (`048`: the thread's clinic; slice B moved the check to the link's
  clinic), the notification centre (`051`/`052`/`054`/`061` clinic names; slice B moved the
  checks to the link's clinic),
  MedWatch clinic names (`medwatch_service`), the denial classifier's clinic comparison
  (`authorization_denial_classifier`): slices C and F, which should read
  `care_teams.clinic_id`.
- SQL functions that pick "the" active link for a (patient, clinician) pair with
  `ORDER BY created_at LIMIT 1` or a single-row `SELECT INTO` (care-plan approval in
  `040`/`042`/`045`/`049`, conversation `open` in `048`): correct while a pair has one link;
  they must take an explicit care team before a second clinic link can exist (slices C, H).

## Slice B design (sign in once and add a clinic to an existing account)

**Status:** in progress on `feature/clinic-sign-in-once`. Migration
`066_clinic_sign_in_once.sql` is written and tested in disposable PostgreSQL only; it is not
applied to any hosted project. The number 066 is also used by LOC-003's unmerged
`066_care_plan_wording_back_translation.sql` (branch `feature/english-first-review`); the
migration validator is unchanged (no exceptions or reservations), so whichever file lands
second is renumbered before it merges. LOC-003's file is renumbered later. Never edit an
existing migration.

**Agreed scope (requester, October 16).** One sign-in (email, password, MFA) with no clinic
code. The clinician lands on the same screens as today. There is no "Choose a clinic" step, no
header switcher, no `PUT /active-clinic` and no global active clinic. Lists stay clinician-wide
through the care-team link (clinic chips and filters are slice C). Clinic-scoped actions take an
explicit `clinic_id`, validated against an active membership, with the role read from **that
clinic's membership**, never `clinicians.role` or `clinicians.clinic_id`.

### Sign-in

- `/login` opens on **Sign in**: email, password, then the authenticator code when the account
  has MFA. `POST /api/v1/auth/login` no longer needs `clinic_code`. A client that still sends
  one (the deployed portal during rollout) must name a clinic the clinician actively belongs to;
  clinics are compared by id, never by name.
- A clinician with no active membership is refused: `INVITATION_ACCEPTANCE_REQUIRED` when the
  account came from an invitation that was never claimed, otherwise `NO_ACTIVE_CLINIC`.
- After sign-in the portal reads `GET /api/v1/clinicians/me/clinics` (MFA-gated) only to decide
  whether the sidebar shows a clinic name (exactly one clinic).
- The clinic code is the secondary path, **Join a clinic**: verify a code, then **I already have
  an account** (sign in, then add the clinic), **Join this clinic (Provider / Nurse)**
  (create an account, unchanged) or **Create a clinic workspace** (unchanged).

### How each clinic-scoped action chooses its clinic

`ClinicMembershipService.acting_membership(clinician, clinic_id)` resolves the clinic: the
named clinic must be an active membership at an active clinic (`CLINIC_MEMBERSHIP_REQUIRED`,
403, otherwise); with no clinic named, the only membership is used; with several the server
answers `CLINIC_REQUIRED` (422) and the portal shows a small picker inside the action. A
clinician with **no** membership is refused (fail closed): there is no `clinicians.role` or
clinic-name fallback, and `StaffService._require_admin`, the `_is_same_clinic` name match and
the name-based peer lookup in `ClinicianService._get_invite_scope` are gone, so two clinics with
the same display name share nothing.

| Endpoint | Clinic comes from | Role check |
| --- | --- | --- |
| `GET /api/v1/staff/?clinic_id=` | query, or the only membership | member of that clinic (any role) |
| `POST /api/v1/staff/invite` | body `clinic_id`, or the only membership | admin at that clinic (service, and again in SQL) |
| `PUT /api/v1/staff/{id}/role` | body `clinic_id`, or the only membership | admin at that clinic; runs in `clinician_clinic_operation` under lock |
| `DELETE /api/v1/staff/{id}?clinic_id=` | query, or the only membership | admin at that clinic; same function |
| `POST /api/v1/clinicians/me/invite-code` | body `clinic_id`, or the only membership | active member; the code and the care-team link carry that clinic |
| `GET /api/v1/clinicians/me/invite-code?clinic_id=` | query, or the only membership | active member; that clinic's latest pending code |
| `GET /api/v1/clinicians/me/invite-codes?clinic_id=` | query, or the only membership | own codes at that clinic; everyone's when admin there |
| `POST /api/v1/clinicians/me/invite-codes/{id}/revoke` | the code's creator | active member of any clinic (owner-scoped as before) |
| `GET /api/v1/email/invitations?clinic_id=` | query, or the only membership | admin at that clinic |
| `POST /api/v1/email/invitations/{id}/revoke` | the invitation's own clinic (SQL) | admin at that clinic |
| `GET /api/v1/clinicians/me/clinics` | the caller's own memberships | none needed |
| `POST /api/v1/clinicians/me/clinics` | `clinic_code` in the body | open code: Provider or Nurse only |
| `POST /api/v1/email/invitations/accept` | the invitation's clinic | the invitation's role, signed-in session |
| `POST /api/v1/auth/invitations/accept` | the invitation's clinic | see "Adding a clinic" |

"Clinic settings" in the portal is the Settings page's clinic code, team and invitation
sections; those three reads and writes are the staff and invitation rows above, so there is no
separate clinic-settings write to audit.

### Adding a clinic to an existing account

- **By clinic code:** `POST /api/v1/clinicians/me/clinics` with `clinic_code` and `role`
  (`provider` or `nurse`; admin only by invitation) adds an active membership. The default
  clinic (`clinicians.clinic_id`) is unchanged, except that a clinician with none gets this one.
  An existing active membership is left as it is (`status: already_member`). A membership ended
  by that clinic's admin is refused with `MEMBERSHIP_INACTIVE`; only that admin can bring the
  person back, by invitation.
- **By email invitation:** an admin can invite an address that belongs to another clinic; it is
  refused only when that address is already an active member of the admin's clinic. Accepting
  with a signed-in session (`/email/invitations/accept`) adds a membership with the invited
  role. Accepting with the account password (`/auth/invitations/accept`) is refused with
  `SIGN_IN_TO_ACCEPT` when the account has an active clinic and a verified authenticator, so
  adding a clinic never skips the second factor: sign in, then open the link again. An MFA
  account with no active clinic cannot sign in, so it gives its current code on that call
  (`MFA_CODE_REQUIRED` asks for it; the code is verified against the account's factor).
- **No duplicate accounts:** clinician signup first looks for a clinician with the same address
  (`ACCOUNT_EXISTS`: sign in to add this clinic), and an Auth signup response with no identities
  is treated as a duplicate without rolling anything back.
- **Profile updates** (`PUT /clinicians/me`) no longer change the clinic: `clinic_code` and
  `clinic_name` are refused with `CLINIC_CHANGE_NOT_SUPPORTED`.

### Default clinic

`clinicians.clinic_id`, `clinic_name` and `role` remain, as the clinician's **default clinic**
(the first clinic joined), for legacy readers. Joining another clinic adds a membership and
leaves them alone; when the default does change (removal from it), its role and name are taken
from the membership of the new default. No authorization on a slice B path reads them.

### Care conversations and notification checks

066 makes them use the care-team link's clinic (`care_teams.clinic_id`) with an active
membership there, so a patient's thread and alerts do not appear, vanish or split because of
another clinic the clinician joins. Access is unchanged: patients are reached only through the
clinician's own active care-team link, and no policy reads memberships.

### Audit

`clinic_membership_audit_events` is append-only: RLS on, `service_role` has SELECT and INSERT
only, no browser role has anything, and triggers refuse UPDATE, DELETE and TRUNCATE even for the
owner. Each row records actor, clinic, action, target, role and time; no email or name.

| Action | Written by |
| --- | --- |
| `joined_at_signup` | trigger on `clinicians` insert with a clinic (signup by code, first admin) |
| `joined_by_code` | `clinician_clinic_operation('join_code')` |
| `joined_by_invitation` | `clinician_email_invitation_operation('accept')` |
| `patient_invite_code_created` | trigger on `care_teams` insert of a pending code |
| `member_role_changed`, `member_removed` | `clinician_clinic_operation`, same transaction as the change |
| `email_invitation_created`, `email_invitation_revoked` | `clinician_email_invitation_operation`; a resend revokes the old invitation and creates a new one, so it writes both |

### Error states

| Code | When | Portal copy |
| --- | --- | --- |
| `CLINIC_REQUIRED` (422) | a clinic-scoped action with several memberships and no `clinic_id` | picker: "Choose which clinic this applies to." |
| `AUTHORIZATION_ERROR` (403), reason `CLINIC_MEMBERSHIP_REQUIRED` | a named clinic without an active membership, or no membership at all | "You are not an active member of that clinic." |
| `AUTHORIZATION_ERROR` (403), reason `ADMIN_SCOPE_ONLY` | staff or invitation action without admin at that clinic | "Only clinic admins can manage staff" |
| `MEMBERSHIP_INACTIVE` (403) | joining by code a clinic whose admin removed you | "Ask that clinic's admin to invite you again." |
| `CLINIC_CODE_INVALID`, `CLINIC_CODE_INACTIVE` (422) | unknown or suspended clinic code | as today |
| `NO_ACTIVE_CLINIC` (401) | sign-in with no active membership | "Your account is not active at any clinic." |
| `SIGN_IN_TO_ACCEPT` (401) | password-only invitation acceptance by an MFA account that has a clinic | "Sign in first, then open the invitation link again." |
| `ACCOUNT_EXISTS` (422) | clinician signup with an address that already has an account | "Sign in to add this clinic to your account." |
| `CLINIC_CHANGE_NOT_SUPPORTED` (422) | profile update naming a clinic | "Use Join a clinic" |

### Migration 066 and deploy order

`066_clinic_sign_in_once.sql` requires 065. It adds the audit table and its triggers,
`public.clinician_clinic_operation` (`list`, `join_code`, `set_member_role`, `remove_member`),
membership-aware `clinician_email_invitation_operation`, the default-clinic role rule,
`private.lock_care_conversation_pair`, `public.care_conversation_operation`, notification checks
reading the link's clinic, and a fail-closed verification block. **Order:** the requester
applies 066 (on explicit authorization) before this backend deploys, because the new routes call
`clinician_clinic_operation`. The deployed backend and portal keep working once 066 is applied:
they still send a clinic code, and every replaced function keeps its signature. Supabase Auth
dashboard changes: none.

### Still on the legacy columns after slice B

The MedWatch reporter clinic (slice F), notification `clinic_name` labels (slice F), the denial
classifier's clinic comparison, care-plan SQL that picks "the" link for a pair (slices C and H),
and per-clinic settings and invitation history pages (slice D).

### Known limitations

- Clinician signup returns `ACCOUNT_EXISTS` for an already registered email, which allows
  account enumeration. Accepted for now because Supabase signup already discloses it and the
  portal needs the copy to send the clinician to sign in. Follow-up: a neutral response plus an
  email to the address.
- Removing a member from their last clinic clears the default clinic and resets the legacy
  `clinicians.role` to `provider`; the deployed backend's direct writes to `clinicians` are
  mirrored into memberships but are not audited (no actor is available to the trigger).

## Review and audit checklist (every CLN-003 slice)

A slice is not ready for review until each invariant has a test that fails if it is broken.
Slice B's tests are listed; later slices add theirs.

| | Invariant | Slice B proof |
| --- | --- | --- |
| a | No patient data without an active care-team link | Docker: `test_access_is_still_the_care_team_link_and_membership_widens_nothing`, `test_no_policy_or_access_helper_reads_memberships` |
| b | Clinic-scoped endpoints check the membership and role for the named clinic | service: `test_staff_service`, `test_clinician_service`; router: `test_staff_api`, `test_clinician_api`, `test_email_api`; Docker: `test_invitation_admin_rights_come_from_the_membership_at_that_clinic` |
| c | No role or admin rights carry between clinics | `test_admin_rights_do_not_carry_between_clinics`, `test_an_admin_at_one_clinic_cannot_act_on_another` (Docker), `test_a_role_change_at_one_clinic_never_reaches_another` (Docker) |
| d | No duplicate accounts per email | `test_clinician_signup_refuses_an_address_that_already_has_an_account` |
| e | No MFA bypass | `test_invitation_password_accept_needs_sign_in_for_mfa_account_with_a_clinic`, `..._still_needs_the_code_for_mfa_without_a_clinic`; portal: add-clinic only after the second factor |
| f | Audit coverage per action | Docker: `test_every_membership_change_and_clinic_action_is_audited` |
| g | The audit table has no UPDATE or DELETE for any role | Docker: `test_the_audit_trail_is_append_only_for_every_role` (as `authenticated` and `service_role`, and the owner) |
| h | Browser roles have no writes on `clinicians`, `clinic_memberships` or the audit table | Docker: `test_browser_roles_cannot_write_clinicians_memberships_or_the_audit` |

Also check: no existing migration edited; the validator unchanged; the CI minimum for
`test_clinic_memberships_postgres` raised to the new count; no email address or name in the
audit rows, logs or fixtures; synthetic data only.

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
