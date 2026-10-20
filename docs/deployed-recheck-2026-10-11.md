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
| DV-007 | PV-001-B | Medium; presentation | After Hannah's new two “do not know” answers, her clinician ADR case lists dose-response and similar previous reaction twice each as “Patient-confirmed”: older entries plus new entries marked “Answered” with a time. | Distinguish historical from latest evidence, or collapse identical answers without losing provenance. | Fixed locally in PR #202, deployed recheck pending. Live Hannah duplicate rows reproduced October 19. Every row remains; patient evidence now identifies Current follow-up, Different follow-up, Recorded follow-up or missing request metadata. Dates stay scoped to exact request matches; no inferred chronology or scoring change. |
| DV-008 | PV-001-C; localization | Low; copy | With Hannah's saved locale es-MX, an answered ADR request rendered its controls, answers and date in Spanish, but the heading read “Unas preguntas sobre nausea and stomach cramps” and the detail said “Reportado con ferrous sulfate.” The symptom is English source text; medication identity intentionally remains untranslated. | Clearly distinguish original patient-reported symptom text from translated interface copy, without inventing a clinical translation. | Fixed locally in PR #202, deployed/bilingual review pending. Headings label quoted symptom text as original wording and medication names as recorded in both locales, without translating clinical free text. New es-MX copy is listed as a draft in the PV-001-C requirements. |
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
| SCH-001-V Morgan | Elena's week agenda and exact visit detail loaded Morgan's October 22 09:00 Pacific visit. The clinician download `appointment-1fbcc232-3f71-41ca-af04-c14156d3cc39.ics` succeeded: `DTSTART:20261022T160000Z`, `DTEND:20261022T163000Z`, confirmed/private. | This narrows DV-003 but does not close the intermittent **patient-side** export/timezone/load failures; Morgan patient login still needed. |
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
