# Care plans and the Today feed

A care plan is the set of patient-facing instructions one care team writes and a clinician
approves. The patient sees every approved plan as one Today list; clinicians on each team
review, publish and follow up.

## What it does

- **Clinician.** Documents and entries produce a cited AI draft for one plan. The clinician
  checks each item beside its source and both languages, resolves conflicts, previews Today
  and approves the whole version. Other teams' plans show as metadata plus shared medications.
- **Patient.** Today shows approved, effective activities labelled with their plan and
  filterable by team. Completions and barriers go to the owning team. Nora answers from
  approved plans and names the plan. A patient may attach one activity to a private
  message; the clinician may open it in a draft.
- **Team ends.** The plan becomes unowned and keeps its activities until a remaining
  clinician adopts it or retires items.

## Rules it must keep

1. The model drafts, never publishes. A clinician on the plan's care team approves the
   complete version. Another team's plan answers `404 NOT_FOUND`.
2. A plan belongs to one care-team link (patient, clinician, clinic), not a specialty, with
   its own versions, one open draft, one approved version and audit trail.
3. Every draft item carries source fact, citation and confidence. The generator gets
   grounded facts only; it may not invent dose, schedule, duration, hydration target,
   generic advice or booking. FHIR/SMART candidates never feed a draft by import alone.
   Patient uploads feed one only after clinician review; pending, rejected, missing or
   withdrawn sources fail closed ([review gate](../patient-upload-care-plan-review-gate.md)).
4. Blockers stop approval: confidence below 0.7, changed or conflicting medication, missing
   instruction, frequency or supported route, unresolved overlap. A source that says stop
   or hold a medication cannot be confirmed (it would publish "take"); remove the item.
   Confirmation never supplies missing text; oversized wording is never truncated.
5. Overlap groups (same source, same name, strength or form variants) are review flags, not
   equivalence; the API and a database trigger reject unresolved ones. Each medication
   needs an explicit create or update decision against current records; a same-name active
   medication blocks creating another, and another plan's medication is not updatable here.
6. Every active item needs English and Spanish wording checked in this review
   ([language](language.md)). Offline stub wording is never verifiable or publishable.
7. Publication is one transaction under a patient-wide lock with an idempotency record; a
   failure leaves the prior plan active. Approved wording is immutable; history, reminders,
   completions and barriers are never rewritten. An activity keeps its identity only when
   source fact, category, wording, frequency and schedule match exactly. Publishing one
   plan never deactivates another plan's activities.
8. Cross-plan blockers: duplicate therapy (supported ingredient or name identity), different
   dose or instruction, stop versus continue, checked against current state inside the
   publish transaction. Same-name matches are flags. Interaction severity is never asserted
   (`not_checked`); reference lookup is never called an interaction check.
9. A blocker clears by changing or removing the item, "keep both" with a written reason
   (audited), or publishing without the item (it stays pending). "Ask the other team"
   notifies them and never clears it. A fingerprint binds both exact instructions; if
   either changes the acknowledgement is stale. Non-medication overlaps only warn.
10. Another team sees only medication instruction fields and plan metadata, never private
    source documents; non-medication overlaps reveal the category only. The other team is
    always told. The patient never sees a conflict and keeps current activities meanwhile.
11. A departing team never stops medication or reminders. Unowned items read "Prescribed by
    Dr. X, no longer on your care team. Ask your care team before changing it." Review
    items go to remaining teams and, without patient detail, the clinic's admins. One
    adopter wins. With no team left the patient is told to contact the clinic. Ambiguous
    legacy ownership is never guessed (`unassigned_legacy`).
12. Today reads only active, effective projections, never drafts. Activities combine only
    with the same supported medication identity (or normalized activity) and identical
    dose, frequency, route, instructions and schedule: one reminder, one check-off, a
    completion written per underlying item. Grouping is read-time; items are never merged.
13. Reminders are per combined entry and idempotent under concurrent runs. If grouping is
    unreadable, reminders are deferred or deduped by identity, never sent ungrouped and
    never dropped for a due dose. As-needed, event-based and unrecognized frequencies
    cannot create routine schedules; the backend enforces cadence counts and explicitly
    named clinical weekdays (patient-chosen times never change them). Today and dispatch
    ignore a stored schedule that no longer matches the current frequency; an unscheduled
    item is available, not due now. A profile timezone change leaves existing per-item
    timezones alone.
14. `taken` and `completed` both count as responses; a future dose stays upcoming until its
    absolute time; empty allergies read "Not documented". The Today preview is read-only,
    unavailable while edits are unsaved or any blocker stands, and not an exact feed;
    Today never shows a previous-locale feed (only the latest request may replace it).
15. Attaching an activity, sending or replying never changes a plan, reminders or
    completions. The server rechecks ownership and current source; stale or foreign
    sources fail neutrally with stable codes.
16. Lock order: authorization reads, patient fence, idempotency record, plan, version,
    items, projections. Use the database clock; log ids, never clinical text.
17. Deterministic medication-error chat floors are in [safety](safety.md).
18. A patient upload marked "Not sure" waits in every care team's queue until one claims the
    whole document (one winner, audited); approve or reject needs the claim. Drafting follows
    the claiming team's plan, and an unrouted document starts no draft. A legacy upload with
    no determinable team becomes "Not sure", never guessed.

## Why it was built this way

- One plan per care-team link: each provider approves their own instructions, where a
  shared plan gave every specialty one approver. Facts stay shared, since a hidden
  medication is how interactions are missed.
- Conflicts block publication. Rejected: warn only, or edit the other team's plan.
- Activities stay when a team ends: stopping an anticoagulant for admin reasons is unsafe.

## Excluded on purpose

Interaction or equivalence engine; editing another team's plan; re-routing orphaned
documents; booking, push, email or SMS from plans; autonomous medication changes; generic
wellness advice in plans; required real-provider evaluation campaigns.

## Where it lives

Backend `backend/src/app/`: `routers/care_plans.py`, `services/care_plan_service.py`,
`care_plan_conflicts.py`, `care_plan_lineage.py`, `feed_service.py`, `activity_grouping.py`,
`cron_service.py`; migrations `040`-`048`, `076`, `083`-`087`, `092`. Clinician
`apps/clinician-portal/src/`: `components/features/care-plan-panel.tsx`,
`cross-plan-conflicts.tsx`, `services/care-team-plans.ts`. Patient: `app/(app)/today`,
`hooks/use-feed-data.ts`. Types: `packages/shared/src/types/care-team-plans.ts`.

## How to check it

Follow [QA handoff 3.3](../qa-handoff-2026-10.md#33-care-team-plans) with a two-team patient,
then confirm a one-team patient's screens are unchanged. From `backend`: `PYTHONPATH=src
.venv/bin/pytest tests/unit/services/test_care_plan_conflicts.py
tests/unit/services/test_feed_combined_entries.py --no-cov`. Postgres contracts need
`CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER=1` (CI shard `care-team-plans`). Portals: `npx vitest
run care-team-today` (patient), `care-plan-cross-plan` (clinician). Evidence:
[final acceptance](../evidence/pat-005-final-acceptance-2026-10-10.md).

## API contract

Under `/api/v1`; errors are `{"error": {"code", "message", "details"?}}`; types are in
`packages/shared/src/types/care-team-plans.ts`. A plan is addressed by `care_plan_id`; the
`{plan_id}` segment of version routes is the VERSION id. Clinician paths are under
`/care-plans/clinician`.

- `GET /patients/{pid}/plans`: own plans carry `active_version_id`, `draft_version_id`;
  another team's is `{owner, approved_at, is_mine:false}`; unowned lists
  `adoptable_by_care_team_ids`. `GET /patients/{pid}/care-team-options` lists my links.
- `GET /patients/{pid}`, `/review-context`, `/generation`, `POST /retry-generation` take
  optional `care_team_id`, `care_plan_id`; two plans, neither named: 422
  `CARE_TEAM_REQUIRED` (`details.options[]`).
- `GET /patients/{pid}/{vid}/cross-plan-review` -> conflicts (`ours`, `theirs`,
  `other_plan`, `acknowledged`, `asked_other_team`) and `interaction_coverage`.
  `POST .../{vid}/conflicts/{fingerprint}/resolution` `{resolution: keep_both |
  ask_other_team, reason 1-2000}`; a changed fingerprint is 409 `CONFLICT_CHANGED`.
- `POST /patients/{pid}/{vid}/approve` `{note, idempotency_key?, excluded_item_ids?}` ->
  `PublishCarePlanResult` with `warnings`. Nothing publishes on 409 `CROSS_PLAN_CONFLICT`
  (`details.conflicts`), `IDEMPOTENCY_KEY_REUSED` or `CONFLICT`.
- `GET /review-items?status=open` -> `{items, clinic_items}` (clinic items non-PHI);
  `POST /review-items/{id}/reply` informs only; `.../resolve` `{action: accept |
  keep_both, reason?}` closes a `conflict_reply` (idempotent, audited).
- `GET /patients/{pid}/plans/{cpid}/activities`; `POST /plans/{cpid}/adopt` `{care_team_id,
  note}` (409 `PLAN_ALREADY_ADOPTED`); `POST /plans/{cpid}/retire-items`; `POST
  /records/{adr_assessment|medwatch_draft}/{id}/take` (409 `RECORD_ALREADY_TAKEN`).
- `GET /care-team/clinician/patients/{pid}/shared-summary` (`some_conditions_private`);
  `GET /documents/claimable?patient_id=`; `POST /documents/{id}/claim` (409
  `DOCUMENT_ALREADY_CLAIMED`); approve or reject of an unrouted document is 422
  `DOCUMENT_CLAIM_REQUIRED`. Uploads, SOAP, ADR review and MedWatch take `care_team_id`.
- Patient: `GET /documents/care-team-options`; `POST /documents/` takes `care_team_id` or
  `not_sure: true`. `GET /feed/today?care_team_id=<uuid|"unowned">` adds `plan_owner`,
  `plan_owners`, `combined_item_ids`, `care_team_filters`, `contact_clinic`. `GET
  /care-plans/patients/{pid}` merges approved plans. `PUT /care-team/patient/conditions/
  {id}/sensitivity` `{is_sensitive}`.

## Still open

Decided but to revisit before real use: a same-clinic colleague may edit and export another
team's visit, and a confirmed-symptom hand-off reaches every assigned clinician.
