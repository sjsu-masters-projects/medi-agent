# PLAN-002 — Care plans per care team

**Status:** PR #210 merged as `1e7dec24` (October 22); backend and portals implemented,
hosted migration/deployment and live acceptance not independently verified in #203's merge review.
Direction and conflict handling decided October 13. Part of CLN-003
(slice H). It changes the PAT-005 contract, so read the
[PAT-005 specification](pat-005-clinician-approved-today-feed-plan.md) first.

## Why

A patient with heart disease, an ear problem and a knee injury may see a cardiologist, an
ENT specialist and an orthopaedic provider, often at different clinics. Each provider
writes and approves their own instructions. Today MediAgent keeps **one care plan per
patient**:

- versions are numbered per patient (`UNIQUE (patient_id, version_number)`, migration 040);
- there is one open draft per patient;
- every document feeds that draft;
- whoever reviews the draft approves everything in it.

So a cardiology instruction and an ENT instruction share one plan and one approver.

## Model

- **A plan belongs to one care-team link: patient, clinician and clinic.** Each plan has
  its own versions, open draft, approver and audit trail. Only a clinician on that care
  team can edit, approve or retire it.
- **Facts are shared; plan items are not.** Reviewed medications, allergies and conditions
  stay one patient-wide record, each medication tagged with the plan and care team that
  added it. This is the shared clinical core in CLN-003.
- **Documents feed the right plan.**
  - A clinician's upload belongs to their care team.
  - A patient upload asks "Which care team is this for?", listing the patient's care teams
    plus "Not sure". Each named care team's clinician reviews it; "Not sure" goes to every
    care team's review queue until one claims the whole document.
  - Extracted facts still enter the shared record only through the review path.
  - Drafting uses the documents routed to that plan, plus the shared medication list for
    reconciliation.

## Patient experience

- Today shows one list built from every approved plan. Each activity names its plan
  ("Cardiology · Dr. Elena Park · Cedar Grove").
- Today can be filtered by care team, and "Care plan details" opens that plan.
- Reminders, completions and barriers stay per activity and are reported to the plan's
  care team only.
- Nora answers from all of the patient's approved plans, and cites which plan an
  instruction came from.

## Safety across plans

The polypharmacy core of the product. When a draft is previewed or published, it is
checked against the patient's other approved plans and the shared medication list.

**What is checked:**

| Check | Example |
| --- | --- |
| Duplicate therapy | two plans with the same ingredient |
| Conflicting instructions | different doses or schedules for the same medication |
| Stop versus continue | this draft stops a medication that another plan keeps active, or the reverse |
| Interaction coverage | Comprehensive interactions/equivalence are unchecked: the requester subsequently excluded that engine from MED-001. Never invent severity or describe public reference retrieval as an interaction check. |

**How a blocker is handled (decided October 13: conflicts block publication):**

1. **Shown where the clinician is working.** The draft shows a "Conflicts with other
   plans" blocker on the item. It shows both instructions side by side, with the other
   plan's specialty, clinician, clinic and approval date, and the shared-list entry they
   overlap on.
2. **The reviewing clinician chooses one of four resolutions.** The clinician changes only
   their own plan; the other plan is never edited from here.
   - **Change this item** (dose, schedule or wording) or **remove it**. The check runs
     again, and the blocker clears if the conflict is gone.
   - **Keep both, with a reason**, when the overlap is intended (for example two
     prescribers agreed on a combination). A written reason is required. This
     acknowledgement clears the blocker for that conflict and is audited.
   - **Ask the other care team.** This sends a "Cross-plan conflict" review item and a
     care-team message to the other plan's clinician. The item stays blocked until they
     reply, or until this clinician resolves it in another way.
   - **Publish without this item.** The rest of the plan publishes; the conflicting item
     stays in the draft as pending.
3. **By severity.**
   - **Must be resolved or acknowledged with a reason:** stop versus continue, a
     supported duplicate ingredient/name identity, and conflicting dose/instructions
     for that identity. Same-name comparisons are review flags, not equivalence proof.
   - **Warning only, with acknowledgement optional:** non-medication schedule overlaps.
   - Interaction severity is not available without a maintained rules source; no
     major/minor interaction verdict is asserted by this increment.
4. **The other care team is always told.** They get a review item ("The orthopaedic plan
   by Dr. X conflicts with your cardiology plan: duplicate ibuprofen"), can adjust their
   own plan, and see the reason if the conflict was acknowledged.
5. **The patient is unaffected until it is resolved.** Their current approved activities
   stay in Today unchanged. The patient never sees the conflict itself, only the result
   once a plan is published.

## When a care team ends

Decided October 13:

- **Approved activities stay in Today.** Medications must not stop because of an
  administrative change; some, such as anticoagulants, are dangerous to stop suddenly.
- **The plan becomes "unowned".** Its activities show "Prescribed by Dr. X, no longer on
  your care team. Ask your care team before changing it." Reminders continue.
- **Someone must adopt or retire it.** A review item goes to the patient's remaining care
  teams and to the clinic admin. A clinician can adopt the plan (it becomes theirs) or
  retire specific items. Nothing is removed automatically.
- **If the patient has no other care team,** the patient is told to contact their clinic.
  The clinic admin's review item stays open until it is handled.

## Migration from one plan per patient

- Existing plans move to the care team of their approving clinician, or the patient's only
  care team when there is one.
- Version history, item identities, reminders, completions and barriers are kept.
- Any draft that cannot be assigned unambiguously goes to a review item. It is never
  guessed.

## Decisions

1. **Decided October 13:** a plan belongs to one care-team link (patient, clinician,
   clinic), not to a specialty.
2. **Decided October 13:** cross-plan conflicts block publication, resolved as described
   in "How a blocker is handled".
3. **Decided October 13:** activities stay in Today when a care team ends, until a clinician adopts or retires them.
4. **Decided October 13:** a patient upload marked "Not sure" appears in every one of the
   patient's care teams' queues. Any of them can claim the whole document; once one does, it
   leaves the other queues, and the claim is audited.

5. **Decided October 22:** Today shows ONE combined entry when two or more approved plans
   contain the same activity with identical instructions (a medication duplicate resolved
   with "keep both, with a reason", or a warning-only non-medication overlap). The key is the
   same supported medication identity (or the same normalized activity) AND identical
   dose/frequency/route/instructions/schedule; any difference keeps the entries apart, and
   publication stays blocked for a medication difference, so a combined entry never hides a
   difference. The entry names every owning care team, has one reminder and one check-off,
   and a completion or barrier is written once per underlying plan item and reported to each
   owner. It is a read-model grouping, recomputed on every read: plan items are never merged
   or deleted, so retiring or changing one side simply dissolves the group and the entry
   falls back to the remaining item with its history. An unowned side participates with its
   "no longer on your care team" label.

## Implementation sequence

**Status (October 21):** the requester asked for full G/H implementation in
PR #210 (branch `feature/voice-mode-and-chat-polish`). This pass delivers the backend
(phases 1-3 below plus the unowned lifecycle and merged Today read) and the API
contract; the portals (phase 4) are a follow-up pass on the same PR. The starter
conflict-policy module is reused. No remote migration, deployment or merge is
authorized.

This is a substantial replacement of the patient-global plan boundary, not a UI
filter. Current main has one draft/version sequence per patient, patient-scoped
generation, publication that supersedes patient-wide projections, and broad
assigned-clinician reads. None may be treated as already per-team.

1. **Domain and migration foundation:** explicit plan lineage and exact care-team
   ownership, fail-closed scope selection, deterministic source-based conflicts,
   content-bound conflict resolutions, append-only ownership/conflict audit. Legacy
   owner assignment must be unambiguous; unresolved ownership stays visible for
   review, never guessed. Applied migrations are immutable.
2. **Shared clinical core / private sources:** medications/allergies shared with
   recording-team provenance; patient-controlled sensitive conditions; owned
   documents, plan details, messages, SOAP and ADR records. Audit every clinician
   read path (including timeline, exports, source preview and notifications), not
   only the new screen. Cross-team conflict summaries reveal only the permitted
   medication instruction and plan metadata, not private source documents.
3. **Routed drafting and atomic publication:** patient team picker/Not sure claim,
   exact clinician upload scope, per-plan generation/drafts, patient-wide
   publication lock and current-state cross-plan checks inside SQL. Preserve
   bilingual/source/overlap gates. Publishing one plan must not deactivate another
   plan's projections. Retries must be content/actor/source bound.
4. **Portals and follow-through:** owner selection and conflict resolutions,
   patient merged Today and care-team filter/details, approved-plan Nora provenance,
   activity-owner barrier/reminder routing, unowned plan review/adopt/retire. Team
   departure never changes medication status or silently stops reminders.
5. **Acceptance:** two clinicians/two clinics, independent concurrent drafts,
   private-source denial and sensitive-condition non-disclosure, duplicate/stop/
   dose conflict + stale acknowledgement, concurrent publication/claim/adoption,
   same clinician at two clinics, ambiguous legacy records, revocation, no remaining
   team, bilingual mobile/desktop states and unchanged activity identities/history.

Use existing services/RPC patterns; no autonomous clinical decisions, no remote
migration, deployment, backfill or merge is authorized by this task. Foundations
and local tests are not full G/H completion; record each integrated acceptance
path before marking Done.


## Delivered in PR #210 (backend)

Migrations (unapplied; no remote SQL is authorized):

| File | What it does |
| --- | --- |
| `083_care_team_plan_ownership.sql` | `care_plans` (one plan per care-team link, owner, `ownership_state`, last-owner snapshot); per-plan versions, one open draft and one approved version per plan (replaces the per-patient constraints); per-plan generation requests, claim, completion and publication guard; legacy backfill (approver's only link, then the link the activities were projected for, then the patient's only care team; ambiguous becomes `unassigned_legacy` and opens a review item, never guessed); team-ends trigger (plan becomes `unowned`, activities and medications untouched, review items to the remaining teams and, without patient detail, the clinic's admins); `adopt_care_plan` and `retire_care_plan_items` (patient-wide lock, exactly one adoption winner); append-only ownership trail; plan RLS follows the owning link. |
| `084_care_team_owned_records.sql` | Document owner and routing (`routed`/`unrouted` = "Not sure"), atomic `claim_document`, drafting only from the plan's own routed sources (`care_plan_source_fact_ids`); provenance, import, SOAP, ADR-review and MedWatch owner columns; recording-team stamping for medications, allergies and conditions; patient-controlled `conditions.is_sensitive` with an audited RPC and the `shared_clinical_summary` RPC; clinician-session RLS and the storage policy follow ownership; browser writes to conditions and allergies revoked. |
| `085_cross_plan_publication.sql` | The only cross-plan comparison (`care_plan_cross_conflicts`), resolutions, review-item replies, `publish_care_plan_version` (authorization, patient advisory lock, idempotency record, current-state conflict check, exclusions carried to the next draft, per-plan supersession; publishing never deactivates another plan's activities); conversation activity context and review restricted to the conversation's own team. |
| `087_clinical_record_owner_and_review_notifications.sql` | ADR review and MedWatch creation take the acting care team and write the owner in the same transaction (the old bodies are wrapped; the ownerless signatures leave the Data API schema; a deferred constraint trigger refuses a new review or draft without an owner); backfill assigns only the unambiguous, otherwise the record is unassigned (visible to no clinician) with an `unowned_clinical_record` review item to each active team and `assign_clinical_record_owner` (one winner); care-team review items are captured as notification-centre items (`care_plan_review`) for the addressed team's clinician. |
| `086_care_team_notification_scope.sql` | Notification fan-out and "open an item" follow record ownership; critical results stay shared with a neutral copy for teams that do not hold the document. |

Contract tests (disposable PostgreSQL 16, CI shard `care-team-plans`): 25 ownership and
backfill, 35 shared core and records, 38 publication, 24 notification, 14 record-owner cases.

### Lock order

Authorization reads (no locks) -> patient fence (`private.lock_care_plan_evidence`, the
patient-wide advisory lock used by documents and generation) -> idempotency record ->
`care_plans` row -> `care_plan_versions` row -> items (item trigger) -> projections. Clinic
and clinician locks are not taken by these functions. Adoption, retirement, claiming,
resolutions and publication all follow this order, use the database clock and write ids,
never clinical text, to logs.

### Read-path audit (clinician reads of owned or sensitive data)

Every path below has a unit test that fails if its check is removed; the SQL paths have
Postgres tests. "Fixed" = it leaked before this PR.

| Path | Result |
| --- | --- |
| Patient deep dive (conditions, other teams, SOAP, obligations, barriers, rates, documents) | Fixed |
| Patient detail header, patient list, sent messages, email-to-patient | Already safe (demographics or own rows only) |
| Timeline | Fixed (documents, visits, plans, ADR, facts, adherence by owner) |
| Risk radar and score | Fixed (per clinician; other teams' adherence and acted-on ADR excluded) |
| SOAP generation context and saved notes | Fixed (filtered context; stored with the team) |
| ADR queue, detail, review; MedWatch list, preview, export, approve, discard, submission | Fixed (pending is shared, reviewed is the reviewing team's) |
| Dashboard counts | Fixed |
| Documents: list, get, source preview, retries, review queue, approve, reject, annotate | Fixed (unrouted must be claimed before approve or reject) |
| Extracted facts and citations, reconciliation preview and apply, sensitive-condition match | Fixed |
| FHIR/SMART: imports, facts, lineage, source, audit export, identity binding, medication reference, external-record workload | Fixed |
| Notifications and email recipients, opening an item, read-through, acknowledge | Fixed in SQL (086); critical results stay shared |
| Direct browser sessions (PostgREST): documents, facts, citations, provenance, SOAP, conditions, ADR, MedWatch, care-plan tables, stored files | Fixed (RLS and storage policy follow ownership) |
| Care conversations, appointment offers | Already per link in SQL; the visit list rule is an open question below |
| Search and export endpoints | None outside the paths above (the only `ilike` is the clinic join code) |

### API contract (PR #210)

All paths are under `/api/v1`. Errors use the existing envelope
`{"error": {"code", "message", "details"?}}`. Types: `packages/shared/src/types/care-team-plans.ts`.
A care plan is addressed by `care_plan_id`; the existing `{plan_id}` path segment of the
version routes is the VERSION id (unchanged for compatibility).

**Clinician: plans**

- `GET /care-plans/clinician/patients/{patient_id}/plans` -> `{plans: ClinicianPlanListEntry[]}`.
  Own plans carry `active_version_id`, `draft_version_id`, `generation`; another team's plan is
  only `{owner, approved_at, is_mine:false}`; an unowned or unassigned plan lists
  `adoptable_by_care_team_ids`.
- `GET /care-plans/clinician/patients/{patient_id}`, `/review-context`, `/generation` and
  `POST .../retry-generation` take optional `care_team_id` and `care_plan_id`. With two links
  that both have plans and neither named: 422 `CARE_TEAM_REQUIRED`,
  `details.options[{care_team_id, care_plan_id}]`.
- `GET /care-plans/clinician/patients/{patient_id}/care-team-options` -> my exact active links
  (`ClinicianCareTeamOption`: `care_team_id`, `clinic_id`, `clinic_name`, `specialty` nullable).
- `PUT .../{version_id}`, `.../items/{id}/translate`, `.../back-translate`,
  `GET .../today-preview`: unchanged; another team's version is `404 NOT_FOUND`.

**Clinician: publication and conflicts**

- `GET .../{version_id}/cross-plan-review` -> `CrossPlanReview`: every conflict with both
  instructions (`ours`, `theirs`: medication fields only; non-medication overlaps reveal only
  the category), `other_plan` metadata (specialty, clinician, clinic, approval date,
  ownership state), `acknowledged`, `acknowledged_reason`, `asked_other_team`, and
  `interaction_coverage: "not_checked"` (interaction severity is never asserted).
- `POST .../{version_id}/conflicts/{fingerprint}/resolution`
  `{resolution: "keep_both"|"ask_other_team", reason}` (reason required, 1-2000). Tells the
  other care team. A fingerprint binds both exact instructions: if either changes, 409
  `CONFLICT_CHANGED` and a fresh review gives a new fingerprint. Change or remove an item with
  the existing `PUT`; publish without an item with `excluded_item_ids`.
- `POST .../{version_id}/approve` `{note, idempotency_key?, excluded_item_ids?}` ->
  `PublishCarePlanResult`. Unresolved blockers: 409 `CROSS_PLAN_CONFLICT`,
  `details: {conflicts, interaction_coverage}`; same key with a different request: 409
  `IDEMPOTENCY_KEY_REUSED`; already published: 409 `CONFLICT`. Nothing is published on any
  error. `warnings` lists non-blocking overlaps.
- Notification centre: a review item addressed to a care team appears in that team's clinician
  list and action count as `event_type: "care_plan_review"` (`metadata.review_kind`, link
  `/patients/{id}?tab=care-plan&review={item_id}`), only for the addressed team's clinician; it
  stops being actionable when resolved. `POST /care-plans/clinician/records/{adr_assessment|medwatch_draft}/{id}/take`
  `{care_team_id}` (409 `RECORD_ALREADY_TAKEN`) takes up a record that has no care team.
- `GET /care-plans/clinician/review-items?status=open` -> `{items, clinic_items}`; each `items`
  entry also carries `patient_name`, `clinic_id` and `clinic_name` (what this clinician already
  sees for that patient through the addressed link); `clinic_items` stay non-PHI;
  `POST .../review-items/{id}/reply` `{note?}` (a reply informs the asker; it never clears the
  blocker).

**Clinician: unowned plans**

- `GET /care-plans/clinician/patients/{patient_id}/plans/{care_plan_id}/activities` (only for a
  plan nobody owns), `POST /care-plans/clinician/plans/{care_plan_id}/adopt`
  `{care_team_id, note}` (409 `PLAN_ALREADY_ADOPTED` for the loser), `POST .../retire-items`
  `{care_team_id, item_ids, reason}`.

**Clinician: shared core and documents**

- `GET /care-team/clinician/patients/{patient_id}/shared-summary` -> `SharedClinicalSummary`
  (`some_conditions_private` is the explicit marker; recording team on every record; other
  care teams with plan metadata).
- `GET /documents/claimable?patient_id=` (routing queue: my routed documents plus unrouted
  ones, each with `needs_claim`, `claimable_care_team_ids`); `POST /documents/{id}/claim`
  `{care_team_id}` (409 `DOCUMENT_ALREADY_CLAIMED`); `POST /documents/patients/{patient_id}`
  takes optional `care_team_id` (required when I hold several links: 422 `CARE_TEAM_REQUIRED`).
  Approve and reject of an unrouted document: 422 `DOCUMENT_CLAIM_REQUIRED`.
- `care_team_id` is optional on SOAP generation, ADR review and MedWatch draft creation and is
  required (422 `CARE_TEAM_REQUIRED`) when the clinician holds several links to the patient.

**Patient**

- `GET /documents/care-team-options` -> `UploadCareTeamOption[]` (`specialty` nullable); `POST /documents/` takes
  `care_team_id` or `not_sure: true` (two or more teams and neither: 422 `CARE_TEAM_REQUIRED`).
- `GET /feed/today?care_team_id=<uuid|"unowned">` -> existing fields plus per task
  `plan_owner`, `plan_owners`, `combined_item_ids`, and `care_team_filters`, `contact_clinic`
  at the top level (`TodayTaskOwnership`, `TodayOwnershipSummary`). `plan_owner.unowned_notice`
  drives "Prescribed by Dr. X, no longer on your care team. Ask your care team before changing
  it."; `contact_clinic` is the "contact your clinic" state. Names are parts, not a label; the
  portals compose "Specialty · Dr. Name · Clinic" with their i18n.
- `GET /care-plans/patients/{patient_id}` -> the merged approved plans (`items[].plan_owner`,
  `plans[]`); retired items are omitted.
- `GET /care-team/patient/conditions`, `PUT /care-team/patient/conditions/{id}/sensitivity`
  `{is_sensitive}` (own conditions only; anything else `404`).
- Nora's context carries `plan` provenance on each medication and activity and a `care_plans`
  list; she cites the plan owner.

## Decided by existing rule (revisit before real use)

- **Visits within a clinic.** A colleague with a link at the same clinic can list, edit and
  export another team's visit (the October 17 decision, kept as is). It differs from
  "visit details are owned by one care team"; revisit before real use.
- **Confirmed-symptom hand-off** (071) messages every assigned clinician with the symptom name
  and severity. Kept shared as safety information; revisit before real use.

## Known limitations

- **SMART launch with two links to one patient** (for example the same clinician at two
  clinics) is refused, fail-closed, with `422 CARE_TEAM_REQUIRED` and
  `details.limitation = "smart_launch_single_link_only"`; the message tells the clinician
  nothing was started and to upload the records as documents instead. Follow-up: a team
  column on `smart_launch_sessions` and an optional `care_team_id` on the launch request.
- **Combined Today entries and reminders.** The dispatcher sends one reminder per entry
  (keyed on the entry's id; deterministic, idempotent, safe under concurrent runs because the
  existing unique notification key decides). If grouping cannot be read it logs and sends
  ungrouped rather than lose a reminder.
- **Clinic-admin work items** carry no patient, and a notification-centre item always names
  its patient, so they stay on `GET /care-plans/clinician/review-items` (`clinic_items`).
- **Storage policy evidence.** `ALTER POLICY ... ON storage.objects` runs as the migration
  role that already created that policy: `003_storage_and_auth.sql` creates
  `documents_read_clinician` on `storage.objects`, and `020_harden_database_security.sql`
  alters every `storage.objects` policy with `ALTER POLICY` in a loop; both are applied
  hosted. Migration 084 uses the same statement for the same object.

## Other open questions

1. **Nora chat, symptom reports and adherence rows** remain patient-wide tables. Clinician
   reads of adherence for another team's activities are filtered in the API, not the table.
2. **Orphaned documents** (owner link deleted) stay routed to nobody and are hidden from every
   clinician; the evidence behind approved activities is not reachable. A re-route tool is out
   of scope.
3. **Reviewed records with no determinable team** (older ADR reviews and MedWatch drafts) are
   unassigned: visible to no clinician until one care team takes them
   (`POST /care-plans/clinician/records/{adr_assessment|medwatch_draft}/{id}/take`; each active
   team of the patient gets an `unowned_clinical_record` item). New reviews and drafts can no
   longer be written without an owner.
4. **Legacy documents** that cannot be attributed (patient with several teams) become
   "Not sure" (visible to each team that could see them before) until claimed.
5. **Portals** (picker, owner chips, conflict screens, adopt/retire, sensitive toggle, claim
    queue) are the follow-up pass; this API is their contract.


## Portal screens (PR #210, branch `feature/care-team-portals`)

Built against the API contract above; verified with mocked-API unit tests and local screenshots
only. A live two-clinician, two-clinic run against a real backend is still required.

**Patient portal**

- Today: owner line under each title ("Cardiology · Dr. Park · Cedar Grove"; a combined entry names
  every owner and has one check-off), a horizontal chip filter (only with two or more owners; scrolls
  inside itself), the muted "no longer on your care team" caption (shown even for a single unowned
  plan) and the "Contact your clinic" card. A single-team patient sees today's screen unchanged.
- Care plan details grouped by care team; falls back to the single list when any item lacks an owner.
- Records upload: "Which care team is this for?" radio cards plus "Not sure" before anything is
  uploaded (one team is preselected, read-only). `CARE_TEAM_REQUIRED` reopens the question. No care
  teams or an unreadable list keeps the previous direct upload.
- Records: a "Health conditions" list with a "Keep private" switch, a confirm step in both directions,
  an optimistic change and rollback with an alert when the save fails.

**Clinician portal**

- Patient record, Care Plan tab: "Care plans" area only when there are two or more plans, another
  team's plan, or review items. My plans are full cards (draft/approved/unowned, clinic chip for
  multi-clinic users) and select which plan the draft review shows (`care_team_id`/`care_plan_id`
  sent only when I hold several plans); other teams are compact read-only rows with a shared
  medication list; plans nobody owns offer Adopt and Retire items. Badge count on the tab.
- Draft review: red "Conflicts with another care team's plan" card per item, comparison (stacked in
  narrow panes), four choices (change, remove, keep both with a reason of at least 10 characters,
  ask the other care team, then "Waiting for Dr. X"), amber collapsible warnings, the persistent
  "Interaction severity is not checked" line, disabled Approve with "N conflicts to resolve", and
  "Publish without these items" with a confirmation listing exclusions. One idempotency key per
  attempt, reused after an unknown outcome and replaced after a definite refusal. Handles
  `CROSS_PLAN_CONFLICT`, `IDEMPOTENCY_KEY_REUSED`, `CONFLICT_CHANGED` and a stale acknowledgement.
- Review items: `/care-plan-reviews` (clinic filter, roster join for names/clinics, non-PHI clinic
  work rows for admins), reply/mark seen, adopt (`PLAN_ALREADY_ADOPTED` handled), retire, take an
  unowned ADR/MedWatch record (`RECORD_ALREADY_TAKEN` handled). Deep links:
  `/patients/{id}?tab=care-plan&review={item_id}` (a missing or resolved item is explained),
  `/care-plan-reviews?item={id}` and `?patient={id}`. Linked from Alerts.
- Documents: unrouted uploads show "Patient uploaded · not routed to a care team" with Claim and a
  confirmation (`DOCUMENT_ALREADY_CLAIMED` removes the row); approve/reject answered by
  `DOCUMENT_CLAIM_REQUIRED` switches to the claim state.
- Shared clinical summary (Profile tab, only for several care teams or private conditions): "Recorded
  by" captions, a neutral "Some conditions are kept private by the patient" row, "Also cared for by".
- A required care-team select (only with two or more links) for document upload, SOAP, ADR review and
  MedWatch draft creation. SMART launch with two links shows the plain "nothing was started" message.

**Contract gaps and notes for the backend**

- Review items carry ids only: the view joins the clinician's roster for patient names and clinics.
  Adding `patient_name` and `clinic_id/name` would remove that join.
- "Ask the other care team" requires a reason (1-2000); the portal prefills an editable question.
- `care-team-options` has no specialty, so the select labels links by clinic name.
- Review items have no endpoint to resolve `conflict_reply`; the portal shows them read-only.

**Pending es-MX wording drafts, not approved (LOC-001 review required):** every string in
`apps/patient-portal/src/content/care-team-copy.ts` (Today filter, unowned/contact-clinic, upload
picker, conditions privacy, plan group labels), including `¿Para qué equipo de atención es esto?`,
`No estoy seguro`, `Tus equipos de atención decidirán quién lo revisa.`, `Mantener privada`,
`Ya no está en tu equipo de atención` and `Comunícate con tu clínica`. The clinician portal is
English only.
