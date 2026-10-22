# CON-001 — Reviewed care-handoff summary and export

Status: implemented. Migration 089 applied; sharing (migration 096) is built and unapplied.

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

## Sharing an approved version with a named colleague (migration 096)

Requester decision, October 22: yes.

* **Who may share.** Only the author of the summary, while they still hold its care-team link,
  and only the approved current version. Editing returns the summary to draft, so a draft or an
  edited summary cannot be shared (`HANDOFF_NOT_APPROVED`, 422).
* **Who may receive** (the picker shows only these: name, specialty, clinic, and why):
  a clinician with an active link to the same patient at any active clinic where they are an
  active member, or an active member of the AUTHOR'S clinic (so a colleague taking over can
  receive it before they are linked). Never the author. Anyone else is
  `HANDOFF_RECIPIENT_NOT_ALLOWED` (422). The server re-checks this on every share and every read.
* **Per version, audited, revocable.** A share is one row per (summary, version, recipient). The
  title, purpose and approval are fixed at share time. Editing creates a new version; the share
  stays on its version. Events: `shared`, `share_revoked`, `shared_viewed` (once per ten minutes
  per reader), `shared_exported` (with format); the author's audit list names the recipient.
  Revoking is immediate: every recipient read, list and notification re-checks that the share is
  not revoked and the recipient is still an allowed recipient (leaving the clinic or ending the
  link also ends access; it returns only if eligibility does). Sharing again after a revoke is a
  new generation with its own notification.
* **What the recipient sees.** Only the shared version's content (sections, narrative, notes),
  read-only, "Shared by Dr. X on date", print and FHIR export (both audited). Source chips are
  labels only: the server strips record ids and links, since the recipient may not hold the
  patient's record. No team, version list, audit trail or other versions. "A newer version
  exists" appears only if that newer version is also shared with the same recipient.
  Sharing grants no access to the patient or to the summary's own endpoints.
* **Notification.** A `handoff_shared` item (clinician en-US copy, category follow-up, news not
  work, no email) is captured in the same transaction as the share, once per generation (event
  key `handoff_share:<share>:<generation>`), and links to `/handoff-shared/<share>`. The ledger
  helpers (`notification_source`, `_authorized`, `_actionable`, `_scope`, `_owner_sees`) are
  wrapped, not rewritten: the existing bodies are renamed to `*_core` and delegate for every other
  source. Risk: a later migration that does `CREATE OR REPLACE` on one of those names would drop
  the wrapper; the `care-handoff` shard covers the share notification end to end and fails if so.
* **API** (`/api/v1/care-team/clinician`): `GET /handoff-summaries/{id}/share-candidates?q=`,
  `GET|POST /handoff-summaries/{id}/shares`, `DELETE /handoff-shares/{share}`,
  `GET /shared-handoffs`, `GET /shared-handoffs/{share}`, `POST /shared-handoffs/{share}/export`.
  Clinician role; `no-store`; any refusal is the same 404. Author routes are keyed by summary.
* **OPS-006.** Authorization is a lock-free read before the single summary-row lock (rules 7, 9);
  share is idempotent (replay returns 200, no second event or notification; rules 4, 5);
  notification written in the share transaction (rule 6); 50 active shares per summary; database
  clock; ids and reason codes only in logs (rule 24); share rows change only by revoke or
  re-share (guard trigger); no PHI in logs.
* **UI.** "Share" on the approved review page opens a side panel (search, clinic chips, current
  shares with Revoke); "Shared with me" is a section of the handoff list page and its own page
  `/handoff-shared`, reached from the notification. Spanish for the notification is an unapproved
  draft (LOC-001) and is never shown: clinician-only.
* **Verification.** `test_care_handoff_shares_postgres.py` (CI shard `care-handoff`), router and
  presentation unit tests, `handoff-share.test.tsx`.
