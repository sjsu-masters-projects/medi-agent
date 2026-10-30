# v2: paired-locale review record

Status: **approved and active**, subject to the limits in [Approval](#approval).

- Resource: [v2.json](v2.json)
- Canonical bundle SHA-256: `c0f83dba4e7c82f8e17be98090395e5fbb6069b779d3b4dd5a39235b8122907a`
- Version: `v2`; same twelve IDs, supported locales and question budget as v1.
- Changes respond to the October 13 PR review and the October 17 requester continuation.

Two questions changed from [v1](v1-review.md):

| Question | English | Mexican Spanish |
| --- | --- | --- |
| Severity | How intense is it from 1 to 10, where 1 is mild and 10 is the worst you can imagine? You can say I don’t know or skip. | ¿Qué intensidad tiene del 1 al 10, donde 1 es leve y 10 es lo peor que te puedas imaginar? Puedes decir no sé o prefiero no responder. |
| Concomitant products | What medicines or products have you taken around this symptom, including prescriptions from other clinicians, over-the-counter medicines and supplements? Include recent starts or changes, what you took for this symptom, and any names, doses, timing or reasons you know. | ¿Qué medicamentos o productos has usado cuando apareció este síntoma, incluidas recetas de otros profesionales, medicamentos sin receta y suplementos? Incluye inicios o cambios recientes, lo que tomaste para este síntoma y los nombres, dosis, momentos o motivos que sepas. |

The concomitant-products question now applies to **every symptom**, including when
the patient reports no product concern. The other ten questions retain v1
wording. Unknown/declined remain valid. No new symptom-specific branch, emergency
mapping, diagnosis or medication instruction is introduced. Confirmed reports
label product answers as patient-reported and unverified; matching record context
cannot supply an answer or add a medicine to the approved list.

## Approval

On October 30, 2026 Rajeev Chaurasia, the project owner, decided to make this wording live
and retire the numbered-candidate process. Both languages were checked against each other
in a model-assisted bilingual review on the requester's authority: meaning against the
English, a tú register, clarity and safety tone. No wording changed as a result.

There was no independent clinical review, reviewer signature or formal PR approval of this
wording. It covers a synthetic demonstration package, not professional clinical validation.
Changed wording requires a new release; see the [release process](README.md).
