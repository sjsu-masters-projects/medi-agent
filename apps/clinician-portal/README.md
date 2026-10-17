# Clinician Portal

Next.js app for clinician and clinic-admin workflows in MediAgent.

## Local Development

From `apps/clinician-portal`, install dependencies and run the portal on port 3001
(the patient portal uses the default 3000):

```bash
npm ci
npm run dev -- --port 3001
```

Default local URLs:

- portal: `http://127.0.0.1:3001`
- backend API: `http://127.0.0.1:8000`

Lint, typecheck and tests:

```bash
npm run lint
npm run typecheck
npm run test
```

## Current Auth Workflow

### Clinic Admin Bootstrap

- First clinic admin signs up at `/signup/admin`
- That flow creates the clinic and provisions the initial clinic code
- Clinic admins land in the clinician dashboard after successful auth

### Clinician Login (sign in once)

1. `/login` opens on **Sign in**: email and password through `POST /api/v1/auth/login`, with no
   clinic code. The account must have an active clinic membership (`NO_ACTIVE_CLINIC` otherwise).
2. If MFA is required, the user completes TOTP verification before session hydration.
3. The clinician lands where they did before: the return path or `/dashboard`. There is no
   "Choose a clinic" step, no header switcher and no global active clinic. Lists stay
   clinician-wide through the care-team link.
4. After sign-in the portal reads `GET /api/v1/clinicians/me/clinics` only to decide what the
   sidebar shows: the clinic name when there is exactly one clinic, nothing otherwise.

The clinic code is the **secondary path**, **Join a clinic** on `/login`:

- verify the code (`POST /api/v1/clinics/resolve-code`), then choose
  - **I already have an account**: sign in (and MFA), then `POST /api/v1/clinicians/me/clinics`
    adds the clinic with a Provider or Nurse / MA role. The clinic is added only after the
    second factor. A membership ended by that clinic's admin is refused (`MEMBERSHIP_INACTIVE`:
    ask the admin to invite you again). If adding fails the clinician is signed in and can
    continue to the dashboard.
  - **Join this clinic (Provider / Nurse)**: create an account at `/signup` (an address that
    already has an account is refused with `ACCOUNT_EXISTS`: sign in to add the clinic).
  - **Create a clinic workspace**: `/signup/admin`.
- An addressed email invitation adds a clinic from `/signup#invitation=...`. An account with
  MFA and an active clinic must sign in first (`SIGN_IN_TO_ACCEPT`).

### Clinic-scoped actions

Staff, role changes and removals, email invitations, patient invite codes (and their history)
and the clinic code shown in Settings belong to one clinic. The portal sends `clinic_id`
automatically for a clinician with one clinic. With several, the server answers
`CLINIC_REQUIRED` and Settings shows a small **Clinic for this page** picker (component
`src/components/features/clinic-picker.tsx`); the choice applies only to those sections. Admin
controls (invitations, staff role changes and removal, clinic name) follow the role held at the
chosen clinic, not a profile-wide role. Error copy for
`CLINIC_REQUIRED`, `ACCOUNT_EXISTS`, `MEMBERSHIP_INACTIVE`, `NO_ACTIVE_CLINIC`,
`SIGN_IN_TO_ACCEPT` and the clinic-code errors lives in `src/services/clinics.ts`.

### Clinic chips and the Clinic filter (CLN-003 slice C)

Patient lists (Patient roster, Risk Radar, Patient Upload Review Queue, ADR Reviews, MedWatch,
Messages, Appointments, Alerts) and the patient header show **which clinic a patient is linked at**,
but only for a clinician with two or more clinics. A single-clinic clinician sees no chip, no
filter and no new request parameter.

- **Chip:** `ClinicChip` in `src/components/features/clinic-chip.tsx`: a small neutral pill (11 px,
  medium weight, `bg-surface-2 text-ink-2 border-line`) with the clinic name, truncated with a
  `title` tooltip. The same tone for every clinic; the meaning is the text. It follows the patient
  name on wide rows and sits on a second line at 390 px. The patient header says "Linked at
  &lt;clinic&gt;" (`LinkedAt`).
- **Filter:** `ClinicFilterField`, a labelled **Clinic** select (All clinics first, then each active
  clinic) on the right of the existing toolbar, never a tab row. State is the URL query parameter
  `clinic` (default All clinics), so it survives reload and back navigation. Hook:
  `src/hooks/use-clinic-filter.ts` (`useClinicFilter`; `useResolvedClinicFilter` for the work lists
  that keep their own URL state). The portal sends `clinic_id` to the list endpoint only after a
  clinic is picked; the server answers an empty list for a clinic the clinician does not belong to.
- **Empty filtered list:** "No patients at &lt;clinic&gt; match" with a **Show all clinics** text button.
- Messages filter the conversation list on the server; Alerts filter the loaded items by
  `clinic_id` (the notification cache is shared with the bell, so it is not refetched per clinic).

### Your clinics, default clinic and leaving (CLN-003 slice D)

Settings -> General Profile has a **Your clinics** card
(`src/components/features/your-clinics-card.tsx`): one row per clinic with the name, a role chip, a
**Default** badge, and, for admins, the clinic code with the Copy button. Row actions are two text
buttons: **Make default** (changes only which clinic is preselected; nothing ends) and **Leave**.
Leave opens a confirm dialog that says the clinician's patient links and unused invite codes at
that clinic will end (nothing is deleted); the confirm button is destructive. Leave is disabled with
a reason for the last clinic ("This is your only clinic.") and for the only admin of a clinic
("You're the only admin here."). Clinic name editing (an Edit name button on the admin's row) and the staff role-change and
removal actions show only to an admin at the picked clinic.

### Clinician MFA

- MFA setup is managed from `/settings/mfa`
- Backend routes:
  - `POST /api/v1/auth/mfa/enroll`
  - `POST /api/v1/auth/mfa/verify`
  - `POST /api/v1/auth/mfa/unenroll`
  - `GET /api/v1/auth/mfa/factors`
- Session tokens are refreshed after successful MFA changes so protected routes continue to work with the updated auth state

## Invite-Code Behavior

Invite codes belong to the clinic that issued them (the patient's care-team link takes that
clinic). Invite history is intentionally role-sensitive, per clinic:

- clinic admins can see that clinic's invite history, and who generated each code
- non-admin clinicians only see invite codes they created at that clinic
- an admin at one clinic sees nothing of another clinic's codes
- revoke remains owner-scoped, so admins do not revoke peer-issued codes from the current UI

## Relevant Files

- login flow: `src/app/(auth)/login/page.tsx`
- admin bootstrap: `src/app/(auth)/signup/admin/page.tsx`
- dashboard review queue: `src/app/(dashboard)/review-queue/page.tsx`
- ADR review queue: `src/app/(dashboard)/adr-reviews/page.tsx`; case page: `src/app/(dashboard)/adr-reviews/[assessmentId]/page.tsx`
- MedWatch reports list: `src/app/(dashboard)/medwatch/page.tsx`; report workspace: `src/app/(dashboard)/medwatch/[draftId]/page.tsx`
- shared list pieces (tabs, search, sort, pagination, URL state): `src/components/features/work-list.tsx`
- patient deep dive: `src/app/(dashboard)/patients/[id]/page.tsx`
- patient deep dive documents panel: `src/components/features/patient-documents-panel.tsx`
- settings / invite history: `src/app/(dashboard)/settings/page.tsx`
- MFA setup: `src/app/(dashboard)/settings/mfa/page.tsx`
- clinician API client: `src/services/clinicians.ts`
- stored clinic context (sidebar display and the join path only): `src/services/clinic-context.ts`
- clinic memberships, `clinic_id` helper and error copy: `src/services/clinics.ts`
- clinic picker for clinic-scoped actions: `src/components/features/clinic-picker.tsx`

## Document review workflow

- Patient-uploaded documents enter a shared clinician review queue.
- Review actions are surfaced in both the dedicated review queue and the patient deep dive documents tab.
- The deep-dive documents experience is intentionally factored into `PatientDocumentsPanel` so document review state, modal flows, and refresh behavior stay isolated from the rest of the deep-dive page.

## Routes: ADR Reviews and MedWatch (UX-005)

| Route | Purpose |
| --- | --- |
| `/adr-reviews` | Compact work queue, one row per case. Tabs: Awaiting review, Information requested, Reviewed, Dismissed (with counts). Search by patient, medicine or reaction; sort by score or age; 10 rows per page. Tab, search, sort and page live in the URL query, so Back from a case restores them. |
| `/adr-reviews/[assessmentId]` | Case page: summary, evidence with provenance labels, collapsed scoring details, missing information, and a side action panel (stacked under the evidence below 1024 px). Mark reviewed is the one primary action; Prepare MedWatch draft opens the report; a reviewed case with a report links to it. |
| `/patients/[id]?tab=adr` | The patient's ADR cases, current and past, linking to the case page. |
| `/medwatch` | Reports table. Tabs: Drafts, Approved, Submitted, Discarded. `/medwatch?assessment=<id>` (an old link) redirects to `/adr-reviews/<id>`. |
| `/medwatch/[draftId]` | Report stepper: Complete (gate issues first, link to each field; Form 3500 sections collapsed) → Preview (the watermarked PDF inline) → Approve (attestation dialog) → Download and record submission. |

- The preview is `GET /api/v1/clinicians/me/medwatch-drafts/{id}/preview.pdf` fetched with the bearer token and shown from a blob URL that is revoked on leaving the step. It is watermarked "DRAFT – not for submission", is not an export, and records no audit event. Continuing from Complete saves pending edits first so the PDF matches the screen. The audited, unwatermarked download stays on the Download step after approval.
- Layouts: below 768 px the tables become stacked rows and the stepper reads "Step N of 4"; from 768 px a grid table and a numbered stepper. Neither page scrolls horizontally at 390 px or 1280 px.

## ADR Review Workflow

- The cases page and report page replace the single `/medwatch` page: where this section says "queue" or "editor", read the routes above.

- `GET /api/v1/clinicians/me/adr-assessments` returns draft assessments only for patients assigned to the authenticated clinician.
- `POST /api/v1/clinicians/me/adr-assessments/{assessment_id}/review` atomically marks a draft reviewed, dismisses it with a reason, or records an information request. The database rechecks active assignment and writes an immutable audit event.
- The ADR review queue shows the deterministic Naranjo score, patient-grounded evidence, and missing inputs. It never exposes private model reasoning or presents the score as a clinician decision.
- Information requests expose only retrospective questions the patient can safely answer. They do not ask for placebo exposure, tests, a medication restart, or an unprescribed dose change.
- After the patient confirms every requested answer, the same draft is deterministically rescored. The queue shows the response evidence and request status while preserving clinician judgment as a separate decision.
- `POST /api/v1/clinicians/me/adr-assessments/{assessment_id}/medwatch-draft` requires an explicit clinician reportability rationale and creates a real evidence-attributed draft; the ADR decision and draft creation are atomic.
- The MedWatch editor is a structured Form FDA 3500 (09/2025, voluntary, not 3500A) draft: Sections A, B, D, F and G as grouped fields, selects and checkbox groups, B3 marked "Best estimate, confirm" until the clinician confirms it, up to 8 B6 test rows, an optional second suspect product and up to 10 F rows. Section C and E are left for the clinician to complete in the PDF. Unsupported items stay empty, source attribution is shown, saves use optimistic revision checks and changed field paths are audited. Name warnings from the server appear beside the B5, B6, B7 and F fields they belong to. The Naranjo score, causality and reportability rationale sit in a separate "MediAgent review (not part of Form 3500)" group.
- The draft lists the items missing for approval (the server's gate on the last saved revision). **Approve for export** opens a dialog that repeats the missing items, lists name warnings to acknowledge, asks for the non-serious attestation when no B2 outcome is checked, and shows the attestation text returned by the API. Approval sends `attestation_version`, `non_serious_attested` and `acknowledged_warnings` with the note.
- **Preview Form 3500** opens a read-only layout of Sections A to G in form order, with item numbers, "Not provided" for blank items, provenance chips (Record, AI-extracted, Patient-confirmed, Clinician edited), "Missing for approval" labels while the draft awaits approval, C and E as "Not completed by MediAgent", the separate MediAgent review panel and a warning once the vendored revision passes its expiry date. **Print preview** prints it on US Letter without navigation or actions, with "Not submitted to FDA by MediAgent" at the foot of every page.
- An approved draft offers **Download Form 3500 (PDF)**. A confirmation states "MediAgent did not submit this report. You submit it to FDA." before the official fillable PDF is saved under the server filename (`fda-3500-<id prefix>-not-submitted.pdf`). Each download is audited by the server and is never retried automatically. The JSON export stays as a secondary action. An approved earlier draft that cannot fill the PDF says to discard it and prepare a new draft.
- **Record FDA submission** records a submission the clinician made outside MediAgent: date (not in the future or before approval), method (MedWatch Online, fax, mail, or other with a description), an optional FDA reference and an attestation. Recording sends nothing to FDA. The draft then appears read-only under **Submitted** with "Submitted by <clinician> outside MediAgent on <date>", its amendment history and **Amend record** (date, method or reference, with a required reason; the original record is kept).
- **Discard draft** (for a draft, or an approved draft without a submission record) asks for a reason and returns the ADR assessment to review. Discarded drafts are listed read-only under **Discarded** with the reason and date.
- The Drafts, Approved, Submitted and Discarded tabs are bound to `?tab=` on `/medwatch`. The application has no FDA filing action and never presents an export or a download as a submission.

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
Save draft edits before approval. PAT-005 is accepted, including live version
supersession; see [the final acceptance](../../docs/pat-005-final-acceptance-2026-10-10.md).

Care Plan review makes each proposed medication an explicit create-or-update
decision against the assigned patient's active medication list. It shows one source action per
document and collapses redundant same-page excerpts in the review display without deleting
stored evidence. Under LOC-001, patient-facing wording is drafted and approved in en-US and
es-MX together: the review shows both side by side and one check per item records that the
clinician read both. The backend and publication transaction both reject missing locale
wording or medication decisions.

Overlap review groups flag identical source facts/instructions and same-name medications;
they do not establish clinical equivalence. “Keep this proposal; remove its overlaps” stages
explicit removals, and “Save review” persists them without changing the active approved plan.
Historical imported proposals can be excluded together; approved carried items are protected
from that bulk action. Removed rows and their evidence remain available under “Show removed
items.” Migration 044 adds the atomic overlap publication guard. Existing completed drafts
need review, not a generation retry; no automatic translation or medication choice is implied.

## Conversations and operational alerts

Interface controls remain English regardless of patient preference. Care-plan
review shows both languages side by side and preserves source and reviewed wording. Expand supporting evidence for filenames/page references;
extraction confidence is not medical certainty. Review blockers and explicit
publication decisions remain visible and enforced. Clinical text containing numbers
is not formatted as a date unless its field is explicitly a date field.
UI review evidence: `docs/portal-ui-ux-review-2026-10-10.md`.

**Messages** opens an assignment-scoped conversation inbox. Choose one linked
patient to start or resume a thread, or select an existing conversation to reply.
Sender and clinic names come from the server. An explicit send is the clinician's
approval; no AI transcript composer or automatic clinical send is provided.
The patient AI transcript links to Messages.

**Alerts** separates current authorized work from notification history. Documents,
care-plan drafts, appointments and follow-up/safety items open their exact existing
workflow; reading does not approve care. Only supported barrier/safety items offer
an audited acknowledgement, meaning seen for follow-up, not clinically resolved.
Messages holds private human conversations, followed by a collapsed **Earlier
messages** section: one-way messages and saved escalation notices from before
conversations, shown as history only (old urgency labels create no active work).

The shared notification cache polls `/api/v1/notification-centre` once a minute
while visible and refreshes on focus. Signed per-page cutoffs protect bulk reads
against new arrivals; "Mark all loaded read" skips items that are no longer
available and says how many; assignment revocation removes access. Counts
unavailable is not zero. See [NOT-001](../../.agent/specs/not-001-notification-centre.md) for
the contract.

The conversation API is `/api/v1/care-conversations`. Pages contain at most 50
messages; older pages use the server cursor. The visible inbox and selected thread
poll every 15 seconds. Inbox refresh updates recipients and removes revoked choices
while preserving selection and drafts; unread counts
come from the server, including after marking read through the last displayed ID. Unconfirmed sends
retain their text and UUID for manual retry, including thread/view switches;
pending text is locked until retry resolves. Drafts are in memory and clear on
reload or account change. Saved sends followed by failed refresh have distinct copy.
Definitive validation rejection preserves text for editing. Idempotency mismatch
requires explicit confirmation to prepare a new send key and warns that the previous
message may already exist. Preparation does not send it.

Conversations shipped in #139 (COM-001-B) with live bilingual persistence verified.

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
- QA account expectations are documented in [Auth-account QA](../../docs/demo-environment.md#auth-account-qa).


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

Response deadlines, Expired history, and re-proposal after all choices expire are
supported. Confirmed/scheduled patient visits cannot
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
