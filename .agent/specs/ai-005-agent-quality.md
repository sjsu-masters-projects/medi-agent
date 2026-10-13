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

## Scope, in order

1. **Results and document context in extraction.** Add `lab_results` (test, value, unit,
   reference range, flag, collected date, specimen) and `vital_signs`, plus document
   metadata (type, date, author, facility). Ground each value against page text like other
   facts. They are review-only candidates: they never become care-plan items or Today tasks.
   Store the extraction prompt version. Show them in the clinician facts dialog and make
   them available to Nora's record tools.
2. **Explanations from the document, not only facts.** Give the explainer the document type,
   grounded text sections and all fact types. For results: plain-language names, which
   values are outside the range, and "your care team will discuss these" — no diagnosis or
   treatment advice. Every number in an explanation must appear in the source (automatic
   check; fail closed to a shorter safe explanation). Lab-only documents get an explanation.
3. **Evaluate what production runs.** Point the triage eval at the production coordinator
   prompt and tool contract; add lab-related and Spanish cases. Run extraction and
   explanation evals with production settings. Fix the golden lab fixture and doc-009.
4. **OCR end to end.** Fixtures rendered from synthetic documents as scanned PDF, phone photo
   (skew, glare) and Spanish print; assert recovered text and extracted values. Pass page OCR
   quality to the model and the reviewer; confirm Tesseract eng+spa in the deployed image.
5. **Consistency.** One Spanish register; SOAP generation through the model registry.

## Acceptance

- The October 12 lab report yields grounded result candidates for every row, flags matching
  the document, and an explanation that names the out-of-range results in English and
  Spanish without advice.
- Scanned and photographed versions of the same report recover the same values within the
  documented OCR tolerance, or are routed to clinician-only review with a reason.
- Updated evals pass in CI with production settings; no regression on existing cases.
- No change to the care-plan eligibility rule (medications and obligations only) and no
  automatic publication. Synthetic data only.
