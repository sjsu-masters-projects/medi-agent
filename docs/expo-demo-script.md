# Expo demonstration run sheet

Status: presentation package prepared; account selection, baseline creation and
rehearsal are not claimed. Use only fictional accounts and synthetic documents.

## The story, in one sentence

A patient and their care teams turn source records into reviewed actions, then
follow the patient's response without treating a generated answer as clinical authority.

## Before presenting

Fill in this run card privately, without passwords or tokens. Display names must
be fictional. Do not put real health information into the portal.

| Field | Presenter supplies |
| --- | --- |
| Patient / clinician / clinic | Fictional names and the intended active assignment |
| Second clinician / clinic, if used | Separate account and its own assignment |
| Synthetic source | Filename, record type and a verified source page |
| Approved baseline | Plan/version, activity and its source |
| Prepared follow-up | Existing synthetic symptom report and review state |
| Visit | An existing valid future offer or visit and its saved time zone |
| Handoff, if used | Existing author, version and draft/approval state |
| Recording | Local approved fallback recording and its capture date |

Confirm the selected account has no unrelated real information. Sign into both
portals before the session and keep MFA codes off screen. Use the patient app at
a mobile width and the clinician portal at a readable desktop width. Zoom is
allowed; never hide warnings to make a screen appear more polished.

Use the prepared historical baseline for high-risk or slow operations. A run
sheet is not permission to create accounts, seed/reset data, publish a clinical
plan, confirm a visit or submit a report in a shared environment. Agree on the
small live synthetic actions before the rehearsal and use normal application APIs.

## Main route: about eight minutes

| Time | Screen and presenter action | Explain and show | Boundary |
| --- | --- | --- | --- |
| 0:00 | Patient Today, then clinician patient record | One patient mobile experience, one clinician desktop workspace; each uses a signed-in role | Synthetic demonstration, not professional clinical validation |
| 0:45 | Patient Records and clinician External records review | Original source beside the mapped candidate, identifier metadata and review status | An import creates evidence/candidates, not approved medications |
| 1:45 | Clinician Care plans, existing approved version and separate draft | Source page, English/Spanish wording, blockers and approval history | Review and explicit publication are required; opening a draft changes nothing |
| 2:45 | Patient Today and plan details | The approved activity, recording care team and existing completion/history | Do not create a new completion just to animate progress; name whether history was prepared |
| 3:30 | Patient Nora, one agreed nonclinical question | Distinct assistant label, streaming reply, saved history and source context where present | Not a clinician; no treatment change from a reply |
| 4:30 | Patient confirmed symptom history and clinician report detail | What the patient confirmed, recorded events, source/consent, independent team review | A chat message or symptom alone is not a confirmed ADR |
| 5:30 | Private care-team Chat and clinician Alerts | Actual recipient/clinic, saved conversation and exact destination | Human message is distinct from Nora; read does not mean a task is resolved |
| 6:15 | Patient Visits and clinician schedule | Matching saved visit time/zone and one-time calendar copy | Choose a time only if that synthetic write was agreed; calendar changes do not sync |
| 7:00 | Clinician approved handoff or clinical-core FHIR download | Approved handoff version/source links; or canonical subset with current visibility | These are different exports. Neither transmits to an EHR or regulator |
| 7:45 | Close with the limitations brief | Identify what was live, what was prepared and any failed/skipped segment | Do not turn a successful software path into a medical-accuracy claim |

## Optional branches: choose at most one

- **Two care teams:** show existing separately owned plans, owner labels in Today
  and a prepared conflict. A clinician leaving does not authorize silent medication
  withdrawal. Use the recording team's normal adoption/retirement flow only with
  separately agreed synthetic writes.
- **Spanish:** switch the synthetic patient's display preference, inspect reviewed
  wording and restore the original preference if the rehearsal plan requires it.
  Human messages remain as written. Interface drafts are listed in the
  [Spanish review pack](spanish-draft-review-pack.md), not approved by this script.
- **SMART sandbox:** use an already recorded launch/import for the short route.
  A live standalone login and consent is an external dependency and must be
  rehearsed and authorized independently. FHIR export does not establish full
  R4 or SMART certification.
- **Voice:** use only after the presenter has checked the actual device/browser,
  microphone, playback and text fallback. Otherwise stay with typed input; a mocked
  transport test is not evidence of working microphone capture.
- **ADR/MedWatch:** show an existing synthetic review and draft/preview/export.
  No FDA transmission or external-submission recording is part of this project.

## What to record after rehearsal

Record date, application revision, fictional account labels, device/browser,
which actions were live, expected versus observed state, and any interruptions.
Link evidence into the task board rather than copying another status tracker here.
Keep the recording free of credentials, MFA challenges and real personal data.

If a segment fails, follow [recovery notes](expo-recovery.md). Explain the failure
and use the dated recording; never insert a fake result, bypass approval or keep
resending an action whose saved state is uncertain.

Related: [environment setup and reset boundaries](demo-environment.md),
[academic limitations brief](project-limitations.md),
[architecture](../.agent/ARCHITECTURE.md).
