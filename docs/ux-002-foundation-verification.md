# UX-002 Foundation verification

## Scope

First of three reference-led UI PRs: Foundation → Patient screens → Clinician
screens. Based on main `657602d` (#141). Screen markup is deliberately not the
finished redesign. No backend, database, API, authorization or clinical gates change.

The updated handoff is version controlled at
[`ux-002-reference-redesign.md`](../.agent/specs/ux-002-reference-redesign.md).
The supplemental presentational reference export was inspected for shared icons,
motion, mobile navigation/sheets and planned screen composition. It is not an
application runtime or a replacement for existing handlers. Prototype strings,
clinical examples and simplified status mappings must not become product data.

## Automated checks

Run from each portal directory:

- `npm test`: patient 377 tests / 45 files; clinician 260 tests / 38 files passed.
- `npm test -- src/__tests__/brand-primitives.test.tsx`: two additional tests passed
  in each app after the full runs (caller-supplied copy and decorative icon labels).
- `npm run lint`: passed in both apps.
- `npm run typecheck`: passed in both apps.
- `npm run build -- --webpack`: passed in both apps, including hosted font retrieval.
- `git diff --check`: passed.

Existing Sentry instrumentation/deprecation and clinician workspace-lockfile
warnings remain. These did not fail the builds and are outside this visual scope.

Language regressions cover saved shared preference, hidden global locale
synchronization, focus restoration, keyboard access to the help disclosure,
pending/error preservation across sheet closure, and care-team load failure.
Keeping the sheet mounted retains the existing save guard; it is hidden and absent
from the accessible dialog tree while closed.

## Manual checks and limitations

Local production previews: patient `127.0.0.1:3102`, clinician `127.0.0.1:3103`.

- Patient guest entry checked at 360px with Spanish UI: no horizontal overflow;
  supplied brand mark and Geist render. Desktop guest entry previously checked.
- Clinician clinic-code entry checked at 1280px: no horizontal overflow; Geist,
  favicon and Apple icon metadata resolve to the supplied assets.
- Animated external reference renders; no `support.js` blocker.
- Authenticated live workflow checks were not repeated by Foundation. Profile
  behavior has component regression coverage, not a new live account write.
- Guest Spanish entry currently retains root `lang=en-US`; correct the guest
  locale attribute with entry-screen presentation in Patient PR2.
- Full revised layouts, touch/keyboard/motion and bilingual screen comparisons
  remain acceptance work for Patient PR2 and Clinician PR3.

## Reproducible review

1. Start each built app on the ports above; check brand icon metadata and font.
2. In an authorized synthetic patient session, open Profile → Preferred language;
   Tab/Shift+Tab includes About language, Escape closes, focus returns to the opener.
3. Throttle a language save, close and reopen the sheet. The request remains
   pending; a failed save remains visible on reopening without changing preference.
4. Simulate care-team load failure: Profile still offers language settings.
5. Preserve approved clinical wording, routes and all existing form handlers.
