# CON-001 — Reviewed care-handoff summary and export

Status: implemented, in review. Migration 089 (unapplied).

## Goal

A clinician drafts a handoff summary for one of their patients (for a colleague, another
care team or a transition of care), reviews and edits it, approves it, and only then
exports it. It reuses the #208 bounded timeline and the PLAN-002 care-team ownership rules;
it adds no event store and no parallel timeline.

## Acceptance path

1. Patient record → "Handoff summary" → choose purpose, optional recipient, care team (when
   the clinician holds several links) → "Create draft".
2. The server assembles the sections deterministically (no model) from records the author
   may see, stores them as version 1 and opens the review page.
3. Review: each section collapses; each line has a source chip linking to its record; the
   narrative and notes are written by the clinician. Saving creates a new version;
   "Rebuild from records" re-reads the sources as a new version.
4. Approve (with a confirmation) pins the current version. Print and FHIR export are enabled
   only for the approved current version; any edit returns the summary to draft.
5. Version history and the audit list (created, edited, refreshed, approved, exported with
   format) are shown. Every export, including print, is an audit event.

## Sections and visibility

| Section | Source | Who may see it |
| --- | --- | --- |
| Patient | `patients` | Assigned clinician |
| Shared record | `shared_clinical_summary` function: active medications, allergies (each with recording team and clinic), non-sensitive conditions, plus the author's own team's sensitive conditions | Shared core; other teams' sensitive conditions become the line "Some conditions are private and are not included in this summary." |
| Your care team's plan | Latest approved version of the plan owned by the author's link | Author's team only |
| Recent activity and adherence | Last 30 days of `adherence_logs`, filtered by `ActivityScope` | Shared activities plus the author's team's |
| Recent confirmed symptoms | `patient_confirmed` reports, 30 days | Shared |
| Open medication-safety reviews | `adr_assessments` reviewed by the author's team, not dismissed/submitted | Author's team only (unreviewed items are not copied) |
| Upcoming visits | Scheduled/confirmed/proposed appointments of the author's link | Author's team only |
| Timeline highlights | `PatientTimelineService` (#208), newest 8, private conversations excluded | Same scope as the timeline |

A section whose read fails is `unavailable` (never `empty`), approval is refused while any
section is unavailable, and nothing is logged beyond the failing section name and exception
type.

## Model-written narrative

Not implemented. No existing grounded generation path fits a reviewed, source-cited
handoff, and deterministic sections must not depend on a model. The narrative is written by
the clinician and labelled as such. If a draft generator is added later it must be a clearly
marked draft with citations and must never feed the deterministic sections.

## Storage (migration 089)

* `care_handoff_summaries`: header, one per summary, belongs to one care-team link
  (`care_team_id`) and its author; `status` draft/approved; `current_version`;
  `approved_version/by/at`.
* `care_handoff_summary_versions`: append-only snapshots (sections JSON, narrative, notes).
  Deleted only when the summary row is erased with its patient.
* `care_handoff_summary_events`: append-only audit (ids and types only, no clinical text).
* All tables: RLS enabled, no policies, no grants to `anon`/`authenticated`. Access is
  through `SECURITY DEFINER` functions (fixed `search_path`) granted to `service_role`
  only. Each function re-checks the actor's active link to the summary's team in the
  database; a missing summary, another team's summary and another patient's summary give the
  same answer (`42501`).
* OPS-006: row lock on the summary for every writer; optimistic `expected_version`
  (`40001` → HTTP 409 `HANDOFF_VERSION_CONFLICT`); create is idempotent by client-supplied
  id; approve is a replay-safe no-op; advisory lock plus a bound of 50 summaries per
  patient/team and 200 versions; database clock; no PHI in logs.

## API (`/api/v1/care-team/clinician/patients/{patient_id}/handoff-summaries`)

`POST` create (201, 200 on replay) · `GET` list · `GET /{id}?version=` · `PUT /{id}` save
(`expected_version`, narrative, notes, title, `refresh`) · `POST /{id}/approve` ·
`POST /{id}/export` (`version`, `format`: `print`|`fhir`). Clinician role only; responses
are `Cache-Control: no-store`. Unassigned clinicians get 403 (audited,
`NO_CARE_TEAM_ASSIGNMENT`); other teams' summaries get 404; export of anything but the
approved current version gets 422 `HANDOFF_NOT_APPROVED`.

## Export format decision

* Printable view: the review page's document region prints through the existing
  `.ma-print-root` stylesheet (navigation and actions hidden, collapsed sections expanded).
* Portable: a FHIR R4B document Bundle (Composition + Patient + Practitioners + Provenance)
  rather than a DocumentReference or a server-generated PDF. A Composition carries the
  sectioned, source-cited content; every source line becomes a Composition section entry
  and a Provenance entity (`urn:mediagent:source-record`). It reuses the `fhir.resources`
  R4B validation already used by the audit export, and is generated on demand, never
  pushed to a server.

## Localisation

The summary is a clinician-facing document (en-US, as the rest of the clinician portal).
Nothing here is shown to patients, so no es-MX wording is added; if a patient-facing
version is ever added it needs es-MX drafts pending LOC-001.

## Verification

Backend unit and router tests, a Postgres contract (`test_care_handoff_summaries_postgres.py`,
CI shard `care-handoff`), and clinician-portal vitest (`handoff-summary.test.tsx`).
