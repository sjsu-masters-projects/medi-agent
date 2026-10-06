# AI runtime decision record — September 2026

**Status:** Implemented routing; deployed acceptance evidence is still being collected.

## Decision

MediAgent uses two explicit Vertex AI transports behind one workload registry. The choice is
per workload, not a clinical authority decision: deterministic safety, authorization, approval,
and provenance rules run independently of a model response.

| Workload | Primary | Fallback | Deterministic outcome |
| --- | --- | --- | --- |
| Triage | Gemini 3.5 Flash-Lite / LOW | Gemini 3.8 Flash / LOW | Emergency floor, then localized unavailable response |
| Patient reply | Gemini 3.8 Flash / LOW | Gemini 3.5 Flash / LOW | Localized template |
| Document explanation | Gemini 3.8 Flash / MEDIUM | Gemini 3.5 Flash / MEDIUM | Localized template |
| Document extraction | Gemini 3.8 Flash / MEDIUM | None | No candidate facts; mark for evidence review |
| Medication discrepancy (evaluation route) | Gemini 3.8 Flash / MEDIUM | None | Deterministic discrepancy engine only |
| Symptom/ADR intake | Gemini 3.8 Flash / LOW | None; backups not qualified | Do not write a symptom report |
| Care-plan categorization | Gemini 3.8 Flash / LOW | None | Preserve approved plan; draft remains retryable |

The authoritative route definitions, output ceilings, thinking levels, kill switches, and
latency budgets are in `backend/src/app/adk/registry.py`.

## Serving locations

- **Gemini Flash** is called with the Google Gen AI SDK through Vertex's global endpoint:
  `GEMINI_VERTEX_AI_LOCATION=global`.
- **Gemini 3.5 Flash-Lite** uses that same native transport and global endpoint. It has its
  own `GEMINI_TRIAGE_MODEL` setting so classification can move independently of clinical
  extraction and patient-facing prose.
- **GPT OSS MaaS** remains in the evaluation harness through `VERTEX_AI_LOCATION`, but no
  live workload route depends on its OpenAI-compatible endpoint or shared-capacity pool.

Cloud Run owns the production settings. The deployment workflow uses an update operation, so
it preserves separately managed variables and secret references. Local configuration is
documented in `.env.example`; do not commit a real `.env` file.

## Safety and reliability controls

1. The emergency safety floor runs before agent/model execution and renders localized copy.
2. Tool access is deny-by-default and constrained per agent.
3. Every model route has a named deterministic result and a kill switch.
4. Structured Gemini output is validated at the boundary; a result is never trusted merely
   because a schema was requested.
5. Model telemetry records provider/model, outcome, finish reason, latency, retries, and
   fallback path. It deliberately records no patient identifier, prompt, or response text.
6. Model-generated clinical data remains a reviewable candidate. A model cannot approve a
   medication change, diagnosis, or external clinical action.
7. ADK agents construct the registry's complete primary/fallback route. Retriable provider
   failures (including HTTP 429) move to the declared fallback before any response is emitted.
8. Every interactive provider attempt has a registry-owned deadline. Its output is buffered
   until the attempt completes, so a timeout can fall back without splicing two models' partial
   answers together.
9. Legacy MaaS evaluation calls retain a process-local circuit breaker. Interactive routes
   stay on the native Gemini transport; prose falls back to full Flash, not Lite. Intake
   has no qualified model backup and fails without persisting a report.
10. The complete coordinator-and-responder turn has a 30-second ceiling and returns reviewed,
    localized unavailable copy when both routes cannot finish. The triage decision tool ends the
    coordinator stage directly; no second model call narrates a decision whose prose is discarded.
11. A missing coordinator decision returns localized unavailable copy before generated prose
    is exposed. It must not be silently presented as successful routine triage.

## Evidence and limits

The synthetic evaluation harness and fixtures are maintained in
`backend/scripts/run_ai_eval.py` and `backend/tests/fixtures/eval/`. The September comparison
supported the routing trade-offs but was not clinician-adjudicated and is not a release-quality
clinical benchmark. Generated reports are local artifacts and are intentionally ignored by Git.

The direct MaaS request has succeeded in `us-central1` in historical evaluation. The current
native chat adapter enforces per-attempt limits and the runtime enforces a whole-turn ceiling.
Post-deployment synthetic acceptance remains separate from the local checks below.

## Superseded material

This record replaces the September spike, market surveys, provider-cost research, and
evaluation narrative documents. Their dated measurements remain available in Git history;
they must not be treated as current pricing, availability, or model-selection guidance.

## Medical capability pilot — 2026-10-03

**Decision: retain current routing pending task-specific adjudication.** Medical knowledge,
record fidelity, patient-language quality, authority boundaries, and endpoint availability
are separate acceptance dimensions. A medical model name or a valid JSON response is not
evidence that all five dimensions pass.

### Medical-model research

| Candidate | Why evaluate it | Constraint for this project |
| --- | --- | --- |
| MedGemma 1 27B text | Medical text comprehension and clinical reasoning | Research shortlist only; no endpoint provisioned or live test performed |
| MedGemma 1.5 4B multimodal | Medical document/lab-report and EHR understanding | Research shortlist only; actual PDF/image extraction needs a separate benchmark |
| MeditronFO / Meditron3-70B | Medically adapted models; FO provides an auditable training pipeline | Not live-tested; published benchmark/LLM-judge results do not establish our bilingual chat performance |
| Med42-v2 70B | Clinical question answering and record summarization | Older text-only, 8K-context candidate; not live-tested |
| BioMistral 7B | Biomedical continued pretraining on PubMed material | Research baseline, not a preferred patient-chat replacement |

Google specifically describes MedGemma 27B as a candidate for medical text reasoning and
MedGemma 1.5 4B as improving document/EHR understanding. Its model card says it has not been
optimized or evaluated for multi-turn use. Google's supported use path requires hosting;
there is no configured pay-per-request endpoint in this project. This pilot did not deploy
compute or change cloud configuration. See the [MedGemma overview](https://developers.google.com/health-ai-developer-foundations/medgemma),
[model card](https://developers.google.com/health-ai-developer-foundations/medgemma/model-card),
and [hosting FAQ](https://developers.google.com/health-ai-developer-foundations/faqs).

The [MeditronFO preprint](https://arxiv.org/abs/2605.16215) reports medical benchmark gains
and judge-based preferences, not a MediAgent clinical validation. The
[Med42-v2 card](https://huggingface.co/m42-health/Llama3-Med42-70B) documents its clinical
adaptation, 8K context, and remaining validation limitations. The
[BioMistral card](https://huggingface.co/BioMistral/BioMistral-7B/blob/main/README.md)
explicitly restricts its recommendation to research pending alignment and testing.

GPT-OSS-120B is general-purpose, but does have published medical capability evidence:
its [model card](https://cdn.openai.com/pdf/419b6906-9da6-406c-a19d-1bb078ac7637/oai_gpt-oss_model_card.pdf)
reports HealthBench scores of 53.0 at low reasoning and 57.6 at high. These are benchmark
scores, not percentages of clinically correct answers; they cannot be compared directly
with MedQA scores or used to rank it against current Gemini models. Our latency-oriented
low-effort test is not a measurement of its maximum reasoning capability.

### Live free-text comparison

The global-endpoint pilot compares `gemini-3.8-flash`, `gemini-3.5-flash`,
`gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.1-pro-preview`,
`openai/gpt-oss-120b-maas`, and `openai/gpt-oss-20b-maas`. Version selection follows
Google's [model lifecycle page](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions);
this is not a test of every image/audio/specialized variant or superseded Flash patch.

Inputs comprise 16 existing synthetic fixtures across document extraction, medication
discrepancy, ADR intake, triage, and explanation, plus six harder bilingual cases:
SGLT2-associated ketoacidosis with glucose 155 mg/dL, methotrexate daily-versus-weekly
instructions, and levothyroxine mg/mcg equivalence. Reference expectations are grounded in
the [FDA SGLT2 warning](https://www.fda.gov/media/94822/download),
[methotrexate information](https://medlineplus.gov/druginfo/meds/a682019.html), and
[levothyroxine information](https://medlineplus.gov/druginfo/meds/a682461.html).

All models receive the same workload-specific prose prompt and synthetic inputs, without
JSON schema, retrieval, tools, retries, or fallback. Temperature is 0.2; output ceiling is
4,096 tokens; Gemini thinking and OSS reasoning are low; request timeout is 90 seconds.
At most two distinct models run concurrently, with one call per model and a 0.6-second
pause after each response. Latency excludes semaphore queue wait. Raw final answers, not
private reasoning, are inspected manually. This tests baseline model behavior, not the
production agent's exact prompts, safety floor, or delivery deadline.

All 154 planned calls finished; all 140 returned final answers were read. Availability is
measured separately from medical quality:

| Model | Answers / 22 attempts | Rate-limited | 90-second timeouts | Median completed call |
| --- | --- | --- | --- | --- |
| Gemini 3.8 Flash | 22 | 0 | 0 | 3.643 s |
| Gemini 3.5 Flash | 22 | 0 | 0 | 5.593 s |
| Gemini 3.5 Flash-Lite | 22 | 0 | 0 | 1.840 s |
| Gemini 3.1 Flash-Lite | 21 | 1 | 0 | 2.397 s |
| Gemini 3.1 Pro preview | 22 | 0 | 0 | 8.197 s |
| GPT-OSS-120B MaaS | 9 | 2 | 11 | 2.714 s |
| GPT-OSS-20B MaaS | 22 | 0 | 0 | 1.427 s |

The OSS median excludes its 13 failed calls and must not be read as healthy interactive
performance. These sampled failures do not establish whether a timeout is caused by
capacity, inference duration, or transport behavior. Pro had 13 completed calls over eight
seconds. A successful 90-second-budget pilot response is not proof that a production
interactive deadline will be met. No retry-recovery or fallback-rate conclusion follows
from this deliberately retry-free, fallback-free run.

Representative findings from the raw answers:

- All five Gemini variants recognized the SGLT2 emergency despite modest glucose and
  correctly converted 0.075 mg to 75 mcg in both languages. Medical knowledge is present.
- Gemini 3.5 Flash-Lite incorrectly explained type-2 diabetes in Spanish as inadequate
  sugar production/processing rather than insulin production/action (`exp-002`).
- GPT-OSS-20B called levothyroxine an antithyroid drug in Spanish despite correctly
  converting its dose. Its English methotrexate answer missed the explicit severe/fatal
  toxicity and urgency; its Spanish answer entertained another daily maintenance regimen.
- Several responses inferred undocumented oral routes, changed symptom timing, or added
  patient-note details. GPT-OSS-20B added a date and once-daily frequency in `adr-004`.
- Some otherwise knowledgeable Gemini responses told patients to hold atorvastatin;
  this exceeds our requested supervised role. Gemini 3.8 also returned an English intake
  note for the Spanish ADR case.
- Gemini 3.1 Pro explicitly identified the aspirin listed-versus-stop contradiction
  (`doc-008`), which several faster models missed. It is a candidate for complex review,
  not an automatically selected chat replacement.
- GPT-OSS-120B escalated Spanish stroke symptoms but supplied 112 for Mexico instead of
  its national 911 number ([official reference](https://www.gob.mx/911/articulos/que-es-el-911emergencias?idiom=es)).
  Its Spanish methotrexate answer identified toxicity but introduced unsupported
  formulation/loading-dose questions and did not clearly convey urgent reconciliation.

Synthetic raw outputs, prompt hashes, configuration metadata, curated review findings,
availability/latency summary, and SHA-256 checksums are local ignored artifacts under
`backend/reports/medical-knowledge-20261003/`. Failed calls receive no medical-quality score.
The temporary API scripts are preserved there for inspection; they require the local
backend environment and normal ADC authentication, and are not a release-grade harness.

**Next acceptance path:** expand EVA-001's bilingual corpus, obtain clinician/pharmacist
adjudication, test actual PDF/OCR and multi-turn chat, and rerun candidate models through
the production prompts and deadlines. Add pinned authoritative retrieval for explanations
where it improves grounding, but verify citations and urgency independently; retrieval
does not repair source ambiguity or guarantee safe triage. No routing change, clinical
readiness claim, or medical-model deployment follows from this small single-run pilot.

## October 4–5 workload tuning — local implementation and synthetic evidence

The routing table above now specifies thinking per task, not one setting for every model.
The native service and ingestion-job deployment definitions pin the same Gemini model IDs
and global endpoint; this workflow has **not** been deployed as part of this task. No database
or external configuration was changed. No dedicated medical-model hosting is required.
Model support and thinking choices were checked against Google's
[model-version guide](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions)
and [thinking guide](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/thinking).

- Triage: 3.5 Flash-Lite, LOW, 1024 output tokens; 3.8 Flash backup. The extra room is
  for context tools plus the decision, not free-form diagnostic reasoning.
- Replies: 3.8 Flash, LOW, 2048; distinct full 3.5 Flash backup, never Lite prose.
- Explanations: 3.8 Flash, MEDIUM, 4096; full 3.5 Flash backup at the same setting.
- Document extraction: 3.8 Flash, MEDIUM, 8192, no model backup.
- Symptom intake: 3.8 Flash, LOW, 4096, 15-second deadline, **no qualified backup**.
  MEDIUM was slower without establishing better source fidelity. The candidate 3.5 Flash
  backup changed a symptom timeline; Pro LOW timed out in 5/10 cases and one returned
  assessment introduced a diagnostic inference. A failed intake writes no report and
  tells the patient so in their language. Primary output is still only a candidate.
- Care-plan categorization: 3.8 Flash, LOW, 8192; supplied fact IDs only, no new instruction.
- Discrepancy MEDIUM remains an evaluation route. Pro preview's legacy task slots now
  explicitly request MEDIUM unless overridden, but have no active workflow callers.
  Those slots are not evidence of implemented SOAP/MedWatch production behavior.

`backend/scripts/check_gemini_workloads.py` provides repeatable global, sequential,
single-attempt fixture checks and real in-memory ADK chat checks. Reports are synthetic,
local, ignored artifacts under `backend/reports/gemini-*-20261004.json`. Only final answers
are retained, not private reasoning. Raw answers were read alongside scores. These checks
are not clinician-adjudicated, PDF/OCR acceptance, database persistence tests, or production
capacity measurements.

| Check | Observation | Limit |
| --- | --- | --- |
| LOW triage JSON proxy | 28/28 intent and urgency matches; median 0.87 s | Not the tool-calling path |
| Final actual ADK chat | 8/8 expected urgency, no degraded answers; median 3.74 s | Synthetic context reads, no database writes; small single-run sample |
| MEDIUM explanation | Primary 8/8 and backup 8/8 returned; medians 7.77/7.42 s | Spanish direct generation is a proxy for the production translation path |
| Revised production intake, Flash LOW | 9/10 returned; one deadline expiry | Source fidelity and clinical review remain required |
| Candidate intake backup, Pro LOW | 5/10 returned, five deadline expiries | Rejected for interactive fallback |
| Native fixture calls across configurations | 144 attempts, 131 returned, 13 deadline expiries; no explicit HTTP 429 observed | Returned does not mean medically correct; this does not prove 429 is eliminated |

Actual chat exposed two problems that the JSON proxy missed: a missing typed decision and
routine classification for an insulin dose-change request. Missing decisions now fail
closed before prose is exposed; dose changes/extra doses are at least urgent. Prompts also
forbid medication experiments and imaginary care-team notifications. The final English/
Spanish answers were reviewed for urgency, those failures, and source-versus-general context.
Regression tests inject 429 → explanation backup and intake failure → localized no-report.

**Remaining qualification gaps:** extraction omitted expected lab conditions in one fixture,
included historically administered contrast as a medication candidate, retained OCR spelling,
and produced a composite rather than verbatim citation for a conflicting aspirin instruction.
These are not silently scored as successful medical understanding. Keep existing provenance,
citation validation and clinician approval gates; do not claim the complete medical pipeline
qualified. Pro MEDIUM performed well on four selected complex cases, but that tiny sample
does not justify automatic promotion; HIGH also caused a discrepancy deadline expiry.

Acceptance commands (from `backend`, unless noted): full pytest without coverage, Ruff check,
Ruff format check, and mypy on `src`; root `git diff --check`. Exact final outcomes are recorded
in EVA-001 in the task tracker. Opt-in PostgreSQL tests remain skipped. Post-deployment
synthetic acceptance, larger bilingual clinical adjudication, and production availability/
fallback telemetry remain follow-up work.
