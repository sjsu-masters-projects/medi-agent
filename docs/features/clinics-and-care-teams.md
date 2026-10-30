# Clinics, care teams and handoff summaries

A clinician signs in once and may belong to several clinics. Patients are reached only
through care-team links, each tagged with a clinic. Clinicians also write reviewed handoff
summaries for colleagues. Care plans per team are in [care plans](care-plans-and-today.md).

## What it does

- **Clinician.** One sign-in (email, password, MFA), no clinic code. Lists open on "All
  clinics" with clinic chips and a Clinic filter when the clinician has two or more clinics.
  A clinic is chosen only inside an action that belongs to one clinic (invite, team roles,
  clinic settings, offering a visit). "Your clinics" shows role, default, and Leave.
- **Admin.** Per clinic: invite or remove staff, change roles, rename, see the clinic code.
- **Patient.** Care-team members, offers, visits and reminders name the clinic.
- **Shared record.** Every clinician on a patient's teams sees active medications,
  allergies, critical results and the other teams (rules 11 and 12).

## Rules it must keep

1. Access to a patient is the active care-team link and nothing else. Clinic membership
   grants no patient access; no RLS policy or access helper reads memberships.
2. A link is unique on (patient, clinician, clinic) and takes the clinic of the invite code
   the patient used. A database trigger fills a missing clinic, rejects a clinic where the
   clinician has no active membership, and refuses clearing it.
3. There is no global active clinic and no header switcher. A clinic-scoped action takes an
   explicit `clinic_id` checked against an active membership, and the role comes from THAT
   membership, never `clinicians.role`. With several memberships and none named: 422
   `CLINIC_REQUIRED`. With none: refused (fail closed). Clinics compare by id, never name.
   Sign-in with no active membership is refused (`NO_ACTIVE_CLINIC`).
4. Admin rights apply only at the clinic where the clinician is admin, enforced in the
   service and again in SQL. The open clinic code is returned only to an admin there. Any
   member may create their own patient invite codes.
5. Adding a clinic never skips MFA: by code only as Provider or Nurse (admin only by
   invitation); a member removed by that clinic's admin must be re-invited
   (`MEMBERSHIP_INACTIVE`); password-only invitation acceptance by an MFA account that has
   a clinic is `SIGN_IN_TO_ACCEPT`. One account per email (`ACCOUNT_EXISTS`); profile
   updates cannot change the clinic.
6. Memberships are deactivated, never deleted. Browser roles cannot write `clinicians`,
   memberships or the audit. The membership audit is append-only for every role, written in
   the same transaction as the change, with ids and types only (no email or name).
7. Leave ends the caller's own active and pending links and unused invite codes at that
   clinic (each audited), and is refused for the last clinic and the sole admin. The
   confirm dialog says in plain words that those links end. Removing a member ends theirs
   too. Nothing is deleted; other clinicians' links are untouched.
8. A filter naming a clinic the caller does not belong to returns the same empty result as
   an unknown clinic, so existence is never revealed. Notification summary counts stay
   clinician-wide.
9. A clinician cannot hold overlapping confirmed or scheduled visits at any clinic; an
   offer checks the whole schedule and a clash returns the other visit's clinic and times,
   never patient data, and the refusal is logged by count only. An appointment's clinic is
   overwritten from its link. Other
   scheduling rules are in [scheduling](scheduling.md).
10. Only the appointment's own clinician, or a colleague with an active link to that
    patient at the appointment's clinic, may edit or export it; a link at another clinic
    grants nothing.
11. Shared core: active medications and allergies carry the recording team and clinic, and
    the patient cannot hide them (a hidden one is how interactions and reactions are
    missed). Critical-result alerts are shared. Active conditions are shared unless the
    patient marks one sensitive: only its recording team sees it; others see "Some
    conditions are kept private by the patient", never a silently partial list. A sensitive
    condition with an unknown recorder is visible to no clinician. The sensitive-condition
    rule is a product rule, not a legal opinion; confirm it before any real use.
12. Owned by one team and not shared: documents, that team's plan detail, chat and
    messages, SOAP notes, ADR reviews. Other teams see only that a plan exists.
13. A clinic tag comes from the link or the appointment, never `clinicians.clinic_id`.
    Email shows a clinic tag only to recipients with two or more clinics; a failed lookup
    defers the row rather than sending it untagged.
14. No coverage or delegation: a clinician sees a patient only through their own link.

## Handoff summary

A clinician drafts a summary of one patient for a colleague, care team or transition,
reviews and edits it, approves it, and only then exports or shares it. It reuses the
bounded patient timeline and care-team ownership; there is no separate event store.

1. Sections are built deterministically with no model, from records the author may see.
   The narrative and notes are written by the clinician and labelled so. A section whose
   read fails is `unavailable`, never `empty`, and approval is refused while any is.
2. Sections: patient; shared record (other teams' sensitive conditions become "Some
   conditions are private and are not included in this summary."); the author team's plan;
   30-day adherence (shared activities plus the author team's) and confirmed symptoms; open
   medication-safety reviews by the author's team (unreviewed ones are not copied); the
   link's upcoming visits; newest 8 timeline events, private conversations excluded. Each
   line has a source chip. Failures log only the section name and exception type.
3. A summary belongs to one care-team link and its author. The database re-checks the
   actor's active link; missing, another team's and another patient's summaries answer
   alike (`42501`, HTTP 404). An unassigned clinician gets an audited 403.
4. Saving creates a new version (`expected_version`, else 409 `HANDOFF_VERSION_CONFLICT`);
   "Rebuild from records" is a new version. Versions and events are append-only; events
   hold ids and types only. Create is idempotent by client id, approve replay-safe, with
   a row lock, database clock, and bounds of 50 summaries per patient and team and 200
   versions. Tables have no browser grants; responses are `no-store`.
5. Approve pins the current version; any edit returns to draft. Print and FHIR export
   (`POST .../export` `{version, format: print|fhir}`) are allowed only for the approved
   current version (422 `HANDOFF_NOT_APPROVED`) and every export is audited. FHIR is an R4B
   document Bundle (Composition, Patient, Practitioners, Provenance), generated on demand
   and never pushed.
6. Sharing: only the author, while holding the link, and only an approved current version.
   Recipients are clinicians with an active link to the patient at a clinic where they are
   active members, or active members of the author's clinic; never the author (422
   `HANDOFF_RECIPIENT_NOT_ALLOWED`), re-checked on every share and read. A share is per
   version and revocable; revocation is immediate, and losing eligibility ends access.
7. A recipient sees only the shared version, read-only, with source chips as labels (record
   ids and links are stripped), plus print and export. No team, versions or audit, and no
   access to the patient. A `handoff_shared` notification is written in the share
   transaction, once per share generation, with no email; views are audited once per ten
   minutes per reader. At most 50 active shares per summary.
   Clinician-only copy: no es-MX wording exists.

API under `/api/v1/care-team/clinician`: `POST|GET /patients/{pid}/handoff-summaries`,
`GET|PUT .../{id}`, `.../approve`, `.../export`; `GET /handoff-summaries/{id}/
share-candidates`, `GET|POST .../shares`, `DELETE /handoff-shares/{share}`, `GET
/shared-handoffs[/{share}]`, `POST /shared-handoffs/{share}/export`. Any refusal on a
share route is the same 404.

## Why it was built this way

- Memberships plus care-team links: a provider at two clinics has two links per patient,
  so access, plans and audit stay per link. Rejected: a global active clinic.
- Leave ends links rather than hiding them: a hidden active link still grants access.
  Rejected: blocking Leave, which traps anyone who ever linked a patient.
- The narrative is clinician-written: no grounded, cited generator fits yet.

## Excluded on purpose

Coverage or delegation; a clinic switcher; model-written handoff narrative (if one is ever
added it must be a marked draft with citations and never feed the deterministic sections);
patient-facing handoffs; pushing exports to a server; sharing drafts or edited versions.

## Where it lives

- Backend `backend/src/app/`: `services/clinic_membership_service.py`, `clinic_link_scope.py`,
  `staff_service.py`, `appointment_schedule_service.py`, `handoff_summary_service.py`,
  `handoff_summary_builder.py`, `handoff_share_service.py`, `handoff_fhir_export.py`;
  routers `clinics.py`, `clinicians.py`, `staff.py`, `handoff_summaries.py`,
  `handoff_shares.py`. Migrations `065`-`067`, `069`, `089`, `096`.
- Clinician `apps/clinician-portal/src/`: `components/features/your-clinics-card.tsx`,
  `clinic-chip.tsx`, `handoff-summary-review.tsx`, `handoff-share-panel.tsx`;
  `services/handoff-summaries.ts`.

## How to check it

QA handoff [3.3](../qa-handoff-2026-10.md#33-care-team-plans) (Elena, two clinics),
[3.4](../qa-handoff-2026-10.md#34-handoff-summaries) and
[3.7](../qa-handoff-2026-10.md#37-scheduling). From `backend`: `pytest
tests/unit/services/test_clinic_membership_service.py tests/unit/services/test_handoff_summary.py
tests/integration/routers/test_handoff_summaries_api.py --no-cov`. Postgres contracts need
`NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER=1` (memberships, scheduling) or
`CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER=1` (handoff; CI shard `care-handoff`). Portal:
`npx vitest run handoff-summary clinic-filter`.

## Still open

- No hand-off tool when a clinician leaves a clinic: their reviews, drafts and visits leave
  their lists and nobody inherits them. Rejoining needs new patient links.
- Other clinics do not see "busy" blocks on a shared clinician's calendar; only the owner
  sees the clash. There is no per-clinic availability.
- Signup returns `ACCOUNT_EXISTS`, which allows account enumeration; a neutral response
  plus an email is the follow-up.
