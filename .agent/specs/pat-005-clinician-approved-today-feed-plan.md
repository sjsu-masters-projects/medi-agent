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

## Revision review after an approved plan

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

## Acceptance checklist

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
