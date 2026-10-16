# PLAN-002 — Care plans per care team

**Status:** Backlog; direction and conflict handling decided October 13. Part of CLN-003
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
| Interactions | through MED-001's checker, with its severity |

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
   - **Must be resolved or acknowledged with a reason:** stop versus continue, an exact
     duplicate ingredient, and a major interaction.
   - **Warning only, with acknowledgement optional:** minor interactions and schedule
     overlaps.
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
