# UX-002 — Reference overhaul verification

Scope: visual, layout and interaction polish for both portals against the
approved reference (`MediAgent Redesign`, Profile & Clinic settings) and
[the specification](../.agent/specs/ux-002-reference-redesign.md). Routes, API
calls, Redux state, handlers, approval gating, clinical text and safety copy are
unchanged. Synthetic demo data only.

## Patient portal (mobile)

- Foundation: cleaned tokens and motion, shared icon set, bottom-sheet modal,
  overflow menu (Refresh stays keyboard-reachable beside pull-to-refresh), list,
  icon-tile and large-title primitives, shimmer skeletons, opt-in disclosures.
- Today: next-up card with one approval seal, status pill with clock time,
  segmented progress, clamped schedule rows (long care-plan titles no longer
  collapse into a narrow column), tinted activity tiles, 44px hit areas.
- Records: cleaned display titles (full filename kept in the sheet), typed
  tiles, readable subtitles, Summary/Reading chips, quieter detail sheet.
- Chat: assistant card, care-team contacts with unread dots, assistant and
  care-team threads with sticky headers, single-row composer, shortened
  connection status (Connected / Connecting… / Offline).
- Profile, Visits, Reminders, Symptoms, entry screens: grouped settings lists,
  reference identity card, language sheet, compact schedule summaries.

## Clinician portal (desktop)

- Tokens: raw palette classes mapped to semantic ink, line, primary, AI, ok,
  risk and warn tokens; shared button, badge, input, table, modal, popover,
  segmented control and compact field primitives.
- Shell: dark rail sidebar with counts from loaded data, breadcrumb header,
  fluid workspace.
- Risk Radar header band with static perspective floor, segmented risk filter,
  compact selects, expanding search, animated re-sort; roster on the same table.
- Patient detail strip and underline tabs; care-plan review as publishing
  stepper (Before publishing in an info popover, requirement lines visible),
  item list, editor with side-by-side overlap comparison, protected source
  pane, file-type badges, sticky approval bar with unchanged gating.
- ADR reviews, review queue, documents, upload, appointments, messages,
  settings, MFA, external record import, adherence/symptom charts and entry
  screens with the supervised-flow illustration.

## Checks recorded October 10, 2026

| Command (run in each app) | Patient | Clinician |
| --- | --- | --- |
| `npx eslint src` | Pass | Pass |
| `npx tsc --noEmit -p .` | Pass | Pass |
| `npx vitest run` | 420 passed, 49 files | 262 passed, 39 files |
| `npx next build --webpack` | Pass (14 routes) | Pass (17 routes) |

Manual browser review against the local backend with the synthetic demo
accounts: patient screens at 390px and 360px (no horizontal overflow on Today,
Records, Chat, Visits, Profile, Reminders); clinician screens at 1440px and
1024px. Tests that asserted old class names or exact split text were updated
to the new presentation only.

## Follow-up (resolved)

Resolved by LOC-001 (#145): care-plan wording is drafted and approved in en-US and
es-MX together; see
[the LOC-001 spec](../.agent/specs/loc-001-bilingual-approved-wording.md).
