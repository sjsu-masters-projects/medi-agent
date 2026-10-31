# UX-007 — English / Mexican Spanish wording review

October 30, 2026, PR #232. Uses the requester-accepted project meaning-and-safety review method recorded in [the wording record](spanish-interface-wording-2026-10-22.md). This is model-assisted review of static interface wording, not professional translation, native-speaker sign-off, independent peer approval or clinical validation.

## Paired inventory review

Compared the changed declaration rows with accepted main. Only `symptom-intake-copy.ts` changed among the 14 inventoried sources; the other 13 retain their accepted hashes. Reviewed all 37 changed/new rows (34 distinct English/Spanish pairs), including placeholders, uncertainty, actor, timezone fallback and medical field distinctions. Clinical values, doses, dates and source text are not translated or approved by this review.

Three corrections: timezone text now reads naturally before a named zone; Report flag uses Indicador del informe; Severity uses Gravedad for recorded clinical/allergy context. Every other pair preserves meaning and the application’s tú register.

| Source key | English | Accepted es-MX | Decision |
| --- | --- | --- | --- |
| `copy.timezone` | Times use | Los horarios se muestran en | Corrected |
| `copy.fallback` | Your saved time zone is unavailable. Times are shown in UTC. | Tu zona horaria guardada no está disponible. Los horarios se muestran en UTC. | Accepted |
| `copy.recordDetail` | Record detail | Dato del expediente | Accepted |
| `copy.factFieldLabels.name` | Name | Nombre | Accepted |
| `copy.factFieldLabels.test_name` | Test | Prueba | Accepted |
| `copy.factFieldLabels.amount` | Amount | Cantidad | Accepted |
| `copy.factFieldLabels.value` | Result | Resultado | Accepted |
| `copy.factFieldLabels.unit` | Unit | Unidad | Accepted |
| `copy.factFieldLabels.reference_range` | Report range | Rango del informe | Accepted |
| `copy.factFieldLabels.flag` | Report flag | Indicador del informe | Corrected |
| `copy.factFieldLabels.observed_at` | Date measured | Fecha de medición | Accepted |
| `copy.factFieldLabels.dose` | Dose | Dosis | Accepted |
| `copy.factFieldLabels.dosage` | Dose | Dosis | Accepted |
| `copy.factFieldLabels.frequency` | How often | Frecuencia | Accepted |
| `copy.factFieldLabels.route` | How taken | Vía de administración | Accepted |
| `copy.factFieldLabels.instructions` | Instructions | Indicaciones | Accepted |
| `copy.factFieldLabels.description` | Description | Descripción | Accepted |
| `copy.factFieldLabels.status` | Status | Estado | Accepted |
| `copy.factFieldLabels.start_date` | Start date | Fecha de inicio | Accepted |
| `copy.factFieldLabels.end_date` | End date | Fecha de término | Accepted |
| `copy.factFieldLabels.allergen` | Allergen | Alérgeno | Accepted |
| `copy.factFieldLabels.reaction` | Reaction | Reacción | Accepted |
| `copy.factFieldLabels.severity` | Severity | Gravedad | Corrected |
| `copy.factFieldLabels.notes` | Notes | Notas | Accepted |
| `copy.factFieldLabels.systolic` | Systolic pressure | Presión sistólica | Accepted |
| `copy.factFieldLabels.diastolic` | Diastolic pressure | Presión diastólica | Accepted |
| `copy.factLabels.medication` | Medicine | Medicamento | Accepted |
| `copy.factLabels.dose` | Dose | Dosis | Accepted |
| `copy.factLabels.allergy` | Allergy | Alergia | Accepted |
| `copy.factLabels.condition` | Condition | Condición | Accepted |
| `copy.factLabels.lab_result` | Test result | Resultado de prueba | Accepted |
| `copy.factLabels.vital_sign` | Measurement | Medición | Accepted |
| `copy.factLabels.immunization` | Vaccine | Vacuna | Accepted |
| `copy.factLabels.procedure` | Procedure | Procedimiento | Accepted |
| `copy.factLabels.appointment` | Appointment | Cita | Accepted |
| `copy.factLabels.instruction` | Instruction | Indicación | Accepted |
| `copy.factLabels.obligation` | Instruction | Indicación | Accepted |

## Explicit review outside the current inventory

These UX-007 pairs are outside the inventory; the renewed paired receipt does not claim to cover arbitrary strings outside its source list. This table records the additional review.

| Source / context | English | Accepted es-MX / decision |
| --- | --- | --- |
| records-copy / original filename | Original file | Archivo original — identifies the retained original, not a translated replacement. |
| records-copy / no saved details | There are no saved details from this document to explain. You can still open the original document above or ask your care team about it. | No hay datos guardados de este documento para explicar. Puedes abrir el original o consultar a tu equipo de atención. — does not claim the original file is empty. |
| records page / duplicate explanation | This file is already in your records. We kept this copy without adding new medical details or care-plan instructions. You can open the original or ask your care team about it. | Este mismo archivo ya está en tus documentos. Guardamos esta copia sin agregar nuevos datos médicos ni indicaciones al plan de atención. Puedes abrir el original o consultar a tu equipo de atención. — preserves source/care-plan boundaries and does not infer uploader identity. |
| care conversations / own message | You | Tú — only when the message belongs to the signed-in patient. |
| record request / known added date | (added {date}) | (agregado el {date}) — identical date value, omitted when the saved zone or date is unavailable; title and original filename stay source-bound. |
| Records count / dynamic branches | {count} record(s), optionally {processing} processing | {count} documento/documentos, optionally {processing} en proceso — reviewed singular/plural and zero-processing omission; no false count while loading. |

## Source fingerprints outside the inventory

| Source | SHA-256 |
| --- | --- |
| `apps/patient-portal/src/components/features/records-copy.ts` | `4316f08533c7a49ce84ee0f7f30586c5a9cde51f392578a8203aea39b80c0f7f` |
| `apps/patient-portal/src/app/(app)/records/page.tsx` | `d60cc36a1e89c37e5142907379f9498b115694e64c5817b7f7b8af824137e55a` |
| `apps/patient-portal/src/components/features/care-conversations.tsx` | `8fbb8d0b2bad87bced0ecc785151f73ba340ddf6b2b3c924dd7a01c92eecf628` |
| `apps/patient-portal/src/components/features/record-request-composer.tsx` | `c1dbc864104256234ba109f0f120ef54c0e5e8de436d9b4aa38c7c0b6e721215` |

## Acceptance boundary

Accepted for the synthetic project’s static interface wording after these corrections. The machine-checkable receipt is refreshed only after this comparison. Visual wrapping, screen-reader behavior, generated clinical content and deployed functional acceptance remain unverified. The existing LOC-003 translation/model disclosures and clinical approval path are unchanged.
