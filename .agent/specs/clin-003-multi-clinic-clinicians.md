# CLN-003 — Clinicians who work at more than one clinic

**Status:** Slices A–F merged and their migrations applied (see the table below); G and H remain. Decisions made October 13. Raised by the project advisor at the
October 13 checkpoint demo.

| Slice | Scope | Status |
| --- | --- | --- |
| A | Memberships, clinic-tagged care-team links (065) | Done, [#176](https://github.com/sjsu-masters-projects/medi-agent/pull/176), applied October 16 |
| B | Sign in once, add a clinic to an existing account (066) | Done, [#178](https://github.com/sjsu-masters-projects/medi-agent/pull/178), applied October 16 |
| C | "All clinics" lists with clinic chips and filters | Done, [#182](https://github.com/sjsu-masters-projects/medi-agent/pull/182), applied October 17 (067) |
| D | Per-clinic roles, settings and invitations, Your clinics | Done, [#182](https://github.com/sjsu-masters-projects/medi-agent/pull/182), applied October 17 (067) |
| E | Cross-clinic scheduling and conflict checks | Done, [#183](https://github.com/sjsu-masters-projects/medi-agent/pull/183), applied October 17 (069) |
| F | Clinic tags in notifications, email and audit | Done, [#183](https://github.com/sjsu-masters-projects/medi-agent/pull/183), applied October 17 (069) |
| G | Shared clinical core | Remaining |
| H | Care plans per care-team link (PLAN-002, Jeevan) | Remaining |

Deployed checks for A–F are tracked on the board (`.agent/TASKS.md`, CLN-003).

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

### Reads still on `clinicians.clinic_id` (after slice A; superseded: the current list is [after slice F](#still-on-legacy-columns-after-slice-f-what-remains))

- Sign-in clinic check and registration (`auth_service`), profile clinic change
  (`clinician_service.update_profile`): slice B.
- Staff listing, role changes, invitations and removal (`staff_service`,
  `ClinicianRepository`), email invitations (`057`/`058` SQL functions, which also read
  `clinicians.role = 'admin'`): membership-based since slice B; slice D adds the history and
  picker UI and the per-clinic settings.
- Care conversations (`048`: the thread's clinic; slice B moved the check to the link's
  clinic), the notification centre (`051`/`052`/`054`/`061` clinic names; slice B moved the
  checks to the link's clinic),
  MedWatch clinic names (`medwatch_service`), the denial classifier's clinic comparison
  (`authorization_denial_classifier`): moved to `care_teams.clinic_id` in slice C (the
  classifier compares the actor's active memberships with the links' clinics).
- SQL functions that pick "the" active link for a (patient, clinician) pair with
  `ORDER BY created_at LIMIT 1` or a single-row `SELECT INTO` (care-plan approval in
  `040`/`042`/`045`/`049`, conversation `open` in `048`): correct while a pair has one link;
  they must take an explicit care team before a second clinic link can exist (slices C, H).

## Slice B design (sign in once and add a clinic to an existing account)

**Status:** merged ([#178](https://github.com/sjsu-masters-projects/medi-agent/pull/178)); migration `066_clinic_sign_in_once.sql` applied October 16.
LOC-003's earlier `066` file was renumbered (see LOC-003). Never edit an applied migration.

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

### Still on the legacy columns after slice B (superseded by [after slice F](#still-on-legacy-columns-after-slice-f-what-remains))

The MedWatch reporter clinic (slice F), notification `clinic_name` labels (slice F), the denial
classifier's clinic comparison, care-plan SQL that picks "the" link for a pair (slices C and H),
and per-clinic settings and invitation history pages (slice D). Slice C moved the notification
centre labels, the classifier and MedWatch's identifier scrub to the link's clinic; slice D added
the settings and history UI.

### Known limitations

- Clinician signup returns `ACCOUNT_EXISTS` for an already registered email, which allows
  account enumeration. Accepted for now because Supabase signup already discloses it and the
  portal needs the copy to send the clinician to sign in. Follow-up: a neutral response plus an
  email to the address.
- Slice C and D: Leave ends the clinician's own links and unused invite codes at the clinic, but
  there is no hand-off tool: reviews, drafts and appointments they held for those patients leave
  their lists and nobody else is assigned. Rejoining a clinic after leaving or removal needs new patient links (a patient who held an
  ended link to the same clinician and clinic cannot claim a second code for that triple).
- Slice C: the Alerts page and the bell filter the already-loaded notification items in the
  browser; the server-side notification filter exists for other clients. The notification summary
  counts stay clinician-wide. The Messages page filters threads on the server, but a clinic's
  thread list already printed the clinic name inline (unchanged for single-clinic users).
- Removing a member from their last clinic clears the default clinic and resets the legacy
  `clinicians.role` to `provider`; the deployed backend's direct writes to `clinicians` are
  mirrored into memberships but are not audited (no actor is available to the trigger).

## Slice C design ("All clinics" lists with clinic chips and filters)

**Status:** merged with slice D in [#182](https://github.com/sjsu-masters-projects/medi-agent/pull/182); migration `067_clinic_lists_and_roles.sql` (see slice D)
applied October 17.

**Rule (unchanged from the agreed scope).** There is no global active clinic and no switcher.
A clinician's lists show every patient they hold an active care-team link to. The clinic of an
item is the clinic of **that clinician's link** (`care_teams.clinic_id`), never
`clinicians.clinic_id`. `UNIQUE (patient_id, clinician_id)` stays on the pair (slice H's job), so
each patient-clinician pair has exactly one clinic and a patient appears once per clinician.

### Backend

- `ClinicMembershipService.link_scope(clinician_id, clinic_id=None)` returns a `ClinicLinkScope`:
  the clinician's active links as `patient_id -> (clinic_id, clinic_name)`, built from one read of
  `care_teams` (`status = 'active'`, patient set, clinic's `display_name` embedded). With
  `clinic_id` it keeps only the links at that clinic **and only when the clinician holds an active
  membership there**; any other clinic (unknown, suspended, or one the caller does not belong to)
  gives the same empty scope, so the response neither errors nor reveals whether the clinic
  exists. Without `clinic_id` the scope is every active link, as before.
- Every clinician list builds its patient set from the scope and tags each item with `clinic_id`
  and `clinic_name`. The tags are new optional fields; the default response is the same rows.

| List | Route | Filter and tag |
| --- | --- | --- |
| Patient roster | `GET /api/v1/clinicians/me/patients` | scope patients; tags on each row |
| Patient header | `GET /api/v1/clinicians/me/patients/{id}` | tags from the caller's link (no filter) |
| Risk Radar | `GET /api/v1/clinicians/me/dashboard?clinic_id=` | rows, totals, pending ADR and MedWatch counts all follow the scope |
| Document review queue | `GET .../me/document-review-queue?clinic_id=` | scope patients |
| ADR assessments | `GET .../me/adr-assessments?clinic_id=` | scope patients |
| MedWatch drafts | `GET .../me/medwatch-drafts?clinic_id=` | scope patients |
| Sent messages | `GET .../me/messages?clinic_id=` | scope patients |
| Care conversations and recipients | `GET /api/v1/care-conversations/` and `/recipients?clinic_id=` | clinician callers only; scope patients |
| Appointments | `GET /api/v1/appointments/?clinic_id=` | clinician callers only; scope patients |
| Notification centre and action items | `GET /api/v1/notification-centre?clinic_id=` and `/action-items?clinic_id=` | SQL: the clinician's visible patients are narrowed to the clinic's links; the portal filters its shared cache by `clinic_id` instead |

  The notification centre pages by cursor inside `notification_centre_operation`, so a filter
  applied after the page would leave short or empty pages with a cursor. 067 narrows the patient
  array inside the function instead, and `notification_row` returns the link's `clinic_id` and
  `clinic_name` (it returned the clinician's default clinic's name). The summary counts stay
  clinician-wide (the bell does not follow a page filter).
- The denial classifier compares the clinics of the actor's **active memberships** with the clinics
  of the patient's active links (`care_teams.clinic_id`); `clinicians.clinic_id` is no longer read.
  MedWatch's identifier scrub uses the clinic names of the patient's active links
  (`care_teams.clinic_id` -> `clinics.display_name`) plus the link's own legacy `clinic_name`.
- Patient-facing lists are unchanged (patients have no clinic filter).

### Portal

- The portal assumes the new backend. Chips and the filter appear only when the caller has two or
  more active memberships (`GET /me/clinics`). A single-clinic clinician sees no chip, no filter
  and no new request parameter.
- The filter is the URL query parameter `clinic` (default: All clinics), so it survives a reload
  and back navigation. The portal sends `clinic_id` only after the user picks a clinic.
- Layout: see "Clinic chips and the Clinic filter" in the portal README. A neutral pill after the patient name
  (second line on narrow screens), a labelled "Clinic" select on the right of the toolbar, and
  "Linked at <clinic>" under the patient header name. An empty filtered list says "No patients at
  <clinic> match" with a "Show all clinics" text button.

### Still on the legacy columns after slice C (superseded by [after slice F](#still-on-legacy-columns-after-slice-f-what-remains))

Sign-in's default-clinic mirror columns and the `clinicians.clinic_name` fallback; care-plan SQL
that picks "the" link for a pair (slice H); notification and email clinic labels outside the centre
(slice F); cross-clinic scheduling (slice E).

## Slice D design (per-clinic roles, settings and invitations)

**Status:** merged with slice C in [#182](https://github.com/sjsu-masters-projects/medi-agent/pull/182). Migration `067_clinic_lists_and_roles.sql` applied
October 17. LOC-003's migrations were renumbered to 067/068 in [#181](https://github.com/sjsu-masters-projects/medi-agent/pull/181) and are also applied.

### What slice B already made membership-based

Staff listing, role changes and removal (`clinician_clinic_operation`), invitation create, list,
revoke and resend (`clinician_email_invitation_operation`: 066 checks `clinic_memberships.role =
'admin'` at the invitation's clinic, not `clinicians.role`), invitation history and patient
invite-code history per clinic. Slice D adds the missing UI (history, clinic picker where the
user belongs to several clinics) and the new actions below. No 057/058 function reads
`clinicians.role` any more; 067's verification block asserts it.

### New actions in `clinician_clinic_operation` (same signature)

| Action | Rule | Audit event |
| --- | --- | --- |
| `set_default` | the caller holds an active membership at an active clinic; changes only `clinicians.clinic_id` (role and name follow the membership, by the 066 trigger) | `default_clinic_changed` |
| `remove_member` (changed) | as in 066, and the removed member's own links and unused invite codes at that clinic end too (`care_link_ended` per row, actor = the admin, then `member_removed`) | see 066 |
| `leave` | the caller leaves one clinic. Refused for the caller's last active clinic (`last_clinic`) and for the sole active admin of the clinic (`sole_admin`). Deactivates the membership; moves the default to the earliest remaining clinic when it was the default | `member_left`, plus one `care_link_ended` per care-team row ended |
| `update_clinic` | admin at that clinic only; changes `clinics.display_name` and `canonical_name` (unique, `clinic_name_taken`) and the legacy `clinicians.clinic_name` of members whose default is that clinic | `clinic_renamed` |

All three run under the same lock order as 066 (clinic, clinician rows by id, memberships) and
write the audit row in the same transaction. The audit table's `action` and `target_type` checks
gain the new values; the table stays append-only (067 does not touch its triggers or grants and
re-checks them).

**Make default** changes only which clinic is preselected and the legacy mirror columns. The 065
mirror trigger used to mark the old default's membership inactive when `clinicians.clinic_id`
changed; 067 skips that when the new clinic is already an active membership of the same
clinician, so a switch of default never ends a membership. A legacy move to a clinic with no
active membership behaves as before.

### Decision: what Leave does to the clinician's patient links there

**Chosen: leaving ends the caller's own active and pending care-team links at that clinic**
(`care_teams.status = 'inactive'`, the same status an expired or revoked patient invite code
gets), in the same transaction, each recorded as a `care_link_ended` audit event. The confirm
dialog says so in plain words. Other clinicians' links, the patients, their records and the
clinic's other data are untouched; nothing is deleted.

Why not "links stay but are hidden": access is the active link (invariant a), so a link that
stays active but is hidden from lists would leave a former member with data access through direct
requests and the patient's alerts and messages routed to someone no longer at the clinic. Hiding
needs the same status change to be safe, so the simpler honest rule is to make it. Why not "block
leaving while active links exist": there is no hand-off or transfer tool yet, so the block would
trap anyone who ever linked a patient, and the only exit would be an admin removing them (which
today leaves their links active). Ending the links is reversible by the patient (a new invite code
from the same or another clinician) and is disclosed before the user confirms. Follow-up (not in
this slice): a hand-off flow so a clinic can reassign open work first. Open work the clinician
held for those patients (reviews, drafts, appointments) disappears from their lists; the records
remain.

Refusals: last clinic (they would have no clinic; they delete the account elsewhere), and sole
active admin (the clinic would have no one to manage staff; promote someone first). Disabled
buttons carry the reason.

### Staff, invitations and history in the portal

- Settings -> Team & Roles and Patient Invites: with several clinics a "Clinic" select picks which one the staff
  list, clinic code, invitation history and patient invite-code history show (the history calls
  pass `clinic_id`). With one clinic nothing changes.
- Staff role-change and remove actions render only when the caller is an admin **at the picked
  clinic** (the UX-003 remainder: non-admins used to see actions the server then rejected).
- Clinic name editing: an admin sees "Edit name" on that clinic's row in "Your clinics";
  `PUT /api/v1/clinicians/me/clinics/{clinic_id}` with `display_name`.
- "Your clinics" card on Settings -> General Profile: one row per active clinic with name, role chip,
  a "Default" badge, the clinic code and Copy button for admins, and two text buttons, "Make
  default" and "Leave".

### Endpoints added

| Endpoint | Clinic comes from | Rule |
| --- | --- | --- |
| `PUT /api/v1/clinicians/me/default-clinic` | body `clinic_id` | active member |
| `POST /api/v1/clinicians/me/clinics/{clinic_id}/leave` | path | active member; refusals above |
| `PUT /api/v1/clinicians/me/clinics/{clinic_id}` | path | admin at that clinic |

A clinic where the caller has no active membership answers `AUTHORIZATION_ERROR` (403, reason
`CLINIC_MEMBERSHIP_REQUIRED`) for these writes, as every clinic-scoped action does.

### Migration 067 and deploy order

`067_clinic_lists_and_roles.sql` requires 066. It extends the audit constraints, replaces
`clinician_clinic_operation` (three actions added, same signature, same grants),
`private.mirror_legacy_clinic_membership` (switching default is not leaving), `private.notification_row`
and `public.notification_centre_operation` (clinic filter, link's clinic) and keeps the fail-closed
checks. **Order:** the requester applies 067 before this backend deploys, because the new routes
call the new actions; the currently deployed backend keeps working once 067 is applied (every
replaced function keeps its signature and behaviour for the old payloads). The product is not live, so a few
minutes of portal and backend mismatch after a merge is accepted (no old-shape fallbacks).

## Slice E design (cross-clinic scheduling and conflict checks)

**Status:** merged with slice F in [#183](https://github.com/sjsu-masters-projects/medi-agent/pull/183). Migration `069_clinic_scheduling_and_tags.sql`
applied October 17 (read-only overlap preflight returned 0 rows; 38 appointments backfilled).

**Rule.** No global active clinic and no switcher. Access is the active care-team link, and each
patient-clinician pair has one link and so one clinic. An appointment (and every slot of an offer
group) carries the clinic of the link it was made under.

### Schema (069)

- `appointments.clinic_id` (→ `clinics`) and `appointments.clinician_id` (→ `clinicians`, cascade),
  backfilled from `care_teams`, then `NOT NULL`. `BEFORE INSERT OR UPDATE OF care_team_id, clinic_id,
  clinician_id` trigger `appointments_link_guard` overwrites both from the link whatever the writer
  sent, and refuses a link with no clinic. `AFTER UPDATE OF clinic_id, clinician_id` trigger on
  `care_teams` carries a moved link's appointments with it (and fails the whole statement if that would
  double-book the new clinician).
- **Fail closed, counts only.** Before changing anything the migration counts appointments that cannot
  be matched to exactly one link that has a clinic and a clinician (the foreign key makes "exactly one"
  by primary key; the clinic-less link is the real case) and existing confirmed/scheduled overlap pairs
  per clinician. Either aborts with a message of counts only, nothing changed, nothing cancelled. The
  read-only `backend/scripts/appointment-clinician-overlap-preflight.sql` lists the pairs for review.
- **Constraint.** `appointments_clinician_no_overlap`: `EXCLUDE USING gist (clinician_id WITH =,
  appointment_booking_window(scheduled_at, duration_minutes) WITH &&) WHERE status IN ('confirmed',
  'scheduled')`, the same `[start, end)` window as the patient constraint from 043, across every clinic.
  Proposed options do not reserve time. The patient constraint and `respond_to_appointment_offer` are
  unchanged: a lost race on accept is the existing safe `conflict` result.
- **Offers.** `propose_appointment_slots` (same signature and grants) takes a per-clinician advisory
  lock, checks every slot against the clinician's whole schedule and returns `clinician_conflict` with
  one entry per conflicting slot: `slot`, the other visit's `clinic_id`, `clinic_name`, `starts_at`,
  `ends_at`. It reads no patient. Nothing is saved when any slot conflicts (no partial offers: an offer
  needs 2-4 slots).
- `authorization_denial_events.clinic_id` (nullable) and the notification centre's clinic label for
  appointment items and appointment reminders now follow the appointment's own clinic (a reminder
  carried no clinician, so a patient with two clinics could be shown the other clinic).
- 069's verification block asserts both constraints, no NULL clinic, appointment equals link,
  `NOT NULL`, browser roles cannot execute the offer functions or guards, the denial trail is still
  append-only and backend-only, and that table and function privileges are identical before and after.

### Backend

`GET /appointments/` rows carry the appointment's own `clinic_id`/`clinic_name` for both roles; a
clinician's list reads only visits at clinics where they hold a link (a shared patient's visits at an
unrelated clinic are not shown). `POST /appointments/propose` and a clinician's single
`POST /appointments/` refuse with 422 `CLINICIAN_SCHEDULE_CONFLICT`, `details.conflicts[]`, message "You
already have an appointment at <clinic> from <time> to <time>." (UTC in the server text; the portal
renders local times from `details`). A patient's accept or self-booking that meets a busy clinician gets
the existing generic `APPOINTMENT_CONFLICT`. The refusal is logged by count only. Calendar/ICS location,
summary and description name the appointment's clinic.

### Portals

Clinician: rows are time (bold), patient, clinic chip (two or more memberships only), status chip; at
390 px time + status on line 1, patient + chip on line 2. The offer form shows a read-only muted "Clinic:
X" from the selected patient's link (no picker), and each conflicting slot gets an inline `risk-soft`
callout with the sentence above; submit stays disabled until each conflicting slot is changed or removed.
Patient: visit and offer cards show "at <Clinic>" / "en <Clínica>" under the date; notification items show
the clinic as small secondary text under the title.

## Slice F design (clinic tags in notifications, email and audit)

Everything outside the notification centre that labelled a clinic from `clinicians.clinic_name` or
`clinicians.clinic_id` now reads the link's or the appointment's clinic.

| Surface | Clinic comes from |
| --- | --- |
| Appointment reminders (scheduled job) | the appointment; body "Clinic: X." and `metadata.clinic_id/clinic_name` |
| Message notice to a patient (`clinician_messages`) | the sender's link to the patient; body prefix and metadata |
| Notice emails (message, appointment offered/changed/response, ADR information request, document review, care-plan draft, critical result) | the appointment, or the link between patient and the clinician the notice concerns; shown only to a recipient who belongs to two or more clinics: subject `<Clinic> · …`, plus a header line under the brand. Notices with no single link (care plan published, document failed) carry none. A failed lookup defers the row for retry rather than sending it untagged |
| Staff invitation email | the invitation's clinic, header line (subject already names it) |
| Care-team list, Today provider card, plan preview provider, Nora care-team context | the link (`care_teams.clinic_id` → `clinics.display_name`) |
| Authorization denials | `authorization_denial_events.clinic_id`, set when the refusal concerns a link (appointment raise sites) |
| FHIR audit events | `AuditEvent.extension` `urn:mediagent:audit-clinic` = the clinic of the actor's single link to the patient; none when the actor has no link or links at two clinics |
| MedWatch | Section G (reporter) never carried a clinic. The identifier scrub already used the patient's links' clinics (slice C) |

Bilingual: the clinic name is data, so email and notification tags add no wording. New Spanish wording
(drafts, not approved): "en {clinic}" on patient cards and "Clínica" in the calendar export.

### Still on legacy columns after slice F (what remains)

- `clinicians.clinic_id`/`clinic_name`/`role` as the default-clinic mirror (065/066/067 triggers) and
  sign-in's default clinic.
- `care_teams.clinic_name` (the link's own legacy text): last-resort label for a link with no clinic in
  the care-team list, the MedWatch identifier scrub (extra caution, a superset of the clinic names),
  and the notification centre's `coalesce(cl.display_name, ct.clinic_name)` fallback.
- `notification_authorized` (066) and care-plan SQL that picks "the" link for a pair (slice H).

### Known limitations (E and F)

- A clinician's own colleagues at the same clinic still see each other's visits for a shared patient
  (unchanged); other clinics' visits are hidden. Other clinics see no "busy" blocks yet: only the owner
  sees the conflict, which names the clinic.
- Editing a confirmed visit's time into a clash returns the generic conflict, not the clinic sentence.
- Notices for a patient with two links to the same clinician at different clinics name no clinic.
- Email clinic names reveal the clinic to the mailbox; recipients with one clinic see no tag.

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

Slices C and D add these proofs (backend unit/router, Docker PostgreSQL, portal):

| | Invariant | Slice C and D proof |
| --- | --- | --- |
| a | No patient data without an active care-team link; Leave ends the links it should | Docker: `test_leaving_ends_the_membership_and_only_the_callers_links_there`; unit: `test_patient_roster_tags_filters_and_hides_other_clinics`, `test_clinic_without_membership_returns_empty_even_when_links_exist`, `test_link_scope_for_a_clinic_without_membership_is_empty_not_an_error` |
| b | Clinic-scoped endpoints check membership and role for the named clinic | Docker: `test_only_that_clinics_admin_can_rename_it`, `test_make_default_ends_no_membership_and_is_audited` (non-member clinic refused); router: `test_default_leave_and_rename_call_the_membership_service`; portal: `Settings team and roles` admin-at-picked-clinic tests |
| c | No role or admin rights carry between clinics | Docker: `test_invitation_admin_rights_do_not_read_clinicians_role`; portal: `shows staff role and removal actions only to an admin at the picked clinic` |
| e | No MFA bypass | unchanged (no sign-in path touched) |
| f | Audit coverage per action | Docker: the make-default, leave (`member_left` + one `care_link_ended` per row) and rename tests assert the rows |
| g | The audit table has no UPDATE or DELETE for any role | Docker: `test_the_new_audit_actions_keep_the_trail_append_only_and_backend_only`; 067's verification block re-checks triggers and grants |
| h | Browser roles have no writes | Docker: `test_browser_roles_cannot_write_clinicians_memberships_or_the_audit` (067 applied) and the new operations are refused to `authenticated` |
| i | A list never shows another clinic's data for a clinic the caller lacks, and never reveals it | unit: per-list tests (own, other, non-member, no filter) in `test_clinician_service`, `test_appointment_service`, `test_care_conversation_service`, `test_medwatch_service`; Docker: `test_clinic_filter_and_link_clinic_on_notification_items` |
| j | Single-clinic users see no chip and no filter | portal: `shows no clinic chip and no clinic filter for a single-clinic clinician` and the per-page tests |


Slices E and F add these proofs:

| | Invariant | Slice E and F proof |
| --- | --- | --- |
| a | Nothing is visible without an active link; appointments of other clinics stay hidden | unit: `test_clinician_appointments_carry_the_links_clinic` (reads only the caller's clinics), `test_clinician_appointments_for_an_unrelated_clinic_are_empty` |
| b | Clinic-scoped writes check the clinic | the offer RPC requires the caller's own active link; Docker `test_offer_checks_the_whole_schedule_and_names_only_the_clinic` |
| c | Clinician conflicts cross clinics, not clinicians | Docker: `test_same_clinician_cannot_overlap_across_two_clinics`, `test_back_to_back_visits_and_other_clinicians_are_allowed`, `test_proposed_options_do_not_reserve_time` |
| f | Audit: refusals are logged without other clinics' patients | unit: `test_offer_conflict_names_the_clinic_and_never_a_patient` (counts-only log), `test_a_denial_that_concerns_a_link_records_its_clinic`, `test_fhir_audit_events_carry_the_clinic_of_the_actors_link` |
| g | The denial trail stays append-only | Docker: `test_denial_events_gain_a_clinic_and_stay_append_only`; 069's verification block |
| h | Browser roles and grants unchanged | Docker: `test_constraint_present_and_no_appointment_without_a_clinic`; 069's before/after privilege comparison |
| i | Backfill and fail-closed | Docker: `test_backfill_tags_each_appointment_with_its_links_clinic_and_clinician`, `..._stops_when_a_link_has_no_clinic_and_changes_nothing`, `..._stops_on_existing_clinician_overlap_and_reports_counts_only` |
| j | Clinic tags are right for multi-clinic people | Docker: `test_reminder_and_appointment_items_name_the_appointments_clinic`; unit: email `test_every_notice_names_the_clinic_when_given_and_is_unchanged_without` (en-US, es-MX, clinician), `test_clinic_label_only_for_recipients_with_several_clinics`, cron, calendar; portals: per-card and per-row tests |

Also check: no existing migration edited; the validator unchanged; the CI minimum for
`test_clinic_memberships_postgres` raised to the new count; no email address or name in the
audit rows, logs or fixtures; synthetic data only.

## Suggested slices

| Slice | Scope |
| --- | --- |
| A | Memberships, backfill and RLS (no visible change) |
| B | Sign-in once and add a clinic to an existing account |
| C | "All clinics" lists with clinic chips and filters (branch `feature/clinic-lists-and-roles`) |
| D | Per-clinic roles, settings and invitations (same branch) |
| E | Cross-clinic scheduling and conflict checks (branch `feature/clinic-scheduling-and-tags`) |
| F | Clinic tags in notifications, email and audit (same branch) |
| G | Shared clinical core (medications, allergies, conditions, critical alerts) with per-team ownership of everything else, and the patient's visibility control |
| H | Care plans per care team (PLAN-002) |
