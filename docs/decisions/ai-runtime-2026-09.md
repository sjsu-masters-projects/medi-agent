# AI runtime decision record — September 2026

**Status:** Implemented routing; deployed acceptance evidence is still being collected.

## Decision

MediAgent uses two explicit Vertex AI transports behind one workload registry. The choice is
per workload, not a clinical authority decision: deterministic safety, authorization, approval,
and provenance rules run independently of a model response.

| Workload | Primary | Fallback | Deterministic outcome |
| --- | --- | --- | --- |
| Triage | GPT OSS MaaS | Gemini Flash | Emergency floor, then localized unavailable response |
| Patient reply and explanation | Gemini Flash | GPT OSS MaaS | Localized template |
| Document extraction | Gemini Flash | None | No candidate facts; mark for evidence review |
| Medication discrepancy | Gemini Flash | None | Deterministic discrepancy engine only |
| ADR extraction | Gemini Flash | GPT OSS MaaS | Do not write a symptom report |

The authoritative route definitions, output ceilings, thinking levels, kill switches, and
latency budgets are in `backend/src/app/adk/registry.py`.

## Serving locations

- **Gemini Flash** is called with the Google Gen AI SDK through Vertex's global endpoint:
  `GEMINI_VERTEX_AI_LOCATION=global`.
- **GPT OSS MaaS** uses Vertex's OpenAI-compatible regional endpoint:
  `VERTEX_AI_LOCATION=us-central1` and `openai/gpt-oss-120b-maas`.
- The locations must remain separate. Moving MaaS to `global` breaks its approved regional
  route; using the MaaS region for Gemini 3.8 Flash caused the responder's immediate client
  error.

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

## Evidence and limits

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
