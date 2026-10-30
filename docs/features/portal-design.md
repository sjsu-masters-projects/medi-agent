# Portal design rules

Layout and motion conventions for the patient portal (mobile PWA) and clinician portal
(desktop web). [`.agent/DESIGN_SYSTEM.md`](../../.agent/DESIGN_SYSTEM.md) owns identity,
accessibility overrides and workflow invariants, each app's `src/app/globals.css` owns
token values, and [brand icons](../brand-icons.md) covers assets. This page keeps the rest.

## What it does

- **Patient:** a large page title (no hero banner), grouped rows with icon tiles, a
  floating five-destination bottom nav (Today, Records, centre chat, Visits, Profile),
  pull-to-refresh and bottom sheets.
- **Clinician:** dark navy sidebar, fluid light workspace, dense tables, and review panes
  that show the item, its evidence and the protected source preview together.

## Rules it must keep

1. **Presentation only.** A redesign does not add, remove or rename routes, API calls,
   Redux slices, locale keys or data fields, nor change clinical workflow, approval gates,
   safety copy or emergency wording. Such content may move, never weaken.
2. **Nothing becomes unreachable.** Moving an action (Refresh to pull-to-refresh) is fine;
   deleting it is not, and gesture refresh keeps an accessible Refresh control. Existing
   `aria-*`, `data-testid` and selectors carry to the equivalent element; change a test
   that pins a class name, not the behaviour.
3. **Seal and chip stay distinct.** `ApprovalSeal` is the only way to say a clinician
   approved, `AiChip` the only way to say AI produced it. The AI-to-approved swap runs only
   after a successful publish.
4. **Patient layout.** The bottom nav is hidden inside an open conversation so the composer
   gets the screen; content keeps bottom padding to clear it. The language selector lives
   in Profile; only login and signup keep a small language button. Entry screens may use
   the teal glow over sand; signed-in screens stay flat.
5. **Clinician layout.** Dashboard content is fluid; only reading text caps at 72ch. Table
   cells wrap on flexible tracks and never overlap. Hover lift is for clickable cards only.
   The care-plan stepper restructures the "Before publishing" guidance but its full text
   stays in an info popover; never drop it.
6. **Motion explains state.** Easing `cubic-bezier(.2,.8,.2,1)`; 160 ms for presses and
   toggles, 240 ms for sheets, tabs and rows; nothing on a clinician work screen over
   300 ms. Animate only after the API call resolves, and not on error. Loops (`ma-pulse`,
   `ma-dot`) only for processing or live status. Never animate risk numbers or safety,
   emergency or approval copy; no confetti, parallax, scroll-jacking or animation library.
   Reduced motion disables every animation and transition.
7. **3D in three places only:** the clinician sign-in layer stack, the static Risk Radar
   grid floor and the optional source-page tilt (off under reduced motion). None in the
   patient app. Sign-in loops pause when the page is hidden.

## Why it was built this way

- One identity with two compositions: warm and thumb-first for patients, dense and
  evidence-first for clinicians. Tokens live in `globals.css`; no component library;
  extend `src/components/ui/*`.
- Where the mockup and the written handoff disagreed the written values won, and the
  accessibility overrides won over the mockup's lighter grays and smaller targets.

## Excluded on purpose

New features or routes, a component or animation library, and mockup sample values
(accounts, signatures, approval marks) as product data.

## Where it lives

`apps/*/src/app/globals.css`, `apps/*/src/components/ui/` (`approval-seal`, `ai-chip`,
`motion`, `modal`, `button`, `badge`), patient `components/layouts/bottom-nav.tsx`,
`page-header.tsx`, `components/ui/pull-to-refresh.tsx`, `app/(app)/layout.tsx`, clinician
`components/layouts/sidebar.tsx` and `top-header.tsx`.

## How to check it

Per portal run lint, typecheck, `npm run test` and a production build. Then inspect real
screens at 360 px (patient) and 1280 px (clinician) plus one narrower and one wider width,
in English and Spanish, by keyboard, with reduced motion, and in loading, error and empty
states. There is no QA handoff section; a passing build is not workflow acceptance.
