# Deployed portal recheck — October 11–19, 2026

Synthetic Morgan Ellis (patient, `app.mediagent.live`) and Elena Park (clinician,
`clinician.mediagent.live`) only, on main `8b93b48` (#149) as deployed. The requester
signed in to both accounts; the checks below were run in a browser against the
production deployment. Later sections record checks after later merges (#151–#157)
and name their own accounts. This is prototype acceptance evidence, not a clinical,
compliance or production-readiness certification.

## Screens and widths

- Clinician at 1280 px: Risk Radar, Patient roster, Appointments, Review Queue, ADR
  Review Queue, Messages, Alerts and Clinic settings loaded without error messages or
  horizontal scrolling. At 390 px: Risk Radar, Alerts, Messages, Appointments and
  Morgan's patient detail (Care Plan tab) had no horizontal scrolling.
- Patient at 390 px and 1280 px: Today, Records, Visits, Notifications, Chat and
  Profile loaded without error messages or horizontal scrolling.

## Language (LOC-001, PAT-005-L)

- Clinician Care Plan tab: V4 approved and live in Today, each item shown in English
  (US) and Español (México) side by side.
- Patient Profile, preferred language switched to Español: the page `lang` became
  `es-MX` immediately. Today then showed Spanish screen text, actions and barrier
  controls, and the approved Spanish wording ("Metformina 500 mg", "Tome un vaso de
  agua…"). The next reminder time stayed 6:00 p.m., as in English. Notifications used
  Spanish (tú) copy. The language was switched back to English afterwards.

## Notifications (NOT-001, NOT-002)

- Clinician bell, sidebar Alerts badge and Alerts header agreed (2 unread; 11 need
  attention). Message notifications showed the clinic once. Messages showed the
  collapsed "Earlier messages (18)" history section.
- Acknowledging an appointment response recorded the audited acknowledgement note and
  lowered Needs attention from 11 to 10 and unread from 2 to 1.
- Patient "Mark all shown as read" (in Spanish) cleared 3 unread to 0 on the page and
  the bell, with no skipped-items note.
- Counts show "unavailable" while the browser tab is hidden: the centre polls only
  visible pages, by design. They loaded once the page was visible.

## Nora (NORA-001, NORA-002)

- With the app set to Spanish, "¿Para qué sirve la metformina que tomo?" was answered
  in Spanish from Morgan's record (Metformin 500 mg twice a day; the record gives no
  indication) with general reference information and the source "MedlinePlus:
  Metformina (consultado el 11 oct 2026)", deferring specifics to the care team.
- With the app still in Spanish, an English question about common side effects was
  answered in English, citing MedlinePlus and the DailyMed FDA label (published
  September 28, 2026), with care-team and 911 guidance. Past conversations, New
  conversation and the language label per message were present.
- Not verified here: spoken replies and hands-free voice (no microphone or audio
  output in this browser). Voice acceptance on a phone remains VOI-001.

## Not covered

- PAT-005-L duplicate fixture: none was available in Morgan's records during this
  earlier check. The later October 18 check used Rajeev's retained synthetic copy;
  see the [campaign verdict](#task-verdicts). No new upload was necessary.
- LOC-001 approval of a new bilingual draft on the deployed clinician portal: no draft
  was pending, and no clinical publication was performed.
- Scheduled jobs: covered by OPS-003 after its deployment.

## Follow-up checks after #151 (evening)

- Scheduled jobs: the requester resumed reminder dispatch and deleted the paused nightly
  ADR scan trigger. The 21:15 UTC reminder run logged `scheduled_job.finished` (INFO,
  success, first-run window, 3 schedules skipped for inactive targets, nothing due). A
  document ingestion run and a manual weekly-refresh execution also logged success; the
  refresh seeded 13 documented conditions and updated 10 subjects, next due October 17.
  MedlinePlus returned no topic for 13 of 29 condition lookups. Cause: Spanish was searched
  with the English name, only the first hit was checked, and qualifiers ("mild persistent",
  "of the knee") defeated the search. Every English topic has a Spanish page at
  `/spanish/<same slug>`, which the fix uses.
- Security: after the merge, GitHub showed 0 open Dependabot alerts, 0 open code-scanning
  alerts and 0 open CodeQL quality findings.
- Profile gender: "Prefer not to say" saved and survived a reload (restored to Female
  afterwards). "Not specified" reported success but kept the previous value — fixed in
  the follow-up PR.
- Focused-document chat: "Ask about this document" opened a new conversation with the
  document card; Nora answered from the document; reopening the conversation after a
  reload restored the card. Dismiss did not remove the card (the server restored the
  saved document) — fixed in the follow-up PR. Answers do not yet show which document
  they used.

## After #153 deployed (night)

- Profile gender: "Not specified" saved and the Gender row stayed hidden after reload;
  restored to Female afterwards.
- Focused-document chat: Dismiss removed the card, and it stayed gone after a reload and
  reopening the conversation; the earlier answer remained.
- SMART standalone launch from the clinician import page reached the sandbox patient
  login (previously the provider patient picker). Stopped before signing in.
- Condition references: the synthetic condition rows were marked due and one refresh was
  run (with requester approval; the service role cannot delete them by design). All 29
  rows were found, in English and Spanish where both exist, for example Osteoarthritis /
  Osteoartritis and Eczema / Eccema; the run logged `scheduled_job.finished` (success).
  Three subjects cached in one language were not seeded in the other (OPS-004).

## After #154 deployed (night)

- Document citations: as Morgan, Records → Metformin prescription → Ask about this
  document. In English the answer ended "Source: Metformin prescription
  (Morgan-Ellis_Metformin-Medication-Order_2026-10-02.pdf)"; in Spanish "Fuente: Receta
  de metformina (…pdf)". Both answers matched the document (one tablet twice daily with
  meals) and pointed to Elena for changes. No page number was shown because Nora answered
  from the document summary; page numbers appear only when page-level details are read.

## EMAIL-001 on production (October 12)

After #152, #156 and #157 deployed, with migrations 057 and 058 applied. Mail went to
requester-owned test accounts (`+clinician` and `+patient` addresses of one university
mailbox) attached to synthetic profiles; Morgan and Elena's login addresses were not
changed. The requester typed every password and one-time code.

- **Clinician invitation:** delivered about one second after sending; SPF, DKIM and
  DMARC passed. The first one landed in Spam (new sending domain). The link carries its
  token after `#` and has no click-tracking redirect. Signup created the account and
  joined Cedar Grove; a non-admin's invitation attempt was refused with a clear message.
  After #156, only clinic admins see the invitation form.
- **Patient verification code:** arrived in the Inbox. Verifying did not turn on any
  notice; opt-in was a separate save.
- **Notices:** an unread care-team message notice and, with the patient set to Spanish,
  an appointment-offer notice ("Horarios de cita disponibles") both arrived in the Inbox.
  Neither contained health details; both linked only to
  `https://app.mediagent.live/notifications`.
- **Opt-out:** with appointment notices turned off, a new appointment offer created the
  in-app notification ("Propuesta de cita") and no outbox row. The setting and the
  patient's English language were restored afterwards.
- **Delivery status:** every send stays "accepted". The backend logs that status checks
  need a full-access Resend key; the configured key can only send.
- **Password reset:** the request page shows the same neutral message either way. The
  first reset links (October 11 template) were reported "unavailable or expired" before
  use, most likely consumed by the university's link scanner; #157 moved the link to the
  portal page, which redeems it only after **Continue**. The new Reset password template
  was installed and confirmed after a reload (6,876 bytes, matching the repository file).
  The clinician reset email then arrived in the Inbox with the MediAgent Pro blue design,
  "Use the button within 1 hour … The link works once" and a link carrying `token_hash`.
  Opening it showed **Continue**, removed the token from the address bar, and Continue
  verified the link. **Saving the new password failed twice ("We could not complete the
  request"), with 401 "Invalid API key" from the account-update call.** Cause: both
  deployed portals were built with a `NEXT_PUBLIC_SUPABASE_ANON_KEY` missing its first
  character (the bundled value starts `yJhbGci`, the project's key `eyJhbGci`). Supabase's
  `/verify` route does not check the key, so Continue worked; the account update does.
  The same client configuration with the correct key, outside the browser, updated the
  account without error.
- **After the key fix:** the requester corrected `NEXT_PUBLIC_SUPABASE_ANON_KEY` in both
  Vercel projects and redeployed. Both portals' bundled key then matched the project's key
  and Supabase accepted it. A new clinician reset (requested 05:34 UTC) was opened from
  the email, continued, saved, and the requester signed in again at 05:36 UTC, landing on
  Risk Radar. Supabase cleared the recovery token. The account has no MFA factor, so MFA
  after reset was not exercised.
- **Patient reset:** requested from `app.mediagent.live` at 05:47:11 UTC (neutral 204);
  the requester opened the email, saved a new password and signed in at 05:47:47 UTC;
  Supabase cleared the recovery token.
- **Reset emails in the inbox (checked in Gmail):** five in one thread, each the intended
  variant. 21:08 PT, `+clinician`: the old October 11 template (green, Supabase verify
  link), the one #157 replaced. 21:55 and 22:34 PT, `+clinician`: MediAgent Pro, blue
  `#2563EB` button, link to `clinician.mediagent.live/reset-password?lang=en-US` with
  `token_hash`. 22:47 PT, `+patient`: green `#147465`, English, `lang=en-US`. 22:48 PT,
  `+patient`: green, Spanish ("Restablece tu contraseña", "menos de 1 hora"), `lang=es-MX`.

## Email preferences, Team & Roles and Copy (October 12, late)

- **#158 email card:** Morgan's Profile shows an EMAIL NOTICES label over one grouped card:
  truncated address, "Email unavailable" chip, "Demo accounts can't receive email. In-app
  notifications stay on." and one footnote; no controls. Same at 375 px, with no
  horizontal scrolling. Elena's Settings shows the same state in a standard Settings card
  (mail icon, Email notices heading and badge, footer note).
- **UX-003 as provider Elena:** Team & Roles shows "Only clinic admins can invite team
  members." and no invite form; the per-member ⋯ menus are still shown (known). Clinic-code
  Copy showed "Copied" with no uncaught error; earlier "Write permission denied" console
  errors predate #156.
- **Public key consumers:** after the key fix both portals' bundled key matches the
  project's and Supabase accepts it. No upload was performed (the browser used here cannot
  choose files). Clinician dashboard realtime is disabled in production
  (`NEXT_PUBLIC_ENABLE_DASHBOARD_REALTIME` is not set), so it was not affected.
- **Requester checks:** as clinic admin Carmen, Copy worked. A fresh invitation link
  opened signed out showed one primary "Create clinician account" button, the invited
  clinic/role/address, and "Already have a MediAgent clinician account? Sign in to accept"
  as a text link.
- **Upload after the key fix:** a synthetic one-page follow-up lab report for Morgan
  (`Morgan-Ellis_Diabetes-Follow-Up-Lab-Report_2026-10-12.pdf`, 3,140 bytes; HbA1c, fasting
  glucose, metabolic panel with eGFR, lipids, liver enzymes, urine albumin/creatinine and
  B12, all consistent with her October 2 visit and Metformin order; every page marked
  "SYNTHETIC TEST DOCUMENT ONLY") was sent through the patient Records upload. Storage
  accepted it with the corrected key (200) and the backend registered it (201) as a
  patient upload pending clinician review; the stored hash matches the file.

## Clinician flow for an uploaded lab report (October 12)

The synthetic lab report above, uploaded by Morgan at 05:59 UTC:

- **Ingestion** (06:03 run): parse completed; record title "Diabetes follow-up lab report" /
  "Reporte de laboratorio de diabetes"; patient explanation ready. One candidate fact: the
  condition "Type 2 diabetes mellitus" (high confidence, page 1 excerpt). None of the 20
  results was extracted: the extraction prompt asks only for medications, conditions,
  allergies and obligations (AI-005). The explanation said the record lists no follow-up
  steps and suggested asking about tests.
- **Review queue and Documents** (Elena): queue item, protected source preview of the full
  page, facts dialog. Two display bugs (UX-004): dates show day-first (12/10/2026) from the
  browser region, and the condition's name is labelled "Medication".
- **Document approval** 06:05 UTC; the draft request queued at parse time completed in the
  06:12 run as version 5: the same four active items as version 4 (Metformin 500 mg twice
  daily, water with meals, walking Monday/Wednesday/Friday, daily fasting glucose), because a
  condition cannot become a care-plan item.
- **Plan approval:** each item's English wording checked against its Spanish source
  (4/4), Metformin reconciled as an update of the existing record, approval note added,
  review saved, Today preview checked, then approved 06:15:43 UTC; version 4 superseded.
- **Patient:** Today shows the same five tasks credited to Dr. Elena Park; notifications
  show "Document processing completed", "Document review updated" and "Your care plan was
  updated".

## AI-005 production check (October 13)

Synthetic test patient (Rajeev Chaurasia) and Elena Park, both portals, after #161–#164
deployed. #164's backend was live only after #165 redeployed `main`: #163 and #164 had
deployed in parallel and the older image took the traffic.

- Critical result: the synthetic potassium 6.9 report raised "Critical test result
  reported" under Alerts → Needs attention; acknowledging it removed it (22 → 21 open).
- Evidence: each result on a new synthetic lipid/A1c upload cites its whole printed row
  (`HDL cholesterol | 38 | L | > 40 | mg/dL`). The first upload lost A1c because the report
  heading names it; after #166 the recheck upload registered all seven results.
- Nora: a question about the lipid report shows the results card (five flagged results,
  "Show 1 result in range", link to Records), still present after a reload; a general
  question in the same conversation gets no card.
- Care plan: the discharge draft was reviewed (glipizide removed per its STOP line,
  lisinopril changed to the printed 20 mg in both languages, routes chosen) and published;
  the patient's Today shows the four activities and "Care plan approved by Dr. Elena Park".
- Email: Resend lists every recent send as Delivered.

Defects found and their fixes are recorded in the
[AI-005 spec](../.agent/specs/ai-005-agent-quality.md).

## October 18 deployed-verification campaign

This campaign began on deployed `main` at `582c397` (#192). Main subsequently
advanced to `ee49c17` (#191 merged); its deployed behavior is not assumed from
the merge. The hosted ledger records `076_care_conversation_activity_review.sql`
as applied at 2026-10-19 06:28 UTC. It covers the real `Verify deployed` rows in
[the task board](../.agent/TASKS.md), with each observation tied to the build and
state actually seen. All patient and clinician data used below remain synthetic.

### Evidence rules

- A row moves to Done only after its stated deployed behavior is observed and the
  observation is recorded here. A successful deployment, migration receipt, old
  staging run or local test is not a substitute.
- Record each check as `Pass`, `Fail`, `Blocked` or `Not applicable`, with the account,
  portal, locale, viewport, destination/state after reload and any downloaded artifact.
- Read-only checks run first. State-changing checks use normal application APIs and UI,
  never ad hoc SQL. They require an explicit synthetic label or a written note here
  identifying the test state they created.
- A defect stays attached to its task with exact reproduction steps and expected versus
  observed behavior. Do not weaken acceptance to close the row.
- One journey may satisfy several task IDs, but each task keeps its own verdict.

### Ordered journeys

| Order | Journey | Task rows covered | Acceptance path | Initial state |
| --- | --- | --- | --- | --- |
| 1 | Presentation and duplicate document | PAT-005-L | At 390 px, inspect the patient's duplicate/skipped record and the clinician's Documents and Review Queue representation. If no duplicate remains, upload one byte-identical synthetic fixture through the normal patient flow, wait for ingestion, confirm it creates no facts/summary/review work, and verify both surfaces explain the skip without a false empty-facts review. | Passed using Rajeev's retained October 14 synthetic copy; no new upload needed. |
| 2 | ADR information loop and MedWatch workspace | PV-001-B, PV-001-C, PV-002, UX-005 | Use an existing synthetic ADR assessment so the known symptom-intake outage is not mistaken for this feature. Verify patient request and answer in en-US and es-MX, clinician evidence attribution/rescore and answered-history alert, patient-record ADR tab, 390 px Form 3500 step navigation, old `/medwatch?assessment=` redirect, draft/edit/approval/preview/PDF and retained discard state. Reload after every authoritative transition. Actual FDA submission and external-submission recording are out of project scope. | Both-language Hannah answers and synthetic MedWatch edit/approval/export/discard passed October 19; deletion, audit-ledger inspection and cross-browser PDF remain. See grouped acceptance continuation. |
| 3 | Canonical appointment loop | SCH-001-V | Use Rajeev's existing future offers to avoid creating a third. With action-time approval, respond to exactly one offer; verify the persisted visit, notifications, responsible clinic/clinician, timezone, reload behavior and one-time calendar download in both portals. Verify clinician cancel/complete/no-show controls separately without conflating them with a patient response. | Patient confirmation, reload and calendar export passed October 19; clinician detail and response alert passed October 19. |
| 4 | English-first review of Spanish content | LOC-003 | Open Spanish-origin facts, care-plan wording and a Spanish care-team message as the clinician. Confirm English presentation is labelled as translation, original evidence remains available, failed guards never display unsafe translation, message reads do not block, and the patient receives only wording that passed the existing review gate. Record incomplete follow-up scope separately rather than calling it shipped. | Partial; one source-label defect, DV-004. |
| 5 | Scheduled bilingual knowledge refresh | OPS-004 | Read the October 18 weekly job/run record and verify active synthetic conditions have both en-US and es-MX cache rows, with `subjects_new_locales` reported. Use an authorized manual run only if the scheduled run did not occur. | Passed; scheduled run succeeded and no active condition lacked a locale. |
| 6 | SMART hand-off and AI safety behavior | INT-003-V, AI-004 | Continue the standalone SMART sandbox flow past patient login and consent to the deployed import review hand-off, preserving provenance. Separately run bounded synthetic Nora checks for emergency guidance/clinician alert, general wellness, mild symptoms, low mood and bilingual behavior; record final responses and saved side effects without claiming clinical validation. | Planned; sandbox credentials/consent and chat mutation need user participation or confirmation. |
| 7 | Merged #191 patient and care-team paths | LOC-002, COM-002 | Verify guest-to-saved locale and reload without changing a schedule or approved wording. For the activity-message path, attach one currently approved item in a named private thread, send a synthetic question only with action-time approval, inspect the clinician's exact draft link/audit, and confirm no publication/reminder change. | October 19: approved Rajeev/Elena send and draft opening completed, but exact-item focus failed (DV-010). Rajeev's approved locale switch and restore preserved schedule/completion, but a transient mixed-language render appeared after restore (DV-011). Guest/signup and full-reload checks remain. |
| 8 | Merged #191 AI and demo evaluation | EVA-001, AI-006 | Run the selected paired-locale synthetic fixtures against the real provider, retain raw final responses and adjudicate observed outputs without claiming clinical validation. Recheck SOAP failure behavior and one bounded general-wellness response; avoid accidental symptom or medication side effects. | Local dry run and unit tests in #191; deployed/provider replay not yet run in this campaign. |

### Task verdicts

| Task | Current verdict | Evidence / blocker |
| --- | --- | --- |
| PAT-005-L | Pass | Elena, Review Queue → Rajeev's byte-identical lipid/A1c copy → exact [Documents anchor](https://clinician.mediagent.live/patients/c102f321-a2b6-40e4-95f4-f21390b18e57?tab=documents#document-f13a4d58-799c-4d02-b529-eef2d7a3f0f1). Both clinician surfaces say “Duplicate upload — extraction skipped”; Documents explains the copy created no new facts or proposals, while upload review is separate. Signed in as Rajeev, [patient Records](https://app.mediagent.live/records) lists “Lipid Panel A1c copy” as “Duplicate upload.” Its detail sheet says the exact contents were already processed, the copy is stored, and no new facts or care-plan instructions were created; it does not present an empty-facts review. Expanding Source document displayed a one-page original preview and a Download original link. At measured 390 CSS px, the detail sheet and page each fit (`scrollWidth = innerWidth = 390`). This is the existing October 14 byte-identical synthetic copy; no new upload, review or deletion occurred. |
| PV-001-B | Partial pass | With the requester's action-time approval, signed-in synthetic Hannah answered “I’m not sure” to both safe retrospective questions on the deployed en-US form, reviewed and confirmed them, then sent. The patient saw “Your answers were sent,” Today no longer showed a waiting request, and after reopening `/chat?view=follow-up&request=523d8a8a-5bff-422d-a0f6-2b821b13e97a`, History showed both saved answers and “Answered.” Elena's exact [ADR case](https://clinician.mediagent.live/adr-reviews/aa904f7b-bd23-4ce2-8d14-6c98f910c297) gained dated, patient-confirmed dose-response and previous-reaction evidence; the deterministic score remained 4 / Possible, as expected for unknown answers. Prior score/classification and clinician decision controls remained intact. The new evidence appears alongside older identical unknown entries (DV-007). Switching Hannah's saved language to es-MX re-rendered the answered request, date and answers in Spanish (`No sé`) without changing the stored outcome; her original en-US setting was restored. Database audit read and submitting a fresh request in Spanish remain. |
| PV-001-C | Partial pass | Hannah's en-US answer created one “Patient answered medication-safety follow-up” notification in clinician Alerts → History, naming Hannah, saying it is not a clinical decision, and linking through `/medwatch?assessment=aa904f7b-bd23-4ce2-8d14-6c98f910c297` to her exact ADR case. The patient request moved from pending to answered, and History persisted after navigation/reload. Maya's reviewed case retains patient-confirmed rechallenge, dose-response and prior-reaction answers, score 6, and the review note. Spanish, patient deletion and broader visual/accessibility checks remain. |
| SCH-001-V | Partial pass; intermittent failures | Elena `/appointments` initially failed, then loaded two existing Rajeev offers and Morgan's confirmed October 22 visit. On October 19, with explicit action-time approval, synthetic Rajeev chose the first Cedar Grove offer's Tuesday October 20, 10:00 AM Pacific slot. Patient Visits immediately showed one confirmed upcoming visit with Elena, withdrew the alternative Wednesday October 21, 3:00 PM slot, and left the second offer untouched. This state persisted after reload. Add to calendar downloaded `appointment-818ff2a5-99b3-4265-b516-e76a9760c495.ics`; its `DTSTART:20261020T170000Z` and `DTEND:20261020T173000Z` match 10:00–10:30 AM Pacific Daylight Time, with `STATUS:CONFIRMED` and `CLASS:PRIVATE`. The patient notification list still contains the older offered notice; opening the list did not mark it read. Elena's refreshed My schedule then fell from two to one awaiting reply and showed Rajeev as the next visit. The exact visit drawer showed Confirmed October 20 at 10:00 AM Pacific, the withdrawn alternative, and the second still-pending offer. Clinician Alerts → History gained one unread “Patient responded to an appointment” item for Rajeev/Cedar Grove linking to the same appointment ID. No clinician decision was taken. Earlier Morgan `/visits` intermittently failed, showed UTC despite a saved Pacific timezone, and her confirmed visit's calendar download failed. See DV-001–003 and DV-006. |
| LOC-003 | Partial pass; one wording defect | Elena, Morgan's approved V5 Care Plan: English-first view and Spanish wording are present. Hydration cites its Spanish source. Metformin says “Source: Spanish document” / “Translated from Spanish” while its sole visible source is an English Metformin order (DV-004). In Messages, Morgan's Spanish note shows the original plus labelled English translation. Other guards and translation failure paths remain untested. |
| OPS-004 | Pass | Staging SQL Editor, scheduler run `2026-10-18 10:02:08–10:02:52 UTC`: success, `subjects_new_locales=2`, `subjects_checked=35`, `subjects_failed=0`, `subjects_deferred=0`. A read-only join of active `conditions` to MedlinePlus `health_knowledge` returned zero names with fewer than two cached locales. The one remaining historical one-language cache key, `diabetes tipo 2` (`es-MX:found`), has no active condition row, so the active-condition requirement is met. No manual run was needed. |
| PV-002 | Partial pass | Elena's Maya report `MP-UMZS` is approved for export, says “Not submitted to FDA,” links to the reviewed ADR case, and exposes the four Complete → Preview → Approve → Download steps. At the Preview step, its link yielded a valid eight-page, AES-256 encrypted PDF 1.7 Form FDA 3500; the first page rendered with synthetic data and a “DRAFT — Not for submission” watermark. Draft editing, a new approval, submission-record action and Acrobat/Preview compatibility remain untested. |
| UX-005 | Partial pass | Maya's patient-record ADR tab lists three cases with score/status and links. `/medwatch?assessment=e4c2daa4-0ac6-475a-9171-2bb8685365ed` redirected to that exact ADR case. At a measured 390 CSS px, the MedWatch detail had no horizontal overflow; the mobile step buttons navigated Download → Approve → Preview and stayed within the viewport. The Preview step had an embedded iframe and “Open in new tab” link; the PDF downloaded and rendered via Poppler, but the in-app browser's embedded PDF area appeared blank, so viewer-specific display still needs a Chrome/phone check (DV-005). At a narrower measured 312 CSS px, the Next button extended to x=323 and clipped; 312 px is below the 390 px acceptance viewport. |
| INT-003-V | Not run | Requires the public sandbox login/consent hand-off. |
| AI-004 | Not run | Use bounded synthetic prompts and record final responses plus server-owned outcomes. |
| LOC-002 | Partial pass; mixed-language transition | With the requester's approval, Rajeev's Profile changed en-US → es-MX → en-US. Spanish Profile, Today and Visits controls/dates appeared; Visits still showed the confirmed October 20, 10:00 AM Pacific appointment and the separate pending offer after refresh. Today remained 0/4 complete, with the four live V1 activities. The saved English preference was restored and English Today returned. Immediately after the restore and navigation to Today, the English interface briefly displayed Spanish approved activity wording and a “Written in Spanish” label before settling to English (DV-011). During the initial Spanish navigation, English activity wording appeared first with its English-source label. No reminder, completion, appointment or approved-plan change was made. Guest/signup, hard-reload first paint, notification copy, small-screen/accessibility and bilingual clinical wording review remain. |
| COM-002 | Partial pass; exact-item deployed recheck pending | With explicit approval, synthetic Rajeev selected his existing approved “Check fasting blood glucose every morning and record it in the portal” activity in his private Elena Park/Cedar Grove thread and sent exactly one message: “Synthetic demo question: Is this check scheduled every morning? No change requested.” The patient thread showed the saved text and activity; Elena's Messages list showed Rajeev with one unread and the thread displayed the attached title/frequency with an explicit warning that replies do not change plans/reminders. “Review activity in draft” opened Rajeev's care plan and created/reused one unpublished V2 draft with four proposed items and 0/4 wording verified. Repeating the open showed no extra draft/items. The deployed destination displayed the first Atorvastatin item, not the attached glucose item; its hash target was not in the rendered DOM and focus remained on `BODY` (DV-010). PR #196 selects the linked item before mounting/focusing its editor and adds a multi-item regression test; that fix is not yet deployed. Patient Today remained live V1 with four activities and 0/4 complete; no edit/save/publication occurred. Database audit, authorization and duplicate-send replay, bilingual review, proof of unchanged reminder schedules and the fixed deployed focus remain. |
| EVA-001 / AI-006 | Narrow live pass | In a new deployed Rajeev Nora conversation, the bounded English prompt “Synthetic QA only: give general sleep-habit tips; I have no new symptoms” received ordinary sleep-habit guidance, a general-wellness limitation and care-team follow-up advice; the UI displayed no symptom-report confirmation. This is one English wellness case, not the repeatable paired-locale EVA-001 run. Mild/stable symptoms, low mood, Spanish, crisis floors, provider calibration and deployed SOAP failure/retry behavior remain. |
| UX-006 | Partial pass | Signed-in Elena, October 19, 1024 CSS px: My schedule's This week view settled to two confirmed Cedar Grove visits (Rajeev October 20 at 10:00 AM and Morgan October 22 at 9:00 AM), with clinic chips and no page overflow (`scrollWidth = innerWidth = 1024`). Needs action showed one awaiting reply, one expiring soon and two change requests. Selecting Willow Terrace showed no Cedar Grove visits and a scoped empty state; returning to All restored the agenda. New offer showed a patient/clinic picker and 2–4 time form. Selecting Rajeev derived Cedar Grove and Pacific timezone; entering an existing booked time did **not** produce conclusive busy-time guidance through this browser automation, so that behavior is not accepted or filed as a defect. Rajeev's patient-record Appointments tab displayed the remaining offer, confirmed slot and withdrawn alternative. Settings showed one Your clinics list with both clinics. No offer or visit was changed. 390/1280 px, busy-time lookup, conflict refusal, distinct-patient count and status-changing visit actions remain. |
| AUTH-002 | Partial pass | Two Elena clinician tabs opened under the same signed-in browser session and independently loaded Settings and My schedule. Both remained Elena after simultaneous reload; neither went to Login. This does not force a rotating-token refresh race or cover cross-tab sign-out, MFA/aal2 or the two-hour idle warning. No session settings or credentials were changed. |
| PAT-001-A | Partial pass | After a hard reload of Rajeev's existing conversation restored its saved answer/source card, a new synthetic wellness turn was sent and the page was hard-reloaded while Nora was still answering. The reloaded page restored the saved patient message, showed that Nora was preparing the reply, and then displayed one completed reply. A second signed-in patient tab showed the same single saved reply. A second document-grounded turn was also reloaded in progress and completed once. No `CHAT_TURN_EXPIRED`, duplicate patient message or duplicate answer appeared, and the bounded Cloud Run error query for 16:45 UTC onward returned no expiry, HTTP 5xx or error entry. A forced socket disconnect, a genuinely competing second-tab send/busy message, retry exhaustion, legacy-client compatibility and Spanish remain. |
| PAT-004 | Partial pass | Rajeev opened the exact “Lipid and glucose lab results” record and chose “Ask about this document.” Nora showed the selected filename as attached context. The approved synthetic prompt asked for a summary with no new symptoms; after a hard reload during generation, the same context and patient message returned, followed by one answer containing the report's values, automatic/unreviewed warning, page-specific source and Results card. Both patient tabs showed the same saved answer. Dismiss removed the active context card and it stayed absent after reload while the historical answer/source remained. Replacement with another document, a subsequent unfocused answer, deleted/unavailable source behavior and Spanish remain. |
| LOC-002 guest entry | Partial pass | A separate `/login?lang=es-MX` tab rendered Spanish labels and `html lang=es-MX` without horizontal overflow at the observed viewport. Its “Crear cuenta” link preserved `?lang=es-MX`; signup rendered Spanish labels and the same document language. This is a settled-page check, not a measured first-frame/flash test. No account was created; onboarding and saved-preference continuity remain. |
| NOT-001 | Partial regression; fix awaiting deployment | Elena's notification panel showed the new Rajeev care-team message with the correct patient, clinic and exact private-conversation link. Following that link opened the expected Rajeev/Elena/Cedar Grove thread and displayed the saved attached-activity message. However, the message notification and total unread count remained unread after the conversation opened and after an explicit panel refresh (DV-013), contrary to the notification contract's conversation-read synchronization. PR #196 makes unread destination navigation wait for the authoritative receipt-read write (but not its background list refresh) before routing, with a regression test; existing database coverage still checks conversation-marker synchronization. No notification was manually marked read during the deployed observation, and the fix still needs a deployed recheck. |

### OPS-005 log correlation — October 19

Read-only Cloud Run request metadata (no URLs with patient identifiers, query strings,
payloads or transcript text retained) confirmed **14 HTTP 502 notification GETs** on
October 18 at 06:13, 06:38 and 06:44 UTC. They were list/summary reads, took
8.18–8.95 seconds and ran on revisions `00156-6df`/`00157-9cj`, before the
notification fix described in the [NOT-001 contract](../.agent/specs/not-001-notification-centre.md#production-fix-slow-reads-duplicate-polling-starved-chat-migration-075).
This supports the notification-pool contention diagnosis; it does **not** by
itself explain Morgan's Visits timezone or calendar-export failures.

From October 18 07:00 UTC through the bounded October 19 log query, no further
backend HTTP 5xx was returned by that metadata filter. Recent notification GETs
were 200, but the then-current revision `00164-46s` had 11 observed requests,
median 0.716 s, p95 1.532 s and 9/11 over 0.5 s. This is end-to-end Cloud Run
latency, not a database-only timing; the small sample is insufficient to close
OPS-005's 0.5 s acceptance target. Revisions changed during the check, so the
sample is identified by revision instead of pooled into one performance claim.
Current patient/clinician browser-console error lists were empty; the clinician
Vercel request-log view showed no Error/Fatal in its available last-30-minute
window. Neither observation reconstructs the earlier browser-side `Failed to
fetch` episode.

Two fresh synthetic Nora turns were then hard-reloaded while in progress. Both
completed once and restored their saved result. A bounded Cloud Run query from
16:45 UTC onward returned no `CHAT_TURN_EXPIRED`, HTTP 5xx or error entry. This
closes neither the representative-latency target nor the forced-disconnect and
competing-tab cases, but it supplies a current successful recovery sample.

Separately, six October 19 backend stderr tracebacks on revision `00159-46c`
(05:53–06:08 UTC) all reached `risk_score_service.py:189` while converting a
null symptom severity with `int(None)`. The clinician deep-dive service catches
that exception and substitutes risk `unknown`, so this is a data-handling defect
(DV-012), **not** evidence that those requests failed or the root cause of the
schedule/Visits intermittent errors. The traceback messages, patient IDs and
request bodies were not copied into this report.

### Defect log

| ID | Task | Severity | Observed | Expected | Status / follow-up |
| --- | --- | --- | --- | --- | --- |
| DV-001 | SCH-001-V | High | Elena at `/appointments`, All clinics: initial load and Retry both showed “Could not load your schedule”; New offer was disabled. Later the same screen loaded and New offer, two Rajeev awaiting replies and Morgan's confirmed visit were usable. | Schedule and roster load consistently so a synthetic offer can be created. | Open as intermittent; Cloud Run request logs show HTTP 200 for appointments/schedule and roster reads during the failure window, which does not prove the frontend could use the response. Exact failure not yet isolated. |
| DV-002 | SCH-001-V | High | Morgan at `/visits`: initial load says “Could not load your visits”; Retry once displayed visits. Visits showed “Your saved timezone is unavailable. Times are shown in UTC,” although `/profile` showed “Pacific Time · Los Angeles.” Later return to Visits again failed. | The saved timezone and visits load consistently, with times rendered in Pacific Time. | Open; do not treat a UTC display as a valid timezone acceptance result. |
| DV-003 | SCH-001-V | Medium | Morgan's confirmed October 22, 2026 visit showed “Could not download this appointment” after Add to calendar; no download event occurred. | A one-time calendar file downloads for an eligible confirmed visit. | Open as intermittent/account-specific: Rajeev's newly confirmed October 20 visit exported a valid calendar file on October 19. Cloud Run request logs showed HTTP 200 for Morgan's failed request, so inspect browser response handling rather than presuming a backend 5xx. |
| DV-004 | LOC-003 | Medium | Morgan V5 Care Plan → Metformin item labels the source “Spanish document” and “Translated from Spanish,” but Source excerpts and confidence shows only English text from `Morgan-Ellis_Metformin-Medication-Order_2026-10-02.pdf` page 1. | Translation/source labels accurately describe the item provenance. | Pass live for the reported Metformin case after #201; English source label matches original English page-one evidence and the false Spanish marker is absent. See the post-merge #200/#201 checkpoint; broader LOC-003 cases remain. |
| DV-005 | UX-005 | Low; browser-specific | At measured 390 CSS px, MedWatch Preview's embedded PDF area was blank in the Codex in-app browser although its “Open in new tab” link returned a valid, renderable eight-page PDF. | The embedded preview shows the document or a helpful fallback in supported browsers. | Open; compare in Chrome/mobile before attributing this to application code. The 390 px stepper itself passed. |
| DV-006 | Cross-portal; SCH-001-V, PV-001-B/C | High; intermittent | Clinician Schedule, ADR case and Alerts, plus patient Visits, Profile, Chat and ADR follow-up alternated between error/indefinite loading and success on retry. Clinician console recorded a Next.js RSC `Failed to fetch` fallback. The October 19 log correlation found older notification-only 502s, while schedule/ADR/profile GETs observed during the earlier failure window were 200; those status codes do not prove browser success. Six separate risk-score `TypeError`s are caught by the clinician deep dive (DV-012), not a demonstrated cause of these page failures. | Stable reads and clear retry rather than stranded loading or misleading empty states. | Open; reproduce in Chrome/phone with browser network timing/response details and correlate exact request IDs across Vercel and Cloud Run. Current last-30-minute Vercel window and browser console had no errors; this does not reconstruct the earlier event. Do not infer a single root cause from status alone. |
| DV-007 | PV-001-B | Medium; presentation | Hannah's repeated answers lacked distinct request attribution. | Preserve evidence and distinguish current from historical requests without inferred dates. | Closed for the reported case after #202: October 20 live retained all rows, four Different follow-up/two Current follow-up, dates only on current pair; score unchanged. [Evidence](#october-20--post-202-live-acceptance). |
| DV-008 | PV-001-C; localization | Low; copy | Spanish headings mixed English clinical source text into the interface without a source label. | Identify original symptom wording and recorded medicine names without inventing translations. | Closed for answered-request path after #202: en-US/es-MX labels, read-only unknown answers and reload pass October 20. Demo wording review accepted; both preferences restored. [Evidence](#october-20--post-202-live-acceptance). |
| DV-009 | Migration ledger | Medium; schema provenance | A read-only hosted-ledger query found `076_care_conversation_activity_review.sql` applied on October 19, but also `071_confirmed_symptom_handoff.sql` applied on October 18. The latter filename is not among current main's 91 local migration files, which include `071_clinician_visit_management.sql`; the two newer local files are 077/078 and their hosted status was not checked. | Every hosted applied filename and checksum should be accounted for in the canonical migration history or an explicit exception record. | Partially reconciled: merged #159 now includes the canonical 071_confirmed_symptom_handoff.sql file and its pinned history. A fresh hosted checksum comparison and full 077/078 reconciliation remain; do not rename/replay applied files. |
| DV-010 | COM-002 | Medium; navigation | Rajeev sent a synthetic message linked to his approved daily fasting-glucose activity. Elena clicked “Review activity in draft” from that private thread. The care-plan route included `#care-plan-item-252f…`, but the panel rendered its first Atorvastatin editor instead. On repeat, the hash remained but the target was not in the DOM because only the selected item editor is mounted; focus was `BODY`. Manually selecting the fourth glucose item worked. | The linked activity is selected, scrolled into view and keyboard-focused when the clinician opens the draft; a repeat open is idempotent. | Pass live after #196: exact glucose article mounted, scrolled and H3 focused, with V2 unpublished and V1 live. See the #196 evening checkpoint. Broader COM-002 acceptance remains. |
| DV-011 | LOC-002 | Medium; locale transition | After Rajeev saved en-US following an es-MX test and navigated to Today, the English chrome briefly displayed Spanish approved activity wording with “Written in Spanish by your care team,” then a subsequent settled render showed the English wording. On the first Spanish Today navigation, English activity wording with the English-source label appeared before the locale-specific feed settled. | The initial and subsequent Today renders use the current saved locale consistently, or hold the feed while locale-specific wording loads; do not show stale approved wording as if it were the current choice. | Observed transition passes live after #200: matching loading state preceded Spanish/English approved tasks; 0/4 completion and confirmed appointment persisted; English restored. See post-merge checkpoint. Every-frame/network-throttled first-paint measurement and broader LOC-002 checks remain. |
| DV-012 | Clinician risk display; symptom reports | Medium; data handling | Six Cloud Run stderr tracebacks on October 19 revision `00159-46c` reached `RiskScoreService._fetch_recent_symptom_severity` line 189: `int(row.get("severity", 0))` received `None`. The caller in `ClinicianService.get_patient_deep_dive` catches the exception and presents risk `unknown`/adherence `0.0`; it does not prove a failed HTTP request. | A missing severity is handled as absent or invalid input according to the risk-score contract, without an exception or misleading fallback. | Partial live evidence after #196: Rajeev and Morgan risk details loaded and bounded serving-revision error logs were empty. Mixed/all-null rows are covered in regression tests; direct null-row execution during the deployed lookback remains unproven. No source row was rewritten. |
| DV-013 | NOT-001; care-team messages | Medium; unread state | Elena followed the unread “New message from Rajeev Chaurasia” notification into the exact private conversation. The saved message and attached care-plan activity were visible, but the notification still showed Unread and the bell remained at 31 after the panel's explicit Refresh. | Opening/reading a private conversation clears its corresponding message unread receipt while leaving unrelated notifications unchanged. | Pass live after #196: fresh message notification 37→38→37 via its exact destination, retained after full reload; unrelated unread/action counts unchanged. See #196 evening checkpoint. |

### PR #196 local fix verification — October 19

This checkpoint validates implementation, not deployment. It changes no migration,
remote configuration, care plan, reminder or clinical record.

| Surface | Command | Result |
| --- | --- | --- |
| Clinician portal behavior | `npm run test -- --silent` | 69 files / 615 tests passed, including multi-item care-plan deep-link selection and read-before-navigation notification coverage. |
| Clinician portal static checks | `npm run lint` and `npm run typecheck` | Passed. |
| Clinician portal production build | `SENTRY_AUTH_TOKEN='' npm run build -- --webpack` | Passed; existing Next.js workspace-root and Sentry migration warnings remain non-blocking. |
| Risk/deep-dive regression | `PYTHONPATH=src .venv/bin/pytest tests/unit/test_risk_score_service.py tests/unit/services/test_clinician_service.py --no-cov -q` | 96 passed. |
| Changed Python quality | `.venv/bin/ruff check`, `.venv/bin/ruff format --check` and targeted `.venv/bin/mypy` | Passed. |
| Diff hygiene | `git diff --check` | Passed. |

After merge/deployment, re-open the existing synthetic activity message and verify the
glucose editor is selected/focused; follow one fresh unread private-message notification
and verify only that receipt/count clears; then query a bounded backend log window to
confirm no new null-severity conversion traceback. Until those checks are recorded,
DV-010, DV-012 and DV-013 remain deployed-recheck items rather than Done.

### PR #196 deployed recheck — October 19 evening

This follow-up supersedes the earlier pending-deployment statements for DV-010
and DV-013. Performed around 18:02–18:07 America/Los_Angeles using the already
signed-in synthetic Rajeev patient and Elena clinician accounts. The backend
reported revision `mediagent-backend-00170-hgw` serving 100% of traffic.

| Check | Result | Observed evidence and remaining boundary |
| --- | --- | --- |
| DV-010: activity message → correct draft editor | **Pass live** | Opened the existing Rajeev/Elena/Cedar Grove conversation and its daily fasting-glucose attachment through “Review activity in draft.” The resulting hash was `#care-plan-item-252f3605-631d-4cd4-82b5-3de16cab2407`; exactly one article mounted, containing the glucose editor, and `document.activeElement` was its H3 heading. The editor was scrolled into view. V2 still had four proposed items, 0/4 verified and disabled publication; V1 remained live. No review edits were saved. COM-002's other acceptance boundaries remain. |
| DV-013: fresh notification → private thread → persisted read state | **Pass live** | The old notification was already read before this recheck. Sent exactly one routine synthetic message from Rajeev to Elena: “Synthetic notification verification after PR #196. No action needed.” It persisted with time 18:05:45 Pacific. Explicit notification refresh showed 38 unread, up from the baseline 37, and a fresh Rajeev entry. Its Open conversation link reached the existing private thread with the saved message; unread returned to 37. Full browser reload retained 37, and the fresh notification no longer had an Unread marker or Mark read control. Unrelated safety and appointment notifications remained unread; 36 action items remained. No bulk/manual-read action was used. |
| DV-012: risk-detail regression and logs | **Partial live evidence** | After reload Rajeev showed Low / 100% recorded completion; Morgan's detail showed Medium / 68%, matching the roster rather than falling back to unknown/0. At 18:07:26 Pacific, a revision-scoped `gcloud logging read` with `--freshness=20m`, limit 20, and filter `RiskScoreService OR TypeError OR severity>=ERROR` returned no entries. This does not establish that a null-severity row was within either calculation's lookback window; the mixed/all-null regression tests remain the direct branch evidence. Do not claim a directly reproduced null-row deployed pass. |

No clinical plan was approved, medication changed, appointment changed or source
row rewritten during this recheck. The routine test message and its read receipt
are the new persisted test records. Existing intermittent and localization defects
remain open; successful loads during this window do not close them.

### October 19 evening follow-up verification and fixes

Latest remote main is `20ea7ac` (merged #159). GitHub reports its Cloud Run and
both Vercel deployments succeeded. This corrects the board's prior claim that
#159 was unmerged; runtime activation/library readiness and actual confirmed
symptom handoff remain unverified by this campaign. The canonical migration
directory now includes `071_confirmed_symptom_handoff.sql`; DV-009's missing-file
portion is explained, but a hosted checksum reconciliation is still required.

| Area | Result | Evidence / remaining boundary |
| --- | --- | --- |
| UX-006 agenda | Additional partial pass | Elena's week view loaded the confirmed Rajeev October 20 10:00 and Morgan October 22 09:00 visits. Measured `innerWidth` and document `scrollWidth` matched at both 390 and 1280 CSS px. The initial viewport requests mapped through browser zoom, so dimensions were adjusted and measured rather than assuming requested pixels equalled CSS pixels. No appointment changed. |
| UX-006 new offer | Booked-day guidance passes | Selecting Rajeev derived Cedar Grove and America/Los_Angeles. Automated datetime filling initially changed the visible field without triggering React's change path. With the month segment selected, an ArrowUp/ArrowDown pair fired native changes and returned the exact value to `2026-10-20T10:00`. The form then showed “Already booked that day” and “10:00–10:30 AM · Cedar Grove Community Health,” matching the confirmed agenda. No offer was sent. Server conflict refusal and visit mutations remain untested. |
| LOC-002 / DV-011 implementation | Fixed locally in PR #200; deployed recheck pending | The feed slice previously retained old-language tasks while loading and accepted every response regardless of arrival order. Added the loaded locale and latest request ID; the hook suppresses mismatched-locale tasks/summary before the effect starts, and ignores superseded successes/failures. Same-locale refresh retains prior data. Failure in a new locale shows retry feedback without old-language instructions. No schedule, history or approved wording API changed. |
| LOC-002 local verification | Pass | Patient suite: 75 files / 814 tests; lint and typecheck pass, with one existing unused-variable warning in the merged chat test. Production webpack build passed with existing Sentry migration warnings. New tests cover delayed old responses, old failures after a new success, and a failed locale transition with no adherence write. `git diff --check` passed. |

DV-010/DV-013 acceptance from the preceding section remains valid. DV-011 must
be rechecked after this PR deploys; remaining auth, Spanish ADR, source-provenance,
intermittent loading and clinical-action paths retain their existing limits.

The busy-time lookup was also repeated with synthetic Evelyn selected at Willow
Terrace. For the same October 20 date, it displayed the clinician's Cedar Grove
10:00–10:30 AM booking without naming the other patient. Cross-clinic busy-time
guidance therefore passes; the separate server refusal on submission remains
untested. The unsent form was closed and no appointment/offer was created.

### Post-merge #200/#201 verification — October 19

PR #200 merged as `5d46c30`; both Vercel deployment statuses succeeded. The
preceding backend-affecting #201 deployment also succeeded. Checked the existing
synthetic Rajeev and Elena accounts after refreshing the patient portal.

| Defect | Result | Evidence / limit |
| --- | --- | --- |
| DV-011 | **Observed language transition passes** | Observed transition passes live after #200: matching loading state preceded Spanish/English approved tasks; 0/4 completion and confirmed appointment persisted; English restored. See post-merge checkpoint. Every-frame/network-throttled first-paint measurement and broader LOC-002 checks remain. |
| DV-004 | **Reported Metformin source-label case passes** | Pass live for the reported Metformin case after #201; English source label matches original English page-one evidence and the false Spanish marker is absent. See the post-merge #200/#201 checkpoint; broader LOC-003 cases remain. |

Rajeev's saved language was restored to English before finishing. These outcomes
supersede the earlier DV-004/DV-011 pending statements while preserving the
original reproductions and the wider LOC-002/LOC-003 remaining requirements.

### PR #202 extended checks and ADR presentation fixes — October 19

| Area | Outcome | Evidence and limit |
| --- | --- | --- |
| PAT-004 context replacement | Additional live pass | In synthetic Rajeev Records, opened the original lipid/A1c report and Ask about this document, then returned to Records and chose the distinct lipid/A1c recheck. Nora showed only the recheck filename as active context. Reload preserved it. Dismiss removed the context; another full reload kept it absent. No AI message was submitted, so this does not accept a subsequent unfocused answer, replacement-answer grounding, deleted-source behavior or Spanish response. |
| DV-007 | Reproduced live; fixed locally | Elena's existing Hannah case still showed two dose-response and two previous-reaction answers labelled Patient-confirmed, with only the current pair dated. PR #202 now labels each row Current follow-up, Different follow-up, Recorded follow-up or Follow-up request not recorded as supported by request metadata. All rows and answers are retained; only exact request matches get the response timestamp. Missing metadata is not treated as proof of age. Deployed recheck remains. |
| DV-008 | Fixed locally | Both locales explicitly label quoted symptom text as original wording and medicine identity as recorded. Shared copy reaches pending forms and read-only answered/closed/history views. Stored clinical source text is unchanged; no automatic clinical translation is introduced. New es-MX strings are drafts recorded in the PV-001-C requirements; bilingual review and deployed patient verification remain. |
| Local checks | Pass | Patient lint/typecheck, 75 files / 814 tests and production webpack build passed. Clinician lint/typecheck, 69 files / 618 tests and production webpack build passed. Existing patient chat-test unused-variable and Sentry/workspace-root warnings remain. Focused patient follow-up tests: 75 passed; clinician evidence tests: 10 passed. `git diff --check` passed. No backend/schema change in this increment. |

These results extend the same PR #202. No case decision, new information request,
patient medical answer, medication change or clinical publication was submitted.

### PR #202 grouped acceptance continuation — October 19

The preceding no-mutation statement applies only to that earlier checkpoint.
The requester separately authorized the synthetic Hannah follow-up and MedWatch
workflow below. No FDA transmission, patient deletion, remote SQL or runtime
configuration change is authorized or performed by this continuation.

| Area | Observed result | Remaining boundary |
| --- | --- | --- |
| PAT-001-A competing sends | Two Rajeev tabs sent distinct routine wellness questions against one conversation. The second received the explicit busy/recovery explanation, displayed the saved first message with one inline progress indicator, and retained its new Spanish message in the composer. Leaving the sending view closed its socket; the other tab received one completed English reply. Sending the retained Spanish question afterwards produced one Spanish reply. | This disconnect is navigation away from the sending view, not a simulated network outage. Retry exhaustion and legacy paths have automated coverage, not a newly forced deployed run. |
| PAT-001-A logs | Bounded content-free logs recorded `begin` → `CHAT_TURN_BUSY` at 03:49:46 UTC and a client-initiated socket close, code 1005, at 03:50:15 UTC on October 20 (October 19 Pacific). The busy warning is expected arbitration, not proof of an outage. The recovered tab had no captured console errors. | The patient account switch ended the extra tab session; an uninterrupted 300-second socket run is **not** accepted. |
| PAT-004 later unfocused answer | After the previously recorded dismissal, the fresh sleep-habit answer gave general guidance without lipid values, a document card or a report citation. The subsequent Spanish wellness answer also did not inherit the dismissed source. | Deleted/unavailable-source live acceptance and Spanish document-grounded answers remain. This does not assert per-message clickable citations. |
| PAT-002-B activation | Read-only Cloud Run inspection found revision `mediagent-backend-00171-r7v` and no explicit `SYMPTOM_INTAKE_ENABLED` or `A2A_RETRY_WORKER_ENABLED` environment override. The committed intake default is false; retry-worker default is true. Starting a private draft returned the explicit guided-intake-unavailable error rather than a success. | Runtime activation and target/library readiness must be authorized and checked before patient confirmation/handoff. Candidate-1 remains the selected approved package in source; candidate-2 remains pending review. No new symptom report was confirmed. |
| SCH-001-V Morgan | Elena's week agenda and exact visit detail loaded Morgan's October 22 09:00 Pacific visit. The clinician download `appointment-1fbcc232-3f71-41ca-af04-c14156d3cc39.ics` succeeded: `DTSTART:20261022T160000Z`, `DTEND:20261022T163000Z`, confirmed/private. | The later [Morgan patient recheck](#morgan-patient-scheduling-recheck) also passed timezone, reload and calendar export. Earlier intermittent failures remain unexplained. |
| DV-014 schedule range display | Switching Today → This week briefly relabelled the old empty day result as “No visits this week” before the week response arrived. PR #202 keys visible schedule data by range, clinic and cancelled filter. A mismatched result is hidden behind loading or retry; same-scope refresh retains its prior data. | Fixed locally, not deployed. Regression cases cover delayed week response and failed changed-range versus retained same-range refresh. No appointment write/API changed. |
| PV-001-B/C Spanish answers | Hannah's saved preference changed from en-US to es-MX. Elena issued a new clearly labelled synthetic request for the same two retrospective questions. Hannah reviewed, attested and sent “No sé” for each. The exact request `3a55f7c9-b3a4-40f1-b686-2df8fdaae479` became Respondida in recent requests and re-opened read-only with both answers after reload. Elena's reloaded evidence showed the new patient-confirmed pair dated October 19 20:59 Pacific, with score 4 / Possible unchanged and unread count 37 → 38. | This is functional Spanish UI acceptance, not independent bilingual approval or a deployed audit-ledger inspection. DV-007/008 fixes still await PR deployment. |
| PV-002 synthetic draft | Created Hannah's draft using an explicit synthetic/non-submission rationale. Initial approval readiness truthfully required event-date confirmation and reporter fields. Saved the synthetic narrative, month-only event date `2026-10` (exact day not established), and fictional reporter role. | Later state transitions are recorded below only if completed; no FDA submission is performed. |
| Local checks | Clinician `npm run lint`, `npm run typecheck`, `npm exec vitest run` (**69 files / 620 tests**) and `npm run build -- --webpack` passed. Focused schedule suite: **28 passed**. Backend `PYTHONPATH=src .venv/bin/pytest tests/integration/routers/test_chat_socket_recovery.py tests/integration/routers/test_chat_document_focus.py tests/integration/routers/test_chat_worker_api.py -q --no-cov`: **52 passed**. | Existing Vite/Sentry/workspace-root and backend deprecation warnings remain. Patient code was unchanged since its previously recorded 814-test/build pass. |

Browser access was temporarily disabled during this campaign and later restored.
That interruption is not an application outage or evidence of portal failure.

#### MedWatch lifecycle outcome

Synthetic report `fe12cb1d-0a1f-4066-86df-75ada171f4c7` (HB-ZAFR) completed
create → edit/save → reload → watermarked preview → revision-2 approval → approved
PDF download → discard → reload/read-only retained report. The narrative and
approval/discard notes explicitly identify a synthetic functional test with no
actual FDA submission. The source ADR case returned to **Awaiting review**, score
4 / Possible; its patient-confirmed evidence remained. Discard is retained history,
not deletion. The exported filename was `fda-3500-fe12cb1d-not-submitted.pdf`.

Poppler parsed the eight-page exports and rendered preview page 1 and approved
page 2. Preview shows the diagonal “DRAFT not for submission” watermark and the
month-only Oct-2026 event date. Approved page 2 shows the saved synthetic narrative
without clipping. This is external-render evidence, **not** Chrome/iPhone embedded
PDF compatibility. DV-005 remains open.

The **Record FDA submission** dialog correctly required a date, method and
attestation of an actual external submission; its save was disabled when empty.
The dialog was cancelled without inventing a submission. The requester's later
October 19 scope decision excludes external-submission recording and actual FDA
submission from project acceptance. It is **not remaining work**; the observation
is retained only as historical evidence of what was inspected.

Additional automated command from `backend`:
`PYTHONPATH=src .venv/bin/pytest tests/unit/services/test_medwatch_service.py tests/unit/services/test_medwatch_form_3500.py tests/unit/services/test_medwatch_form_3500_pdf.py tests/unit/services/test_medwatch_form_3500_legacy.py tests/unit/models/test_medwatch_approval_request.py -q --no-cov`
— **285 passed**, three existing deprecation warnings. No backend source changed.

Hannah's original en-US Profile preference was restored and the language sheet
closed after the Spanish journey. The saved retrospective answers remain unchanged.

#### Morgan patient scheduling recheck

After the requester switched to Morgan, Profile showed Pacific Time / Los Angeles.
Visits loaded the confirmed October 22 09:00 visit in `America/Los_Angeles`, with
no UTC fallback. Add to calendar downloaded the exact confirmed visit's file:
`DTSTART:20261022T160000Z`, `DTEND:20261022T163000Z`, confirmed/private. A full
reload retained the correct local time and visit. Captured browser error logs were
empty. No appointment was changed. DV-002/003 therefore have a successful repeated
patient-side observation; the earlier intermittent failures and DV-006 remain
unexplained, not retroactively disproved or assigned a guessed root cause.

### Acceptance closure evidence — October 19

**Read-only deployed audit checks:** queried only the selected synthetic Hannah
assessment/request and MedWatch draft, using a target-host guard. The exact Spanish
request has **one** `patient_information_provided` audit event at
`2026-10-20T03:59:44.145118+00:00`, with Hannah as patient actor and no clinician
actor. The MedWatch draft has exactly one each of `created`, `edited`,
`preview_viewed`, `approved`, `exported`, `discarded`, in that order, all under
the same identified clinician actor. No audit row or clinical source was changed.

**Requester-authorized LLM-assisted demo wording review:** compared en-US/es-MX
ADR copy and notification templates. Retrospective restart/dose-change questions
retain their past-tense constraints; `No lo reinicies para responder` and
`No cambies tu dosis para responder` preserve the prohibitions. The shared caution
also prohibits stopping a medicine. `No sé` preserves unknown, not a negative
answer. The attestation describes past events, not consent to treatment.
Review/send, unsaved-warning, answered/closed and retry messages retain their
intended states. Notifications request existing information without diagnosing.
`texto original` and `nombre registrado` identify unchanged clinical source text,
not translated or independently verified medicine facts. The tú register is
consistent. **Accepted for the synthetic demo; no professional translation or
clinical validation is asserted.** The requester explicitly removed the separate
fluent-reviewer requirement. PR #202's label rendering still needs deployment.

**Intake activation:** all exact target migration checksums, candidate-1 eligibility,
handoff trigger and browser-write restrictions passed read-only preflight. With
specific requester authorization, only `SYMPTOM_INTAKE_ENABLED=true` was updated
on Cloud Run. Revision `mediagent-backend-00172-vp5` serves 100% traffic; a selective
configuration read confirms the flag. Candidate-2, SQL and other settings were not
changed. Activation alone is not patient-confirmation/handoff acceptance.

The chat worker initially retained its false default, explaining Nora's unavailable
answer after backend activation. Separately authorized flag-only revision
`mediagent-chat-worker-00015-65j` now enables the same flag; other settings/image
were preserved. Both services are required for this path.

**PDF compatibility:** the approved eight-page export was inspected in Chrome
(including filled page 2) and macOS Preview (filled page 1/form values), in addition
to the prior Poppler renders. No clipped sampled narrative was observed. Chrome
reported an unavailable text-extraction helper, so full PDF accessibility is not
claimed. DV-005's blank inline in-app viewer remains distinct; no Acrobat or
physical-phone acceptance is asserted.

**Longer chat observation:** Connected at 04:16:41 UTC remained Connected at
04:21:47 UTC, then a harmless synthetic greeting completed once. This is a
306-second observed connected view plus successful turn, not proof of an unchanged
socket ID. The bounded close/connect log query returned no matching records.
Forced network outage and the 3500-second renewal remain untested.

### Push checkpoint and resume order

Morgan's private intake `3eee92cb-e2e3-4e25-bbb4-132caf0cb66e` was ready for
confirmation with no report ID. Explicit consent/confirmation persisted report
`09e479d8-806b-411c-ac05-ded43beb43e4`; the saved state survived reload. Elena's
alert opened ADR case `aa81a4c9-22cb-4a28-b9a1-9a2b5b2b10e7`, awaiting review,
with synthetic mild nausea 2/10 and unverified patient-reported medication facts.
No medication, care plan or clinician decision changed. Unknown and declined
intake answers remained distinct.

**DV-015 — duplicate confirmed-report handoff:** the same report produced completed
tasks `8e30ed34-feba-4c1d-8759-999dff65708c` (`symptom_event:` key) and
`7c424e40-60cb-4ae4-bbf8-930ec1e9e103` (`confirmed_symptom:` key). Migration 071
queues atomically under the latter, while the post-confirmation service used the
former. PR #202 now reuses the canonical task, including queued/working/completed
states, with legacy-key fallback only when no canonical task exists. Existing
live history is preserved; no remote repair or SQL was performed. The fix is
local, **not deployed**. Regression tests cover canonical reuse and legacy history.

Verification: 95 owning intake/API/voice/service tests pass; changed-service mypy,
Ruff and format checks pass. The disposable PostgreSQL contract run initially
found a stale test-adapter whitelist (missing `status`); that adapter was corrected
without changing production claim semantics. Final database result is recorded
in the push verification below. Prior portal suites/builds and 285 MedWatch tests
remain applicable; the only patient-copy change in this increment is a comment.

**Push verification:** `PYTHONPATH=src SYMPTOM_INTAKE_TEST_POSTGRES=1
CHAT_SAFETY_TEST_POSTGRES_DOCKER=1 .venv/bin/pytest
tests/integration/test_symptom_handoff_postgres.py -q --no-cov --tb=short`
from `backend` — **8 passed**, three existing deprecation warnings. The local
adapter also needed the current plain-insert interface; corrected to preserve
its actual conflict behavior. Final changed-file Ruff/format and `git diff --check`
pass. This database suite uses disposable local PostgreSQL, not hosted writes.

Resume in this order:
1. Review/merge/deploy #202 (not authorized here); recheck DV-007/008/014 presentation
   and a fresh single-task confirmed intake for DV-015. No migration is added.
2. Complete forced-network chat failure and quiet socket-renewal acceptance;
   physical voice, bilingual, denial/outage and mobile intake acceptance.
3. Perform explicitly authorized synthetic patient-deletion acceptance; retain
   DV-005 inline viewer and DV-006 intermittent scheduling/read failures for bounded
   reproduction/log correlation. Successful rechecks do not establish root cause.
4. Keep candidate-2 approval separate. FDA transmission/submission recording and
   a human Spanish reviewer are not remaining expo gates under requester decisions.

### October 20 — PR #202 CI continuation

PR remains open; main is still `5d46c30`. Original CI run `39370392453`, attempt 1:
`PR Policy Check` failed because the description replacement omitted all seven
mandatory checked statements. Restored the verified checklist and reran failed
jobs. `Clinician Portal Lint` actually failed its Vitest step: 619/620 passed;
`appointments-page.test.tsx` asserted two schedule calls but observed one immediately
after the success notice. The offer callback sets refresh state; the request runs
in a later effect. The test now awaits the same exact two-call assertion with
`waitFor`, rather than sleeping or changing production behavior. `CI Summary`
was downstream of those failures, not a third implementation defect.

Local `npm run test -- src/__tests__/appointments-page.test.tsx` — **28 passed**;
`npx eslint src/__tests__/appointments-page.test.tsx` and `npm run typecheck` pass.
Full `npm run test` — **69 files / 620 tests passed** after the test-only correction. Existing live
acceptance boundaries above remain unchanged; no merge or deployment was done.

At commit `114d487`, rerun attempt 2 completed successfully. The next head's run
`39486309863` found a newly reported dependency vulnerability: locked
`certifi==2026.7.22`, advisory `GHSA-6q48-6c7w-9gw2`, fix `2026.10.19` according
to its pip-audit output. This is separate from the test timing and PR policy
failures. Do not suppress the advisory or weaken the audit; upgrade the package
in both compiled locks, then verify reproducibility and audit.

**Read-only live continuation:** Morgan's saved report still appears after reopening
his conversation. Elena's signed-in exact case remains Awaiting review, 2/10,
score 0 / Doubtful, explicitly patient-reported rather than a clinical decision.
At 390×844, the conversation's width is 358px and document scrollWidth equals
viewport width (390px); no horizontal overflow. Viewport override was restored.
This is one mobile layout sample, not physical voice or full intake acceptance.

**DV-016:** saved report heading correctly says “Report saved for care-team review”,
but its enclosing accessible region remains “Draft — not submitted”. The local
fix uses the same localized state title for region and heading, including cancelled
and safety-interrupted states. No new copy, mutation, API or clinical behavior.
Both locales and all four state labels are covered; **21 intake tests pass**,
changed-file ESLint and patient typecheck pass. Deployed recheck awaits #202.

Dependency correction: `uv 0.9.24` compiled both locks with
`--universal --python-version 3.12 --upgrade-package certifi`; only certifi changed
to `2026.10.19`. Recompiling without the upgrade option retained identical SHA-256
for each lock. `uvx --from pip-audit==2.10.1 pip-audit -r requirements-dev.txt`
completed **No known vulnerabilities found**. No advisory was ignored; no workflow
gate or runtime certificate verification was disabled.

Final local patient `npm run test` — **75 files / 816 tests passed** including
the new both-locale region-state regressions. The clinician full-suite result
remains 69 files / 620 passed for the schedule-test correction.

### October 20 — post-202 live acceptance

**Deployment:** #202 merged as `7c4d9f9`; main CI, frontend CI, CodeQL and
automatic backend rollout succeeded. Both Vercel commit statuses succeeded.
Backend serves revision `mediagent-backend-00173-t5q`; chat worker serves
`mediagent-chat-worker-00016-29q`. No manual deployment, migration, configuration
change or repair was performed during this recheck.

**DV-007 passes:** Elena opened Hannah's existing case
`aa904f7b-bd23-4ce2-8d14-6c98f910c297`. All six repeated patient-confirmed rows
remain: four label Different follow-up, two Current follow-up. Only the current
pair shows the October 19 answer time; no dates were inferred for older rows.
Two AI-extracted rows remain separately identified. Score remains 4 / Possible,
Awaiting review. No clinician decision changed.

**DV-008 passes:** requester switched the patient portal to Hannah. Opened answered
request `3a55f7c9-b3a4-40f1-b686-2df8fdaae479`: en-US labels identify original
symptom wording and medicine name as recorded. Temporarily switched saved locale
to es-MX: `Síntoma reportado (texto original): «nausea and stomach cramps»` and
`Medicamento (nombre registrado): ferrous sulfate.` appear. The two unchanged
`No sé` answers stay read-only with the October 19 answered date, including after
reload. Original clinical free text was not translated or modified. Restored
Hannah's original en-US preference and closed the language sheet.

**Spanish typed/mobile confirmation passes; DV-015/016 close for this path:**
Morgan's saved preference switched en-US→es-MX. In a new daily session
`day-2026-10-20`, sent clearly fictional mild nausea 2/10 with no emergency symptoms
or treatment-change request. Nora created private intake
`fedcbe69-09c5-40bd-85f9-b4244de263cb`, locale es-MX. A target-host-pinned service
read proved `confirmed_report_id=null` before confirmation. The typed Spanish
questions, source-suggestion acceptance, rating, detailed medication testimony,
`No sé` concomitant answer and `Prefiero no responder` history answer persisted.
Private answers did not become ordinary chat bubbles.

At 390×844, preview separates patient-reported/unverified product from recorded
Metformin 500 mg context; it does not add a medicine. Preview and answers survived
reload. Consent remained unchecked and confirm disabled until explicitly checked.
After authorized confirmation, patient saved state and accessible region both read
`Informe guardado para revisión del equipo clínico`, including after reload.
Document scrollWidth equalled viewport width (390px). A rapid attempted 360/430
override still reported 390 before resize settled, so **no 360/430 result is claimed**.
Viewport reset and Morgan's en-US preference restored afterward.

Confirmed report `9bf8db93-f512-494c-b02c-7437512c7047` has exactly one task:
`1d70d896-f316-4826-8d8e-d33deb8d584a`, completed, key
`confirmed_symptom:9bf8db93-f512-494c-b02c-7437512c7047`. Exactly one ADR case
exists, `b3824e74-0d78-424a-a9f5-e853b3aea399`, status draft. Elena opened that
exact case: Spanish original testimony, 2/10, patient-reported association,
Awaiting review and score 0 / Doubtful. No medication/plan/clinical decision changed.
The older duplicate-task history was preserved, not deleted or relabelled.

**DV-014 passes sampled transitions:** Elena's Today showed Rajeev Oct 20 10:00.
Selecting This week immediately showed Loading your schedule with no stale agenda,
then the correct Rajeev and Morgan Oct 22 09:00 entries. Changing All clinics to
Willow Terrace likewise hid prior clinic visits while loading, then displayed
`No visits at Willow Terrace Family Medicine match.` Failure/retained-refresh
branches retain automated regression evidence, not a forced live-failure claim.

**Bounded failure check:** metadata-only query for errors/HTTP 5xx on backend
revision `00173-t5q` returned no rows during this recheck. This does not explain
the earlier intermittent DV-006 failures. No patient text or credentials logged.

Local screenshots retained: `/private/tmp/pr202-spanish-intake-preview-390.png`
and `/private/tmp/post202-spanish-report-saved-390.png`. Physical microphone,
forced network outage, quiet 3500-second renewal, wider mobile/accessibility
matrix remain distinct next steps. Disposable-account deletion was subsequently
excluded by the requester October 20; existing safeguards remain. Hannah's label screenshot
is `/private/tmp/post202-hannah-spanish-source-labels.png`.

### October 20 — PR #205 outage, accessibility and RCA

**Scope:** requester excludes disposable-account deletion from live acceptance.
PV-001-C's answer/review/export slice is Done; keep existing privacy behavior and
automated deletion regressions. No account was deleted.

**Real outage / DV-017:** after specific requester approval, native System Settings
showed Wi-Fi off at `20:17:45.120Z`, restored on by `20:18:10.849Z` (about 26s
including UI observation). Only a clearly labelled synthetic nonclinical to-do-list
question was sent to Hannah's Nora. Browser still showed Connected/typing during
the outage, with a truthful symptom-draft load/retry error, and remained stalled
after restoration. Reload restored the saved reply once, without another send.
Read-only target-pinned evidence: turn `ce80f802-c124-494f-a0b0-4708dc9b7da2`,
attempt 1, created `20:17:29.141011Z`, completed `20:17:55.364382Z`, no failure code;
one user-message ID and one assistant-message ID. Server completed during outage.
Socket log: `chat_ws.closed`, client, code 1005, at `20:18:23.616335Z`.

**RCA and local fix:** the portal relied on socket close/error and OPEN readyState,
without offline/online handlers or a liveness check. Recovery sends on that same
socket could therefore leave a saved result invisible. #205 explicitly closes the
view/pauses reconnects offline; online re-subscribes with the current token and
never automatically resends. Existing ping/pong every 15s detects stale visible
OPEN sockets (unanswered ping closes on the next 15s tick). Hidden tabs skip health
failure checks so timer throttling does not create false disconnects. Preserve
saved messages, clinical-side-effect safeguards and the bounded retry budget.
Regression coverage includes own-message recovery/no resend, dead OPEN socket,
healthy 3500-second renewal, hidden-page throttling and existing startup/retry cases.
This fix is **local/in review, not deployed**; live outage did not pass automatic
recovery, and no contrary success is claimed.

**Intermittent-read investigation:** 20 current backend appointment/ADR/notification/
chat request rows between `20:24:59Z` and `20:27:49Z` returned 200, with latency
0.002–0.569s. Example trace `8d403880e138ef2cb755271a22c239e4` returned 200 at
`20:27:49.976657Z`, 0.171s. Metadata-only output, no bodies/tokens. The controlled
outage demonstrates why server success need not equal browser receipt. It does
**not** prove the cause of all historical DV-006 scheduling/ADR errors; retain that
distinction and the earlier notification 502 findings.

**Broader accessibility sample:** actual patient Profile/Records/Visits/Today at
360px had no horizontal overflow; all controls had accessible names (wrapped input
labels verified manually), no positive tabindex. Today agenda reminder was 40px,
and full-chat header/mic controls were 40×40: DV-019 local fix raises them to 44px,
with paired-locale agenda and chat-control tests. Chat inbox at actual 390/430px
had no overflow or undersized targets. Clinician schedule measured 819, 1024 and
1280 CSS px, no overflow or interactive targets below 24px. Caller viewport requests
were not blindly treated as actual CSS sizes. Language dialog (5 Tab steps),
notifications (12) and unsaved clinician offer (5) retained keyboard focus; Escape
closed each and returned focus to its trigger. No offer or notification read action
was submitted.

**DV-018:** Records initially announced zero while its request was loading, then
showed two actual records. Count now waits for successful loading, never describing
an unavailable read as zero. Pending and failed-read regression tests added.

**DV-020:** secondary clinician text and small sidebar counts had contrast below
4.5:1 on the relevant surfaces. Local token overrides use muted `#596980` and
rail-faint `#8797B2`; seven tests read actual CSS tokens and verify workspace/track
and rail surfaces. A sampled patient inbox text check found 36 readable text nodes
with no contrast failures. Gradient/unsupported colour cases are not certified by
that limited DOM probe; an initial CSS-lab background calculation was discarded,
not asserted as a real failure. Reduced-motion global overrides were source-checked
(`animation:none`, `transition:none`, `scroll-behavior:auto`); OS-setting emulation,
screen-reader testing and actual 200% browser zoom are not claimed.

**Live long-session check:** following reload recovery, original user-owned Hannah
Nora tab was Connected at `20:20:29Z` / 13:20:29 Pacific and left untouched. A one-time
thread follow-up (`verify-nora-quiet-socket-renewal`) is scheduled 14:25 Pacific,
after the 3500-second renewal boundary. Separate temporary tabs were used for
accessibility; no account switch or reload of the watched tab. The follow-up must
inspect state/logs before any action, then verify one harmless saved reply and note
visibility/session interruptions. Status remains **pending real elapsed-time check**,
distinct from the passing simulated timer test.

Screenshots: `/private/tmp/pr205-outage-stalled-chat.png` and
`/private/tmp/pr205-after-wifi-restored.png`. Wi-Fi restored; no other system,
service configuration, database schema or clinical decision was changed.

**Final local verification:** clean `npm ci --no-audit --no-fund` in each portal,
then `npm run lint`, `npm run typecheck`, `npm run test`, and
`npm run build -- --webpack` — patient **75 files / 825 tests**, clinician
**70 files / 627 tests**, both production builds pass with the committed
**Next.js 16.3.8**. Focused chat suite: 102; Today/Records: 62; contrast/brand: 9.
One existing patient `_options` unused-variable warning remains; existing Sentry
and workspace-root warnings remain. Initial sandbox build could not resolve
Google Fonts; retry with network access passed. An older local Next 16.3.4 install
was detected and replaced by clean lockfile installation before final checks.
No package/lockfile change was needed. `git diff --check` passes. No new backend
code or database change in this increment; prior backend evidence is not described
as a fresh rerun. DV-017–020 fixes require #205 merge/deployment and live recheck.

### Post-205 merge and delayed renewal observation

#205 merged October 20 at `20:54:59Z` as
`fb7fb33d16faffd26952caeddc2e72ae7582dcbc`. GitHub commit statuses confirm both
Vercel portal deployments succeeded; Frontend CI and both CodeQL workflows passed.
Main CI run `39496052965` failed only the clinician test
`shows a week on request and passes the clinic filter to the server`
(626/627 clinician tests passed). It awaited a heading that renders before the
schedule request finishes, then synchronously queried the not-yet-mounted radio.
Follow-up waits for the actual `This week` radio before clicking; no production
scheduling logic, timing delay or weaker assertion is introduced.

**Real-time check is inconclusive:** the one-time follow-up was scheduled for
`21:25Z` (14:25 Pacific), but the resumed inspection occurred much later; tool
clock was `2026-10-21T03:12:13Z` (October 20, 20:12 Pacific). Do not present the
scheduled trigger time as an actual observation. Original user-owned patient tab
1 was inspected before any navigation/reload/send and showed `/login` with the
original day-session return path. Temporary tab 5 separately showed
`reason=session_expired`. No greeting was submitted and no account was changed.
Screenshot: `/private/tmp/pr205-long-session-signin.png`.

Content-free backend close logs bounded to the intended observation window
`20:20:29Z`–`21:25:05Z` show client/code pairs at `20:35:17.935418Z` (1005),
`20:43:53.218473Z` (1001), `20:58:19.989292Z` (1005) and `21:18:32.435804Z`
(1005). These are service-wide metadata without per-tab attribution; temporary
tabs also existed. None establishes the watched socket's identity, renewal or
sign-out cause. An initially unbounded query included later closes and is not
used as evidence for the intended window. This is an interrupted acceptance
run, not a demonstrated renewal regression or success.

DV-017–020 fixes are now deployed. Before session expiry, a separate Records
tab showed the actual two-record count, no unnamed or sub-44px controls, and
scroll width equal to its actual 1280px viewport. This does not exercise pending
or failed network reads, nor finish the full mobile acceptance matrix. Remaining:
requester re-login; fresh timed renewal with recorded observation time; one
harmless saved reply; post-fix outage recovery; deployed full-chat/agenda target
and clinician contrast checks. Do not repeat the Mac-wide outage without fresh
specific authorization, or during an uninterrupted renewal observation.

**Follow-up verification:** clinician `npm run lint`, `npm run typecheck`,
`npm run test` pass (70 files / 627 tests); focused schedule suite passes
(28 tests). `git diff --check` passes. Only a test synchronization and evidence
documents changed; no new application bundle, auth setting or database change.
Clinician tab independently reports sign-out after two hours of inactivity;
that visible reason does not establish the separate patient session's cause.
Continuation branch: `codex/post-205-live-checks`, from merged main, rather than
adding code to an already-merged #205. Both existing user tabs are preserved;
temporary tab 5 is closed after observation.

### Fresh quiet-session baseline after requester sign-in

October 20, 21:41 Pacific (`2026-10-21T04:41:18Z` clock): patient user tab at
`/chat?session=day-2026-10-19` shows Connected, blank composer, no pending reply;
DOM visibility is `visible`, actual width/scroll width 433px. The baseline is a
new observation, not evidence that the preceding signed-out run passed. Current
browser IDs are patient 2 / clinician 1, different from the preceding inventory;
always resolve by current URL. Elena's assigned Morgan ADR review is signed in.
No send, reload, account change or clinical decision performed. Screenshot:
`/private/tmp/pr206-renewal-start.png`.

Existing one-time follow-up `verify-nora-quiet-socket-renewal` updated, not
duplicated, for October 20 at 22:45 Pacific (more than 3500 seconds after baseline).
Inspect before interaction, record actual execution time, then send one labelled
nonclinical greeting and verify one saved reply. Record hidden state, expiry,
late dispatch and lack of per-tab socket attribution rather than inferring
uninterrupted transport identity. No Wi-Fi interruption during this observation.

Deployed chat header/back/care-team/new-chat/hands-free/mic controls measured
approximately 43.99px (44px CSS subpixel rounding), send approximately 52px.
Listen's visible button is 30px but its existing `before` hit area extends 7px
above/below, giving 44px; do not incorrectly report its visible box as a new
touch-target failure. Full mobile hit-testing and agenda sampling remain.
Clinician computed muted text is `rgb(89,105,128)` with token `#596980`, confirming
the deployed contrast override, not a new all-screen contrast certification.

#206 portal CI checks/builds pass. Its PR policy failed because its initial body
omitted the required checklist. Dependency audit separately reports eight Pillow
12.3.0 advisories with fix 13.0.0; do not call CI green or suppress the audit.
That backend dependency upgrade has not been made or tested in this UI/evidence
increment. Logs: run `39537621296`, jobs `119017808667` and `119017808944`.

**CI fix follow-up:** after the requester flagged the failures, the PR body was
corrected to the required checklist, with actual verification and manual steps.
Pillow's direct constraint is now `>=13.0.0,<14.0.0`; both locks were regenerated
using CI's uv 0.9.24, universal Python 3.12 commands. The only resolved package
change is Pillow 12.3.0 → 13.0.0. Official release/security changes reviewed:
https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html . No ignore list,
gate weakening or application-code workaround was added.

With Pillow 13.0.0 installed in the existing local Python 3.13.2 backend venv,
`PYTHONPATH=src .venv/bin/python -m pytest tests/unit/services/test_document_preview_service.py tests/unit/services/document_intelligence --no-cov -q`
passes **152 tests**. CI-equivalent audit
`uvx --python 3.12 --from pip-audit==2.10.1 pip-audit -r requirements-dev.txt`
passes **No known vulnerabilities found**. Full backend/CI checks remain the
remote acceptance gate after push. No deployed service, clinical record or timed
patient tab was changed while resolving CI.

### Quiet-session acceptance — October 20 22:45 Pacific

The one-time follow-up actually started at `2026-10-21T05:45:24Z`, after its
`05:45:17Z` trigger, rather than the hours-late dispatch of the previous run.
Baseline was `04:41:18Z`: at least **3846 seconds / 64 minutes 6 seconds** elapsed
before observation. Inventory resolved the same patient URL to user tab 2.
Before any interaction, it still showed **Connected**, blank composer, no pending
reply, no visible alert; read-only DOM `visibilityState` was `visible`.
Visibility throughout the intervening hour is not independently proven. No
navigation, reload, account change or Wi-Fi interruption was performed by this
verification run before the observation.

Exactly one authorised nonclinical greeting was sent with the specified synthetic
QA wording. It progressed through typing/saved-user-message and returned:
"Hello! I am here and ready to help. Please let me know if you have any questions
about your care or health records." The original tab received it without reload,
manual retry or resend. DOM counts were one exact user message and one matching
reply. Only after observing completion, the first reload restored the same single
pair and Connected state. No medication, clinical report or plan change requested.
Screenshot: `/private/tmp/pr206-long-session-reply.png`.

Metadata-only logs identify turn `75d56b39-d67b-4b33-8e29-e2a1d704d9dd`:
worker claim `05:46:14.584503Z`, model start `05:46:15.621721Z`, complete
`05:46:27.569709Z`, finished `05:46:27.708932Z`, worker_done attempt **1** at
`05:46:27.816473Z`. The UI waited through queue/recovery polling before the reply;
this was not an instant response. No second send was used to unstick it.

Close metadata bounded to `04:41:18Z`–`05:46:00Z` shows one service-wide client
close/code 1005 at `05:38:58.870123Z`. It is consistent with a quiet renewal near
the expected boundary but has no per-tab/session identity in the selected output;
do not call it proof of an uninterrupted socket or attribute it conclusively to
this tab. The accepted result is the **real elapsed-time user journey beyond
3500 seconds and persisted single reply**, superseding the earlier inconclusive
run. The post-fix actual network-outage test and historical intermittent-read
investigation remain separate, not silently marked Done.

### Grouped closure campaign after #206

Requester scope: one PR for the remaining bounded checks, bug fixes and tracker
corrections. Physical voice is separately tracked as VOI-001-M for the requester.
Start branch `codex/grouped-deployed-acceptance` at main `c54c7b5`; working tree
was clean. #206's 37 PR checks and main CI pass; both portals deployed. No remote
migrations/configuration/deployment or clinical publication authorised here.

| Lane | Acceptance path | Evidence level / initial state |
| --- | --- | --- |
| PAT-001-A | One nonclinical turn → approved brief real outage → automatic reconnection → one saved reply, reload persistence; retry limit and legacy contract tests | Long-session already passes; post-fix outage pending; no intentional retry exhaustion against a clinical action |
| PAT-002-B | Existing private draft → unchanged consent/history across reload/offline; deterministic microphone denial/text fallback; mobile 360/390/430 layouts | Physical audio/phone acceptance remains VOI-001-M; no new clinical confirmation without exact approval |
| PAT-004 | Spanish question on selected synthetic document → correct source; unavailable/deleted/foreign source refuses without chart-wide fallback | Use isolated contract fixtures for deletion/foreign negatives; do not delete existing cited live records merely to manufacture a test |
| COM-002 | Existing attached approved activity → same draft on replay → audit/ownership/clinic checks → approved plan/reminders unchanged | Compare scoped read-only state; no draft edit/publication or revoked assignments in live shared accounts |
| SCH-001-V / OPS-005 | Repeated scope-matched schedule/timezone/export reads and bounded metadata correlation | Preserve distinction between successful journeys and unexplained historical intermittent errors |
| AUTH-002 | Two authorised clinician tabs → refresh continuity → approved sign-out in one → both signed out; MFA/idle warning tests | Real MFA re-login requires requester; simulated expiry/warning tests cannot be described as a real two-hour observation |
| Tracker cleanup | Reconcile merged/deployed #206 and observed worker attempt; keep unfinished OPS-006 phases open | No implication that one worker reply proves the entire worker/load/rollout matrix |

Requester expressly approved one ~20-second Mac-wide Wi-Fi interruption and
Elena sign-out propagation testing followed by requester re-login. Perform
sign-out last so it does not invalidate the other clinician checks. No password,
OTP, token or clinical body belongs in diagnostic output.

#### Recorded grouped outcomes

**Real outage:** first cut was observed off `2026-10-21T06:09:28.736Z`, on
`06:09:54.425Z`; turn `f86d1d10-36f9-497f-8349-21fcf7b47d3f` had already
completed at `06:09:19.459806Z`, attempt 1. It is only idle-reconnection evidence.
The requester then expressly approved one immediate-toggle repeat. Second cut:
off `06:18:41.794Z`, restored on `06:19:09.203Z`; worker claimed turn
`dfc7922d-4245-422a-a539-c599e0383e9a` at `06:18:41.303112Z`, completed at
`06:18:59.506911Z` **during the outage**, worker_done attempt 1 at `06:18:59.718334Z`.
Original tab delivered one bookshelf-answer automatically without reload/resend;
one exact prompt and one reply were counted. The subsequent first reload restored
the same pair and Connected state. Wi-Fi on verified; System Settings closed.
Screenshot: `/private/tmp/grouped-inflight-outage-pass.png`. The observed off/on
interval includes UI inspection overhead, not precisely 20 seconds. No more
Mac-wide interruption is authorised by these two specific approvals.

**PAT-004 / DV-021:** Hannah's metadata-only lab document
`b38a622d-8ee2-47b1-8666-5668b8f162e8`, focused session
`chat-787dfc96-3078-4a32-b6d4-4c5ab89109aa`, was rejected safely at begin with
`CHAT_DOCUMENT_UNAVAILABLE` (`06:15:37.281431Z`, 311ms). It did not start a general
chart answer. The composer restored the unsaved Spanish question and disabled
send, but the retained attachment hid the specific unavailable notice; only a
generic connection/action error appeared. Screenshot:
`/private/tmp/grouped-unavailable-document-before-fix.png`.
Local fix hides the invalid attachment card, always shows the existing localized
document-unavailable explanation and one explicit Dismiss, suppresses redundant
generic feedback while invalid, and clears that stale feedback on dismissal.
No automatic resend or backend rejection change. Four regressions cover both
document codes in both locales. This fix awaits review/merge/deployment.

**COM-002:** replayed the original Rajeev message
`b2ca9e36-c715-4e24-ab49-1913ab8bf815`, thread
`accc6e08-bd27-4531-97a0-168025106d62`, source item
`af9c341e-8cc8-40fc-aea3-8480829b0f31`. It reused draft
`f80fe99f-1d60-4ac2-806d-d75889b1bd3f`, focusing item
`252f3605-631d-4cd4-82b5-3de16cab2407`. Existing audit
`bbd60f04-74bf-4e6e-a76f-04a45e1695eb` stayed the sole message-review audit,
actor Elena `74225aad-52c7-4b51-be36-9500d4f0e864`. No edit, attestation or
publication. V1 still approved, V2 draft, 0/4 verified, publication disabled.
Read-only, target-pinned privileged metadata reads before/after (not an RLS proof)
returned identical approved-plan/items, medications, obligations and reminder
fingerprints. Counts: 1 approved plan, 5 approved items including removed history,
3 medications, 1 obligation, 0 reminder rows. Empty live reminders alone are not
proof: strengthened the actual full-migration-chain PostgreSQL test with one
obligation, enabled Pacific 09:00 reminder and completed adherence row; repeated
attach/review must preserve their exact complete JSON and one audit. That test
passes. Screenshot `/private/tmp/grouped-activity-draft-replay.png`.

**Scheduling/RCA:** live Today → week displayed loading before showing Rajeev
October 20 10:00 and Morgan October 22 09:00; Willow showed loading, then its
correct empty result; Show all restored those same visits. No offer/visit write.
Bounded 30-row request sample `06:17:07Z`–`06:21:55Z` for appointment/notification/
ADR reads returned all 200, 0.002–1.277 seconds. Example slow trace
`3a7fcc531201c2a2006a79bf501ad051` at `06:17:07.211235Z`, 1.2765s. This does not
meet a universal sub-0.5s claim or explain historical DV-006; do not close that
RCA on this sample. The document rejection above is a known domain outcome, not
evidence of that historical transport failure.

**Automated checks:** patient initial batch 147 tests; clinician auth batch 35;
backend service/router batches 128 + 41. Isolated PostgreSQL: conversations 45,
chat turns 47, no skips. The strengthened full-chain reminder test passes again.
New microphone-denial cases (ordinary/private × en-US/es-MX) leave typed input
usable and send no audio/user message/intake mutation. Confirmation lost-response
replay now runs in both locales, reusing exact identity/consent/preview hash and
never resubmitting merely on reload. Mocks are not physical audio evidence.

**Spanish source acceptance:** Rajeev's original lipid report
`e007ffcf-3224-4c8c-b8ed-2a9a19506561`, session
`chat-611caf56-f3bf-403b-a197-893716246e3a`, answered the single labelled
synthetic Spanish question in Spanish. It retained total cholesterol 242, LDL
164, triglycerides 201, non-HDL 204, HDL 38 and estimated average glucose 186
mg/dL from that original, not the replacement report. It cited the exact report,
page 1, warned that extracted information needs care-team review, and proposed
no treatment/plan change. One saved answer and selected context survived reload.
Saved Profile remained English, so interface controls correctly stayed English.
Screenshots: `/private/tmp/grouped-spanish-grounded-answer.png` and
`/private/tmp/grouped-spanish-actual-360.png`.

Measured viewport matrix (actual dimensions, after compensating for browser zoom):

| Width × height | Document width | Composer bottom | Verdict |
| --- | --- | --- | --- |
| 360 × 800 | 360 | 781.45 | No horizontal overflow; composer within viewport |
| 390 × 844 | 390 | 825.89 | Same |
| 430 × 889 | 430 | 870.34 | Same |

Viewport override reset. This proves chat layout, not every private intake form.
Opening Report a symptom reached its unsubmitted entry; no symptom answer or
confirmation was sent. Wider private-intake acceptance remains separate from
the measured chat screen and permission-denial/lost-response automated tests.

**COM-002 wording:** nonclinical activity attachment/status/retry and explicit
no-plan-or-reminder-change messages passed English/es-MX LLM meaning-and-safety
review under the requester's accepted expo standard. See the retained string
inventory in the feature specification. No professional validation or new clinical
translation is asserted. With live audit/replay/state comparison and isolated
authorization/nonempty-reminder preservation, this scoped task is Done.

**AUTH-002:** both clinician tabs were authenticated. The second tab's MFA page
offered Begin setup: no enrolled authenticator was demonstrated. Using the
specifically approved Logout in that tab, Elena's original care-plan tab changed
automatically to login with `reason=logged_out` and its original return path,
without reload. Rajeev's patient tab remained authenticated. Screenshot:
`/private/tmp/grouped-clinician-signout-sync.png`. Temporary clinician tab closed;
the user-owned clinician tab is left at sign-in for the requester. No MFA factor,
credential, session limit or external configuration changed. The 35-test clinician
auth suite covers aal2 preservation and inactivity warning timers, but live MFA
and actual idle-warning observation remain unperformed, not silently closed.

Requester then independently enrolled one authenticator for clinician Rajeev
Ranjan Chaurasia (not Elena). The live MFA page and a new second tab both showed
MFA enabled, one authenticator; concurrent reloads retained authenticated identity
and that status in both tabs. Screenshot `/private/tmp/grouped-mfa-two-tabs.png`.
Temporary tab closed. This proves enabled-factor persistence, not inspection of
token assurance or a freshly challenged sign-in. Requester was asked to perform
the fresh sign-out/password/TOTP sign-in directly on the site; no code requested
in chat. The earlier no-enrolled-factor observation applies only to Elena.

**Fresh MFA follow-up — October 20 (Pacific):** requester confirmed completion
of the requested sign-out/password/TOTP sign-in and supplied screenshots of the
Verify MFA challenge and subsequent authenticated MFA-enabled page for clinician
Rajeev. No code/credential was received or entered by the verifier. The original
live tab was authenticated as that clinician; a new second tab reached the same
page/identity. Concurrent reloads of both retained the authenticated identity and
one enabled authenticator, with no sign-in redirect or error. Saved proof:
`/private/tmp/grouped-fresh-mfa-reload-pass.png`; temporary tab closed. This
closes the fresh MFA sign-in and second-tab continuity acceptance using requester
challenge evidence plus observed post-login persistence, not a raw-token aal2
inspection or a deliberately forced refresh-token race. AUTH-002 now retains only
the real inactivity-warning observation; its timer/modal tests already pass.

**Final verification:** patient full suite 834 tests / 75 files; clinician full
suite 627 / 70. Both portals passed lint, typecheck and production build (patient
build preceded the final test-only locale expansion; final focused typecheck and
full suite passed afterward). Backend focused suites 128 + 41; isolated
PostgreSQL conversations 45 and chat turns 47 with no skips, followed by the
strengthened full-chain reminder test passing again. Changed Python test passes
Ruff check and format. Existing Vite, Sentry and deprecation warnings remain;
no clean-warning claim. No deployment, remote SQL or configuration changes.

Reproducible commands (run in the corresponding portal/backend directory):

```sh
npm test -- --run
npm run lint
npx tsc --noEmit
npm run build
CARE_CONVERSATION_TEST_POSTGRES_DOCKER=1 PYTHONPATH=src .venv/bin/python -m pytest tests/integration/test_care_conversation_postgres.py --no-cov -q
CHAT_TURN_TEST_POSTGRES_DOCKER=1 PYTHONPATH=src .venv/bin/python -m pytest tests/integration/test_chat_turn_postgres.py --no-cov -q
.venv/bin/ruff check tests/integration/test_care_conversation_postgres.py
.venv/bin/ruff format --check tests/integration/test_care_conversation_postgres.py
```

An extra strict mypy invocation on the standalone PostgreSQL test module is not
clean (209 errors across its existing untyped fixture/helper/test surface); this
is outside the configured source-only mypy lane and is not reported as passing.
No typing configuration was weakened to hide it.
The configured CI command, `.venv/bin/mypy src/ --ignore-missing-imports`, passes
all 278 source files. Without that existing CI option the local untyped
`google.cloud` package produces one import-stub error; no configuration change.

Delivery: [PR #207](https://github.com/sjsu-masters-projects/medi-agent/pull/207),
initial commit `e2bc42c`; no merge/deployment performed. Continue its explicit
remaining checks rather than reopening already accepted recovery/review slices.

**Closure boundaries:** PAT-001-A and COM-002 Done; PAT-004 awaits deployment and
live DV-021 correction recheck. PAT-002-B retains wider private-intake UI checks;
VOI-001-M owns physical voice. AUTH-002 retains enrolled-MFA/real-idle observation.
SCH-001-V successful scoped transitions do not explain OPS-005 historical
intermittent failures; bounded logs found no reproduced transport failure.

## Post-208 grouped acceptance

Scope: REC-001/002, NOT-003, MED-001, CLN-001/002. Contract:
[workflow completion](../.agent/specs/expo-workflow-completion.md).
Branch `codex/post-208-acceptance` starts from merged main `f235c278`.
Formal model/provider evaluation is optional; synthetic functional verification,
approval boundaries and automated safety/access tests remain required.

### Release baseline and authority

October 21: #208 merged/closed. Main CI Pipeline, Frontend CI and backend deployment
report success. Backend `mediagent-backend-00177-xgh` serves 100% traffic. Refreshed
deployed patient and clinician tabs are synthetic Rajeev and Elena; no sign-in or
credential transfer was needed. Patient Today is 0/4; clinician Profile retains
three active medicines (atorvastatin, lisinopril 20 mg daily, metformin), the glucose
activity and unconfigured reminders. These are observed UI values, not DB hashes.

The initial read-only Supabase check found 079 absent. After explicit requester
approval, only the reviewed 079 file and its receipt were committed in one
transaction under advisory lock 726340181. Ledger application time:
**2026-10-22 03:40:37.892769 UTC** (October 21 Pacific). Verified SHA-256:
`6b781b77e48d41f618d131d33fd0a710af5cd585a6172fdd42eb56bee92a947e`.
Independent read-only checks returned `trigger=true`, `function=true`,
`all_rls=true`, `browser_access_denied=true`. An intermediate verification query
failed because replacing Monaco's visible textarea left old SQL in the editor;
the successful receipt predates that failed read. A fresh query buffer completed
the permission checks. No second migration application or other schema change.
No backfill, clinical approval, account deletion or configuration change is included.

### Grouped acceptance matrix

| Group / tasks | Acceptance path | Current result / next action |
| --- | --- | --- |
| Release / all six rows | Merge → serving code → reviewed migration identity | Main/deployment success; Timeline visible; only 079 applied with explicit approval, matching receipt and independent security checks above. |
| Records / REC-001/002, MED-001 | Original/source titles → candidate/local comparison → explicit approved decision → reload/provenance | Authorized Keep existing saved on Rajeev's imported Lisinopril 10 mg tablet with the exact approved synthetic note. Reload retains Approved / Kept Existing. Pending 39→38, approved 0→1; shared inbox 386→385 and Rajeev 39→38. Profile retains all three medicines, Lisinopril 20 mg daily, morning glucose activity and unconfigured reminders; Today remains 0/4. Other lifecycle decisions not exercised live. |
| Product concern / MED-001, CLN-001 | New explicitly confirmed unlisted concern → assigned alert → exact report → audited acknowledge | Await 079 and separate approval of exact synthetic report/confirmation. No medication/ADR/plan changes allowed by acknowledgement. |
| Notifications / NOT-003 | Count/list → single/read-through action → reload; unrelated items unchanged | Patient single read 12→11, then displayed-read 11→0; clinician loaded-read 42→0, all retained after reload. Elena's 40 action items remain unchanged. No source review/approval. Expired-cursor recovery remains unforced live; signing isolation is covered separately by the passing automated tests, not inferred from counts. |
| Shared inbox / CLN-001 | Exact candidate counts → correct patient/source → scoped refresh; second reviewer/access boundary | Exact source counts update after the saved decision. Willow Terrace filter clears old rows and returns a genuine zero for one assigned patient; All clinics restores scoped work. Maya's 200-candidate capture-time limit is explicit. Existing PostgreSQL/PostgREST access contracts retained; second actor live acceptance and acknowledgement remain. |
| Timeline / CLN-002 | Actual source dates/coverage → exact disclosure/destination → reload/keyboard/narrow layout | All 12 buckets available, truthful zero rows, no source failure. New reconciled audit event visible after navigation; exact source link focuses its DETAILS ID and exposes only recorded event type. Coverage expands using Enter; refresh succeeds. At measured 423 CSS px, document content width is also 423, no horizontal overflow. Elena's own private-thread links observed; different-actor isolation remains automated, not asserted as a live second-actor test. |
| Risk / CLN-002 | Versioned factors → actual source dates → unknown/unavailable disclosure | Rajeev explanation exposes rule version outpatient-review-priority-v1, calculation time and actual adherence/medication dates. Missing rated symptoms/open ADR dates explicitly Unknown; recorded-response denominator and non-atomic/current-source limits shown. No risk thresholds or diagnosis changes. |

REC-002 audit query returned exactly `matching_saved_decisions=1`,
`matching_audits=1`, `nonempty_mutation_snapshots=0`. Actor equality was checked
between the immutable decision and its audit event. This proves saved attribution,
not that every lifecycle decision was exercised live. The prior 44 PostgreSQL
cases retain lifecycle/retry/access/reminder coverage. REC-002's agreed deployed
decision/reload/provenance path is complete; other tasks retain their own gaps.

### Reproduced presentation defects in this follow-up

- **DV-022:** imported-fact detail count displayed the old filter's total while
  loading (including 38 pending under the newly selected Approved heading).
  Initial loading/failure could also imply zero. Fix shows loading/unavailable
  explicitly and uses singular/plural for confirmed counts.
- **DV-023:** async reconciliation preview could capture BODY as its focus-return
  target after the opener was disabled. Escape lost keyboard position. Fix keeps
  an explicit opener reference; no clinical decision handler changes.
- **DV-024:** English clinician reference lookup showed Spanish before English.
  Fix orders the same bounded, validated references English first, retaining
  Spanish wording, source dates and provenance; no new lookup or chart write.

Local fixes require review/merge/deployment before any live-correction claim.
Reference lookup itself passed: lisinopril ingredient 29046, official English/
Spanish MedlinePlus and DailyMed references with source/check/cache dates and
explicit unchecked clinical coverage. No automatic canonical-field application.
Evidence screenshots: `/private/tmp/post208-migration079-verified.png`,
`/private/tmp/post208-keep-existing-persisted.png`,
`/private/tmp/post208-reconciliation-audit.png`,
`/private/tmp/post208-medication-comparison.png`.

### Follow-up verification and continuation

Commands run against this follow-up branch:

- Clinician `npm test -- --run`: **680 passed, 76 files** (includes async focus,
  initial failure/genuine zero and filter-loading count regressions).
- Clinician `npm run lint`, `npx tsc --noEmit`: pass.
- Clinician `npm run build -- --webpack`: pass. Existing Sentry deprecations and
  workspace-lockfile warnings remain; no CI build configuration changed.
- Backend `.venv/bin/python -m pytest tests/unit/services/test_medication_reference_service.py --no-cov -q`:
  **30 passed**; English-first reference ordering preserves Spanish provenance.
- Backend notification token/service/presentation and patient-timeline unit suites:
  **197 passed**. No new live signing-key rotation was performed.
- Backend `.venv/bin/ruff check src/app/services/medication_reference_service.py tests/unit/services/test_medication_reference_service.py`
  and `.venv/bin/mypy src/ --ignore-missing-imports`: pass (283 source files).
- `git diff --check`: pass.

No new report was submitted: exact synthetic unlisted-product report plus alert
acknowledgement authorization was requested separately and has not yet arrived.
Remaining: that approved journey, REC-001 correction/source lifecycle UI checks,
live stale-cursor recovery and second-reviewer/access acceptance. DV-022–024 need
follow-up PR review/merge/deployment and live correction checks. No other remote
migration/configuration, clinical changes, deployment or merge performed.

### Tracker reconciliation

#208 rows move from In review to Verify deployed, not automatically Done.
EVA-001 becomes optional P3 research; AI-004's shipped prompt-review slice no longer
depends on a formal campaign. Runtime acceptance remains in AI-006/SAFE-002.
PAT-002-C is Ready because confirmed intake is implemented; its patient history
and full clinician report workflow are not delivered by a generic source timeline.
CON-001 reuses the merged timeline, retaining handoff/export scope. CI-001 is
already enforced in code: its old canary prerequisite is retired, with narrow-PR
selection evidence still needing reconciliation. No CI/runtime safety gate changed.
