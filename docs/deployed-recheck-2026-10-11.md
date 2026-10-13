# Deployed portal recheck — October 11–12, 2026

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
  Supabase cleared the recovery token. The email itself was checked by the requester,
  not inspected here.
