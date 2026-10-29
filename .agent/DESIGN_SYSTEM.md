# MediAgent — Design system

## Canonical visual reference

The approved UX-002 redesign replaces the previous palette, typography, hero cards
and layout conventions. Do not combine it with the abandoned portal-theme draft.

Read [the implementation handoff](specs/ux-002-reference-redesign.md) and
[brand-icon integration](../docs/brand-icons.md) before changing either portal.
The requester-supplied animated reference is
[the MediAgent redesign](https://claude.ai/artifact/97piWWCbSeiGMFWEUkeJ5d).
The handoff provides exact tokens and component values. The updated reference adds
clinician sign-in layers and motion demonstrations. Where these differ materially,
record the decision before implementation; do not silently invent a new design.

[Profile & Clinic settings](https://claude.ai/artifact/HWCwWAVWQCp3aGGk5Abp1Q)
supplements that reference for those two screens. Keep their existing fields,
handlers and permissions; sample values in mockups must not become product data.

## Delivery sequence

1. Foundation: brand assets, Geist/Geist Mono, role-specific tokens, shared icons,
   approval seal, AI chip, motion primitives and saved language in Profile.
2. Patient screens: mobile-first Today, Records, chat inbox/threads, navigation,
   Visits, Profile and entry screens.
3. Clinician screens: desktop-first shell, Risk Radar, roster, care-plan review,
   ADR, appointments, messages, settings and entry screens.

Each PR leaves both apps working. Screen-specific layouts do not belong in the
Foundation PR. Track scope and evidence in [TASKS.md](TASKS.md).

## Shared identity, different composition

- Patient: warm sand canvas, near-white surfaces, emerald actions and restrained
  gold Nora accents. Mobile PWA shell, thumb-friendly navigation, next action first.
- Clinician: dark navy sidebar, light fluid workspace, blue primary actions and
  teal approval states. Dense but readable tables and efficient review panes.
- Geist for prose; Geist Mono only for times, versions, counts, scores and eyebrows.
- Use the supplied M-check assets unchanged. No recoloring or replacement marks.
- Use tokens from each app's globals.css, not competing ad hoc palettes.
- A check seal communicates actual clinician approval/verification. A sparkle chip
  identifies AI-produced content. Never substitute one for the other.
- Records override (requester-approved October 29, REC-001-UX): document-type
  tiles and file-format chips use neutral tokens in both portals. Shape identifies
  type, with visible type and uploader labels; unknown types use the file icon.
  Source-review badges state approval in words. Completed parsing stays neutral
  so processing success cannot be mistaken for clinical approval.

## Motion and depth

Motion explains real state changes, processing and orientation. Follow the handoff
and updated reference timing. No fake live indicators, count-up risk values,
confetti, parallax or scroll-jacking. No 3D transforms in the patient app.
Clinician decoration is limited to the sign-in layer stack, static dashboard grid
and optional source-page tilt; it must not move controls or impair source reading.
Pause sign-in loops when hidden. Reduced motion disables animations, transitions,
smooth scrolling and decorative transforms. Clinical and emergency wording is
never animation-gated.

## Accessibility overrides approved by the requester

- Text, including small timestamps, needs readable contrast: at least 4.5:1 for
  normal text. Use the muted token instead of the reference's lighter faint gray.
- Patient controls retain at least 44×44px touch areas even when visually smaller.
- Visible keyboard focus, accessible icon labels, Escape, focus trapping and focus
  return are mandatory for dialogs and sheets. Help works on tap, not hover alone.
- Preserve zoom, safe-area insets and long Spanish wrapping. Never truncate clinical
  instructions. Ellipsis is appropriate only for nonessential previews.
- Keep an accessible refresh action alongside gesture-based refresh.

## Workflow and content invariants

This redesign changes presentation only. Preserve routes, API calls, state actions,
data fields, validation, handlers, permissions, review/publication gates and safety
copy. Carry existing selectors and aria attributes to equivalent controls.

No synthetic mockup content becomes application data. Counts, risk, approval,
verification, confidence, audit labels and source highlights require actual backing
data. Unknown is not zero. Clinical wording and historical messages are not UI
translations; patient en-US/es-MX switching uses the existing saved preference,
while clinician controls remain English.

All existing actions remain reachable after restructuring. Source identity and page
references remain visible in expanded evidence. Never rename a clinical document
type based only on styling; shortened filenames are display-only with the original
available in detail.

## Verification before review

Run both apps' lint, typecheck, unit tests and production builds. Review actual
screens at patient 360px and clinician 1280px plus narrower/wider breakpoints;
verify keyboard, reduced motion, English/Spanish, loading/error/empty states and
safe-area behavior. Record screenshots and exact coverage honestly. Passing tests
or a rendered mockup alone does not prove live workflow acceptance.
