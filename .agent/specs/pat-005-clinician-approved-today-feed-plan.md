# PAT-005 — Clinician-Approved Care Plan to Today Feed

## Outcome

PAT-005 closes MediAgent's first controlled-care loop:

```text
synthetic documents → grounded facts → automatic AI draft → clinician review/edit
→ whole-plan approval → deterministic Today feed → completion/barrier → clinician follow-up
```

The model drafts. It never publishes a patient-facing clinical instruction. An assigned
clinician approves the complete plan version. The first complete scenario is `en-US`; `es-MX`
parity is a follow-up task.

## Product contract

- Both patient and clinician uploads use the existing document-ingestion, grounding, provenance,
  and authorization paths.
- A five-minute quiet window groups newly processed documents for one patient into one automatic
  draft request. One patient has at most one open draft at a time.
- Every draft item carries source fact/citation, document/page/excerpt, confidence, uncertainty,
  and any conflict. The generator receives grounded facts only; it cannot invent dose, schedule,
  duration, hydration target, generic advice, or appointment booking.
- Low-confidence, conflicting, or incomplete items block whole-plan approval until the clinician
  confirms, edits, or removes them.
- Approval is atomic: it records the final payload and decision, freezes the plan version,
  supersedes the old version, projects medication changes and non-medication obligations, and
  writes audit events. Failure leaves the prior approved plan active.
- Patient Today reads only active, effective projections. The patient can complete an item or
  report a structured barrier. In-app states only; no push, email, SMS, or appointment booking.

## Delivery sequence

1. **Evidence review and scenario.** Add document-level read-only extracted-facts review with
   authorized source preview. Add the fresh fictional scenario and acceptance fixtures.
2. **Automatic draft lifecycle.** Add versioned plans, items, request queue, retries, worker,
   and a clinician API for status/current draft. New evidence revises a draft or creates `N+1`;
   it never edits an approved version.
3. **Clinician decision surface.** Add the Care Plan tab, evidence-visible item cards, edits,
   blockers, patient preview, and a transactional approve-and-publish operation. Replace the
   upload-page direct-obligation control with draft-based authoring.
4. **Patient and follow-up loop.** Enrich Today tasks with approved-plan provenance, extend
   adherence with barriers, and show missed/barrier results to the assigned clinician.
5. **End-to-end proof.** Verify upload, draft consolidation, evidence review, blocker handling,
   approval, Today projection, completion/barrier, audit reconstruction, version supersession,
   and assignment isolation.

## Technical boundaries

- Store the immutable plan snapshot in `care_plan_versions` and `care_plan_items`; keep a linked
  `clinical_recommendations` recommendation for the whole-plan approval decision.
- Use a `care_plan_generation_requests` claim queue with bounded retries and a patient-scoped
  uniqueness constraint. The existing scheduled Cloud Run document worker may process this stage
  after document extraction without turning the request path into a worker.
- Retain medications and obligations as runtime projections so existing reminders, Today feed,
  and adherence statistics continue to work. Link each projection to its source plan item.
- New database tables enable RLS, use explicit least-privilege grants/policies, and have
  assignment-based allow and deny tests. Browser clients use authenticated backend routes only.
- Existing adherence history is never rewritten when a plan is superseded.

Migration 045 retains an obligation identity only when one active canonical activity matches
the prior approved item and its exact source fact, category, wording, frequency, and schedule.
Its reminders and adherence logs therefore continue across approval. Changed, newly sourced,
inactive, or ambiguous activities receive new identities; historical item links remain immutable.
This protects future revisions, not a retroactive rewrite of already-published V2 history.
Apply `045_care_plan_activity_continuity.sql` through `scripts/apply-supabase-migrations.sh`
before repeating revision acceptance. Local opt-in PostgreSQL tests exercise unchanged identity,
changed wording/schedule/source, inactive or externally edited canonical records, rollback, and
browser-role denial without remote credentials. Live clinician-barrier and revision acceptance
must still be repeated after deployment.

Draft review may save an unresolved medication matching decision as a visible publication
blocker; saving exclusions must not require finishing reconciliation first. Publication still
validates matching against current canonical records. A saved conflict resolution survives only
unchanged active clinical content; edits or restoration require renewed confirmation. Clinician
deep-dive responses include the existing patient-reported barrier details, not only aggregate
adherence scores.

Incomplete evidence stays in a cited draft item with empty missing fields and an explicit
review blocker. Confirmation cannot substitute for missing instructions, frequency, or
medication fields; the clinician must supply reviewed wording or remove the item. New
evidence items and the generation completion marker commit in one service-only transaction
that rejects stale claims. Publication independently checks completed generation and complete
active items inside its transaction, and approved item wording is immutable. Migration 043
must precede deployment of this contract; disposable local PostgreSQL tests cover it without
remote credentials or live provider calls.

Oversized source wording must not fail the entire draft batch. Preserve the full fact and
citations; abbreviate only the review heading and require a clinician replacement or removal
before publication. Confirmation alone cannot resolve an abbreviated heading. Oversized
instructions or frequency stay empty and blocked until reviewed wording is supplied; never
silently truncate clinical instructions. This uses migration 043's existing draft contract.

## Revision review after an approved plan

Automatic generation uses only medication/activity facts supported by unwithdrawn uploaded
documents or clinician entries. SMART/FHIR and external-record candidates remain in their
reconciliation workspace; import alone does not mean a historical therapy belongs in today's
care plan. Already-persisted imported proposals are retained and labeled, with an explicit
clinician action to exclude them from the draft (not delete source records). Approved
carried-forward items are not included in that bulk exclusion.

Exact structured-source matches, identical instructions with potentially different cadence,
and same-name medication proposals are overlap review groups, not automatic equivalence or
translation decisions. The reviewer compares sources and keeps/removes proposals explicitly;
all item rows, source facts and citations survive. Removed items can be expanded and restored.
The API and migration 044 publication trigger reject unresolved overlaps atomically, including
identical-source items whose carried-forward display wording was translated. Different
event/schedule contexts are not automatically combined. Future carried-forward medications
link their prior approved projection as an update, never reuse the original create decision.
No missing route is inferred; unsupported route wording requires clinician review.

Patient reminder preferences are administrative, not a new clinical regimen. The reminder
screen shows compact saved-day/time/timezone summaries and opens one editor at a time.
New times are blank; weekly days are patient-selected rather than silently assigned.
Existing per-item timezones remain unchanged when the profile timezone changes.
Save failures retain the patient's unsaved choices for retry.
As-needed, activity-based and unrecognized frequencies cannot create routine schedules.
Today and notification dispatch also reject older schedules that no longer match the current
frequency; these records remain available for review/removal, not silently deleted.
Unscheduled pending items are available, not labeled due now. Known cadence counts and
eight-hour intervals are enforced by the backend, independently of UI validation.

Rollout: apply `044_care_plan_overlap_publication_guard.sql` with the existing migration
runner before deploying. Reload the existing draft, explicitly exclude imported proposals,
review overlap groups, save, then verify publication/Today and historical adherence. Do not
retry completed generation to clean up an existing draft. Full PAT-005 live proof remains open.

When new documents register grounded facts, the approved version remains active while a newer
draft is prepared. The assigned clinician needs both snapshots in one review: the current
approved version, the proposed version, each item's linked source documents/pages, and a clear
distinction between carried-forward wording, edits, removals, and newly sourced facts. A new
fact is **not** automatically a new therapy or a reconciled medication change. The review UI
must not call an item list an exact Today preview while timezone, reminders, and existing
medications can alter the final feed.

Before live revision approval is considered complete, add explicit matching decisions for each
medication against active canonical records, prevent duplicate projections, verify patient-facing
wording in the patient's preferred locale, and test the v1-approved → new document → v2-draft →
v2-approved path with unchanged adherence history. The current comparison surface is a review
aid, not a substitute for those publication safeguards or clinician judgment.

Publication review records the clinician-verified locale on each active draft item and an
explicit create/update decision on each proposed medication. The API validates those decisions
against current patient and medication state; the atomic database publication operation checks
again before any recommendation, supersession, or projection write. Verification is human
attestation against the source, not automatic translation or a claim of clinical correctness.
An absent match decision or a same-name active medication blocks creation. The exact Today
preview and live supersession proof remain separate acceptance gates.

The saved-draft Today preview is a read-only, assigned-clinician snapshot using the same
renderer as the patient feed. It includes canonical legacy activities, proposed medication
create/update decisions, exact unchanged-activity continuity, effective dates, valid stored
reminders and retained responses in the patient-local day. New identities are preview-only;
changed/new activities never inherit previous reminders or completion. Blocked/incomplete
generation, incomplete review, missing evidence and failed reads cannot produce a successful
preview. Unsaved edits invalidate the UI snapshot. Publication remains the separately guarded
database transaction; the preview neither writes nor guarantees unchanged state at approval.

## Acceptance checklist

### Fresh-scenario follow-through safeguards

Medication `taken` and activity `completed` responses both count in clinician
response-based adherence. Future scheduled doses stay upcoming until their absolute
`scheduledAt` timestamp; missing/invalid timestamps never establish that a dose is due.
Explicit daily meal routines support reminders, and explicitly named clinical weekdays
are returned as `required_days_of_week` and enforced by the API and feed cadence guard.
Patient-selected clock times do not alter those clinical days. Unknown, PRN and
event-based frequencies still require clarification rather than inferred routine times.

Simple medication strength/form suffix variants are grouped for explicit overlap
review. This is not clinical-equivalence matching: source names, doses, release markers,
citations and decisions are retained. The API blocks unresolved groups; the existing
atomic database guard still uses exact medication names. No new migration is required.

New explanations use `patient-explanation/2`, source-attributed descriptions and no
treatment-selection language. The Records warning also applies to previously cached
explanations, which are not automatically regenerated. Extraction excludes clinician-only
workflow instructions. These prompt contracts do not establish clinical correctness;
new model output still needs live review. Empty allergy records mean "Not documented",
not a documented absence of allergies. Approved plans do not show draft decision prompts.

The fresh Morgan browser run proved patient and clinician uploads, source review,
guarded approval, Today projection, medication completion and a clinician-visible access
barrier. Post-deployment verification of these follow-through fixes, five-document live
worker timing, v2 continuity and the complete denial/bilingual matrix remain open.

The October 5 follow-up found that the risk-summary header still counted only
`completed`, even though the detailed view also counted medication `taken`. The
follow-up fix aligns these 30-day recorded-response ratios; neither is a measure
of all expected doses. Risk thresholds are unchanged. Live unassigned-clinician
navigation was denied; router regressions also exercise edit/approval/ownership
guards. Mock database tests are not a substitute for deployed RLS checks.
Read-only audit reconstruction verified generation request, editing/approval actor,
publication linkage and subsequent responses for V1. Intermediate edit wording
snapshots are not retained. V2 continuity, the full live barrier matrix and the
initial unconfirmed-save cause remain acceptance work, not completed items.

- [ ] A fresh synthetic `en-US` scenario produces evidence-backed candidates from clinician and
      patient uploads.
- [ ] Several completed documents inside the quiet window create one draft.
- [ ] The clinician can inspect a candidate and plan item beside its protected source preview.
- [ ] A blocker prevents approval until it is resolved.
- [ ] Approval atomically creates or updates medications and publishes non-medication items.
- [ ] Only approved effective items appear in the correct patient-local Today feed.
- [ ] Completion and each barrier category become clinician-visible.
- [ ] Unassigned users cannot read, draft, approve, preview, or report against the plan.
- [ ] Plan version, citations, approval, projections, and adherence outcome are reconstructable
      from audit records.
- [ ] A clinician can compare active and proposed versions, identify all contributing documents,
      reconcile overlapping medications, and verify localized wording before v2 publication.

## Explicitly deferred

- Spanish parity, appointment booking, external notifications, production capacity alerts,
  generic wellness advice, autonomous medication changes, and production-readiness claims.
