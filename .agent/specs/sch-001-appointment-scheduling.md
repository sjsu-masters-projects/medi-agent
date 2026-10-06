# SCH-001 — Appointment scheduling design

> **Status:** Draft for review · **Owner:** Tushar Singh (patient portal, scheduling)
> · **Clinician-portal work:** coordinate with Jeevan Kurian
> **Tracker:** `.agent/TASKS.md` → SCH-001

This document defines the whole appointment feature end to end so the vertical
slices build toward one coherent, clinically-correct product rather than a set of
disconnected screens. It supersedes the ad-hoc slice notes for anything it conflicts
with.

## 1. Goal

Let an outpatient clinic and its chronic-care patients agree on a visit time inside
the product, with a full audit trail, in both English (`en-US`) and Mexican Spanish
(`es-MX`), using synthetic data only. MediAgent is supervised decision support: a
clinician always controls which times are on the table; the model never books,
proposes, or parses a time.

## 2. UX decision — clinician offers slots, patient picks one (Option B)

**Decision:** The clinician offers a small set of candidate times (2–4). The patient
picks the one that works, which confirms it. The patient may also decline the whole
offer, ask for different times (with an optional note), or cancel a confirmed visit.

**Why (rationale):**

- **Clinician authority is preserved.** Only times the clinician offered can be
  booked. This matches the product's supervised posture.
- **Fewer round trips** than proposing a single time and waiting for accept/decline.
- **Accessible for the target cohort.** Choosing among 2–4 clearly labelled options is
  easier for older or less tech-savvy patients, and translates cleanly to `es-MX` and
  to screen readers, versus navigating a full calendar grid.
- **No availability engine required.** The clinician asserts "I can do these," so we
  do not need free/busy, working-hours, or calendar-sync infrastructure.

**Rejected alternatives:**

- *Single proposed time (accept/decline only)* — too much back-and-forth; every "no"
  is a full round trip. This is the Slice 1–2 foundation and an acceptable fallback if
  the timeline forces it, but not the target.
- *Patient self-books from an open calendar* — requires real availability management
  and removes clinician control over who books when. Out of scope for this project.

**Boundary that is not optional:** all concrete times come from a date/time picker
that emits a structured timestamp. We never parse a time from free text. The patient's
optional note is a message to the care team, not a scheduling input.

## 3. Roles and journeys

### Clinician (proposing side)

1. Opens a patient they are assigned to.
2. Uses a **date/time picker** to offer 2–4 candidate times for one visit.
3. Sees the patient's response (picked a time / declined / asked for different times).
4. If the patient asked for different times or declined, **re-proposes** a new set.
5. Later, marks a visit completed or no-show (future).

### Patient (responding side)

1. Opens **Visits** and sees an offer: "Your clinician offered these times."
2. **Picks one** → that time is confirmed; the other candidates are withdrawn.
   - or **declines the offer** (with optional note),
   - or **asks for different times** (with optional note),
   - or later **cancels** a confirmed visit (with optional note).
3. Sees the confirmed visit under "Upcoming," in their own timezone and language.

## 4. Data model

Evolve the existing `appointments` table rather than adding a parallel one, so the
Slice 1–2 machinery (rows, statuses, RLS, authorization, list rendering) carries over.

**Additions:**

- `proposal_group_id uuid NULL` — candidate slots offered together share one group id.
  `NULL` for a standalone or legacy appointment.
- New status `withdrawn` — a candidate the patient did not choose, or one the clinician
  retracted. (Distinct from `declined`, which is the patient rejecting the whole offer,
  and `cancelled`, which ends a booked visit.)

**A "proposal" is** one or more `appointments` rows sharing a `proposal_group_id`, each
created as `proposed` with its own `scheduled_at`.

### State machine

```
  clinician offers a group of candidate slots (each 'proposed')
        |
        v
   proposed ──patient picks THIS slot──────► confirmed
      │  │                                       │
      │  │   (its siblings in the group) ──────► withdrawn
      │  │
      │  ├──patient declines the offer────────► declined      (whole group)
      │  └──patient asks for different times──► alternative_requested (whole group)
      │
   confirmed ──patient or clinician cancels──► cancelled
   confirmed ──visit happens (future)────────► completed / no_show

   Legend: proposed/confirmed/declined/alternative_requested/cancelled = built (Slices 1–2, single-slot)
           withdrawn and group semantics                              = Slice 3b (local)
           completed/no_show UI                                       = future
```

**Group-level rules:**

- **Pick one:** chosen slot → `confirmed`; sibling `proposed` rows in the group →
  `withdrawn`. Done in one transaction.
- **Decline / request-different:** applies to every `proposed` row in the group.
- **Cancel:** applies to a single `confirmed` (or `scheduled`) visit.

## 5. Time, timezone, and language rules

These are correctness requirements, not polish.

- **Storage:** `scheduled_at` is `timestamptz` (already). Always store an exact instant.
- **Patient rendering:** show times in the **patient's stored timezone**
  (`patients.timezone`, e.g. `America/Los_Angeles`), not the browser's, and in the
  **selected locale** (`en-US` / `es-MX`), with the timezone shown explicitly.
- **Clinician rendering:** show times in the clinic/patient timezone with the zone
  labelled, so a clinician in another zone cannot misread a slot.
- **No free-text time parsing**, ever.

**Slice 3a implementation:** Visits reads `preferred_language` and `timezone` from the
patient profile. All page-owned copy uses `en-US` or `es-MX`; clinician-entered reasons
and patient notes remain as written. Dates use the saved timezone and display its name.
While settings load, appointment times remain hidden. Failed profile requests fall back
to English and explicitly labelled UTC with a notice and retry; missing/invalid zones
also use labelled UTC, preserving the saved language when available. Profile results
are scoped to the authenticated session and late responses are ignored. Existing
`usePatientProfile()` callers retain their profile-or-null interface.

Load and action failures use localized messages; action failures keep visits visible.
No backend API or migration change is needed for this slice.

## 6. Clinical-safety and authorization constraints

- Only an **assigned clinician** may propose or re-propose for their care-team patient.
- Only the **owning patient** may respond to their own appointment/offer.
- A slot can be confirmed only while still `proposed`; withdrawing siblings only affects
  the same `proposal_group_id`.
- No double-booking: a patient cannot hold overlapping `confirmed` or `scheduled`
  visits after Slice 5 migrations are applied. Adjacent visits are allowed.
- Slice 5 expires proposals seven days after creation, with individual deadlines
  capped at each slot's start time. Authorized reads/responses persist expiry.
- Every transition is auditable (who, what, when). The model proposes/parses nothing.

## 7. API surface

- `POST /appointments/propose` *(clinician, implemented in Slice 3b)* — offer a group of candidate slots
  `{ care_team_id, slots: [datetime, …], reason?, location? }` → creates the proposed
  group. Legacy single-slot proposals retain `POST /appointments/`.
- `POST /appointments/{id}/respond` *(exists)* — patient `accept` (pick this slot),
  `decline`, `request_alternative`, `cancel`, each with an optional `note`. `accept`
  becomes group-aware (confirm this, withdraw siblings).
- `GET /appointments/` *(exists)* — returns the patient's visits / a clinician's
  assigned-patient visits.
- `GET /appointments/{id}/calendar?locale=en-US|es-MX` *(Slice 6)* — authenticated
  JSON `{ filename, content }` for a one-time `.ics` download; own patient or active
  assigned clinician, current confirmed/scheduled status, private/no-store response.

## 8. What is already built, and how it evolves

- **Slice 1 (PR #97):** statuses `proposed/confirmed/declined`; clinician-created visit
  starts `proposed`; patient accept/decline; patient-portal Visits page. Still valid.
- **Slice 2 (branch `feature/sch-001-slice-2-visit-changes`):** `request_alternative`,
  `cancel`, optional note; transition table; inline action errors. Still valid.
- **Evolution:** Slice 3 generalises the single proposed appointment into a *group* of
  candidate slots and makes `accept` confirm-one-withdraw-siblings. The transition table
  and endpoint are extended, not replaced.

## 9. Revised slice plan

| Slice | Scope | Lane |
| --- | --- | --- |
| 1 ✅ | Propose single slot + accept/decline | Patient/backend |
| 2 ✅ | Request-alternative + cancel + note | Patient/backend |
| **3a** | **Saved timezone + locale rendering, full Visits copy translation, labelled UTC fallback (implemented locally)** | Patient |
| **3b** | **Multi-slot offer + patient "pick one", group-aware responses and atomic audit (implemented locally; staging acceptance pending)** | Patient/backend |
| **4** | **Clinician Appointments screen: offer 2–4 slots, view responses/notes, re-propose (implemented locally; live acceptance/review pending)** | Clinician (Jeevan review) |
| **5** | **Patient overlap protection and seven-day proposal expiration (migrated; live synthetic API checks passed October 3; review pending)** | Backend/portals |
| **6** | **One-time calendar export (implemented; local builds, tests and authenticated browser downloads passed October 3; review/merge pending)** | Patient/clinician |

Slice 4 provides the clinician screen locally. October 3 live acceptance evidence
for Slice 5 and calendar downloads is below. Clinician review with Jeevan, merge,
dependency remediation and target-deployment verification remain release work.

## 10. Open decisions

- Candidate count is fixed at 2–4 for the grouped proposal endpoint; legacy single-slot proposals remain supported.
- Offer expiry is seven elapsed days (168 hours), capped at each slot's start.
- Whether a patient may hold only one active offer per visit reason at a time.
- Exact clinician-portal ownership split for Slice 4.

## 11. Slice 3a acceptance evidence

Local verification on 2026-09-26: patient portal lint and typecheck pass; all 121 tests
in 29 files pass; `npm run build -- --webpack` passes. A clean `npm ci` restored the
missing PDF viewer dependency without changing manifests or lockfiles and reported
zero vulnerabilities. No API or migration change was required.

Manual acceptance: log in as a synthetic patient, check the saved timezone in Profile,
open Visits, then save Español (México) in Profile and return to Visits. Confirm dates,
headings, statuses, controls, note prompts, and retry messages use Spanish while
patient notes and visit reasons remain unchanged. Switch back to English and repeat.
The user confirmed the live display changes on 2026-09-26; existing Slice 2 writes still
require migration `039` to be applied separately through the authorized process.

## 12. Slice 3b contract and manual acceptance

`POST /api/v1/appointments/propose` is clinician-only and accepts `care_team_id`,
2–4 distinct timezone-aware `slots`, optional `duration_minutes` (5–480, default 30),
`appointment_type` (default `follow_up`), `location`, and `reason`. Times must be in the
future. The response is the created appointment list with a shared `proposal_group_id`.
Existing list/respond responses gain an optional `proposal_group_id`; standalone
appointments retain null. The respond endpoint still returns the addressed appointment.

Accept confirms that slot and withdraws its proposed siblings. Decline and
request-alternative change every proposed slot in the offer and retain the optional note.
Cancel changes only a confirmed/scheduled visit; grouped proposed offers use decline.
The Visits hook applies these committed group transitions to its loaded rows, so sibling
buttons disappear immediately. Reloading reads the authoritative database state.

Migrations `040` and `041` must follow `039` and precede grouped-offer writes. The first
adds the group field, withdrawn status, one-confirmation constraint, and restrictive
policies blocking direct authenticated group writes. The second adds service-only,
security-invoker RPC functions and append-only `appointment_offer_events`. Group locks,
ownership checks, mutation, and per-slot audit events run in one transaction. Generic
appointment PATCH/PUT operations refuse grouped rows. Cross-visit conflict prevention,
offer expiry, and clinician proposal/re-proposal screens remain later slices.

Audit records intentionally retain their appointment/patient references. The existing
demo reset cannot delete patients with these audit records; do not reset such a shared
environment. Any future reset/purge path needs a separately reviewed retention design.
The new audit table is for workflow history, not additional demo clinical content.

### Click-through steps

1. Have the authorized database owner apply migrations through the ledger-backed
   `scripts/apply-supabase-migrations.sh` process in the setup guide. This implementation
   applies no remote migration. Ensure `039`, `040`, and `041` are recorded as applied.
2. Identify an active synthetic patient/clinician care team. The patient can read their
   care-team IDs with `GET /api/v1/patients/me/care-team` in API docs. Use the clinician
   assigned to that care team for the next request; keep login tokens out of chats/docs.
3. In local API docs, authorize as that clinician and use **appointments →
   POST /api/v1/appointments/propose**. Replace the example care-team ID with the actual
   synthetic care-team ID, and choose future dates with explicit timezone offsets:

   ```json
   {
     "care_team_id": "00000000-0000-4000-8000-000000000001",
     "slots": ["2026-10-05T09:00:00-07:00", "2026-10-06T14:00:00-07:00"],
     "duration_minutes": 30,
     "appointment_type": "follow_up",
     "location": "Telehealth",
     "reason": "Synthetic appointment offer test"
   }
   ```

4. As the matching patient, open Visits. Expect one offer card with two times. Choose
   the second time: only it moves to Upcoming/Confirmed; the other appears Withdrawn in
   Past & other. Refresh to confirm the result persists.
5. Create fresh offers to test **Decline these times** with an optional note and
   **Request different times** with an optional note. Every candidate moves to the
   corresponding state. An already chosen/withdrawn slot cannot be accepted again.
6. Save Español (México) in Profile and revisit Visits to check the translated choices
   and prompts. The example times stay 9:00 a.m. and 2:00 p.m. in America/Los_Angeles.

The clinician portal can create these offers through Slice 4's Appointments screen;
see section 13 below for the UI acceptance path.

### Slice 3b verification — 2026-09-26

Backend Ruff/mypy pass; 42 migrations parse; all 1,359 backend tests pass with 83.81%
coverage. Eight transaction/RLS tests execute migrations 038–041 against a disposable
PostgreSQL 18.6 cluster, using the actual hardened private RLS helpers. They cover
concurrent accepts, group responses/notes, sibling isolation, caller/function grants,
direct-write denial, append-only events, active-assignment audit visibility, and rollback
when an audit insert fails. Server binaries are optional for ordinary test discovery:
the transaction tests explicitly skip when only PostgreSQL client tools are installed.
For release acceptance, run them with server binaries on PATH and confirm none skip.

Patient portal lint/typecheck, all 130 tests, and the webpack production build pass.
Clinician typecheck passes with the extended shared types. Its existing missing PDF
library was restored using `npm ci` (zero vulnerabilities; lockfiles unchanged).
Local HTTP checks and authenticated staging acceptance are recorded in the tracker.

### Migration ledger follow-up — 2026-09-28

The user supplied a 46-entry ledger listing containing all 42 migrations in this
checkout, including appointment migrations 038–041. Its four additional files are
`038_document_summary_lifecycle.sql`, `039_document_summary_retry_schedule.sql`,
`040_clinician_approved_care_plans.sql`, and
`041_backfill_document_grounded_care_plan_requests.sql`. A refreshed `origin/main`
at `c2567cd` contains these files; the scheduling branch predates them. The earlier
45-versus-42 verifier error reflects differing inventories, not an identified
appointment migration failure. The later filename listing has one more entry than
that earlier count; its timing was not independently verified.

Integrate current main while preserving working-tree changes, keep applied migration
filenames unchanged, and compare checksums before declaring the ledger synchronized.
Filename presence alone does not independently verify schema contents or the full
patient action journey. No remote database access or migration was performed for
this diagnosis.


## 13. Slice 4 — clinician Appointments screen

The `/appointments` sidebar destination uses the existing authenticated API client.
`GET /clinicians/me/patients` supplies assigned patient names and care-team IDs.
Selecting a patient loads their existing profile endpoint for the saved timezone.
The picker and history both label that timezone explicitly; browser timezone does
not determine the submitted instant. Missing/invalid saved zones use labelled UTC.
Profile load failures block entry and expose retry instead of guessing a zone.

The form offers 2–4 structured date/time choices, duration (5–480 minutes), type,
optional location, and optional reason. It converts wall-clock inputs to exact UTC
instants before `POST /appointments/propose`. Invalid dates, past/duplicate times,
DST gaps, and repeated DST times are rejected before submission. A repeated hour
currently requires choosing another wall-clock time; an offset-choice control is
not part of this slice. Backend and database validation remain authoritative.

The page shows only appointments matching the selected patient and the selected
clinician care-team assignment. History consolidates offer groups, shows each slot
status and patient note as written, and reads updated patient responses on Refresh
appointments. Offer new times appears for declines and alternative requests; it
prefills reason/location/duration/type but starts with empty time choices. Submitting
creates a new group, preserving the old response and audit history. No existing offer
is rewritten, and no new database migration is needed.

While sending, the form, patient selector, and refresh controls are disabled. Failed
submission preserves the draft/history and asks the clinician to check persisted
appointments before retrying an uncertain save. Refresh failure preserves loaded
history but blocks new writes until a successful retry. Patient/session changes
clear the corresponding draft/profile/history and ignore late responses. There is
no automatic retry or polling. Cross-offer booking conflicts and expiry remain
Slice 5; calendar export remains Slice 6. Clinician cancellation and completion/
no-show controls are not delivered by this screen.

### Steps to see the changes

1. The implementation runs from `.worktrees/clinician-scheduling`, branch
   `feature/clinician-appointment-offers`, based on current main at `c2567cd` with
   scheduling Slices 1–3 carried forward. The original checkout is preserved.
2. Open `http://localhost:3001/login`. Verify the actual clinic code, then sign in
   as synthetic clinician Elena Park. The canonical fixture uses `CA-CLINIC-001`;
   its deployed value must match the actual configured clinic.
3. Choose **Appointments** in the sidebar and select **Maya Patel**. No manual
   care-team/clinician/patient UUID entry is needed. Confirm the displayed timezone.
4. For America/Los_Angeles, offer **October 5, 2026 at 09:00** and **October 6, 2026
   at 14:00**, 30 minutes, Telehealth, reason `Synthetic Slice 4 offer test`.
   Expected instants: `2026-10-05T16:00:00Z`, `2026-10-06T21:00:00Z`.
   Use other future dates if repeating this after those dates have passed.
5. Send the offer. Expect a success notice and one history card with both options.
6. In a separate patient-portal tab/window at `http://localhost:3000`, sign in as
   Maya (`maya.patel@accounts.mediagent.live`) using her configured synthetic password.
   Open/refresh **Visits**, choose one time, then refresh to confirm persistence.
7. Return to Elena's **Appointments** page and choose **Refresh appointments**.
   The selected slot is Confirmed and its sibling Withdrawn.
8. Create fresh offers to exercise **Decline these times** and **Request different
   times** with a note as Maya. Refresh as Elena and confirm the matching status and
   exact note. Choose **Offer new times**, select new future choices, and send.
   Confirm the previous note/history remains alongside the new offer.
9. Cancel a confirmed appointment as Maya, then refresh as Elena to verify Cancelled
   and the note. Switch Maya's profile to Español (México) and verify the existing
   translated patient flow still works.

Live testing requires recorded appointment migrations 038–041 and an active
assignment. The user-supplied ledger includes those filenames, but their checksums
and schema contents have not been independently checked. This slice applied no
remote migrations or seed/reset operation. The 46-file integrated inventory matches
the supplied filename set; it does not establish production readiness.

### Verification — 2026-09-28

Both portals pass lint, typecheck, and webpack production builds. Patient tests:
132 pass. Clinician tests: 119 pass with
`NODE_OPTIONS=--no-experimental-webstorage npm run test`; ordinary tests initially
hit two existing storage failures under Node 26.8.2. All 32 focused scheduling and
sidebar tests pass with `TZ=Asia/Tokyo`, covering saved-zone conversion independent
of the machine zone, winter/summer/midnight, DST gaps/repeated hours, automatic
care-team selection, group status/note refresh, re-proposal preserving history,
validation, pending controls, failure/retry, and session/patient isolation.

Backend Ruff check/format and mypy pass. All 1,416 backend tests pass with 83.47%
coverage, using synthetic CI configuration and a disposable local PostgreSQL 18.6
cluster (eight transaction tests included). Missing isolated-worktree test settings
and sandbox-blocked database initialization were resolved as environment issues.
All 46 migrations parse. Local route/health smoke checks return 200. Authenticated
cross-portal manual acceptance and peer review remain pending.

### Auth hydration follow-up — 2026-09-28

The clinician auth guard previously selected dashboard content immediately when
the browser had a restored session, while the server rendered the loading skeleton.
It now uses a hydration snapshot so the server and first client render show the same
skeleton. After hydration, it shows the authenticated dashboard or redirects to
login with the original return path. It continues waiting while session restoration
is in progress. This shared guard covers Appointments and other dashboard routes.

A real React server-render/hydrate regression reproduced the reported mismatch
before the fix. Authenticated and logged-out hydration now both pass without
recoverable errors; session-loading and login return-path tests also pass.
Clinician lint, typecheck, and webpack production build pass. The full clinician
suite passes 122 tests in 22 files using
`NODE_OPTIONS=--no-experimental-webstorage npm run test` for the existing Node 26
storage issue. The local clinician server was restarted with the fix, and
`/appointments` returns HTTP 200.

To verify in the browser, sign in at `http://localhost:3001`, open **Appointments**,
and hard refresh with Cmd+Shift+R. Expect a brief loading skeleton followed by the
page without a hydration error. Sign out and revisit `/appointments`; expect a
login redirect, then a return to Appointments after successful sign-in. Authenticated
browser testing of this fix was confirmed by the requester on 2026-09-28. Full
cross-portal offer acceptance remains separate; no database changes are involved.

## 14. Slice 5 — booking conflicts and proposal expiry

Pending options do not reserve time. A PostgreSQL exclusion constraint prevents
overlapping confirmed/scheduled intervals for the same patient, including across
different care teams, standalone bookings, generic edits, and direct database writes.
Intervals are `[start, end)`, so back-to-back appointments are allowed. UTC elapsed
minute arithmetic makes this independent of database/browser timezone and DST.
The constraint remains authoritative under concurrency. Patient responses first
lock the patient, then the offer and rows; competing responses produce one booking
and a safe conflict result. Exclusion/deadlock failures roll back the entire response,
including sibling changes and action audits. Other transaction failures are sanitized.
This does not implement clinician-wide capacity or external-calendar availability.

Every proposed slot has `proposal_expires_at = min(created_at + 168 hours, scheduled_at)`.
Existing proposed rows receive the same creation-based deadline during migration;
editing a proposal cannot extend it, and expired rows cannot be reopened. A fresh
offer creates fresh rows. An elapsed option expires individually; remaining future
choices stay usable until the seven-day deadline. Responses check the database wall
clock after obtaining locks, so a request started earlier cannot confirm a late slot.
Standalone patient responses now use the same atomic RPC and transition audit.

Authorized list reads expire due proposals belonging to the patient or the
clinician's actively assigned patients. Responses expire due rows of the affected
offer before returning an expired error. Each expiration appends one `expire` event
with a null actor (system transition); legacy events may have a null group. Expiry
and its audit commit together, and repeat reads create no duplicate transition.
No background Job is added: persistence occurs on authorized reads/responses. Visits
refreshes at the earliest response deadline and on browser focus, with bounded retry
after an elapsed deadline and no automatic retry after a failed read.

API business failures retain HTTP 422 with documented codes:
`APPOINTMENT_CONFLICT`, `APPOINTMENT_EXPIRED`, `APPOINTMENT_UNAVAILABLE`, and
`APPOINTMENT_PAST`. Client copy uses those codes; raw server text is not displayed.
English and Mexican Spanish include deadlines, expired history, and specific errors.
Expired cards have no response actions. Action failure keeps the list and manual
refresh available. A successful response reads authoritative sibling states; if that
read fails, the notice explicitly says the response was saved. Session changes clear
visits and ignore old loads/responses. Clinician history shows deadlines and permits
**Offer new times** after all choices expire, preserving old notes and rows.

### Rollout and steps to see the changes

1. Use `.worktrees/clinician-scheduling`; the original checkout is preserved.
   Review the read-only `backend/scripts/appointment-booking-preflight.sql` in the
   synthetic development database. It must return no overlap pairs before 043 can
   succeed. Existing overlapping bookings require a separately reviewed resolution;
   this slice never cancels or deletes them automatically.
2. Apply `042_appointment_expired_status.sql`, commit it, then apply
   `043_appointment_booking_guards.sql` through the existing filename/checksum
   migration ledger. Apply schema before activating the new backend. The extension
   `btree_gist` is required. See the Supabase setup guide for the authorized rollout
   process. These files were tested only on disposable local PostgreSQL, not applied
   to remote Supabase. The original 038–041 migration bytes are unchanged.
3. Restart the backend using this checkout's `backend/src` and the existing local
   backend configuration. Both portal servers now serve this checkout on ports
   3000/3001; the port-8000 backend still serves the previous checkout until the
   migrations are applied and the new backend is deliberately activated.
4. As Elena, offer Maya two future times, then as Maya accept the first. For the
   proposed example, October 5, 2026 09:00 in America/Los_Angeles is
   `2026-10-05T16:00:00Z`; a 30-minute booking ends at 09:30.
5. As Elena, send a separate offer including October 5 at 09:15 and another free
   time. As Maya choose 09:15: expect a conflict message and the existing booking
   and unchosen offer to remain visible. Choose the free time instead to succeed.
   A new visit starting exactly at 09:30 is allowed. Repeat in Español (México).
6. For a quick expiry check, offer a slot a few minutes ahead plus one on another
   day. Leave Visits open through the near slot's start, or refresh after it: expect
   **Expired/Vencida** for that option and the future option still selectable. A late
   acceptance is rejected by the server. The full offer expires seven days after
   creation; confirmed visits do not expire. Automated tests cover the seven-day
   boundary without altering remote timestamps.
7. Refresh clinician Appointments to see the persisted states. After all options
   expire, **Offer new times** creates fresh history and keeps the original notes.

Authenticated live acceptance, migration/schema verification, and peer review remain
pending. Calendar export is Slice 6; clinician cancellation/completion/no-show controls
and a clinician availability engine remain outside this slice.

### Verification — 2026-09-28

Final backend command (synthetic CI settings and local PostgreSQL binaries on PATH):
`PYTHONPATH=src python -m pytest tests/ --cov=app --cov-report=term -q --tb=short`:
1,453 pass, 83.55% coverage. All 28 real transaction tests run on a disposable
PostgreSQL 18.6 cluster. They exercise competing offers (five runs), direct booking
versus acceptance (three runs), partial overlap/adjacency, duration/time edits,
different care teams/patients, legacy atomic responses, wall-clock expiry after
transaction start, partial expiry, creation-based backfill, scoped/idempotent reads,
append-only audit and rollback, direct write/grant denials, and the read-only preflight.
A repeated race caught an intermittent exclusion-check deadlock; patient-first locking
and safe nested rollback handling fixed it before final verification.

Ruff lint and format pass; mypy passes for 198 source files. All 48 migrations parse.
Both portals pass lint, typecheck, and webpack builds. Patient tests: 165 pass in 32
files; clinician tests: 125 pass in 23 files with
`NODE_OPTIONS=--no-experimental-webstorage npm run test`. Existing Node 26 Web Storage
and tool deprecation warnings remain environment concerns. A concurrent patient
build/typecheck encountered replaced generated type files; rerunning typecheck after
the completed build passes. Both development route smoke checks return HTTP 200.

No remote schema application, synthetic seed/reset, deployment, commit, or push was
performed. The new backend is not active against remote Supabase. Live acceptance
requires the migration-first rollout above; automated evidence does not replace it.

### Migration-only rollout — 2026-10-03

The requester authorized migration execution only. Read-only preflight returned
zero overlap pairs. The existing 50 ledger entries all matched their source
checksums; four newer care-plan files were verified against fetched `origin/main`
`019598b` without merging or changing the scheduling checkout.

The repository migration script applied `042_appointment_expired_status.sql` and
`043_appointment_booking_guards.sql` in separate committed transactions and recorded
both checksums. The deadline backfill updated zero rows. Post-application inventory
has 52 applied entries, zero checksum mismatches and no pending scheduling migrations.
`backend/scripts/verify-appointment-slice5.sql` executed read-only against Supabase
and returned `Slice 5 schema and function permissions verified`.

This supersedes earlier statements that remote application/schema verification
were pending. Backend and portal activation, authenticated live acceptance, and
peer review remain pending. No server restart, seed/reset, deployment, or Slice 6
implementation occurred in this migration-only operation. The separate local
PostgreSQL fixture failure still prevents claiming the new verifier regression
tests have passed.

### Ordered rollout follow-up — 2026-10-02 (historical)

Slice 5 migration/live acceptance precedes Slice 6 calendar export. The migration
connection is awaiting local configuration by the requester; no remote query or
migration has run. All three development servers are currently stopped, superseding
the running-server snapshot above. Restore them after verifying the schema.

After the ledger/checksum and overlap preflight checks and authorized migration
application, run `backend/scripts/verify-appointment-slice5.sql` with
`psql -v ON_ERROR_STOP=1`. This read-only script checks the expiry enum/column,
validated overlap constraint, enabled booking/expiry/immutable-audit triggers,
RLS, service-only RPC grants and invoker security, and proposal deadline bounds.
It must report `Slice 5 schema and function permissions verified`; live acceptance
remains necessary.

Three regression tests check success and rejection of browser RPC grants or a
disabled expiry audit trigger. Ruff lint/format and SQL parsing pass. The October 2
run was blocked at fixture startup by missing temporary PostgreSQL support files.
After repairing the disposable installation, all **31 PostgreSQL transaction tests
passed on October 5**, including these three verifier regressions.

## 15. Slice 6 — one-time calendar export

Confirmed/scheduled visits in patient Visits and individual booked rows in clinician
Appointments offer **Add to calendar**. Patient controls, errors, event title and
notice support `en-US`/`es-MX`. Existing appointment response actions remain intact.
Downloads show a one-time-copy notice: external calendar copies do not automatically
receive later changes or cancellation, and their display timezone follows the
calendar application's settings.

Each click uses an authenticated, uncached
`GET /api/v1/appointments/{id}/calendar?locale=en-US|es-MX`. The server loads the
current appointment, checks the owning patient or active clinician assignment, then
requires `confirmed` or `scheduled`. It returns JSON `{ filename, content }` with
`Cache-Control: private, no-store`; the portal downloads a `text/calendar` Blob.
There are no credentials in the download URL, public file links, external calendar
requests, calendar invitations, schema changes or appointment mutations. Revoked
assignment or a newly cancelled/expired visit is rejected on a subsequent request.
The export is a snapshot at read time, not a guarantee against later changes.

The serializer follows [RFC 5545](https://www.rfc-editor.org/rfc/rfc5545): UTC
`DTSTART`/`DTEND` preserve the instant and elapsed duration across DST and midnight;
the UID is stable for an appointment across languages and repeated downloads.
Calendar clients decide how repeated imports are handled. Location is preserved
with TEXT escaping, CRLF line endings and 75-octet UTF-8-safe line folding. A generic
localized title and no-sync notice are included; clinical reasons, patient notes,
clinician notes and patient identifiers are omitted. Failed requests show localized
inline errors without raw server detail; retries remain available. Pending requests
cannot trigger duplicate downloads and are ignored after unmount/session changes.

### Verification — 2026-10-03

- Backend appointment suite (calendar serializer/service/route and existing
  proposal/response regression tests): **86 passed**. Ruff check/format passed on
  six changed Python/test files; `mypy src/ --ignore-missing-imports` passed for
  **199 source files**. Tests cover own/other patient, active/inactive clinician
  assignment, anonymous access, fresh status after an earlier successful export,
  invalid input, both locales, winter/summer LA offsets, date rollover, elapsed DST
  duration, stable identity, control/newline injection and multibyte folding.
- Patient: `npm run lint`, `npm run typecheck`, `npm run test` (**174 tests, 34 files**),
  `npm run build -- --webpack` all passed. Clinician: lint, typecheck, webpack build,
  and `NODE_OPTIONS=--no-experimental-webstorage npm run test`
  (**132 tests, 24 files**) passed. UI tests cover booked-only visibility, bilingual
  errors/retry, no download after session change/unmount, duplicate-click prevention,
  Blob/link cleanup and preservation of existing visit actions.
- Live normal synthetic logins against the updated local backend and migrated
  Supabase: Maya and Elena exported both locales (200); Hannah was denied Maya's
  visit (403); anonymous access denied (401); cancelled/expired/withdrawn visits
  rejected (422). No direct database mutation was used for this acceptance.
- Chromium login/click/download acceptance passed in patient English and Spanish
  and clinician Appointments. `Asia/Tokyo` browser timezone still showed Maya's saved
  `America/Los_Angeles` 09:00 appointment. Downloaded bytes have the exact expected
  UTC start/end below. Screenshots inspected; no hydration console errors. Original
  patient language restored after verification. External calendar import remains a
  manual step; download checks do not establish compatibility with every calendar app.
- Slice 5 live API prerequisite passed first: overlap rejection without changing
  the booked visit/pending offer, acceptance of free and adjacent slots, cancellation,
  expiry at slot start, late acceptance rejection, acceptance of a future sibling,
  and persisted clinician history. Test offers were created through the proposal API;
  one confirmed synthetic visit was retained for the calendar walkthrough.

Dependency/environment evidence is separate from feature checks: both portal
`npm audit --omit=dev --audit-level=high` runs report 3 findings (critical Next.js,
high brace-expansion, moderate fast-uri). The Next.js
[maintainer advisory](https://github.com/vercel/next.js/security/advisories/GHSA-vcvr-r3jv-pc5j)
concerns attacker-controlled SVG input to Node `next/og` ImageResponse; no such source
usage was found in these portals, but dependency remediation remains open. No dependency
or lockfile change was made. Existing Node/Vite/Sentry/workspace warnings remain.
The prior disposable PostgreSQL fixture failure is unchanged; this slice adds no
migration and does not claim a fresh transaction-suite run. No deployment/merge occurred.

### Integrated PR verification — 2026-10-05

The scheduling branch integrates main through `4d9a469`, preserving the existing
hydration implementation and newer care-plan, ADR and clinician messaging work.
Full backend tests with the merged lock in isolated Python 3.12 and disposable
PostgreSQL 18.6 passed **1,733 tests**, with **85.72% coverage**. All 31 appointment
transaction tests executed; 20 unrelated opt-in care-plan PostgreSQL tests skipped.
Backend Ruff/format, mypy, migration validation (53 files) and production-placeholder
checks pass. Patient **200 tests / 38 files** and clinician **180 tests / 30 files**
pass; both portals pass lint, typecheck and webpack production builds. Local Node 26
test commands use `NODE_OPTIONS=--no-experimental-webstorage`.

The repaired temporary PostgreSQL installation resolves the historical fixture
failure above. Redacted Gitleaks branch-range scanning and whitespace checks pass.
The October 5 production dependency audits report four existing findings per portal:
critical Next.js, high brace-expansion/source-map-js and moderate fast-uri. Dependency
remediation remains separate; this branch changes no portal dependency lock. No additional
remote migration, seed/reset, deployment or PR merge occurred during preparation.
Live UI/API evidence remains the October 3 acceptance described above; importing the
download into an external calendar application remains a reviewer step.

PR #133's first CI run exposed two inherited backend advisories. Security floors
and both generated locks now require `multidict` 6.9.1 and `langgraph-sdk` 0.4.4;
all other locked versions remain unchanged. Locks reproduce with CI's uv 0.9.24,
Python 3.12 dependency compatibility passes, and pip-audit 2.10.1 reports no known
vulnerabilities. The full backend suite rerun with these packages retains the same
1,733 passes, 20 opt-in skips and 85.72% coverage above. Portal dependency findings
remain open; no CI security gate was weakened.

### Steps to see the changes

1. Open `http://127.0.0.1:3000/visits` and sign in as synthetic Maya Patel.
2. Find **Synthetic scheduling acceptance: calendar demonstration**, October 6,
   2026, **09:00–09:30 America/Los_Angeles**, at **Synthetic clinic, Suite 2**.
   Appointment `0fa4a1f9-0d9f-4e4d-8f07-7afac18f69fe` is confirmed and intentionally
   retained. Its exported UTC start/end are `20261006T160000Z` / `20261006T163000Z`.
3. Click **Add to calendar**, open/import the downloaded `.ics`, and check time,
   30-minute duration and location. Configure the calendar to Los Angeles to compare
   the same wall time; another calendar timezone represents the same UTC instant.
4. In **Profile → Edit**, save **Español (México)**; return to Visits and click
   **Agregar al calendario**. The downloaded title is **Cita de MediAgent**.
5. Open `http://127.0.0.1:3001/appointments`, sign in as Elena Park with clinic code
   `CA-CLINIC-001`, select Maya Patel, and download the same confirmed history row.
6. Proposed, withdrawn, expired, cancelled and completed visits have no export
   control. If a visit changes after the page loads, another download rechecks its
   status and fails safely. Existing external calendar copies are unchanged.

Remaining scheduling work: clinician cancellation/completion/no-show controls,
clinician-wide availability/capacity rules and notification delivery are separate
future scopes. Calendar export does not complete the full SCH-001 lifecycle.
