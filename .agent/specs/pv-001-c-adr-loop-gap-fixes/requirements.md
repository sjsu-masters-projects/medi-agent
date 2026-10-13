# Requirements Document

> **Status:** PR 1 and groundwork delivered in the PR that adds this folder; PR 2 and PR 3 are planned follow-ups.
> Requirements 1 to 14 (PR 1, PR 2) were approved by the requester on 2026-10-12; requirements 15 to 24 (PR 3) were
> added the same day, and the requester decided D12 to D17 exactly as proposed. Design in `design.md`, tasks in
> `tasks.md`.
> **Worktree / branch:** `.worktrees/adr-loop-gaps`, `fix/adr-information-loop-gaps`, based on `origin/main` `87a466d`
> (drafted at `62a1945`; the only later commit is the #157 email-branding change, re-checked: no ADR copy, category
> or link impact; `email_service.py` keeps the `adr_information_requested` titles and links every notice to
> `/notifications`).
> **Scope tracker:** a scoped task entry (proposed ID `PV-001-C`) is created in `.agent/TASKS.md` before implementation (Requirement 2).

## Introduction

PR #136 (`feat(adr): close patient information loop`) lets an assigned clinician request up to three
patient-answerable, retrospective Naranjo questions (`reappeared_on_rechallenge`, `dose_response`,
`similar_previous_reaction`). The patient answers in chat. The RPC `respond_to_adr_information_request`
records the answers, deterministically rescores and writes audit. PR #150
(`feat(medwatch): add clinician-approved draft lifecycle`) added the MedWatch draft lifecycle
(`048_medwatch_draft_lifecycle.sql`, applied by the requester to the `mediagent-staging` Supabase project on
2026-10-12; the migration ledger reported synchronized through 058). MedWatch stays draft and export only. It is never
submitted to the FDA.

Both PRs predate the notification centre (migrations 051 to 056), the UX-002 redesign (#142 to #145), LOC-001
bilingual wording, NORA-002 daily conversations and the account-deletion work (053). Reading the code at
`62a1945`, re-checked at `87a466d`, shows ten gaps (G1 to G10). This spec fixes them in two deliverables:

- **PR 1, patient and clinician surfaces (no migration):** G1 to G5.
- **PR 2, notification lifecycle and data deletion (one new migration, 059, written but not applied):** G6 to G10.
- **PR 3, MedWatch Form 3500 fidelity, preview and export (one new migration, 060, written but not applied; owner
  Rajeev):** the draft becomes a structured, non-identifying Form FDA 3500 (not 3500A) with a read-only preview, an
  official-PDF download, a clinician-recorded external submission and discard/reopen (D8, now in scope). The app
  still never submits to the FDA (PROJECT.md: MedWatch "Draft only"; submitting a regulatory report "Prohibited").
  The requester assigned this work to Rajeev on 2026-10-12, overriding TEAM.md's PV-002 assignment to Jeevan.

MediAgent is supervised clinical decision support for California outpatient chronic care. Data is synthetic only.
Patient-facing locales are exactly `en-US` and `es-MX`. Clinician controls are English only. Decision support
never replaces clinician judgment. Nothing here changes who may request information, the three allowed questions,
or the Naranjo scoring.

### Evidence legend

Each acceptance criterion ends with the basis for the gap it closes. Nothing was executed while writing this
spec. "Observed" means read in source, not run.

| Tag | Meaning |
| --- | --- |
| **Observed** | Read directly in this worktree's source (at `62a1945`, re-read at `87a466d`); the file is cited. Not executed. For PR 3 it also covers the FDA Form 3500 instructions page and the official PDF, both read on 2026-10-12 and cited by URL. |
| **Inferred** | Follows from the code read but depends on runtime behaviour not exercised. Confirm with a test or manual check. |
| **NEEDS REPRO** | Must be reproduced by the disposable PostgreSQL 16 contract test against unmodified `main` behaviour before the fix is accepted (Requirement 14). |
| **Design** | A target-behaviour decision or standard, not a claim about current code. |

### Non-goals

No FDA submission, and no transmission of any report to the FDA (PR 3 only records a submission the clinician made
outside MediAgent). No Form 3500A, no device reporting. No new email, SMS or push beyond the existing 057 category
mapping. No new Naranjo questions or scoring change. No remote migration apply, deployment or merge. No real data.
No change to who may request information.

## Glossary

- **Patient_Portal**: `apps/patient-portal`, the mobile-first patient app (tokens in its `globals.css`).
- **Clinician_Portal**: `apps/clinician-portal`, the desktop-first clinician app (tokens in its `globals.css`).
- **Saved_Locale**: the patient's saved `preferred_language`, either `en-US` or `es-MX`. It is not the browser locale.
- **Follow_Up_Form**: the Patient_Portal view where a patient answers an Information_Request. Today this is
  `ADRFollowUpPanel` in `adr-follow-up-panel.tsx`, rendered only inside an open Nora assistant thread.
- **Information_Request**: a row in `public.adr_information_requests` with status `pending`, `answered` or
  `cancelled`. At most one is `pending` per ADR assessment.
- **Question_Key**: one of `reappeared_on_rechallenge`, `dose_response`, `similar_previous_reaction`.
- **Notification_Centre**: the NOT-001 recipient-scoped in-app notification system (tables, RPCs, API, both portals).
- **Presentation_Layer**: `backend/src/app/services/notification_centre_presentation.py`, which builds titles,
  bodies, links and action labels from allowlisted copy.
- **Capture_Trigger**: `private.capture_notification_source()` (latest definition: 055) and its source-table triggers.
- **Actionable**: the result of `private.notification_actionable()` (latest definition: 054). An actionable item is
  an open task. A non-actionable item is History.
- **Legacy_Notification_Row**: the English-only `public.notifications` row (`adr_alert`, "Your care team has
  follow-up questions", `action_url` `/chat`, `dedupe_key` `adr-information-request:<id>`) inserted by 047.
- **ADR_Evidence_Entry**: one element of `adr_assessments.evidence`. Entries written by patient answers carry
  `source: "patient_follow_up"` (`patient_service.py`); extraction entries carry no `source`.
- **AI_Extracted_Evidence / Patient_Confirmed_Answer**: evidence produced by model extraction from chat, versus an
  answer the patient reviewed, confirmed and sent through the Follow_Up_Form.
- **MedWatch_Draft**: a row in `public.medwatch_drafts` (`draft`, `reviewed`, `submitted`; the app never sets `submitted`
  today; after PR 3, a submitted state is reachable only by a clinician recording an External_Submission_Record).
- **UI_Standard**: Requirement 1.
- **Migration_059**: the single new migration, `backend/src/app/db/migrations/059_*.sql`, written but not applied.
- **Contract_Test**: the opt-in Docker `postgres:16` test (pattern: `backend/tests/integration/test_notification_centre_postgres.py`).
- **ADR_Database**: the ADR and MedWatch tables, RPCs and triggers in PostgreSQL.
- **ADR_API**: the backend ADR endpoints and services (`routers/patients.py`, `patient_service.py`, `clinician_service.py`).
- **MedWatch_API**: the backend MedWatch routes in `routers/clinicians.py` (`/me/medwatch-drafts...`) and
  `services/medwatch_service.py`.
- **Form_3500**: Form FDA 3500, the FDA MedWatch form for voluntary reporting by health professionals. It is not
  Form FDA 3500A, the mandatory form for manufacturers, importers and user facilities. Item references such as A1 or
  B5 follow the FDA instructions.
- **Official_Template**: the official fillable Form_3500 PDF (revision 09/2025, OMB 0910-0291, expires 09-30-2027),
  vendored in the repository at a pinned SHA-256 (Requirement 15).
- **External_Submission_Record**: a clinician's attested record that they submitted an approved MedWatch_Draft to the
  FDA themselves, outside MediAgent. It holds the date, method, optional FDA reference and the recording clinician.
  Creating it sends nothing anywhere.
- **Migration_060**: the single PR 3 migration, `backend/src/app/db/migrations/060_*.sql`, written but not applied.

## Requirements

## Cross-cutting

### Requirement 1: UI standard for every ADR and MedWatch surface

**User Story:** As a patient or clinician, I want the ADR follow-up and MedWatch screens to match the redesigned
app, so that safety-relevant tasks feel as clear and trustworthy as Today, Chat and Visits.

The requester's instruction applies to every UI requirement below: "The standard of UI has improved across both
apps, so make sure we are in that league." The ADR surfaces from #136 and #150 predate UX-002 and must be brought
to the same level, not only made bilingual. Requirements 3, 4, 6, 7 and 8 reference this requirement.

#### Reference exemplars (patterns to match, inspected at `62a1945`, unchanged at `87a466d`)

| App | Exemplar | What it demonstrates |
| --- | --- | --- |
| Patient | `components/features/visit-offer-card.tsx` (closest analogue, an actionable response card) | `Button` primitive with `min-h-11`; hairline row `border-b border-line px-[14px] py-[13px]`; `break-words` on all stored text; labelled textarea with `focus:ring-4 focus:ring-brand/15`; two-step compose, confirm, back; no hex literals |
| Patient | `components/features/notification-centre.tsx` | `role="status"` for loading and unavailable, `role="alert"` for errors, `aria-busy`, `min-h-11` controls, `font-mono` for times, shared `Modal` |
| Patient | `components/features/care-conversations.tsx`, `nora-conversations.tsx` | `Modal` for sheets, `safe-area-inset-bottom` composer, `break-words [overflow-wrap:anywhere]`, `role="status"` / `role="alert"` states |
| Patient | `components/features/today-presentation.tsx`, `app/(app)/chat/page.tsx` | `IconTile`; `ApprovalSeal` used for clinician-approved care-plan tasks; `bg-danger-tint text-danger-ink` caution strip; Nora card tokens |
| Patient | `components/ui/*` | `Button` (`sm`/`md`/`lg`, 44px minimum height), `Card`, `Badge`, `GroupedList`/`IconTile`/`SectionLabel`, `EmptyState`, `ErrorState` (locale-aware), `Skeleton`, `Modal`, `AiChip`, `ApprovalSeal`, `ProcessingDots` |
| Clinician | `components/features/notification-centre.tsx`, `care-plan-panel.tsx`, `appointment-offer-form.tsx` | `Button` variants and `Modal` (notification centre); `fieldClass` inputs, `aria-live="polite"` and `ApprovalSeal` (care-plan panel); `role="status"` / `role="alert"` and `font-mono` for counts and times across all three |
| Clinician | `components/ui/*` | `Button` (`primary`/`secondary`/`ghost`/`danger`/`approve`), `Badge` (incl. `ai`), `Input`/`fieldClass`, `Toolbar` (`SegmentedControl` with `role="radiogroup"`, `CompactField` with `focus-within` ring), `DataTable`, `EmptyState`, `ErrorState`, `Skeleton`, `AiChip`, `ApprovalSeal`, `Modal` |
| Clinician | `app/(dashboard)/medwatch/page.tsx` header band and `adr-review-card.tsx` | Already at the UX-002 level; the target for the MedWatch draft components |

#### Acceptance Criteria

1. THE Patient_Portal and THE Clinician_Portal SHALL build every changed ADR and MedWatch surface from that app's
   shared `components/ui` primitives (Button, Card, Badge, EmptyState, ErrorState, Skeleton, Modal; patient
   GroupedList, IconTile and SectionLabel; clinician Input and `fieldClass`) and SHALL add no one-off equivalent of
   an existing primitive. *Evidence: Observed. `adr-follow-up-panel.tsx` hand-builds notices, option tiles and row
   markup; `medwatch-draft-card.tsx` and `medwatch-preparation-action.tsx` hand-build inputs.*
2. THE Patient_Portal and THE Clinician_Portal SHALL express colour in changed ADR and MedWatch files only through
   tokens defined in that app's `globals.css`. Changed files SHALL contain no hex literal and no raw palette class
   (`gray-`, `slate-`, `blue-`, `indigo-`, `amber-`, `green-`, `red-`, `emerald-`). *Evidence: Observed. The panel
   uses `#e6f4f1`, `#b6d9d2`, `#17233a`, `#FFF7E8`, `#F0D7AA`, `#d9cbc0`, `#efbeb5`, `#fff2ef`, `#48627c` (none are
   tokens) and `#147465` (equals `brand`). The MedWatch components use `border-indigo-200 bg-indigo-50`,
   `text-gray-900`, `focus:ring-blue-500`. UX-002 section 1.3 requires replacing such colours.*
3. WHERE a needed colour has no token, THE change SHALL add a named token to that app's `globals.css` instead of an
   inline value. *Evidence: Design.*
4. THE Patient_Portal and THE Clinician_Portal SHALL set prose in Geist (`font-sans`) and use Geist Mono
   (`font-mono`) only for scores, times, counts and uppercase eyebrow labels. *Evidence: Design (DESIGN_SYSTEM.md).*
5. THE Patient_Portal SHALL give every interactive ADR control, including each radio option, the confirmation
   checkbox, links and icon buttons, a hit area of at least 44 by 44 CSS px. *Evidence: Observed. Radio labels use
   `min-h-12`, but the confirmation checkbox is `h-4 w-4` inside a label with no minimum height.*
6. THE Clinician_Portal SHALL give every interactive ADR and MedWatch control a height of at least 32 CSS px.
   *Evidence: Design (UX-002 section 4).*
7. WHILE any ADR control has keyboard focus, including a visually hidden radio or checkbox, THE Patient_Portal and
   THE Clinician_Portal SHALL show the app's focus indicator on the visible control (for example on the label via
   `has-[:focus-visible]` or `peer-focus-visible`). *Evidence: Observed. Global CSS sets `input:focus-visible {
   outline: none }`, and the panel's radios are `sr-only` inside labels whose classes define no focus state, so
   focus is invisible.*
8. THE Patient_Portal and THE Clinician_Portal SHALL keep text contrast at 4.5:1 or higher for every text and
   background pair on changed surfaces, including selected, hover, tinted-chip and error states, and SHALL record
   the computed ratio for each token pair used. *Evidence: Observed by calculation. The current panel pairs measure
   4.68 to 13.88, so the requirement is to preserve contrast when moving to tokens, not to repair it.*
9. THE Patient_Portal SHALL wrap long Spanish text, clinician-authored messages, symptom names and medication names
   without truncating them, using the `break-words` and `[overflow-wrap:anywhere]` patterns of `visit-offer-card.tsx`
   and `care-conversations.tsx`. *Evidence: Design.*
10. WHEN the viewport is 320 CSS px wide or text is zoomed to 200 percent, THE Patient_Portal SHALL keep every ADR
    question, caution, answer option and action visible and reachable with no horizontal scrolling. *Evidence: Design.*
11. WHERE a fixed or sticky ADR action bar or bottom padding is used, THE Patient_Portal SHALL honour
    `env(safe-area-inset-bottom)` and SHALL keep the last control clear of the bottom navigation. *Evidence: Design
    (UX-002 section 2.1).*
12. THE implementation SHALL be checked at patient widths 320, 360 and 430 px and clinician widths 1024, 1280 and
    1536 px. *Evidence: Design (narrower and wider than the 360 / 1280 references).*
13. THE Patient_Portal and THE Clinician_Portal SHALL build loading states from `Skeleton`, empty states from
    `EmptyState`, error states from `ErrorState` with a retry action, and success notices from a token-styled
    `role="status"` block. *Evidence: Observed. The panel's loading state is a plain-text Card and its error state is a
    bespoke Card; the MedWatch page's `Suspense` fallback is a bare `<p>`.*
14. WHEN an ADR surface changes because of a real state change (loading, submitting, appearing), THE Patient_Portal
    and THE Clinician_Portal SHALL animate it only with the existing `ma-enter`, `ma-press` and `ProcessingDots`
    patterns, SHALL run loops only while work is in progress, and SHALL honour `prefers-reduced-motion`. *Evidence:
    Design (UX-002 sections 1.4 and 1.7).*
15. THE Patient_Portal and THE Clinician_Portal SHALL show the sparkle `AiChip` only on AI-produced content and the
    check `ApprovalSeal` only for actual, server-backed clinician approval. Patient-confirmed answers SHALL carry
    neither. *Evidence: Design (DESIGN_SYSTEM.md).*
16. WHERE an ADR surface opens a sheet or dialog, THE Patient_Portal and THE Clinician_Portal SHALL use the shared
    `Modal` so that focus is trapped, Escape closes it and focus returns to the invoking control. *Evidence: Design.*
17. THE implementation SHALL preserve every existing handler, route, `aria-*` attribute and test selector on changed
    ADR and MedWatch surfaces, or migrate each deliberately with the affected tests updated and listed in the PR.
    Examples: the labels "Yes" and "I’m not sure", the buttons "Review answers" and "Send to care team", roles
    `group`, `textbox`, `checkbox` and `alert`, and on the clinician side `id="assessment-<id>"` and the region labels
    "ADR assessments awaiting review" and "MedWatch drafts". *Evidence: Observed in
    `adr-follow-up-panel.test.tsx` and `medwatch/page.tsx`.*
18. THE Patient_Portal SHALL render every patient-visible ADR string from the Saved_Locale, and THE Clinician_Portal
    SHALL keep every ADR and MedWatch control in English. *Evidence: Design (AGENTS.md, DESIGN_SYSTEM.md).*
19. THE PR description SHALL attach screenshots of each changed state at the stated widths in both Saved_Locale
    values (patient) and in English (clinician), taken with synthetic data only. Screenshots not produced locally
    SHALL be listed as manual items for the requester. *Evidence: Design (DESIGN_SYSTEM.md "Verification before review").*

### Requirement 2: Scope guardrails, delivery evidence and tracker

**User Story:** As the requester, I want the fixes split into two reviewable PRs with honest evidence, so that I can
approve rollout without ambiguity.

#### Acceptance Criteria

1. THE PR 1 changeset SHALL contain no SQL migration file, and THE PR 2 changeset SHALL contain exactly one new
   migration file, numbered 059. *Evidence: Design.*
2. THE changes SHALL keep MedWatch draft and export only, with no code path that submits a report to the FDA.
   *Evidence: Observed. `medwatch_drafts_not_submitted_by_app` and the page copy "Not submitted to FDA".*
3. THE changes SHALL keep the three Question_Key values, the Naranjo scoring and the set of clinicians allowed to
   request information unchanged. *Evidence: Observed (047 allowlist and assignment check).*
4. THE changes SHALL add no email, SMS or push category beyond the existing 057 mapping. *Evidence: Observed
   (`private.email_preference` in 057).*
5. WHEN implementation starts, THE contributor SHALL first add a scoped task entry to `.agent/TASKS.md` and SHALL
   update the PV-001, PV-001-B, PV-002 and NOT-003 rows, the "Synthetic database schema" row (048 MedWatch applied
   by the requester to `mediagent-staging` on 2026-10-12, ledger synchronized through 058; 059 written and not
   applied anywhere), the NOT-001 specification and the ADR section of `apps/patient-portal/README.md` when
   behaviour changes. *Evidence: Observed. TASKS.md still describes 048 MedWatch as unapplied and lists applied
   migrations only through 056; the applied date and ledger state are requester-supplied facts.*
6. THE PR descriptions SHALL record the exact commands and outcomes of every check, mark each criterion's evidence as
   observed or inferred, and list manual items as needing the requester. *Evidence: Design (AGENTS.md).*
7. THE branch names, commit messages, source comments and product documentation SHALL not identify an authoring tool,
   provider or assistant. *Evidence: Design (AGENTS.md).*

## PR 1 - Patient and clinician surfaces (no migration)

### Requirement 3: Bilingual, token-built follow-up form (G1)

**User Story:** As a patient who uses Spanish, I want to read and answer my care team's questions entirely in
Spanish, so that I can answer accurately and safely.

#### Acceptance Criteria

1. WHILE the Saved_Locale is `es-MX`, THE Follow_Up_Form SHALL render every string in Mexican Spanish: heading,
   caution, question prompts, answer options, evidence prompts, review step, confirmation, buttons, loading, error
   and success text. WHILE the Saved_Locale is `en-US`, THE Follow_Up_Form SHALL render every string in English.
   *Evidence: Observed. Every string in `adr-follow-up-panel.tsx` is a hard-coded English literal.*
2. THE Follow_Up_Form SHALL read its strings from a typed per-locale copy module (pattern: `content/visits-copy.ts`,
   `content/chat-copy.ts`), and a test SHALL assert that both locales define the same keys. *Evidence: Design.*
3. WHILE the Saved_Locale is not yet resolved, THE Follow_Up_Form SHALL show its loading state and no text in a
   default locale. *Evidence: Inferred. The chat page falls back to `DEFAULT_LOCALE` while the profile loads.*
4. THE Follow_Up_Form SHALL show the clinician-authored message, the symptom and the medication name exactly as
   stored, without translating them, and SHALL label the message as coming from the care team. *Evidence: Observed
   (`request.patientMessage`, `request.symptom` rendered verbatim).*
5. THE Follow_Up_Form SHALL keep all three safety statements in both locales: "do not restart it to answer", "do not
   change your dose to answer", and "Answer only from what has already happened. Do not restart, stop, or change a
   medicine just to answer these questions." The confirmation text SHALL keep its meaning in both locales.
   *Evidence: Observed in `QUESTION_COPY` and the notice block.*
6. THE es-MX strings SHALL use the second-person register of existing es-MX copy ("tu equipo de atención") and SHALL
   be reviewed by a Spanish-fluent reviewer before acceptance. *Evidence: Observed register in
   `notification_centre_presentation.py`; review is a manual item.*
7. IF saving the answers fails, THEN THE Follow_Up_Form SHALL show a message in the Saved_Locale chosen from the
   failure class (request closed, not found, unavailable, other) and SHALL not display raw server text. *Evidence:
   Observed. The panel renders `submissionError.message`; backend errors such as "This information request has
   already been completed" are English.*
8. THE Follow_Up_Form SHALL keep the answer options as real radio inputs inside a `fieldset` with a `legend`, and
   SHALL show the selected option with a check glyph in addition to its fill colour. *Evidence: Observed (radios in
   fieldsets); the glyph is Design.*
9. THE Follow_Up_Form SHALL keep its behaviour unchanged: "Yes" and "No" require a non-empty description of at most
   500 characters, "I’m not sure" sends no description, the confirmation checkbox is required before sending, Edit
   returns to the answers, and the request payload shape is unchanged. *Evidence: Observed
   (`ADRInformationAnswerInput`, `respondToADRInformationRequest`).*
10. THE Follow_Up_Form SHALL satisfy Requirement 1. The sparkle chip and the check seal SHALL not appear on it,
    because the content is clinician-authored and patient-confirmed. *Evidence: Design.*

### Requirement 4: A working path from notification, chat inbox and Today to the form (G2)

**User Story:** As a patient, I want the notification about my care team's questions to open the form for those
questions, so that I can answer in one step.

#### Acceptance Criteria

1. WHEN a patient follows the link of an `adr_information_requested` item, THE Patient_Portal SHALL open the
   Follow_Up_Form for that request directly, with no thread or recipient selection first. *Evidence: Observed.
   `destination()` links to `/chat?view=care-team&recipient=<clinician>`, which opens the human thread.*
2. THE Presentation_Layer SHALL build the link and action label for `adr_information_requested` in the patient's
   locale (for example "Answer questions" / "Responder preguntas"), SHALL use a route whose pathname is in the
   Patient_Portal destination allowlist (`/chat`, `/today`, `/visits`, `/records`, `/reminders`) or extend that
   allowlist with a test, and SHALL not put raw identifiers in copy. The link target SHALL be resolvable without a
   migration, for example by the assessment ID that is already the event's `source_id`. *Evidence: Observed
   (`destination()`; `notificationDestination()` in `services/notifications.ts`).*
3. THE Patient_Portal SHALL no longer depend on an open Nora assistant thread to show the Follow_Up_Form, and a
   patient inside an open Nora thread SHALL still reach it from a visible control. *Evidence: Observed. The panel
   renders only in the `assistantThread` branch of `chat/page.tsx`.*
4. WHILE at least one Information_Request is `pending`, THE Patient_Portal SHALL show an entry row to the
   Follow_Up_Form in the chat inbox and on Today, each in the Saved_Locale, built from `GroupedList` / `IconTile`
   and at least 44 px tall. WHILE none is pending, THE Patient_Portal SHALL show neither row. *Evidence: Design
   (decision D6, decided: both rows, only while a request is pending).*
5. THE Follow_Up_Form SHALL show the existing emergency and "messages are not continuously monitored" caution
   (`controls.caution` in `chat-copy.ts`) in the Saved_Locale wherever it is hosted. *Evidence: Observed. The caution
   renders immediately above the panel in the Nora thread today; moving the form must not lose it.*
6. WHEN the patient is not signed in and opens the link, THE Patient_Portal SHALL follow its existing sign-in redirect
   and return to the form afterwards. *Evidence: Inferred (existing protected-route behaviour).*
7. THE Patient_Portal SHALL keep the new view and entry rows within Requirement 1. *Evidence: Design.*

### Requirement 5: Deterministic bilingual request notification text (G3)

**User Story:** As a patient, I want my notification to describe what my care team is asking in plain language in my
language, so that I never see internal codes.

Proposed wording (subject to Spanish-fluent review, decision D9):

| Question_Key | en-US | es-MX |
| --- | --- | --- |
| `reappeared_on_rechallenge` | Whether the symptom came back after restarting this medicine | Si el síntoma volvió después de reiniciar este medicamento |
| `dose_response` | Whether the symptom changed after a dose change your clinician directed | Si el síntoma cambió después de un cambio de dosis indicado por tu profesional de salud |
| `similar_previous_reaction` | Whether you have had a similar reaction to this medicine before | Si has tenido antes una reacción similar a este medicamento |

#### Acceptance Criteria

1. WHEN the Presentation_Layer builds an `adr_information_requested` item, THE Presentation_Layer SHALL list each
   Question_Key found in `metadata.requested_information` using the fixed wording above for the item's locale, in
   the order requested, with duplicates removed and at most three entries. *Evidence: Observed. `_questions()`
   prints the stored strings "as written" under "Questions from your clinician (shown as written)"; 047 stores
   machine keys.*
2. FOR ALL values of `metadata.requested_information` (keys, free text, UUIDs, non-strings, empty, over-long), THE
   title and body SHALL contain no raw Question_Key, no UUID and no value outside the fixed wording. Entries that
   are not an allowed Question_Key SHALL be omitted. *Evidence: Observed (the unit test
   `test_notification_centre_presentation.py` currently asserts that free text is echoed).*
3. IF no allowed Question_Key remains, THEN THE Presentation_Layer SHALL show the fixed introductory sentence and no
   list. *Evidence: Design.*
4. THE body SHALL tell the patient to answer in the app and SHALL not instruct them to contact the clinician through
   Care team messages. *Evidence: Observed. The current body says "Contact the requesting clinician through Care team
   messages."*
5. THE body SHALL keep the "only describe what already happened" safety meaning in both locales. *Evidence: Design.*
6. THE Presentation_Layer SHALL keep the existing titles ("Your care team requested information" / "Tu equipo de
   atención solicita información"), which the 057 email copy also uses. *Evidence: Observed (`_COPY`, `email_service.py`).*
7. THE existing presentation unit tests that assert the old link and the "shown as written" behaviour SHALL be
   migrated deliberately to assert the new behaviour. *Evidence: Observed (`test_notification_centre_presentation.py`).*

### Requirement 6: Complete request lifecycle states in the patient view (G4)

**User Story:** As a patient, I want to see what happened to a request I was asked about, so that I am never left on
a blank screen or asked to answer something that is closed.

Product decisions D2 (draft persistence) and D5 (how much history to show) are decided as stated below.

#### Acceptance Criteria

1. WHEN the Follow_Up_Form is opened for a request whose status is `answered`, THE Follow_Up_Form SHALL show a
   read-only summary of the patient's own saved answers, the answered date in the patient's timezone and Saved_Locale,
   and a statement that the care team has the answers, without any Naranjo score or causality text. *Evidence:
   Observed. The list endpoint returns only `pending` rows (`patient_service.py`), and the panel renders nothing when
   there is no pending request.*
2. WHEN the Follow_Up_Form is opened for a request whose status is `cancelled`, THE Follow_Up_Form SHALL state in the
   Saved_Locale that the care team closed or replaced the request and that no answer is needed, and SHALL link to
   the newer pending request for the same assessment when one exists. *Evidence: Observed (cancel behaviour in 047
   `review_adr_assessment`).*
3. IF the requested ID does not exist or belongs to another patient, THEN THE ADR_API SHALL answer with the same
   not-found response in both cases and THE Follow_Up_Form SHALL show a localized not-found state. *Evidence:
   Observed for another patient's ID (`NotFoundError` in `respond_to_adr_information_request`); Inferred for a missing
   ID: `.single()` on zero rows raises a PostgREST `APIError` (PGRST116) that `execute_async` re-raises unmapped, so
   the response is likely a 500, not a 404. RPC errors (`P0002`, `23514`) are also unmapped today.*
4. IF a submission fails because the request is no longer pending (for example answered in another tab or cancelled),
   THEN THE Follow_Up_Form SHALL switch to the answered or closed state instead of offering another retry. *Evidence:
   Observed. The service and RPC raise "already completed" / "no longer awaiting information".*
5. THE ADR_API SHALL return recent non-pending requests to the patient only as a bounded list (default: the most
   recent 5 within 90 days, newest first) and SHALL return only fields the patient may see. The Naranjo score and
   causality fields SHALL not be rendered. *Evidence: Design (decision D5). Observed: the pending read model already
   carries `current_naranjo_score` and `current_causality` that the UI never shows; removing them stays D11 (later).*
6. WHILE the Follow_Up_Form loads, THE Patient_Portal SHALL show `Skeleton` placeholders. WHEN there is no request at
   all, THE Patient_Portal SHALL show an `EmptyState`. WHEN loading fails, THE Patient_Portal SHALL show an
   `ErrorState` with retry in the Saved_Locale. *Evidence: Observed (current loading and error are plain Cards).*
7. WHEN the patient sends answers successfully, THE Follow_Up_Form SHALL show a `role="status"` confirmation in the
   Saved_Locale that persists on screen until the patient leaves it, and SHALL move focus to that confirmation.
   *Evidence: Observed. The current notice is a transient parent-state string.*
8. THE Patient_Portal SHALL not write draft answer text to `localStorage`, `sessionStorage` or cookies. Unsent text
   SHALL be lost on reload, and the Follow_Up_Form SHALL state this limit near the Send action. *Evidence: Design
   (decision D2, decided: option a). Observed: drafts live only in component state today.*
9. THE Patient_Portal SHALL satisfy Requirement 1 for every state in this requirement. *Evidence: Design.*

### Requirement 7: Accurate evidence provenance on the clinician ADR card (G5)

**User Story:** As a clinician, I want each piece of Naranjo evidence labelled by where it came from, so that I do
not mistake a patient's confirmed answer for AI extraction.

#### Acceptance Criteria

1. THE Clinician_Portal SHALL label each ADR_Evidence_Entry individually: an entry with `source` equal to
   `patient_follow_up` as "Patient-confirmed", an entry without a `source` as "AI-extracted", and an entry with any
   other `source` with a neutral "Other source" label that makes no AI claim. *Evidence: Observed.
   `adr-review-card.tsx` places one `AiChip` ("AI-extracted") over the whole list; `patient_service.py` writes
   `source: "patient_follow_up"`; extraction entries come from `followup/service.py`.*
2. THE Clinician_Portal SHALL show the sparkle `AiChip` only on AI-extracted entries and SHALL show the check
   `ApprovalSeal` on none of them. "Patient-confirmed" SHALL use a neutral `Badge` with no sparkle and no check seal.
   *Evidence: Design (Requirement 1.15).*
3. THE Clinician_Portal SHALL extend the `ADRReviewEvidence` type with the optional `source` and
   `information_request_id` fields that the API already passes through, and SHALL render only provenance that the
   stored data supports. *Evidence: Observed. The TS type declares only `answer`, `evidence`, `question`; the API
   model is `list[dict[str, Any]]`.*
4. WHEN two entries share a question (an AI-extracted entry and a later patient-confirmed entry), THE Clinician_Portal
   SHALL render both with distinct React keys and distinct labels. *Evidence: Observed. `key={entry.question}`; the
   response flow appends entries without removing the earlier one.*
5. WHEN a patient-confirmed entry is shown, THE Clinician_Portal SHALL show the answer date when `patientRespondedAt`
   is available, formatted in `en-US`. *Evidence: Observed (`patientRespondedAt` is in the item type).*
6. THE existing text "Naranjo scores support your review; they do not make a clinical decision." and the
   "Decision support only" footer SHALL remain. *Evidence: Observed.*
7. THE Clinician_Portal SHALL satisfy Requirement 1 for the changed card and extend `adr-review-card` tests to cover
   all-AI, all-patient and mixed evidence. *Evidence: Design.*

### Requirement 8: MedWatch page and draft defects (G5, second part)

**User Story:** As an assigned clinician, I want the MedWatch draft screens to behave and look like the rest of the
clinician app, so that I can edit and approve an export without losing work.

Only real defects are listed. Everything else reviewed is recorded under "Out of scope".

#### Acceptance Criteria

1. THE Clinician_Portal SHALL rebuild `medwatch-draft-card.tsx` and `medwatch-preparation-action.tsx` from tokens and
   shared primitives (`fieldClass`/`Input`, `Badge`, `Button`, `Card`), with no raw palette classes. *Evidence:
   Observed. Both files use `gray-`, `blue-`, `indigo-`, `amber-`, `green-`, `red-` utility classes.*
2. THE Clinician_Portal SHALL keep the "Not submitted to FDA" notice on every draft, restyled with warning tokens.
   *Evidence: Observed (amber pill in the card header).*
3. WHILE a MedWatch_Draft has status `reviewed`, THE Clinician_Portal SHALL show an `ApprovalSeal` stating approval
   for export, and WHILE the status is `draft` it SHALL show no seal. No AI chip SHALL appear on the draft. *Evidence:
   Observed. Status is a `Badge` only; the draft is built deterministically from reviewed ADR evidence.*
4. WHEN the queue refreshes while a draft card holds unsaved edits, THE Clinician_Portal SHALL keep those edits and
   show an "Unsaved changes" indication. *Evidence: Inferred. `useEffect(() => setForm(draft.formData), [draft.formData])`
   resets the form whenever `loadQueue()` replaces the draft objects, which happens after any ADR review action and
   on Refresh. Confirm with a component test.*
5. IF preparing a draft fails, THEN THE Clinician_Portal SHALL show the error inline beside the preparation form with
   `role="alert"` and SHALL not leave an unhandled promise rejection. *Evidence: Observed. `submit()` awaits
   `onPrepare` with `try/finally` and no `catch`, and the page's `prepareDraft` sets a page-level error and rethrows.*
6. THE Clinician_Portal SHALL format the approval time with the same fixed `en-US` formatter as `adr-review-card.tsx`
   instead of `toLocaleString()`. *Evidence: Observed (`new Date(draft.approvedAt).toLocaleString()`).*
7. WHEN the viewport is 1024 px wide, THE Clinician_Portal SHALL wrap the draft ID, field paths and citations with no
   horizontal scrolling. *Evidence: Inferred (the draft ID is an unbroken 36-character string).*
8. THE MedWatch page `Suspense` fallback SHALL use `Skeleton`/`LoadingQueue` instead of a bare paragraph.
   *Evidence: Observed.*
9. THE Clinician_Portal SHALL keep every existing action reachable (Save draft, Approve for export, Export approved
   JSON, Prepare MedWatch draft, Refresh), the approval attestation and note requirements, and all selectors listed in
   Requirement 1.17. *Evidence: Observed.*
10. THE Clinician_Portal SHALL satisfy Requirement 1 for the two draft components and the page states. *Evidence: Design.*

## PR 2 - Notification lifecycle and data deletion (migration 059, not applied)

### Requirement 9: Answering resolves the patient's action item (G6)

**User Story:** As a patient, I want my open question to close when I answer it, so that I am not told again to answer
something I already answered.

#### Acceptance Criteria

1. WHEN a patient answers a pending Information_Request, THE ADR_Database SHALL create no new `adr_information_requested`
   event for that answer. *Evidence: NEEDS REPRO. Observed: `respond_to_adr_information_request` updates
   `adr_assessments.updated_at` but leaves `last_review_action = 'request_information'` and `requested_information`;
   the 055 trigger branch re-fires when `(last_review_action, requested_information, updated_at)` differs from OLD.*
2. WHEN a patient answers a pending Information_Request, THE Notification_Centre SHALL report that request's patient
   notification as non-actionable (History). *Evidence: NEEDS REPRO. Observed: `notification_actionable` (054) checks
   only assessment `status = 'draft'` and `last_review_action = 'request_information'`, not the request's own status.
   054 `notification_row` asks for action only on the newest receipt per (source, kind), so the original item turns
   into History while the re-captured item from criterion 1 becomes the new, unread, actionable one.*
3. WHEN a patient answers a pending Information_Request, THE Notification_Centre SHALL mark that request's patient
   receipt read. *Evidence: Observed. 047 marks the Legacy_Notification_Row read, so the intent exists; this extends it
   to the centre (decision D10, decided: yes).*
4. WHEN an `adr_assessments` row changes without a new clinician request (score change, evidence change,
   `updated_at` touch), THE Capture_Trigger SHALL create no patient request event. *Evidence: Inferred from the
   trigger tuple.*
5. WHEN an answer is saved, THE ADR_Database SHALL create no `email_outbox` row for a repeated "Your care team
   requested information" email. *Evidence: Inferred. 057 queues a notice for every new receipt, and 058 sends it only
   while the event is still actionable and unread, so the re-captured event would qualify.*
6. THE ADR_Database SHALL leave every previously captured event unchanged (history is append only). *Evidence:
   Observed (051 append-only trigger).*
7. THE fix SHALL associate each patient request event with its Information_Request so that actionability follows the
   request's own status. *Evidence: Observed. The event metadata carries `requested_information` and `clinician_id`
   but no request ID.*

### Requirement 10: One request, one patient notification (G7)

**User Story:** As a patient, I want one clear notification per request in my language, so that I am not shown a
duplicate.

#### Acceptance Criteria

1. WHEN a clinician requests information, THE Notification_Centre SHALL present exactly one patient-facing item for
   that request, bilingual and linked per Requirement 4. *Evidence: NEEDS REPRO for the final count. Observed:
   `review_adr_assessment` (047) inserts a Legacy_Notification_Row, and the 055 branch for `notifications` captures
   every INSERT as a `legacy_update` event, alongside the `adr_information_requested` event.*
2. WHEN a clinician requests information, THE ADR_Database SHALL create no new English-only Legacy_Notification_Row,
   or SHALL create one that the Capture_Trigger does not capture. *Evidence: Design (mechanism left to design).*
3. THE Notification_Centre SHALL show no English-only ADR request text to a patient whose Saved_Locale is `es-MX`.
   *Evidence: Observed. The centre renders the legacy row only as the bilingual generic "Earlier notification"
   (`legacy_update`), so the visible defect is the duplicate item (criterion 1). The English text is still served
   by the legacy `GET /api/v1/notifications/` route (`routers/notifications.py`), which no portal client calls at
   `87a466d`.*
4. THE ADR_Database SHALL leave existing Legacy_Notification_Rows and already captured `legacy_update` events
   unchanged. Those events are already non-actionable and remain as "Earlier notification" History. *Evidence:
   Observed (054 `legacy_update` returns false).*
5. WHEN a patient answers, THE respond RPC SHALL still complete without error if no Legacy_Notification_Row exists for
   the request. *Evidence: Observed. It updates by `dedupe_key`, which affects zero rows safely.*

### Requirement 11: Clinician alert when a patient answers (G8)

**User Story:** As an assigned clinician, I want to be told when a patient has answered my follow-up questions, so
that I can review the updated evidence.

#### Acceptance Criteria

1. WHEN a patient's answers are saved, THE Notification_Centre SHALL capture a clinician-audience event of a new
   type (proposed `adr_information_answered`) in the same transaction as the answers. *Evidence: Observed. No event
   exists today; the trigger branch only emits `adr_information_requested` (patient) and `adr_review`.*
2. THE Presentation_Layer SHALL show the title "Patient answered medication-safety follow-up" in English, in category
   `safety`, with a body free of clinical content (no symptom, medication, answer text, score or causality), and
   SHALL link to `/medwatch?assessment=<assessment id>` with the action label "Review source". *Evidence: Design.
   Observed: `_safety_link` already builds that route for `adr_review`.*
3. THE event SHALL be addressed per current assignment, as shared work (as `adr_review`), so that WHILE a clinician has
   an active care-team assignment and an active clinic they receive it, and WHEN the assignment ends they lose
   access to it. *Evidence: Observed (`notification_authorized` for `audience in ('clinician','shared')`). Decision D7,
   decided: option a, shared with all currently assigned clinicians.*
4. THE Notification_Centre SHALL deny the event to patients and to clinicians who are not assigned. *Evidence:
   Observed (`notification_authorized`: patient access to `adr_assessments` events requires
   `adr_information_requested`).*
5. THE alert SHALL be informational and History-only, unread in the bell, and SHALL not add to the Needs attention
   count, because the assessment's own `adr_review` item is already the open work. *Evidence: Design (decision D3,
   decided: option b).*
6. THE alert SHALL state in its body that it is not a clinical decision. *Evidence: Design (consistent with `adr_review` copy).*
7. IF the same answer is processed twice (retry), THEN THE ADR_Database SHALL keep exactly one event for that
   request through a unique event key derived from the request ID. *Evidence: Design.*
8. THE alert SHALL create no email in 057 (the new type maps to no email category) and no SMS or push. *Evidence:
   Observed. `private.email_preference` returns NULL for unmapped types.*
9. IF capturing the alert fails, THEN THE ADR_Database SHALL roll back the answer as well (capture is part of the
   source transaction, as in NOT-001). *Evidence: Observed (NOT-001 "Atomic source-change event capture").*
10. THE Clinician_Portal Alerts page SHALL list the alert under the `safety` category filter and in the bell, and
    opening the link SHALL focus the assessment card, or show the existing "no longer awaiting review" status text
    when it is resolved. *Evidence: Observed (`medwatch/page.tsx` behaviour).*

### Requirement 12: Deleting a patient removes their ADR and MedWatch data (G9)

**User Story:** As a patient who deletes my account, I want my ADR requests, answers, audit and MedWatch drafts
deleted with it, so that no medication-safety data of mine remains.

Per the requester's decision recorded in 053, a patient's data is deleted with the patient's account. 053 did not
cover these tables.

#### Acceptance Criteria

1. WHEN a patient who has answered an Information_Request is deleted, THE ADR_Database SHALL complete the deletion
   without a foreign-key error. *Evidence: NEEDS REPRO. Observed: `adr_assessment_audit_events.patient_actor_id`
   is `REFERENCES patients(id) ON DELETE RESTRICT` (047). In PostgreSQL, RESTRICT cannot be deferred and is checked
   when the referenced row is deleted, so the delete is expected to fail even though the same audit row would also
   be removed by the cascade through `adr_assessments`. The referential-action triggers on `patients` run in a fixed
   internal order, so the outcome is decided by the test, not by reading. The fix is `ON DELETE CASCADE`; `SET NULL`
   would violate `adr_assessment_audit_events_exactly_one_actor`.*
2. WHEN that patient is deleted, THE ADR_Database SHALL remove their Information_Requests with responses,
   `adr_assessment_audit_events`, MedWatch_Drafts and `medwatch_draft_audit_events`. *Evidence: Observed that
   `adr_information_requests.patient_id`, `medwatch_drafts.patient_id` and `adr_assessment_id` all cascade (047, 001,
   048); NEEDS REPRO for the full path including the audit table.*
3. THE ADR_Database SHALL leave other patients' data and the clinician's own record untouched by that deletion.
   *Evidence: Design (pattern: `test_patient_with_conversations_and_offer_history_can_be_deleted`).*
4. THE ADR_Database SHALL keep append-only semantics for `adr_assessment_audit_events` and
   `medwatch_draft_audit_events`: no role among `anon`, `authenticated` and `service_role` SHALL hold DELETE or
   TRUNCATE on them, so the cascade is the only removal path. *Evidence: Observed. 053 revokes and verifies this for
   conversation history; 048 grants `ALL` on `medwatch_draft_audit_events` to `service_role`, and no backend code
   deletes from either table, so Migration_059 revokes DELETE and TRUNCATE (as 053 did).*
5. THE clinician side (deleting a clinician who requested information, authored or approved a draft) SHALL remain as
   today until decision D1 is made, and THE spec SHALL not introduce a policy for it. *Evidence: Observed. 046, 047
   and 048 reference `clinicians(id)` `ON DELETE RESTRICT`: `adr_information_requests.requested_by`,
   `adr_assessment_audit_events.actor_id`, `medwatch_drafts.created_by` / `approved_by`,
   `medwatch_draft_audit_events.actor_id`; TASKS.md NOT-003 records the open decision.*
6. IF the Contract_Test does not reproduce criterion 1, THEN no foreign-key change SHALL ship for it and the
   Migration_059 verification block SHALL omit the foreign-key check (Requirement 14.9). *Evidence: Design.*

### Requirement 13: End state of cancelled and superseded requests (G10)

**User Story:** As a patient, I want a request that my care team withdrew or replaced to stop asking me for action,
so that I am not misled.

A later clinician action on the same assessment cancels pending rows (047 `review_adr_assessment`; 048
`create_medwatch_draft`).

#### Acceptance Criteria

1. WHEN a clinician marks an assessment reviewed, dismisses it or prepares a MedWatch draft, THE Notification_Centre
   SHALL report the patient's request notification as non-actionable (History) and THE Follow_Up_Form SHALL show the
   closed state of Requirement 6.2. *Evidence: Observed in the existing test
   `test_adr_reviewed_questions_only_and_current_status` for the notification; the form state is Requirement 6.*
2. WHEN a clinician issues a new request on an assessment that still has a pending one, THE Notification_Centre SHALL
   report the older request's notification as non-actionable and the newer one as actionable. *Evidence: NEEDS REPRO.
   Observed: actionability reads assessment-level state, which stays `draft` / `request_information` across both
   requests. However 054 `notification_row` already asks for action only on the newest receipt per
   (`source_type`, `source_id`, `event_type`), and both events share the assessment as source, so the older item is
   likely already History on main. If the reproduction passes, Requirement 14.9 applies and the test stays as a
   regression guard; Migration_059 is still needed for Requirement 9 and keeps this result once each request is its
   own source.*
3. WHILE a patient has an older cancelled request's notification in History, THE Notification_Centre SHALL keep its
   unread state unchanged (read is not resolution) and keep its link, which opens the closed state. *Evidence:
   Design (NOT-001 "History items keep their exact-source link").*
4. THE ADR_Database SHALL not delete the cancelled request, its notification or its audit. *Evidence: Observed
   (cancellation sets `status = 'cancelled'`).*
5. WHEN a request becomes cancelled, THE Patient_Portal pending-request entry rows (Requirement 4.4) SHALL disappear on
   the next load. *Evidence: Observed (list endpoint filters `status = 'pending'`).*

### Requirement 14: Migration 059 safety and contract-test coverage

**User Story:** As the requester, I want PR 2 reviewed and verified without touching a remote environment, so that I
decide when to apply it.

#### Acceptance Criteria

1. THE Migration_059 SHALL be a single new file named `059_<snake_case_name>.sql` that passes
   `backend/scripts/validate_migrations.py`, and SHALL not edit any existing migration (the ledger refuses a changed
   file). *Evidence: Observed (CONTRIBUTING.md; 058 is the latest).*
2. THE Migration_059 SHALL be written but not applied to any remote environment, and applying it SHALL require the
   requester's explicit authorization naming that action. *Evidence: Design (AGENTS.md).*
3. THE Migration_059 SHALL redefine changed functions with `CREATE OR REPLACE`, copying the latest definitions (051
   `notification_source`, 054 `notification_actionable`, 055 `capture_notification_source`, 047
   `review_adr_assessment` and `respond_to_adr_information_request`) so that no behaviour of 051 to 058 regresses.
   *Evidence: Observed at `87a466d`: none of these is redefined in 052 to 058. `create_medwatch_draft` (048) and
   `email_preference` (057; 058 only calls it) need no change: the former already cancels pending requests and the
   latter returns NULL, meaning no email, for an unmapped event type.*
4. THE Migration_059 SHALL extend the `notification_events` event-type and source-type allowlists
   (`notification_events_event_type_check`, `notification_events_source_type_check`, inline CHECKs in 051, never
   altered since), keep the append-only trigger, grant RPC execution to `service_role` only, add no DELETE privilege,
   and end with a fail-closed verification block (as 053 does) that raises if a patient-owned ADR or MedWatch
   reference still blocks deletion or a listed role can delete ADR or MedWatch audit rows. *Evidence: Observed (051
   constraints, 053 pattern).*
5. THE PR 2 description SHALL state whether the backend is safe before 059 is applied or requires 059 first, because a
   merge deploys the backend. *Evidence: Observed (TASKS.md: "merge auto-deploys the backend").*
6. THE Contract_Test fixture SHALL apply the ADR-related migrations in ledger (lexicographic) order, including
   `042_auditable_adr_assessments.sql` (before 046), `047_adr_patient_information_loop.sql`,
   `047_care_plan_private_rls_helpers.sql` and `048_medwatch_draft_lifecycle.sql`, and SHALL show that 048 MedWatch
   applies on a fresh database. Tests that assert email behaviour SHALL also apply 057 and 058 in order (pattern:
   `test_email_postgres.py`). *Evidence: Observed. The current fixture applies 046 but not 042 auditable ADR (which
   adds `naranjo_answers`, `naranjo_assessment` and `evidence`, written by the 047 respond RPC), 047 ADR or 048
   MedWatch, and stops at 056; TASKS.md flags the duplicated 047/048 numbers as needing order review.*
7. THE existing contract test `test_adr_reviewed_questions_only_and_current_status` SHALL be migrated to use allowed
   Question_Key values, because 047 rejects free-text questions. *Evidence: Observed (it requests
   `["¿Cuándo comenzó?"]`).*
8. THE Contract_Test SHALL cover: answer then no new request event and non-actionable request (R9); one patient item
   per request (R10); one clinician alert, its routing, isolation, idempotence, rollback and absence of email (R11);
   patient deletion after answering with a MedWatch draft present (R12); and cancel, supersede, reviewed, dismissed and
   draft-prepared end states (R13). *Evidence: Design.*
9. THE Contract_Test for every NEEDS REPRO criterion SHALL fail against unmodified main behaviour before the fix and
   pass after it. IF a criterion does not reproduce, THEN the corresponding schema change SHALL not ship and the test
   SHALL remain as a regression guard. *Evidence: Design (requester instruction; AGENTS.md "do not add schema solely...").*
10. THE unit tests for Migration_059 SHALL assert its key guarantees at text level (pattern:
    `test_adr_patient_information_loop_migration.py`). *Evidence: Observed pattern.*

## PR 3 - MedWatch Form 3500 fidelity, preview and export (migration 060, not applied)

Owner: Rajeev. The requester added this work to the spec on 2026-10-12 and overrode TEAM.md's PV-002 assignment to
Jeevan for it. MediAgent prepares, previews and downloads a Form_3500. The clinician submits it. MediAgent never
transmits a report to the FDA.

Sources read on 2026-10-12: the FDA instructions
(<https://www.fda.gov/safety/medwatch-forms-fda-safety-reporting/instructions-completing-form-fda-3500>) and the
official PDF (<https://www.fda.gov/media/76299/download>). Field names below come from that PDF, shortened by
dropping `topmostSubform[0].` and the `[0]` indexes (for example `Page1.SecA_Patient.PatientIdentifier`). The PDF
nests items B1 to B4 (report type, outcomes, event date, report date) inside the `SecA_Patient` subform, and item
C (product availability) inside `Page3.TestDataTable` (`EvalYes`, `EvalNo`, `EvalRetd`, `ReturnDate`).

### Requirement 15: Form 3500, not 3500A, from a pinned official template

**User Story:** As an assigned clinician, I want MediAgent to produce the current voluntary Form FDA 3500, so that
what I download is the form a health professional files.

#### Acceptance Criteria

1. THE MedWatch_API SHALL identify every MedWatch artifact (JSON and PDF), the stored export version and the
   clinician-visible labels as Form_3500 and SHALL use no 3500A label. *Evidence: Observed. `export_draft` returns
   `artifact_type: "medwatch_3500a_draft"`; 048 defaults `export_version` to `'medwatch-3500a-draft-v1'`; 001
   comments `form_data` as "FDA 3500A field values". The FDA instructions describe 3500 as voluntary reporting by
   health professionals and 3500A as mandatory reporting by manufacturers, importers and user facilities.*
2. THE repository SHALL vendor the Official_Template as a file in the backend source tree, and THE MedWatch_API
   SHALL read the template only from that file and SHALL make no network request for it at runtime. *Evidence: Design.
   Observed: `backend/Dockerfile` copies `src/` into the image, so a template under `src/` ships with the backend.*
3. THE repository SHALL record a pinned template record beside the file: title "FORM FDA 3500", revision 09/2025, OMB
   0910-0291, expiry 09-30-2027, 8 pages, 239 terminal fields, the source URL, the download date and the SHA-256.
   The copy inspected on 2026-10-12 has SHA-256
   `1147d7c86bb002cba7fb9352ca8e3402524d8fa0236916b7bf7e5dcdcf88bf9c` (921,232 bytes). IF a fresh download differs,
   THEN the PR SHALL say so and record the new value. *Evidence: Observed (official PDF: footer "Form FDA-3500
   MedWatch (09/2025)", metadata title `FORM FDA 3500`, 142 text, 83 checkbox and 14 choice fields).*
4. IF the vendored file's SHA-256 differs from the pinned value, or a field name in the field map is absent from the
   template, THEN THE MedWatch_API SHALL refuse the PDF export with an error naming the template mismatch and SHALL
   record no `exported` audit event. *Evidence: Design.*
5. WHEN the current date is after the pinned expiry date, THE Clinician_Portal SHALL show on the preview and the
   download control that the vendored form revision may be superseded, and THE MedWatch_API SHALL continue to export.
   *Evidence: Design. Observed: the form shows an expiry of 09-30-2027.*
6. THE contributor SHALL confirm, before vendoring, that the Official_Template carries no copyright notice, and SHALL
   record in the template README that it is a US government work with no copyright claimed. *Evidence: Design. The
   absence of a notice is not yet verified (V23).*
7. THE backend tests SHALL fail when the template's checksum, revision record or field-name inventory changes without
   the pinned record changing in the same commit. *Evidence: Design.*

### Requirement 16: Structured Form 3500 data model, backward compatible

**User Story:** As an assigned clinician, I want the draft to hold the Form 3500 items a drug report needs, so that
nothing I must report is missing or squeezed into free text.

#### Acceptance Criteria

1. THE MedWatch_API SHALL represent a draft as these Form_3500 sections for a drug report: A (identifier, age with
   unit or date of birth, sex, weight with unit, race, ethnicity); B (B1 report types, B2 outcomes with date of death,
   B3 event date, B4 report date, B5 narrative, B6 tests with dates, B7 other relevant history); D (up to two suspect
   products, fields `Prod1*` and `Prod2*`: name, strength and unit, manufacturer or compounder, NDC or unique ID, lot,
   dose and unit, frequency, route, therapy start, stop and duration, therapy ongoing, reason for use, product type,
   expiration date, dechallenge and rechallenge); F (up to 10 other products with start and end dates,
   `SecF_Other.Table1` rows 1 to 10); and G (reporter name, address, phone, email, health professional, occupation,
   also reported to, identity disclosure). *Evidence: Observed. `MedWatchFormData` (`models/adr.py`) holds only patient
   {identifier, date of birth, sex}, free-text event {description, onset, outcome, seriousness}, one suspect product,
   concomitant products as one comma-separated string, tests and history, and reporter {name, email, specialty, clinic
   name}.*
2. THE MedWatch_API SHALL leave Section C (product availability) and Section E (suspect medical device) blank in every
   artifact, and the PR 3 scope SHALL exclude device reporting. *Evidence: Design (requester scope). Observed: Section C
   is product availability, not a device section (`EvalYes`, `EvalNo`, `EvalRetd`); Section E is `SecE_Device`. With
   D13, the clinician can complete Section C in the downloaded PDF.*
3. IF a saved value for an enumerated item (sex, age and weight units, report type, outcome, route, frequency, dose
   and strength units, product type, dechallenge, rechallenge, health professional, occupation, also reported to) is
   outside the Official_Template's option list or checkbox set, THEN THE MedWatch_API SHALL reject the save with a 422
   naming the field path. *Evidence: Observed (for example `Prod1Route`, `Prod1Freq` with `BID`, `Daily`, `HS`, `PRN`,
   `QID`, `TID`, `Other`; `SecG_Reporter.Occupation` with 12 options; checkboxes `SexF` and `SexM` only).*
4. IF a saved date is not a valid full date or a valid month and year, an event or report date is later than the
   save date, or a therapy stop date precedes its start date, THEN THE MedWatch_API SHALL reject the save with a 422
   naming the field path. *Evidence: Observed (FDA B3: actual date or best estimate, month and year acceptable).
   The expiration date may be in the future.*
5. WHEN THE MedWatch_API reads a draft stored in the 048 shape, THE MedWatch_API SHALL load it with each legacy value
   mapped to its Form_3500 item, every new item blank, and the stored row unchanged until a clinician saves. *Evidence:
   Observed. 048 was applied to `mediagent-staging` on 2026-10-12, so 048-shape drafts may exist; 048 only checks that
   `form_data` is a JSON object.*
6. IF an approved 048-shape draft fails the Requirement 19 gate, THEN THE MedWatch_API SHALL refuse its PDF download
   with a message to discard and prepare a new draft (Requirement 23), and THE MedWatch_API SHALL keep its JSON export
   and preview. *Evidence: Observed. `update_draft` rejects edits unless the status is `draft`.*
7. THE MedWatch_API SHALL keep the Naranjo score, causality and reportability rationale as an internal MediAgent review
   section, shown in MediAgent and in the JSON export, and SHALL write them into no Form_3500 field. *Evidence:
   Observed. The Official_Template has no causality-score field; `update_draft` already rejects score and causality
   edits.*
8. FOR ALL valid Form_3500 draft data, saving then loading SHALL return equal data, and FOR ALL 048-shape payloads,
   loading, saving and loading again SHALL return the same data as the first load. *Evidence: Design (round trip and
   idempotent upgrade).*

### Requirement 17: Non-identifying patient identifier and narrative

**User Story:** As an assigned clinician, I want the patient identifier and narrative to carry no names, so that the
report follows FDA's confidentiality instructions.

#### Acceptance Criteria

1. WHEN a draft is prepared, THE MedWatch_API SHALL set the A1 patient identifier to a default code in the D16 format
   and SHALL not use the patient's name. *Evidence: Observed. `_build_form_data` sets `patient_identifier` to the
   patient's first and last name, and `_approval_missing_fields` requires it. FDA instructions: the identifier is held
   in confidence.*
2. THE default code SHALL reveal no patient UUID, email, phone or date of birth, and SHALL stay the same for the life of
   the draft. *Evidence: Design (D16, decided).*
3. IF a saved A1 identifier equals the patient's full name, contains the first or last name as a whole word, or
   contains the patient's email or date of birth, THEN THE MedWatch_API SHALL reject the save with a 422. Matching
   SHALL ignore case and accents. *Evidence: Design (es-MX names carry accents).*
4. WHEN B5, B6, B7 or F text contains the patient's first or last name, the name of the reporter or another assigned
   clinician, or the reporter's clinic name, THE MedWatch_API SHALL return a warning naming the field and the kind of
   match, and THE Clinician_Portal SHALL show it beside the field. *Evidence: Observed. `_build_form_data` copies the
   symptom report's `notes` verbatim into the event description. FDA B5: do not identify any patient, physician or
   institution by name.*
5. WHEN a clinician approves a draft with unresolved name warnings, THE Clinician_Portal SHALL list each warning in the
   approval dialog, and THE MedWatch_API SHALL record the acknowledged warnings in the `approved` audit event.
   *Evidence: Design.*
6. THE MedWatch_API SHALL write reporter identity (name, address, phone, email, occupation, clinic) only into
   Section G and SHALL write no reporter or clinic name into Sections A, B, D or F during prefill. *Evidence:
   Observed (FDA: reporter identity goes in Section G; today `reporter.clinic_name` is a reporter field only).*

### Requirement 18: Prefill with provenance, never invented

**User Story:** As an assigned clinician, I want each prefilled item to show where it came from and stay editable, so
that I can check it before I sign.

#### Acceptance Criteria

1. WHEN a draft is prepared, THE MedWatch_API SHALL fill each Form_3500 item only from a stored source and SHALL attach
   source evidence (source type, record ID, citation, attribution) for every filled field path. *Evidence: Observed
   (`source_evidence` entries carry `field_paths`, `source_type`, `citation`).*
2. THE MedWatch_API SHALL map: A from the patient profile (date of birth; `gender` `female` to F and `male` to M); B5
   from the symptom report; B7 from active conditions and allergies with reactions; D product 1 from the suspect
   medication record or its source document; F from the patient's other active medications; G name and email from the
   authenticated clinician. *Evidence: Observed (`patients`, `conditions`, `allergies`, `symptom_reports`,
   `medications`, `clinicians` in 001; `_load_source_records`).*
3. IF no stored source holds a value for an item, THEN THE MedWatch_API SHALL leave the item blank and SHALL not derive,
   guess or generate a value, including from model output. This covers A race, ethnicity and weight, G phone, address
   and occupation, and sex for `gender` `other` or `prefer_not_to_say`. *Evidence: Observed. `patients` has no race,
   ethnicity or weight column; `clinicians` has no phone or address column; `gender_enum` is `male`, `female`,
   `other`, `prefer_not_to_say` while the form offers only `SexF` and `SexM`.*
4. WHEN a draft is prepared, THE MedWatch_API SHALL propose B3 from the symptom report `onset` if it parses as a date or
   a month and year, and otherwise from the date of the report's `created_at`, labelled "Best estimate, confirm" with its
   source. *Evidence: Observed. `symptom_reports.onset` is free text, copied verbatim into `onset_date_or_time` today.
   FDA B3 accepts a best estimate.*
5. WHEN the assessment holds Naranjo answers for `improved_on_dechallenge` or `reappeared_on_rechallenge`, THE
   MedWatch_API SHALL map yes to Yes and no to No in D "event abated after use stopped or dose reduced"
   (`Prod1AbatedYes/No`) and "event reappeared after reintroduction" (`Prod1ReappearYes/No`), SHALL leave the item
   blank for an unknown or absent answer, and SHALL label the source per entry as Requirement 7.1 does. *Evidence:
   Observed. Only `reappeared_on_rechallenge` is patient-answerable (`PATIENT_ANSWERABLE_NARANJO_QUESTIONS`), so a
   dechallenge answer can only be AI-extracted or clinician-entered.*
6. THE MedWatch_API SHALL attribute each assessment evidence entry by its own `source` and SHALL not label an entry
   without `source: "patient_follow_up"` as patient-confirmed. *Evidence: Observed. `_build_form_data` gives every
   `assessment.evidence` entry `source_type: "patient_confirmed_adr_evidence"`, including AI-extracted entries.*
7. WHERE approved clinical facts of a laboratory kind exist for the patient, THE MedWatch_API SHALL prefill B6 with the
   test, result and date and their provenance. *Evidence: Inferred. No lab table exists in the migrations; Observed in design: no
   migration creates a lab-result table, and `clinical_facts` stores FHIR Observations as `fact_type = 'observation'`
   without the Observation category, so a laboratory result cannot be told apart from a vital sign or survey answer.
   The WHERE condition is therefore never met in PR 3, and B6 stays blank for the clinician to complete.*
8. WHILE a draft has status `draft`, THE Clinician_Portal SHALL keep every prefilled item editable, and THE MedWatch_API
   SHALL record each edit in `clinician_edited_fields` and the `edited` audit event. *Evidence: Observed
   (`update_draft`, `_changed_leaf_paths`).*

### Requirement 19: Approval gate aligned with Form 3500

**User Story:** As an assigned clinician, I want approval blocked until the items FDA needs are complete, so that an
approved draft can actually be filed.

#### Acceptance Criteria

1. WHEN a clinician approves a draft, THE MedWatch_API SHALL refuse approval and list every missing item unless the
   stored revision has: A1 identifier; at least one B1 report type; B3 event date confirmed by the clinician; B5
   narrative; D product 1 name; G reporter first and last name, a phone or email, the health-professional answer and
   occupation; and the reportability rationale. *Evidence: Observed. `_approval_missing_fields` checks only identifier,
   event description, suspect product, reporter name and rationale.*
2. IF B2 Death is checked and the date of death is blank, THEN THE MedWatch_API SHALL refuse approval. *Evidence:
   Observed (FDA B2: death with date; fields `Death`, `DeathDate`).*
3. IF no B2 outcome is checked, THEN THE MedWatch_API SHALL refuse approval unless the clinician gives the D12
   non-serious attestation, and THE MedWatch_API SHALL record that attestation in the `approved` audit event.
   *Evidence: Observed (FDA asks reporters to limit submissions to serious events). D12 decided.*
4. THE MedWatch_API SHALL evaluate the gate, including the Requirement 17.3 identifier rule, on the stored revision
   named by `expected_revision`, not on client-supplied form data. *Evidence: Observed (`approve_draft` validates the
   stored `form_data`).*
5. THE MedWatch_API SHALL return the missing-item list with each draft, and THE Clinician_Portal SHALL show that list
   before the clinician opens the approval dialog. *Evidence: Design (one rule, shown before and enforced at approval).*
6. THE Clinician_Portal SHALL show attestation text stating that approval makes the draft exportable as Form FDA 3500,
   that the clinician submits it, that MediAgent does not submit it to the FDA, and that the clinician is responsible
   for its content. THE MedWatch_API SHALL record the attestation text version in the `approved` audit event.
   *Evidence: Observed. `MedWatchDraftApprovalRequest` carries only `attested: bool` and a note.*

### Requirement 20: Read-only Form 3500 preview

**User Story:** As an assigned clinician, I want to see the draft laid out like Form 3500 before and after approval,
so that I can check it the way FDA will read it.

#### Acceptance Criteria

1. WHEN an assigned clinician opens the preview of a draft in any status, THE Clinician_Portal SHALL show Sections A, B,
   C, D, E, F and G in form order with item labels and numbers taken from the Official_Template, and SHALL show C and E
   as not completed by MediAgent. *Evidence: Observed. The draft card (rebuilt in task 8.1) is an editable grouped form;
   no read-only Form 3500 preview exists.*
2. THE Clinician_Portal SHALL show each item's provenance (record source, AI-extracted, patient-confirmed or clinician
   edited) beside the item. *Evidence: Design (Requirements 7 and 18).*
3. THE Clinician_Portal SHALL show each blank item as "Not provided" and SHALL omit the FDA-use-only fields
   (`Header.RecDate`, `Header.TriageNum`). *Evidence: Observed (these fields are for FDA receipt).*
4. WHILE a draft has status `draft`, THE Clinician_Portal SHALL mark each item missing for approval with a text label
   as well as colour. *Evidence: Design.*
5. THE Clinician_Portal SHALL show the Naranjo review in a separate panel labelled as MediAgent review and not part of
   Form 3500. *Evidence: Design (Requirement 16.7).*
6. WHEN the preview is printed, THE Clinician_Portal SHALL print every section on US Letter paper without navigation
   and SHALL print "Not submitted to FDA by MediAgent" on each page. *Evidence: Design.*
7. THE preview SHALL contain no input controls and SHALL satisfy Requirement 1. *Evidence: Design.*

### Requirement 21: Official PDF download

**User Story:** As an assigned clinician, I want to download the approved draft as the official fillable Form 3500
PDF, so that I can review it and submit it myself.

#### Acceptance Criteria

1. WHEN an assigned clinician requests the PDF of a draft whose status is approved (`reviewed`) or that has an
   External_Submission_Record, THE MedWatch_API SHALL return the Official_Template filled from the stored revision.
   IF the draft is not approved, THEN THE MedWatch_API SHALL refuse with a 422. *Evidence: Observed (`export_draft`
   accepts only `reviewed` with `approved_at`).*
2. THE MedWatch_API SHALL write each mapped value to both the AcroForm field and the matching XFA `datasets` element,
   and SHALL re-encrypt the output with the template's original permissions, including fill and print. *Evidence:
   Observed. The template is an Adobe LiveCycle hybrid form (AcroForm and XFA), encrypted with an owner password and
   no user password. A pypdf 6.20.1 fill test that wrote both rendered page 1 with the values; viewers disagree when
   only one is written.*
3. THE MedWatch_API SHALL write full dates as `dd-mmm-yyyy` with English month abbreviations (for example
   `03-Oct-2026`), checked boxes as `/1` with all others `/Off`, and choice fields only with a value from the
   template's option list. *Evidence: Observed (field tooltips: 2-digit day, 3-letter month, 4-digit year; checkbox
   states `/1` and `/Off`).*
4. THE MedWatch_API SHALL return the PDF fillable, not flattened, with FDA-use-only fields blank. *Evidence: Design (D13,
   decided).*
5. THE MedWatch_API SHALL add no text to any official field or page. THE Clinician_Portal SHALL state "MediAgent did not
   submit this report" beside the download control and in the download confirmation, and the filename SHALL contain
   `fda-3500`, `not-submitted` and no patient name. *Evidence: Design (D14, decided; the PDF metadata note is part of
   D14).*
6. WHEN a PDF or JSON export is returned, THE MedWatch_API SHALL record one `exported` audit event with the format and,
   for a PDF, the template revision and SHA-256. *Evidence: Observed. `record_medwatch_draft_export(uuid, uuid)` takes
   no format argument.*
7. FOR ALL valid approved drafts, filling the template then reading back the AcroForm values and XFA `datasets` SHALL
   return the mapped value for every mapped field and blank for every unmapped field. *Evidence: Design (round trip).*
8. THE MedWatch_API SHALL fill the PDF with `pypdf` and SHALL not use PyMuPDF for this path. *Evidence: Observed.
   PyMuPDF is AGPL and already a backend dependency (`requirements.in`; `pymupdf==1.28.2`) for document ingestion and
   preview (see Out of scope).*
9. THE MedWatch_API SHALL keep the JSON export as a secondary download, labelled Form_3500, with
   `not_submitted_to_fda: true`. *Evidence: Observed (current JSON content).*

### Requirement 22: Record a submission made outside MediAgent

**User Story:** As an assigned clinician, I want to record that I submitted the report to FDA myself, so that the
draft shows it was filed and cannot be changed afterwards.

#### Acceptance Criteria

1. WHILE a draft is approved and has no External_Submission_Record, THE MedWatch_API SHALL let the assigned clinician
   record the submission date, method (MedWatch Online, fax, mail or other with a description), an optional FDA
   confirmation or reference number, and an attestation that the clinician submitted it outside MediAgent. *Evidence:
   Design.*
2. IF the submission date is in the future or earlier than the approval date, or the attestation is false, THEN THE
   MedWatch_API SHALL reject the record with a 422. *Evidence: Design.*
3. THE MedWatch_API SHALL send no request to any FDA system when a submission is recorded, and the codebase SHALL
   contain no path that transmits a report. *Evidence: Observed (PROJECT.md: submitting a regulatory report is
   "Prohibited").*
4. WHEN a submission is recorded, THE ADR_Database SHALL store the External_Submission_Record and an append-only
   `submission_recorded` audit event in one transaction. *Evidence: Design. Observed: 048 audit event types are
   `created`, `edited`, `approved`, `exported`.*
5. WHILE a draft has an External_Submission_Record, THE MedWatch_API SHALL reject edit, approval and discard, and THE
   Clinician_Portal SHALL show it read-only with "Submitted by <clinician> outside MediAgent on <date>". *Evidence:
   Observed. `list_drafts` returns only `draft` and `reviewed`, so a submitted row would vanish from the queue today.*
6. THE Migration_060 SHALL replace `medwatch_drafts_not_submitted_by_app` with a constraint that allows the submitted
   state only when the row has approval and a complete External_Submission_Record. *Evidence: Observed. The 048 CHECK
   is `status = 'submitted' OR submitted_at IS NULL`; it ties `submitted_at` to the status but does not stop a
   `submitted` status, and `service_role` holds ALL on the table.*
7. IF a recorded submission contains a mistake, THEN THE MedWatch_API SHALL let the assigned clinician correct the date,
   method or reference only through an amendment with a required reason, keeping the original record and recording an
   append-only `submission_amended` audit event. *Evidence: Design (D17, decided).*

### Requirement 23: Discard and reopen a draft

**User Story:** As an assigned clinician, I want to discard a mistaken draft and return the assessment to review, so
that I can review it again or prepare a correct draft.

#### Acceptance Criteria

1. WHILE a draft has status `draft`, or is approved without an External_Submission_Record (D15), THE MedWatch_API SHALL
   let the assigned clinician discard it with a required reason of 1 to 2000 characters. *Evidence: Observed. No discard
   exists; this was D8, now in scope. D15 decided.*
2. WHEN a draft is discarded, THE ADR_Database SHALL keep the row, mark it discarded with the actor, time and reason,
   and record an append-only `discarded` audit event. *Evidence: Design.*
3. WHEN a draft is discarded, THE ADR_Database SHALL return its ADR assessment to `draft` in the same transaction and
   record an ADR audit event, so that the clinician can review it again or prepare a new draft. *Evidence: Observed.
   `create_medwatch_draft` sets the assessment to `reviewed` with `last_review_action = 'mark_reviewed'`.*
4. THE ADR_Database SHALL allow at most one non-discarded draft per assessment. *Evidence: Observed.
   `idx_medwatch_one_draft_per_assessment` is unique on `adr_assessment_id`, and `create_draft` rejects any existing
   draft.*
5. IF a draft has an External_Submission_Record, THEN THE MedWatch_API SHALL refuse to discard it. *Evidence: Design.*
6. WHEN a discard returns an assessment to `draft`, THE Notification_Centre SHALL show assigned clinicians one actionable
   `adr_review` item, SHALL make no patient `adr_information_requested` item actionable again, and SHALL queue no
   email. *Evidence: Inferred. 055 captures `adr_review` when the old status is not `draft`; 054 treats `adr_review` as
   actionable while the status is `draft`; the patient predicate needs `last_review_action = 'request_information'`;
   057 maps no email category to `adr_review`. Confirm in the Contract_Test.*
7. THE discarded state SHALL not reuse `submitted`. THE Migration_060 SHALL account for the PostgreSQL rule that an enum
   value added by `ALTER TYPE ... ADD VALUE` cannot be used in the transaction that adds it. *Evidence: Observed
   (`medwatch_status_enum` is `draft`, `reviewed`, `submitted` in 001).*
8. THE MedWatch_API SHALL apply `expected_revision` to discard, and THE Clinician_Portal SHALL list discarded drafts
   read-only, apart from the active queue. *Evidence: Observed (all 048 write RPCs use optimistic revision).*

### Requirement 24: Authorization, deletion, Migration 060 safety and delivery

**User Story:** As the requester, I want PR 3 to keep access, deletion and migration safety at the PR 2 standard, so
that I can approve it without touching a remote environment.

#### Acceptance Criteria

1. THE MedWatch_API SHALL allow preview, PDF download, submission record, amendment and discard only to a clinician
   with an active care-team assignment to the patient, SHALL answer 403 to an unassigned clinician, and SHALL answer
   404 for a missing draft. *Evidence: Observed (`_get_authorized_draft` raises `AuthorizationError` for an
   unassigned clinician). Inferred: a missing draft ID likely returns 500 today, because `.single()` raises an unmapped
   PostgREST error (as in Requirement 6.3).*
2. THE Migration_060 SHALL make every new table or column holding patient data cascade on patient deletion, as
   Requirement 12 does, and SHALL reference clinicians (recorder, amender, discarder) with `ON DELETE RESTRICT` until D1
   is decided, with the new references added to NOT-003. *Evidence: Observed (048 clinician references are RESTRICT;
   NOT-003).*
3. THE Migration_060 SHALL be one file named `060_<snake_case_name>.sql` that passes
   `backend/scripts/validate_migrations.py`, is ordered after 059 and states in its header that it requires 059. It
   SHALL be written but not applied, and applying it SHALL require the requester's explicit authorization naming that
   action. *Evidence: Design (060 relies on 059's patient cascade and revoked audit DELETE).*
4. THE Migration_060 SHALL grant RPC execution to `service_role` only, re-check the active assignment inside each RPC
   as 048 does, extend the MedWatch audit event types, keep audit tables append-only with no DELETE or TRUNCATE for
   `anon`, `authenticated` or `service_role`, and end with a fail-closed verification block. *Evidence: Observed (048
   RPCs check `status = 'active'` assignments; 053 verification pattern).*
5. THE backend SHALL pin `pypdf==6.20.1` in `backend/requirements.in`, and THE contributor SHALL regenerate
   `requirements.txt` and `requirements-dev.txt` with the CI `uv pip compile` commands so that the lock check and
   `pip-audit` pass. *Evidence: Observed (`.github/workflows/ci.yml` recompiles and runs `git diff --exit-code`;
   the Dockerfile installs `requirements.txt`). pypdf is BSD-licensed and pure Python.*
6. THE PR 3 description SHALL state whether the backend is safe before 060 is applied or requires 060 first.
   *Evidence: Observed (TASKS.md: a merge auto-deploys the backend).*
7. THE Contract_Test SHALL cover discard and return to review, one active draft, the submitted-state constraint, the
   External_Submission_Record and amendment audit, patient deletion with PR 3 data, and append-only audit. *Evidence:
   Design.*
8. WHEN PR 3 implementation starts, THE contributor SHALL update `.agent/TASKS.md` (PV-001-C and PV-002 rows, schema
   row with 060 not applied) to record Rajeev as PR 3 owner and the requester's 2026-10-12 override of TEAM.md's
   PV-002 assignment to Jeevan. *Evidence: Observed (TEAM.md: Jeevan owns PV-002; TASKS.md PV-002 owner "Ganesh (#150);
   Jeevan review").*
9. THE PR 3 changeset SHALL contain exactly one new migration, numbered 060. *Evidence: Design.*

## Out of scope and adjacent observations (not requirements)

Recorded so reviewers do not read them as hidden scope.

- **Discarding a MedWatch draft:** moved into PR 3 (Requirement 23; D8 now decided in scope). It is not part of 059.
- **PyMuPDF licence (adjacent):** the backend already pins `pymupdf==1.28.2` (AGPL) for document ingestion and preview
  (`document_preview_service.py`, `document_intelligence/pipeline.py`, `agents/ingestion/graph.py`). PR 3 does not use
  it (Requirement 21.8). Reviewing the existing dependency's licence is outside this spec.
- **Requirement 2.2 evidence wording:** the 048 CHECK `medwatch_drafts_not_submitted_by_app` does not by itself stop a
  `submitted` status (Requirement 22.6). For PR 1 and PR 2, the guarantee comes from no code path setting it.
- **Form 3500 Section C and Section E, and Form 3500A:** not prepared by MediAgent (Requirement 16.2).
- **Other MedWatch observations, no defect found at this reading:** save, approve and export errors already appear
  inline in the card; export is a local JSON download; approval requires attestation and a note; the page header band
  already matches Risk Radar.
- **Patient API exposes score fields:** `ADRInformationRequestRead` returns `current_naranjo_score` and
  `current_causality` to the patient client, which never renders them. Removing them is data minimisation, outside the
  ten gaps (decision D11).
- **Extraction re-run risk (unverified):** `a2a_task_service.py` upserts `adr_assessments` on `symptom_report_id` with
  `status: "draft"`, AI `evidence` and `naranjo_answers`. If that task reruns for a symptom report that already has a
  patient answer or a review, it could overwrite them. It also touches `updated_at`, which relates to R9.4. Not
  investigated.
- **Request expiry:** no expiry exists today (decision D4).
- **Page-level disabled-text hex** `text-[#94A3B8]` on the MedWatch page repeats the shared Button's value; left as is.
- **Clinician UI for choosing questions** (`adr-review-actions.tsx`) is unchanged.
- **Legacy notifications API:** `GET /api/v1/notifications/` still returns `public.notifications` rows, including
  existing English ADR rows. No portal client calls it at `87a466d`. Retiring it is outside the ten gaps.
- **Email after #157:** the branding change does not touch ADR categories or copy. `adr_information_requested`
  keeps the `records` email category (057); the new clinician alert maps to no category.

## Decisions

D1 to D11 recorded with the requester's approval on 2026-10-12; D8 updated the same day. The requester accepted D12
to D17 for PR 3 on 2026-10-12, exactly as proposed.

| ID | Status | Decision | Outcome | Affects |
| --- | --- | --- | --- | --- |
| **D1** | **Open** | Clinician-deletion policy for MedWatch drafts and ADR audit (TASKS.md NOT-003) | Unchanged by this work. Options remain: (a) keep records, NULL the clinician reference, keep a name snapshot (as 053); (b) delete the clinician's authored drafts and audit; (c) keep blocking deletion until ownership is reassigned. | R12.5, NOT-003 |
| **D2** | Decided | Do draft answers persist across reload? | (a) No. Unsent answers live only in component state; the form shows a visible note near Send. | R6.8 |
| **D3** | Decided | Is the clinician "patient answered" alert actionable? | (b) Informational, History-only, unread in the bell, not in Needs attention. | R11.5 |
| **D4** | Decided | Do requests expire? | No expiry now. | none |
| **D5** | Decided | History shown to the patient | Last 5 requests within 90 days, collapsed, newest first. | R6.1, R6.5 |
| **D6** | Decided | Does Today also carry an entry row? | Entry row in both the chat inbox and Today, only while a request is pending. | R4.4 |
| **D7** | Decided | Who receives the answered alert? | (a) Shared with all currently assigned clinicians. | R11.3 |
| **D8** | Decided: in scope (PR 3) | Can a MedWatch draft be discarded or reopened? | Yes, in PR 3 (requester, 2026-10-12): discard with a reason returns the assessment to review. | R23 |
| **D9** | Manual requester item | Spanish wording sign-off | A Spanish-fluent reviewer named by the requester signs off (V13). | R3.6, R5 |
| **D10** | Decided | Does answering mark the request's notification read? | Yes. | R9.3 |
| **D11** | Decided (later) | Remove unused score fields from the patient read model? | Later, as data minimisation. | none |
| **D12** | Decided (2026-10-12) | Non-serious events (no B2 outcome): block approval, or allow with attestation? | Allow with an explicit, audited clinician attestation that the event is not serious and is reported anyway. FDA's "please limit" is guidance, not a prohibition. | R19.3 |
| **D13** | Decided (2026-10-12) | Downloaded PDF fillable or flattened? | Fillable, so the clinician can complete or correct it (including Section C) before submitting. | R21.4 |
| **D14** | Decided (2026-10-12) | How is the PDF marked as not submitted by MediAgent? | No overlay on official fields or pages; state it in the UI, the download confirmation, the filename, and a PDF document-metadata note only. | R21.5 |
| **D15** | Decided (2026-10-12) | Can an approved draft be discarded? | Yes, until an External_Submission_Record exists. | R23.1 |
| **D16** | Decided (2026-10-12) | Default A1 identifier format | Patient initials plus a 4-character local reference that reveals no UUID, email, phone or date of birth. | R17.1, R17.2 |
| **D17** | Decided (2026-10-12) | Correcting a mistaken External_Submission_Record | An audited amendment of date, method or reference with a reason, keeping the original; no withdrawal of the record. | R22.7 |

## Verification plan

Evidence is recorded in the PR with exact commands and outcomes. Items marked **Requester** need the requester or a
named human; they stay open until recorded.

Environment set-up (once per worktree; `backend/.venv` and the apps' `node_modules` did not exist in this worktree
at `87a466d` and were created for task 10). CI uses Python 3.12 and Node 20; task 10 ran on Python 3.12.11 and Node
24.3.0, so the portal results are a local proxy for the Node 20 CI jobs:

```bash
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cd apps/patient-portal && npm ci
cd apps/clinician-portal && npm ci
```

`pyproject.toml` adds `--cov-fail-under=80` to every pytest run, so focused runs pass `--no-cov` (as
`backend/README.md` does for the opt-in PostgreSQL suites).

| # | Check | Command / method | PR | Evidence type |
| --- | --- | --- | --- | --- |
| V1 | Python style (CI scope) | `cd backend && .venv/bin/ruff check src/ scripts/ && .venv/bin/ruff format --check src/ scripts/`. CI does not lint tests; also run `ruff check` and `ruff format --check` on the touched test files | 1, 2, 3 | Run output |
| V2 | Python types | `cd backend && .venv/bin/mypy src/ --ignore-missing-imports` | 1, 2, 3 | Run output |
| V2a | Production placeholder check (CI job) | `python3.12 backend/scripts/check_production_placeholders.py` from the repository root (exempts `__init__.py`, so an empty package marker passes) | 1, 2, 3 | Run output |
| V3 | Focused backend tests | `cd backend && SUPABASE_URL=https://test.supabase.co SUPABASE_ANON_KEY=test-anon-key SUPABASE_SERVICE_ROLE_KEY=test-service-role-key SUPABASE_JWT_SECRET=test-jwt-secret-for-ci PYTHONPATH=src .venv/bin/pytest tests/unit/services/test_notification_centre_presentation.py tests/unit/services/test_patient_service.py tests/unit/services/test_clinician_service.py tests/unit/db tests/integration/routers/test_patient_api.py tests/integration/routers/test_clinician_api.py --no-cov -q` (state it is focused) | 1, 2 | Run output |
| V3a | Full backend suite with coverage (CI `backend-coverage` job, without the Docker opt-ins) | `cd backend && SUPABASE_URL=https://test.supabase.co SUPABASE_ANON_KEY=test-anon-key SUPABASE_SERVICE_ROLE_KEY=test-service-role-key SUPABASE_JWT_SECRET=test-jwt-secret-for-ci .venv/bin/pytest tests/ -v -rs --tb=short` (`--cov-fail-under=80` comes from `pyproject.toml`). CI also sets `CARE_CONVERSATION_TEST_POSTGRES_DOCKER=1` and `NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER=1` and requires non-skipped Docker cases; a run without them reports those suites as skipped, and the Docker suites are recorded separately (V6). Local PostgreSQL binaries (`initdb`) are needed for `test_appointment_offer_transactions.py`; macOS can exhaust SysV shared-memory IDs (`shmget` "No space left on device"), which fails its 31 tests at setup until leaked segments are removed. | 1, 2, 3 | Run output with totals and coverage |
| V4 | Migration validator | `cd backend && .venv/bin/python scripts/validate_migrations.py` (CI runs it on every PR). PR 1 also shows it adds no migration: `git status --short \| grep -i '\.sql'` prints nothing. Do not use `git diff --name-only origin/main` for this once `origin/main` has moved: it lists migrations merged to `main` after the branch point; use `git merge-base HEAD origin/main` as the base | 1, 2, 3 | Run output |
| V5 | Migration text tests | `cd backend && PYTHONPATH=src .venv/bin/pytest tests/unit/db/test_adr_loop_gap_fixes_migration.py --no-cov -q` | 2 | Run output |
| V6 | PostgreSQL contract tests (R9 to R13) | Baseline (unmodified behaviour, no 059): `cd backend && NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER=1 ADR_LOOP_GAP_BASELINE=1 PYTHONPATH=src .venv/bin/pytest tests/integration/test_adr_loop_postgres.py --no-cov -v`. Fixed: the same command without `ADR_LOOP_GAP_BASELINE=1`. Regression: `NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER=1 PYTHONPATH=src .venv/bin/pytest tests/integration/test_notification_centre_postgres.py --no-cov -q` and `EMAIL_TEST_POSTGRES_DOCKER=1 PYTHONPATH=src .venv/bin/pytest tests/integration/test_email_postgres.py --no-cov -q`. Opt-in; cached `postgres:16`, `--network=none`; fixture extended per R14.6. **The baseline run comes first and its failures for G6, G7, G9 and the superseded case of G10 are recorded.** | 2 | Run output, including the baseline result |
| V7 | Patient portal | `cd apps/patient-portal && npm run lint && npm run typecheck && npm run test && npm run build` | 1 | Run output |
| V8 | Clinician portal | `cd apps/clinician-portal && npm run lint && npm run typecheck && npm run test && npm run build` | 1 | Run output |
| V9 | Token and palette check | The two V9 commands below the table print nothing | 1 | Run output |
| V10 | Locale parity and wording tests | Copy-key parity test; presentation tests for all three keys in both locales; exhaustive table test over generated `requested_information` values (R5.2; no property-testing library is a dependency, see design) | 1 | Run output |
| V11 | Contrast record | Computed ratio for each text / background token pair on changed surfaces (script or devtools) | 1 | Recorded table |
| V12 | Authenticated manual checks, synthetic accounts | Patient in `en-US` and `es-MX` at 320, 360 and 430 px: notification to form, chat-inbox and Today rows, answer, review, send, answered and closed states, keyboard-only pass including hidden radios, 200% zoom, reduced motion, safe areas. Clinician at 1024, 1280 and 1536 px: ADR card provenance (AI, patient, mixed), MedWatch prepare, edit, refresh with unsaved edits, approve, export, answered alert from the bell. | 1, 2 | **Requester** (screenshots per R1.19) |
| V13 | Spanish copy review | Fluent reviewer signs off es-MX question, caution, confirmation and notification wording | 1 | **Requester** |
| V14 | Apply 059 to a remote environment | Not done by this work; needs explicit authorization naming the action | 2 | **Requester** |
| V15 | Tracker and docs | TASKS.md rows, NOT-001 spec, patient-portal README updated as in R2.5, recording 048 MedWatch applied to `mediagent-staging` on 2026-10-12 (ledger synchronized through 058) and 059 not applied anywhere | 1, 2 | Diff review |
| V16 | Dependency lock and audit | After adding `pypdf==6.20.1` to `requirements.in`: `cd backend && uv pip compile requirements.in --universal --python-version 3.12 --output-file requirements.txt && uv pip compile requirements-dev.in --universal --python-version 3.12 --output-file requirements-dev.txt && git diff --stat -- requirements.txt requirements-dev.txt`, then `uvx --from pip-audit==2.10.1 pip-audit -r requirements-dev.txt` (as CI; `uv` 0.9.24 as pinned in CI). CI runs `git diff --exit-code` after recompiling, which is meaningful only once the lockfiles are committed; before that, copy both files first and `cmp` them with the recompiled output | 1, 3 | Run output |
| V17 | Python style, types and focused tests | V1 and V2, plus `cd backend && PYTHONPATH=src .venv/bin/pytest tests/unit/services/test_medwatch_service.py tests/unit/services/test_medwatch_form_3500.py tests/integration/routers/test_clinician_api.py --no-cov -q` (file names fixed in design; state the run is focused) | 3 | Run output |
| V18 | Template pin and PDF read-back | Template checksum, revision record and field-inventory test (R15.7); fill then read-back of every mapped AcroForm field and XFA `datasets` element over generated drafts (R21.7); 048-shape load and round trip (R16.8) | 3 | Run output |
| V19 | Migration 060 validator and text tests | V4, plus `cd backend && PYTHONPATH=src .venv/bin/pytest tests/unit/db/test_medwatch_form_3500_migration.py --no-cov -q` (name fixed in design) | 3 | Run output |
| V20 | PostgreSQL contract tests (R22 to R24) | V6 commands with 059 and 060 applied in ledger order, covering R24.7 | 3 | Run output |
| V21 | Clinician portal | V8 commands; component tests for the preview, missing-item list, approval attestation, PDF download notice, submission record, amendment and discard | 3 | Run output |
| V22 | Manual PDF check, synthetic draft | Requester opens a downloaded PDF in Adobe Acrobat Reader and macOS Preview, confirms values show in both, the form stays fillable and printable, and no official field carries added text | 3 | **Requester** |
| V23 | Template provenance | Contributor confirms the Official_Template carries no copyright notice and records the source URL, download date and SHA-256 (R15.3, R15.6) | 3 | Recorded note |
| V24 | Apply 060 to a remote environment | Not done by this work; needs explicit authorization naming the action | 3 | **Requester** |

V9 commands, from the repository root. The MedWatch page keeps its two known `text-[#94A3B8]` disabled-text values
(see Out of scope), so it is checked for palette classes only.

```bash
grep -nE '#[0-9A-Fa-f]{3,8}\b' apps/patient-portal/src/components/features/adr-follow-up-*.tsx \
  apps/clinician-portal/src/components/features/adr-review-card.tsx \
  apps/clinician-portal/src/components/features/medwatch-draft-card.tsx \
  apps/clinician-portal/src/components/features/medwatch-preparation-action.tsx
grep -nE '\b(gray|slate|blue|indigo|amber|green|red|emerald)-[0-9]{2,3}\b' \
  apps/patient-portal/src/components/features/adr-follow-up-*.tsx \
  apps/clinician-portal/src/components/features/adr-review-card.tsx \
  apps/clinician-portal/src/components/features/medwatch-draft-card.tsx \
  apps/clinician-portal/src/components/features/medwatch-preparation-action.tsx \
  "apps/clinician-portal/src/app/(dashboard)/medwatch/page.tsx"
```
