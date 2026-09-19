# Evaluation harness protocol — September 2026

Status: adopted for the expo model comparison. Supersedes the measurement method used in
`ai-model-routing-spike-2026-09.md` §7 and `inference-hosting-options-2026-09.md` §10.

## Why this document exists

The first comparison ranked nine models on one composite score per workload. Investigation on
2026-09-16 and 2026-09-17 found that the score mixed three unrelated things — whether Google
answered the call, whether the reply was packaged as valid JSON, and whether the clinical content
was right — and that several of the differences it reported were caused by the harness rather
than by the models. The numbers in that table cannot be used to pick a model.

This protocol is what the harness must do so the next comparison measures the models.

## 1. Every call ends in exactly one disposition

The scorer records one of five outcomes, and each metric states which of them it counts.

| Disposition | Meaning | Counts toward accuracy? |
| --- | --- | --- |
| `answered` | The provider returned a complete reply | Yes |
| `infra_error` | 429, 5xx, timeout, DNS, auth — the call never produced a reply | **No.** Reported as its own rate |
| `truncated` | `finish_reason` says the token budget ran out | **No.** Reported as its own rate |
| `unparseable` | A complete reply that is not valid JSON for the schema | Yes, scored zero |
| `refused` | The provider's safety layer declined | Yes, scored zero, reported separately |

The rule behind the split: a model's failure to follow the contract is the model's failure and
scores zero, but our failure to obtain a reply is ours and must not be charged to the model.
A rate limit on our shared project quota says nothing about clinical ability. Truncation is a
budget we chose, not a property of the model.

Two headline numbers are always published together, never merged: **answered rate** and
**accuracy on answered**. A provider that fails half its calls must not look good by
disappearing from the denominator, and a provider we throttled must not look incompetent.

Read `finish_reason` *before* attempting to parse. Never infer truncation from a parse failure.

## 2. Request parity

- **Sequential, not concurrent.** The previous run fired eight models at one project quota with
  `asyncio.gather`, so the models competed with each other for the capacity we were measuring.
  One provider at a time, with a fixed pause between calls.
- **Identical retry policy for every provider**, recorded per call. Retries for `infra_error`
  only; never retry a parse failure, because that measures retry policy rather than the model.
  Report retried calls separately and check they do not score differently from first-attempt calls.
- **Token budget set per provider, not shared.** Vertex counts thinking tokens against
  `max_output_tokens`, so an identical cap is a tighter answer budget for a reasoning model than
  for a plain one. Size each budget so the visible answer is never cut, and record the setting.
- **Reasoning effort is explicit and recorded.** Gemini 3.x cannot disable thinking; use the
  lowest documented level. MedGemma's thinking is off unless the system instruction asks for it,
  so leave it off. gpt-oss always reasons; budget for it.
- **Warm the endpoint first and discard the warm-up.** A self-deployed endpoint answers the
  first call after idling with a 429. Scoring that as a model failure is a harness bug.
- **Chain-of-thought is stripped at ingest and never persisted**, in reports, fixtures or logs.

## 3. Schema parity

Three serving stacks enforce three different JSON Schema subsets, and each silently ignores
what it does not support — so "we sent the same schema" does not mean "the same constraint was
applied". The harness therefore uses one portable dialect that all three accept:

- every property a plain scalar type, no `null` unions, no `anyOf`, `oneOf`, `$ref` or `$defs`;
- every property listed in `required`, with absence expressed as a sentinel (`""`, or an explicit
  `"unknown"` enum member) rather than `null`;
- string enums only, shallow nesting, `additionalProperties: false`.

Two further rules, both of which the previous run broke:

- **Reasoning-first field order.** Schema key order is generation order on every one of these
  stacks. A schema that puts the answer before the reasoning field deletes the chain of thought,
  and the published literature attributes its largest reported "structured output hurts quality"
  effect to exactly this. Assessment and evidence fields come before verdict fields.
- **The schema and the prompt must agree.** The old run told the model in the prompt that every
  item MUST carry an evidence quote while handing it a schema that marked evidence optional.
  Constrained decoding follows the schema. Do not restate the schema in the prompt either;
  Google documents that duplication lowers output quality.

Structured-output mode is declared per provider and recorded per call. Where a provider supports
both, run both arms, because constrained and prompt-only decoding trade different errors, and
report format compliance separately from content accuracy.

## 4. Scoring rules

- **Drug names match strictly.** The old matcher accepted any shared three-character token, so
  `insulin glargine` matched `insulin aspart` and `levothyroxine 50 mcg` matched `500 mcg`.
  Matching requires equality after normalisation, or the same RxNorm ingredient. Report a
  relaxed score alongside it if useful, never instead of it.
- **Precision and recall are micro-averaged** over true and false positive counts, not averaged
  across scenarios holding one to three items each.
- **Evidence is required and scored.** Every extracted item must carry a quote that appears in
  the cited page, which is what the ingestion service enforces in production.
- **Fixtures carry `[Page N]` markers**, because production prepends them to every page before
  the model sees the text. Asking for a page number the input does not contain produced
  degenerate digit runs in four models.
- **Quote checking normalises whitespace, case and unicode punctuation** before comparison, so a
  formatting artefact is not scored as a fabricated quote.
- **Safety classes are reported per class with their own interval** — red flag, allergy conflict,
  emergency triage — never folded into a mean where a rare critical class disappears.
  Under-triage and over-triage are reported separately and never netted against each other.
- **Language is detected with a real language identifier**, not a stopword heuristic that reads
  a Spanish medication list as English.

## 5. Prompts are part of what we measure

The same prompt goes to every provider, which is the convention the major harnesses follow, and
it means we are measuring each model through one generic interface rather than its best possible
prompt. State that limit rather than implying it is the model's ceiling. Our prompts were written
against Gemini in production, which is a home-field advantage for Gemini and must be disclosed.

Two controls run alongside the main comparison:

- **No-document control** for extraction: ask with the document removed. Anything the model still
  "extracts" is coming from its training data, not the record.
- **Example-value perturbation**: the symptom prompt's example contains `"severity": 1`, and three
  models answered 1 almost every time, including for symptoms whose expected range is 7 to 10.
  Flip the example values; if scores move, the prompt is what is being measured.

## 6. Statistics

Implemented in `backend/src/app/services/eval_statistics.py`.

- **Proportions use a Wilson interval**, which stays inside 0 to 1 and does not collapse to zero
  width at a perfect score. At 8 scenarios, 8 of 8 correct means the true accuracy could be 68%.
- **Partial-credit means use a percentile bootstrap.**
- **Model-vs-model claims use a paired comparison on identical scenarios**, not a difference of
  aggregate scores. At this sample size a difference needs at least **six one-sided
  disagreements** to be significant, and the report states that threshold so "no significant
  difference" is not misread as "no difference".
- **Each scenario runs at least three times.** Temperature-zero output is not reproducible on
  shared serving infrastructure, and run-to-run noise is the largest reducible error at this n.
- **No pass/fail stamp on a point estimate.** A threshold verdict needs the interval.

What may be claimed at 8 to 28 scenarios: gross failure, presence or absence of a capability,
and error taxonomies. What may not: a ranking between models whose intervals overlap, or any
improvement of a few points. Where intervals overlap, the honest sentence is that the evaluation
could not detect a difference at this sample size.

## 7. Report layout

Per workload and model, in this order:

```
Reliability   answered | infra_error | truncated | unparseable | refused
Format        schema-valid first attempt | after repair | repairs applied
Content       accuracy on answered [95% interval]      <- headline
Safety        per-class recall with intervals; under-triage and over-triage separately
Grounding     evidence present | evidence verbatim in the cited page
Efficiency    median latency (min-max) | answer tokens | reasoning tokens | cost
Variance      trials, spread across runs
```

Self-hosted cost is GPU hours and wall-clock, never a $0.00 entry in a column of metered prices.

## 8. References

Collected in the 2026-09-17 sweep. The vendor behaviour claims were checked against Google's
documentation service; the statistical claims were reproduced in code and are covered by unit
tests. The papers below were identified by that sweep and are cited for the claims attributed to
them here, but have not been read end to end by this team — verify before quoting in the report.

- Tam et al., *Let Me Speak Freely?*, EMNLP 2024 Industry Track — format restriction and reasoning.
  https://aclanthology.org/2024.emnlp-industry.91/
- dottxt, *Say What You Mean* — the rebuttal, on prompt asymmetry and parser choice.
  https://blog.dottxt.ai/say-what-you-mean.html
- *JSONSchemaBench*, https://arxiv.org/abs/2501.10868 — constrained decoding did not reduce quality.
- Bowyer et al., *Don't Use the CLT in LLM Evals With Fewer Than a Few Hundred Datapoints*,
  ICML 2025. https://arxiv.org/abs/2503.01747
- Miller, *Adding Error Bars to Evals*. https://arxiv.org/abs/2411.00640
- Inspect AI scoring policy — the clearest statement of which failures leave the denominator.
  https://inspect.aisi.org.uk/scoring-policy.html
- Hugging Face, *Open LLM Leaderboard: DROP deep dive* — parsing bugs misread as model failure.
  https://huggingface.co/blog/open-llm-leaderboard-drop
- Sclar et al., *FormatSpread*, ICLR 2024 — formatting alone moves accuracy.
  https://arxiv.org/abs/2310.11324
- Vertex structured output and thinking behaviour:
  https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/control-generated-output
  and https://ai.google.dev/gemini-api/docs/generate-content/thinking

## 9. The document workload measures structuring, not reading

How documents are read was already settled by the OCR spike
(`docs/document-intelligence-assessment.md`, 2026-09-10): deterministic reading first —
pypdfium2 for embedded text, PaddleOCR PP-OCRv5 through RapidOCR for scans and photos —
the model only structures the text it is handed, and a deterministic anchoring step ties
every value back to a page, box and quote. On its 23-case corpus PaddleOCR found 97.8% of
required fields and Nemotron-Parse 100%, both with 100% page-citation accuracy, against
35.9% for embedded text alone, which is what production does today.

So the routing evaluation's document workload answers a narrow question: given
page-marked text that OCR has already produced, how well does a model turn it into
structured candidates? It is not a reading test and must never be used to choose an OCR
engine. Three consequences:

- Fixtures carry `[Page N]` markers because that is what the OCR layer emits.
- The model's page citation is scored as instruction-following only. Whether a value is
  genuinely on the page is decided by deterministic anchoring, which the OCR benchmark
  measures — never by the model's own claim.
- A model that does badly here costs structuring quality, not evidence integrity. An
  unanchored value is flagged and shown to the clinician, never silently accepted.

This is also why the earlier "no model passed 64% on documents" result does not mean what
it appeared to. It measured a model doing a job the product does not ask of it, through a
schema that forbade the evidence the prompt demanded.

## 10. What is built, and what is not yet

Implemented and covered by tests as of 2026-09-17:

- the five-way disposition with `finish_reason` and reasoning-token capture, and HTTP 400
  recorded as a rejected request rather than an outage;
- sequential provider execution, with the run's parameters recorded in the report;
- the portable schema dialect, evidence required, reasoning fields generated first;
- strict drug matching with bilingual, brand and OCR-digit handling;
- negation-aware safety wording, per-workload abstention, no safety verdict on a call
  that never answered, micro-averaged precision and recall, `[Page N]` markers;
- accuracy on answered calls with a bootstrap interval, published beside the answered
  rate and the disposition counts; thresholds judged on the interval's lower end;
- Wilson intervals, bootstrap and paired McNemar in `eval_statistics.py`.

Not yet built, and therefore not claimable in the next report:

- repeat trials with run-to-run variance (§6 asks for at least three);
- per-class safety recall with its own interval, and separate under- and over-triage rates;
- a uniform, logged response-repair step reported as its own metric;
- the no-document and example-perturbation controls in §5;
- a real language identifier in place of the stopword heuristic;
- both structured-output arms run per provider (§3) — the harness supports one mode per
  run, so two runs are needed.

## 11. Two things measured against Vertex on 2026-09-17

**gpt-oss does not reliably obey a schema it accepts; Gemini does.** Measured over five
trials per variant at temperature 0, against an instruction deliberately asking for a
shape the schema forbids:

| Model | Schema violated |
| --- | --- |
| `openai/gpt-oss-120b-maas`, no `minLength` | 2 of 5 |
| `openai/gpt-oss-120b-maas`, with `minLength` | 1 of 5 |
| `google/gemini-3.8-flash`, either way | 0 of 10 |

A first one-shot test suggested `minLength: 1` was the trigger. **That was wrong**, and it
had already been written into this document as fact before the repeat test refuted it: the
keyword makes no difference, and the violation happens with it absent. What the numbers
show is a difference between the two serving paths — Vertex enforces the schema for Gemini
and only sometimes for gpt-oss. It is not caused by our schema.

Two caveats on the 3-in-10 figure. The probe prompt deliberately instructs the model to
answer with an array, so it is an upper bound rather than a working rate; and a real
scenario (`adr-001`) produced the same violation without being asked to, so it is not an
artefact of the adversarial prompt either. The honest conformance number will come from
the run itself, which is why format compliance is reported as its own metric.

`minLength`, `maxLength` and `pattern` stay out of the dialect because the published
guidance lists them among the constructs these stacks enforce inconsistently, and the
scorer can check lengths itself. That is a precaution, not a proven fix.

Consequences for the comparison: gpt-oss's schema conformance is a **property of deploying
it**, not evidence about its clinical ability, so it is reported beside accuracy and never
folded into it. And the durable lesson: a schema that is accepted is not necessarily a
schema that is applied; probe enforcement per provider before a run; and a single trial
cannot separate causation from nondeterminism.

**The prompt's example value was worth more than the model.** The symptom prompt showed
`"severity": 1` and never stated the scale, and gpt-oss answered 1 almost every time.
Replacing it with `5` moved every answer to 5. Removing the number entirely and stating
the 1-to-10 scale moved the same four scenarios to 9, 9, 2 and 2 — all inside their
expected ranges — and took gpt-oss from 0.00 and 0.80 to 1.00 on all four. Much of what
the September run reported as weak clinical judgement in the smaller models was our own
example telling them what to say. This is why §5's perturbation control is mandatory
rather than optional.

## 12. First result under this protocol, 2026-09-17

`backend/reports/ai_eval_20260917_172344.json` — gpt-oss-120b and Gemini 3.8 Flash, all 70
scenarios, run sequentially, low reasoning effort, 4x token budget, 2 retries.

**Availability first.** Both answered 65 of 70. Gemini 3.8 Flash lost 5 calls to
infrastructure, all in triage; gpt-oss lost 3, plus 2 replies that were not valid against
the schema. Running them one at a time removed most of the contention seen in September,
but 3.8 Flash still loses calls on shared capacity.

**Accuracy on answered calls**, with 95% intervals:

| Workload | gpt-oss-120b | Gemini 3.8 Flash |
| --- | --- | --- |
| Triage | 100% (100-100), 27/28 answered | 96% (89-100), 23/28 answered |
| Symptom / ADR | 98% (94-100) | 96% (90-100) |
| Medication discrepancy | 81% (60-98), recall 71% | 98% (93-100), recall 94% |
| Patient explanation | 94% (89-98) | 98% (95-100) |
| Document structuring | 85% (61-99) | 89% (69-100) |

**Paired comparison finds no measurable difference on any workload.** Scored item by item
on the same scenarios, the closest call is triage, where gpt-oss wins 7 scenarios and
loses 1 — p = 0.07, short of the six-to-nil-style margin this sample size needs. Every
other workload is 3-to-nil or less.

So the honest conclusion is that **at 8 to 28 scenarios per workload these two models are
not distinguishable on clinical accuracy**, and the September table's confident ranking of
nine models was largely noise plus harness defects. What does separate them is not
accuracy: gpt-oss costs roughly a tenth as much per workload block, answers triage faster
(median 2.2 s against 6.2 s), and violates the output schema occasionally, which Gemini
never did. Those are deployment properties and they are the defensible basis for a choice.

Still outstanding before any decision: MedGemma's leg, repeat trials for run-to-run
variance, and the controls in §5.

## 13. MedGemma fails our contract in both directions — probe, 2026-09-17

The nullable-free dialect fixed the 400 that blocked native structured output in
September: the vLLM container now accepts the schema. Accepting it is not the same as
using it well. One warm-up call each, same prompt, same schema:

**Constrained (native schema).** Perfectly shaped, entirely empty:
`{"symptom":", ","onset":", ",...,"severity":0,...}` — every string field the literal
`", "`, and a severity of 0 that the schema's own 1-to-10 bound should have forbidden, so
the numeric constraint is not being enforced either. This is the grammar-versus-reasoning
collision the literature describes for a small model served without a reasoning parser:
the grammar applies from the first token and the model never gets to think.

**Unconstrained (schema in the prompt only).** Clinically sensible and structurally wrong:
it correctly separated the thigh ache from the dark urine and attributed both to
atorvastatin, but answered with a top-level array and invented keys (`location`,
`associated_factors`) instead of the agreed object. Our parser scores that zero.

Neither arm is a fair measure of clinical ability on its own, which is exactly why both
are being run over all 70 scenarios rather than one being picked. Reporting only the
constrained arm would say MedGemma is useless; reporting only the unconstrained arm would
say it cannot produce usable output. The truthful statement is narrower: **on this serving
configuration MedGemma cannot both think and conform**, and that is a property of the
deployment, not a verdict on the model's medical knowledge.

## 14. Three-way result, 2026-09-17

Reports: `ai_eval_20260917_172344` (gpt-oss, 3.8 Flash), `_183906` (MedGemma, constrained),
`_192522` (MedGemma, prompt-only). 70 scenarios each, sequential, one trial per scenario.

**Availability.** gpt-oss and 3.8 Flash answered 65 of 70 each. MedGemma answered 62 under
constrained decoding, losing 8 to timeouts concentrated on long document prompts, and 60
unconstrained, losing 10 to replies that did not satisfy the contract.

**Safety is where the decision is made, not accuracy.**

| Workload | gpt-oss | 3.8 Flash | MedGemma (constrained) | MedGemma (prompt) |
| --- | --- | --- | --- | --- |
| Allergy conflict never missed | 100% | 100% | **0%** | **0%** |
| Urgent never under-triaged | 100% | 100% | **79%** | **75%** |
| Red flag never missed | 100% | 100% | 100% | **33%** |

**Corrected 2026-09-17, after inspecting the outputs.** The 0% figures above are the
scored safety rate and they are accurate as such, but the sentence originally written here
— "MedGemma missed every allergy conflict in both arms" — was wrong, and wrong in the
exact way this whole document exists to prevent. Checking what it actually wrote:

- **Prompt-only arm: it found both allergy conflicts.** On `med-005` it emitted a
  `"type": "allergy_conflict"` finding, and scored zero because a *different* finding in
  the same reply came back as `"type": "missing_medication | dose_mismatch"` — it had
  copied the literal enum menu out of our own prompt template, which fails validation and
  voids the whole object. On `med-012` it identified the conflict but named the allergen
  (Penicilina) rather than the conflicting drug (Amoxicilina), which our matcher rejects.
- **Constrained arm: it genuinely did not produce them.** Neither reply mentions
  `allergy_conflict` at all, consistent with the grammar suppressing its reasoning.

Four of its fourteen discrepancy answers copied that enum menu; no other model did it once.
Five of fourteen failed to parse. So the reconciliation collapse is dominated by contract
and prompt-template effects, not by an inability to see the clinical finding.

**Accuracy on answered calls**, with paired tests on identical scenarios:

- **Patient explanation**: 91-98% for all four, and no pair shows a measurable difference.
- **Triage**: gpt-oss 100%, 3.8 Flash 96%, MedGemma 89% and 80%. gpt-oss beats MedGemma
  prompt-only significantly (p=0.021); nothing else separates.
- **Symptom/ADR**: gpt-oss 98%, 3.8 Flash 96%, MedGemma 39% constrained and 76% prompt.
  Both cloud models beat constrained MedGemma significantly (p=0.004 and p=0.008).
- **Medication discrepancy**: 3.8 Flash 98%, gpt-oss 81%, MedGemma 14% and 43%. Both cloud
  models beat both MedGemma arms significantly (p=0.001 to p=0.031). gpt-oss fails the
  90% recall bar at 71%; 3.8 Flash passes at 94%.

**September's MedGemma claim is refuted.** It was reported as the most accurate document
reader at 90% field accuracy. Measured under the fixed harness it reaches 75% (49-97)
unconstrained and 49% constrained on 3 of 10 answered calls. The old number came from a
lenient matcher, an evidence axis that penalised the constrained models, and a single arm.

**Cost.** The endpoint lived about 91 minutes including a 13-minute deploy, roughly $3 of
L4 time, against about 7 cents of tokens for the entire cloud leg. MedGemma is slower per
call than both cloud models when constrained (median 12.7 s) and, notably, the fastest of
all four unconstrained (5.7 s).

**Verdict: MedGemma does not earn its GPU for this product.** It is no better than the
metered models anywhere, significantly worse on two workloads, misses allergy conflicts
outright, under-triages urgent cases, and on this serving configuration cannot both reason
and conform to the output contract.

**Limits of this result.** One trial per scenario, 8 to 28 scenarios per workload, no
repeat-variance measurement, and the §5 controls were not run. Anything the paired tests
call "no measurable difference" should be read as this evaluation being unable to tell
them apart, not as proof they are equal.

## 15. The endpoint was never recorded — verified and fixed, 2026-09-17

Building the production transport for `gpt-oss-120b-maas` exposed a gap in every report
this protocol has produced: **`base_url` was never written to the environment block.**
Reports record the provider name, the model id, the reasoning effort and whether a native
schema was requested, but not the endpoint the calls actually reached. So the run that our
routing decision rests on (`ai_eval_20260917_172344`) cannot, from its own report, be
told apart from the same models served regionally, from a different project, or from a
self-hosted container. The endpoint had to be reconstructed from a `--provider` line in a
spec written weeks earlier.

This is the failure §7 was meant to prevent, one field short. `run_ai_eval.py` now records
`base_url` per provider. Earlier reports cannot be repaired; treat their endpoint as
unrecorded rather than assumed.

**What was verified live**, against project `medi-agent-490106` with Application Default
Credentials:

- Both endpoint forms serve the model and return `finish_reason: stop`:
  `https://aiplatform.googleapis.com/v1/projects/{P}/locations/global/endpoints/openapi`
  and the `us-central1` regional equivalent. The global host carries no region prefix,
  so the two forms are not one template with a region substituted in.
- **The publisher prefix is part of the model id**, not decoration: `openai/gpt-oss-120b-maas`
  and `google/gemini-3.8-flash` on this surface, against a bare `gemini-3.8-flash` through
  the Gen AI SDK. The prefix is spelled identically to a LiteLLM provider prefix and reads
  as redundant beside a transport already named for the OpenAI dialect, which is exactly
  how it would get removed. It is now pinned by a test.
- **`reasoning_tokens` is not reported** by this surface — `completion_tokens_details` is
  absent. Cost and truncation accounting that reads that field gets nothing here, so a
  thinking model's spend is visible only in the completion total.
- A 16-token budget returns HTTP 200 with empty content and no error. That is the
  documented `TRUNCATED` disposition, not a failure: a one-word answer needed 18-20
  completion tokens because the model reasons first. Any probe of this model that budgets
  tokens as if it were a plain model will measure nothing and look like a broken endpoint.

**Latency, with the correction that matters.** The first probe showed 0.47 s global
against 8.35 s regional, which looked decisive and was not: repeating it alternately for
four rounds showed the large regional numbers were cold starts. Warm, the comparison is
0.34-0.46 s global against 0.56-1.21 s regional. Global is chosen for consistency and
because it matches the `location=global` the Gemini client already uses, so one project
setting describes both transports — not on the strength of the first measurement, which
was an artefact of warm-up on n=1.

## 16. The token floor rests on a false premise — measured, 2026-09-17

`GeminiClient._generate_genai_sdk` raises every request to `max(max_tokens, 8192)`. The
comment beside it says the Gen AI SDK "seems to have a lower default max_output_tokens".
It does not. `GenerateContentConfig.max_output_tokens` defaults to `None`, and measured
against `gemini-3.8-flash` on Vertex with an identical prompt and `temperature=0`:

| Config | finish_reason | output tokens | thought tokens |
| --- | --- | --- | --- |
| no `max_output_tokens` | `STOP` | 1890 | 202 |
| `max_output_tokens=8192` | `STOP` | 1890 | 297 |
| `max_output_tokens=512` | `MAX_TOKENS` | 224 | 284 |
| `512`, `thinking_budget=0` | `MAX_TOKENS` | 508 | none |
| `2048`, `thinking_budget=0` | `STOP` | 1920 | none |

Unset and 8192 are the same result, so the floor does nothing in the case it was written
for. It was added in `1a5820e` (2026-03-22) and never measured.

**What it does accidentally mask is real.** Thought tokens are charged against the same
budget as the answer, so at 512 the model spent 284 tokens thinking and emitted 224 — it
ran out of budget mid-answer. Production callers ask for 384 to 2048 (`symptom/graph.py`
384, `triage/graph.py` 512, `explanation_service.py` 512, `ingestion/graph.py` 2048), so
removing the floor and honouring those numbers would truncate a thinking model on its own
reasoning. That is why this is one change and not two: **the budget and the thinking
policy have to be decided together.**

**`thinking_budget=0` frees the budget for the answer** — the same 512 produced 508
visible tokens instead of 224. Two caveats that keep this from being a flag flip:
`thinking_budget=128` behaved identically to `0` rather than thinking a little, so only
"off" is demonstrated and graduated budgets are unverified; and every accuracy number we
have for this model was measured *with* thinking, so disabling it is a quality change this
evaluation has not covered. It needs a measured decision, not an edit.

**Consequence for the migration.** Until this is resolved, setting `GOOGLE_PROJECT_ID` in
production moves every caller onto the Vertex path at up to 16x the requested budget. The
switch to Vertex should wait for it.

## 17. Correcting §16: `thinking_level`, not `thinking_budget` — 2026-09-17

§16 was written from probes alone, before checking Google's documentation for Gemini 3.x.
Two of its conclusions are wrong and are corrected here rather than edited away.

**`thinking_budget` is deprecated on Gemini 3.x.** It is accepted for backwards
compatibility and no longer honoured as a token count. That is the real explanation for
the §16 anomaly where `thinking_budget=128` behaved identically to `0` — it was not a
budget being rounded, it was a deprecated parameter being coerced. §16 recorded that as
"only off is demonstrated, graduated budgets unverified"; the truth is that the parameter
itself was the wrong lever.

**Dynamic thinking cannot be disabled on Gemini 3.x.** It is always on, and the model
decides how much to think up to the ceiling set by `thinking_level`. So "turn thinking
off" was never an option, and §16's framing of it as an unmeasured quality trade-off was
answering a question that does not exist.

**`thinking_level` is the supported control**, taking `MINIMAL`, `LOW`, `MEDIUM`, `HIGH`.
Measured against `gemini-3.8-flash` on Vertex, `max_output_tokens=1024`, one realistic
bilingual-clinical prompt:

| thinking_level | thought tokens | answer tokens | finish_reason |
| --- | --- | --- | --- |
| unspecified | 661 | 265 | `STOP` |
| `LOW` | 464 | 285 | `STOP` |
| `MEDIUM` | 568 | 317 | `STOP` |
| `HIGH` | 752 | 268 | **`MAX_TOKENS`** |
| `MINIMAL` | — | — | **HTTP 400, unsupported on this model** |

**Thinking cost is not predictable from the level.** Repeating the measurement with a
short triage prompt and a long `es-MX` explanation prompt shows the level is a ceiling the
model may ignore entirely, and that what it actually spends depends on the prompt:

| Prompt | level | budget | thoughts | answer | finish_reason |
| --- | --- | --- | --- | --- | --- |
| triage (short) | `LOW` | 1024 | 201 | 115 | `STOP` |
| triage (short) | `MEDIUM` | 1024 | 416 | 125 | `STOP` |
| explanation (long) | `LOW` | 1024 | **0** | 1045 | **`MAX_TOKENS`** |
| explanation (long) | `LOW` | 2048 | **0** | 957 | `STOP` |
| explanation (long) | `MEDIUM` | 1024 | 984 | **36** | **`MAX_TOKENS`** |
| explanation (long) | `MEDIUM` | 2048 | 941 | 1080 | `STOP` |

The long prompt at `LOW` produced **no thinking at all** while the short prompt at the same
level spent 201–439 tokens, so a fixed "budget = N × expected answer" rule cannot be
derived from the level. The worst cell is `MEDIUM` at 1024: 984 tokens of reasoning and a
**36-token** clinical answer, truncated — which under today's client is returned to the
patient as though it were the whole reply.

Two practical numbers for sizing: triage answers run 115–136 tokens, so 1024 is ample;
the explanation answer runs 950–1166 and truncates at 1024, so it needs 2048 as a floor.
Because the thinking share is prompt-dependent and ranged from 0% to 96% across these
runs, **budgets cannot be tuned to be always-sufficient** — detecting `MAX_TOKENS` and
regenerating is the part that has to be reliable.

Three things follow. **Thinking takes 45–73% of the budget**, so a limit sized for a
non-thinking model starves the answer. **Our production callers ask for 384 to 2048**, and
the smallest of those would be consumed entirely by reasoning. And **`MINIMAL` is rejected
by 3.8 Flash**, so the usable range is `LOW` to `HIGH` and a config that assumes otherwise
fails with a 400 at call time, not at startup.

**Google's guidance matches the measurement**: do not use a small `max_output_tokens` to
control cost or latency — lower `thinking_level` instead, and size `max_output_tokens` for
reasoning plus answer together. Google also says to drop `temperature`, `top_k` and
`top_p` for 3.x, which our call sites still send; the API accepts them without error, so
this is a quiet mismatch rather than a failure.

**The defect this exposes is not cost.** `_generate_genai_sdk` logs a warning when
`finish_reason` is not `STOP` and then **returns the partial text anyway**, so a truncated
clinical answer reaches the patient looking complete. That is the argument for detecting
`MAX_TOKENS` and regenerating, and it is a correctness problem, not an efficiency one.
