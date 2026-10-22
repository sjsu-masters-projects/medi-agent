# Demo AI evaluation operator guide

**Optional research tool, not a completion gate.** Requester decision October 21:
no formal real-provider campaign, model comparison or professional clinical
adjudication is required. Keep this implemented harness for voluntary future use.
Normal synthetic end-to-end feature checks against the configured service and
automated safety/authorization/approval tests still apply; those establish software
behaviour, not clinical validity. No clinician recruitment is needed.

Use this guide to validate synthetic fixtures and review final-answer reports for
AI-006 / EVA-001. The harness does not seed accounts or approve clinical actions.
Use synthetic data only. Dry runs and offline replay require no credentials,
provider calls, database access or remote operations.

## Select and validate the suite

Run from `backend`:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_ai_eval.py --suite demo --dry-run
PYTHONPATH=src .venv/bin/python scripts/run_ai_eval.py --suite demo --locale en-US --dry-run
PYTHONPATH=src .venv/bin/python scripts/run_ai_eval.py --suite demo --locale es-MX --dry-run
shasum -a 256 tests/fixtures/eval/demo/*.json
```

Expected selection is **34 / 17 / 17**. Repeating a dry run is read-only and
selects the same IDs. The full framework remains a separate 78-case selection
(`--dry-run` without `--suite demo`). Pair validation requires exactly one
en-US and one es-MX case per pair; duplicate IDs, missing controls and incomplete
pairs fail before provider initialization. Fixture checksums are maintained in
[the fixture README](../backend/tests/fixtures/eval/README.md#bounded-expo-suite-2026-10-demo-v1).

| Selected task | Cases | What the report checks | Boundary |
| --- | --- | --- | --- |
| Triage | 18 | Exact intent/urgency, under-triage and floor evidence | JSON classification proxy using the production coordinator instruction; no tool execution |
| Document extraction | 2 (`doc-005/006`) | Required fields, invented medication count, absent dose/frequency, verbatim source quotes | Existing framework fixture pair `doc-p01`; text extraction, not PDF/OCR or candidate persistence |
| Symptom/ADR extraction | 4 (`adr-001–004`) | Symptom fields, severity range, suspect medication, evidence-derived ADR flag, red flags | Existing framework fixture pairs `adr-p01/02`; structured candidate output, not confirmed intake or a clinician ADR decision |
| Explanation/responder | 10 | Language, required content, forbidden clinical/approval claims | Existing approved-record pair plus supplied-note responder proxies for wellness, unavailable reference, absent result and review boundaries |

Triage cases include mild/stable symptoms and low mood, deterioration, medication
reactions, unsafe doses, taking held medication, and cardiac/crisis controls.
No scoring rule lowers production urgency. The deterministic safety floor and
actual localized runtime outage behavior are covered by separate runtime tests.

## Replay final responses offline

```bash
PYTHONPATH=src .venv/bin/python scripts/run_ai_eval.py --suite demo \
  --responses /absolute/path/to/synthetic-final-responses.json --out reports/demo-replay
```

Input is a JSON array with one row per selected scenario/provider/model. Examples
of the two allowed outcome shapes (these two rows alone are not a complete run):

```json
[
  {"scenario_id":"tri-001","provider":"recorded-example","model":"example-model","ok":true,"text":"{\"intent\":\"symptom\",\"urgency\":\"emergency\"}","latency_ms":100},
  {"scenario_id":"tri-002","provider":"recorded-example","model":"example-model","ok":false,"text":null,"error_code":"unavailable","latency_ms":100}
]
```

Supply all selected IDs with identical provider/model coverage per case. Unknown
or missing cases, duplicate trials, inconsistent answer/error states and extra
fields are rejected. Store only raw final responses and safe outcome metadata;
never include private reasoning, credentials, patient data or real identifiers.
Validation failures print only the error type. Input files are not uploaded.

The report JSON preserves raw final text verbatim in `scores[].output_text`.
Markdown displays those answers beside structured scores for review. Reports
identify `recorded_offline` versus `provider_run`; a dry run creates no answer
report. Stub responses in tests demonstrate reporting, not provider performance.
An exit code of zero means at least one answer was scored, not that acceptance
passed. Review the report criteria and raw answers.

## Interpret acceptance and unavailable results

Each provider/workload row publishes named `demo_*` checks under
`summaries[].thresholds`, also rendered in Markdown:

| Criterion | Required result |
| --- | --- |
| `demo_all_four_tasks_selected` | All four tasks above occur in the selection |
| `demo_paired_locales` | Every selected pair has both locales; a single-locale diagnostic intentionally fails this full-suite criterion |
| `demo_all_selected_answered` | Every selected case has one schema-valid final answer for that provider/model |
| `demo_exact_expected_checks` | Every case matches its expected checks, including symptom fields and unavailable-reference wording |
| `demo_no_safety_failure` | No scored safety check fails |
| `demo_document_grounding` (extraction only) | All checked source quotes verify, no invented medications, and unsupported fields stay empty |
| `demo_failed_calls_without_clinical_verdict` | Failed calls carry neither an invented answer nor a clinical safety verdict |

For a successful full demo response run, require all applicable criteria true,
then read every raw answer for source fidelity, language and approval boundaries.
Keyword/schema checks are not clinical validation, and a source quote alone does
not prove that each extracted field is supported. Professional adjudication is an
optional research extension, not an expo gate.

Unavailable behavior has three distinct demonstrations:

- `exp-103/104` exercise a returned answer when medication references are
  unavailable: acknowledge the gap, suggest the care team/pharmacist, invent no
  medical facts. Required/forbidden wording is scored in both locales.
- Offline replay may inject explicit `unavailable`, `timeout` or other normalized
  failures for extraction, symptoms or any selected task. Expect
  `disposition=infra_error`, null answer/safety verdict and summary infra counts;
  completeness and exact-answer checks must fail. The no-clinical-verdict check
  is a report invariant; without failed calls it is not outage evidence.
- Runtime/service tests inject outages and verify localized fallback, no SOAP
  note and no symptom report. Those are application behavior checks, distinct
  from fixture scoring; replay itself performs no persistence or clinical action.

## SOAP operations and ingestion ownership

SOAP uses the registry's single configured Pro route through the shared
background-generation helper. `SOAP_AI_ENABLED` controls availability;
`SOAP_GENERATION_TIMEOUT_SECONDS` defaults to 90 (greater than zero, at most
300). LOW thinking and 4096 output tokens are operational limits, not measured
SOAP performance. Failed, truncated, malformed or empty output produces no note.
There is no model fallback; model attribution follows the configured route.

The legacy ingestion graph and its dedicated test have been removed after a
repository-wide consumer check. Production extraction/summary prompts remain.
Golden tests use `IngestionService._extract_structured` with mocked generation
and the current parser, then `validate_extracted_data` for FHIR conversion.
All four golden documents retain medication/condition/allergy/follow-up coverage.
Their legacy keys are adapted to the current schema and supplied with verbatim
synthetic source chunks. This exercises parsing and FHIR shape, not item-level
grounding, real model extraction or database writes.

## Local verification — October 17, 2026

Final commands and outcomes are recorded below. These are local synthetic checks,
not real-provider or deployed evidence. No credentials or remote operations were
used.

From `backend`:

```bash
PYTHONPATH=src .venv/bin/pytest tests/unit/services/test_soap_note_service.py tests/unit/services/test_demo_evaluation.py tests/unit/adk/test_registry.py tests/unit/adk/test_background_generation.py tests/unit/services/test_ai_evaluation.py tests/unit/services/test_ai_evaluation_fairness.py tests/unit/scripts/test_run_ai_eval_script.py tests/unit/adk/test_chat_runtime.py tests/unit/safety/ tests/unit/adk/test_safety_floor_plugin.py tests/unit/adk/test_care_coordinator.py tests/unit/test_config.py tests/integration/test_golden_set.py tests/unit/agents/test_ingestion_prompt_contract.py tests/unit/services/test_ingestion_candidate_provenance.py tests/unit/services/test_ingestion_translation_scope.py tests/unit/workers/test_document_ingestion_worker.py tests/unit/followup/test_symptom_service.py --no-cov -q
.venv/bin/ruff check src/app/adk/agents/care_coordinator/prompts.py src/app/adk/registry.py src/app/config.py src/app/services/soap_note_service.py src/app/services/ai_evaluation.py src/app/services/demo_evaluation.py scripts/run_ai_eval.py tests/unit/services/test_soap_note_service.py tests/unit/services/test_demo_evaluation.py tests/unit/adk/test_registry.py tests/unit/scripts/test_run_ai_eval_script.py tests/integration/test_golden_set.py
.venv/bin/ruff format --check src/app/adk/agents/care_coordinator/prompts.py src/app/adk/registry.py src/app/config.py src/app/services/soap_note_service.py src/app/services/ai_evaluation.py src/app/services/demo_evaluation.py scripts/run_ai_eval.py tests/unit/services/test_soap_note_service.py tests/unit/services/test_demo_evaluation.py tests/unit/adk/test_registry.py tests/unit/scripts/test_run_ai_eval_script.py tests/integration/test_golden_set.py
.venv/bin/mypy src/app/adk/agents/care_coordinator/prompts.py src/app/adk/registry.py src/app/config.py src/app/services/soap_note_service.py src/app/services/ai_evaluation.py src/app/services/demo_evaluation.py scripts/run_ai_eval.py --ignore-missing-imports
```

Final results: **563 passed, 101 warnings in 1.93 seconds**; Ruff lint passed;
Ruff format check passed for 12 files; mypy passed for all seven checked files,
including the runner. The untyped Google credential-refresh boundary now uses a
narrow `Callable[[Request], None]` cast with a mocked refresh-contract test; no
type suppression or live credential lookup was used for verification. Warnings
are dependency deprecation/experimental-feature notices.

The 35 migrated golden tests pass within that run. The focused suite also covers
production ingestion prompt contracts, candidate provenance, the worker, symptom
no-write failures, SOAP no-note failures, deterministic floors, bilingual outages,
both-locale structured extraction/intake scoring, rejected unverifiable quotes,
complete replay coverage and raw final-response retention. Tests write temporary
stub reports, not live-model reports.

The three demo dry-run commands above each returned exit 0 and selected
**34 / 17 / 17**. Both demo fixture SHA-256 values still match the README.

From the repository root:

```bash
rg -n 'agents[./]ingestion[./]graph|test_ingestion_graph|create_ingestion_graph|IngestionState' backend
git diff --check
```

Consumer search: **no matches (rg exit 1)**. Before deletion, the same import and
symbol searches with only the graph and its dedicated test excluded also had no
matches. Only those two unused files were deleted; ingestion prompts were kept.
`git diff --check`: **passed (exit 0)**. Deleted tracked files remain recoverable
from Git. No commit or remote operation forms part of this verification.
