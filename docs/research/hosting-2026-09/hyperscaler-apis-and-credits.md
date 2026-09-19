# Hyperscaler-Managed Model APIs and Credit Programs for MediAgent (as of 2026-09-10)

Scope: Google Vertex AI, AWS Bedrock, Azure AI Foundry/Azure OpenAI, Anthropic and OpenAI
first-party APIs, and startup/education credit programs, evaluated as hosting options for
MediAgent (FastAPI on Cloud Run today, Supabase, synthetic data only, en-US/es-MX, may need
HIPAA/BAA later). All prices are list/on-demand USD per 1M tokens unless stated otherwise. All
figures were retrieved by web search/fetch on **2026-09-10**; most underlying blog sources are
themselves dated within the prior few weeks of that date, and official vendor pages are noted as
"(official)". Where sources disagreed or a primary page could not be loaded, this is flagged
explicitly rather than resolved by guessing.

---

## 1. Google Vertex AI

### 1.1 Gemini pricing (Vertex vs. Gemini API)

Retrieved directly from Google's official Gemini API pricing page (`ai.google.dev/gemini-api/docs/pricing`, official, page self-dated "Last Updated: 2026-09-08 UTC", retrieved 2026-09-10):

| Model | Standard input /1M | Standard output /1M | Batch input /1M | Batch output /1M | Context-cache price /1M |
|---|---|---|---|---|---|
| Gemini 3.5 Flash-Lite | $0.30 | $2.50 | $0.15 | $1.25 | $0.03 |
| Gemini 3.1 Flash-Lite | $0.25 (text/image/video); $0.50 (audio) | $1.50 | $0.125 / $0.25 | $0.75 | $0.025 / $0.05 |
| Gemini 3.8 Flash | $0.75 (intro, through 2026-12-31; $1.50 from 2027-01-01) | $3.75 (intro; $7.50 from 2027-01-01) | $0.375 ($0.75) | $1.875 ($3.75) | $0.075 ($0.15) |
| Gemini 3.1 Pro (Preview) | $2.00 (≤200k ctx); $4.00 (>200k) | $12.00 (≤200k); $18.00 (>200k) | $1.00 / $2.00 | $6.00 / $9.00 | $0.20 / $0.40 |

**Vertex parity:** MediAgent's own measured baseline (from CONTEXT.md) already has Gemini 3.5
Flash-Lite on Vertex at $0.30/$2.50 per 1M tokens — identical to the Gemini API number above — and
Gemini 3.1 Flash-Lite at $0.125/$0.75, which matches the *batch* input/standard-output-adjacent
tier here (small discrepancy likely reflects a rate-card update between when that baseline was
measured and 2026-09-08; treat $0.25/$1.50 standard as current). **Net: for the Flash-Lite family,
Vertex on-demand token pricing tracks the Gemini API price list dollar-for-dollar.** One caveat:
several third-party aggregators (CloudZero, "Google Vertex AI pricing in 2026," retrieved
2026-09-10) assert "Vertex AI pricing runs 10–20% higher than AI Studio for the same model." I
could not verify this against Google's own `cloud.google.com/vertex-ai/pricing` page directly — my
fetch of that URL failed (`maxContentLength` exceeded, page too large to retrieve in this
session) — so this is an open item; see §7 Confidence and Gaps. Direct-to-Anthropic-style channel
pricing (Claude, see 1.2) and the CONTEXT.md-verified Flash-Lite parity both argue against a
blanket 10–20% Vertex premium for base token rates, but this needs a direct calculator check
before budgeting.

The context-cache figures above are what Google's pricing page lists under "Context Caching" per
model; the page did not make explicit (and a follow-up fetch of `ai.google.dev/gemini-api/docs/caching`,
official, returned insufficient detail) whether this is a per-token discount rate for cache **hits**
during generation or a cache **storage** fee billed hourly, or both combined into one number. Historically
Gemini has billed both a reduced per-token rate for cached content used in a prompt and a separate storage
fee per 1M tokens/hour; treat the $0.03–$0.20 figures above as indicative of caching's order-of-magnitude
saving (roughly 88–90% off standard input) rather than a fully verified mechanic.

### 1.2 Claude on Vertex AI (Model Garden)

- Per-token pricing for Claude Sonnet 5, Haiku 4.5, and Opus 5 on Vertex Model Garden matches
  Anthropic's own list price dollar-for-dollar: **Sonnet 5 $2/$10, Haiku 4.5 $1/$5, Opus 5 $5/$25**
  per 1M input/output tokens (multiple 2026 pricing analyses, e.g. cloudzero.com/blog/claude-pricing,
  clauder-navi.com/en/vertex-claude-pricing, retrieved 2026-09-10; consistent with Anthropic's own
  `claude.com/pricing`, official, fetched directly 2026-09-10, which lists Opus 5 $5/$25, Sonnet 5
  $2/$10, Haiku 4.5 $1/$5, plus prompt-caching reads at 90% off and writes at ~25% above standard input).
- **Endpoint premium:** Google Cloud offers three Claude endpoint types on Vertex — global (dynamic
  routing, default), multi-region, and regional (pinned to one region). Regional and multi-region
  endpoints carry a **10% premium** over the global default (per Google Cloud blog, "Multi-region
  endpoints for Claude available on Vertex AI," retrieved 2026-09-10). For HIPAA/data-residency
  workloads that need a pinned region, budget for this 10% surcharge.
- **Enablement steps** (based on Vertex Model Garden's standard third-party-model pattern plus the
  endpoint-type documentation found; I did not locate a single official step-by-step console walkthrough
  in this session, so treat this sequence as inferred/typical rather than a verified checklist):
  1. Enable the Vertex AI API on the GCP project.
  2. In Vertex AI Model Garden, locate the Anthropic Claude model card (Claude Opus/Sonnet/Haiku).
  3. Click "Enable" and accept Anthropic's model EULA/terms presented in Model Garden.
  4. Request quota for the target region(s) if not already granted (Claude quota is separate from Gemini quota).
  5. Choose an endpoint type — global (default, no premium) vs. regional/multi-region (10% premium) — based on residency needs.
  6. Call via the Vertex AI SDK or REST, addressing `publishers/anthropic/models/claude-<version>`.
- Vertex Model Garden hosts 200+ foundation models total, spanning Google's own Gemini/Gemma
  families and third-party models including Anthropic Claude, Meta Llama, and Mistral (Spheron
  Network, "Vertex AI Model Garden Pricing 2026," retrieved 2026-09-10).

### 1.3 Model Garden MaaS open models

- **Llama 4** is generally available as Managed-as-a-Service (MaaS) on Vertex — billed per token,
  not per GPU-hour (Google Developers Blog, "Announcing the general availability of Llama 4 as MaaS
  on Vertex AI," retrieved 2026-09-10). One source quotes Llama 4 70B on Vertex at **$2.50/$3.40**
  per 1M input/output tokens; Llama 3.3 70B is quoted at a blended **$1.36 per 1M tokens** (Spheron
  Network / tokenmix.ai aggregator figures, retrieved 2026-09-10 — not independently confirmed against
  an official Vertex price list page in this session).
- **Mistral**: aggregator sources reference Mistral models in Model Garden but did not surface
  precise Vertex per-token numbers in this session (Bedrock's Mistral pricing, which is likely a
  closer proxy since Mistral sets list price across clouds, is in §2.3 below).
- **General billing rule:** "Google models bill per token, third-party [MaaS] models follow vendor
  list pricing, and self-deployed **open** models bill per Endpoint instance-hour (Spot instances
  give a 70% discount)" (Spheron Network, retrieved 2026-09-10). This matters directly for
  MediAgent's open-weights shortlist: **gpt-oss-120b/20b, Gemma 4, Qwen 3.6, MedGemma 1.5,
  Baichuan-M2, Llama Guard 4** are not confirmed as Vertex MaaS per-token offerings — most would
  need self-hosting on a Vertex custom prediction endpoint, billed by the underlying GPU
  instance-hour (see CONTEXT.md's GPU reference: g2-standard-4/1×L4 $0.71/h, a2-highgpu-1g/A100 40GB
  $3.67/h), not by token. Only **Llama 4** (Scout/Maverick) is confirmed as per-token MaaS on Vertex.
- **MedGemma / HAI-DEF terms:** MedGemma and other Health AI Developer Foundations (HAI-DEF) models
  are free open-weight downloads (Hugging Face) and are also deployable on Vertex AI Model Garden as
  a scalable HTTPS endpoint or batch-prediction job; the model weights themselves carry no license
  fee for research or commercial use, but you pay standard Vertex compute (GPU instance-hours) for
  hosting, and usage is subject to the HAI-DEF Terms of Use and a Prohibited Use Policy
  (developers.google.com/health-ai-developer-foundations, official, retrieved 2026-09-10).

### 1.4 Provisioned throughput (GSU)

- Vertex AI generative AI provisioned throughput is priced in **Generative AI Scale Units (GSUs)**;
  one GSU delivers a model-specific tokens/second floor.
- Global on-demand-committed GSU pricing bands found: **~$7.14/GSU-hour for a 1-week commitment,
  ~$3.70 for 1-month, ~$3.29 for 3-month, and ~$2.74/GSU-hour for a 1-year commitment** (Oreate AI /
  nOps aggregator figures, retrieved 2026-09-10 — not cross-checked against Google's own provisioned-
  throughput pricing page, which was not successfully fetched in this session).
  For example context, one GSU on Gemini 2.0 Flash reportedly delivered "9,000 input + 1,000 output
  tokens/second sustained" for $42/hour (older-generation figure; treat as illustrative order of
  magnitude only, not current-model pricing).
- Provisioned throughput customers are served ahead of on-demand traffic and get deterministic
  monthly/weekly cost instead of variable token billing — relevant for MediAgent only at Scenario C
  scale or above, where sustained peak concurrency might otherwise hit on-demand rate limits.

### 1.5 HIPAA / BAA coverage

- Google's Cloud Healthcare/BAA program covers a specific, named list of "Covered Services" — the
  generic name "Vertex AI" is reportedly **not** the exact string used in the current covered-services
  list; you must verify the specific product name (e.g., "Vertex AI Workbench" was explicitly named
  in one source) against Google's live BAA covered-services page before relying on it for PHI
  (authentech.ai, "Is Google Vertex AI HIPAA Compliant? The Naming Trap," retrieved 2026-09-10).
- Multiple 2026 compliance-blog sources (ibl.ai, strac.io, sonomos.ai, aptible.com — all retrieved
  2026-09-10, none an official Google page) converge on: **Vertex AI generative AI inference is
  usable under Google's Cloud BAA** once the org has an executed BAA and uses IAM-controlled,
  customer-project inference (as opposed to consumer Gemini at gemini.google.com, Google AI Studio,
  or free/non-Enterprise Workspace Gemini, all of which are explicitly **out of scope**). Cloud
  Healthcare API (FHIR/HL7) is separately listed as a covered service for clinical-data integration
  alongside Vertex inference.
- **I could not independently confirm this against Google's own live "HIPAA compliance" / covered-
  services page in this session** (searches surfaced only third-party summaries, and a Japanese-locale
  SecOps HIPAA page that was off-topic). Before processing any real PHI, MediAgent should pull the
  current covered-services list directly from `cloud.google.com/security/compliance/hipaa` (or
  successor URL) and confirm the exact Vertex AI Generative AI product line is named.

### 1.6 Data residency

- Google has rolled out ~10 additional data-residency regions for Vertex AI generative AI, including
  EU options (Netherlands, France, UK, Germany, Belgium) (TechMonitor, retrieved 2026-09-10).
- Data stored at rest is kept in the customer-selected region regardless of which endpoint is
  called; however, **endpoints don't guarantee data residency or in-region ML processing in all
  cases** — the official Google documentation page on this (`docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/data-residency`)
  exists but returned only a search snippet in this session, not full fetched content, so the exact
  regional guarantee language should be re-verified before any residency claim is made to a customer
  or reviewer.
- Claude on Vertex specifically now supports **multi-region endpoints (public preview)** for US and
  EU, which pool capacity across regions while keeping processing within the chosen geography — at
  the 10% endpoint premium noted in §1.2.

### 1.7 Committed-use discounts (CUDs)

- Standard Google Cloud resource-based CUDs (up to ~55% off) apply to **Compute Engine SKUs**
  underlying Vertex AI training jobs and self-managed inference endpoints (vCPU/memory/GPU-hours) —
  **they do not apply to serverless per-token Gemini/Claude/MaaS billing.**
  Vertex management fees, storage, egress, and generative-AI token usage continue at standard rates
  regardless of CUD purchases (nOps, "Vertex AI Cost Optimization," retrieved 2026-09-10).
- For per-token generative AI spend specifically, the only documented discount levers are:
  (a) **batch mode** (roughly 50% off standard for supported models, per the Gemini pricing table above),
  (b) **context caching** (see §1.1), and
  (c) **Provisioned Throughput (GSU) commitments** (§1.4), which function as a volume-commitment discount.
- Separately, very-large accounts can negotiate **spend-based committed-use contracts** (reported
  minimum ~$15,000/month) directly with Google sales for a custom discounted rate — not self-serve,
  and irrelevant at MediAgent's Scenario A/B/C volumes (§6).

---

## 2. AWS Bedrock

### 2.1 Claude pricing on Bedrock

- **Claude Sonnet 5: $2/$10, Claude Haiku 4.5: $1/$5, Claude Opus 5: $5/$25** per 1M input/output
  tokens — at parity with Anthropic's direct API list price (multiple 2026 aggregator sources,
  cloudzero.com/blog/amazon-bedrock-pricing and others, retrieved 2026-09-10). One source noted the
  previously-scheduled Sonnet increase to $3/$15 was cancelled and the $2/$10 introductory rate
  became the permanent rate as of 2026-09-01.
- **Caveat:** my direct fetch of the official `aws.amazon.com/bedrock/pricing/` page in this session
  returned stale/legacy figures (Claude 3.5 Sonnet at $6.00/$30.00, a superseded model/price), most
  likely because the automated page-summarization step surfaced an older cached pricing table rather
  than the full current SKU list. Treat the $2/$10 / $1/$5 / $5/$25 figures (corroborated by several
  independent 2026 analyses and matching Anthropic's own posted price) as the reliable numbers, but
  **re-verify directly against the live AWS Bedrock pricing calculator before finalizing a budget.**
- Regional/multi-region Bedrock endpoints carry the same **10% premium** over the global default that
  Vertex applies (per the same aggregator source set, retrieved 2026-09-10) — not independently
  confirmed on an AWS-official page in this session.
- **Batch inference: flat 50% off on-demand** for supported models from Anthropic, Meta, Mistral,
  and Amazon; results land in S3 within 24 hours (AWS official pricing page + AWS ML blog, retrieved
  2026-09-10). Good fit for MediAgent's SOAP-note batch summarization or nightly document-structuring
  backlog where latency doesn't matter.

### 2.2 Llama 4, Amazon Nova pricing

- **Amazon Nova** (official AWS pricing page cross-checked against aggregators, retrieved 2026-09-10):
  - Nova Micro: **$0.035 / $0.14** per 1M tokens
  - Nova Lite: **$0.06 / $0.24** per 1M tokens
  - Nova Pro: **$8 per 1M output tokens equivalent** (~$0.008/1K quoted; input rate not clearly separated in the sources found — treat as needing direct verification)
  - Nova Premier: **$2.50 / $12.50** per 1M tokens
  - All Nova tiers support Standard, Priority, Flex, and Batch pricing tiers, with **batch at 50% of on-demand**.
- **Llama 4** (Scout/Maverick) on-demand per-token pricing was not surfaced with a clean official
  number in this session's Bedrock-specific searches; Vertex's $2.50/$3.40 figure for Llama 4 70B
  (§1.3) is a plausible cross-cloud proxy but should not be assumed identical on Bedrock — **not found** as a verified Bedrock-specific number.

### 2.3 Mistral pricing on Bedrock

Direct fetch of the official AWS Bedrock pricing page (2026-09-10) surfaced, for US regions
(N. Virginia, Ohio, Oregon):

| Model | Input /1M | Output /1M |
|---|---|---|
| Mistral Large 3 | $0.50 | $1.50 |
| Ministral 14B (3.0) | $0.20 | $0.20 |
| Ministral 8B (3.0) | $0.15 | $0.15 |

### 2.4 Bedrock Guardrails pricing (safety layer)

- **Content filters / denied topics: $0.15 per 1,000 text units.**
- **Sensitive information (PII) filters and contextual grounding checks: $0.10 per 1,000 text units.**
- **Automated Reasoning checks: ~$0.17 per 1,000 text units** (one source; not cross-confirmed).
- **Word filters and regex-based PII rules are free.**
- Charges apply only per safeguard actually enabled — e.g., using only content filters + PII
  filters incurs charges for those two, not for unused guardrail types.
- These prices reflect an 80–85% cut AWS made effective 2024-12-01 from the original Guardrails
  pricing (AWS "What's New" posts, official, retrieved 2026-09-10). This is directly relevant as a
  candidate replacement/supplement for MediAgent's own safety-classifier LLM call: a Guardrails PII
  + content-filter pass on a ~500-token safety-classifier input would run roughly $0.10–$0.15 per
  1,000 calls combined (i.e., a small fraction of a cent per call) — cheaper per call than an LLM
  safety-classifier token cost, but a fundamentally different (non-generative, rule/classifier-based)
  mechanism, not a drop-in replacement for judgment-requiring emergency triage.

### 2.5 HIPAA eligibility and BAA process

- **Amazon Bedrock (including Bedrock AgentCore) is HIPAA-eligible** and was added to AWS's HIPAA
  Eligible Services Reference; one source dates a relevant list update to 2026-02-10. A single AWS
  BAA covers all Bedrock-accessible models (Claude, Llama, Titan, Mistral, etc.) without separate
  per-model-provider negotiation (aptible.com, accountablehq.com, retrieved 2026-09-10).
  One source flags that **"Fable and Mythos" models are explicitly excluded** from Bedrock's HIPAA
  eligibility in the AWS reference — a naming detail that should be reconciled against the live AWS
  page rather than assumed, since "Fable" also appears elsewhere as an Anthropic-family/beta
  reference; this could not be verified further in this session.
- BAA execution: **AWS BAA terms are available and reviewable via AWS Artifact in the AWS Management
  Console** — self-serve, no separate sales negotiation required for the base BAA (paubox.com, official-adjacent, retrieved 2026-09-10).
- Being "HIPAA-eligible" is necessary but not sufficient: AWS's shared-responsibility model still
  requires the customer to implement required controls (encryption, access control, logging, BAA
  execution) before treating any workload as compliant.

### 2.6 Data retention, batch, provisioned throughput, regions

- **Batch:** 50% discount, S3-based delivery within 24 hours (see §2.1).
- **Provisioned throughput:** hourly-billed dedicated capacity in "model units," reportedly in the
  **~$40–$200/hour range**, requiring a 1-month or 6-month commitment (aggregator estimate, retrieved
  2026-09-10 — not confirmed against an official page, which requires a sales quote per AWS's own
  pricing page).
- **Regions:** Claude models on Bedrock are available via a **global cross-region inference
  endpoint**, with region-specific cross-region inference expansions confirmed for the Middle East
  (UAE, Bahrain), APAC (Thailand, Malaysia, Singapore, Indonesia, Taiwan), and Japan/Australia
  (AWS ML blog posts, official, retrieved 2026-09-10). A single global endpoint plus regional/
  multi-region pinned options (10% premium, §2.1) mirrors Vertex's Claude endpoint model.
- **Data retention:** not found as a single clear on-demand-inference retention policy number in
  this session (would need AWS's data-privacy/Bedrock FAQ directly); Bedrock's default posture is
  that customer inputs/outputs are not used to train underlying FMs and are not retained beyond
  what's needed to provide the service, but an exact retention-window number was not located.

---

## 3. Azure AI Foundry / Azure OpenAI

### 3.1 GPT-5.6 family pricing on Azure

- **GPT-5.6 Sol**: promotional pricing **$4.00/$20.00** per 1M tokens (a 20% cut on input, 33.3% cut
  on output from a presumed $5/$30 base), running **2026-09-01 through at least 2026-11-30**
  (Microsoft Q&A / Azure blog, retrieved 2026-09-10). Treat $5/$30 as the standard/list rate this
  promo discounts from.
- **GPT-5.6 Terra**: **$2/$12** per 1M tokens (a reported 20% cut effective around 2026-07-30).
- **GPT-5.6 Luna**: **$0.20/$1.20** per 1M tokens (a reported 80% cut effective around 2026-07-30).
- **gpt-5-nano**: **$0.05/$0.40** per 1M tokens — the cheapest model in the Azure OpenAI lineup
  (OpenRouter/BenchLM aggregator confirmation, retrieved 2026-09-10).
- Azure OpenAI splits pricing by deployment type: **Global Standard** (cheapest, no residency
  guarantee), **Data Zone Standard** (regional bloc residency, e.g. EU/APAC), and **Regional
  Standard** (single-region pinning), plus **Provisioned Throughput Units (PTU)** for reserved
  capacity. GPT-5.6 is available across Global Standard/Priority, Data Zone Standard, and Global
  Provisioned "from day one" per Microsoft's own GPT-5.6-on-Foundry announcement (azure.microsoft.com/en-us/blog, official, retrieved 2026-09-10). Context-length tiering applies:
  requests over ~272,000 input tokens bill at a long-context rate for the whole request.
- These match the numbers already known from CONTEXT.md/OpenAI first-party pricing (§4), i.e. **Azure
  and OpenAI first-party pricing for the GPT-5.6 family are at parity** on standard/global deployment,
  which is consistent with Microsoft's general practice of mirroring OpenAI's list price on Azure.

### 3.2 Azure "Models as a Service" open models (Llama, Mistral, Phi)

- Foundry Models serverless API (MaaS) spans **135 models** with pricing from **$0.04 to $22.00 per
  1M input tokens** across the catalog (llmreference.com, retrieved 2026-09-10).
- **Phi-4-mini**: **$0.07/$0.23** per 1M tokens via serverless API.
- **Mistral**: Mistral Large, Mistral Small, and Mistral Medium 3 are offered as premium serverless
  APIs with pay-as-you-go token billing (exact current per-token numbers for each variant were not
  cleanly surfaced in this session beyond the official Azure "Mistral AI" pricing page existing at
  `azure.microsoft.com/en-us/pricing/details/ai-foundry-models/mistral-ai/`; that page should be
  fetched directly for exact figures before budgeting).
- **Llama**: Meta Llama models are available as Foundry Models serverless API, hosted/managed by
  Azure with pay-as-you-go token billing; exact current per-token Llama 4 figures on Azure were
  **not found** in this session (searches surfaced the general MaaS billing structure but not a
  clean Llama 4 Scout/Maverick number on Azure specifically).
- Serverless API (MaaS) requires no GPU provisioning by the customer; Provisioned Throughput is a
  separate, reserved-capacity option for the same model families.

### 3.3 Azure AI Content Safety pricing

- **Standard tier: $0.38 per 1,000 text records**, where a text record = up to 1,000 characters
  (i.e., a 7,500-character input = 8 text records) (azure.microsoft.com pricing page, official, retrieved 2026-09-10).
- **Free tier (F0): up to 5,000 text records/month and 5,000 image analyses/month.**
- Exact USD pricing outside the displayed reference region can vary by Azure region/currency per the
  official pricing calculator.
- This is directly comparable to Bedrock Guardrails (§2.4, $0.10–$0.15/1,000 text units) — **Azure
  Content Safety is meaningfully more expensive per unit** ($0.38 vs. $0.10–$0.15 per 1,000) for a
  comparable content/PII-filtering safety layer, though the exact unit definitions ("text record"
  vs. "text unit") are not guaranteed to be identical in size, so this is a directional, not exact, comparison.

### 3.4 HIPAA BAA coverage

- **Azure OpenAI Service is HIPAA-eligible**, and Microsoft's BAA is bundled by default into the
  Microsoft Online Services Data Protection Addendum for eligible licensing agreements (Enterprise
  Agreement or CSP) — **no separate BAA signature is required** beyond having a qualifying agreement
  (Microsoft Q&A community answers, corroborated across several threads, retrieved 2026-09-10; not
  an official Microsoft Trust Center page fetched directly in this session, so should be re-confirmed there).
- **Scope limitation flagged by sources: HIPAA coverage applies to production-level, text-based
  interactions only.** Preview features and non-text models (e.g., DALL·E image generation, voice
  input models) are reportedly **not** covered unless explicitly stated otherwise — directly relevant
  to MediAgent's voice-minutes workload if it were ever routed through an Azure OpenAI audio model
  rather than Deepgram.
- As with AWS and Google, Microsoft explicitly disclaims that having a BAA "does not ensure your
  organization's HIPAA compliance" — the customer remains responsible for its own compliance controls.

### 3.5 Data residency

- Azure OpenAI supports **Global Standard** (28 regions, no residency guarantee), **Data Zone
  Standard** (EU or APAC data-zone processing boundary), and **Regional Standard** (single-region
  pinning, e.g., France Central, Sweden Central, UK South for guaranteed EU processing)
  (Azure blog "Announcing... Azure OpenAI Data Zones," official, retrieved 2026-09-10).
- Endpoints are regional; data is stored in the same region as the deployment endpoint. Regional
  deployments are Microsoft's own recommendation for the "highest level of data sovereignty and control."

### 3.6 Microsoft healthcare-specific services

- **Dragon Copilot** is Microsoft's clinical-documentation product (ambient scribing, order
  suggestions) — a packaged clinical product, not a generic API MediAgent would call directly; noted
  per the task but out of scope as a hosting option for MediAgent's own LLM calls.
- **Azure AI Language — Text Analytics for Health**: pricing is per **text record** (1,000
  characters/record), with a **free tier of 5,000 text records/month** on both F0 and initial
  Standard (S) tier usage. The specific per-record USD rate for the paid Standard tier beyond the
  free quota was **not found** in this session — `azure.microsoft.com/en-us/pricing/details/language/`
  should be fetched directly for the exact number before use. This service (medical NER/relation
  extraction) could plausibly substitute or complement MediAgent's own document-structuring LLM
  calls for clinical entity extraction, but is a fundamentally different (non-generative, fixed-
  schema NER) capability, not a like-for-like replacement.

---

## 4. Anthropic and OpenAI first-party APIs

### 4.1 Anthropic (official `claude.com/pricing`, fetched directly 2026-09-10)

| Model | Input /1M | Output /1M | Cached read /1M | Cached write /1M |
|---|---|---|---|---|
| Opus 5 | $5 | $25 | $0.50 | $6.25 |
| Sonnet 5 | $2 | $10 | $0.20 | $2.50 |
| Haiku 4.5 | $1 | $5 | $0.10 | $1.25 |

- **Batch processing: 50% off, across all models** (official pricing page).
- **Prompt caching: cached reads are ~90% cheaper than standard input** (e.g., Opus 5 cached read
  $0.50 vs. $5 standard input); cache **writes** cost more than standard input (e.g., ~25% premium:
  Opus 5 write $6.25 vs. $5 input) to account for the initial cache-population cost.
- **Anthropic Structured Outputs**: a native `output_format` parameter now provides
  grammar-constrained JSON generation (moving beyond tool-call emulation), launched first for Sonnet
  4.5/Opus 4.1 with Haiku 4.5 following (tessl.io, retrieved 2026-09-10) — directly relevant to
  MediAgent's document-structuring and SOAP-note JSON-schema needs.
- **BAA/HIPAA**: Anthropic offers a signed BAA plus a "HIPAA-enabled organization" configuration that
  together support processing PHI over supported API features. Important scope limits found:
  - The BAA covers **only the Claude API (Platform) and the Claude Enterprise plan** (with admin
    opt-in) — Pro, Team, Max, Free, Workbench, Console, Cowork, Design, and beta features are
    **explicitly out of scope**.
  - **Covered Models under the BAA require 30-day data retention and are not compatible with
    zero-data-retention (ZDR)** — i.e., **an org cannot have both a HIPAA BAA and ZDR on the same
    covered traffic simultaneously**; these are two different, mutually exclusive data-handling
    arrangements per Anthropic's own docs (`support.claude.com`, official, retrieved 2026-09-10).
  - ZDR itself is a discretionary, Anthropic-approval-gated arrangement for qualifying API/Enterprise
    customers, not a self-serve toggle.
  - Claude Code CLI's HIPAA-relevant coverage specifically requires ZDR to be configured, and is only
    available to qualified accounts — not automatic on any plan.

### 4.2 OpenAI (pricing confirmed via aggregators; official `openai.com/api/pricing/` returned HTTP 403 to automated fetch in this session)

| Model | Input /1M | Output /1M |
|---|---|---|
| GPT-5.6 Sol | $5 (list); promo $4 through 2026-11-30 | $30 (list); promo $20 through 2026-11-30 |
| GPT-5.6 Terra | $2 | $12 |
| GPT-5.6 Luna | $0.20 | $1.20 |
| gpt-5-nano | $0.05 | $0.40 |

(Sources: openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6, edtechinnovationhub.com,
layer3labs.io, getapipulse.com — all retrieved 2026-09-10, cross-consistent with each other and with
CONTEXT.md's baseline figures.)

- **Prompt caching**: OpenAI's cache-read discount mechanics were confirmed via the (Azure-hosted,
  same-API) `learn.microsoft.com/.../prompt-caching` official doc, fetched directly 2026-09-10:
  - Minimum cacheable prompt length: **1,024 tokens**, with the **first 1,024 tokens required to be
    identical** for a cache hit; a single character difference in that prefix causes a full miss.
  - Cache **reads** get "a discount on input token pricing" (exact % not stated on that page — see
    the OpenAI/Azure pricing pages for the live number, historically ~50–75% off for OpenAI-family
    models, but **not confirmed as an exact % in this session — flagged as a gap**).
  - **GPT-5.6 and later models can incur a cache-write charge** (a new behavior — pre-GPT-5.6 models
    did not charge for cache writes at all). This is an important nuance for cost modeling: caching
    system prompts/few-shot context on GPT-5.6 Luna/Sol is not pure upside the way it is on older
    GPT models or on Claude's read-only cache-hit discount (Claude does also charge for cache writes,
    per §4.1).
  - Extended (24-hour) cache retention is supported on several pre-5.6 models; GPT-5.6 uses a
    30-minute minimum TTL by default via `prompt_cache_options.ttl`.
- **Batch API**: OpenAI's standard Batch API discount (well-established in general OpenAI docs) is
  **50% off** synchronous pricing — consistent with the pattern seen at Anthropic and on Bedrock;
  not re-confirmed against a fresh 2026 OpenAI page in this session due to the 403 fetch failure, but
  no source found any indication this discount level has changed.
- **HIPAA/BAA**: To use OpenAI's API with PHI, a covered entity needs (a) **zero data retention
  (ZDR)** configured on the API endpoints used, and (b) an **executed BAA** — both are required
  together; ZDR alone is not sufficient once PHI is in scope. BAA requests go to **baa@openai.com**,
  with a reported 1–2 business day initial response time. A **"Healthcare-specific tier"** reportedly
  launched around February 2026 bundling BAA-by-default plus enhanced retention controls (specode.ai,
  protecto.ai, retrieved 2026-09-10 — **not independently confirmed on an official OpenAI page** in
  this session; treat as needing verification). Only **Chat Completions and the Responses API** are
  usable for PHI under the BAA with retention controls; Assistants, Threads, Vector Stores, Files,
  Batch, and fine-tuning retain state until explicitly deleted regardless of ZDR, so those surfaces
  should be avoided for PHI-bearing workloads.

### 4.3 Structured output support (cross-provider)

One aggregator benchmark (agenta.ai-adjacent sources, retrieved 2026-09-10) reported schema-compliance
rates of **OpenAI Structured Outputs 99.9%, Anthropic tool-use 99.8%, Gemini schema mode 99.7%** —
directionally useful but a single, non-primary source; treat as illustrative, not authoritative.

---

## 5. Startup / education / research credit programs

### 5.1 Credit programs at a glance

| Program | Amount | Eligibility gist | Source (retrieved 2026-09-10) |
|---|---|---|---|
| Google Cloud free trial | $300, 90 days | Any new billing account, personal card OK, no company needed | cloud.google.com/signup-faqs (official) |
| Google Cloud Research Credits (Higher-Ed/Nonprofit) | Faculty/postdoc: up to $5,000 (one-time); PhD student: up to $1,000/yr | Faculty, PhD students, postdocs at accredited institutions, or eligible nonprofit researchers; requires a research proposal + cost estimate | edu.google.com/.../credits/research, support.google.com/google-cloud-higher-ed (official) |
| Google for Startups Cloud Program — Start tier | Up to $2,000 | Tech startup <5 yrs old, no institutional funding, no prior Google Cloud credits beyond free trial | cloud.google.com/startup/benefits (official) + cloudkompas.com |
| Google for Startups Cloud Program — Scale/AI-First tiers | $200,000 (Scale) / $350,000 (AI-First) | Requires pre-seed–Series A **equity funding** (SAFEs count; grants/crowdfunding/angel/F&F do not) | cloud.google.com/startup/ai (official) + aggregator |
| AWS Activate — Founders tier | $1,000 | Self-funded/bootstrapped, pre-Series B, verifiable company website, paid AWS account, no prior equal/greater Activate credit | wring.co, cloudkompas.com |
| AWS Activate — Portfolio tier | $1,000–$100,000+ | Requires affiliation with a named accelerator (YC, Techstars, 500 Global, etc.) or VC partner | same as above |
| AWS Educate | Training/labs only, no direct compute credit grant since 2023 | Open to any individual (student/career-changer); institutional credit grants ended 2023, moved to AWS Academy | aws.amazon.com/education/awseducate (official) |
| Microsoft for Startups Founders Hub — Basic | ~$1,000 Azure credit | Email verification only, very low barrier | grantedai.com, aicredits.co |
| Microsoft for Startups Founders Hub — Enhanced | Up to $5,000 | Requires business verification | same |
| Microsoft for Startups Founders Hub — Investor-affiliated | $100,000, up to $150,000 total | Requires investor affiliation | same |
| Azure for Students | $100/year, renewable | .edu email verification, 18+, full-time student at accredited institution, no credit card | azure.microsoft.com/en-us/free/students (official) |
| GitHub Student Developer Pack (incl. Copilot Student) | Copilot Student free; cloud credits from partners (DigitalOcean, Azure, etc.); free domains | .edu email/student verification via GitHub Education | github.com Education docs, itechguides.com |
| NVIDIA Inception | Up to $100,000 AWS credits + up to $100,000 DGX Cloud credits, preferred GPU pricing, DLI training | **Must be officially incorporated**, <10 years old, ≥1 developer, working website | nvidia.com/en-us/startups (official) |
| Anthropic Claude for Startups | $25,000–$100,000+ Claude API credit | Primarily venture-backed startups | opportunitiesforyouth.org, getaiperks.com |
| Anthropic Research/Academic credits | $500–$25,000+ per project (rare-disease call: up to $50,000 over 6 months, closed 2026-08-02) | Academics, AI-safety researchers, scientists, qualifying nonprofits — proposal-based, periodic calls | getaiperks.com/anthropic-research-credit-program |
| OpenAI Researcher Access Program | Up to $1,000 API credit, 12-month validity | Active affiliation with an academic institution, research org, or research nonprofit; reviewed quarterly (Mar/Jun/Sep/Dec) | help.openai.com (official FAQ), openai.smapply.org (official application) |
| OpenAI for Startups | $2,500 (via Ramp) to $5,000 (via VC/accelerator partner) | Pre-seed–Series A, registered business, typically needs a Ramp corporate-card account | guptadeepak.com, aicreditmart.com |
| Groq for Startups | $10,000 GroqCloud credit | Bootstrapped/pre-seed/seed OK, no VC referral required | guptadeepak.com/startup-offers/programs/groq-startups |
| Fireworks AI for Startups | Up to $10,000 credit (expires after 1 year) | No equity, no VC backing required | fireworks.ai/startups (official) |
| Together AI for Startups | Not specified | Funding-gated (requires VC backing), unlike Groq/Fireworks | fin.ai aggregator |

### 5.2 Realistic options for an SJSU masters capstone team (not incorporated)

| Program | Realistic? | Why |
|---|---|---|
| Google Cloud free trial ($300) | **Yes** | No company, no funding proof, just a Google account + card for verification. Easiest first step; expires in 90 days though, so time it to a demo/eval window. |
| Azure for Students ($100/yr) | **Yes** | Pure student-email verification, no card, renewable annually. Each teammate can claim their own. |
| GitHub Student Developer Pack / Copilot Student | **Yes** | .edu-based, individual, no incorporation needed. Bundles small cloud credits from partners too. |
| Google Cloud Research Credits — Higher-Ed (faculty/postdoc $5,000, PhD student $1,000) | **Maybe** | Explicitly targets faculty/PhD students/postdocs, not named for master's students. A faculty advisor sponsoring/applying is the realistic path to the $5,000 award; a lone master's team likely doesn't qualify directly. Worth pursuing via the capstone's faculty advisor. |
| Anthropic Research/Academic credit calls | **Maybe** | Explicitly open to "academics" and disease/research-focused calls; a clinical-decision-support capstone with a faculty PI framing could plausibly qualify for a modest award, but calls are periodic/thematic (e.g., the rare-disease call closed 2026-08-02) and proposal-based, not guaranteed. |
| OpenAI Researcher Access Program (up to $1,000) | **Maybe** | Explicit academic-institution affiliation is the exact bar SJSU satisfies; but the program's stated focus is "study of responsible AI deployment, risk mitigation, societal impact" research, not general product-building — a capstone framed around safety/evaluation of clinical AI could plausibly qualify; framed as pure app development, less likely. |
| Microsoft for Startups Founders Hub — Basic tier (~$1,000) | **Yes, plausible** | Described as email-verification-only with no incorporation requirement at the Basic tier — the lowest-barrier startup-labeled program found. Team would sign up as a "startup" project; terms should be double-checked at application time since program terms shift often. |
| AWS Activate — Founders tier ($1,000) | **Maybe** | Wants "a verifiable company website or web profile" and a paid AWS account — achievable without formal incorporation (a project site suffices per the phrasing found), but some AWS Activate variants have historically wanted an EIN/registered entity; ambiguous and should be tested directly in the application flow rather than assumed. |
| NVIDIA Inception | **No** (not yet) | Explicitly requires the applicant to be "officially incorporated." Off the table until/unless the team incorporates. |
| Google for Startups Cloud Program (any tier) | **No** | Start tier still frames itself around "technology startups," and Scale/AI-First tiers require equity funding (pre-seed–Series A) — a non-incorporated, unfunded capstone team does not fit either bar cleanly. |
| Anthropic Claude for Startups ($25k+) | **No** | Framed around venture-backed startups; not a fit pre-incorporation/pre-funding. |
| OpenAI for Startups ($2,500–$5,000) | **No** (not yet) | Typically requires a registered business entity and a Ramp account tied to a company. |
| AWS Educate | **Yes, but low value** | Open to any individual with no incorporation needed, but as of 2026 it provides training/labs and badges only — **not** a compute-credit grant since the 2023 change. Useful for skills, not for the compute budget. |
| Groq / Fireworks for Startups ($10,000 each) | **Maybe** | Both explicitly say "no VC backing required," which is promising for an unincorporated team, but neither source confirmed whether a registered business entity (any entity, not necessarily funded) is still a hard requirement at application time — worth applying to test, low downside. |
| Together AI for Startups | **No** | Explicitly funding-gated. |

**Bottom line for MediAgent's SJSU capstone context:** the fastest, close-to-certain path is
stacking the **Google Cloud $300 trial + Azure for Students $100/teammate + GitHub Student
Developer Pack**, which is low-effort and requires no incorporation. The next-best realistic swing
is **Microsoft for Startups Founders Hub Basic tier (~$1,000)** and testing an **AWS Activate
Founders** application (both plausibly reachable without incorporating). The **highest-value but
least-certain** path is routing through the capstone's **faculty advisor** to apply for **Google
Cloud Research Credits ($5,000)** and/or an **Anthropic academic/research credit call**, since both
explicitly target academic research rather than incorporated startups. NVIDIA Inception, Google for
Startups (Scale/AI-First), Anthropic/OpenAI startup tracks, and Together AI are not realistic without
first incorporating and/or raising funding.

---

## 6. Scenario cost tables

### 6.1 Workload assumptions (from CONTEXT.md, restated)

Per-unit token counts used below (chat turns bundle a classification sub-call and a reply sub-call;
the safety classifier is a separate third call per chat turn):

| Task | Input tokens | Output tokens | Volume A (demo) | Volume B (1 clinic) | Volume C (10 clinics) |
|---|---|---|---|---|---|
| Chat turn (classification 400/60 + reply 1500/250) | 1,900 | 310 | 3,000 | 60,000 | 600,000 |
| Safety classifier (1 per chat turn) | 500 | 10 | 3,000 | 60,000 | 600,000 |
| Document structuring | 700 | 700 | 600 | 3,000 | 30,000 |
| Patient explanation | 600 | 350 | 600 | 15,000 | 150,000 |
| SOAP note | 3,000 | 600 | 300 | 1,500 | 15,000 |
| Voice minutes (ASR, excluded here — handled by Deepgram, not an LLM token cost) | — | — | 900 min | 9,000 min | 90,000 min |

**Note on the document-structuring token count**: CONTEXT.md states "~700 in / 700 out tokens per
1–2 pages; 5 pages avg." This is ambiguous between (a) 700/700 tokens being the flat per-document
rate regardless of the "5 pages avg" note, or (b) 700/700 being a per-1.5-page rate that should be
scaled up ~3.3× for a 5-page average document. I used interpretation (a) — flat 700 in/700 out per
document — because it reproduces CONTEXT.md's own stated baseline cost check ("~$0.002–0.005 per
document" on Gemini 3.5 Flash-Lite: 700×$0.30/1M + 700×$2.50/1M = $0.00196, inside that range).
Interpretation (b) would raise the per-document cost roughly 3×. **This is flagged as an assumption,
not a verified fact — see §7.**

Voice minutes are **excluded** from the token-cost tables below because MediAgent's transcription is
handled by Deepgram (per CONTEXT.md, "Deepgram credits exist"), a specialized ASR service, not one of
the four LLM options being compared here. If voice were ever routed through a hyperscaler's native
audio-in LLM model instead, that would need separate per-minute/per-token audio pricing not covered
in this report.

Total monthly input/output tokens by scenario (sum across chat + safety + documents + explanations + SOAP):

| Scenario | Total input tokens | Total output tokens |
|---|---|---|
| A (demo) | 8,880,000 | 1,770,000 |
| B (1 clinic) | 159,600,000 | 27,450,000 |
| C (10 clinics) | 1,596,000,000 | 274,500,000 |

(C is exactly 10× B and B is exactly 20× A on chat/safety/explanations and 5–10× on
documents/SOAP, consistent with the volume multipliers given in CONTEXT.md.)

### 6.2 Monthly compute cost by option (on-demand, no caching, no batch)

All figures = (input tokens in millions × input price) + (output tokens in millions × output price),
using the on-demand per-1M-token prices established in §1–4.

| Option | Input $/1M | Output $/1M | Scenario A | Scenario B | Scenario C |
|---|---|---|---|---|---|
| (a) Gemini 3.5 Flash-Lite (Vertex, baseline) | $0.30 | $2.50 | **$7.09** | **$116.51** | **$1,165.05** |
| (b) Claude Haiku 4.5 (Vertex or Bedrock) | $1.00 | $5.00 | **$17.73** | **$296.85** | **$2,968.50** |
| (c) GPT-5.6 Luna (Azure) | $0.20 | $1.20 | **$3.90** | **$64.86** | **$648.60** |
| (d) gpt-5-nano (Azure) | $0.05 | $0.40 | **$1.15** | **$18.96** | **$189.60** |

Ranking at every scenario size: **gpt-5-nano < GPT-5.6 Luna < Gemini 3.5 Flash-Lite (baseline) <
Claude Haiku 4.5**, by a wide margin — gpt-5-nano is roughly **6× cheaper** than the Gemini
Flash-Lite baseline and **15–16× cheaper** than Claude Haiku 4.5 at this workload's input/output
mix (which is input-heavy, so the input-price gap dominates: gpt-5-nano's $0.05 vs. Haiku's $1.00
input price is a 20× gap, moderated somewhat by output pricing).

### 6.3 With batch discounts (where the workload tolerates async processing)

Document structuring, patient explanations, and SOAP notes are plausible batch candidates
(non-interactive, can tolerate a delay); chat turns and safety-classifier calls are not (interactive,
latency-sensitive) and stay at on-demand pricing. Applying each provider's documented **50% batch
discount** (Gemini, Claude/Bedrock, and OpenAI/Azure all documented at 50% off in §1.1/§2.1/§4.1/§4.2)
to just the batchable slice:

Batchable tokens by scenario (documents + explanations + SOAP only):

| Scenario | Batchable input tokens | Batchable output tokens |
|---|---|---|
| A | 1,680,000 | 810,000 |
| B | 15,600,000 | 8,250,000 |
| C | 156,000,000 | 82,500,000 |

Interactive-only tokens (chat + safety) = Total − Batchable:

| Scenario | Interactive input | Interactive output |
|---|---|---|
| A | 7,200,000 | 960,000 |
| B | 144,000,000 | 19,200,000 |
| C | 1,440,000,000 | 192,000,000 |

| Option | Scenario A total | Scenario B total | Scenario C total | Savings vs. fully-on-demand (§6.2) |
|---|---|---|---|---|
| (a) Gemini 3.5 Flash-Lite | **$5.82** | **$103.85** | **$1,038.53** | ~11–18% |
| (b) Claude Haiku 4.5 | **$14.87** | **$268.43** | **$2,684.25** | ~10–16% |
| (c) GPT-5.6 Luna | **$3.25** | **$58.35** | **$583.50** | ~10–17% |
| (d) gpt-5-nano | **$0.95** | **$16.92** | **$169.20** | ~11–18% |

Each total = (interactive tokens × on-demand price) + (batchable tokens × 50%-off batch price), e.g.
for Gemini at Scenario A: interactive = 7.2M×$0.30 + 0.96M×$2.50 = $4.56; batch = 1.68M×$0.15 +
0.81M×$1.25 = $1.26; total = $5.82. The saving is modest in percentage terms (~10–18%, not 50%)
because chat + safety-classifier calls — which cannot be batched, since they're interactive — make up
the large majority of total tokens at every scenario size (chat alone is 64–72% of input tokens); only
the document/explanation/SOAP-note slice benefits from the batch discount. GPT-5.6's batch rate was
assumed at the same 50%-off pattern documented for Gemini/Claude/Bedrock (§1.1/§2.1/§4.1) since a
GPT-5.6-specific batch percentage was not separately confirmed in this session — flagged in §7.

### 6.4 Prompt-caching upside (illustrative, not precisely quantified)

MediAgent's chat-turn and safety-classifier calls likely share a large static prefix (system prompt,
safety rubric, few-shot examples) across every call. If, hypothically, ~50% of the *input* tokens in
the chat+safety category were cacheable at each provider's documented cache-hit discount:

- **Claude (Haiku 4.5)**: cached-read price is $0.10/1M vs. $1/1M standard (90% off). Caching half of
  Scenario C's interactive input (144M × 50% = 72M tokens) at $0.10 instead of $1.00 saves
  72 × ($1.00 − $0.10) = **~$64.80/month** at Scenario C, **before** accounting for cache-write
  costs (Claude also charges for cache writes, at a premium over standard input — see §4.1 — so the
  net saving depends heavily on cache hit-rate and prefix-refresh frequency).
- **Gemini (Flash-Lite)**: context-caching price is documented at $0.03/1M vs. $0.30/1M standard
  input (also ~90% off), but as noted in §1.1 it was not confirmed in this session whether that
  figure already nets out a separate hourly storage fee — so a precise savings number is **not
  computed here**, only the ballpark magnitude (same order as Claude's ~90% cache-hit discount).
- **GPT-5.6 (Azure/OpenAI)**: cache-read discount percentage was not found as an exact number in
  this session (§4.2); GPT-5.6-and-later models also introduce a cache-write charge, which is a
  new cost that didn't exist on pre-5.6 OpenAI models. Net caching benefit is directionally positive
  but **not quantifiable from sources found in this session.**

**Recommendation**: before relying on caching savings in a budget, MediAgent should measure its own
actual cache-hit rate (how much of each request's input is a stable prefix) against live traffic,
since the reported ~90% per-hit discounts only pay off net-positive if the cache is reused enough
times to amortize the write cost and any storage fee.

---

## 7. Confidence and gaps

- **Vertex vs. Gemini API price parity**: confirmed for Gemini 3.5/3.1 Flash-Lite by matching
  CONTEXT.md's own measured baseline against the official `ai.google.dev` price list. The claim (from
  third-party aggregators only) that "Vertex runs 10–20% higher than AI Studio" was **not** resolved
  — my fetch of `cloud.google.com/vertex-ai/pricing` failed due to page size, so this needs a direct
  re-check before final budgeting, especially for Gemini 3.8 Flash / 3.1 Pro specifically on Vertex.
- **AWS Bedrock official pricing page fetch returned stale Claude 3.5 Sonnet figures** ($6/$30)
  instead of current Sonnet 5/Haiku 4.5/Opus 5 numbers, despite being pointed at the live URL — most
  likely a summarization/caching artifact of the fetch tool rather than the page itself being wrong.
  The $2/$10 (Sonnet 5) / $1/$5 (Haiku 4.5) / $5/$25 (Opus 5) figures used throughout this report are
  corroborated by several independent 2026 analyses and match Anthropic's own first-party price, but
  **should be re-verified against the live AWS Bedrock pricing calculator** before committing a budget.
- **Google's own HIPAA covered-services page and Vertex AI's exact data-residency guarantee language
  were not directly fetched** in this session (only third-party compliance-blog summaries were
  available); before processing any real PHI, pull `cloud.google.com`'s live BAA covered-services
  list and confirm the exact Vertex AI Generative AI product name appears in it.
- **Document-structuring token-count interpretation** (§6.1) is an assumption reconciling an
  ambiguous CONTEXT.md line item against CONTEXT.md's own stated cost-check range; flagged explicitly
  rather than silently resolved.
- **§6.3's batch-discount totals assume GPT-5.6 gets the same 50%-off batch rate documented for
  Gemini/Claude/Bedrock**; a GPT-5.6-specific batch discount percentage was not independently
  confirmed in this session and should be checked against Azure/OpenAI's live batch pricing.
- **Prompt-caching savings (§6.4) are illustrative only** — exact net savings depend on real
  cache-hit rates, and OpenAI/Azure's exact cache-read discount percentage and Gemini's context-cache
  mechanics (storage fee vs. per-use discount) were not pinned down to an exact, sourced number in
  this session.
- **Llama 4 pricing on Bedrock and on Azure Foundry Models** were not found as clean, provider-specific
  numbers in this session (only a Vertex number was found, at $2.50/$3.40/1M for Llama 4 70B, itself
  from an aggregator rather than an official Google page).
- **Azure Text Analytics for Health's exact paid per-record rate** beyond the free tier was not found.
- **OpenAI's exact HIPAA "Healthcare-specific tier" (Feb 2026) and its cache-read discount percentage**
  were reported only by secondary/aggregator sources, not an official OpenAI page (the official
  `openai.com/api/pricing/` returned HTTP 403 to the automated fetch tool used in this session).
- **NVIDIA Inception's "officially incorporated" requirement, and each startup-credit program's exact
  incorporation bar (AWS Activate Founders, Groq, Fireworks)**, were stated by aggregator/community
  sources, not always an official program page; SJSU capstone applicants should test the actual
  application flow rather than assume eligibility from these summaries.
- **Amazon Nova Pro's input price** was not clearly separated from a "$0.008/1K" blended figure found
  in one source — treat as unverified until checked against the official AWS Bedrock pricing page directly.
- General caveat: the vast majority of pricing/compliance figures in this report come from **2026
  third-party pricing-aggregator blogs**, not vendor-official pages, because several official pricing
  pages either failed to fetch (size limits, 403s) or did not surface in search results with the
  specific numbers needed. Cross-source agreement across 2–4 independent aggregators was used as a
  substitute for official confirmation wherever an official fetch wasn't possible, and is noted
  per-figure above; anywhere only a single aggregator supported a number, that is flagged inline.

---

## 8. Sources

**Google Cloud / Vertex AI**
- https://ai.google.dev/gemini-api/docs/pricing (official, fetched directly 2026-09-10, page self-dated 2026-09-08)
- https://ai.google.dev/gemini-api/docs/caching (official, fetched directly 2026-09-10)
- https://cloud.google.com/vertex-ai/pricing (official; fetch failed, size limit, 2026-09-10)
- https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing
- https://www.cloudzero.com/blog/google-vertex-ai-pricing/
- https://www.nops.io/blog/vertex-ai-pricing/
- https://www.nops.io/blog/vertex-ai-cost-optimization-guide/
- https://www.opslyft.com/blog/google-vertex-ai-pricing
- https://benchlm.ai/google/api-pricing
- https://www.spheron.network/blog/vertex-ai-model-garden-pricing-2026-cost-vs-self-hosted/
- https://cloud.google.com/blog/products/ai-machine-learning/anthropics-claude-opus-4-and-claude-sonnet-4-on-vertex-ai
- https://cloud.google.com/blog/products/ai-machine-learning/multi-region-endpoints-for-claude-available-on-vertex-ai
- https://www.clauder-navi.com/en/vertex-claude-pricing
- https://developers.googleblog.com/llama-4-ga-maas-vertex-ai/
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/use-partner-models
- https://tokenmix.ai/blog/vertex-ai-pricing
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/provisioned-throughput/measure-provisioned-throughput
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/provisioned-throughput/overview
- https://www.oreateai.com/blog/demystifying-vertex-ai-provisioned-throughput-pricing-what-you-need-to-know/0c9efbc0e2b8243798f2830d6d36d70b
- https://ibl.ai/blog/is-gemini-hipaa-compliant-2026
- https://www.aptible.com/hipaa-compliant-ai-tools/gemini-baa
- https://www.strac.io/blog/is-gemini-hipaa-compliant
- https://authentech.ai/healthcare/is-google-vertex-ai-hipaa-compliant/
- https://sonomos.ai/blog/is-gemini-hipaa-compliant-2026/
- https://www.techmonitor.ai/cloud/google-cloud-vertex-ai-data-residency/
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/data-residency
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/release-notes
- https://developers.google.com/health-ai-developer-foundations (official)
- https://developers.google.com/health-ai-developer-foundations/medgemma/get-started (official)
- https://console.cloud.google.com/vertex-ai/publishers/google/model-garden/medgemma

**AWS Bedrock**
- https://aws.amazon.com/bedrock/pricing/ (official, fetched directly 2026-09-10; Mistral/Guardrails/batch confirmed, Claude figures appear stale)
- https://www.spheron.network/blog/aws-bedrock-pricing-2026-managed-api-cost/
- https://www.cloudzero.com/blog/amazon-bedrock-pricing/
- https://caylent.com/blog/amazon-bedrock-pricing-explained
- https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-sensitive-filters.html (official)
- https://aws.amazon.com/about-aws/whats-new/2024/12/amazon-bedrock-guardrails-reduces-pricing-85-percent/ (official)
- https://aws.amazon.com/about-aws/whats-new/2025/06/amazon-bedrock-guardrails-tiers-content-filters-denied-topics (official)
- https://www.aptible.com/hipaa-compliant-ai-tools/aws-bedrock-baa
- https://www.accountablehq.com/post/is-amazon-bedrock-hipaa-eligible-what-to-know-about-the-aws-baa-and-using-phi
- https://www.paubox.com/blog/amazon-web-services-aws-hipaa-compliant
- https://patient-protect.com/aws-hipaa-eligible-services
- https://thescimus.com/blog/aws-bedrock-hipaa-baa-whats-covered-whats-not/
- https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock (official Anthropic doc)
- https://aws.amazon.com/blogs/machine-learning/introducing-amazon-bedrock-global-cross-region-inference-for-anthropics-claude-models-in-the-middle-east-regions/ (official)
- https://aws.amazon.com/blogs/machine-learning/global-cross-region-inference-for-latest-anthropic-claude-opus-sonnet-and-haiku-models-on-amazon-bedrock-in-thailand-malaysia-singapore-indonesia-and-taiwan/ (official)
- https://aws.amazon.com/about-aws/whats-new/2025/10/claude-4-5-haiku-anthropic-amazon-bedrock/ (official)
- https://aws.amazon.com/blogs/machine-learning/introducing-amazon-bedrock-cross-region-inference-for-claude-sonnet-4-5-and-haiku-4-5-in-japan-and-australia/ (official)
- https://repost.aws/articles/ARe4RqNtZ8Q2OWq9HgPSDaoQ/never-miss-an-amazon-bedrock-model-deprecation-notice-with-aws-user-notifications-and-eventbridge
- https://vorplabs.com/models/amazon-bedrock-model-retirements
- https://schematical.com/posts/aws-bedrock-eol-legacy_20260416
- https://aws.amazon.com/education/awseducate/ (official)

**Azure AI Foundry / Azure OpenAI**
- https://azure.microsoft.com/en-us/blog/gpt-5-6-now-available-in-microsoft-foundry/ (official)
- https://learn.microsoft.com/en-us/answers/questions/5962521/pricing-of-openai-gpt-5-6-models-luna-terra
- https://www.cloudzero.com/blog/azure-openai-pricing/
- https://pricepertoken.com/endpoints/azure
- https://azure.microsoft.com/en-us/pricing/details/azure-openai/ (official)
- https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/mistral-ai/ (official)
- https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/models-inference-examples (official)
- https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure (official)
- https://www.llmreference.com/provider/microsoft-foundry/models
- https://azure.microsoft.com/en-in/pricing/details/cognitive-services/content-safety/ (official)
- https://azure.microsoft.com/en-us/pricing/details/content-safety/ (official)
- https://learn.microsoft.com/en-us/answers/questions/2106637/azure-openai-hipaa-compliance-status
- https://learn.microsoft.com/en-us/answers/questions/2258799/does-azure-openai-services-provide-hipaa-complianc
- https://www.aptible.com/hipaa-compliant-ai-tools/azure-openai-baa
- https://learn.microsoft.com/en-us/azure/ai-services/language-service/text-analytics-for-health/quickstart (official)
- https://azure.microsoft.com/en-us/pricing/details/language/ (official)
- https://azure.microsoft.com/en-us/blog/announcing-the-availability-of-azure-openai-data-zones-and-latest-updates-from-azure-ai/ (official)
- https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/prompt-caching (official, fetched directly 2026-09-10)
- https://openrouter.ai/openai/gpt-5-nano
- https://www.getapipulse.com/blog-gpt56-luna-pricing.html
- https://www.edtechinnovationhub.com/news/openai-cuts-gpt-56-luna-api-prices-by-80-and-terra-by-20
- https://www.layer3labs.io/guides/gpt-5-6-pricing

**Anthropic / OpenAI first-party**
- https://claude.com/pricing (official, fetched directly 2026-09-10)
- https://platform.claude.com/docs/en/manage-claude/api-and-data-retention (official)
- https://privacy.claude.com/en/articles/8956058-i-have-a-zero-data-retention-agreement-with-anthropic-what-products-does-it-apply-to (official)
- https://privacy.claude.com/en/articles/8114513-business-associate-agreements-baa-for-commercial-customers (official)
- https://support.claude.com/en/articles/15455031-covered-models-under-a-business-associate-agreement-baa (official)
- https://www.aptible.com/hipaa/claude-baa
- https://tessl.io/blog/anthropic-brings-structured-outputs-to-claude-developer-platform-making-api-responses-more-reliable
- https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/ (official)
- https://openai.com/api/pricing/ (official; returned HTTP 403 to fetch tool, 2026-09-10)
- https://developers.openai.com/api/docs/guides/your-data (official)
- https://help.openai.com/en/articles/10139500-researcher-access-program-faq (official)
- https://openai.smapply.org/prog/openai_researcher_access_program/ (official)
- https://www.protecto.ai/blog/openai-hipaa-baa-what-it-actually-covers-and-what-leaves-phi-exposed/
- https://www.specode.ai/blog/openai-llm-api-hipaa
- https://agenta.ai/blog/the-guide-to-structured-outputs-and-function-calling-with-llms

**Credit programs**
- https://cloud.google.com/signup-faqs (official)
- https://cloud.google.com/free (official)
- https://cloud.google.com/terms/free-trial (official)
- https://cloud.google.com/startup/benefits (official)
- https://cloud.google.com/startup/ai (official)
- https://cloudkompas.com/blog/google-cloud-for-startups-2026-credits-guide
- https://creditforstartups.com/companies/google
- https://edu.google.com/intl/ALL_us/programs/credits/research/ (official)
- https://support.google.com/google-cloud-higher-ed/answer/10324705 (official)
- https://support.google.com/google-cloud-higher-ed/answer/10723679 (official)
- https://research.google/blog/announcing-the-google-cloud-platform-research-credits-program/ (official)
- https://docs.cloud.google.com/billing/docs/how-to/edu-grants (official)
- https://www.wring.co/blog/aws-credits-for-startups
- https://cloudkompas.com/blog/aws-activate-complete-guide-2026
- https://startground.com/deals/aws-activate-founders/
- https://perkstack.co/blog/aws-activate-guide
- https://grantedai.com/grants/microsoft-for-startups-founders-hub-azure-ai-credits-program-microsoft-a9b0c1d2
- https://www.aicredits.co/en/blogs/azure-startup-credits-2026
- https://saastweaks.com/startup-credits/microsoft-for-startups
- https://azure.microsoft.com/en-us/free/students (official)
- https://azure.microsoft.com/en-us/pricing/offers/ms-azr-0170p (official)
- https://learn.microsoft.com/en-us/azure/education-hub/about-azure-for-students (official)
- https://github.com/orgs/community/discussions/111352
- https://www.itechguides.com/the-github-student-developer-pack-is-back-eligibility-benefits-and-2026-copilot-changes/
- https://www.nvidia.com/en-us/startups/ (official)
- https://www.thundercompute.com/blog/nvidia-inception-program-guide
- https://grantedai.com/grants/anthropic-startup-grant-program-anthropic-cb6dbe2d
- https://opportunitiesforyouth.org/2026/08/11/claude-for-startups/
- https://klymentiev.com/blog/claude-free-credits
- https://www.getaiperks.com/en/ai/anthropic-startup-program
- https://www.getaiperks.com/en/ai/anthropic-research-credit-program
- https://grantedai.com/grants/openai-researcher-access-program-api-credits-openai-group-c2fd0099
- https://openai.com/index/openai-grove/ (official)
- https://fin.ai/learn/ai-credits-for-startups
- https://fireworks.ai/blog/fireworks-for-startups (official)
- https://fireworks.ai/startups (official)
- https://guptadeepak.com/startup-offers/programs/groq-startups
- https://perkbook.co/startup-programs/groq-for-startups/

**Deprecation / lifecycle**
- https://hidekazu-konishi.com/entry/ai_model_deprecation_and_lifecycle_calendar.html
- https://benchlm.ai/deprecations
- https://dev.to/om_shree_0709/google-just-killed-vertex-ai-heres-what-the-gemini-enterprise-agent-platform-4fh4
