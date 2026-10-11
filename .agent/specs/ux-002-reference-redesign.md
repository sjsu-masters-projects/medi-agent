# MediAgent UI redesign — implementation handoff

> **Status:** Delivered in #142 (foundation), #143 (patient), #144 (clinician) and #145
> (responsive/wording); deployed recheck passed October 11 (docs/deployed-recheck-2026-10-11.md).

Visual reference: the hosted redesign (screens A–F) linked from
[DESIGN_SYSTEM.md](../DESIGN_SYSTEM.md#canonical-visual-reference). This document is the source of truth for values. If the mockup and this file disagree, follow this file.

Additional approved reference: [Profile & Clinic settings](https://claude.ai/artifact/HWCwWAVWQCp3aGGk5Abp1Q).
Patient Profile uses an identity card, grouped label/value settings, language and
edit sheets, linked care teams and account actions. Clinician settings keeps its
existing tabs and forms, with a desktop section navigator, clearly read-only
fields and compact card action footers. Illustrative account values, signatures,
approval marks and saved-state examples in the references are not application data.
Only actual persisted state may be shown. Readable timestamps and patient touch
areas of at least 44×44px override smaller/lighter reference values.

## 0. Scope rules (read first)

This is a **visual, layout and interaction-polish PR only**.

The requester additionally approved clearer nonclinical interface copy from the
reference (entry screens, navigation and settings help). Keep existing locale keys
and behavior. This does not authorize changing clinical instructions, approval
claims, historical messages or emergency/safety wording. Entry screens may use the
reference's subtle teal glow over the warm-sand canvas; authenticated screens keep
the flat canvas.

- Do NOT add, remove or rename routes, API calls, Redux slices, i18n keys, data fields, or features.
- Do NOT change any clinical workflow, approval gating, safety copy, or emergency wording. You may move them, never weaken them.
- Every existing button and handler must still exist and be reachable. Moving something (e.g. Refresh → pull-to-refresh, hands-free → header icon) is allowed. Removing it is not.
- Keep all existing `aria-*`, `data-testid` and test selectors. If you restructure markup, carry them over to the equivalent element.
- Run each app's existing unit tests, lint, typecheck and build before opening the PR. Visual changes must not break tests. If a test asserts on a class name, update the test, not the behaviour.
- Ship as 3 PRs, in order: **PR1 Foundation → PR2 Patient screens → PR3 Clinician screens.** Each PR must leave both apps working.

Stack: Next.js 16, React 19, Tailwind CSS v4 (`@theme` in `globals.css`). Don't add a component library. Extend the existing `src/components/ui/*` files.

---

## 1. PR1 — Foundation (both apps)

### 1.1 Fonts

Replace Aptos/Inter with Geist + Geist Mono via `next/font/google` in each `src/app/layout.tsx`:

```tsx
import { Geist, Geist_Mono } from "next/font/google";
const geist = Geist({ subsets: ["latin"], variable: "--font-geist", display: "swap" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });
// <html lang=... className={`${geist.variable} ${geistMono.variable}`}>
```

Use mono (`font-mono`) ONLY for times (`08:00`), versions (`v4`), scores (`92%`, `Naranjo 6`), counts in tables, and small uppercase eyebrow labels. Everything else is `font-sans`.

### 1.2 Tokens — patient-portal `src/app/globals.css`

Replace the `@theme inline` block. Keep `@import "tailwindcss";` at the top.

```css
@theme inline {
  --font-sans: var(--font-geist), -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-mono: var(--font-geist-mono), ui-monospace, monospace;

  --color-background: #F6F1EA;   /* app canvas (warm sand) */
  --color-surface: #FFFDF9;      /* cards, rows, nav */
  --color-surface-2: #F1ECE3;    /* secondary buttons, chips, inputs */
  --color-line: #EFE9DF;         /* row dividers */
  --color-line-strong: #E8E1D6;  /* borders */
  --color-ink: #10202B;          /* primary text */
  --color-ink-2: #33434E;        /* body text */
  --color-muted: #5B6872;        /* secondary text (passes 4.5:1 on surface) */
  --color-faint: #8A949B;        /* timestamps only, ≥12px */

  --color-brand: #147465;        /* primary action, approval seal */
  --color-brand-hover: #0F5F53;
  --color-brand-tint: #E3F0EC;
  --color-brand-ink: #0F5C50;    /* text on brand-tint */
  --color-brand-deep: #0F3D37;   /* Nora AI card background */
  --color-gold: #F5C46A;         /* logo check + Nora accent only */

  --color-danger-tint: #FBEAE5;  /* overdue / missed / emergency */
  --color-danger-ink: #A33A27;

  /* activity-type icon tiles: tint / ink */
  --color-med-tint: #E3F0EC;     --color-med-ink: #147465;   /* medication */
  --color-lab-tint: #E4EEF8;     --color-lab-ink: #285B8F;   /* glucose/monitoring, lab results */
  --color-hyd-tint: #E1F1F5;     --color-hyd-ink: #1D6F84;   /* hydration */
  --color-note-tint: #F3E9D8;    --color-note-ink: #8A5A00;  /* visit notes */
  --color-upload-tint: #F1ECE3;  --color-upload-ink: #4A5964;/* patient uploads */

  --radius-card: 28px;   /* hero / next-up card */
  --radius-group: 22px;  /* grouped list container */
  --radius-tile: 13px;   /* 44px icon tiles */
  --radius-btn: 16px;    /* 54px primary buttons */

  --shadow-raised: 0 1px 0 rgba(16,32,43,.04), 0 12px 32px -12px rgba(16,32,43,.18), 0 2px 6px rgba(16,32,43,.05);
  --shadow-nav: 0 10px 30px -10px rgba(16,32,43,.25);
  --shadow-fab: 0 10px 20px -6px rgba(20,116,101,.55);
}
```

Body: replace the gradient backgrounds with flat `background: var(--color-background)`. Delete the decorative radial gradients on `body` and `.app-shell`. Keep `.app-shell` width (`min(100%, 480px)`) and `:focus-visible`, but change the outline to `3px solid rgba(20,116,101,.45)`.

### 1.3 Tokens — clinician-portal `src/app/globals.css`

Dark sidebar, **light workspace**.

```css
@theme inline {
  --font-sans: var(--font-geist), -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-mono: var(--font-geist-mono), ui-monospace, monospace;

  /* workspace (light) */
  --color-background: #F4F6FA;
  --color-surface: #FFFFFF;
  --color-surface-2: #F8FAFC;
  --color-line: rgba(100,116,139,.10);
  --color-line-strong: rgba(100,116,139,.20);
  --color-ink: #0F172A;
  --color-ink-2: #334155;
  --color-muted: #64748B;

  /* sidebar (dark) */
  --color-rail: #0A1222;
  --color-rail-ink: #E6ECF5;
  --color-rail-muted: #A9B6CA;
  --color-rail-active: rgba(96,165,250,.12);
  --color-rail-accent: #60A5FA;

  /* semantic */
  --color-primary: #2563EB;        /* primary buttons */
  --color-primary-hover: #1D4ED8;
  --color-ai-tint: #DBEAFE;  --color-ai-ink: #1D4ED8;       /* "AI draft" chip */
  --color-ok-tint: #CCFBF1;  --color-ok-ink: #0F766E;       /* "Verified"/"Approved" seal */
  --color-ok: #0F766E;
  --color-risk-tint: #FEE2E2; --color-risk-ink: #B91C1C; --color-risk: #DC2626;
  --color-warn-tint: #FEF3C7; --color-warn-ink: #92400E; --color-warn: #D97706;

  --shadow-card: 0 1px 2px rgba(15,23,42,.04);
  --shadow-raised: 0 16px 30px -16px rgba(37,99,235,.35);
}
body { background: var(--color-background); color: var(--color-ink); }
```

Replace every hard-coded `bg-blue-600`/`#1E5EFF`-style primary with `bg-primary hover:bg-primary-hover`. Grep for `blue-` and `#1e5eff` (case-insensitive) in both apps.

### 1.4 Motion — add to BOTH `globals.css`

```css
@keyframes ma-pulse { 0% { transform: scale(1); opacity: .7 } 100% { transform: scale(3.2); opacity: 0 } }
@keyframes ma-dot { 0%, 80%, 100% { opacity: .25 } 40% { opacity: 1 } }
@keyframes ma-enter { from { opacity: 0; transform: translateY(8px) } to { opacity: 1; transform: none } }

:root {
  --ease-out: cubic-bezier(.2,.8,.2,1);
  --ease-spring: cubic-bezier(.34,1.56,.64,1);
  --dur-micro: 160ms;  /* press, toggle, check-off */
  --dur-panel: 240ms;  /* sheets, row expand, hover lift */
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
```

Rules:
- Buttons: `transition-transform duration-[160ms] active:scale-[0.98]`.
- Page enter: keep the existing `.patient-page` animation but change it to `ma-enter 240ms var(--ease-out) both`. Keep the stagger, capped at 4 children × 45ms.
- Loops (`ma-pulse`, `ma-dot`) are ONLY for "processing" and "live" states. Never on static content.
- No parallax, no scroll-jacking, no 3D transforms in the patient app.

### 1.7 Motion map (exact specs; see "Motion, transitions & depth" in the mockup)

Use CSS transitions or the Web Animations API (`element.animate`). **No animation library.** Every item below must be a no-op under `prefers-reduced-motion: reduce`.

**Patient app**
| Moment | Trigger | Spec |
|---|---|---|
| Check-off → next task | Mark as taken / done succeeds | Check icon path `stroke-dasharray:1; pathLength=1`, dashoffset 1→0 over 160ms. Then the card goes `opacity 1→0, translateY 0→-8px` (160ms, ease-out). Then the next card enters with `ma-enter` 240ms `cubic-bezier(.34,1.56,.64,1)`. Only animate AFTER the API call resolves; on error, no animation and show the existing error. |
| Progress segment | Any completion | Segment background via an inner bar, `transition: width 240ms var(--ease-out)`, 0→100%. |
| Tab change | Bottom nav | Active pill = one absolutely positioned element, `transition: transform 240ms var(--ease-out)` to the active item's offsetLeft. Page content uses the existing `.patient-page` enter (retimed to 240ms). |
| Bottom sheet | Details, language, new message, join clinic | Sheet `translateY(100%)→0` 240ms ease-out; backdrop `rgba(16,32,43,.4)` opacity 0→1 160ms. Close on backdrop tap and Esc. Trap focus. |
| Pull to refresh | Today, Records, Visits, Chat lists | Over-scroll at scrollTop 0 shows a 40px M-check (`/brand/icon.svg` paths inline). Bind `stroke-dashoffset = 1 - min(pull/80,1)`. Release past 80px → call the existing refetch; while pending, loop `ma-draw 1.2s`. |
| Processing | Records "Reading", Nora typing | `ma-dot 1.2s infinite` on 3 × 4px dots, delays 0 / .15s / .3s. When ready, the Summary chip fades in (opacity 160ms). |
| Messages | Send / receive | New bubble: `opacity 0→1, translateY 6px→0` 160ms. Listen while playing: three 3px bars scaling Y (0.4→1) on staggered 600ms loops. Stop when audio ends. |

Depth (patient): shadows only (`--shadow-raised`, `--shadow-nav`, backdrop-blur on the nav). **No 3D transforms.**

**Clinician app**
| Moment | Trigger | Spec |
|---|---|---|
| Supervised-flow stack | Sign-in left panel | See 3.6. A 6s loop. Pause with `animation-play-state: paused` when `document.hidden`. |
| Table re-sort (FLIP) | Risk Radar / Roster filter or sort change | Before the state update, record each row's `getBoundingClientRect().top` by patient id. After render, for each row `el.animate([{transform:\`translateY(${old-new}px)\`},{transform:'none'}],{duration:240,easing:'cubic-bezier(.2,.8,.2,1)'})`. New rows fade in 160ms. |
| Verify item | Care-plan item marked verified | Status box `background-color` 160ms to `--color-ok`; check path draws 160ms; stepper count text cross-fades. |
| Item → source | Select item | Source pane `scrollTo({top, behavior:'smooth'})` to the excerpt. Excerpt ring flashes once: `@keyframes ma-flash{0%{box-shadow:0 0 0 0 rgba(202,138,4,.6)}100%{box-shadow:0 0 0 10px rgba(202,138,4,0)}}` 600ms. |
| AI → approved | Approve & publish succeeds | Header chips stacked in `display:inline-grid` (both in `grid-area:1/1`). The AI chip goes `opacity 1→0, translateY -4px`; the teal seal goes `opacity 0→1, translateY 4px→0`; 300ms. Only on success. |
| Hover lift | Clickable cards only | `transition: transform 240ms, box-shadow 240ms`; hover `translateY(-3px)` + `--shadow-raised`. |
| Tabs underline | Patient-detail tabs | One 2px underline element, transform + width transition 240ms. |
| Live status | Document ingestion running | `ma-pulse 1.8s` ring on an 8px teal dot. Only while a job is running. |

**Never animate:** risk numbers or percentages (no count-ups), safety / emergency / approval copy, confetti or celebrations, parallax, scroll-jacking. Nothing on clinician work screens runs longer than 300ms. Loops are allowed only for live or processing status.

**3D is allowed in exactly three places:** (1) the clinician sign-in layer stack, (2) the Risk Radar `.radar-floor` grid (static), (3) the source-page tilt `perspective(1200px) rotateY(-3deg)`.

### 1.5 Shared components (create in both apps' `src/components/ui/`)

**`approval-seal.tsx`** — the only way to say "clinician approved".
```tsx
export function ApprovalSeal({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2 text-[13px] font-medium text-brand-ink">  {/* clinician: text-ok-ink */}
      <span className="flex h-[18px] w-[18px] items-center justify-center rounded-[5px] bg-brand text-white">  {/* clinician: bg-ok */}
        <CheckIcon className="h-3 w-3" strokeWidth={2.4} />
      </span>
      {children}
    </span>
  );
}
```
Pill variant (clinician headers): add `rounded-full bg-ok-tint px-3 py-1.5`.

**`ai-chip.tsx`** — the only way to say "AI produced this".
`inline-flex items-center gap-1.5 rounded-md bg-ai-tint px-2 py-1 text-xs font-medium text-ai-ink` + a 12–14px sparkle icon.
Patient app: use it for "AI Summary" chips on Records (`bg-brand-tint text-brand-ink`, sparkle icon).
**Never** put the check icon on AI content, and never put the sparkle on approved content.

**Icons**: inline SVG components, 24×24 viewBox, `fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round"`. Path data comes from the reference's `<symbol>` definitions: home, folder, chat, cal, user, pill, drop, gauge, walk, check, search, plus, lab, rx, note, up, mic, send, arrow, back, alert, users, grid, inbox, gear, spark, speaker. They live in each portal's `src/components/ui/icons.tsx`. Don't add an icon package.

**Logo**: use `/brand/icon.svg` (patient) and `/brand/mark-sidebar.svg` (clinician) from the earlier brand handoff (`docs/brand-icons.md`).

### 1.6 Language picker → Profile (patient)

- Remove the language `<select>` + "About language" from the top of every screen.
- Profile already has "Preferred language". Make that row editable inline (tap → bottom sheet with the same options the old select had), using the **same Redux action / API call** the old select dispatched.
- On the login and signup screens only, keep a small language button top-right: `h-9 rounded-full bg-surface-2 px-3 text-sm`.

---

## 2. PR2 — Patient screens (mobile PWA)

General layout for every tab screen:
- Screen padding: `px-4` for containers, `px-[22px]` for headings.
- **Large-title header** replaces `PageHeader`'s teal hero on ALL tabs (Today, Records, Visits, Profile, Chat):
  `<h1 className="text-[32px] font-semibold tracking-[-0.02em] text-ink">` at `pt-2`, with an optional right action (44×44 `rounded-[14px] bg-brand text-white`).
  Today uses a two-line variant: date `text-sm text-muted` above `text-[28px] font-semibold` greeting.
  Keep `PageHeader`'s `backButton` prop behaviour, restyled: 40×40 ghost button with the `back` icon.
- Delete the decorative circles in `page-header.tsx`.
- **Refresh buttons** → pull-to-refresh calling the same refetch function. Also keep a `Refresh` item in an overflow `⋯` menu for accessibility.
- Section eyebrow labels: `font-mono text-xs tracking-[0.08em] text-muted uppercase px-[22px] pt-5 pb-2`.
- **Grouped list** container: `mx-4 overflow-hidden rounded-[22px] bg-surface`. Rows: `flex items-center gap-3 px-[14px] py-[13px] border-b border-line last:border-b-0`.
- **Icon tile**: `flex h-11 w-11 flex-none items-center justify-center rounded-[13px] bg-{type}-tint text-{type}-ink`, icon 20px. In Today rows use 40×40 / `rounded-xl`.

### 2.1 Bottom nav — `components/layouts/bottom-nav.tsx`
- Container: `fixed inset-x-[14px] bottom-[18px] h-[68px] rounded-3xl border border-[rgba(16,32,43,.06)] bg-[rgba(255,253,249,.86)] backdrop-blur-[18px] shadow-[var(--shadow-nav)] grid grid-cols-5 items-center` plus `pb-[env(safe-area-inset-bottom)]`.
- Item: `flex flex-col items-center gap-[3px] text-[11px]`, icon 22px. Inactive `text-[#6B7780]`, active `text-brand font-semibold`. Minimum 44×44 hit area.
- Centre chat button: `-mt-[26px] h-[54px] w-[54px] rounded-[18px] bg-brand text-white shadow-[var(--shadow-fab)]`. When the chat route is active: `bg-brand-deep text-gold ring-4 ring-brand-tint`.
- **Hide the bottom nav inside a conversation thread** (Nora or care team) so the composer gets the bottom of the screen.
- Content needs `pb-[110px]` so the last row clears the nav.

### 2.2 Today — `app/(app)/today/page.tsx`
Same data and same handlers (mark taken/done, "I couldn't do this", care plan details).

1. **Header**: date + "Good morning, {firstName}" + 42px avatar (`rounded-full bg-brand-tint text-brand font-semibold`).
2. **Progress strip** (replaces the hero ring): text row `text-[13px] text-muted` — "**{done} of {total}** done today" on the left, next reminder time on the right if one exists. Below it, `grid grid-cols-{total} gap-[5px]` of `h-1.5 rounded-[3px]` segments, one per task, in schedule order. Colors: done `bg-brand`, missed `bg-[#E39A86]`, upcoming/available `bg-[#DCD5CA]`. Drop "About this progress" into an (i) button on the strip that opens the same text in a sheet.
3. **Next-up card**: the first task that is missed or available (same logic the list already uses to sort; don't invent new rules). `mx-4 mt-[18px] rounded-[28px] bg-surface p-5 shadow-[var(--shadow-raised)] flex flex-col gap-4`.
   - Row 1: eyebrow "NEXT UP" + status pill (`rounded-full px-2.5 py-1 text-xs font-semibold`; missed = `bg-danger-tint text-danger-ink`, label "Overdue · {time}"; available = `bg-brand-tint text-brand-ink`).
   - Row 2: 52px icon tile (`rounded-2xl`) + title `text-[22px] font-semibold` + instruction `text-[15px] text-ink-2`.
   - Row 3: `<ApprovalSeal>In your plan · approved by {clinicianName}</ApprovalSeal>`. Shown ONCE here. Remove the per-card "CARE-TEAM APPROVED • …" eyebrow and "Care plan approved by…" line from list rows.
   - Row 4: primary `h-[54px] rounded-2xl bg-brand text-white text-[17px] font-semibold` with a check icon ("Mark as taken" for medication, "Mark as done" for others); secondary `h-[46px] rounded-[14px] bg-surface-2 text-ink-2 text-[15px] font-medium` "I couldn't do this". Same handlers as today.
   - After completion: animate the card out (`opacity 0, translateY(-8px)`, 160ms) and the next task in (`ma-enter` with `--ease-spring`, 240ms).
4. **"Later today" grouped list**: one row per remaining task. Icon tile by type (medication = pill, monitoring = gauge, hydration = drop, activity = walk). Title `text-[15px] font-semibold`, sub `text-[13px] text-muted` (timing text). Right side: time in `font-mono text-[13px]`, OR a "Done ✓" in `text-brand`, OR a compact `h-[34px] rounded-[11px] bg-brand-tint text-brand px-3 text-[13px] font-semibold` "Mark done" button. Tapping a row opens the existing "Care plan details" in a bottom sheet. Don't use `<details>`.
5. **"Set reminder times" banner** → remove the banner. Instead, rows that need a time get a `text-[13px] text-brand font-medium` "Set time" link in place of the time. It goes to the same reminders route.
6. **"Report a symptom" card**: keep it, restyled as a grouped-list row with a spark icon tile in `bg-brand-deep text-gold`, linking to the same route.

### 2.3 Records — `app/(app)/records/page.tsx`
- Header: "Records" large title + upload button (same handler).
- Under the title: `text-sm text-muted` "{n} records · {m} processing".
- Group by date: "THIS WEEK", "EARLIER" (client-side grouping of the existing list; no new data).
- Row title: the document's display title if the API provides one. Otherwise **clean the filename for display only**: strip the extension, the patient-name prefix, dates and language codes, and replace `-`/`_` with spaces. Show the full filename in the detail view. Don't change what's stored.
- Row subtitle: "{Type} · {Dr. Name | Your upload} · {Mon D}". Type from the existing tag: `medical record` → "Visit note", `prescription` → "Prescription", lab-type → "Lab result". Unknown → "Document".
- Icon tile by type (note / rx / lab / upload tokens).
- Right chip: "AI Summary" → `<AiChip>Summary</AiChip>` in brand tint. Processing → `bg-surface-2 text-muted` "Reading" + 3 animated dots (`ma-dot 1.2s` with 0/.15/.3s delays). Duplicate upload → no chip; dim title to `text-[#6B7780]`, subtitle "Your upload · already on file".
- Remove the blue focus outline on cards. Use the global `:focus-visible` style.

### 2.4 Chat inbox — `app/(app)/chat/page.tsx`
Replace the two tab buttons + recipient form with one inbox screen:
- **Nora card** (top): `mx-4 mt-4 rounded-[28px] bg-brand-deep p-5 text-[#F2F7F5] shadow-[0_18px_36px_-16px_rgba(15,61,55,.6)] relative overflow-hidden`, with one decorative glow `absolute -right-[60px] -top-[60px] h-[200px] w-[200px] rounded-full bg-[radial-gradient(circle,rgba(245,196,106,.28),transparent_70%)]`.
  - Avatar: 48px `rounded-2xl bg-white/10 border border-white/20 text-gold` with the spark icon.
  - Name "Nora" `text-[19px] font-semibold` + "AI" badge `text-[11px] font-semibold tracking-[.06em] bg-[rgba(245,196,106,.18)] text-gold rounded-md px-1.5 py-0.5`.
  - Sub: "Care assistant · not a clinician" `text-[13px] text-[#B9D1CC]`.
  - Buttons: "Report a symptom" (`h-9 rounded-full bg-gold text-[#2B1F05] px-3.5 text-sm font-semibold`) and "Open chat" (`bg-white/10 border border-white/15`). Both open the existing Nora thread.
- **"YOUR CARE TEAM"** eyebrow, then one contact row per existing conversation: 48px initials avatar (`bg-note-tint text-note-ink`), name, clinic, last message (1 line, ellipsis), time (mono 12px), unread dot (`h-[9px] w-[9px] rounded-full bg-brand`). Tapping a row opens the same conversation the old "Open conversation" button opened.
- "New message" text button → bottom sheet containing the existing recipient select.
- Keep the existing safety copy exactly ("Messages are not continuously monitored…") as `text-[13px] text-muted` under the list, plus the emergency strip `rounded-2xl bg-danger-tint text-[#7A2A1B] px-3.5 py-3 text-sm` with the alert icon, pinned above the bottom nav.
- "Historical care-team messages (n)" → a plain row at the end of the list.

### 2.5 Conversation thread (Nora and care team)
- Full screen. Bottom nav hidden.
- Header: back (40px) + 36px avatar + name/sub + right action. For Nora the right action is the **hands-free toggle** (speaker icon, 40px `rounded-xl bg-surface`, `aria-pressed`). It uses the same handler as "Turn on hands-free mode".
- Bubbles: patient `self-end max-w-[82%] rounded-[20px_20px_6px_20px] bg-brand text-white px-3.5 py-[11px] text-[15px] leading-[1.4]`. Other side: `self-start max-w-[88%] rounded-[20px_20px_20px_6px] bg-surface px-[15px] py-[13px]`.
- Meta under bubbles: `font-mono text-[11px] text-faint` "{time} · Original language: {lang}". The care-team thread shows the sender name instead.
- "Listen" stays inside Nora bubbles as `h-[30px] rounded-full bg-surface-2 px-3 text-[13px]` with the speaker icon.
- **Composer** (one row, sticky bottom, `pb-[calc(env(safe-area-inset-bottom)+12px)]`): field `flex-1 h-[52px] rounded-[26px] bg-surface border border-line-strong pl-[18px] pr-1.5`; mic button inside the field (40px circle `bg-surface-2`, same "Tap to speak" handler); send button outside (52px circle `bg-brand text-white`, disabled `opacity-40`). Textarea auto-grows to 4 lines max.
- Replace raw timestamps like "10/10/2026, 11:03:28 AM" with relative time ("11:03", "Yesterday", "Oct 3") using `Intl.DateTimeFormat` in the user's locale.

### 2.6 Visits, Profile, Login (same system, no mockup)
- **Visits**: large title, empty state as one centred block (48px icon tile + `text-[17px] font-semibold` + `text-[15px] text-muted`), and "Open chat" as a secondary button. No dashed border.
- **Profile**: identity row (avatar + name + email) → grouped lists: "Personal information" (label/value rows, edit opens a sheet), "Reminders" (row → same route; change the blue button to a row with a chevron), "Care team" (contact rows + "Message your care team" row), "Join another clinic" (row → sheet), "Sign out" (row, `text-danger-ink`, same handler). Use the same field set and handlers.
- **Login** (mockup screen 0): replace the teal hero and circles with a white page: 64px app icon, "Welcome back" `text-[32px] font-semibold`, sub `text-muted`, inputs `h-[52px] rounded-2xl bg-surface border border-line-strong px-4 text-base`, primary button as in Today. Keep the language button top-right. "Create one" link in `text-brand font-semibold`.

---

## 3. PR3 — Clinician screens (desktop web)

### 3.1 App shell
- `sidebar.tsx`: `w-[232px] bg-rail text-rail-ink border-r border-white/10 px-3.5 py-5 flex flex-col`.
  - Logo row: `/brand/mark-sidebar.svg` at 30px + "MediAgent**Pro**" `text-[17px] font-semibold`, with Pro in `text-rail-accent`.
  - Nav items: `h-[38px] rounded-[10px] px-2.5 flex items-center gap-2.5 text-sm text-rail-muted hover:bg-white/5`. Active: `bg-rail-active text-rail-ink font-medium`, icon `text-rail-accent`. Count on the right: `ml-auto font-mono text-xs`.
  - Keep the **same items and order**: Risk Radar, Patient Roster, Appointments, Review Queue, ADR Reviews, Messages, then the "ADMINISTRATION" eyebrow (`font-mono text-[11px] tracking-[.08em] text-[#55647D]`) and Clinic Settings.
  - User card at the bottom: `rounded-xl bg-white/5 p-2.5`, 34px avatar + name + "{Role} · {Clinic}". Keep Logout as-is (restyled `h-9 rounded-lg border border-white/10`).
- `top-header.tsx`: `h-[60px] bg-surface border-b border-line px-7 flex items-center justify-between`. Left: the page's existing search input if it has one (`w-[440px] h-[38px] rounded-[10px] bg-surface-2 border border-line px-3`). Right: existing actions (e.g. "Patient invitations" as a secondary button).
- **Content width: fluid.** Remove `max-w-*`/`mx-auto` centring on dashboard pages. Use `px-7 py-6` and let content fill. Cap only reading text at `max-w-[72ch]`.
- Main background: `bg-background` (#F4F6FA). Cards: `bg-surface border border-line rounded-2xl shadow-[var(--shadow-card)]`.

### 3.2 Buttons, badges, tables (update `ui/button.tsx`, `ui/badge.tsx`, `ui/data-table.tsx`)
- Primary: `h-[34px] rounded-[9px] bg-primary px-4 text-[13px] font-semibold text-white hover:bg-primary-hover`. Large: `h-[42px] rounded-[10px] px-[18px] text-sm`.
- Secondary: `h-[34px] rounded-[9px] border border-line-strong bg-surface px-4 text-[13px] font-medium text-ink-2 hover:bg-surface-2`.
- Disabled: `bg-[#E2E8F0] text-[#94A3B8] cursor-not-allowed`.
- Risk badge: `inline-flex items-center gap-1.5 rounded-[7px] px-2 py-1 text-[13px]` + 7px dot. High: `bg-risk-tint text-risk-ink`, dot `bg-risk`. Medium: warn tokens. Low: ok tokens. Unknown: `bg-[rgba(100,116,139,.1)] text-ink-2`, dot `#64748B`. Keep the existing risk thresholds.
- Flag chip: `rounded-md px-2 py-[3px] text-xs` (risk tint when it's a risk flag, neutral otherwise) + sub-line `text-xs text-muted`.
- Table: header row `font-mono text-[11px] tracking-[.06em] text-muted uppercase py-3 px-[22px] border-b border-line`. Rows `py-4 px-[22px] border-b border-line hover:bg-[rgba(100,116,139,.05)]`. Use CSS grid with **flexible tracks**, e.g. `grid-cols-[minmax(180px,1.2fr)_120px_minmax(160px,1fr)_minmax(200px,1.4fr)_minmax(150px,1fr)_100px]`. Text in cells may wrap; never overlap.

### 3.3 Risk Radar — `app/(dashboard)/dashboard/page.tsx` (screen E)
Same three metrics, filters, columns and Review links.
- **Header band** (replaces the three KPI cards): `relative overflow-hidden rounded-[20px] bg-surface border border-line px-7 py-[26px] flex items-end justify-between`.
  - Left: `text-sm text-muted` "{weekday, date} · {clinic}" / `text-[34px] font-semibold tracking-[-0.025em]` "Risk Radar" / `text-[15px] text-ink-2` "Assigned patient overview".
  - Right: three stats, `gap-9`. Value `font-mono text-[28px] font-medium` (critical in `text-risk`, ADR in `text-warn-ink`), label `text-[13px] text-muted`.
  - **The only 3D element in the app** is a perspective grid floor behind the band. It's decorative, so give it `aria-hidden` and `pointer-events-none`:
    ```css
    .radar-floor{position:absolute;left:-10%;right:-10%;bottom:-140px;height:260px;
      background-image:linear-gradient(rgba(37,99,235,.10) 1px,transparent 1px),linear-gradient(90deg,rgba(37,99,235,.10) 1px,transparent 1px);
      background-size:44px 44px;transform:perspective(500px) rotateX(62deg);transform-origin:center top;
      mask-image:linear-gradient(180deg,rgba(0,0,0,.9),transparent 75%);}
    .radar-glow{position:absolute;right:120px;top:-80px;width:360px;height:260px;background:radial-gradient(ellipse,rgba(20,184,166,.12),transparent 65%);}
    ```
- **Toolbar** (replaces the four full-width dropdowns), inside the table card header `px-[22px] py-3.5 border-b border-line flex justify-between`:
  - Risk filter → segmented control `rounded-[10px] bg-[rgba(100,116,139,.06)] p-[3px]` with buttons `h-[30px] rounded-lg px-3 text-[13px]` (active `bg-surface text-ink font-medium shadow-sm`). Options = the existing select's options.
  - Sort by / Sort order / Minimum medications → compact `<select>`s `h-[34px] rounded-[9px] border border-line-strong px-3 text-[13px]`, each with an inline muted label ("Sort", "Order", "Min. meds"). Same state and handlers.
  - Search patients + refresh → icon buttons (34px) on the right; search expands to 240px on focus.
- Table columns unchanged (Patient, Risk, Adherence, Recent flag, ADR / Meds, Actions).
  - Patient: 34px initials avatar `bg-[#E2E8F0]` + name `text-[15px] font-semibold`.
  - Adherence: `w-[120px] h-1.5 rounded-[3px] bg-[#E2E8F0]` track + fill (`bg-risk` when < 60%, else `bg-primary`) + value `font-mono text-[13px]`. "Not enough data" stays as text.
  - Actions: "Review" is a **primary** button on High/critical rows and **secondary** on the others.
- "How to read these metrics" → footer row of the card (chevron + `text-[13px] text-muted`). Same disclosure content, opened in a popover.
- Hover lift for cards (`hover:-translate-y-[3px] transition-transform duration-[240ms]`) is allowed on clickable cards only.

### 3.4 Patient Roster
Same table component and styles as Risk Radar (3.2). The toolbar uses the existing "All risks" / "Sort by risk" selects as compact selects. No header band; use a simple `text-2xl font-semibold` title row.

### 3.5 Patient detail › Care Plan tab (screen F)
Same data, same blockers, same save/preview/approve actions and rules.
- **Patient strip** (top of patient detail, all tabs): 40px avatar, name `text-lg font-semibold` + risk badge, sub `text-[13px] text-muted` "DOB … · Patient language … · {n}% recorded completion". Right side on the Care Plan tab: `<ApprovalSeal pill>v{active} live in Today</ApprovalSeal>` → arrow → `<AiChip>v{draft} draft · not visible to patient</AiChip>`.
- **Tabs**: keep all 8. Style as an underline tab bar (`h-11 border-b border-line`; active `text-ink font-medium` + 2px `bg-primary` underline). Icons 16px.
- **Stepper** (replaces the blue info box and the yellow "Before publishing" box; same content, restructured): the steps are exactly what "Before publishing" lists — Sources → Patient wording ({verified}/{total}) → Resolve blockers ({resolved}/{total}) → Preview Today → Approve. Step circle 22px: done `bg-ok text-white` + check; current `border-2 border-primary`; blocker `border-[1.5px] border-warn text-warn-ink`; future `border-[1.5px] border-[#CBD5E1] text-muted`. Connectors `w-10 h-px bg-line-strong`. The full "Before publishing" text moves into an (i) popover on the stepper. **Do not remove it.**
- **Three panes**: `grid grid-cols-[320px_minmax(0,1fr)_400px]` filling the remaining height, each pane scrolling independently.
  1. **Items list** (left, `border-r border-line p-3`): one row per proposed item, `rounded-[10px] p-2.5 flex gap-2.5`. Status box 20px: verified `bg-ok` + check; blocker/overlap `border-[1.5px] border-warn text-warn` + alert icon; unverified `border-[1.5px] border-[#CBD5E1]`. Title `text-sm font-medium`, sub `text-xs text-muted` "{Type} · {carried forward | n sources | overlaps item N}". Selected: `bg-[rgba(96,165,250,.1)] border border-[rgba(96,165,250,.35)]`. "Show removed items (n) — sources retained" stays as a toggle at the bottom.
  2. **Editor** (centre, `p-5 px-6 flex flex-col gap-4`): selected item title `text-xl font-semibold`, with the existing explanation text as the sub-line. For overlaps, show the two proposals side by side (`grid grid-cols-2 gap-3`), each card `rounded-[14px] border p-3.5` with an eyebrow (`font-mono text-[11px]` "ITEM 3 · v3 LIVE" / "ITEM 4 · NEW EVIDENCE" + date), the wording `text-[15px]`, and the source line `text-xs text-muted`. The card whose source is open: `border-[1.5px] border-primary bg-[#EFF6FF]`. Then the existing keep/remove actions as secondary buttons. Then the patient-facing wording field (existing editable field) `rounded-xl border border-[rgba(96,165,250,.5)] p-3.5 text-[15px] ring-4 ring-[rgba(96,165,250,.1)]` when focused, labelled "Patient-facing wording · {language}" with "Shown in Today exactly as written" on the right. Then the existing confidence ("{n}% extraction confidence") with the clarifier "how clearly the text was read, not clinical certainty".
  3. **Source preview** (right, `bg-[#EEF2F7] border-l border-line p-4`): the existing protected source preview. Header: document name + page, plus "Protected · access logged" (only if access is logged today; otherwise just "Protected preview"). The page renders on white with `rounded-[10px] shadow-[0_18px_36px_-18px_rgba(15,23,42,.35)]` and an optional `transform: perspective(1200px) rotateY(-3deg)` (disabled under reduced-motion). The cited excerpt gets `bg-[rgba(250,204,21,.38)] ring-[1.5px] ring-[rgba(202,138,4,.6)] rounded`. When the selected item changes, scroll the excerpt into view inside the pane with `element.parentElement.scrollTo({top, behavior:'smooth'})`.
- **Sticky approval bar** (bottom of the tab, `sticky bottom-0 h-[72px] bg-white/90 backdrop-blur border-t border-line-strong px-7 flex items-center gap-4`): left `text-[13px] text-ink-2` "v{active} stays active in Today until this version is approved." (existing sentence, shortened); centre = the existing approval note field (`flex-1 h-[42px] rounded-[10px] border border-line-strong bg-surface-2 px-3.5`); right = progress `font-mono text-xs text-muted` "{verified} of {total} verified · {blockers} blocker(s)" + the existing approve button as a large primary. Its enabled/disabled logic is unchanged.
- The overlap explanation box (yellow) → the overlap item's editor header (warn chip "OVERLAP" + the same sentence).

### 3.6 Review Queue, ADR Reviews, Appointments, Messages, Settings, auth (same system, no mockup)
- **ADR Reviews**: replace the three KPI cards with a header band like Risk Radar (no 3D floor). Each case card uses two columns: left (`flex-1`) = Reported symptom + Patient-grounded Naranjo evidence rows (question `text-sm font-medium` + yes/no chip + quote `text-sm text-ink-2 border-l-2 border-line-strong pl-3`); right (`w-[360px]`, sticky) = Suspect medication, the Naranjo score card (`font-mono text-3xl` score + category chip + the existing sentence "Naranjo scores support your review; they do not make a clinical decision" pinned under it), Missing information chips, Information requested. Same actions.
- **Review Queue**: same list, table styles from 3.2; AI-generated items get `<AiChip>`.
- **Appointments**: two columns on ≥1280px. Left `w-[420px]` = the existing offer form, restyled with the input styles in 3.2 (style the datetime inputs; same fields, same validation). Right = "Appointments and patient responses" as a compact list (status badge right-aligned, times in mono).
- **Messages**: two-pane (conversation list `w-[320px]` | thread), with bubbles mirroring the patient thread (clinician `bg-primary text-white`, patient `bg-surface-2`). Same data.
- **Clinic settings**: keep the tabs. Cards per 3.1. The clinic code in `font-mono text-lg`.
- **Login / setup / signup** (mockup screens G and H): keep the split layout. Add a step indicator to the right card (`STEP n OF 3 · CLINIC ACCESS`: three 6px bars, current 24px wide `bg-primary`, done `bg-ok`, future `bg-[#CBD5E1]`). Show the verified clinic as a badge (`rounded-[14px] bg-[#F0FDFA] border border-[#99F6E4] p-3.5`, 40px `bg-ok` check tile, clinic name + `font-mono` code). Focused input: `border-[1.5px] border-primary ring-4 ring-[rgba(37,99,235,.12)]`; clinic code in `font-mono tracking-[.04em]`. Left panel `bg-rail`: logo, the existing headline in `text-[44px] font-semibold tracking-[-0.03em] text-rail-ink`, the existing sub-copy, and below it the **supervised-flow layer stack** (mockup G/H), `aria-hidden="true"`, in a `relative w-[640px] h-[420px]` box:
  - Four 240×240 planes, `absolute left-[80px] rounded-[28px] p-[30px]`, each with `transform: rotateX(60deg) rotateZ(-45deg)` (isometric, no perspective). Tops: 210px (01 Documents), 138px (02 AI draft), 66px (03 Gate), -6px (04 Today). Render them in that order so the higher planes overlap.
  - 01 Documents: `bg-[rgba(148,163,184,.08)] border border-[rgba(148,163,184,.35)]`, three page rectangles inside.
  - 02 AI draft: `bg-[rgba(59,130,246,.12)] border-[1.5px] border-dashed border-[rgba(96,165,250,.6)]`, sparkle icon + 4 bars `rgba(147,197,253,.45)`.
  - 03 Gate: `bg-[rgba(15,118,110,.22)] border-[1.5px] border-[rgba(45,212,191,.8)]`, centred 96px `bg-ok` check tile. Inner glow overlay: `absolute -inset-0.5 rounded-[28px]` with `@keyframes ma-gate` (6s; peaks at 46–56%: `box-shadow:0 0 44px 8px rgba(45,212,191,.5); background:rgba(45,212,191,.2)`).
  - 04 Today: `bg-[rgba(255,253,249,.94)]` with 4 rows (22px tiles, the first two `bg-brand`) and `shadow-[0_30px_50px_-20px_rgba(0,0,0,.6)]`.
  - The rising light: a 12px `bg-[#5EEAD4]` dot with `shadow-[0_0_16px_4px_rgba(94,234,212,.7)]` at `left-[194px] top-[324px]`, animated with `@keyframes ma-rise` (6s ease-in-out infinite: translateY 0 → -144px by 40%, hold to 58%, → -216px by 88%, fading in/out at the ends). A dashed 1px guide line `rgba(94,234,212,.35)` runs from y=114 to y=330 at x=199.
  - Flat labels at `left-[424px]`, vertically centred on each plane (y = 114 / 186 / 258 / 330), with a 36px leader line: mono number in its layer colour (gold / #5EEAD4 / #93C5FD / #A9B6CA), title `text-[15px] font-semibold`, sub `text-[13px] text-[#8B9AB3]`: "Only approved items appear", "Nothing passes without approval", "Not visible to the patient", "Source evidence with citations".
  - Under reduced-motion, show it static with the dot hidden. Right panel `bg-background` with the form card per 3.1.

---

## 4. Accessibility & QA checklist (every PR)

- [ ] Text contrast ≥ 4.5:1. `text-faint` only for ≥12px timestamps.
- [ ] Patient hit targets ≥ 44×44. Clinician controls ≥ 32px tall.
- [ ] `prefers-reduced-motion` disables all animation and the 3D tilt.
- [ ] Keyboard: every action reachable with Tab, visible `:focus-visible` ring, sheets/popovers trap focus and close on Esc.
- [ ] Icon-only buttons have `aria-label`. Decorative SVGs have `aria-hidden="true"`.
- [ ] EN and ES: check long Spanish strings at 360px width (patient) and 1280px (clinician). Nothing truncates important text; ellipsis only on message previews.
- [ ] Safe-area insets respected on iOS (bottom nav, composer).
- [ ] Every flow still works end to end: login → Today mark taken / couldn't do this → Records upload → Nora chat + Listen + hands-free → care-team message → Visits accept/decline → Profile language change; clinician login → Risk Radar filters → patient detail → Care Plan verify/resolve/preview/approve → ADR review → appointment offer → messages.
- [ ] Before/after screenshots of every screen attached to each PR.
