# Synthetic AI evaluation scenarios

Gold-labeled, synthetic scenarios for comparing AI providers per workload (`EVA-001`,
September 2026 routing spike). Everything here is invented for testing. No real
patient, clinician, clinic, or document appears in these files, and none may be added.

## Layout

One JSON file per workload. Each file is an `EvalScenarioSet`
(`app.models.ai_evaluation`): a `version`, the `workload`, and a list of scenarios.

| File | Workload | What a provider must produce | Headline score |
| --- | --- | --- | --- |
| `triage_classification.json` | Patient-message triage | `{intent, urgency, reason}` via the production classifier prompt | urgency and intent match; **no under-triage of urgent or emergency cases** |
| `document_extraction.json` | Clinical document parsing | The ingestion prompt's JSON, plus verbatim `evidence` quotes and `confidence` | required-field accuracy; hallucinated medications; unsupported fields left empty; evidence quotes found in the source |
| `medication_discrepancy.json` | Multi-source medication comparison | `{discrepancies[], abstain, abstain_reason}` | precision and recall by discrepancy type; abstention on ambiguous cases; **no missed allergy conflict** |
| `adr_extraction.json` | Symptom and ADR intake | The symptom agent's JSON plus `red_flag` | field checks; **no missed red flag**; no invented suspect medication |
| `patient_explanation.json` | Plain-language record explanation | Free text in the patient's language | language match; required content present; **no prescribing or diagnostic wording** |

Document scenarios may reuse the existing golden fixtures one directory up through
`inputs.document_file` and `expected.expected_file`; the loader inlines both.

## Scenario fields

- `scenario_id`: `<workload prefix>-<nnn>`, unique within the file.
- `locale`: `en-US` or `es-MX`. High-risk cases are authored in both and linked by
  `pair_id` so English and Spanish safety behaviour can be compared directly.
- `risk`: `low`, `medium`, or `high`. Every `high` scenario needs clinician or
  pharmacist adjudication before it counts toward a release decision.
- `inputs`: what the provider sees. `expected`: the gold label the scorer checks.
- `adjudication`: `pending` until a clinician or pharmacist signs off. Record the
  reviewer role and date; do not adjudicate your own scenario.
- `rationale`: why the label is what it is, in one or two sentences.

## Coverage (version `2026-09-spike-v1`)

| Workload | en-US | es-MX | High risk | Notes |
| --- | --- | --- | --- | --- |
| Triage | 14 | 14 | 16 | 4 emergency pairs, 2 of which no deterministic keyword covers |
| Document extraction | 6 | 4 | 7 | incomplete record, OCR noise, contradiction, multi-page evidence |
| Medication discrepancy | 10 | 4 | 8 | all five discrepancy types, brand/generic control, abstain case |
| ADR extraction | 6 | 4 | 3 | red-flag cases, a non-ADR case that must not be attributed to a drug |
| Patient explanation | 4 | 4 | 4 | safety wording and language parity |

Seventy scenarios in total. `EVA-001` requires at least 120 scenarios and at least 40
adjudicated high-risk cases; the tracker records the remaining authoring and review work.

## Running

```bash
cd backend
PYTHONPATH=src .venv/bin/python scripts/run_ai_eval.py --dry-run
PYTHONPATH=src .venv/bin/python scripts/run_ai_eval.py --models flash --workload triage_classification
```

Reports are written to `backend/reports/ai_eval_<timestamp>.{json,md}` with the run's
environment metadata. Prompts are never written to the report; model outputs on these
synthetic scenarios are, because reviewers need them.
