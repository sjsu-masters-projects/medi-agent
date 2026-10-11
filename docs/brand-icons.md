# MediAgent app icons — integration handoff

Logo: "M-check" monogram (option 1a). Same glyph in both apps, different colorways.

- Patient (MediAgent Care): tile #147465, glyph #FFF8EE, check accent #F5C46A
- Clinician (MediAgent Pro): tile #0B1324, glyph #FFFFFF, check accent #60A5FA

All paths below are relative to the repo root. The files in this folder mirror the repo layout, so copy them over as-is.

## Patient portal — apps/patient-portal

New files in public/brand/:
- favicon.svg: bold-weight favicon (better at 16px)
- favicon-16.png and favicon-32.png
- icon.svg, icon-192.png, icon-512.png: rounded tile, manifest purpose "any"
- icon-maskable.svg, icon-maskable-192.png, icon-maskable-512.png: full-bleed with the glyph inside the 80% safe zone, purpose "maskable"
- apple-touch-icon.png: 180x180, full-bleed (iOS rounds the corners itself)

Replaced files:
- src/app/favicon.ico: contains 16, 32 and 48 px images
- public/manifest.webmanifest: icons array now points at /brand/*; every other field is unchanged

Edit src/app/layout.tsx and replace the icons block:
```ts
icons: {
  icon: [
    { url: "/brand/favicon.svg", type: "image/svg+xml" },
    { url: "/brand/favicon-32.png", sizes: "32x32", type: "image/png" },
    { url: "/brand/favicon-16.png", sizes: "16x16", type: "image/png" },
  ],
  apple: { url: "/brand/apple-touch-icon.png", sizes: "180x180" },
},
```
Then delete public/pwa-icon.svg and grep for any other references to it. You can also delete the unused Next.js starter SVGs in public/: file, globe, next, vercel, window.

In-app header mark: <img src="/brand/icon.svg" alt="" width={32} height={32} /> next to the existing "MediAgent Care" text. Mark the image decorative, because the text carries the name.

## Clinician portal — apps/clinician-portal

New files in public/brand/:
- favicon.svg, favicon-16.png, favicon-32.png
- icon.svg, icon-192.png, icon-512.png
- icon-square.svg and apple-touch-icon.png (180, full-bleed)
- mark-sidebar.svg: tile #1E293B, so it stands out against the bg-slate-950 sidebar

Replaced file:
- src/app/favicon.ico (this removes the default Next.js icon)

Edit src/app/layout.tsx and add to metadata:
```ts
icons: {
  icon: [
    { url: "/brand/favicon.svg", type: "image/svg+xml" },
    { url: "/brand/favicon-32.png", sizes: "32x32", type: "image/png" },
    { url: "/brand/favicon-16.png", sizes: "16x16", type: "image/png" },
  ],
  apple: { url: "/brand/apple-touch-icon.png", sizes: "180x180" },
},
```

Edit src/components/layouts/sidebar.tsx and change the brand block to:
```tsx
<p className="flex items-center gap-2.5 text-xl font-semibold tracking-tight">
  <img src="/brand/mark-sidebar.svg" alt="" width={28} height={28} className="rounded-md" />
  <span>MediAgent<span className="text-blue-400">Pro</span></span>
</p>
```
You can also delete the Next.js starter SVGs in public/.

## Rules
- Don't recolor the icons, redraw them, or add gradients or shadows. The SVGs are the source of truth; regenerate the PNGs from them if a size is missing.
- Use favicon.svg (the bold version) only at 48px and below. Use icon.svg everywhere else.
- Verify: hard-refresh each portal and check the Chrome tab icon. For the patient PWA, check the manifest in Chrome DevTools → Application → Manifest (both "any" and "maskable" icons should load with no warnings), then install it on Android and iOS and confirm the home-screen icon.
