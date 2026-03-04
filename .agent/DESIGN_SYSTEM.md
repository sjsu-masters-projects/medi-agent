# MediAgent — Design System

> **Source of Truth for Frontend Development.**
> All agents writing or reviewing frontend UI MUST strictly adhere to these design guidelines based on the approved Figma screens.

---

## 🎨 1. Color Palette

### Core Brand & Surfaces
- **Brand Blue (Primary):** `bg-blue-600` (`#2563EB`) / `text-blue-600`
- **Sidebar Navy:** `bg-gray-900` (`#111827`) or `bg-slate-900`
- **App Background:** `bg-gray-50` (`#F9FAFB`)
- **Card/Surface:** `bg-white` (`#FFFFFF`)

### Semantic Status Colors (Highly utilized for Medical context)
Used in badges, indicators, and risk warnings.
- **🟢 Success / Normal:** `bg-green-100 text-green-800` (e.g., Vitals Normal, Routine Follow-up)
- **🟡 Warning / Review:** `bg-yellow-100 text-yellow-800` (e.g., Monitor closely, Missing data)
- **🔴 Danger / Critical:** `bg-red-100 text-red-800` (e.g., Severe ADR, Critical Vitals)
- **🔵 Info / Active:** `bg-blue-100 text-blue-800` (e.g., Active chat, Processing)

### Typography Colors
- **Primary Text:** `text-gray-900` (Headings, primary data values)
- **Secondary Text:** `text-gray-500` (Subtitles, metadata, timestamps)
- **Disabled/Placeholder Text:** `text-gray-400`

---

## 📝 2. Typography

Use modern, clean sans-serif (Inter, Tailwind default sans). Readability is the top priority for clinical apps.

- **Page Titles (H1):** `text-2xl font-bold text-gray-900`
- **Section/Card Titles (H2):** `text-lg font-semibold text-gray-900`
- **Standard Body:** `text-sm text-gray-700` (often used instead of `text-base` for denser data views)
- **Small/Meta:** `text-xs text-gray-500`

---

## 🧩 3. Core Components

### Layout Structure
- **Global Layout:** `h-screen flex overflow-hidden`
- **Sidebar:** Fixed width (e.g., `w-64`), dark theme (`bg-gray-900 text-white`). Active navigation item uses `bg-blue-600`. User profile at the bottom.
- **Top Header:** White background (`bg-white`), search bar, notifications, bordered bottom (`border-b border-gray-200`).
- **Main Content:** Light gray background (`bg-gray-50`), scrollable content area, adequate padding (`p-6` or `p-8`).

### Cards & Panels
Used to encapsulate related data (Patient Profiles, Risk Radar, Vitals).
- **Styling:** `bg-white rounded-xl shadow-sm border border-gray-200`
- **Inner Padding:** Standardize on `p-5` or `p-6`.

### Buttons
- **Primary:** `bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg px-4 py-2`
- **Secondary:** `bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 rounded-lg px-4 py-2 shadow-sm`
- **Ghost/Icon:** Transparent background, `text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg p-2`

### Data Tables
- Header row: `bg-gray-50 border-y border-gray-200 text-xs font-semibold text-gray-500 uppercase tracking-wider py-3 px-4`
- Body rows: White background, bottom border (`border-b border-gray-200`), hover effect (`hover:bg-gray-50`).
- High use of inline status Badges for clinical status.

### Status Badges (Pills)
- `inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium`
- Combine with the Semantic Status Colors listed above.

### Forms & Inputs
- **Inputs:** `border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none w-full shadow-sm`
- **Labels:** `text-sm font-medium text-gray-700 mb-1 block`

---

## 💬 4. AI Chat Interface (Patient Details View)

The AI Medical Assistant interface is a critical part of the UI.
- **Split Layout:** Often a 2-column view (Left: Medical Record, Right: AI Assistant Panel).
- **Chat Container:** `bg-white border border-gray-200 rounded-xl flex flex-col`
- **AI Response Bubble:** `bg-gray-50 border border-gray-200 text-gray-800 rounded-2xl rounded-tl-sm p-3 text-sm`
- **User Message Bubble:** `bg-blue-50 border border-blue-100 text-blue-900 rounded-2xl rounded-tr-sm p-3 text-sm`
- **Chat Input Field:** Pill-shaped or large-rounded (`rounded-full` or `rounded-xl`) with integrated Send/Voice button on the right.

---

> **Rule:** Do NOT use arbitrary hex colors or inline styles in frontend code. Always map back to these Tailwind utilities to maintain the cohesive MediAgent aesthetic.
