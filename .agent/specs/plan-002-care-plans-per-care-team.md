# PLAN-002 — Care plans per care team

**Status:** Backlog; direction decided by the requester on October 13. Part of CLN-003
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
    care team's review queue until one claims it.
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

The polypharmacy core of the product:

- **Cross-plan checks when a draft is reviewed and published.**
  - Duplicate therapy: two plans with the same ingredient.
  - Conflicting instructions for the same medication.
  - A plan that stops a medication another plan keeps active.
  - Overlapping schedules for the same medication.
  - Interactions with the other plans' medications, through MED-001's checker.
- **These block publication** until the reviewing clinician resolves or acknowledges them.
  The other plan's care team is notified and gets a review item. The other plan is never
  edited.
- **Visibility of other plans.** Clinicians on other care teams see that a plan exists and
  its medication items, through the shared list. They do not see its other items, sources
  or notes, as CLN-003 recommends.

## Migration from one plan per patient

- Existing plans move to the care team of their approving clinician, or the patient's only
  care team when there is one.
- Version history, item identities, reminders, completions and barriers are kept.
- Any draft that cannot be assigned unambiguously goes to a review item. It is never
  guessed.

## Decisions needed

1. Is a plan keyed by care-team link (recommended) or by specialty? Two providers in one
   specialty at the same clinic would then share a plan.
2. Do cross-plan conflicts block publication until acknowledged (recommended), or only
   warn?
3. How does a patient upload with "Not sure" get claimed: the first care team to claim it,
   or a split per item?
4. When a care team ends (the patient leaves that provider), are its approved activities
   retired from Today immediately, or kept until another clinician reviews them?
