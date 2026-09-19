# Serverless token-priced inference providers for MediAgent open-weight hosting (as of 2026-09-10)

## Executive summary

- **Every provider researched beats the Gemini 3.5 Flash-Lite baseline** ($0.30/$2.50
  per 1M in/out) on raw per-token price for gpt-oss-120b, often by 4–8x on blended
  scenario cost. Cheapest confirmed: **DeepInfra** at $0.037/$0.17 per 1M — about
  12–20x cheaper than Gemini on a blended workload.
- For a **HIPAA/BAA-track deployment**, the strongest confirmed BAA paths are
  **Baseten** ($0.10/$0.50), **Groq** ($0.15/$0.60 — its own Services Agreement
  §3.4 commits to processing PHI under a separately published BAA, plus a
  standalone BAA addendum document), **Fireworks AI** (also $0.15/$0.60,
  explicitly "HIPAA, SOC2-Type II, GDPR compliant" per its own docs), and **AWS
  Bedrock** ($0.1545/$0.618, official on-demand price, Sydney region shown).
  **Together AI's HIPAA claim could not be confirmed in its own accessible
  security/privacy documentation**, despite a third-party trust-registry summary
  describing it as "HIPAA Compliant" — treat that specific claim as unverified.
  Google Vertex AI and Azure AI Foundry both have account-level BAAs, but
  **neither provider's own HIPAA documentation clearly states that third-party
  open-weight MaaS endpoints (as opposed to first-party Gemini / Azure OpenAI
  models) are in scope** — this is the single most consequential open compliance
  question in this report.
- **Llama Guard 4 12B has strikingly limited serverless availability — confirmed
  from three independent research passes.** Of 16 providers researched, only
  **DeepInfra** (and Hugging Face Inference Providers, which simply routes to
  DeepInfra) has a confirmed, priced, pay-per-token endpoint ($0.18/$0.18 per 1M
  standard; Priority $0.27/$0.27; Flex $0.144/$0.144). It is confirmed **absent**
  from Groq (which instead sells the unrelated "Llama Prompt Guard 2" product),
  Together AI (a model page exists showing a nominal $0.20/$0.20 rate but
  explicitly states "not available on Together's Serverless API... Launching
  soon"), Fireworks AI (404), Cerebras, AWS Bedrock, and Cloudflare Workers AI
  (Llama Guard 3 8B only), and **available but unpriced** on Google Vertex AI
  Model Garden. No provider with a confirmed price for this model has a
  confirmed BAA — a real gap for a HIPAA-track safety classifier.
- **MedGemma 1.5 4B has no serverless token-priced endpoint anywhere in scope.**
  It is HAI-DEF-licensed, free to download, and deployable only as a
  self-managed/dedicated (GPU-hour-billed) endpoint on Vertex AI or via
  self-hosting; Hugging Face's own API confirms zero Inference Providers serve
  it; also confirmed absent (404/not in catalog) on Groq, Cerebras, Together,
  Fireworks, and DeepInfra.
- **Baichuan-M2 32B** (medical-enhanced reasoning model) is offered as pay-per-token
  by exactly two providers in scope: **Novita** ($0.07/$0.07, confirmed direct) and,
  via Hugging Face Inference Providers, **Featherless AI** (pricing not confirmed
  as strict per-token). Confirmed absent from Groq, Cerebras, Together, Fireworks,
  and DeepInfra. Neither confirmed offering has a confirmed BAA.
- **Gemma 4** (released 2026-04-02) has reached serverless pricing on **DeepInfra**
  (31B-it $0.13/$0.38, E4B $0.02/$0.10), **Cloudflare Workers AI** (26B MoE
  variant, $0.10/$0.30), **Together AI** (31B, $0.39/$0.97), and **AWS Bedrock**
  (31B, $0.14/$0.40, official, US East); most other providers in scope still only
  price **Gemma 3** SKUs. Notably, **Cerebras offered Gemma 4 31B as a public
  preview model but removed it from public serverless endpoints on 2026-09-03 —
  one week before this report — moving it to Dedicated-Endpoints-only, custom
  pricing** (source: [Cerebras deprecation log](https://inference-docs.cerebras.ai/support/deprecation)).
- **Concrete 2026 model-retirement/outage evidence is worth planning around.**
  Cerebras deprecated `qwen-3-32b` on 2026-02-16 and pulled `gemma-4-31b` from
  public serverless on 2026-09-03; Together AI's status page shows several
  multi-hour 2026 outages, including a 7h13m Gemma-4-31B-IT outage (Jun 13–20)
  and a 17h5m outage on an unrelated model (Aug 6), plus gpt-oss-120b incidents
  Sep 3–7; DeepInfra logged 8h+ and 6h+ outages on its Gemma-4-31B-it-turbo
  endpoint in July 2026. See §5b and §7 for full detail.

## 0. Scope and method

This report evaluates 16 serverless, pay-per-token inference offerings as hosting
options for MediAgent's open-weight model workloads (chat classification+reply,
safety classification, document structuring), against the Gemini 3.5 Flash-Lite
baseline MediAgent runs today on Vertex AI.

Providers covered: Groq, Cerebras, Together AI, Fireworks AI, DeepInfra, OpenRouter,
SambaNova, Baseten (model APIs), Nebius AI Studio, Novita, Hyperbolic, Cloudflare
Workers AI, Hugging Face Inference Providers, Google Vertex AI MaaS (open models),
AWS Bedrock (open models), Azure AI Foundry serverless open models.

All prices are USD per 1,000,000 tokens unless stated otherwise. Every figure is
sourced in the "Per-provider notes and citations" section (§7) with a URL and the
date it was retrieved (research was conducted 2026-09-10). Numbers in the master
table are flagged **[official]** (provider's own pricing/docs page), **[aggregator]**
(cross-checked via OpenRouter's public endpoints API or a third-party pricing
tracker, not independently confirmed on the provider's own page), or **not found**.
Nothing in this report is estimated or guessed where a source could not be found.

Research method: this report combines (1) direct WebSearch/WebFetch research
performed in this session, and (2) a detailed research pass (also WebSearch/WebFetch,
including direct fetches of Cloudflare's, Hugging Face's, AWS's, and Microsoft's own
documentation and APIs) covering Cloudflare Workers AI, Hugging Face Inference
Providers, Google Vertex AI MaaS, AWS Bedrock, and Azure AI Foundry, whose findings
are integrated throughout and specifically credited in §7. Two additional research
passes (covering Groq/Cerebras/Together/Fireworks/DeepInfra and
OpenRouter/SambaNova/Baseten/Nebius/Novita/Hyperbolic) were launched but had not
returned by the time this report was finalized at the requester's direction; those
five-plus-six providers are covered instead by this session's own direct research,
which is generally shallower on rate limits/SLA/retention detail than the
hyperscaler section — see §6 for exactly which fields are weaker as a result.

## 1. Workload token volumes used for scenario costing

Per CONTEXT.md, chat turn = classification (400 in / 60 out) + reply (1,500 in /
250 out) = **1,900 in / 310 out tokens/turn**. Safety classifier = 500 in / 10 out
tokens, one call per chat turn. Documents = 700 in / 700 out tokens/document.

| Workload | Model | Scenario A (expo) | Scenario B (1 clinic) | Scenario C (10 clinics) |
|---|---|---|---|---|
| (a) Chat classification + reply | gpt-oss-120b | 3,000 turns → 5.70M in / 0.93M out | 60,000 turns → 114.0M in / 18.6M out | 600,000 turns → 1,140.0M in / 186.0M out |
| (b) Safety classifier | Llama Guard 4 12B | 3,000 calls → 1.50M in / 0.03M out | 60,000 calls → 30.0M in / 0.6M out | 600,000 calls → 300.0M in / 6.0M out |
| (c) Documents | gpt-oss-120b | 600 docs → 0.42M in / 0.42M out | 3,000 docs → 2.10M in / 2.10M out | 30,000 docs → 21.0M in / 21.0M out |

Cost formula: `cost = (input_tokens / 1e6) × price_in + (output_tokens / 1e6) × price_out`.

## 2. Gemini 3.5 Flash-Lite baseline (Vertex AI)

Confirmed current: Gemini 3.5 Flash-Lite is priced **$0.30 / 1M input, $2.50 / 1M
output** on Vertex AI, GA since July 2026, priced level with Gemini 2.5 Flash
(source: [CloudZero Vertex AI pricing 2026](https://www.cloudzero.com/blog/google-vertex-ai-pricing/),
[Requesty gemini-3.5-flash-lite](https://www.requesty.ai/models/vertex/gemini-3.5-flash-lite),
[BenchLM Gemini pricing Sept 2026](https://benchlm.ai/google/api-pricing); seen
2026-09-10). This matches CONTEXT.md, so the CONTEXT.md baseline is current.

Gemini 3.5 Flash-Lite baseline cost per scenario, combining (a)+(b)+(c) (i.e., what
MediAgent would pay running all three workloads on one model):

| Scenario | Total in tokens | Total out tokens | Cost |
|---|---|---|---|
| A | 7.62M | 1.38M | 7.62×0.30 + 1.38×2.50 = **$5.74** |
| B | 146.10M | 21.30M | 146.10×0.30 + 21.30×2.50 = **$97.08** |
| C | 1,461.00M | 213.00M | 1,461.00×0.30 + 213.00×2.50 = **$970.80** |

(Per-chat-turn cost ≈ $0.00135, consistent with CONTEXT.md's "~$0.0015 per chat
turn"; per-document cost ≈ $0.00196, consistent with CONTEXT.md's "~$0.002–0.005
per document" range.)

## 3. Model availability and release facts

- **gpt-oss-120b / gpt-oss-20b**: OpenAI open-weight reasoning models, released
  2025-08-05 under Apache 2.0 + OpenAI gpt-oss usage policy; not served by OpenAI's
  own API (source: [OpenAI gpt-oss model card](https://openai.com/index/gpt-oss-model-card/),
  [OpenAI Help Center](https://help.openai.com/en/articles/11870455-openai-open-weight-models-gpt-oss),
  seen 2026-09-10). 120b: MoE, 116.8B total/5.1B active, fits one 80GB GPU; 20b:
  21B total/3.6B active (~16GB memory).
- **Qwen 3.6**: Qwen3.6-Plus-Preview released 2026-03-30 (1M context, proprietary
  tier); **Qwen3.6-35B-A3B** (35B total/~3B active MoE) is the open-weight release
  closest to "32B-class," published 2026-04-16; Qwen3.6-Max-Preview released
  2026-04-20 (source: [BuildFastWithAI](https://www.buildfastwithai.com/blogs/qwen3-6-max-preview-review-2026),
  [AIMLAPI](https://aimlapi.com/blog/qwen-3-6-series-alibabas-open-source-llm-revolution-in-2026),
  [Yotta Labs](https://www.yottalabs.ai/post/qwen-3-7-vs-qwen-3-6-what-actually-exists-and-what-to-use-in-production);
  seen 2026-09-10). Most providers in scope still price the older dense
  **Qwen3-32B** as their "32B-class Qwen" SKU rather than the 3.6-generation model
  — flagged per-provider in §5/§7.
- **Gemma 4**: released 2026-04-02 by Google DeepMind (Apache 2.0), sizes E2B, E4B,
  12B, 26B, 31B, up to 256K context (source: [Google Cloud blog](https://cloud.google.com/blog/products/ai-machine-learning/gemma-4-available-on-google-cloud),
  [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4); seen
  2026-09-10). Reached serverless pricing on Cloudflare Workers AI (26B-A4B,
  $0.10/$0.30), Together AI (31B, $0.39/$0.97) and AWS Bedrock (31B, $0.14/$0.40,
  US East, official) as of this report; most other providers still only price
  Gemma 3 SKUs.
- **MedGemma 1.5 4B**: released 2026-01-13 under HAI-DEF terms; free to download,
  but Vertex AI Model Garden serves it only via **self-managed/dedicated
  (GPU-hour-billed) deployment, not pay-per-token MaaS** (source: [Google Research
  blog](https://research.google/blog/next-generation-medical-image-interpretation-with-medgemma-15-and-medical-speech-to-text-with-medasr/),
  [HAI-DEF MedGemma card, HF](https://huggingface.co/google/medgemma-1.5-4b-it),
  seen 2026-09-10). Independently confirmed via Hugging Face's own API that
  `google/medgemma-4b-it` has an **empty `inferenceProviderMapping`** — zero
  Inference Providers currently serve it (source:
  `huggingface.co/api/models/google/medgemma-4b-it?expand[]=inferenceProviderMapping`,
  seen 2026-09-10). No serverless token-priced MedGemma endpoint was found on any
  of the 16 providers.
- **Baichuan-M2 32B**: 32.8B-parameter medical-enhanced reasoning model on
  Qwen2.5-32B, open-weight. **Novita** offers it pay-per-token at **$0.07/$0.07
  per 1M** (131K context; source: [Requesty](https://www.requesty.ai/models/novita/baichuan-baichuan-m2-32b),
  page states "provider prices per 1M tokens, updated September 11, 2026," seen
  2026-09-10). Also confirmed served, via Hugging Face Inference Providers, by
  **Featherless AI** (source: `huggingface.co/api/models/baichuan-inc/Baichuan-M2-32B?expand[]=inferenceProviderMapping`,
  seen 2026-09-10) — Featherless's own pricing is subscription/quota-based rather
  than strict per-token, so not usable for direct $/1M comparison. No other
  in-scope provider was found to offer it.
- **Llama Guard 4 12B — a market-gap finding**: confirmed **absent** from AWS
  Bedrock's full model catalog and from Cloudflare Workers AI (which offers only
  the older Llama Guard 3 8B, $0.484 in / $0.030 out per 1M). Confirmed
  **available but with no published per-token price** on Google Vertex AI Model
  Garden (a Google Cloud sample notebook demonstrates deployment, but no MaaS rate
  card entry was found). The only provider in scope with a confirmed, priced,
  serverless endpoint is **DeepInfra** ($0.18/$0.18 per 1M), also reachable
  pass-through via Hugging Face Inference Providers at three speed tiers: Flex
  $0.144/$0.144, Standard $0.18/$0.18, Priority $0.27/$0.27 (source:
  `huggingface.co/api/models/meta-llama/Llama-Guard-4-12B`, cross-checked against
  `deepinfra.com/meta-llama/Llama-Guard-4-12B`, seen 2026-09-10). Not found at all
  on Groq, Cerebras, Together, Fireworks, SambaNova, Baseten, Nebius, Novita,
  Hyperbolic, or Azure AI Foundry within this session's research.

## 4. Cross-check: OpenRouter aggregator raw endpoint pricing snapshot (2026-09-10)

OpenRouter's public `/api/v1/models/{id}/endpoints` JSON lists upstream providers
and their raw per-token prices for a model. Used only as a cross-check — a
provider can serve a model directly without being an OpenRouter-integrated
upstream for that slug (e.g., Fireworks AI and Hyperbolic did not appear for
gpt-oss-120b via OpenRouter despite offering it directly). Source: openrouter.ai
public endpoints API, seen 2026-09-10.

**openai/gpt-oss-120b:**

| Upstream (via OpenRouter) | Input $/1M | Output $/1M |
|---|---|---|
| AkashML | 0.03 | 0.17 |
| CoreWeave | 0.03 | 0.17 |
| DeepInfra (tier 1) | 0.037 | 0.17 |
| Novita | 0.05 | 0.25 |
| DigitalOcean | 0.055 | 0.385 |
| Mancer 2 | 0.055 | 0.50 |
| Google (Vertex, via OR) | 0.09 | 0.36 |
| Baseten | 0.10 | 0.50 |
| Parasail | 0.10 | 0.75 |
| SambaNova | 0.14 | 0.95 |
| Amazon Bedrock | 0.15 | 0.60 |
| Nebius | 0.15 | 0.60 |
| DeepInfra (tier 2) | 0.15 | 0.60 |
| SiliconFlow | 0.15 | 0.60 |
| Phala | 0.15 | 0.60 |
| Together | 0.15 | 0.60 |
| Groq | 0.15 | 0.60 |
| Mara | 0.15 | 0.75 |
| Cerebras | 0.35 | 0.75 |

Note: AWS Bedrock's *own* pricing page, fetched directly, shows $0.1545/$0.618 per
1M (Sydney region) for gpt-oss-120b — close to but not identical to the $0.15/$0.60
OpenRouter shows for the "Amazon Bedrock" upstream; the small gap is plausibly a
region or rounding difference. Where both exist, §5/§7 use the official Bedrock
figure.

**openai/gpt-oss-20b:**

| Upstream (via OpenRouter) | Input $/1M | Output $/1M |
|---|---|---|
| Darkbloom | 0.02 | 0.10 |
| AkashML | 0.02 | 0.10 |
| CoreWeave | 0.03 | 0.13 |
| DeepInfra | 0.03 | 0.14 |
| Parasail | 0.03 | 0.15 |
| Phala | 0.04 | 0.15 |
| Novita | 0.04 | 0.15 |
| SiliconFlow | 0.04 | 0.18 |
| Together | 0.05 | 0.20 |
| Amazon Bedrock | 0.07 | 0.15 |
| Google (Vertex, via OR) | 0.07 | 0.25 |
| Groq | 0.075 | 0.30 |

(AWS's own page shows $0.0721/$0.309 for gpt-oss-20b — consistent with the OR figure.)

**meta-llama/llama-guard-4-12b:** only **DeepInfra** appeared as a routed upstream,
$0.18/$0.18 per 1M — matches the direct DeepInfra/HF-API confirmation in §3.

**meta-llama/llama-4-scout:**

| Upstream | Input $/1M | Output $/1M |
|---|---|---|
| DeepInfra | 0.10 | 0.30 |
| Novita | 0.18 | 0.59 |
| Google (Vertex, via OR) | 0.25 | 0.70 |

**meta-llama/llama-4-maverick:**

| Upstream | Input $/1M | Output $/1M |
|---|---|---|
| DigitalOcean | 0.20 | 0.696 |
| DeepInfra | 0.20 | 0.80 |
| Novita | 0.27 | 0.85 |
| Parasail | 0.35 | 1.00 |
| Google (Vertex, via OR) | 0.35 | 1.15 |

**qwen/qwen3-32b** (dense, non-3.6):

| Upstream | Input $/1M | Output $/1M |
|---|---|---|
| DeepInfra | 0.08 | 0.28 |
| SiliconFlow | 0.14 | 0.57 |

**qwen/qwen3.6-35b-a3b** (actual Qwen 3.6-generation, ~32B-class MoE):

| Upstream | Input $/1M | Output $/1M |
|---|---|---|
| Darkbloom | 0.05 | 0.70 |
| AkashML | 0.10 | 0.90 |
| DeepInfra | 0.10 | 0.95 |
| Venice | 0.10 | 1.00 |
| Io Net | 0.133 | 0.9405 |
| Parasail | 0.15 | 1.00 |
| AtlasCloud | 0.186 | 1.11375 |
| Phala | 0.20 | 1.27 |
| SiliconFlow | 0.24 | 1.80 |
| CoreWeave | 0.25 | 1.25 |

**google/gemma-3-27b-it:**

| Upstream | Input $/1M | Output $/1M |
|---|---|---|
| DeepInfra | 0.08 | 0.16 |
| Parasail | 0.08 | 0.45 |
| Nebius | 0.10 | 0.30 |
| Novita | 0.119 | 0.20 |

**google/gemma-4-31b-it and google/gemma-4-26b-a4b-it** (a later, targeted re-query
found Gemma 4 *is* routed on OpenRouter after all — the initial check above simply
queried the wrong model slug; corrected here): `gemma-4-31b-it` ranges **$0.09–$0.75
in / $0.34–$1.15 out across 14 upstream providers**; `gemma-4-26b-a4b-it` ranges
**$0.042–$0.15 in / $0.22–$0.60 out across 10 upstream providers** (source:
`openrouter.ai/api/v1/models/google/gemma-4-31b-it/endpoints` and
`.../gemma-4-26b-a4b-it/endpoints`, seen 2026-09-10).

## 5. Master comparison table

### 5a. Pricing — $ per 1,000,000 tokens, input / output ("—" = not offered, "nf" = not found)

| Provider | gpt-oss-120b | gpt-oss-20b | Llama 4 Scout | Llama 4 Maverick | Qwen "32B-class" | Gemma (latest priced) | Llama Guard 4 12B | MedGemma 1.5 4B | Baichuan-M2 32B |
|---|---|---|---|---|---|---|---|---|---|
| Groq | 0.15 / 0.60 [official] | 0.075 / 0.30 [official] | — (not offered) [official] | — (not offered) [official] | qwen3.6-27b: 0.60/3.00; qwen3.8-27b: 0.80/4.00 (Preview) [official] | — (no Gemma in catalog) [official] | — (not offered; Groq sells "Llama Prompt Guard 2" instead) [official] | N | N |
| Cerebras | 0.35 / 0.75 [official] | — (not on public tier) [official] | dedicated-endpoints only, custom price [official] | dedicated-endpoints only, custom price [official] | qwen-3.8-27b: 0.99 / 1.49 [official] (qwen-3-32b deprecated 2026-02-16) | gemma-4-31b: **removed from public endpoints 2026-09-03**, now dedicated-only [official] | nf (not on public tier) | N | N |
| Together AI | 0.15 / 0.60 [official] | 0.05 / 0.20 [official] | 0.18 / 0.59 [official] | 0.27 / 0.85 [official] | Qwen3-32B "Launching soon," not yet live [official]; Qwen3.6-Plus 0.50/3.00 live [official] | Gemma 4 31B: 0.39 / 0.97 (eff. 2026-05-21) [official] | shown as 0.20/0.20 but page states **"not available on Together's Serverless API... Launching soon"** [official] | N (404) | N (404) |
| Fireworks AI | Standard 0.15 / 0.60 (cached-in 0.015), Priority 0.18 / 0.72 [official] | nf (page exists, price not rendered) | 0.15 / 0.60 [official] | nf (page exists, price not rendered) | nf (page exists, price not rendered) | multiple Gemma 4/3 SKUs in catalog, price nf | — (404, not offered) [official] | N (404) | N (not found) |
| DeepInfra | 0.037 / 0.17 [official] | 0.03 / 0.14 [official] | 0.10 / 0.30 [official] (one earlier fetch showed 0.08/0.30 — minor discrepancy, re-verify) | 0.20 / 0.80 [official] | Qwen3-32B (dense) Standard 0.08/0.28, Priority 0.12/0.42, Flex 0.064/0.224 [official] | Gemma 4 31B-it: 0.13/0.38; Gemma 4 E4B: 0.02/0.10 [official] | 0.18/0.18 Standard, Priority 0.27/0.27, Flex 0.144/0.144 [official] | N (404) | N (404) |
| SambaNova | 0.22 / 0.59 [official, live pricing API] | — (not offered) [official] | — (deprecated/removed mid-2025) [official] | 0.63 / 1.80 [official, live] but **marked deprecated 2026-06-09 in SambaNova's own docs while still live-priced today — catalog/docs inconsistency** | Qwen3-32B: 0.40 / 0.80 [official, live] but **also marked deprecated 2026-04-06 in docs while still live-priced — same inconsistency** | Gemma 4 31B-it: 0.22/0.59 (pricing API) vs. 0.38/1.15 (rendered pricing page) — ambiguous dual-SKU pricing [official, conflicting] | — (never offered LG4; only ever had Llama Guard 3 8B, removed from Cloud 2025-06-25) [official] | N | N |
| Baseten | 0.10 / 0.50 [official] — **the only one of the 7 target models in Baseten's entire 15-model Model APIs catalog** | — (not offered; catalog has no Llama, Qwen, or Gemma models at all) [official] | — (not offered) [official] | — (not offered) [official] | — (not offered) [official] | — (not offered) [official] | — (not offered) [official] | N | N |
| Nebius AI Studio (rebranded **"Nebius Token Factory"** — docs moved to docs.tokenfactory.nebius.com) | ~0.15 / 0.60 [aggregator; official dashboard requires login] | — (not in the 18-model catalog) | — (not in the catalog) | — (not in the catalog) | Qwen3-32B **officially removed from serverless 2026-08-31** per Nebius's own deprecation notice (replaced by nvidia/Nemotron-3.5-Lightning) — any aggregator price for it is stale [official deprecation notice] | Gemma 4 (31B-it, E2B, E4B) confirmed available for **fine-tuning only**; not found in the live serverless-inference catalog [official docs] | — (not offered) | N | N |
| Novita | **0.05 / 0.25 [official, live API]** | 0.04 / 0.15 [official, live API] | 0.18 / 0.59 [official, live API] | 0.27 / 0.85 [official, live API] | plain Qwen3-32B no longer in the 117-model catalog (superseded by 3.5/3.6/3.7/3.8 lines); closest is qwen3-coder-30b-a3b (coder-specialized) at 0.07/0.27 [official] | Gemma 4 26B-A4B: 0.13/0.40; Gemma 4 31B-it: 0.14/0.40 [official, live API] | — (no "guard" model in the 117-model catalog) [official] | N | **0.07 / 0.07 [official, live API]** |
| Hyperbolic | offered (model page confirmed to exist), price **not found** — app.hyperbolic.ai is a client-rendered SPA with no scrapeable pricing, and no third-party aggregator lists Hyperbolic for this model either | nf | nf | nf | nf | nf | nf | N | N |
| Cloudflare Workers AI | 0.35 / 0.75 [official] | 0.20 / 0.30 [official] | 0.27 / 0.85 [official] | — (not in catalog) | Qwen3-30B-A3B: 0.051 / 0.335 [official] | Gemma 4 26B-A4B: 0.10 / 0.30 [official] | — (only Llama Guard 3 8B: 0.484 / 0.03) [official] | N | N |
| Hugging Face Inference Providers | pass-through, 0.037–~0.35 range across 11 upstreams [official API] | nf (routed) | nf (routed) | nf (routed) | nf | nf | 0.144–0.27 / 0.144–0.27 (3 speed tiers via DeepInfra) [official] | — (empty provider mapping) [official] | Y, via Featherless (price not per-token) [official] |
| OpenRouter | 0.03–0.35 / 0.17–0.95 across 18 upstreams, ~5% markup typical [official live API] | 0.02–0.075 / 0.10–0.30 across 13 upstreams [official live API] | 0.10–0.25 / 0.30–0.70 [official live API] | 0.20–0.35 / 0.70–1.15 [official live API] | 0.08–0.14 / 0.28–0.57 (Qwen3-32B dense) [official live API]; 3.6-generation MoE 0.05–0.25/0.70–1.80 via §4 | Gemma 4 31B-it: 0.09–0.75/0.34–1.15 across 14 upstreams; Gemma 4 26B-A4B: 0.042–0.15/0.22–0.60 across 10 upstreams [official live API] | 0.18/0.18, single upstream (DeepInfra) [official live API] | — (confirmed absent from full 437-model catalog) [official] | — (confirmed absent from full 437-model catalog) [official] |
| Google Vertex AI MaaS | **0.09 / 0.36 [official, GA]** | nf | ~0.25 / 0.70 [aggregator; GA confirmed] | ~0.35 / 1.15 [aggregator; GA confirmed] | GA confirmed, price nf | nf | available (sample notebook), price nf | self-deploy/dedicated only, not MaaS | nf / not found |
| AWS Bedrock | **0.1545 / 0.618 [official, ap-southeast-2 shown]** | 0.0721 / 0.309 [official] | catalog-confirmed, price nf from official page | catalog-confirmed, price nf from official page | 0.1545 / 0.618 [official, flag: identical to gpt-oss-120b row, needs re-verification] | Gemma 4 31B (US East): 0.14 / 0.40 [official]; Gemma 3 27B/12B/4B also priced | — (not in catalog) [official] | — (not in catalog) | — (not in catalog) |
| Azure AI Foundry | availability nf beyond Llama 4 | nf | catalog-confirmed available, official page shows placeholder "$-" | catalog-confirmed available, official page shows placeholder "$-" | nf | nf | nf | nf | nf |

### 5b. Free tier, rate limits, structured output, retention/BAA/SLA/region

| Provider | Free tier / credits | Paid rate limits | JSON-schema structured output | Retention / training / ZDR | HIPAA / BAA | SLA | Region | 2026 notes |
|---|---|---|---|---|---|---|---|---|
| Groq | Rate-limit-gated (no consumable dollar credit found): Free plan e.g. 30 RPM / 1,000 RPD / 8,000 TPM / 200,000 TPD for gpt-oss models, no card required [official docs] | Developer plan "significantly increased" over free tier; exact numeric RPM/TPM not published; Enterprise is custom via sales [official docs] | **Yes** — JSON Schema *strict mode* via constrained decoding (`response_format: json_schema`), guaranteed schema-conformant, confirmed supported on gpt-oss-20b/120b and qwen3.8-27b; best-effort mode also available [official docs] | Per Services Agreement: no access/use/storage of inputs/outputs beyond serving the request; Customer Data deleted within 30 days of termination; contractually barred from training on inputs/outputs absent explicit permission; **ZDR available self-serve to "Eligible Customers" via Console** (not a blanket default) [official] | **Yes** — Services Agreement §3.4 commits to processing PHI under a separately published BAA; eligibility tier (self-serve vs. enterprise) not specified in the text; a standalone BAA addendum document is also published | No numeric SLA; contractual "service level commitments" require a supplemental agreement; status page shows 100% historical uptime Jun–Sep 2026 (not a guarantee) | nf (Trust Center JS-rendered, not retrievable) | No 2026 incidents found on status page; a Groq blog post titled "GPT-OSS improvements, prompt caching and lower pricing" exists but its exact new price could not be extracted — current pricing above may already be conservative/stale on the high side |
| Cerebras | **$5 free credit** after signup + payment method, 30-day expiry; Free Trial limits e.g. 5 RPM / 30K uncached TPM / 90K total TPM / 1M TPH-TPD [official] | Developer (pay-as-you-go): gpt-oss-120b 1,000 RPM / 1M uncached TPM / 3M total TPM, no daily cap; qwen-3.8-27b 300 RPM / 150K / 450K TPM; Enterprise fully custom [official] | **Yes** — `response_format: json_schema` with `strict: true`; confirmed supported models: qwen-3.8-27b, gpt-oss-120b (public tier), gemma-4-31b (dedicated only) [official] | Privacy policy: "We do not retain inputs and outputs associated with... inference... Services," logs deleted "when no longer necessary" — effective zero-retention by default; opt-in-for-training language not explicit | nf — Trust Center lists SOC 2 Type 2, GDPR, CCPA but **no HIPAA/BAA mention retrievable** (page largely JS-rendered) | No numeric SLA; status page shows only scheduled maintenance, no uptime percentage published | Infrastructure runs on AWS per Trust Center; no specific region/residency guarantee found | **Deprecations**: zai-glm-4.6 (Jan 20), qwen-3-32b + llama-3.3-70b (Feb 16), disable_reasoning param (Mar 24), llama3.1-8b + qwen-3-235b-a22b (May 27), zai-glm-4.7 (Aug 17), **gemma-4-31b pulled from public endpoints (Sep 3)** — all 2026, all official [deprecation log] |
| Together AI | **None** — "does not currently offer free trials"; minimum $5 credit purchase required to use the API [official] | **Dynamic, per-organization** limits that scale with sustained traffic rather than fixed published tiers; visible via response headers; guaranteed capacity requires Dedicated Endpoints / Provisioned Throughput / Batch [official] | **Yes** — `response_format: json_schema` plus regex-constrained output; works with reasoning and vision models [official] | **Stores prompts/responses by default**; data sharing for training other models is opt-in, not default; **Zero Data Retention is self-serve opt-in** (Org Settings → "Store prompts and model responses" → No), not retroactive [official] | **No HIPAA mention found** in accessible security/privacy docs, despite a third-party trust-registry summary separately describing Together as "HIPAA Compliant" — treat that claim as unverified pending direct confirmation; Trust Center page was JS-rendered/inaccessible | No numeric SLA; per-model historical uptime 97–100%; Provisioned Throughput offers a throughput SLA with no disclosed percentage | Serverless endpoints have **no region selection**; VPC/regional (incl. EU) deployment only via Dedicated Endpoints [official] | Status page logged real 2026 outages: Gemma-4-31B-IT multiple outages Jun 13–20 (one 7h13m), MiniMax M3 scheduled maintenance ~3h Jul 1, Inkling Small extended downtime Aug 1–6 (17h5m on Aug 6), gpt-oss-120b incidents Sep 3–7 (one 2h+) [official status page] |
| Fireworks AI | **$1 free credit** at signup; specific rate-limit numbers/expiry not found [official] | **Adaptive**, tied to account Spending Tier + model size class: small (<400B params) ceiling 64.8M total prompt TPM, medium (400B–1.6T) 43.2M TPM, large (≥1.6T) 21.6M TPM; self-serve tier increases, sales contact for launch-time or above-max limits [official] | **Yes** — JSON mode (`response_format: json_schema`, most of JSON Schema 2020-12 incl. regex/composition) **and** a separate Grammar mode (custom BNF) [official] | **Zero data retention is the default for open-model inference** — "does not log or store prompt or generation data for any open models, without explicit user opt-in"; exception: Responses API stores by default when `store=True`, disableable [official] | **Yes** — "Fireworks is HIPAA compliant and supports healthcare and life sciences organizations"; "fully HIPAA, SOC2-Type II, and GDPR compliant"; exact plan tier for a signed BAA not specified; also SOC 2 Type II, ISO 27001/27701/42001 certified [official docs + blog] | No numeric SLA; Reserved Throughput plan references an undisclosed-percentage "throughput SLA"; status page showed no incidents at check time | "US-only Serverless" option exists for residency-sensitive customers (implying a non-US-only default also exists); full region list nf | Status page "fully operational" at check time; blog showed only release/funding news (DeepSeek V4 Pro, Kimi K3, Series D) — no 2026 outage or deprecation posts found |
| DeepInfra | **None** — "You have to add a card or pre-pay" before use; no free trial found [official] | Default **200 concurrent requests per model** (independent per model); effective RPM ranges ~12,000 (1s requests) down to ~200 (60s requests); self-serve increase via Dashboard [official] | **Yes** — `json_schema` mode with `strict: true` / `additionalProperties: false`, available across many models [official] | **Zero Data Retention is the contractual default** (Terms of Service §7(b)): no retention/storage/logging beyond the time needed to process and return the request, deleted "in the ordinary course of operations"; training on customer data prohibited by default except customer-initiated fine-tuning; ZDR clause explicitly overrides other DeepInfra policies [official ToS] | Privacy Notice: "security measures comply with SOC 2 and ISO 27001... include technical and organizational measures for GDPR and HIPAA compliance," but **no explicit statement of offering a signed BAA found**; dedicated /security and /enterprise pages 404'd — treat as unconfirmed | No numeric SLA; status page shows 99.10%–100% trailing-90-day uptime per model, explicitly no formal commitment | nf (subprocessors: Stripe, AWS, GCP; no region-residency documentation found) | Status page logged real 2026 outages: GLM-5.2 partial outages Jun 17–19 (up to ~6h combined), Gemma-4-31B-it-turbo outages Jul 7 (2h10m) and Jul 24–26 (8h1m + 6h19m), gpt-oss-120b partial outage Jul 24 (1h12m) [official status page] |
| SambaNova | No dollar credit; Free tier is rate-limit-gated (below) [official] | Free: 20 RPM / 20 RPD / 200,000 TPD, uniform across models. Developer (payment method linked): 60 RPM / 12,000 RPD most models (Meta Llama models 240 RPM / 48,000 RPD), 20M tokens/day account cap. Enterprise: custom via sales [official, page dateModified 2026-09-03] | **Yes** — `response_format: json_schema` (strict) and `json_object` both supported on chat completions; confirmed model list includes gpt-oss-120b, Qwen3-235B, Llama-3.3-70B, DeepSeek-V3.1/V3.2, MiniMax-M2.7 [official] | Not documented publicly for API prompts/outputs specifically; no ZDR option found; support directs specifics to privacy@sambanova.ai | **Not found publicly** — `/security`, `/trust`, `/compliance`, `/hipaa`, `/soc2` all 404'd; no BAA evidence located | No SLA published on status page | Primarily US; status page also references a "SambaCloud Japan" component, implying at least secondary APAC presence | **Live catalog is out of sync with SambaNova's own deprecation docs** — Llama-4-Maverick and Qwen3-32B are both marked deprecated (Jun 9 and Apr 6, 2026 respectively) yet still live-priced today; a documented, extensive 2026 deprecation cadence exists (Mar–Jun waves); this catalog/doc mismatch is itself a procurement-risk flag |
| Baseten | New accounts "come with credits," dollar amount undisclosed publicly [official] | Basic (unverified) 15 RPM/100,000 TPM; Basic (email-verified)/Pro 120 RPM/500,000 TPM; Enterprise custom; token-bucket replenishment, a separate 529 "Overloaded" response can occur even under rate limit [official] | **Yes** — tool calling, structured outputs, and JSON mode supported across all 15 catalog models [official] | **Zero data retention by default for synchronous inference** — inputs/outputs not stored by default; async inputs held only until processing; KV cache memory-only, discarded on replica restart [official] | **Yes** — SOC 2 Type II certified, HIPAA compliance announced, BAA available; compliance reports "available... upon request," suggesting a sales/negotiated process rather than pure self-serve | No explicit SLA percentage; status page tracks rolling-90-day uptime | `us`/`eu` region selection confirmed for **dedicated** deployments; unconfirmed whether the shared serverless Model APIs pool offers the same regional constraint | Three minor 2026 incidents on status page: Sep 9 (Nemotron Ultra partial outage, ~7 min), Aug 31 (elevated 500s in one US cluster, 24 min), Aug 27 (upstream-provider-caused errors, auto-recovered) |
| Nebius AI Studio / Token Factory | Dollar amount not found; elastic PAYG with dynamic rate-limit scaling (below), no explicit signup credit found | **Dynamic/elastic**: per-account baseline (e.g., docs' own example of 60 RPM/400,000 TPM) auto-scales +20%/15-min window when utilization ≥80%, up to 20× base; scales down ⅓ when utilization ≤50%; sustained higher need requires Enterprise tier (removes soft caps, adds dedicated capacity + SLA, sales-negotiated) [official] | **Yes** — `json_schema` (strict) and `json_object` both supported, flagged per-model via a "JSON mode" tag [official] | **Notable finding**: inputs/outputs are used **by default** for "speculative decoding" (training smaller draft models) unless Zero Data Retention is enabled; ZDR is an account-level toggle | **Yes, unusually well-documented** — Nebius will sign a BAA (sales/account-manager negotiated, not self-serve), but coverage is scoped **only to `/chat/completions` and `/completions` with ZDR enabled**; fine-tuning, batch inference, embeddings, and file/dataset storage are explicitly **excluded** from BAA scope — the most explicit, actionable HIPAA guidance found among all 16 providers, but also the most narrowly scoped | Self-service: **no formal SLA**, ~99.9% historical average success rate; contractual SLA only under sales-negotiated Enterprise tier | **Broadest region footprint found**: EU-NORTH1, EU-NORTH2, EU-WEST1, EU-WEST2, UK-SOUTH1, US-CENTRAL1, ME-WEST1 | Two formal deprecation waves: 2026-06-22 (11 models removed, incl. gpt-oss-120b-fast, GLM-5) and 2026-08-31 (10 more, incl. Qwen3-32B, Llama-3.3-70B, Qwen2.5-VL-72B), both with named replacements and "no automatic reroute" warnings; no major outages found |
| Novita | Dollar/token amount not found despite checking docs and pricing page | Five usage tiers (T1–T5) gated by trailing-3-calendar-month top-up total: T1 <$50/mo, T2 $50–500, T3 $500–3,000, T4 $3,000–10,000, T5 ≥$10,000; per-model RPM/TPM numbers render client-side and weren't extractable; above T5 requires Discord/sales contact [official] | **Yes** — `response_format: json_schema`, JSON-Schema-constrained, flagged per-model via a `structured-outputs` tag [official] | Privacy policy: personal information "will not be used for model training" by default; prompt/output-specific retention period not stated (only generic categories: account info 7yr, communications 3yr, technical data 2yr); no explicit ZDR toggle found | Not found — no HIPAA/BAA mention in the privacy policy; a "Trust Center" exists at trust.novita.ai but is fully JS-rendered/inaccessible; only a SOC 2 badge reference found | No formal SLA; status page shows component-level historical uptime (API Gateway ~100%, individual model endpoints 98.7%–99.95%) | Not clearly documented; privacy policy notes data may be transferred to "countries outside your country or region, including the United States" via SCCs — implies at least US processing | Multiple 2026 incidents: Sandbox Usage service outages/degradations (Jun 23, Jul 20, Jul 23, Aug 23, up to ~6h degraded); Kimi K3 multi-hour downtime events in August (Aug 3, 4, 20–21) |
| Hyperbolic | Inference itself is available on **free plans** with no stated dollar/expiry limit; only GPU-instance creation requires a one-time $5 deposit to unlock "Pro"; purchased compute credits are 1:1 with dollars and **never expire** [official] | Not found — no RPM/TPM documentation located for the inference API at all (docs corpus is GPU-rental-focused) | Not found — no JSON-schema/structured-output documentation located for the inference API | General platform encryption confirmed (TLS 1.2+, AES-256 at rest, per-instance isolation); no inference-specific prompt retention/training policy found; GDPR DPAs available on request with EU residency options mentioned generally | **Explicitly NOT HIPAA-certified** — Hyperbolic's own docs state: "Hyperbolic is not currently HIPAA-certified. Do not process Protected Health Information (PHI) on the platform without consulting our team first." Case-by-case BAAs possible for "qualified use cases," Enterprise/sales-only, no self-serve path; SOC 2 Type II described as "pursuing" (not yet certified) | No SLA found; public status page showed no incidents in the trailing 7 days but uptime widgets were unpopulated ("error while fetching the data") | GPU availability described as varying "by product, supply, region, and configuration" — no fixed inference-region list documented | None found in the trailing-7-day status window; weakest public-documentation posture of all 16 providers — its serverless "Model APIs" product is surfaced mainly through a client-rendered dashboard SPA that could not be scraped for pricing, rate limits, or structured-output support despite repeated attempts |
| Cloudflare Workers AI | **10,000 free "Neurons"/day on all plans**, no stated expiry, then $0.011/1,000 Neurons | Default 300 RPM (up to 1,500 RPM for some models); higher limits need a "Custom Requirements Form" | Yes ("JSON Mode"/`response_format`), but the documented supported-model list only names older Llama 3.x + 2 others — **not confirmed for gpt-oss/Llama 4/Qwen3/Gemma 4/Llama Guard 4**; no streaming with JSON mode; schema compliance "not guaranteed" in edge cases | Cloudflare states it does not use Customer Content to train models or improve services; no specific retention time-window stated; no separate ZDR option documented | BAA offered on **Enterprise plan only**, but **Workers AI is NOT listed among covered services** on Cloudflare's own HIPAA trust-hub page (AI Gateway is listed; Workers AI is not) — material gap | Not found (general SLA URL 404'd) | Global edge network by design; no US-only guarantee confirmed | One incident: "Workers AI increased errors," 2026-09-09 14:25–20:09 UTC, Minor, resolved |
| Hugging Face Inference Providers | Free: $0.10/mo credit; PRO: $2.00/mo; Team/Enterprise: $2.00/seat/mo (shared pool; also usable for Endpoints/Spaces/Jobs) | Not found (governed by whichever backend provider serves the model) | Yes — API spec documents `response_format: json_schema` (+ `strict`) and `json_object`, tools/grammars generally; per-provider enforcement fidelity not verified | Delegated to the routed backend provider's own policy — no single HF-wide retention/training statement found | No evidence found that HF itself offers a BAA for Inference Providers (separately, HF Enterprise Hub is reported elsewhere to include a general BAA, but that is not confirmed to extend to the Inference Providers routing product) | Not found | Depends on routed backend provider; not consolidated | Status page shows only scheduled maintenance in 2026 (100% measured API uptime over the reported window); no unplanned outage found |
| OpenRouter | No dollar credit; `:free`-tagged model variants capped at 20 RPM always, 50 requests/day on unfunded accounts or 1,000/day once $10+ lifetime credits purchased [official docs] | No platform-level RPM/TPM cap on paid models; limits governed per-key with automatic upstream failover [official docs] | **Yes** — `response_format: {type: "json_schema", ...}`, per-endpoint "strict" support varies by upstream, filterable via a `structured_outputs` supported-parameter flag [official docs] | **ZDR by default at the OpenRouter layer** (prompts not retained unless logging is opted in); per-upstream-provider policies vary and are tracked per endpoint; ZDR-only routing enforceable account-wide, per model group, or per request [official docs] | **Explicitly does NOT offer a HIPAA BAA** — no BAA, no published HIPAA/SOC2 coverage; compliance surface spans every upstream provider in the routing mesh | No formal SLA (no downtime credits); status page shows ~99.97–99.99% recent measured uptime | No first-party region guarantee — dynamic routing across whichever upstream serves a model; a "data residency" routing filter exists to constrain routing but is not a fixed OpenRouter region [official docs/blog] | No OpenRouter-specific incident history found beyond the live status page; as an aggregator, model deprecations/outages are upstream-provider events rather than OpenRouter's own |
| Google Vertex AI MaaS | Google Cloud's standard $300/90-day new-customer credit **explicitly excludes** "a generative AI partner model offered as MaaS" — i.e., does not cover open-weight MaaS token usage | Not found (model-specific QPM/TPM quotas not extracted; standard Cloud Console quota-increase mechanism applies) | Yes for MaaS generally (dedicated docs page confirmed to cover Qwen/DeepSeek MaaS models among others); full model-support list and exact syntax not fully retrieved | Not found — data-governance page did not yield a citable retention/training statement this session despite referencing "zero data retention" in its title | Google's HIPAA "Covered Products" list, as fetched, does **not name "Vertex AI"** — it lists "Generative AI on Gemini Enterprise Agent Platform" and other Gemini-branded items. **Whether third-party open-weight MaaS endpoints (gpt-oss, Llama, Qwen, Gemma, Llama Guard) are in scope of Google's BAA, vs. only Gemini-branded models, is unresolved** | Not found (SLA pages 404'd or exceeded fetch size across multiple attempts) | Not found for MaaS specifically | One incident: 2026-02-27, Vertex AI Gemini API global-endpoint elevated errors, ~2h, affected Gemini on Agent Platform; no MaaS/open-model-specific incident found |
| AWS Bedrock | No Bedrock-specific free-token allocation found (only generic AWS Free Tier sign-up messaging) | Three quota dimensions (RPM, TPM, Tokens-Per-Day), model- and region-specific, increasable via AWS Service Quotas console | **Yes at platform level** — constrained/grammar decoding via `outputConfig.textFormat`/`response_format`, JSON Schema Draft 2020-12 subset, `strict: true` tool calls, 24h grammar cache — **but explicitly marked "Not Supported" on the Llama 4 Scout model card specifically**, i.e., capability is model-specific | Does not store customer prompts/completions as standard operation; not used to train AWS models; not distributed to third parties; fine-tuning data deleted after job completion | **Yes — Amazon Bedrock and Bedrock AgentCore are explicitly HIPAA-eligible** under the standard AWS BAA (self-service via AWS Artifact); AWS's HIPAA-eligible-services reference states generally-available features of eligible services are HIPAA-eligible "unless specifically excluded," and no exclusion was found for open-weight serverless models specifically | **99.9% Monthly Uptime Percentage** commitment (10%/25%/100% service-credit tiers below 99.9%/99.0%/95.0%); SLA document itself last updated 2023-10-04, predating these specific models | Llama 4 Scout confirmed available only via US cross-region inference ("Geo (US)": us-east-1/2, us-west-1/2), not single-region endpoints | **Llama 4 Scout's Bedrock model card lists "EOL no sooner than: Apr 05, 2026"** — a live 2026 retirement-window flag for this exact model on this exact provider |
| Azure AI Foundry | Standard Azure 12-month free-service allowances + "65+ always-free services" exist at the account level; applicability to Foundry Models MaaS token usage specifically not confirmed | Not found (rate-limits doc URL attempted 404'd) | `response_format: json_schema` "Structured Outputs" is thoroughly documented, but the **official supported-model list is restricted entirely to Azure OpenAI models** (gpt-5.1, gpt-4.1, o3, o4-mini, etc.) — Llama/gpt-oss/Qwen/Gemma MaaS models are **not on this list** | For "Models sold by Azure" (confirmed to include Azure OpenAI): prompts/completions not shared with other customers or the model provider, not used to improve services, not used to train foundation models without explicit permission; ZDR-like "modified abuse monitoring" exists via approval. **Whether third-party open-weight MaaS models (billed via Azure Marketplace) fall under this same policy category, vs. a separate marketplace-terms category, was not conclusively confirmed** | Microsoft's HIPAA BAA is available by default via the Online Services DPA to covered entities/business associates for "in-scope Azure services," but the general HIPAA/HITECH page does not itself enumerate in-scope services by name, and Foundry-Models-MaaS-specific coverage (as distinct from Azure OpenAI) is **not publicly confirmed** — an unresolved, materially important gap per community threads | Azure OpenAI commonly cited at 99.9%, but "standard/serverless" deployments are described elsewhere as "best-effort" and "Developer deployments don't include an SLA"; the specific legal SLA URL attempted 404'd, so the precise current serverless-MaaS SLA wording is not confirmed | "Global," "DataZone" (e.g., all-US or all-EU), and standard regional deployment types exist for "Models sold by Azure" generally; not individually re-confirmed per target model | One broad West US regional network-connectivity outage, 2026-07-23 14:44–19:41 UTC (break-fix maintenance defect), which listed "Azure AI Speech in Foundry Tools" among many impacted services — infrastructure-wide, not AI-model-specific; no Azure open-model MaaS deprecation announcement found |

## 6. Per-scenario cost tables

Using the token volumes in §1. Providers chosen: the **three cheapest with a
confirmed BAA path** (Baseten, Groq, AWS Bedrock — see ranking note below) and the
**two cheapest overall regardless of BAA** (DeepInfra, Novita), compared against
the Gemini 3.5 Flash-Lite baseline.

**BAA-path ranking note:** Vertex AI MaaS's official gpt-oss-120b price
($0.09/$0.36) is the single cheapest number in this entire report, and Azure's
Llama 4 pricing is unknown — but both hyperscalers' HIPAA documentation leaves
**open-weight MaaS coverage specifically unconfirmed** (§3, §5b), so neither is
included in the "confirmed BAA-path" ranking below; they are shown separately as
a lower-confidence alternative. **Fireworks AI is tied with Groq at $0.15/$0.60**
for gpt-oss-120b and is independently confirmed HIPAA-compliant with a BAA
offering (its own docs state "fully HIPAA, SOC2-Type II, and GDPR compliant");
Groq is shown as the table representative of that price tier, with Fireworks
noted as an equally-priced, equally-BAA-confirmed alternative. **Together AI**,
despite also pricing gpt-oss-120b at $0.15/$0.60, is excluded from the
confirmed-BAA set: direct research into Together's own security/privacy
documentation found no HIPAA/BAA mention, despite a third-party trust-registry
summary calling it "HIPAA Compliant." **Nebius Token Factory** is also worth
flagging here: at a similar aggregator-sourced ~$0.15/$0.60, Nebius will sign a
BAA — but scoped narrowly to `/chat/completions`+`/completions` with Zero Data
Retention enabled (see §5b/§7/§8) — which would make it a fourth same-tier
BAA-documented option once its price is confirmed from an official source
rather than an aggregator.

### (a) Chat classification + reply — gpt-oss-120b

| Provider | BAA path | A (3,000 turns) | B (60,000 turns) | C (600,000 turns) |
|---|---|---|---|---|
| Baseten ($0.10/$0.50) | Yes (confirmed) | $1.04 | $20.70 | $207.00 |
| Groq ($0.15/$0.60) | Yes (confirmed, self-serve) | $1.41 | $28.26 | $282.60 |
| AWS Bedrock ($0.1545/$0.618, official) | Yes (confirmed) | $1.46 | $29.11 | $291.08 |
| DeepInfra ($0.037/$0.17) — cheapest overall | Not confirmed | $0.37 | $7.38 | $73.80 |
| Novita ($0.05/$0.25) — 2nd cheapest overall | No (explicit) | $0.52 | $10.35 | $103.50 |
| *Vertex AI MaaS ($0.09/$0.36, official)* — BAA scope for MaaS unconfirmed | Unresolved | *$0.85* | *$16.96* | *$169.56* |
| Gemini 3.5 Flash-Lite baseline ($0.30/$2.50) | Yes (Vertex AI, general) | $4.04 | $80.70 | $807.00 |

### (b) Safety classifier — Llama Guard 4 12B

Only one provider in scope has a confirmed, priced, pay-per-token endpoint for
this model: **DeepInfra** (also reachable via Hugging Face Inference Providers at
the same underlying host, with a cheaper "Flex" tier). Neither has a confirmed
BAA. No BAA-path provider in scope has a confirmed price for this model — Google
Vertex AI confirms the model is *available* but no rate-card price was found; AWS
Bedrock and Cloudflare confirm it is **not offered** at all. This is reported as a
genuine gap rather than estimated.

| Provider | BAA path | A (3,000 calls) | B (60,000 calls) | C (600,000 calls) |
|---|---|---|---|---|
| DeepInfra, standard tier ($0.18/$0.18) | Not confirmed | $0.28 | $5.51 | $55.08 |
| HF Inference Providers → DeepInfra, Flex tier ($0.144/$0.144) | Not confirmed (HF: no BAA evidence found) | $0.22 | $4.41 | $44.06 |
| HF Inference Providers → DeepInfra, Priority tier ($0.27/$0.27) | Not confirmed | $0.41 | $8.27 | $82.62 |
| *Vertex AI (available, price not found)* | Unresolved | n/c | n/c | n/c |
| AWS Bedrock / Cloudflare Workers AI | N/A — model not offered at all | — | — | — |
| Gemini 3.5 Flash-Lite baseline, used as classifier ($0.30/$2.50) | Yes (Vertex AI, general) | $0.53 | $10.50 | $105.00 |

### (c) Documents — gpt-oss-120b

| Provider | BAA path | A (600 docs) | B (3,000 docs) | C (30,000 docs) |
|---|---|---|---|---|
| Baseten ($0.10/$0.50) | Yes (confirmed) | $0.25 | $1.26 | $12.60 |
| Groq ($0.15/$0.60) | Yes (confirmed, self-serve) | $0.32 | $1.58 | $15.75 |
| AWS Bedrock ($0.1545/$0.618, official) | Yes (confirmed) | $0.32 | $1.62 | $16.22 |
| DeepInfra ($0.037/$0.17) — cheapest overall | Not confirmed | $0.09 | $0.43 | $4.35 |
| Novita ($0.05/$0.25) — 2nd cheapest overall | No (explicit) | $0.13 | $0.63 | $6.30 |
| *Vertex AI MaaS ($0.09/$0.36, official)* — BAA scope unresolved | Unresolved | *$0.19* | *$0.95* | *$9.45* |
| Gemini 3.5 Flash-Lite baseline ($0.30/$2.50) | Yes (Vertex AI, general) | $1.18 | $5.88 | $58.80 |

### Combined (a)+(b)+(c) — realistic "best available" total per month

Using each provider for (a)+(c), and DeepInfra standard-tier for (b) since it is
the only confirmed price (no other provider row can be added to (b) with a real
number):

| Combination | A | B | C |
|---|---|---|---|
| Baseten (a,c) + DeepInfra (b) | $1.56 | $27.47 | $274.68 |
| Groq (a,c) + DeepInfra (b) | $2.00 | $35.34 | $353.43 |
| AWS Bedrock (a,c) + DeepInfra (b) | $2.06 | $36.24 | $362.38 |
| DeepInfra (a,b,c) — single provider, cheapest, no BAA | $0.73 | $13.32 | $133.23 |
| Novita (a,c) + DeepInfra (b) | $0.92 | $16.49 | $164.88 |
| *Vertex AI MaaS (a,c) + DeepInfra (b)* — BAA unresolved | *$1.31* | *$23.41* | *$234.09* |
| **Gemini 3.5 Flash-Lite baseline (all three, one model)** | **$5.74** | **$97.08** | **$970.80** |

Even the most expensive confirmed-BAA combination in this table (AWS
Bedrock+DeepInfra) is roughly **2.7–2.8x cheaper than the Gemini baseline** at
every scenario size; the cheapest confirmed-BAA combination (Baseten+DeepInfra)
is roughly **3.5–3.7x cheaper**; and the cheapest overall combination (DeepInfra
alone, no confirmed BAA) is roughly **7.3–7.9x cheaper**.
These multiples exclude egress, embeddings, voice, SOAP-note, and
patient-explanation workloads, which were out of scope for this cost table per the
task instructions (only chat classification+reply, the safety classifier, and
documents were requested).

## 7. Per-provider notes and citations

**Groq** — model catalog and pricing (gpt-oss-120b $0.15/$0.60; gpt-oss-20b $0.075/$0.30; no Llama 4, Gemma, or Llama Guard 4 in catalog; Qwen only via expensive Preview SKUs qwen3.6-27b/qwen3.8-27b) confirmed via direct fetch of [console.groq.com/docs/models](https://console.groq.com/docs/models), seen 2026-09-10. Rate limits: [console.groq.com/docs/rate-limits](https://console.groq.com/docs/rate-limits); billing FAQ: [console.groq.com/docs/billing-faqs](https://console.groq.com/docs/billing-faqs). Structured outputs: [console.groq.com/docs/structured-outputs](https://console.groq.com/docs/structured-outputs). Legal/BAA/retention: [console.groq.com/docs/legal/services-agreement](https://console.groq.com/docs/legal/services-agreement) (Services Agreement §3.4 BAA commitment; ZDR for Eligible Customers) and the standalone [Business Associate Addendum](https://console.groq.com/docs/legal/customer-business-associate-addendum). Status/uptime: [groqstatus.com](https://groqstatus.com/). 2026 blog activity (funding/partnerships, no outages): [groq.com/blog](https://groq.com/blog). All seen 2026-09-10.

**Cerebras** — model catalog, pricing, and 2026 deprecation history confirmed via direct fetch of [inference-docs.cerebras.ai/models/overview](https://inference-docs.cerebras.ai/models/overview), [/models/openai-oss](https://inference-docs.cerebras.ai/models/openai-oss), [/models/qwen-3.8-27b](https://inference-docs.cerebras.ai/models/qwen-3.8-27b), and the [deprecation log](https://inference-docs.cerebras.ai/support/deprecation) (lists qwen-3-32b deprecated 2026-02-16 and gemma-4-31b pulled from public endpoints 2026-09-03). Rate limits and free-trial credit: [inference-docs.cerebras.ai/support/rate-limits](https://inference-docs.cerebras.ai/support/rate-limits) and [cerebras.ai/pricing](https://www.cerebras.ai/pricing). Structured outputs: [inference-docs.cerebras.ai/capabilities/structured-outputs](https://inference-docs.cerebras.ai/capabilities/structured-outputs). Privacy: [cerebras.ai/privacy-policy](https://www.cerebras.ai/privacy-policy). Trust Center (SOC 2/GDPR/CCPA, no HIPAA found): [trust.cerebras.ai](https://trust.cerebras.ai). Status: [status.cerebras.ai](https://status.cerebras.ai). All seen 2026-09-10.

**Together AI** — model catalog and pricing confirmed via direct fetch of [docs.together.ai/docs/serverless-models](https://docs.together.ai/docs/serverless-models), [together.ai/pricing](https://www.together.ai/pricing), and individual model pages: [gpt-oss-20b](https://together.ai/models/gpt-oss-20b), [llama-4-scout](https://together.ai/models/llama-4-scout), [llama-4-maverick](https://together.ai/models/llama-4-maverick), [gemma-4-31b](https://together.ai/models/gemma-4-31b) ("effective May 21, 2026"), [llama-guard-4-12b](https://together.ai/models/llama-guard-4-12b) (explicitly "not available on Together's Serverless API"), [qwen3-32b](https://together.ai/models/qwen3-32b) ("Launching soon"). Billing/free-tier: [docs.together.ai/docs/billing-credits](https://docs.together.ai/docs/billing-credits.md) (no free trial). Rate limits: [docs.together.ai/docs/serverless/rate-limits](https://docs.together.ai/docs/serverless/rate-limits.md). Structured output: [docs.together.ai/docs/json-mode](https://docs.together.ai/docs/json-mode). Privacy/ZDR: [docs.together.ai/docs/privacy-and-security](https://docs.together.ai/docs/privacy-and-security.md), [docs.together.ai/docs/zero-data-retention](https://docs.together.ai/docs/zero-data-retention.md) (no HIPAA mention found in either). Status/2026 incidents: [status.together.ai](https://status.together.ai). All seen 2026-09-10.

**Fireworks AI** — pricing (Standard/Priority tiers, cached-input rate) and model catalog confirmed via direct fetch of [docs.fireworks.ai/serverless/pricing](https://docs.fireworks.ai/serverless/pricing) and model pages [llama4-scout-instruct-basic](https://fireworks.ai/models/fireworks/llama4-scout-instruct-basic), [llama4-maverick-instruct-basic](https://fireworks.ai/models/fireworks/llama4-maverick-instruct-basic) (price not rendered), [qwen3-32b](https://fireworks.ai/models/fireworks/qwen3-32b) (price not rendered); Llama Guard 4 12B and MedGemma both 404 at expected slugs. Free credit: [fireworks.ai/pricing](https://fireworks.ai/pricing). Rate limits: [docs.fireworks.ai/serverless/rate-limits](https://docs.fireworks.ai/serverless/rate-limits.md). Structured output: [docs.fireworks.ai/structured-responses/structured-response-formatting](https://docs.fireworks.ai/structured-responses/structured-response-formatting). Data handling/ZDR-by-default: [docs.fireworks.ai/guides/security_compliance/data_handling](https://docs.fireworks.ai/guides/security_compliance/data_handling.md). HIPAA: [docs.fireworks.ai/guides/security_compliance/data_security](https://docs.fireworks.ai/guides/security_compliance/data_security.md), [fireworks.ai/enterprise](https://fireworks.ai/enterprise), [SOC 2 Type II + HIPAA announcement](https://fireworks.ai/blog/fireworks-ai-achieves-soc-2-type-ii-and-hipaa-compliance). Reserved Throughput SLA language: [docs.fireworks.ai/serverless/reserved-throughput](https://docs.fireworks.ai/serverless/reserved-throughput.md). Status/blog: [status.fireworks.ai](https://status.fireworks.ai), [fireworks.ai/blog](https://fireworks.ai/blog). All seen 2026-09-10.

**DeepInfra** — pricing confirmed via direct fetch of [deepinfra.com/openai/gpt-oss-120b](https://deepinfra.com/openai/gpt-oss-120b), [deepinfra.com/openai/gpt-oss-20b](https://deepinfra.com/openai/gpt-oss-20b), [deepinfra.com/pricing](https://deepinfra.com/pricing) (Llama 4 Scout/Maverick, Gemma 3/4 family), [deepinfra.com/Qwen/Qwen3-32B](https://deepinfra.com/Qwen/Qwen3-32B) (Standard/Priority/Flex tiers), and [deepinfra.com/meta-llama/Llama-Guard-4-12B](https://deepinfra.com/meta-llama/Llama-Guard-4-12B) (Standard/Priority/Flex), cross-checked against Hugging Face's own provider-mapping API. MedGemma and Baichuan-M2 both 404. Rate limits: [docs.deepinfra.com/account/rate-limits](https://docs.deepinfra.com/account/rate-limits.md). Structured output: [docs.deepinfra.com/chat/structured-outputs](https://docs.deepinfra.com/chat/structured-outputs). Terms (contractual ZDR default, §7(b)): [deepinfra.com/terms](https://deepinfra.com/terms). Privacy: [deepinfra.com/privacy](https://deepinfra.com/privacy). Subprocessors: [docs.deepinfra.com/account/subprocessors](https://docs.deepinfra.com/account/subprocessors.md). Status/2026 incidents: [status.deepinfra.com](https://status.deepinfra.com). All seen 2026-09-10.

**SambaNova** — pricing and full 20-model catalog confirmed via SambaNova's own live pricing API, [cloud.sambanova.ai/api/pricing](https://cloud.sambanova.ai/api/pricing), cross-checked against the rendered [cloud.sambanova.ai/pricing](https://cloud.sambanova.ai/pricing) page. Deprecation history (and the live-catalog/docs inconsistency for Llama-4-Maverick and Qwen3-32B): [docs.sambanova.ai/docs/en/models/deprecations](https://docs.sambanova.ai/docs/en/models/deprecations). Rate limits: [docs.sambanova.ai/docs/en/models/rate-limits](https://docs.sambanova.ai/docs/en/models/rate-limits) (page dateModified 2026-09-03). Structured output: [docs.sambanova.ai/docs/en/features/function-calling](https://docs.sambanova.ai/docs/en/features/function-calling). Privacy: [sambanova.ai/privacy-policy](https://sambanova.ai/privacy-policy). HIPAA/security/trust pages (`/security`, `/trust`, `/compliance`, `/hipaa`, `/soc2`) all 404'd. Status: [status.sambanova.ai](https://status.sambanova.ai). All seen 2026-09-10.

**Baseten** — full Model APIs catalog (15 models total) and pricing confirmed via direct fetch of [baseten.co/pricing](https://www.baseten.co/pricing/) and [docs.baseten.co/development/model-apis/overview](https://docs.baseten.co/development/model-apis/overview). Rate limits: [docs.baseten.co/inference/model-apis/pricing-and-limits](https://docs.baseten.co/inference/model-apis/pricing-and-limits). Retention/security: [docs.baseten.co/observability/security](https://docs.baseten.co/observability/security.md). HIPAA: [Baseten HIPAA compliance announcement](https://www.baseten.co/blog/baseten-announces-hipaa-compliance/). Region (dedicated deployments): [docs.baseten.co/deployment/regional-deployments](https://docs.baseten.co/deployment/regional-deployments.md). Status: [status.baseten.co](https://status.baseten.co). All seen 2026-09-10.

**Nebius AI Studio / Token Factory** — now rebranded; docs moved to [docs.tokenfactory.nebius.com](https://docs.tokenfactory.nebius.com). Pricing remains aggregator-sourced ([Requesty](https://www.requesty.ai/models/nebius), [Artificial Analysis](https://artificialanalysis.ai/providers/nebius)) since the official dashboard requires login. Qwen3-32B removal and Gemma-4-for-fine-tuning-only: [august-2026-deprecation-notice](https://docs.tokenfactory.nebius.com/august-2026-deprecation-notice), [post-training/models](https://docs.tokenfactory.nebius.com/post-training/models). Rate limits: [ai-models-inference/rate-limits](https://docs.tokenfactory.nebius.com/ai-models-inference/rate-limits). Structured output: [ai-models-inference/json](https://docs.tokenfactory.nebius.com/ai-models-inference/json). Retention/training default and HIPAA scope: [legal/privacy-policy](https://docs.tokenfactory.nebius.com/legal/privacy-policy), [legal/hipaa-guideline](https://docs.tokenfactory.nebius.com/legal/hipaa-guideline) (BAA scoped to `/chat/completions` + `/completions` with ZDR only). SLA: [dedicated-endpoints/capacity-and-scaling](https://docs.tokenfactory.nebius.com/ai-models-inference/dedicated-endpoints/capacity-and-scaling). Region footprint and status: [status.nebius.com](https://status.nebius.com). Earlier June deprecation wave: [june-2026-deprecation-notice](https://docs.tokenfactory.nebius.com/june-2026-deprecation-notice). All seen 2026-09-10.

**Novita** — pricing and full 117-model catalog confirmed via Novita's own live model API, [api.novita.ai/v3/openai/models](https://api.novita.ai/v3/openai/models), seen 2026-09-10 (this supersedes the earlier OpenRouter-aggregator-sourced figures with an official direct source, which happened to match). Rate-limit tiers: [docs.novita.ai/guides/llm-rate-limits](https://docs.novita.ai/guides/llm-rate-limits). Structured output: [docs.novita.ai/guides/llm-structured-outputs](https://docs.novita.ai/guides/llm-structured-outputs). Privacy/HIPAA: [novita.ai/legal/privacy-policy](https://novita.ai/legal/privacy-policy) (explicitly not tailored for HIPAA/FISMA); Trust Center at [trust.novita.ai](https://trust.novita.ai) is JS-rendered/inaccessible. Status: [status.novita.ai](https://status.novita.ai). All seen 2026-09-10.

**Hyperbolic** — confirmed as one of the providers offering gpt-oss-120b via a live model-card URL, `app.hyperbolic.ai/models/gpt-oss-120b`; exact pricing could not be extracted from the client-rendered SPA dashboard, Hyperbolic's own docs (which are GPU-rental-focused: [hyperbolic.ai/docs/on-demand/pricing](https://www.hyperbolic.ai/docs/on-demand/pricing)), or any third-party aggregator checked. Billing (free inference, $5 unlocks Pro/GPU, non-expiring credits): [hyperbolic.ai/docs/general/billing-payments](https://www.hyperbolic.ai/docs/general/billing-payments). Explicit non-HIPAA-certified statement and case-by-case BAA: [hyperbolic.ai/docs/general/security-compliance](https://www.hyperbolic.ai/docs/general/security-compliance). Status: [status.hyperbolic.ai](https://status.hyperbolic.ai). All seen 2026-09-10.

**OpenRouter** (expanded) — full-catalog absence check for MedGemma/Baichuan-M2 and free-tier mechanics via the live [openrouter.ai/api/v1/models](https://openrouter.ai/api/v1/models) catalog and [openrouter.ai/docs/api_reference/limits](https://openrouter.ai/docs/api_reference/limits). Structured outputs: [openrouter.ai/docs/features/structured-outputs](https://openrouter.ai/docs/features/structured-outputs). Status/uptime: [status.openrouter.ai](https://status.openrouter.ai/). Region-routing filter: [openrouter.ai/blog/insights/ai-data-residency](https://openrouter.ai/blog/insights/ai-data-residency/). All seen 2026-09-10.

**Cloudflare Workers AI** — full pricing, limits, JSON-mode, privacy, HIPAA, and incident detail from direct fetches of [developers.cloudflare.com/workers-ai/platform/pricing/](https://developers.cloudflare.com/workers-ai/platform/pricing/) (page states "Last Updated: August 28, 2026"), [/models/](https://developers.cloudflare.com/workers-ai/models/), [/platform/limits/](https://developers.cloudflare.com/workers-ai/platform/limits/) (Aug 7, 2026), [/features/json-mode/](https://developers.cloudflare.com/workers-ai/features/json-mode/) (Apr 21, 2026), [/privacy/](https://developers.cloudflare.com/workers-ai/privacy/) (Apr 21, 2026), [cloudflare.com/trust-hub HIPAA page](https://www.cloudflare.com/trust-hub/compliance-resources/hipaa/), and [cloudflarestatus.com/history](https://www.cloudflarestatus.com/history), all seen 2026-09-10.

**Hugging Face Inference Providers** — pricing/credits from [huggingface.co/docs/inference-providers/pricing](https://huggingface.co/docs/inference-providers/pricing); model-availability facts (gpt-oss-120b's 11 upstreams, Llama Guard 4 12B's DeepInfra tiers, MedGemma's empty mapping, Baichuan-M2's Featherless mapping) from Hugging Face's own `inferenceProviderMapping` API queried directly per model, e.g. `huggingface.co/api/models/openai/gpt-oss-120b?expand[]=inferenceProviderMapping`; structured-output spec from [chat-completion task docs](https://huggingface.co/docs/inference-providers/tasks/chat-completion); uptime from [status.huggingface.co](https://status.huggingface.co/); all seen 2026-09-10.

**OpenRouter** — endpoint pricing snapshots from the public `openrouter.ai/api/v1/models/{id}/endpoints` API, seen 2026-09-10 (used throughout §4). ZDR routing control: [openrouter.ai/docs/guides/features/zdr](https://openrouter.ai/docs/guides/features/zdr). No-BAA finding: third-party HealthTech engineering write-up ["I Passed OpenRouter's Verify But Can't Use My Model"](https://dredyson.com/i-passed-openrouters-verify-but-cant-use-my-model-a-hipaa-compliant-healthtech-engineers-guide/), seen 2026-09-10.

**Google Vertex AI MaaS** — gpt-oss-120b $0.09/$0.36 confirmed official and GA via [docs.cloud.google.com/gemini-enterprise-agent-platform/models/maas/openai/gpt-oss-120b](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/maas/openai/gpt-oss-120b) and cross-checked against a [Google Developer forum GA announcement thread](https://discuss.google.dev/t/now-ga-openais-gpt-oss-qwen3-models-on-vertex-ai-as-open-model-apis/253945), seen 2026-09-10. Llama 4 GA-on-Vertex announcement: [developers.googleblog.com/en/llama-4-ga-maas-vertex-ai](https://developers.googleblog.com/en/llama-4-ga-maas-vertex-ai/). Serving-option split (MaaS vs. dedicated) from [docs.cloud.google.com/vertex-ai/generative-ai/docs/open-models/choose-serving-option](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/open-models/choose-serving-option). MedGemma dedicated-endpoint framing: [developers.google.com/health-ai-developer-foundations/medgemma/get-started](https://developers.google.com/health-ai-developer-foundations/medgemma/get-started) (updated 2026-06-05). Free-credit MaaS exclusion: [docs.cloud.google.com/free/docs/free-cloud-features](https://docs.cloud.google.com/free/docs/free-cloud-features) ("Last Updated: September 3, 2026"). HIPAA covered-products list: [cloud.google.com/security/compliance/hipaa](https://cloud.google.com/security/compliance/hipaa) (shows last-updated 2026-08-28). Incident: [status.cloud.google.com/summary](https://status.cloud.google.com/summary). Llama Guard 4 12B availability: [GoogleCloudPlatform/vertex-ai-samples Llama Guard deployment notebook](https://github.com/GoogleCloudPlatform/vertex-ai-samples/blob/main/notebooks/community/model_garden/model_garden_llama_guard_deployment.ipynb). All seen 2026-09-10.

**AWS Bedrock** — model-card catalog: [docs.aws.amazon.com/bedrock/latest/userguide/model-cards.html](https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards.html). Pricing table (gpt-oss-120b $0.1545/$0.618, gpt-oss-20b $0.0721/$0.309, Qwen3-32B $0.1545/$0.618 [flagged as needing re-verification — identical to gpt-oss-120b], Gemma 4 31B US East $0.14/$0.40, Gemma 3 27B/12B/4B): [aws.amazon.com/bedrock/pricing/](https://aws.amazon.com/bedrock/pricing/), seen 2026-09-10. Rate-limit dimensions: [quotas-runtime.html](https://docs.aws.amazon.com/bedrock/latest/userguide/quotas-runtime.html). Structured output: [structured-output.html](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html); Llama 4 Scout exclusion confirmed on its own [model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-4-scout-17b-instruct.html), which also carries the "EOL no sooner than Apr 05, 2026" flag and the US-cross-region-only availability note. Privacy: [aws.amazon.com/bedrock/amazon-models/privacy/](https://aws.amazon.com/bedrock/amazon-models/privacy/). HIPAA: [aws.amazon.com/compliance/hipaa-eligible-services-reference/](https://aws.amazon.com/compliance/hipaa-eligible-services-reference/) (page last updated September 3, 2026). SLA: [aws.amazon.com/bedrock/sla/](https://aws.amazon.com/bedrock/sla/) (legal doc dated 2023-10-04). All seen 2026-09-10.

**Azure AI Foundry** — Llama 4 availability: [Microsoft Tech Community blog](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/expanding-the-llama-4-herd-new-models-now-available-on-azure-ai-foundry/4403609), [azure.microsoft.com/en-us/products/ai-foundry/models/](https://azure.microsoft.com/en-us/products/ai-foundry/models/). Pricing placeholder: [azure.microsoft.com/en-us/pricing/details/ai-foundry-models/llama/](https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/llama/) ("Prices are estimates only..."). Free services: [azure.microsoft.com/en-us/pricing/free-services/](https://azure.microsoft.com/en-us/pricing/free-services/). Structured outputs restricted to Azure OpenAI models: [learn.microsoft.com/.../structured-outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs) (dated 2026-08-24). Data privacy for "Models sold by Azure": [learn.microsoft.com/.../data-privacy](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy) (dated 2026-05-18). HIPAA BAA general offering: [learn.microsoft.com/.../offering-hipaa-us](https://learn.microsoft.com/en-us/azure/compliance/offerings/offering-hipaa-us) and the general [offering-hipaa-hitech](https://learn.microsoft.com/en-us/compliance/regulatory/offering-hipaa-hitech) page (updated_at 2026-06-02) confirmed directly in this session — neither page names "Azure AI Foundry" or "Foundry Models MaaS" among in-scope services, only pointing to a separate, non-public "Cloud services in audit scope" document. Incident: [azure.status.microsoft/en-us/status/history/](https://azure.status.microsoft/en-us/status/history/). All seen 2026-09-10.

## 8. Confidence and gaps

- **All three parallel deep-research passes originally launched ultimately
  returned and are fully integrated**: the hyperscaler pass (Cloudflare, Hugging
  Face, Vertex AI, Bedrock, Azure), the Groq/Cerebras/Together/Fireworks/
  DeepInfra pass, and the OpenRouter/SambaNova/Baseten/Nebius/Novita/Hyperbolic
  pass. All three relied heavily on direct official-page or live-API fetches
  (console.groq.com, inference-docs.cerebras.ai, docs.together.ai,
  docs.fireworks.ai, deepinfra.com, cloud.sambanova.ai/api/pricing,
  api.novita.ai/v3/openai/models, openrouter.ai's public endpoints/models APIs,
  docs.baseten.co, docs.tokenfactory.nebius.com, plus each provider's status
  page) rather than third-party trackers, and each correction they produced
  relative to this session's own initial direct research is called out inline
  in §5/§7 (e.g., the Together AI BAA downgrade, the Cerebras Gemma-4
  removed-from-public-endpoints finding, SambaNova's live-catalog/deprecation-doc
  mismatch, Nebius's narrowly-scoped-but-detailed BAA terms, Baseten's
  surprisingly narrow 15-model catalog, and Novita's official-API price
  confirmation). **The one provider where pricing and policy remain almost
  entirely unconfirmed despite genuine effort across two independent research
  passes is Hyperbolic** — its serverless "Model APIs" product is exposed only
  through a client-rendered dashboard SPA with no scrapeable pricing, rate-limit,
  or structured-output documentation; its own docs are otherwise focused
  entirely on GPU rental. Hyperbolic should not be treated as a viable candidate
  for a cost or compliance decision without a manual, logged-in dashboard check.
- **Google Vertex AI and Azure AI Foundry HIPAA scope for open-weight MaaS models
  is the most consequential unresolved question in this report.** Both
  hyperscalers have account-level BAAs, and both have official documentation that
  stops short of explicitly naming "Vertex AI Model Garden MaaS" or "Azure AI
  Foundry Models-as-a-Service (open-weight)" among BAA-covered/HIPAA-eligible
  services — as distinct from first-party Gemini and Azure OpenAI models, which
  are explicitly named. This should be confirmed directly with each vendor's
  compliance/sales team, not assumed either way, before routing PHI through
  either platform's open-weight MaaS endpoints.
- **AWS Bedrock's official pricing table shows the exact same rate
  ($0.1545/$0.618 per 1M) for both gpt-oss-120b and Qwen3-32B**, which is
  plausible (a shared pricing tier by parameter-count band) but was not
  independently confirmed — worth re-checking against the live AWS pricing page
  before relying on the Qwen3-32B figure specifically. The gpt-oss-120b/-20b
  figures were shown in an Asia Pacific (Sydney) column; the US-region on-demand
  rate was not independently re-confirmed as identical (AWS Bedrock on-demand
  pricing is often, but not always, uniform across commercial regions for a given
  model).
- **Llama Guard 4 12B pricing is confirmed for exactly one underlying host
  (DeepInfra) among 16 providers researched**, reachable directly or via Hugging
  Face's pass-through routing. This is reported as a genuine market-availability
  finding, not a research shortfall — Bedrock and Cloudflare explicitly do not
  carry the model at all, and Vertex AI's Model Garden entry has no published
  rate card. If MediAgent needs a BAA-covered safety classifier today, the
  practical options are: (1) accept DeepInfra without a confirmed BAA (fine for
  synthetic data, not for real PHI), (2) ask Google/AWS/Azure sales whether
  Llama Guard 4 12B pricing and BAA coverage can be confirmed contractually, or
  (3) substitute a differently-licensed safety check running on an
  already-BAA-confirmed provider (e.g., a prompt-based classifier on gpt-oss-20b
  via Groq or Bedrock).
- **MedGemma 1.5 4B and Baichuan-M2 32B are confirmed to have essentially no
  serverless, token-priced, multi-provider market** — MedGemma has zero Inference
  Providers on Hugging Face and is Vertex-Model-Garden-dedicated-only; Baichuan-M2
  is priced by exactly one provider in scope (Novita) plus one HF-routed,
  non-per-token option (Featherless). Neither should be assumed available
  elsewhere without a fresh check.
- **Gemma 4 pricing is confirmed, from official pages, on only 4 of 16
  providers** (DeepInfra, Cloudflare, Together, AWS Bedrock); Cerebras briefly
  had it but pulled it from public serverless on 2026-09-03; most others in
  scope still price Gemma 3 SKUs as their newest Gemma offering as of this
  report's research date. **Qwen 3.6-generation ("32B-class")** availability is
  fragmented and inconsistently priced across providers that do offer a "32B
  Qwen": Groq only has expensive Preview-tier qwen3.6-27b/qwen3.8-27b
  ($0.60–0.80/$3.00–4.00), Cerebras has qwen-3.8-27b ($0.99/$1.49) after
  deprecating qwen-3-32b, Together's Qwen3-32B is "Launching soon" (not live),
  and DeepInfra's Qwen3-32B ($0.08/$0.28) is actually the older dense
  (non-3.6-generation) model — no provider in scope was confirmed to serve the
  true Qwen3.6-35B-A3B MoE model directly (only via OpenRouter aggregator
  upstreams in §4).
- **Together AI's HIPAA/BAA claim did not hold up under direct research**: a
  third-party trust-registry summary described it as "HIPAA Compliant," but a
  direct fetch of Together's own security/privacy/ZDR documentation found no
  HIPAA or BAA mention at all. **Fireworks AI's claim is well-supported** by its
  own docs and blog ("fully HIPAA, SOC2-Type II, and GDPR compliant"), though the
  exact plan tier for obtaining a signed BAA is still unspecified. **Nebius's**
  HIPAA story is unusually well-documented but narrow: Nebius will sign a
  sales-negotiated BAA, but its own HIPAA guideline explicitly scopes coverage to
  only the `/chat/completions` and `/completions` endpoints with Zero Data
  Retention enabled, excluding fine-tuning, batch inference, embeddings, and file
  storage — a materially different (and more specific/actionable) picture than
  this report's own earlier, more general finding that Nebius's broader AI Cloud
  product cannot process PHI at all; treat the HIPAA-guideline-specific,
  narrowly-scoped answer as authoritative for the Token Factory serverless
  inference product covered in this report. **SambaNova** has no HIPAA/BAA
  evidence at all (every compliance-related URL attempted 404'd), and its live
  model catalog was separately found to be **out of sync with its own
  deprecation documentation** (two models still live-priced despite being
  marked deprecated) — a procurement-risk signal independent of the HIPAA
  question. **Hyperbolic explicitly states it is not HIPAA-certified** and
  offers BAAs only case-by-case to Enterprise customers via direct sales.
- **Structured-output (JSON-schema) support is now confirmed from official
  documentation for 13 of 16 providers**: Groq (strict constrained decoding,
  named-model list), Cerebras (`strict: true`, named-model list), Together AI,
  Fireworks AI (JSON mode + separate BNF grammar mode), DeepInfra, SambaNova,
  Baseten, Nebius Token Factory, Novita, OpenRouter (per-endpoint "strict"
  support varies by upstream), Cloudflare Workers AI (model-list caveat —
  gpt-oss/Llama4/Qwen3/Gemma4/Llama-Guard-4 not confirmed compatible), Hugging
  Face (API-level, per-provider fidelity unverified), and AWS Bedrock
  (platform-level, but explicitly unsupported on the Llama 4 Scout model
  specifically). Azure AI Foundry's documented support is restricted entirely to
  Azure OpenAI models — MaaS open-weight models are excluded from its supported
  list. **Only Hyperbolic (no inference-API documentation of any kind was found)
  and Vertex AI MaaS (partially confirmed — a docs page exists but the full
  per-model support list wasn't fully retrieved) remain genuinely
  unconfirmed.**
- **A numeric, contractual uptime SLA is confirmed for exactly one provider in
  this entire report: AWS Bedrock (99.9% Monthly Uptime Percentage)**, plus a
  vaguer "throughput SLA" (no percentage disclosed) for Fireworks AI's Reserved
  Throughput plan and Nebius's sales-negotiated Enterprise tier. Every other
  provider — Groq, Cerebras, Together, DeepInfra, SambaNova, Baseten, Nebius
  self-serve, Novita, Hyperbolic, OpenRouter, Cloudflare, Hugging Face, Vertex AI
  MaaS, and (for MaaS specifically) Azure — has **no confirmed numeric SLA**;
  several instead publish historical/measured uptime percentages on a status
  page, which is not a contractual guarantee. Region/residency detail is
  similarly uneven: **Nebius Token Factory has by far the broadest confirmed
  footprint** (7 named regions across EU/UK/US/Middle East), Fireworks AI offers
  a "US-only Serverless" option for residency-sensitive customers, AWS Bedrock's
  Llama 4 Scout is US-cross-region-only (no single-region option), and most
  other providers (Groq, Cerebras, Together serverless, DeepInfra, SambaNova,
  Baseten's shared Model APIs, Novita, Hyperbolic, OpenRouter, Cloudflare) either
  have no documented region-selection feature or the report could not confirm
  one.
- **2026 outage and model-retirement history turned out to be richly
  documented once each provider's own status/deprecation pages were fetched
  directly** — this is one of the strongest evidence bases in the report, not a
  gap: Cerebras (qwen-3-32b deprecated Feb 16; gemma-4-31b pulled from public
  endpoints Sep 3 — one week before this report), Together AI (several
  multi-hour 2026 outages, including a 7h13m Gemma-4-31B-IT outage and a 17h5m
  outage on another model), DeepInfra (multiple outages including 8h+ on a
  Gemma-4-31B-it-turbo endpoint), SambaNova (an extensive, well-documented 2026
  deprecation cadence — but one where the **live pricing catalog is confirmed
  out of sync with SambaNova's own deprecation docs**, a procurement-risk flag
  in itself), Nebius (two formal deprecation waves with named replacements),
  Novita (several multi-hour incidents on specific model endpoints), Baseten
  (three minor, quickly-resolved incidents), Cloudflare (one minor Sep 9
  incident), Google Cloud (one Feb 27 incident), Azure (one Jul 23 regional
  incident), and AWS Bedrock (Llama 4 Scout's own model card flags an EOL window
  "no sooner than Apr 05, 2026"). Only **Groq, OpenRouter, and Hyperbolic** show
  a clean/unremarkable 2026 status-page history in this research — for Groq and
  OpenRouter this is a positive signal from an actual live status-page check;
  for Hyperbolic it more likely reflects the provider's generally thin public
  documentation (§ above) than a genuinely clean track record.
- All dollar figures are current **on-demand/pay-as-you-go list prices as of
  2026-09-10** and exclude any volume discounts, committed-throughput/provisioned
  pricing, prompt-caching discounts (noted separately for Groq), or batch-API
  discounts (also noted for Groq) that could lower real-world spend further.

## Sources

Grouped by section; every URL was accessed 2026-09-10 unless a different
"page states"/"last updated" date is called out in §7.

**Baseline & model facts:** [OpenAI gpt-oss model card](https://openai.com/index/gpt-oss-model-card/) · [OpenAI Help Center: open-weight models](https://help.openai.com/en/articles/11870455-openai-open-weight-models-gpt-oss) · [CloudZero: Vertex AI pricing 2026](https://www.cloudzero.com/blog/google-vertex-ai-pricing/) · [Requesty: gemini-3.5-flash-lite](https://www.requesty.ai/models/vertex/gemini-3.5-flash-lite) · [BenchLM: Gemini pricing Sept 2026](https://benchlm.ai/google/api-pricing) · [BuildFastWithAI: Qwen3.6-Max-Preview](https://www.buildfastwithai.com/blogs/qwen3-6-max-preview-review-2026) · [AIMLAPI: Qwen 3.6 series](https://aimlapi.com/blog/qwen-3-6-series-alibabas-open-source-llm-revolution-in-2026) · [Yotta Labs: Qwen 3.7 vs 3.6](https://www.yottalabs.ai/post/qwen-3-7-vs-qwen-3-6-what-actually-exists-and-what-to-use-in-production) · [Google Cloud blog: Gemma 4](https://cloud.google.com/blog/products/ai-machine-learning/gemma-4-available-on-google-cloud) · [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4) · [Google Research: MedGemma 1.5/MedASR](https://research.google/blog/next-generation-medical-image-interpretation-with-medgemma-15-and-medical-speech-to-text-with-medasr/) · [MedGemma 1.5 4B, Hugging Face](https://huggingface.co/google/medgemma-1.5-4b-it).

**OpenRouter aggregator cross-checks:** `openrouter.ai/api/v1/models/{id}/endpoints` for `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `meta-llama/llama-guard-4-12b`, `meta-llama/llama-4-scout`, `meta-llama/llama-4-maverick`, `qwen/qwen3-32b`, `qwen/qwen3.6-35b-a3b`, `google/gemma-3-27b-it`.

**Groq:** [console.groq.com/docs/models](https://console.groq.com/docs/models) · [Rate limits](https://console.groq.com/docs/rate-limits) · [Billing FAQ](https://console.groq.com/docs/billing-faqs) · [Structured outputs](https://console.groq.com/docs/structured-outputs) · [Services Agreement](https://console.groq.com/docs/legal/services-agreement) · [Business Associate Addendum](https://console.groq.com/docs/legal/customer-business-associate-addendum) · [Status](https://groqstatus.com/) · [Blog](https://groq.com/blog).

**Cerebras:** [Models overview](https://inference-docs.cerebras.ai/models/overview) · [gpt-oss pricing](https://inference-docs.cerebras.ai/models/openai-oss) · [qwen-3.8-27b](https://inference-docs.cerebras.ai/models/qwen-3.8-27b) · [Deprecation log](https://inference-docs.cerebras.ai/support/deprecation) · [Rate limits](https://inference-docs.cerebras.ai/support/rate-limits) · [Structured outputs](https://inference-docs.cerebras.ai/capabilities/structured-outputs) · [Pricing/free trial](https://www.cerebras.ai/pricing) · [Privacy policy](https://www.cerebras.ai/privacy-policy) · [Trust Center](https://trust.cerebras.ai) · [Status](https://status.cerebras.ai).

**Together AI:** [Serverless models](https://docs.together.ai/docs/serverless-models) · [Pricing](https://www.together.ai/pricing) · Model pages: [gpt-oss-20b](https://together.ai/models/gpt-oss-20b) · [Llama-4-Scout](https://together.ai/models/llama-4-scout) · [Llama-4-Maverick](https://together.ai/models/llama-4-maverick) · [Gemma-4-31b](https://together.ai/models/gemma-4-31b) · [Llama-Guard-4-12b](https://together.ai/models/llama-guard-4-12b) · [Qwen3-32B](https://together.ai/models/qwen3-32b) · [Billing/credits](https://docs.together.ai/docs/billing-credits.md) · [Rate limits](https://docs.together.ai/docs/serverless/rate-limits.md) · [JSON mode](https://docs.together.ai/docs/json-mode) · [Privacy/security](https://docs.together.ai/docs/privacy-and-security.md) · [Zero data retention](https://docs.together.ai/docs/zero-data-retention.md) · [Status](https://status.together.ai).

**Fireworks AI:** [Serverless pricing](https://docs.fireworks.ai/serverless/pricing) · Model pages: [llama4-scout-instruct-basic](https://fireworks.ai/models/fireworks/llama4-scout-instruct-basic) · [llama4-maverick-instruct-basic](https://fireworks.ai/models/fireworks/llama4-maverick-instruct-basic) · [qwen3-32b](https://fireworks.ai/models/fireworks/qwen3-32b) · [Pricing/free credit](https://fireworks.ai/pricing) · [Rate limits](https://docs.fireworks.ai/serverless/rate-limits.md) · [Structured response formatting](https://docs.fireworks.ai/structured-responses/structured-response-formatting) · [Data handling](https://docs.fireworks.ai/guides/security_compliance/data_handling.md) · [Data security/HIPAA](https://docs.fireworks.ai/guides/security_compliance/data_security.md) · [Enterprise](https://fireworks.ai/enterprise) · [SOC 2 Type II + HIPAA announcement](https://fireworks.ai/blog/fireworks-ai-achieves-soc-2-type-ii-and-hipaa-compliance) · [Reserved throughput](https://docs.fireworks.ai/serverless/reserved-throughput.md) · [Status](https://status.fireworks.ai) · [Blog](https://fireworks.ai/blog).

**DeepInfra:** [gpt-oss-120b](https://deepinfra.com/openai/gpt-oss-120b) · [gpt-oss-20b](https://deepinfra.com/openai/gpt-oss-20b) · [Pricing](https://deepinfra.com/pricing) · [Qwen3-32B](https://deepinfra.com/Qwen/Qwen3-32B) · [Llama-Guard-4-12B](https://deepinfra.com/meta-llama/Llama-Guard-4-12B) · [Rate limits](https://docs.deepinfra.com/account/rate-limits.md) · [Structured outputs](https://docs.deepinfra.com/chat/structured-outputs) · [Terms (ZDR §7(b))](https://deepinfra.com/terms) · [Privacy policy](https://deepinfra.com/privacy) · [Subprocessors](https://docs.deepinfra.com/account/subprocessors.md) · [Status](https://status.deepinfra.com).

**SambaNova:** [Live pricing API](https://cloud.sambanova.ai/api/pricing) · [Pricing page](https://cloud.sambanova.ai/pricing) · [Deprecations](https://docs.sambanova.ai/docs/en/models/deprecations) · [Rate limits](https://docs.sambanova.ai/docs/en/models/rate-limits) · [Function calling/structured output](https://docs.sambanova.ai/docs/en/features/function-calling) · [Privacy policy](https://sambanova.ai/privacy-policy) · [Status](https://status.sambanova.ai) · [gpt-oss-120b launch blog](https://sambanova.ai/blog/start-building-with-lightning-fast-gpt-oss-120b-on-sambacloud).

**Baseten:** [Pricing](https://www.baseten.co/pricing/) · [Model APIs overview](https://docs.baseten.co/development/model-apis/overview) · [Pricing and limits](https://docs.baseten.co/inference/model-apis/pricing-and-limits) · [Security](https://docs.baseten.co/observability/security.md) · [HIPAA compliance announcement](https://www.baseten.co/blog/baseten-announces-hipaa-compliance/) · [Regional deployments](https://docs.baseten.co/deployment/regional-deployments.md) · [Status](https://status.baseten.co).

**Nebius AI Studio / Token Factory:** [Requesty aggregator](https://www.requesty.ai/models/nebius) · [Artificial Analysis](https://artificialanalysis.ai/providers/nebius) · [August 2026 deprecation notice](https://docs.tokenfactory.nebius.com/august-2026-deprecation-notice) · [June 2026 deprecation notice](https://docs.tokenfactory.nebius.com/june-2026-deprecation-notice) · [Post-training models](https://docs.tokenfactory.nebius.com/post-training/models) · [Rate limits](https://docs.tokenfactory.nebius.com/ai-models-inference/rate-limits) · [JSON output](https://docs.tokenfactory.nebius.com/ai-models-inference/json) · [Privacy policy](https://docs.tokenfactory.nebius.com/legal/privacy-policy) · [HIPAA guideline](https://docs.tokenfactory.nebius.com/legal/hipaa-guideline) · [Capacity/SLA](https://docs.tokenfactory.nebius.com/ai-models-inference/dedicated-endpoints/capacity-and-scaling) · [Status](https://status.nebius.com).

**Novita:** [Live model/pricing API](https://api.novita.ai/v3/openai/models) · [Rate-limit tiers](https://docs.novita.ai/guides/llm-rate-limits) · [Structured outputs](https://docs.novita.ai/guides/llm-structured-outputs) · [Privacy policy](https://novita.ai/legal/privacy-policy) · [Status](https://status.novita.ai) · [Requesty: Baichuan-M2-32B on Novita](https://www.requesty.ai/models/novita/baichuan-baichuan-m2-32b).

**Hyperbolic:** [Model card (gpt-oss-120b)](https://app.hyperbolic.ai/models/gpt-oss-120b) · [On-demand pricing docs](https://www.hyperbolic.ai/docs/on-demand/pricing) · [Billing/payments](https://www.hyperbolic.ai/docs/general/billing-payments) · [Security/compliance (non-HIPAA-certified statement)](https://www.hyperbolic.ai/docs/general/security-compliance) · [Status](https://status.hyperbolic.ai) · [Artificial Analysis provider list](https://artificialanalysis.ai/models/gpt-oss-120b/providers).

**Cloudflare Workers AI:** [Pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) · [Models catalog](https://developers.cloudflare.com/workers-ai/models/) · [Limits](https://developers.cloudflare.com/workers-ai/platform/limits/) · [JSON mode](https://developers.cloudflare.com/workers-ai/features/json-mode/) · [Privacy](https://developers.cloudflare.com/workers-ai/privacy/) · [HIPAA trust hub](https://www.cloudflare.com/trust-hub/compliance-resources/hipaa/) · [Status history](https://www.cloudflarestatus.com/history).

**Hugging Face Inference Providers:** [Pricing](https://huggingface.co/docs/inference-providers/pricing) · provider-mapping API for `openai/gpt-oss-120b`, `meta-llama/Llama-Guard-4-12B`, `google/medgemma-4b-it`, `baichuan-inc/Baichuan-M2-32B` · [Chat-completion task docs](https://huggingface.co/docs/inference-providers/tasks/chat-completion) · [Status](https://status.huggingface.co/).

**OpenRouter:** [ZDR guide](https://openrouter.ai/docs/guides/features/zdr) · [No-BAA write-up](https://dredyson.com/i-passed-openrouters-verify-but-cant-use-my-model-a-hipaa-compliant-healthtech-engineers-guide/) · [Full model catalog API](https://openrouter.ai/api/v1/models) · [Rate-limit docs](https://openrouter.ai/docs/api_reference/limits) · [Structured outputs](https://openrouter.ai/docs/features/structured-outputs) · [Status](https://status.openrouter.ai/) · [Data-residency routing blog](https://openrouter.ai/blog/insights/ai-data-residency/) · endpoints API additionally queried for `google/gemma-4-31b-it` and `google/gemma-4-26b-a4b-it`.

**Google Vertex AI MaaS:** [gpt-oss-120b MaaS docs](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/maas/openai/gpt-oss-120b) · [GA forum announcement](https://discuss.google.dev/t/now-ga-openais-gpt-oss-qwen3-models-on-vertex-ai-as-open-model-apis/253945) · [Llama 4 GA on Vertex](https://developers.googleblog.com/en/llama-4-ga-maas-vertex-ai/) · [Serving-option choice docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/open-models/choose-serving-option) · [MedGemma get-started](https://developers.google.com/health-ai-developer-foundations/medgemma/get-started) · [Free-cloud-features exclusion](https://docs.cloud.google.com/free/docs/free-cloud-features) · [HIPAA covered products](https://cloud.google.com/security/compliance/hipaa) · [Cloud status summary](https://status.cloud.google.com/summary) · [Llama Guard Model Garden notebook](https://github.com/GoogleCloudPlatform/vertex-ai-samples/blob/main/notebooks/community/model_garden/model_garden_llama_guard_deployment.ipynb).

**AWS Bedrock:** [Model cards](https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards.html) · [Pricing](https://aws.amazon.com/bedrock/pricing/) · [Quotas](https://docs.aws.amazon.com/bedrock/latest/userguide/quotas-runtime.html) · [Structured output](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html) · [Llama 4 Scout model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-4-scout-17b-instruct.html) · [Privacy](https://aws.amazon.com/bedrock/amazon-models/privacy/) · [HIPAA eligible services reference](https://aws.amazon.com/compliance/hipaa-eligible-services-reference/) · [SLA](https://aws.amazon.com/bedrock/sla/).

**Azure AI Foundry:** [Llama 4 on Azure AI Foundry blog](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/expanding-the-llama-4-herd-new-models-now-available-on-azure-ai-foundry/4403609) · [Foundry Models](https://azure.microsoft.com/en-us/products/ai-foundry/models/) · [Llama pricing (placeholder)](https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/llama/) · [Free services](https://azure.microsoft.com/en-us/pricing/free-services/) · [Structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs) · [Data privacy for models sold by Azure](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy) · [HIPAA offering (Azure)](https://learn.microsoft.com/en-us/azure/compliance/offerings/offering-hipaa-us) · [HIPAA/HITECH general offering](https://learn.microsoft.com/en-us/compliance/regulatory/offering-hipaa-hitech) · [Azure status history](https://azure.status.microsoft/en-us/status/history/).
