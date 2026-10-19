# candidate-2 — review required before activation

Status: **pending review**. No approval or signature is asserted. The active
`candidate-1` package and its October 12 approval record remain unchanged.

- Resource: [candidate-2.json](candidate-2.json)
- Canonical Pydantic bundle SHA-256: `cb35ff1dcd75d42cc147744ce5f056d6b676ba00d19a069769f1db6244c4939f`
- Version: `candidate-2`; same twelve IDs, supported locales and question budget.
- Changes respond to the October 13 PR review and October 17 requester continuation.

Review these two changes in both languages:

| Question | English | Mexican Spanish |
| --- | --- | --- |
| Severity | How intense is it from 1 to 10, where 1 is mild and 10 is the worst you can imagine? You can say I don’t know or skip. | ¿Qué intensidad tiene del 1 al 10, donde 1 es leve y 10 es lo peor que te puedas imaginar? Puedes decir no sé o prefiero no responder. |
| Concomitant products | What medicines or products have you taken around this symptom, including prescriptions from other clinicians, over-the-counter medicines and supplements? Include recent starts or changes, what you took for this symptom, and any names, doses, timing or reasons you know. | ¿Qué medicamentos o productos has usado cuando apareció este síntoma, incluidas recetas de otros profesionales, medicamentos sin receta y suplementos? Incluye inicios o cambios recientes, lo que tomaste para este síntoma y los nombres, dosis, momentos o motivos que sepas. |

The concomitant-products question now applies to **every symptom**, including when
the patient reports no product concern. The other ten questions retain candidate-1
wording. Unknown/declined remain valid. No new symptom-specific branch, emergency
mapping, diagnosis or medication instruction is introduced. Confirmed reports
label product answers as patient-reported and unverified; matching record context
cannot supply an answer or add a medicine to the approved list.

The designated safety/backend reviewer should record approved, rejected or changes
requested, the actual identity/role/date, and a reference tied to this exact hash.
A requester-reported decision may be recorded transparently; do not assert an
independent signature, itemized findings or PR approval without that evidence.
Changed wording requires a new hash and review. This review covers the synthetic
demonstration package, not professional clinical validation.

After actual approval, pin the immutable reference and metadata in `manifest.json`
and publish exactly matching eligibility through an explicitly authorized rollout.
Pending content must never be selected by a live intake or substituted for an
existing pinned draft.
