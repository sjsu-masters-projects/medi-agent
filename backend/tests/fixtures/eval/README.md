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
  pharmacist adjudication before it counts toward a research claim.
- `inputs`: what the provider sees. `expected`: the gold label the scorer checks.
- `adjudication`: `pending` until a clinician or pharmacist signs off. Record the
  reviewer role and date; do not adjudicate your own scenario.
- `rationale`: why the label is what it is, in one or two sentences.

## Coverage (version `2026-09-spike-v1`)

| Workload | en-US | es-MX | High risk | Notes |
| --- | --- | --- | --- | --- |
| Triage | 18 | 18 | 22 | 4 emergency pairs plus denial, context, and safety controls |
| Document extraction | 6 | 4 | 7 | incomplete record, OCR noise, contradiction, multi-page evidence |
| Medication discrepancy | 10 | 4 | 8 | all five discrepancy types, brand/generic control, abstain case |
| ADR extraction | 6 | 4 | 3 | red-flag cases, a non-ADR case that must not be attributed to a drug |
| Patient explanation | 4 | 4 | 4 | safety wording and language parity |

Seventy-eight scenarios in the current default suite. Growing this to 120 scenarios with 40 professionally
adjudicated high-risk cases is an optional research expansion, not an expo gate
(`EVA-001` in the tracker).

## Running

```bash
cd backend
PYTHONPATH=src .venv/bin/python scripts/run_ai_eval.py --dry-run
PYTHONPATH=src .venv/bin/python scripts/run_ai_eval.py --models flash --workload triage_classification
```

Reports are written to `backend/reports/ai_eval_<timestamp>.{json,md}` with the run's
environment metadata. Prompts are never written to the report; model outputs on these
synthetic scenarios are, because reviewers need them.

For native Gemini checks using the registry's actual thinking, output ceiling and deadline:

```bash
PYTHONPATH=src .venv/bin/python scripts/check_gemini_workloads.py --dry-run
PYTHONPATH=src .venv/bin/python scripts/check_gemini_workloads.py --production-contract --workload adr_extraction
PYTHONPATH=src .venv/bin/python scripts/check_gemini_workloads.py --production-contract --fallback --workload patient_explanation --out reports/explanation-fallback.json
PYTHONPATH=src .venv/bin/python scripts/check_gemini_workloads.py --chat --workload triage_classification --case tri-017 --case tri-018 --out reports/chat-check.json
```

Native fixture checks use `global`, one SDK attempt, sequential calls with 0.6-second
pacing, and no automatic fallback. `--fallback` tests the backup independently.
`--thinking LOW|MEDIUM|HIGH` and `--model` allow explicit comparisons, not promotions.
By default the existing evaluation addenda/schema are used; `--production-contract`
uses production prompts and the live symptom schema with its boundary validators.
The discrepancy prompt is an evaluation contract; the Spanish explanation is a direct
generation proxy for production's English-then-translation flow. Triage JSON is also a
proxy, not the tool-calling coordinator. Use `--chat` for real chat models, tools and safety
plugins with in-memory sessions, stubbed synthetic patient-context reads and database
telemetry disabled. That mode uses registry settings and refuses ignored model overrides.
Reports retain final synthetic answers, never private reasoning. A valid schema or a
passing keyword score is not medical adjudication; read the raw answers.

## Bounded expo suite (`2026-10-demo-v1`)

`run_ai_eval.py --suite demo --dry-run` selects 34 cases, 17 per locale:
18 triage, 10 explanation/responder, 2 document-extraction and 4 symptom/ADR cases.
Seven existing paired controls are reused (`tri-p01`, `tri-p02`, `tri-p05`,
`exp-p01`, `doc-p01`, `adr-p01`, `adr-p02`); `demo/` adds six triage pairs
and four responder pairs. The existing 78-case default suite remains separate.

Added cases cover mild/stable symptoms, low mood, deterioration, suspected
medication reactions, unsafe doses, taking held medication, wellness education,
unavailable reference data, absent document results, and unapproved instructions.
All content is invented for offline testing, not seed data or upload material.
No database, account, credential, provider call or clinical approval is required.

The triage JSON check is a classifier proxy; `care_responder` cases use the
production responder instruction with supplied synthetic notes, not real tool
retrieval or a complete chat turn. Existing explanation controls retain their
original document-summary contract. Keyword checks cannot establish factual
accuracy or clinical safety; inspect raw final answers as well as scores.
Provider-outage replay and runtime outage tests are separate from the responder's
unavailable-reference cases.

Document and symptom/ADR cases reuse existing framework fixtures and structured
scorers, not prose-only triage checks. Every report summary includes strict
`demo_*` criteria for coverage, complete answers, expected checks and safety;
extraction additionally checks grounding and unsupported fields. Failed calls
remain infrastructure outcomes with no invented answer or medical verdict. See
the operator guide for the exact criteria and outage demonstrations.

Fixture SHA-256 (update deliberately if content changes):

| File under `demo/` | SHA-256 |
| --- | --- |
| `patient_explanation.json` | `6307b7bcbe05e654762515a2e5e5e73323c2b1d9212793aa6e74155f9ec033c1` |
| `triage_classification.json` | `f9161dd578a2f19174afb84d12b7c2a7da4c66dce1894949fd6e53965ad2b8d0` |

Offline replay format, exact commands and evidence limits:
[demo AI evaluation](../../../../docs/demo-ai-evaluation.md).
