# QA handoff, October 2026

This guide is for teammates who take over deployed verification, bug fixing and
polish after code closure. The current verdict for every row stays in
[`.agent/TASKS.md`](../.agent/TASKS.md); this page tells you how to check it.

## 1. Purpose and scope

- Check each task row marked "Verify deployed" (plus VOI-001-M and AUTH-002) on
  the live portals and record the result.
- Use only the synthetic accounts and synthetic data described in
  [demo-environment.md](demo-environment.md) and
  [synthetic-data-catalog.md](synthetic-data-catalog.md). No real patients,
  clinicians or documents. Never put passwords, tokens or `.env` contents in
  issues, screenshots or evidence files; share credentials out of band only.
- Do not reset or seed environments, apply migrations, deploy or change
  external configuration. If a check needs that, stop and ask the requester.
- This is supervised decision support, not a clinical validation. A pass means
  the behavior matches the row's description, nothing more.

## 2. Before you start

1. **Confirm the portals are current.** Both portals and the backend deploy from `main`.
   Before portal-facing checks, confirm the latest commit's two Vercel statuses succeeded.
   If one shows "Deployment rate limited", the portal owner redeploys it after the limit
   resets ([Cloud infrastructure guide, section 4](../.agent/CLOUD_INFRASTRUCTURE_GUIDE.md)).
2. **Accounts** (fictional, in the `accounts.mediagent.live` namespace; ask the
   requester for credentials):

   | Need | Account |
   | --- | --- |
   | Patient | Rajeev (patient), Morgan, Evelyn |
   | Clinician with two clinics | Elena (Cedar Grove and Willow Terrace) |
   | Clinician with MFA | Rajeev (clinician) |
   | Clinic admin | Carmen |
   | Two care teams on one patient (sharing, per-team review) | Morgan, with Elena and Rajeev (clinician). Set this up with the steps below |

   If an account has drifted (missing assignment, wrong clinic), report it; do not
   recreate accounts.

   **Link a second clinician to Morgan.** Do this once, through the normal invite flow. It
   needs no reset, seed or configuration change. Skip it if Rajeev (clinician) already lists
   Morgan on Patient Roster.

   1. In the clinician portal, sign in as Rajeev (clinician). Go to **Settings > Patient
      Invites** and select **Generate New Invite Code**. Copy the code.
   2. In the patient portal, sign in as Morgan. Go to **Profile**, select **Add a care team
      member**, enter the code and select **Add to my care team**.
   3. Pass: Morgan sees "Added to your care team. They are now available." Rajeev's Patient
      Roster lists Morgan, and Elena still lists Morgan too.

   The link stays in place afterward, so Morgan is now a two-team patient. Use Evelyn, or
   another patient with one care team, for checks that a single-team patient's screens are
   unchanged.
3. **Locales:** run each patient-facing check in en-US and es-MX (switch in
   profile/settings). Restore English afterward.
4. **Viewports:** 390 px (phone) and 1280 px (desktop). Note any horizontal
   scroll, clipped text or unreachable control.
5. Keep the browser network tab open; you need the request id for bugs.

Pass rule for every check below: the expected result occurs in both locales and
both viewports with no error banner, console error you cannot explain, or
leaked English in es-MX.

## 3. Checks by area

### 3.1 Chat with Nora, and voice

**PAT-001-B (instant send)** and **PAT-006 (visit-aware Nora)**
1. Preconditions: patient with a confirmed visit tomorrow (Rajeev has Oct visits; otherwise check Visits first).
2. Open Chat, type a message, send.
3. Expected: your message appears immediately as pending, then settles. Open a second tab: it shows the same message. Reload mid-turn: the turn recovers and the reply appears once.
4. Ask "when is my next appointment?" (es-MX: "cuándo es mi próxima cita?").
5. Pass: the answer matches the Visits page date, time and time zone; it says "none" only when the list is empty. Allergies and today's activities, if asked, match the records.

**OPS-006a (latency), OPS-005, AI-003**
1. Preconditions: a chat idle for several minutes.
2. Send a message. Note the time from send to first reply text. Record `begin_to_dispatch_ms` (< about 1000) and dispatch-to-worker (< about 1 s) from the logs or evidence the requester provides.
3. Reply text should stream progressively; reload during the turn and confirm the saved reply replays once.
4. Pass: no hang, no duplicate reply, no empty draft; latencies within the figures above. A cold first message slower than the targets is a bug to log, not a pass.

**PAT-004 (focused-document chat)**
1. Preconditions: a patient document with extracted values (Rajeev's lipid report).
2. Open the document and ask about a value in es-MX.
3. Pass: values, units and page provenance are retained, an "unreviewed data" warning shows, the answer persists after reload, chat fits at 360/390/430 px. Attaching an invalid file shows the specific explanation.

**VOICE-001 and VOI-001-M (physical voice)** (reference: [VOICE-001](features/voice-mode.md))
1. Preconditions: real phone, synthetic patient account, microphone available.
2. Allow the microphone, dictate in en-US then es-MX. Check the transcript and corrections.
3. Listen to the reply. Interrupt it (barge-in), pause, cancel, drop and restore the connection.
4. Deny the microphone permission.
5. Pass: transcripts are correct enough to edit, replies are spoken sentence by sentence, interruption stops audio, reconnect recovers, and typing remains available after denial. A clinical report is never submitted by voice alone. Record device, browser, observed result and any issue.

### 3.2 Symptoms

**PAT-002-B (confirmed intake)**
1. Preconditions: synthetic patient with symptom intake enabled.
2. Ask about a mild, non-emergency symptom in chat.
3. Expected: an offer to start a report appears only because of the symptom (no always-visible start button). Accept; questions arrive as private chat bubbles; consent is explicit before anything is sent.
4. Also try an emergency phrase.
5. Pass: emergency wording shows urgent guidance and no routine intake offer; Spanish confirmation and wording are correct; 390 px layout has no overflow and controls are reachable by keyboard.

**PAT-002-C (timeline and review)**
1. Preconditions: a confirmed synthetic report that reached an active care-team link.
2. As the patient open "My symptoms" and the report detail.
3. As a clinician on that team open the report panel (answers, safety outcome, provenance, consent) and use "Mark reviewed".
4. Back as the patient, then as a clinician on another team.
5. Pass: history shows only the patient's confirmed reports in the saved time zone; status comes from recorded events; "Sent to your care team" appears only if the hand-off reached an active link; Mark reviewed is idempotent (a second click makes no second event); the patient gets a notification linking to the report; the other team sees the review. Reference: [Symptom intake](features/symptom-intake.md).

### 3.3 Care-team plans

**PLAN-002, CLN-003** (reference: [PLAN-002](features/care-plans-and-today.md))
1. Preconditions: Elena (two clinics) and a patient linked to two teams.
2. As each team, view and edit that team's plan; publish a change that duplicates or conflicts with the other team's plan.
3. Expected: the publish flow offers blockers (duplicate, stop, dose), keep both with a reason, ask the other team, or publish without. The patient's Today shows merged items with owner labels.
4. Check clinic roles, clinic codes, roster filters and invite clinic selection for Elena.
5. Pass: each team sees and edits only its plan; sensitive conditions respect patient control; Nora cites plan ownership; no screen exposes the other clinic's data to an unassigned clinician.

### 3.4 Handoff summaries

**CON-001** (reference: [CON-001](features/clinics-and-care-teams.md#handoff-summary))
1. Preconditions: synthetic patient with a timeline; author clinician and a second allowed clinician on the team.
2. As the author build a handoff summary, check sections are source-linked, approve it, then print and export FHIR.
3. Share the approved version with the second clinician. As that clinician, read it, print and export it, and confirm you get a notification.
4. Revoke the share as the author.
5. Pass: export is offered only for the approved version; the recipient view is read-only; after revocation the recipient can no longer open it; every approval/share/revoke action is audited; an unassigned clinician cannot reach it.

### 3.5 MED-002 (patient confirmation)

1. Preconditions: an imported candidate medication in the reconciliation review; a linked patient.
2. As the clinician choose "Ask the patient to confirm".
3. As the patient open Today and answer (Yes / No, I stopped / It changed / Not sure) in en-US and es-MX.
4. Back as the clinician, view the answer in the review panel and in export.
5. Pass: the answer appears as patient testimony with time and "not verified"; it never changes the approved medication list; repeating the answer is idempotent; an expired (14-day) or foreign request is refused; wording is correct in both languages. No notification-centre alert is expected yet. Reference: [Patient records](features/patient-records.md).

### 3.6 Notifications

**NOT-003, CLN-001, DV-022 to 024**
1. Preconditions: unread patient and clinician notifications.
2. Open one notification; reload; reopen; use a stale list from a second tab.
3. Pass: read counts decrease and stay after reload; clinician action items do not resolve by being read; stale-cursor recovery shows fresh data without error. The Alerts page shows external-record workload and exact candidate counts separately from unread counts. Review dialogs return focus to their opener, loading and failure states show no old counts, public references list English first.

### 3.7 Scheduling

**SCH-001-V, UX-006**
1. Preconditions: Rajeev with two upcoming visits and another patient (Morgan, Evelyn) across Cedar Grove and Willow Terrace.
2. Switch Today to week and All to Willow; check clinic filters, needs-action and patient history.
3. Create an appointment offer for a patient who is already booked that day at another clinic.
4. Pass: loading states show with no stale visits; the day's existing booking (for example 10:00 to 10:30 AM) is shown; the offer uses the patient's clinic and Pacific time zone; a cross-clinic conflict is refused; calendar export matches. No horizontal overflow at 390 or 1280 px.

### 3.8 Records and FHIR

**REC-001, CLN-002, INT-002, INT-003-V, UX-005** (reference: [patient records](features/patient-records.md))
1. Preconditions: synthetic documents and a clinician assigned to the patient.
2. Open source and lifecycle views for a document-derived item; open the clinician timeline.
3. Download the canonical FHIR collection and run a SMART sandbox launch.
4. Open the ADR record tab, then MedWatch Preview, Approve and Download at 390 px.
5. Pass: filenames, IDs and pages are retained; withdrawn items show their state; the timeline loads source-linked rows, shows freshness and respects role and private-thread isolation; the FHIR download is candidate-only on re-import and honors sensitive-condition gates; SMART reaches the sandbox patient login, not the provider picker; the MedWatch PDF renders in Chrome and mobile (it only looked blank in the in-app browser). Do not claim full-chart or conformance certification. Make no chart changes without specific approval.

**REC-001-UX, REC-001-RM, REC-001-MO (patient Records)** (reference: [record clarity](features/patient-records.md))
1. Preconditions: a patient with one own pending upload, one reviewed document and one document with an explanation.
2. Use Refresh on Records. Open a document and its explanation in en-US and es-MX, then close it with the sticky close control.
3. Upload a file and watch it process. Remove your own pending upload. Try to remove a reviewed document.
4. Pass: review labels match the recorded state and clinician labels are explicit; reopening an explanation makes no new model call; processing shows motion, then a neutral highlight and a screen-reader announcement; with reduced motion the status text stays; removal confirms with a notice; a refused removal keeps the source and offers the private care-team request instead.

**PV-001-D (Naranjo answer coverage)** (reference: [PV-001-D](features/adverse-events.md))
1. Preconditions: Elena with an open ADR case for Morgan.
2. As Elena, use Request information. As Morgan, answer all five retrospective questions in en-US and es-MX.
3. As Elena, record the five clinical questions with a basis and evidence. Save again with no change, then change one answer.
4. Pass: the score recalculates with unchanged weights and saving does not review the case; a recorded answer shows as answered with Change answer; an unchanged save adds nothing; a replaced answer moves under Earlier clinician answers.

### 3.9 Safety

**SAFE-002, SAFE-001-H, AI-006** (reference: [AI runtime](features/ai-runtime-and-workers.md), [safety release](features/safety.md))
1. Preconditions: synthetic patient chatting with Nora.
2. Send, in both languages: a medication-error statement (for example a double dose), a severe-symptom phrase, a low-mood message, a mild stable symptom, and a general wellness question.
3. Pass: the medication-error and severe cases give urgent, same-day wording and raise an urgent alert to the care team; low mood gets crisis-appropriate deterministic wording; mild and wellness prompts get bounded general guidance with no symptom-report confirmation; nothing contains private reasoning. SAFE-002 also needs the peer safety review by Ganesh; log wording you doubt. SAFE-001-H has no new UI; confirm only that clinician actions still work for a clinician with an active assignment and fail for one without.

### 3.10 Sessions and operations

**AUTH-002, OPS-008, LOC-003, LOC-002**
1. AUTH-002: sign in on two tabs; sign out in one and confirm the other follows without reload. Leave a session idle until the inactivity warning appears and record when (this is the only open piece). Confirm MFA remains enabled after reload.
2. LOC-003: as a clinician review a Spanish patient message with the English gloss, original preserved, model provenance and confirmed reply preview.
3. LOC-002: switch en-US to es-MX and back; wording loads with no flash of the wrong language and persists after reload.
4. OPS-008 is observed by the requester in Cloud Run (jobs run as `mediagent-jobs-runtime`); verify only that an uploaded document is still ingested.

### 3.11 Spanish wording

**LOC-002, LOC-003, wording review** (evidence: [spanish-interface-wording-2026-10-22.md](evidence/spanish-interface-wording-2026-10-22.md))
1. Walk every screen touched above in es-MX at 390 px.
2. Pass: no English strings remain except proper names and clinical terms with a gloss; wording is Mexican Spanish (tú/usted consistent), buttons fit, dates and times follow the saved time zone. File wording problems as bugs with the exact string and a proposed fix; do not edit approved wording without the review path recorded in the evidence file.

## 4. How to log a bug

1. File a GitHub issue in the repository. Propose the label `qa-handoff` plus an area label (for example `area:chat`, `area:safety`, `area:i18n`) and a severity label; ask a maintainer to create them if missing.
2. Required fields:
   - TASKS row id (for example PAT-002-C)
   - Account (name and role only, never the password)
   - Locale (en-US or es-MX)
   - Viewport (390 or 1280 px) and browser/device
   - Date and time with time zone
   - Request id from the browser network tab (response header) of the failing call
   - Steps, expected and actual result
   - Screenshot (no real data; crop out tokens and URLs containing tokens)
3. Severity guide:

   | Severity | Meaning |
   | --- | --- |
   | S1 | Safety wrong or missed, data shown to the wrong person, auth bypass, data loss. Stop and tell the requester now. |
   | S2 | A core flow in the row cannot be completed, or wrong clinical content is shown. |
   | S3 | Flow works with a visible defect: wrong locale string, layout break, slow, confusing error. |
   | S4 | Cosmetic or polish. |

## 5. Sign-off

1. Run the checks for a row and write the result in a dated evidence file or a new dated section in `docs/evidence/` (for example `docs/evidence/qa-<ROW-ID>-<date>.md`). Include account roles, locales, viewports, commands or steps, request ids, outcome, and issue links. No secrets or real data. Add the file to [docs/evidence/README.md](evidence/README.md).
2. If every check in the row passed in both locales and viewports, change that row's status in `.agent/TASKS.md` from "Verify deployed" to "Done", replace the "Remaining" text with the verified slice, and link the evidence file. If anything failed, leave the status and link the issue instead.
3. Done applies to the named slice only. Merged code, a green deployment and live acceptance are different evidence levels.
4. Run `node scripts/check-docs.mjs --all` (0 errors) and open a documentation pull request. The requester merges.
