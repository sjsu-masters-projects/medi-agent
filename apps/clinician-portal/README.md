# Clinician Portal

Next.js app for clinician and clinic-admin workflows in MediAgent.

## Local Development

Install dependencies from the repo root, then run the portal:

```bash
npm run dev
```

Default local URLs:

- portal: `http://127.0.0.1:3001`
- backend API: `http://127.0.0.1:8000`

Typecheck and tests:

```bash
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/vitest run
```

## Current Auth Workflow

### Clinic Admin Bootstrap

- First clinic admin signs up at `/signup/admin`
- That flow creates the clinic and provisions the initial clinic code
- Clinic admins land in the clinician dashboard after successful auth

### Clinician Login

1. User enters a clinic code on `/login`
2. Frontend verifies the clinic through `POST /api/v1/clinics/resolve-code`
3. Verified clinic context is stored locally and reused on refresh
4. User chooses login and submits email/password through `POST /api/v1/auth/login`
5. If MFA is required, the user completes TOTP verification before session hydration

### Clinician MFA

- MFA setup is managed from `/settings/mfa`
- Backend routes:
  - `POST /api/v1/auth/mfa/enroll`
  - `POST /api/v1/auth/mfa/verify`
  - `POST /api/v1/auth/mfa/unenroll`
  - `GET /api/v1/auth/mfa/factors`
- Session tokens are refreshed after successful MFA changes so protected routes continue to work with the updated auth state

## Invite-Code Behavior

Invite history is intentionally role-sensitive:

- clinic admins can see clinic-wide invite history
- admins also see who generated each code
- non-admin clinicians only see invite codes they created
- revoke remains owner-scoped, so admins do not revoke peer-issued codes from the current UI

## Relevant Files

- login flow: `src/app/(auth)/login/page.tsx`
- admin bootstrap: `src/app/(auth)/signup/admin/page.tsx`
- dashboard review queue: `src/app/(dashboard)/review-queue/page.tsx`
- ADR evidence queue: `src/app/(dashboard)/medwatch/page.tsx`
- patient deep dive: `src/app/(dashboard)/patients/[id]/page.tsx`
- patient deep dive documents panel: `src/components/features/patient-documents-panel.tsx`
- settings / invite history: `src/app/(dashboard)/settings/page.tsx`
- MFA setup: `src/app/(dashboard)/settings/mfa/page.tsx`
- clinician API client: `src/services/clinicians.ts`
- stored clinic context: `src/services/clinic-context.ts`

## Phase 6 Review Workflow

- Patient-uploaded documents enter a shared clinician review queue.
- Review actions are surfaced in both the dedicated review queue and the patient deep dive documents tab.
- The deep-dive documents experience is intentionally factored into `PatientDocumentsPanel` so document review state, modal flows, and refresh behavior stay isolated from the rest of the deep-dive page.

## ADR Review Workflow

- `GET /api/v1/clinicians/me/adr-assessments` returns draft assessments only for patients assigned to the authenticated clinician.
- `POST /api/v1/clinicians/me/adr-assessments/{assessment_id}/review` atomically marks a draft reviewed, dismisses it with a reason, or records an information request. The database rechecks active assignment and writes an immutable audit event.
- The ADR review queue shows the deterministic Naranjo score, patient-grounded evidence, and missing inputs. It never exposes private model reasoning or presents the score as a clinician decision.
- MedWatch records remain a separate lifecycle and are not counted or presented as generated until a real `medwatch_drafts` record exists.

## Care-plan revision review

The Care Plan tab loads the latest version and the currently approved version through an
assignment-scoped backend review endpoint. When a newer draft exists, the approved plan remains
active in Today. The tab lists the source documents/citations attached to proposed items and
labels an item as carried forward, edited, removed, or linked to new evidence by source-fact ID.
“New evidence” does not establish a new therapy or reconcile medications. The publication
summary lists plan instructions only. After resolving review requirements and saving the draft,
**Preview Today** requests a read-only current-record snapshot from
`GET /api/v1/care-plans/clinician/patients/{patient_id}/{plan_id}/today-preview`. It uses the
live Today renderer with the patient-local date, valid reminders, existing medications,
proposed projections and retained activity responses. New activity IDs are preview-only;
new/changed activities do not inherit reminder times or completion. Edits and saves clear the
preview. Refresh it if records or reminders change: it is not a transaction reservation or a
guarantee of later publication. Errors discard the snapshot, not display an empty success.
The backend must be deployed before the preview UI; no new migration is required.
Save draft edits before approval. Clinical review of medication matching
and locale wording, plus a live version-supersession proof, remain PAT-005 acceptance work.

Care Plan review makes each proposed medication an explicit create-or-update
decision against the assigned patient's active medication list. It shows one source action per
document and collapses redundant same-page excerpts in the review display without deleting
stored evidence. The clinician must edit patient-facing wording into the patient's preferred
language and attest to reviewing the final text; the checkbox is not a translation service.
The backend and publication transaction both reject missing locale or medication decisions.
Apply migration `042_care_plan_publication_review_guards.sql` before deploying this contract.

Overlap review groups flag identical source facts/instructions and same-name medications;
they do not establish clinical equivalence. “Keep this proposal; remove its overlaps” stages
explicit removals, and “Save review” persists them without changing the active approved plan.
Historical imported proposals can be excluded together; approved carried items are protected
from that bulk action. Removed rows and their evidence remain available under “Show removed
items.” Migration 044 adds the atomic overlap publication guard. Existing completed drafts
need review, not a generation retry; no automatic translation or medication choice is implied.

## Notes

Patient detail distinguishes 403 access denial and 404 missing records from transient
load errors: roster navigation replaces Retry for denied/missing records. Account/route
changes and refresh clear prior content; late responses cannot restore it. Both API
wrappers preserve HTTP status and share bounded recovery: GET/HEAD may retry once after
100–249 ms. HTTP errors and writes are never replayed. After an uncertain write, refresh
to confirm persisted state before manual retry.

The Adherence tab shows response-based completion, coverage, daily counts, current activities,
and the latest 20 patient-reported barriers (including historical versions). Its chart uses
UTC daily buckets from the reporting API; barrier timestamps use the patient's timezone.
Unrecorded days are gaps, not missed doses. Current activity counts are not the historical
scheduled-dose denominator, and patient-reported side effects are not clinician-reviewed ADRs.

- A browser extension such as Grammarly can inject attributes into the document body and trigger a dev-only hydration warning. That warning is not a portal auth bug.
- QA account expectations are documented in [docs/qa-auth-accounts.md](../../docs/qa-auth-accounts.md).


## Appointments workflow

Use **Appointments** in the sidebar to select an assigned patient and offer 2–4
future appointment times. The roster supplies the care-team ID automatically.
The patient profile supplies the explicitly labelled timezone for entry and display;
missing/invalid values use UTC, and profile failures require retry before entry.

History shows grouped choices, patient responses, and notes. **Refresh appointments**
loads persisted responses. **Offer new times** creates a fresh offer after a decline
or request for alternatives while preserving prior history. Time conversion rejects
DST gaps and repeated hours rather than guessing. Failed writes preserve the draft;
refresh to check whether an uncertain request saved before retrying.

Slice 4 needs appointment migrations 038–041. Slice 5 adds response deadlines,
Expired history, and re-proposal after all choices expire; it requires migrations
042 then 043 and the updated backend. Confirmed/scheduled patient visits cannot
overlap; pending offers reserve no time. Slice 6 adds **Add to calendar** to each
confirmed/scheduled history row, including the chosen row of an offer. Each download
rechecks active patient assignment and current appointment status. The one-time `.ics`
copy contains exact start/end and location; changes/cancellations do not sync.
Clinician cancellation/completion controls remain subsequent work. Full synthetic click-through steps and
verification evidence are in
[the scheduling design](../../.agent/specs/sch-001-appointment-scheduling.md#13-slice-4--clinician-appointments-screen).

On Node 26, if existing auth-session tests fail because localStorage is unavailable,
run `NODE_OPTIONS=--no-experimental-webstorage npm run test` so jsdom supplies browser
storage. This is a test-runtime setting, not a change to portal authentication.
