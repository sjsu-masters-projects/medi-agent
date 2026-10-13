# AI-005 — Agent quality: documents, explanations, triage and OCR

## Why

On October 12 a synthetic one-page follow-up lab report for Morgan Ellis (HbA1c 7.8%,
fasting glucose 146, lipids, eGFR 98, urine albumin/creatinine, B12) went through the
production upload → review → care-plan path. Every step worked, but the AI steps
understood almost nothing of the document:

- Extraction returned one fact (the diagnosis). The extraction prompt asks only for
  medications, conditions, allergies and obligations, so all 20 results were dropped.
- The patient explanation said the record listed no follow-up steps and suggested asking
  about tests. It is generated from extracted facts only, never from the document text.
- Nora answers about documents from those facts and the explanation, so it could not
  say what the A1c was either.

Evidence: [deployed recheck](../../docs/deployed-recheck-2026-10-11.md#clinician-flow-for-an-uploaded-lab-report-october-12).

## Current behaviour (origin/main, October 12)

| Step | Where | Inputs | Gap |
| --- | --- | --- | --- |
| Extraction | `agents/ingestion/prompts.py:9-49`, schema `models/document_extraction.py:75-83`, Flash, temperature 0.1 | Text of usable pages (embedded text or OCR) | Four categories only; no lab results, vitals, procedures, immunizations, document date, author or facility; no prompt version stored |
| Grounding | `services/document_intelligence/grounding.py` | Model output + page text | Unknown categories silently dropped |
| Patient explanation | `agents/ingestion/prompts.py:52-82`, `services/document_summary_service.py` (`patient-explanation/4`) | Persisted facts (medication, condition, obligation) | No document text or type; allergies dropped; lab-only documents get no explanation; no faithfulness check |
| Chat triage | `adk/agents/care_coordinator/prompts.py:16` (+ deterministic floor `safety/triage_floor.py`) | Message, history, record tools | The triage eval scores a separate proxy prompt (`services/triage_prompts.py`), not this one |
| OCR | `services/document_intelligence/pipeline.py`, Tesseract eng+spa | Scanned pages and images | Never evaluated end to end; OCR confidence is not given to the model |
| Evals | `services/ai_evaluation.py`, `tests/fixtures/eval/*` | Synthetic cases | Lab case doc-009 expects empty lists; golden lab fixture uses an outdated schema; extraction eval runs at temperature 0.3 vs 0.1 in production |
| Spanish | care-plan translation (`usted`) vs explanation and Nora (`tú`) | | Inconsistent register |

## Documents and workflows covered

| Document | What the agents must get right |
| --- | --- |
| Lab report | Every printed result with value, unit, range and flag on its own row; calculated values; critical flags; no interpretation |
| Discharge / after-visit summary | Medication actions (continue, new, changed, stop, hold); diagnoses; allergies or "no known allergies"; vitals; procedures; vaccines; follow-up visits; patient instructions |
| Prescription, medication list, pharmacy label | Name, dose, frequency, route and directions as printed; one item per line, never merged |
| Imaging, pathology, ECG and other studies | Procedure, date and the printed impression verbatim |
| Referral, clinic note | Problems, instructions, follow-up appointments |
| Immunization record, home logs | Each vaccine dose; each reading |
| Spanish documents | Same as above in Spanish ("Suspender", "Alto", "Sin alergias conocidas") |
| Scanned or photographed copies | Same values through OCR, or clinician-only review with a reason |

| Workflow | Rule |
| --- | --- |
| Clinician review | Every candidate is grounded on the page; results and vitals anchor on their own printed row and need an exact value; a flag that contradicts its range is low confidence |
| Care-plan drafting | Only medications and patient obligations; a stopped or held medication is never publishable and blocks matching active items until a clinician decides; a changed medication needs the new dose confirmed; results-only documents do not open a draft |
| Patient explanation | Built from grounded facts of every type; out-of-range and critical results named with their ranges, no advice; stopped medications described as stopped; every number must exist in the facts, and every number must survive translation, or nothing is shown |
| Assistant (Nora) | Sees results with their flag and range and medication actions; never interprets a result or reminds a patient to take a stopped medication |

## Delivered in the first slice

Branch `feature/document-results-extraction`:

- Model input keeps printed table rows (`PageExtraction.layout_text`), for embedded text
  and OCR alike.
- Extraction prompt `document-extraction/2` (version stored in each fact's provenance):
  document type, medication `status`, lab results, vital signs, immunizations, procedures,
  appointments, "no known allergies"; output validated item by item, so one malformed item
  no longer discards the document; output ceiling 8192 tokens.
- Grounding: row-scoped anchoring, exact values, deterministic `flag_meaning`,
  `range_status`, flag/range contradiction check, critical flag note, `medication_action`.
- An "other" upload records its classified document type; a chosen type is never replaced.
- Care-plan safety: stop/hold, changed-dose blockers; drafts only for medication or
  obligation facts.
- Explanation `patient-explanation/5` with the number check and retry; translation keeps
  numbers and uses no gendered clinician titles.
- Nora: result and action fields, 60 facts per document, prompt rules for results and
  stopped medications.
- Clinician facts dialog per type (lab rows, flag and Critical badges, Stop/Hold badges);
  clinician dates in en-US (UX-004).
- Evaluation measures the production settings and scores lab results.

Verified locally against the production model on synthetic documents: the October 12 lab
report (20 of 20 results, flags and ranges correct), a discharge summary with continue,
stop, increase and new medications, NKDA, vitals, an X-ray impression, a flu vaccine and a
follow-up visit, and a Spanish visit summary with "Suspender". A 200-dpi scan of the lab
report reads at OCR confidence 0.93; its one decimal loss ("4.0 - 5.6" read as "40-56") is
caught by the contradiction check.

## Remaining

1. **Critical result alert to clinicians.** Needs a new notification event type, which is
   a migration (`notification_events.event_type` check), so it waits for authorization.
2. **Triage evaluation on the production coordinator prompt** with result and Spanish
   cases; today it scores a proxy prompt.
3. **OCR fixtures:** phone photos (skew, glare), handwriting routed to clinician-only review,
   and OCR quality passed to the model.
4. **Patient Records view** of results (today patients see the explanation only).
5. **Consistency:** one Spanish register across care-plan wording ("usted") and the
   explanation and assistant ("tú"); SOAP generation through the model registry.

## Acceptance

- Results, vitals and medication actions are extracted, grounded and shown to clinicians as
  above; the October 12 lab report yields every result with its printed flag.
- No stopped or held medication can be published as a Today activity.
- Explanations state only numbers present in the facts, in English and Spanish.
- No change to the care-plan eligibility rule and no automatic publication. Synthetic data
  only.
