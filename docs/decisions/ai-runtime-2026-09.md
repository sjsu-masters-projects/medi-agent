# AI runtime decision record — September 2026

**Status:** Implemented routing; deployed acceptance evidence is still being collected.

## Decision

MediAgent uses two explicit Vertex AI transports behind one workload registry. The choice is
per workload, not a clinical authority decision: deterministic safety, authorization, approval,
and provenance rules run independently of a model response.

| Workload | Primary | Fallback | Deterministic outcome |
| --- | --- | --- | --- |
| Triage | Gemini 3.1 Flash-Lite | Gemini Flash | Emergency floor, then localized unavailable response |
| Patient reply and explanation | Gemini Flash | Gemini 3.1 Flash-Lite | Localized template |
| Document extraction | Gemini Flash | None | No candidate facts; mark for evidence review |
| Medication discrepancy | Gemini Flash | None | Deterministic discrepancy engine only |
| ADR extraction | Gemini Flash | Gemini 3.1 Flash-Lite | Do not write a symptom report |

The authoritative route definitions, output ceilings, thinking levels, kill switches, and
latency budgets are in `backend/src/app/adk/registry.py`.

## Serving locations

- **Gemini Flash** is called with the Google Gen AI SDK through Vertex's global endpoint:
  `GEMINI_VERTEX_AI_LOCATION=global`.
- **Gemini 3.1 Flash-Lite** uses that same native transport and global endpoint. It has its
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
   stay on the native Gemini transport and use distinct Flash-Lite and Flash models for fallback.
10. The complete coordinator-and-responder turn has a 30-second ceiling and returns reviewed,
    localized unavailable copy when both routes cannot finish. The triage decision tool ends the
    coordinator stage directly; no second model call narrates a decision whose prose is discarded.

## Evidence and limits

### Capacity controls — 2026-10-03 (not deployed)

Interactive ADK routes allow one 429 retry with 200–400 ms jitter (or a valid
`Retry-After` plus 0–100 ms jitter). Delays over one second, or without at least
500 ms remaining for the response, immediately return the original error to the
declared fallback. Admission, provider work, and retry sleep remain inside the
existing route deadline. Other statuses do not gain retries. Failed response
buffers and request mutations are discarded. SDK/LiteLLM automatic retries are
explicitly disabled for these routes; the application owns the retry.

Native Vertex chat and background text calls share process/event-loop-local
endpoint/model gates: two in-flight calls and 250 ms between starts by default.
Background text calls can occupy only one of those two slots. Retries re-enter
admission. `MODEL_MAX_CONCURRENCY` and `MODEL_MIN_START_INTERVAL_SECONDS` are
validated configuration; a concurrency setting of one cannot reserve a slot.
Independent Cloud Run instances and worker Jobs do not share these gates, so
these controls reduce local bursts, not aggregate project traffic or Google's
shared-pool contention. Existing background retry limits remain unchanged.

The `model_attempt` structured log contains only model, endpoint location, numeric
status, retry count, latency, fallback-candidate role and safe failure category.
No raw exception, prompt, response, patient identifier, credential, or endpoint
URL is logged. This per-transport-attempt evidence supplements existing workload
database telemetry; no database schema change is required.

The first eight-call global synthetic probe yielded 7/8 first-attempt successes,
zero 429s and zero retry recoveries, and one GPT OSS deadline/fallback (11.002 s
total). Flash-Lite finished 4/4 first attempts (1.471–2.474 s); GPT OSS finished
3/4 (0.662–3.732 s). Strict response-contract checks passed 7/8: the Spanish
fallback translated JSON keys rather than only values. Emergency responses all
included 911; routine responses contained generic, unverified contact suggestions.
The preflight prompt now explicitly fixes key names and forbids invented contact
details. This is a small transport/payload sanity check, not the production tool
prompt, a clinical benchmark, or proof that 429s are eliminated. Controlled tests
provide retry-recovery and bilingual unavailable-response evidence without
forcing failures against a live service. GPT OSS remains evaluation-only.

After tightening that synthetic prompt, a second global run passed 8/8 response
contracts and first attempts, with no 429s, retries or fallbacks. Flash-Lite total
latency was 1.198–3.004 s (median 1.959 s); GPT OSS 0.824–6.582 s (median 2.784 s).
Manual inspection confirmed the requested English/Spanish language, secure-message
contact instructions and 911 emergency advice. GPT OSS Spanish routine wording
was understandable but less natural. Across both small runs, one of eight GPT OSS
primary calls timed out; no live retry recovery can be claimed because no 429
occurred. Keep production routing unchanged and collect post-deployment metrics
before considering a model promotion or claiming reduced production fallback rates.

The synthetic evaluation harness and fixtures are maintained in
`backend/scripts/run_ai_eval.py` and `backend/tests/fixtures/eval/`. The September comparison
supported the routing trade-offs but was not clinician-adjudicated and is not a release-quality
clinical benchmark. Generated reports are local artifacts and are intentionally ignored by Git.

The direct MaaS request has succeeded in `us-central1`, and telemetry records successful
coordinator calls. The remaining live acceptance check is a post-deployment synthetic chat
request that records a successful Gemini responder event. The runtime still needs enforced
wall-clock budgets around the ADK runner before the registry's named latency budgets can be
claimed as complete.

## Superseded material

This record replaces the September spike, market surveys, provider-cost research, and
evaluation narrative documents. Their dated measurements remain available in Git history;
they must not be treated as current pricing, availability, or model-selection guidance.
