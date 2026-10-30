# Portal UI, content and language review: October 10, 2026

## Scope and acceptance

UX-001 polishes the existing synthetic master's-project workflows. It does not
certify production readiness, change clinical truth, deploy, migrate, merge or
approve a care plan. The acceptance path is readable patient tasks and clinician
review, appropriate information density, honest states, accessible controls,
responsive layouts and one persisted patient interface language.

## Information hierarchy

- Patient first: the activity, complete reviewed instruction, status and action.
  Display a reminder time once. Suppress only identical repeated instruction
  text, never a distinct dose, frequency or instruction.
- Clinician first: patient identity, current approved/draft distinction, blockers,
  source-review action, editable wording and publication requirements. Keep
  supporting excerpts, document inventory and retained summaries expandable.
  Expanded evidence must retain visible filenames and page references.
- Keep actual sender, clinic and selected recipient in human conversations.
  Nora stays clearly identified as AI. Operational alerts are not human replies.
- Do not turn unknown response history into missed doses. Extraction confidence
  is not medical certainty. Parsing, upload review, fact reconciliation and plan
  approval remain different actions.
- Internal IDs, parser versions and model names are not primary clinical content.
  Keep necessary audit metadata in supporting disclosures. Clinical names must
  never be inferred to be dates merely because they contain numbers.
- Remove invented symptom history and unconnected Save controls. Until a patient
  symptom-history API is connected, explicitly explain the limitation and link
  to the existing Nora reporting workflow.
  Today opens Nora directly rather than routing through an unnecessary timeline.
  Existing symptom links still open a compact, patient-branded reporting handoff;
  history limitations are in a disclosure rather than a second oversized panel.

## Language decision

Patient interface language is the saved `preferred_language` (`en-US` or `es-MX`),
shared by navigation, Today, Records, Reminders, Visits, Profile and chat controls.
The global selector persists through the existing authenticated profile endpoint;
failure leaves the prior preference unchanged. Entry screens have a separate
guest choice before a profile exists. Chat no longer owns a competing preference.

Clinician controls remain English. Superseded by
[LOC-001](../features/language.md): care-plan wording is
approved in English and Spanish together, so a language switch changes Today and
Reminders without new review. Historical messages keep the language they were written
in, and older single-language records are labelled with their language. The language
control explains this.

## Review coverage

| Surface | Review method |
| --- | --- |
| Patient Today, Records, Profile, Reminders, Visits, Nora/human chat, Symptoms | Live synthetic account inspection plus source/test review |
| Patient login, signup, onboarding | Source/test review; local sign-in visual inspection |
| Clinician dashboard, roster, all eight patient tabs, appointments, upload review queue, messages, ADR queue, settings | Live synthetic inspection plus source/test review |
| Clinician upload, login/signup/setup/admin signup, MFA, standalone import | Source/shared-layout and focused regression review; not live credential changes |

Four parallel workstream reviews were integrated, then cross-reviewed for shared
language state, auth/voice behavior and evidence identity. A temporary local-only
fixture renders the actual updated patient task/chat/dialog components without
API requests or record mutations; it is removed before delivery. At 320, 768 and
1280 pixels the fixture has no page-level horizontal overflow. Spanish sign-in
was visually checked at 320 pixels. Dialog Escape restores focus to its trigger.
These are component/layout checks, not proof of every deployed route after rollout.

## Verification and remaining limits

Final integrated checks passed **372 patient tests (45 files)** and **260
clinician tests (38 files)**. In each app directory, the commands were:

```sh
npm run lint
npm run typecheck -- --incremental false
NODE_OPTIONS=--no-experimental-webstorage npm test
npx next build --webpack
```

Both app builds passed. The default Turbopack build cannot create its loader
subprocess port in this sandbox, so local build verification used webpack.
Regression coverage includes language-save/refresh/session races, late profile
fetches, translated error recovery, historical chat playback, source filenames,
numeric clinical text, task instruction retention and modal focus behavior.
PR #140 is merged; these changes are a separate combined portal-polish review.

After merge and deployment, recheck the actual authenticated screens at narrow
width and both locales. Existing messages and clinical text may intentionally
remain in their original language. Patient symptom history is not yet connected.
The dashboard reporting API cannot distinguish missing response data from a
genuine zero for every known-risk record; the UI must not invent that distinction.
Existing MFA lookup-failure behavior remains an operational follow-up, not a new
claim that MFA is enabled or that enrollment is required.
