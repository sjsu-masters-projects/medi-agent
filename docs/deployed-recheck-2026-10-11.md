# Deployed portal recheck — October 11–18, 2026

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
| 2 | ADR information loop and MedWatch workspace | PV-001-B, PV-001-C, PV-002, UX-005 | Use an existing synthetic ADR assessment so the known symptom-intake outage is not mistaken for this feature. Verify patient request and answer in en-US and es-MX, clinician evidence attribution/rescore and answered-history alert, patient-record ADR tab, 390 px Form 3500 step navigation, old `/medwatch?assessment=` redirect, draft/edit/approval/preview/PDF and the supported discard or external-submission-record state. Reload after every authoritative transition. Never submit anything to FDA. | en-US Hannah answer → clinician evidence and alert passed October 18; es-MX, deletion and the remaining Form 3500 state transitions still pending. |
| 3 | Canonical appointment loop | SCH-001-V | Use Rajeev's existing future offers to avoid creating a third. With action-time approval, respond to exactly one offer; verify the persisted visit, notifications, responsible clinic/clinician, timezone, reload behavior and one-time calendar download in both portals. Verify clinician cancel/complete/no-show controls separately without conflating them with a patient response. | Two offers observed; response awaiting approval. |
| 4 | English-first review of Spanish content | LOC-003 | Open Spanish-origin facts, care-plan wording and a Spanish care-team message as the clinician. Confirm English presentation is labelled as translation, original evidence remains available, failed guards never display unsafe translation, message reads do not block, and the patient receives only wording that passed the existing review gate. Record incomplete follow-up scope separately rather than calling it shipped. | Planned. |
| 5 | Scheduled bilingual knowledge refresh | OPS-004 | Read the October 18 weekly job/run record and verify the three formerly one-language synthetic conditions now have both en-US and es-MX cache rows, with `subjects_new_locales` reported. Use an authorized manual run only if the scheduled run did not occur. | Planned; read-only cloud/database access may be needed. |
| 6 | SMART hand-off and AI safety behavior | INT-003-V, AI-004 | Continue the standalone SMART sandbox flow past patient login and consent to the deployed import review hand-off, preserving provenance. Separately run bounded synthetic Nora checks for emergency guidance/clinician alert, general wellness, mild symptoms, low mood and bilingual behavior; record final responses and saved side effects without claiming clinical validation. | Planned; sandbox credentials/consent and chat mutation need user participation or confirmation. |

### Task verdicts

| Task | Current verdict | Evidence / blocker |
| --- | --- | --- |
| PAT-005-L | Pass | Elena, Review Queue → Rajeev's byte-identical lipid/A1c copy → exact [Documents anchor](https://clinician.mediagent.live/patients/c102f321-a2b6-40e4-95f4-f21390b18e57?tab=documents#document-f13a4d58-799c-4d02-b529-eef2d7a3f0f1). Both clinician surfaces say “Duplicate upload — extraction skipped”; Documents explains the copy created no new facts or proposals, while upload review is separate. Signed in as Rajeev, [patient Records](https://app.mediagent.live/records) lists “Lipid Panel A1c copy” as “Duplicate upload.” Its detail sheet says the exact contents were already processed, the copy is stored, and no new facts or care-plan instructions were created; it does not present an empty-facts review. Expanding Source document displayed a one-page original preview and a Download original link. At measured 390 CSS px, the detail sheet and page each fit (`scrollWidth = innerWidth = 390`). This is the existing October 14 byte-identical synthetic copy; no new upload, review or deletion occurred. |
| PV-001-B | Partial pass | With the requester's action-time approval, signed-in synthetic Hannah answered “I’m not sure” to both safe retrospective questions on the deployed en-US form, reviewed and confirmed them, then sent. The patient saw “Your answers were sent,” Today no longer showed a waiting request, and after reopening `/chat?view=follow-up&request=523d8a8a-5bff-422d-a0f6-2b821b13e97a`, History showed both saved answers and “Answered.” Elena's exact [ADR case](https://clinician.mediagent.live/adr-reviews/aa904f7b-bd23-4ce2-8d14-6c98f910c297) gained dated, patient-confirmed dose-response and previous-reaction evidence; the deterministic score remained 4 / Possible, as expected for unknown answers. Prior score/classification and clinician decision controls remained intact. The new evidence appears alongside older identical unknown entries (DV-007). Switching Hannah's saved language to es-MX re-rendered the answered request, date and answers in Spanish (`No sé`) without changing the stored outcome; her original en-US setting was restored. Database audit read and submitting a fresh request in Spanish remain. |
| PV-001-C | Partial pass | Hannah's en-US answer created one “Patient answered medication-safety follow-up” notification in clinician Alerts → History, naming Hannah, saying it is not a clinical decision, and linking through `/medwatch?assessment=aa904f7b-bd23-4ce2-8d14-6c98f910c297` to her exact ADR case. The patient request moved from pending to answered, and History persisted after navigation/reload. Maya's reviewed case retains patient-confirmed rechallenge, dose-response and prior-reaction answers, score 6, and the review note. Spanish, patient deletion and broader visual/accessibility checks remain. |
| SCH-001-V | Partial pass; intermittent failures | Elena `/appointments` initially said “Could not load your schedule” on load and Retry, leaving New offer disabled. Later, the same deployed screen loaded: New offer form, clinic picker, Needs action counts, two existing Rajeev offers and Morgan's confirmed October 22 visit all appeared. An opened Rajeev offer showed two selectable times, expiry, responsible clinic and Pacific timezone; no offer was created or answered. Morgan `/visits` initially failed, later loaded after Retry, then failed again; it showed UTC despite Profile's saved Pacific Time. Add to calendar on her confirmed visit said “Could not download this appointment.” See DV-001–003. The full offer → patient response → persisted visit journey remains unverified. |
| LOC-003 | Partial pass; one wording defect | Elena, Morgan's approved V5 Care Plan: English-first view and Spanish wording are present. Hydration cites its Spanish source. Metformin says “Source: Spanish document” / “Translated from Spanish” while its sole visible source is an English Metformin order (DV-004). In Messages, Morgan's Spanish note shows the original plus labelled English translation. Other guards and translation failure paths remain untested. |
| OPS-004 | Pass | Staging SQL Editor, scheduler run `2026-10-18 10:02:08–10:02:52 UTC`: success, `subjects_new_locales=2`, `subjects_checked=35`, `subjects_failed=0`, `subjects_deferred=0`. A read-only join of active `conditions` to MedlinePlus `health_knowledge` returned zero names with fewer than two cached locales. The one remaining historical one-language cache key, `diabetes tipo 2` (`es-MX:found`), has no active condition row, so the active-condition requirement is met. No manual run was needed. |
| PV-002 | Partial pass | Elena's Maya report `MP-UMZS` is approved for export, says “Not submitted to FDA,” links to the reviewed ADR case, and exposes the four Complete → Preview → Approve → Download steps. At the Preview step, its link yielded a valid eight-page, AES-256 encrypted PDF 1.7 Form FDA 3500; the first page rendered with synthetic data and a “DRAFT — Not for submission” watermark. Draft editing, a new approval, submission-record action and Acrobat/Preview compatibility remain untested. |
| UX-005 | Partial pass | Maya's patient-record ADR tab lists three cases with score/status and links. `/medwatch?assessment=e4c2daa4-0ac6-475a-9171-2bb8685365ed` redirected to that exact ADR case. At a measured 390 CSS px, the MedWatch detail had no horizontal overflow; the mobile step buttons navigated Download → Approve → Preview and stayed within the viewport. The Preview step had an embedded iframe and “Open in new tab” link; the PDF downloaded and rendered via Poppler, but the in-app browser's embedded PDF area appeared blank, so viewer-specific display still needs a Chrome/phone check (DV-005). At a narrower measured 312 CSS px, the Next button extended to x=323 and clipped; 312 px is below the 390 px acceptance viewport. |
| INT-003-V | Not run | Requires the public sandbox login/consent hand-off. |
| AI-004 | Not run | Use bounded synthetic prompts and record final responses plus server-owned outcomes. |

### Defect log

| ID | Task | Severity | Observed | Expected | Status / follow-up |
| --- | --- | --- | --- | --- | --- |
| DV-001 | SCH-001-V | High | Elena at `/appointments`, All clinics: initial load and Retry both showed “Could not load your schedule”; New offer was disabled. Later the same screen loaded and New offer, two Rajeev awaiting replies and Morgan's confirmed visit were usable. | Schedule and roster load consistently so a synthetic offer can be created. | Open as intermittent; Cloud Run request logs show HTTP 200 for appointments/schedule and roster reads during the failure window, which does not prove the frontend could use the response. Exact failure not yet isolated. |
| DV-002 | SCH-001-V | High | Morgan at `/visits`: initial load says “Could not load your visits”; Retry once displayed visits. Visits showed “Your saved timezone is unavailable. Times are shown in UTC,” although `/profile` showed “Pacific Time · Los Angeles.” Later return to Visits again failed. | The saved timezone and visits load consistently, with times rendered in Pacific Time. | Open; do not treat a UTC display as a valid timezone acceptance result. |
| DV-003 | SCH-001-V | Medium | Morgan's confirmed October 22, 2026 visit showed “Could not download this appointment” after Add to calendar; no download event occurred. | A one-time calendar file downloads for an eligible confirmed visit. | Open; Cloud Run request logs show HTTP 200 for the calendar request, so inspect browser response handling rather than presuming a backend 5xx. Retry after visit/timezone service is healthy. |
| DV-004 | LOC-003 | Medium | Morgan V5 Care Plan → Metformin item labels the source “Spanish document” and “Translated from Spanish,” but Source excerpts and confidence shows only English text from `Morgan-Ellis_Metformin-Medication-Order_2026-10-02.pdf` page 1. | Translation/source labels accurately describe the item provenance. | Open; investigate whether review metadata or UI wording is wrong before changing historical approval data. |
| DV-005 | UX-005 | Low; browser-specific | At measured 390 CSS px, MedWatch Preview's embedded PDF area was blank in the Codex in-app browser although its “Open in new tab” link returned a valid, renderable eight-page PDF. | The embedded preview shows the document or a helpful fallback in supported browsers. | Open; compare in Chrome/mobile before attributing this to application code. The 390 px stepper itself passed. |
| DV-006 | Cross-portal; SCH-001-V, PV-001-B/C | High; intermittent | During this run, clinician Schedule, ADR case and Alerts, plus patient Visits, Profile, Chat and ADR follow-up alternated between an error/indefinite loading state and successful content on retry/navigation. For example, Hannah's follow-up and Elena's ADR case failed after reload, then showed the persisted answer on later navigation. Clinician console recorded a Next.js RSC `Failed to fetch` fallback. Cloud Run request logs included successful HTTP 200 GETs for the same follow-up, ADR case, profile, schedule and calendar endpoints; OPTIONS-only bursts were also present. These status codes do not prove the browser received or accepted the responses. | Stable reads and clear retry rather than stranded loading or misleading empty states. | Open; reproduce in Chrome/phone, inspect browser network/CORS/auth-refresh behavior and backend response bodies without logging patient text. Do not infer a single root cause from HTTP status alone. |
| DV-007 | PV-001-B | Medium; presentation | After Hannah's new two “do not know” answers, her clinician ADR case lists dose-response and similar previous reaction twice each as “Patient-confirmed”: older entries plus new entries marked “Answered” with a time. | Distinguish historical from latest evidence, or collapse identical answers without losing provenance. | Open as a usability/provenance review; do not delete historical clinical evidence to hide the duplication. |
| DV-008 | PV-001-C; localization | Low; copy | With Hannah's saved locale es-MX, an answered ADR request rendered its controls, answers and date in Spanish, but the heading read “Unas preguntas sobre nausea and stomach cramps” and the detail said “Reportado con ferrous sulfate.” The symptom is English source text; medication identity intentionally remains untranslated. | Clearly distinguish original patient-reported symptom text from translated interface copy, without inventing a clinical translation. | Open as copy/label review; do not translate free-text medical evidence automatically. |
| DV-009 | Migration ledger | Medium; schema provenance | A read-only hosted-ledger query found `076_care_conversation_activity_review.sql` applied on October 19, but also `071_confirmed_symptom_handoff.sql` applied on October 18. The latter filename is not among current main's 89 local migration files, which include `071_clinician_visit_management.sql`. | Every hosted applied filename and checksum should be accounted for in the canonical migration history or an explicit exception record. | Open; compare the applied 071 migration's origin and checksum before any corrective action. Do not rename or replay an applied migration based solely on its numeric prefix. |
