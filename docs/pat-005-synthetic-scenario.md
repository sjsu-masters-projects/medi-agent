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

## Chat and weekday regression checks

The patient assistant is **Nora**, explicitly labeled "AI care assistant" in en-US
and "Asistente de cuidado con IA" in es-MX. Its conversation and the read-only
care-team message view are separate. The latter does not imply a two-way clinical
messaging channel: replies still require direct contact with the clinic. Voice
capture/processing/playback must finish before switching to that view.

Clinician inbox escalation notices remain stored for clinician review. Their
reserved subject/body signature is excluded from patient delivery and again
filtered by the client during staggered rollout. Patient UUIDs remain structured
metadata, not text in new operational alert bodies. Existing stored alerts and
historical assistant conversations are not rewritten or deleted. The current
delivery query remains bounded to the latest 20 inbox rows; alerts within that
window can reduce the number of available clinician-authored messages.

After deployment, verify the following using only this synthetic patient:

1. Ask whether a patient-reported barrier automatically confirms an adverse drug
   reaction, first in English and then in Spanish, while explicitly reporting no
   symptoms. The educational question alone must not force urgent classification.
   Genuine symptom reports, mixed questions/reports, emergency signals and a
   model's higher urgency must retain their existing escalation behavior.
2. Confirm automated escalation notices, internal IDs and internal routing text
   never appear in either patient view. A genuine clinician-authored message must
   appear only under care-team messages, including when its subject says urgent.
3. Check an approved Monday/Wednesday/Friday walking instruction on Thursday and
   Friday in the patient's timezone. It must be absent Thursday and present Friday,
   even without reminders or with an incompatible reminder. Changing reminder
   preferences must not change the approved clinical weekday eligibility.
4. Confirm bilingual Nora labels/typing, care-team empty states, and switching back
   to the AI composer without losing the conversation. Do not relabel an automated
   notice as a human reply or invent a clinician response to make this test pass.

Local regressions support these checks but do not establish deployed acceptance,
clinical validation, or complete PAT-005 readiness.
