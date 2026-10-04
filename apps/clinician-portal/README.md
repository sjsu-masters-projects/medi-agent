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

## Notes

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
