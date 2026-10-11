# MediAgent app icons

Logo: "M-check" monogram (option 1a). Same glyph in both apps, different colorways.

- Patient (MediAgent Care): tile #147465, glyph #FFF8EE, check accent #F5C46A
- Clinician (MediAgent Pro): tile #0B1324, glyph #FFFFFF, check accent #60A5FA

The icons are applied in `apps/*/src/app/layout.tsx` (favicon and Apple touch icon
metadata), the patient `public/manifest.webmanifest`, and the clinician sidebar and auth
shell (`mark-sidebar.svg`).

## Files

Patient portal, `apps/patient-portal/public/brand/`:
- `favicon.svg` (bold weight, better at 16px), `favicon-16.png`, `favicon-32.png`
- `icon.svg`, `icon-192.png`, `icon-512.png`: rounded tile, manifest purpose "any"
- `icon-maskable.svg`, `icon-maskable-192.png`, `icon-maskable-512.png`: full-bleed with the
  glyph inside the 80% safe zone, purpose "maskable"
- `apple-touch-icon.png`: 180x180, full-bleed (iOS rounds the corners itself)

Clinician portal, `apps/clinician-portal/public/brand/`:
- `favicon.svg`, `favicon-16.png`, `favicon-32.png`
- `icon.svg`, `icon-192.png`, `icon-512.png`
- `icon-square.svg` and `apple-touch-icon.png` (180, full-bleed)
- `mark-sidebar.svg`: tile #1E293B, so it stands out against the dark sidebar

## Rules
- Don't recolor the icons, redraw them, or add gradients or shadows. The SVGs are the source of truth; regenerate the PNGs from them if a size is missing.
- Use favicon.svg (the bold version) only at 48px and below. Use icon.svg everywhere else.
- Mark an in-app icon decorative (`alt=""`) when adjacent text carries the name.
- Verify: hard-refresh each portal and check the Chrome tab icon. For the patient PWA, check the manifest in Chrome DevTools → Application → Manifest (both "any" and "maskable" icons should load with no warnings), then install it on Android and iOS and confirm the home-screen icon.
