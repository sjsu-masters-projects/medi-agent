# Deployed portal recheck — October 11, 2026

Synthetic Morgan Ellis (patient, `app.mediagent.live`) and Elena Park (clinician,
`clinician.mediagent.live`) only, on main `8b93b48` (#149) as deployed. The requester
signed in to both accounts; the checks below were run in a browser against the
production deployment. This is prototype acceptance evidence, not a clinical,
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

- PAT-005-L duplicate fixture: no byte-identical duplicate upload exists in Morgan's
  records any more, so the skipped-duplicate display could not be observed without a
  new upload.
- LOC-001 approval of a new bilingual draft on the deployed clinician portal: no draft
  was pending, and no clinical publication was performed.
- Scheduled jobs: covered by OPS-003 after its deployment.

## Follow-up checks after #151 (evening)

- Scheduled jobs: the requester resumed reminder dispatch and deleted the paused nightly
  ADR scan trigger. The 21:15 UTC reminder run logged `scheduled_job.finished` (INFO,
  success, first-run window, 3 schedules skipped for inactive targets, nothing due). A
  document ingestion run and a manual weekly-refresh execution also logged success; the
  refresh seeded 13 documented conditions and updated 10 subjects, next due October 17.
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
