# UX-008 portal readability

Requester-approved October 30, 2026 after the UI review. Implement on a separate
branch from current main. This is a presentation and navigation-semantics change.

## Acceptance

- Operational table headings use sentence case, dark slate, semibold sans text
  around 14px and a distinguishable header surface. Section headings and field
  labels use reusable roles rather than 11px uppercase metadata styling.
- The roster is a native table with caption, column/row headers, correctly aligned
  numeric columns and a real patient link supporting ordinary browser navigation.
  Preserve filtering, sorting, unknown-data, loading, empty and retry behavior.
- Medication/adherence tables retain native semantics and adopt the same header
  hierarchy. Review and clinical-summary headings remain easy to find.
- Both portals have opaque high-contrast keyboard focus, a contrasting halo for
  dark/colored surfaces, and forced-color support. Fields retain visible focus.
- Lower reported severity is neutral rather than sharing the approved/reviewed
  success treatment. Keep existing recorded scores, thresholds and wording.
- Explanations retain the existing heading-free paragraphs and bullets, with a
  readable text measure in wide modals. Source viewers retain their usable width.
- Shared clinician action text is readable without removing compact desktop
  controls or the patient portal's 44px targets.

## Boundaries and verification

No backend, database, clinical wording, generated translations, approval gates,
API permissions or inference changes. Keep source names/values exact. Lint,
typecheck, full unit suites and production builds in both portals. Meaningful
regressions cover table semantics, links, sorting/filtering and empty states.
Check contrast from actual tokens and test keyboard, zoom, English/Spanish and
mobile/desktop rendering where available. Record any unavailable live/visual
verification rather than inferring it from tests. No deploy or remote SQL.
