# UX-008 readability verification

October 30, 2026. Requester-approved readability work on
`feature/portal-readability`, isolated from main `77f9698d`. No backend, clinical
wording, thresholds, approval state, source content or database changes.

## Implemented

Readable shared clinician table/field/section roles, consistent action labels,
native roster headers and patient links, right-aligned counts, matching medication
and adherence headers, opaque focus outlines with contrasting halos and system
forced-color handling in both portals. Lower reported severity is neutral, with
review wording and thresholds retained. Patient explanations keep their paragraphs
and bullets and cap text at 65ch; source previews retain their width.

## Automated checks

Fresh `npm ci --no-audit --no-fund` in each isolated app uses the committed locks
(including Vitest 4.1.12). Original checkout dependencies and local files are untouched.
From each app directory:

```sh
npm run lint
npm run typecheck
NODE_OPTIONS=--no-experimental-webstorage npm test -- --run
NEXT_PUBLIC_SUPABASE_URL=https://test.supabase.co NEXT_PUBLIC_SUPABASE_ANON_KEY=test-anon-key npm run build -- --webpack
```

Both lint/typecheck and production builds pass using synthetic configuration and
public configured fonts. Patient: **97 files / 1,078 tests**. Clinician: **88 files /
854 tests**. New roster cases exercise column/row semantics, real hrefs/accessibility
names, sorts, risk filtering, unknown adherence and the spanning empty cell.
An initial new assertion counted decorative avatar initials via raw textContent;
it was corrected to test actual destinations and accessible names. The final full
clinician suite passes. Existing navigation/Node deprecation notices remain.

Repository-root commands:

```sh
python3 backend/scripts/build_spanish_review_pack.py --check --require-reviewed
node --test scripts/tests/check-docs.test.mjs
node scripts/check-docs.mjs --all
git diff --check
```

The accepted Spanish source snapshot matches; no receipt renewal or changed static
Spanish pair. Documentation helper tests pass (3 tests). Final link/fence checks pass across
114 tracked Markdown files; staged diff whitespace checks also pass.

## Bounded browser/visual evidence

Synthetic fixtures render the actual DataTable, Button, Badge and ExplanationSections
components. They use the generated production CSS and built Geist font assets,
rendered in cached headless Chromium 1208 with a fresh temporary profile. The fixture
is a component preview, not an authenticated application journey or real chart.

Inspected desktop clinician and wide English explanation images, narrow clinician,
Spanish mobile and forced-color images. Browser metrics cover:

| Preview | CSS viewport | Result |
| --- | --- | --- |
| Clinician | 1280px and 320px | No page-level horizontal overflow; the native table scrolls within its region. Headers compute to 14px / 600 / dark slate. |
| Patient English | 320px and 1280px | Reading width 232px and about 690px respectively, within the 65ch cap; visible focused button, at least 44px target. |
| Patient Spanish | 360px | Reading width 272px, wrapping preserved; visible focused button, at least 44px target. |
| Clinician forced colors | 1280px | Browser confirms forced colors; visible system focus and labels preserve status meaning without tint. |

Programmatic focus rendering checks pass for links, an outline-none field and shared
buttons. All checked outlines compute to 3px; patient controls retain at least 44px
height. Token contrast: dark-slate headings on the header surface about 9.9:1;
opaque action/brand outlines exceed 3:1 against their light halo. Forced colors are
user-agent/system colors rather than fixed palette assumptions.

Local-only preview artifacts and metrics are in `output/ux-008/` in this worktree.
Temporary renderer scripts are retained there for inspection; no preview route,
mock account or fixture data was added to the product. Live browser access was
unavailable. Full authenticated roster/record/plan flows, real Tab and screen-reader
navigation, physical devices, 200/400% browser zoom and deployed acceptance remain.
No compliance or clinical-validation claim follows from these component checks.

No remote migration, deployment, push or PR creation is performed in this slice.
