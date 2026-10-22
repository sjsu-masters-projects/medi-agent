# PLAN-002 — Care plans per care team

**Status:** In progress on `codex/care-team-plans` from main `f235c278` (October 21).
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

## Implementation sequence

**Isolated starter checkpoint:** requester reassigned G/H to a separate contributor
before schema work. This branch contains an initial conflict-policy module (30
unit tests pass) and an unfinished care-team-options scaffold. No schema migration,
full scope/API tests, publication integration, UI, deployment or PR is delivered.
Do not merge this starter as completed G/H. The records/continuity and reliability
work proceeds on a separate branch from merged #209.

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
