# PAT-005 synthetic Today-feed scenario

This is the controlled, **en-US**, synthetic-only journey for PAT-005. It is a
test fixture, not clinical guidance, and must not be used with a real patient or
production-like data.

The version-controlled source is
[`synthetic_today_feed_scenario.json`](../backend/tests/fixtures/pat005/synthetic_today_feed_scenario.json).
It deliberately stays separate from the canonical eight-patient portal fixture:
the PAT-005 operator creates one new synthetic patient and assigns one synthetic
clinician for this journey. Do not alter an existing patient to make the scenario
appear to pass.

## Build the upload bundle

Run locally from the repository root:

```bash
PYTHONPATH=backend/src backend/.venv/bin/python \
  backend/scripts/build_pat005_synthetic_scenario.py --out-dir tmp/pat-005-scenario
```

This produces three labelled PDF files in an ignored local directory. The builder
does not access Supabase, create accounts, or upload content.

## Controlled journey

1. Create a new synthetic `en-US` patient named **Morgan Ellis** and assign one
   synthetic clinician with ordinary care-team record access.
2. Upload all three generated documents from the clinician Documents tab within
   the five-minute evidence quiet window:
   - `pat-005-synthetic-medication-order.pdf` as **Prescription**;
   - `pat-005-synthetic-follow-up-instructions.pdf` as **Discharge Summary**;
   - `pat-005-synthetic-medication-reconciliation-conflict.pdf` as **Clinical Note**.
3. Wait for ingestion, then use **Review extracted facts** to inspect candidate
   fields and each protected source preview. Confirm page/excerpt provenance.
4. Confirm that the two Metformin instructions are shown as unresolved/conflicting
   evidence. The complete plan must remain unapprovable until the assigned clinician
   edits, confirms, or removes the conflict.
5. Once the conflict is resolved and the clinician approves the complete plan,
   confirm that only the approved instructions appear in the patient's local-time
   Today feed. Record both a completion and a barrier, then verify the assigned
   clinician can see the adherence result and barrier.

## Expected approved content

After the explicit clinician decision, the intended demonstration contains a
Metformin instruction plus one monitoring, movement, hydration, and follow-up item.
The exact values, source pages, intentional conflict, and expected directions are
in the JSON manifest. Those values remain **draft evidence** until the clinician
approves them; neither the generated files nor the AI worker may publish them.

## Evidence to retain

- The three document IDs and their ingestion state.
- Extracted candidate IDs, confidence, excerpts, page references, and conflict state.
- Plan draft/version ID, clinician decision and audit event.
- Patient feed response after approval, one completion, one barrier, and the
  clinician adherence/barrier view.
- Denial evidence for an unassigned clinician and an unrelated patient.
