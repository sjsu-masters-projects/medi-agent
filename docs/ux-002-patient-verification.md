# UX-002 — Patient screen acceptance

Scope: second PR in Foundation → Patient screens → Clinician screens. Foundation
#142 is merged. This slice replaces patient presentation, not application logic.
Requirements and both approved references are linked from
[the specification](../.agent/specs/ux-002-reference-redesign.md) and
[the task board](../.agent/TASKS.md).

## Implemented presentation

- Today: real progress segments, first eligible task, activity icons, compact
  schedule rows, full clinical instructions and accessible plan/barrier sheets.
  Completion feedback waits for a confirmed save; failed/uncertain saves do not
  animate, and reduced motion skips the transition.
- Records: document-type rows, date groups, detail sheet, unchanged source and
  duplicate/processing explanations. Long names do not push close controls away.
- Chat: separate Nora and actual human recipients, full-height threads, growing
  composer and safe-area clearance. Nora retains Enter-to-send; Shift+Enter and
  composition do not submit. Symptoms and Today ordinary clicks open Nora directly.
- Profile: identity card, grouped settings, edit/language/join sheets and existing
  care-team/account actions. Pending profile saves cannot be dismissed.
- Visits, reminders, onboarding and guest entry: matching compact surfaces and
  controls. Existing refresh buttons remain beside optional pull-to-refresh.
- Bottom navigation: consistent active indicator, 44px touch targets and hidden
  navigation only inside an open conversation.

## Checks recorded October 10, 2026

Commands run independently inside each app:

| Command | Patient | Clinician regression |
| --- | --- | --- |
| `npm run lint` | Pass | Pass |
| `npm run typecheck` | Pass | Pass |
| `npm test -- --reporter=dot` | 420 passed, 49 files | 262 passed, 39 files |
| `npm run build -- --webpack` | Pass after final reviewer fixes | Pass |

`git diff --check` passed. Existing Sentry configuration/deprecation, PDF.js Node
legacy-build and occasional shared clinician-test `act` warnings remain visible;
none failed these checks. Sandbox builds cannot download the existing Google
fonts; network-enabled builds passed. No dependency or monitoring changes were
added to this visual slice.

Read-only lane review found direct-Nora navigation and keyboard submission
regressions; both were fixed with focused tests. Records/Visits/Reminders/Symptoms/
Onboarding review otherwise found preserved API payloads, actions and locale paths
(102 focused tests passed). No backend, migration, service, Redux or API-contract
files are changed by this slice.

Guest browser checks at 360px: Spanish signup and login render; signup has no
horizontal overflow, password buttons are 44×44px, submit is 54px high and document
language is es-MX. Navigation initially hydrates guest preference; it is not a
clinical translation operation.

The subsequent fidelity pass verified the warm-sand entry canvas, reference teal
glow, inset native-language chevron, 52px inputs and 54px submit control. Spanish
entry at 360px and English signup at 430px had document widths matching their
viewports (no horizontal overflow). Shared native selects reserve caret space;
high-contrast mode retains the platform caret. Header actions wrap rather than
squeezing titles; buttons constrain long labels. Profile/Records and Chat lane
reviews removed duplicate interface copy without removing handlers or safety text.
Clearer nonclinical entry/settings wording was explicitly approved by the requester.

PR review follow-up removed a redundant `loading` predicate inside the already
loaded inbox branch. Opening/sending refresh guards remain unchanged. Targeted
ESLint, patient typecheck and 32 conversation/pull-to-refresh tests passed.

## Still required before visual acceptance

- Authenticated screenshots and interaction checks for Today, Records, Nora,
  human conversations, Visits, Profile and reminders at 360/430px in both locales.
- Confirm portrait safe areas, keyboard composer clearance, reduced motion and
  long clinical text using real synthetic account data.
- Confirm upload, completion/barriers, reply, appointment response and saved
  language through the preview. Do not treat component tests as deployed proof.
- Final CI and requester comparison against references. Clinician screen redesign
  remains the third PR, including the new Clinic Settings reference.

Patient changes are in [draft PR #143](https://github.com/sjsu-masters-projects/medi-agent/pull/143).
The local compiled preview uses the fallback `http://localhost:8000`; a read-only
health request could not connect. Authenticated checks need a configured, reachable
backend or the PR's deployed preview. No authentication code was changed to bypass
this environment limitation.

Live portals were signed out when inspected. No auth bypass, invented runtime
records, remote publication, migration, deployment or merge was performed.
