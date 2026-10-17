# UX-005 — ADR review and MedWatch workspace

Status: accepted design (October 16, 2026); merged and deployed ([#179](https://github.com/sjsu-masters-projects/medi-agent/pull/179), mobile stepper fix [#180](https://github.com/sjsu-masters-projects/medi-agent/pull/180)); remaining deployed checks are on the board (UX-005). Owner: Rajeev. Builds on PV-001
(ADR review) and PV-002/PV-001-C (Form 3500 drafts and PDF export).

## Problem

Production review on October 16 found the `/medwatch` page hard to use. Every
ADR case renders as a fully expanded card (evidence, Naranjo inputs, missing
information, actions), and every Form 3500 draft renders below them as a full,
always-open editor. With more than a few cases the page becomes a long scroll
with no overview. The Form 3500 "preview" is an HTML table, not the document
the clinician actually sends.

## Decisions

1. **ADR Reviews is a work queue.** `/adr-reviews` shows a compact table, one
   row per case: patient, symptom/event, suspect medicine, Naranjo score and
   band, status, age, and a count of missing items. Status tabs: Awaiting
   review · Information requested · Reviewed · Dismissed. Sort by score or
   age; search by patient or medicine. No evidence is expanded in the list.
2. **Each case opens on its own page**, `/adr-reviews/[assessmentId]`.
   Evidence first, each answer with its provenance label; the actions
   (Request information, Mark reviewed, Dismiss, Prepare MedWatch draft) sit in
   a fixed side panel (stacked under the evidence on narrow screens). Back
   returns to the queue with its tab and filters intact.
3. **Patient view.** The patient record gets an "ADR" tab listing that
   patient's cases, current and past, linking to the same case page.
4. **MedWatch is its own sidebar section**, `/medwatch`, separate from ADR
   Reviews. A table of reports with tabs Drafts · Approved · Submitted ·
   Discarded; each row shows the patient code, product, event, status and last
   update.
5. **A report opens on its own page**, `/medwatch/[draftId]`, as steps:
   1. *Complete* — the gate issues (missing or "check this" fields) listed
      first, each linking to its field; full Form 3500 sections are
      collapsible and collapsed by default.
   2. *Preview* — the actual filled Form FDA 3500 PDF, shown inline.
   3. *Approve* — the existing attestation dialog.
   4. *Download and record submission* — the existing audited PDF/JSON export
      and record dialogs.
6. **The preview is the PDF.** Before approval the preview is watermarked
   "DRAFT – not for submission" and is not an export: it does not create an
   export record or change draft state. Each preview is audited as a separate
   `preview_viewed` event with the actor (decided October 17; migration 070). The audited, unwatermarked
   download stays tied to approval. The field-table preview is kept only as
   the editing view.

## UI review fixes (October 17)

- The status filters on both lists are toggle buttons (`aria-pressed`) in a labelled group, not
  a tab widget: they filter one list in place and have no separate panels. They show a visible
  focus ring, and the chosen one scrolls into view on narrow screens.
- Truncated names, products and events carry a `title` with the full text.
- The stepper's buttons read "Previous: <step>" and "Next: <step>"; the visible text is the
  accessible name.
- The PDF preview keeps a visible "Open in new tab" link (at least 40 px tall) at every width,
  because iOS often will not render a PDF inside an iframe.
- Sort and filter controls are 40 px tall below the `md` breakpoint.

## Backend changes

- `GET /clinicians/me/adr-assessments/{id}` and
  `GET /clinicians/me/medwatch-drafts/{id}`: single-item reads with exactly
  the same authorization as the list endpoints (assigned clinician, active
  care-team link). Unknown or unauthorised IDs return the same 404.
- `GET /clinicians/me/medwatch-drafts/{id}/preview.pdf`: the filled Form 3500
  with a "DRAFT – not for submission" watermark on every page, for any draft
  state the clinician can read. Not recorded as an export; `Cache-Control:
  no-store`; `Content-Disposition: inline`.
- List endpoints accept the status filters the tabs need. No schema changes.

## Must not change

- Authorization, audit events, approval attestation, the export gate and the
  draft revision history behave as today.
- The ADR score stays labelled as decision support, never a clinician verdict.
- Old `/medwatch` links to a case redirect to the new case page.
- Both 390 px and 1280 px layouts work without horizontal scrolling; the
  clinician portal stays English-only.

## Acceptance

- With 25+ synthetic cases the queue fits on one screen per page of results
  and no case expands inline.
- A clinician can go queue → case → prepare draft → complete → PDF preview →
  approve → download without leaving the two sections.
- The preview PDF is watermarked, writes one `preview_viewed` audit row and no
  export row; the
  approved download is unwatermarked and audited as today.
- Focused backend tests for the three endpoints (authorization, 404,
  watermark, one preview-viewed row and no export row); portal tests for the queue, case page, report
  stepper and redirects; lint, typecheck, build; deployed check in the
  clinician portal.
