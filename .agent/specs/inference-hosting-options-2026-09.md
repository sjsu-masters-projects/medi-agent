# Inference and hosting options for MediAgent — September 2026

**Status:** Research complete; decision proposed. **Date:** 2026-09-10. **Tracker:** `AI-002`.
**Companions:** [`ai-use-case-decision-sheet-2026-09.md`](ai-use-case-decision-sheet-2026-09.md)
(what each use case needs and how well it is measured to work),
[`ai-model-routing-spike-2026-09.md`](ai-model-routing-spike-2026-09.md) (model quality
evidence), [`medical-models-landscape-2026-09.md`](medical-models-landscape-2026-09.md)
(which models exist and are licensed).
**Evidence:** five sourced research reports under
[`docs/research/hosting-2026-09/`](../../docs/research/hosting-2026-09/) (NVIDIA ecosystem,
token-priced open-model providers, GPU-hour hosting, hyperscaler APIs and credit programmes,
speech providers), each with a confidence-and-gaps section and a source list dated 2026-09-10.

## 1. The two-minute answer

1. **At demo and single-clinic volume, managed per-token APIs are 5 to 100 times cheaper than any
   GPU we would own, and nothing self-hosted scored higher on our harness.** The whole text
   workload for one clinic costs about $117 a month on Gemini 3.5 Flash-Lite, about $82 on Gemini
   3.1 Flash-Lite, about $40 on `gpt-oss-120b` through Bedrock, and about $19 on `gpt-5-nano`
   through Azure. One always-on L4 costs $360 to $560 a month before licences.
2. **The only GPU shape that pays for itself below ten-clinic scale is scale-to-zero.** Cloud Run
   GPU or RunPod Serverless at two active hours a day is about $46 a month and breaks even against
   Gemini at roughly 31,000 chat turns a month. Every always-warm option needs 185,000 to 392,000
   turns a month. Self-hosting becomes unambiguously cheaper only at the ten-clinic scenario,
   where one L4 no longer has the capacity anyway.
3. **NVIDIA is an evaluation source, not a hosting lane, for us today.** The hosted catalogue is a
   trial service: no published price, no SLA, no BAA, no retirement-notice policy, and terms that
   prohibit sending personal data at all. Running NIM in production requires an AI Enterprise
   licence ($1,125 to $4,500 per GPU per year, or $1 per GPU-hour metered), and Inception requires
   an incorporated company. Open weights can be served with vLLM or Ollama on the same GPU without
   any NVIDIA licence.
4. **Every hyperscaler has a BAA path; only a few specialist providers do.** Vertex, Bedrock, and
   Azure are HIPAA-eligible under their standard agreements, each with a scope caveat to verify;
   neither Google nor Microsoft documents whether their BAA covers third-party open-weight models
   served as a managed service. Anthropic's BAA requires 30-day retention (no zero-retention),
   OpenAI's requires zero-retention plus a BAA. Among open-model hosts, Groq publishes a Business
   Associate Addendum for paid, generally available services (its free tier is excluded), and
   Nebius signs one after review for zero-retention chat endpoints; Fireworks and Baseten state
   HIPAA compliance with zero retention by default but publish no BAA terms. DeepInfra, Together,
   OpenRouter, Novita, Vast.ai, Lambda, Replicate, and Fly.io have no confirmed BAA.
5. **Speech is a solved cost problem and an unsolved Spanish-accuracy problem.** All three viable
   stacks cost $3 to $15 a month for the demo. Deepgram Nova-3 Medical is English-only; AssemblyAI
   is the only vendor with a self-serve BAA and a medical mode that covers Spanish; Google's classic voices have
   no Mexican Spanish, though Gemini text-to-speech now lists `es-MX` in preview. Real Latin American Spanish medical audio measured 14% word error on
   the best commercial system in an independent 2026 study, so our own es-MX vocabulary test is
   mandatory before choosing.
6. **Credits that a non-incorporated capstone team can actually get:** Google Cloud $300 trial,
   Azure for Students $100 per teammate per year, GitHub Student Developer Pack, Microsoft Founders
   Hub Basic (about $1,000), and, through the faculty advisor, Google Cloud Research Credits
   ($5,000) and Anthropic or OpenAI academic programmes. NVIDIA Inception, Google for Startups
   Scale, and the Anthropic and OpenAI startup tracks require incorporation or funding.

## 2. Lanes compared

Monthly cost is for the five text workloads (chat classification and reply, safety classifier,
documents, explanations, SOAP notes) at scenario A (expo), B (one clinic), C (ten clinics), using
the token volumes in the research brief. Voice is separate (§5).

| Lane | Example | A | B | C | BAA path | Lifecycle risk | Fit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Managed Google, current pin | Gemini 3.5 Flash-Lite on Vertex ($0.30 / $2.50) | $7 | $117 | $1,165 | Yes, GCP BAA (verify exact covered-service name) | GA alias; ≥6 months' notice policy for GA retirements | Measured best on every interactive workload; **primary** |
| Managed Google, cheaper pin | Gemini 3.1 Flash-Lite on Vertex ($0.25 / $1.50) | $4.8 | $82 | $820 | Same | GA replacement of a retired preview | Measured fallback; more over-triage |
| Managed hyperscaler, cheapest | `gpt-5-nano` on Azure ($0.05 / $0.40) | $1.2 | $19 | $190 | Azure BAA bundled; text endpoints only | OpenAI cadence | **Unmeasured on our harness**; candidate |
| Managed hyperscaler, mid | GPT-5.6 Luna on Azure or OpenAI ($0.20 / $1.20) | $3.9 | $65 | $649 | Azure bundled; OpenAI needs BAA + ZDR | OpenAI cadence | Unmeasured; candidate |
| Managed hyperscaler, Claude | Claude Haiku 4.5 on Vertex or Bedrock ($1 / $5) | $18 | $297 | $2,969 | GCP or AWS BAA | Anthropic cadence | Unmeasured; Sonnet 5 relevant for PDF citations, not Haiku |
| Open model, BAA path | `gpt-oss-120b` on Bedrock ($0.1545 / $0.618, official) | $2.5 | $42 | $416 | AWS BAA via Artifact, self-serve | Open weights; provider can drop the SKU but the model persists | **Strongest open-model lane**; unmeasured on our harness |
| Open model, Google | `gpt-oss-120b` on Vertex AI managed service ($0.09 / $0.36, official) | $1.4 | $24 | $243 | GCP account BAA; coverage of third-party open models not documented | Same | Cheapest lane with a plausible BAA; confirm scope with Google first |
| Open model, cheapest | `gpt-oss-120b` on DeepInfra tier 1 ($0.037 / $0.17) | $0.6 | $11 | $106 | Not confirmed | Aggregator routing shifts | Synthetic evaluation only until a BAA is confirmed |
| Open model, free tier | `gpt-oss-120b` on Groq (free at 30 RPM; paid $0.15 / $0.60) | $0 | $40 | $404 | Business Associate Addendum on paid GA services; free tier excluded | No 2026 incidents on its status page | $0 evaluation lane on synthetic data; paid tier is a BAA-path alternative |
| Safety classifier | Llama Guard 4 12B on DeepInfra ($0.18 / $0.18) | $0.3 | $6 | $55 | Not confirmed | Only serverless host with a price; absent from Groq, Bedrock, Fireworks, Cloudflare | Synthetic only; a BAA-track classifier must run on our own GPU |
| NVIDIA hosted catalogue | build.nvidia.com trial (≈40 RPM, $0) | $0 | quote only | quote only | **No BAA; PII prohibited by terms** | No notice policy; 410s observed | Synthetic evaluation only |
| Self-hosted L4, scale-to-zero | Cloud Run GPU or RunPod Serverless, 2 h/day | $46 | $46 | needs >1 instance | GCP BAA; RunPod Secure tier | You own the model lifecycle | Classifier, local MedGemma extraction, evaluations |
| Self-hosted L4, warm 12 h | Cloud Run GPU $277; RunPod Secure pod $176 | $176–277 | $176–277 | ×2–3 | Same | Same | Clinic-hours chat only at scale |
| Self-hosted L4, 24/7 | RunPod Secure $358; GCE $518; Cloud Run $562; Vast.ai $146 (no compliance) | $358–562 | $358–562 | ×2–3 | Same (not Vast.ai) | Same | Only at scenario C |
| Self-hosted NIM licence add-on | AI Enterprise: EDU/Inception $94/mo, list $375/mo, metered $730/mo per GPU | + | + | + | Runs inside the cloud's BAA boundary | NVIDIA support cadence | Only if a NIM feature is needed; vLLM needs no licence |
| Self-hosted A100-80GB, 24/7 (32B bf16) | Azure NC A100 v4 $2,681; RunPod Secure $1,161; GCP $3,672; Vertex Model Garden ≈ $4,219 | — | — | $1,161–4,219 | Azure, AWS, GCP, RunPod Secure | — | Only if a 32B model earns it on the harness; none has yet |

Reading the table: the cheapest managed lane (`gpt-5-nano`) and the open-weight lanes
(`gpt-oss-120b` on Bedrock, Vertex, or Groq) cost between a sixth and a third of the current pin.
None has been run through our scenarios. The routing spike's rule stands: nothing is pinned until
it is measured. Open-weight serverless SKUs also move: Cerebras withdrew Gemma 4 31B from public
serverless on 2026-09-03 and retired Qwen 3 32B in February, and Together and DeepInfra logged
multi-hour outages this year, so any open-model lane needs a second provider for the same weights.

## 3. Break-even and capacity

| Hosting option (chat only, vs $0.0015 per turn on Flash-Lite) | Monthly cost | Break-even chat turns per month |
| --- | --- | --- |
| Cloud Run GPU, scale-to-zero, 2 h/day | ≈ $46 | ≈ 31,000 |
| Vast.ai L4 24/7 (no compliance, eviction risk) | ≈ $146 | ≈ 97,000 |
| Cloud Run GPU, warm 12 h/day | ≈ $277 | ≈ 185,000 |
| RunPod Secure Cloud L4 24/7 | ≈ $358 | ≈ 239,000 |
| GCE g2-standard-4 24/7 | ≈ $518 | ≈ 345,000 |
| EC2 g6.xlarge 24/7 | ≈ $588 | ≈ 392,000 |

Scenario A (3,000 turns) clears nothing; B (60,000) clears only scale-to-zero; C (600,000) clears
everything. Offloading documents, explanations, and SOAP to the same GPU lowers every threshold
somewhat, but the GPU report's capacity estimate says one L4 running a 12B-class model in bf16
covers about 12% of its ceiling at B and is over its ceiling at C, so C needs two or three
instances or a larger GPU. The throughput numbers are scaled estimates from an A100 benchmark,
not L4 measurements, and a 12B model in bf16 leaves almost no KV-cache room on 24 GB, so
quantization would be required. A 4B-class model (MedGemma 1.5, Gemma 4 e4b) fits with headroom.

## 4. Data handling and compliance posture

| Provider | Training on inputs | BAA | Retention | Notes to verify before PHI |
| --- | --- | --- | --- | --- |
| Google Vertex AI | No | GCP BAA | Configurable, no logging by default | Exact covered-service naming for Vertex generative inference; whether third-party open models on the managed service are in scope |
| Google AI Studio free tier | Yes, plus human review | None | — | Never for anything but synthetic data; this project's key is also out of credit |
| AWS Bedrock | No | AWS BAA via Artifact, self-serve; one BAA covers all models | No retention by default | One source lists model exclusions; check the live eligible-services page |
| Azure OpenAI / Foundry | No | Bundled in the DPA for EA/CSP agreements | Abuse monitoring, opt-out available | Production text endpoints only; previews and audio excluded |
| Anthropic first-party | No by default | HIPAA-ready orgs; **30-day retention required, incompatible with ZDR** | 30 days | Claude API and Enterprise only |
| OpenAI first-party | No | BAA at baa@openai.com **plus ZDR**, both required | ZDR on eligible endpoints | Chat Completions and Responses only; Batch, Files, Assistants excluded |
| Groq | Not used for training unless permitted | Published Business Associate Addendum for paid, generally available services; free tier, beta, and preview excluded; acceptance step not stated | Deleted within 30 days of termination; zero-retention setting for eligible customers | Confirm how the addendum is accepted before PHI |
| Nebius Token Factory | Not stated | BAA after account-manager review | Zero retention mandatory | Chat and completions endpoints only; fine-tuning, batch, embeddings, files excluded |
| Fireworks, Baseten | Zero retention by default for open models or synchronous inference | State HIPAA compliance; BAA terms not in public docs | Zero retention by default | Request the BAA from sales or the trust centre |
| Together, DeepInfra, OpenRouter, Novita, Cerebras, SambaNova | Varies | Not confirmed; Together's third-party "HIPAA compliant" listing is not backed by its own docs | Varies | Synthetic evaluation only |
| NVIDIA build.nvidia.com | "Solely to provide the service" | None | Not guaranteed | Terms prohibit personal data outright |
| RunPod Secure Cloud, Modal (GPU hosting) | You control | Compliance tiers exist | You control | Tier-dependent; confirm in contract |
| Vast.ai, Lambda, Replicate, Fly.io, OCI, HF Endpoints (standard) | You control | Not confirmed | You control | Do not plan PHI here |
| Deepgram | Model-improvement programme, opt-out per request | Enterprise plan | Fractional retention under the programme | Ask for Enterprise before PHI |
| AssemblyAI | Opt-out on streaming | Self-serve BAA, no premium | Zero retention on streaming | Session-time billing |
| Azure Speech, Google STT/TTS, AWS Transcribe/Polly | No | Bundled / covered / eligible | Not persisted (Azure real-time), no logging (Google) | Google STT must not opt into data logging |

## 5. Voice

| Stack | A (900 min) | B (9,000 min) | C (90,000 min) | Spanish and medical fit | BAA |
| --- | --- | --- | --- | --- | --- |
| Deepgram Nova-3 multilingual + Aura-2 es-MX voices (promo streaming rate) | $12.85 | $128.52 | $1,285 | Code-switching in both directions; keyterm prompting; **Nova-3 Medical is English-only** | Enterprise only |
| Google STT v2 Chirp 3 + Chirp 3 HD | $8.64 | $153.60 | $1,806 | es-MX STT in preview; classic voices are es-US only, Gemini-TTS lists es-MX in preview; same GCP BAA | Covered |
| AssemblyAI Universal-Streaming Multilingual + Medical Mode + Azure Neural es-MX | $2.70–10.26 | $71–103 | $780–1,026 | Only vendor with Spanish medical mode; 14 es-MX voices on Azure; two vendors | Self-serve (AssemblyAI) + bundled (Azure) |
| OpenAI gpt-4o-mini-transcribe + gpt-4o-mini-tts | $7.02 | $70.20 | $702 | English-centric voices, no es-MX voice | BAA + ZDR |
| Self-hosted Parakeet or Whisper + Kokoro/Piper on a warm L4 | ≈ $18 | ≈ $169 | ≈ $339 | Weak drug-name accuracy; Piper es-MX voices are low quality | GCP BAA boundary |

Independent evidence on real Latin American Spanish medical consultations (medRxiv, July 2026):
Gemini 2.5 Pro 14.0% WER (best commercial), Whisper Large v3 18.6% WER (best open). Vendor
FLEURS numbers (3–5% WER) do not transfer to clinical audio. Decision rule: run one 50-utterance
es-MX medication script through Deepgram `multi` with keyterms, AssemblyAI Medical Mode,
Speechmatics Spanish Medical, and Gemini 3.5 Transcribe with biasing, and score keyword error rate
before any voice provider is pinned.

## 6. Credits and programmes a capstone team can use

| Programme | Amount | Realistic for an unincorporated SJSU team |
| --- | --- | --- |
| Google Cloud free trial | $300, 90 days | Yes; time it to an evaluation window |
| Azure for Students | $100 per year per student | Yes; each teammate |
| GitHub Student Developer Pack | Partner credits, Copilot | Yes |
| Microsoft for Startups Founders Hub, Basic | ≈ $1,000 Azure | Plausible (email verification) |
| AWS Activate Founders | $1,000 | Maybe; needs a project site and paid account |
| Google Cloud Research Credits (higher-ed) | $5,000 via faculty or postdoc | Maybe; apply through the advisor |
| Anthropic academic and research calls | $500–25,000, proposal-based | Maybe; periodic and thematic |
| OpenAI Researcher Access | up to $1,000 | Maybe; framed as safety evaluation research |
| Groq and Fireworks startup credits | $10,000 each | Maybe; entity requirement unclear |
| NVIDIA Inception | up to $100k credits, 75% off AI Enterprise | **No** until incorporated |
| Google for Startups Scale/AI-First, Anthropic and OpenAI startup tracks, Together | $25k–350k | **No**; equity funding or entity required |

## 7. The decision

1. **Serve on Vertex Gemini through the expo and the first clinic.** Budget $10 a month for the expo
   and $120 to $150 a month for a clinic including voice on Deepgram credits. Keep the measured
   pins from the routing spike.
2. **Measure the cheaper lanes before switching anything:** `gpt-oss-120b` (open weights; on
   Bedrock under the AWS BAA, on Vertex if Google confirms open-model BAA scope, or on Groq's paid
   tier under its addendum) and `gpt-5-nano` on Azure. They cost a third to a sixth of the current
   pin. Run them through the 70-scenario harness; adopt one only if it meets the same thresholds,
   and keep Vertex Gemini as the fallback. Groq's free tier gives the `gpt-oss-120b` measurement
   at $0 on synthetic data.
3. **Add one scale-to-zero L4 (Cloud Run GPU) at about $46 a month** for the safety classifier,
   MedGemma 1.5 4B document extraction, and evaluation runs. No serverless provider with a BAA path
   hosts Llama Guard 4 or MedGemma, so this is their only compliant home. Do not keep any GPU warm
   before ten-clinic scale, and never re-deploy a 27B endpoint.
4. **Do not treat NVIDIA as a hosting lane.** Keep build.nvidia.com for synthetic-data evaluation
   and OCR second opinions behind a flag. Revisit NIM only if the team incorporates and qualifies
   for EDU/Inception licence pricing, and only for a feature vLLM cannot provide.
5. **Voice:** Deepgram now; when a BAA is required, AssemblyAI Medical Mode for STT and Azure
   Neural es-MX voices for TTS, chosen on the es-MX script test, not on list price.
6. **Claim the realistic credits now** and route the larger academic asks through the faculty
   advisor; decide separately whether to incorporate, since that unlocks NVIDIA Inception, Google
   for Startups, and the AI Enterprise discount.
7. **Before any BAA-dependent deployment,** verify on the vendor's live page: the exact covered
   service name on Google's HIPAA list, Bedrock's model exclusions, Azure's text-only scope, and
   the retention terms on whichever speech vendor is chosen.

## 8. Confidence and gaps

- The session's web-search budget was exhausted partway through the research; several official
  pricing pages (Google Cloud Run and GPU pricing, EC2 on-demand, OpenAI pricing) did not render
  for automated fetching, so many numbers come from two to four independent aggregators rather
  than the vendor page. Each report marks per-figure confidence.
- L4 throughput is estimated by scaling an A100 benchmark; treat capacity conclusions as
  directional and load-test before procurement.
- The token-priced provider report was completed after the first version of this document; its
  BAA statements for Groq, Nebius, Fireworks, and Baseten were checked against each vendor's own
  pages on 2026-09-10. Hyperbolic's pricing and limits could not be confirmed from any public
  source.
- Vertex Model Garden scale-to-zero eligibility for Gemma and MedGemma deployments is unconfirmed;
  the default is one replica always on.
- No SLA percentages were captured for any provider.
- `gpt-5-nano`, GPT-5.6 Luna, `gpt-oss-120b`, and Claude Haiku 4.5 have not been run through the
  MediAgent harness; their cost advantage is real, their quality on our workloads is unknown.
- Corrected 2026-09-15: Gemini 3.1 Flash-Lite's interactive list price is $0.25 in and $1.50 out.
  The $0.125 and $0.75 figures first used here are its batch and Flex price, which understated
  that lane by about half.

## 9. Verified against Google's documentation, 2026-09-15

Checked through the Developer Knowledge documentation service, which replaced the aggregator
sources for everything below.

**Endpoints retiring before the expo.** These managed open-model endpoints on Vertex were
deprecated on 2026-07-21 and retire on 2026-10-21: `qwen3-next-80b-a3b-instruct-maas` and its
thinking variant, `glm-4.7-maas`, `glm-5-maas`, `deepseek-ocr-maas`, `deepseek-v3.1-maas`,
`deepseek-v3.2-maas`, `deepseek-r1-0528-maas`, `gpt-oss-20b-maas`, `llama-3.3-70b-instruct-maas`,
`kimi-k2-thinking-maas`, `minimax-m2-maas`, both `multilingual-e5` embedding endpoints,
`qwen3-235b-a22b-instruct-2507-maas`, and `qwen3-coder-480b-a35b-instruct-maas`. Not affected:
`gpt-oss-120b-maas`, generally available, and `gemma-4-26b-a4b-it-maas`, which is at the
Experimental launch stage.

**Gemini lifecycle.**

| Model | Stage | Guaranteed until |
| --- | --- | --- |
| `gemini-3.5-flash-lite` | GA | 2027-07-21 or later |
| `gemini-3.5-flash` | GA | 2027-05-19 or later |
| `gemini-3.1-flash-lite` | GA | 2027-05-07 or later |
| `gemini-3.6-flash`, `gemini-3.7-flash`, `gemini-3.8-flash` | GA, short-term availability | Retire 45 days after a replacement ships |
| `gemini-3.1-pro-preview` | Preview | No date announced |

**Standard prices, per million input and output tokens.**

| Model | Input | Output | Note |
| --- | --- | --- | --- |
| `gemini-3.1-flash-lite` | $0.25 | $1.50 | Batch and Flex are half |
| `gemini-3.5-flash-lite` | $0.30 | $2.50 | Batch and Flex are half |
| `gemini-3.5-flash` | $1.50 | $9.00 | |
| `gemini-3.7-flash`, `gemini-3.8-flash` | $0.75 | $3.75 | Introductory through 2026-12-31, then $1.50 and $7.50 |
| `gemini-3.1-pro-preview` | $2.00 | $12.00 | Prompts up to 200k tokens |
| `gpt-oss-120b-maas` | $0.09 | $0.36 | |

**Capacity on demo day.** Standard pay-as-you-go assigns a baseline throughput by the
organization's spend over 30 days, starting at $10 for the first tier. Those tiers cover Gemini
3.5 Flash and 3.1 Flash-Lite, but not 3.5 Flash-Lite, the 3.6 to 3.8 Flash models, or preview
models, which run on best-effort shared capacity. A 429 there means pool contention, not a quota
that was used up. Google's guidance is the global endpoint, exponential backoff, and smooth
traffic, or Provisioned Throughput for a guarantee. In the first scenarios of today's run,
Gemini 3.8 Flash and the Gemma 4 managed endpoint returned 429 on several calls that succeeded
when repeated seconds later.

**Claude on Vertex.** The global endpoint path works, but this project receives
quota-exceeded errors. The documentation says quotas vary by account and access can be
restricted, so Claude needs a quota increase request against the `anthropic-claude-sonnet` base
model before it can be measured.

**Gemini 3.5 Transcribe.** Preview, global endpoint only. Spanish (Latin America, `es-419`) is
marked Experimental, Spanish (United States, `es-US`) is Supported, and there is no `es-MX` code.
About $0.005 a minute for files and $0.009 a minute live.

**Scale-to-zero for self-deployed models.** Preview. The first request after idling is answered
with a 429 and dropped while a replica starts, the shortest idle period before scaling down is
five minutes, capacity can be unavailable without a reservation, and a model idle for 30 days is
undeployed. Model Garden's default deployment for a small open model is a `g2-standard-12` with
one L4. For a live demo, send a warm-up request before visitors arrive.

**Model Armor is not the self-harm layer.** Its content filters cover hate speech, harassment,
sexual content, dangerous content, violence, and CSAM, plus prompt-injection and jailbreak
detection and sensitive-data screening. There is no self-harm or suicide category. When
integrated with Gemini it skips screening if the service is unavailable or errors, so it fails
open. It is a reasonable prompt-injection screen for the chat, billed separately, but the
self-harm layer remains the keyword floor plus a classifier such as Llama Guard 4 on our own GPU.

**Mexican Spanish voices now exist on Google.** Gemini text-to-speech (`gemini-2.5-flash-tts`,
`gemini-2.5-pro-tts`, `gemini-3.1-flash-tts-preview`) lists Spanish (Mexico, `es-MX`) and Spanish
(Latin America, `es-419`) at the Preview stage, on the global endpoint through either the Cloud
Text-to-Speech or Vertex API. Gemini 3.1 Flash TTS is billed at $1 per million text input tokens
and $20 per million audio output tokens, at 25 audio tokens a second, which is about $0.03 a
minute of speech and close to Deepgram Aura-2. This keeps a single-vendor Google voice stack
possible, subject to the same Mexican Spanish listening test as every other option.


## 10. Expo model measurement and decision, 2026-09-15

All 70 synthetic scenarios ran against eight Vertex models on the global OpenAI-compatible
endpoint (`backend/reports/ai_eval_20260915_194824`, 560 of 560 scored). Thinking models ran
at low reasoning effort, and the harness retried 429 and transient 5xx responses with backoff.
MedGemma 1.5 4B ran on 28 scenarios on a temporary endpoint
(`backend/reports/ai_eval_20260915_201947`). Each workload has 8 to 28 scenarios, below the
spike's 120-scenario bar, so treat gaps of a few points as noise.

**Score by workload** (answered share in brackets when below 100%).

| Model | Triage | Explanation | Discrepancy | Symptom/ADR | Documents | Answered overall |
| --- | --- | --- | --- | --- | --- | --- |
| 3.5 Flash-Lite | 98% | 98% | 86% | 79% | 64% | 100%, no retries |
| 3.7 Flash, low | 96% | 94% | 95% | 98% | 47% | 99% |
| 3.5 Flash, low | 93% | 98% | 88% | 100% | 62% | 97%, 27% needed a retry |
| 3.1 Pro preview | 91% | 100% | 100% | 100% | 33% | 99%, p50 6–29 s |
| 3.1 Flash-Lite (current default) | 91% | 87% | 33% | 38% | 35% | 97%, schema-valid 40–50% on structured work |
| gpt-oss-120b | 98% | 89% | 71% | 61% | 46% | 100%, safety 67–96% |
| 3.8 Flash, low | 86% | 86% | 90% | 70% | 12% | 77%, rate-limited and timeouts |
| Gemma 4 managed | 80% | 80% | 51% | 35% | 18% | 79%, rate-limited and timeouts |
| MedGemma 1.5 4B | — | 89% | — | 55% | 49% | 100%, p50 7–14 s |

**Decision for the expo.**

| Workload | Primary | Fallback | Why |
| --- | --- | --- | --- |
| Triage classification (after the keyword floor) | 3.5 Flash-Lite | 3.1 Flash-Lite | 98% with every safety check passed, p95 1.4 s; the fallback is tier-covered and fast |
| Patient explanation and chat reply | 3.5 Flash-Lite | 3.1 Flash-Lite | 98%, p50 2.3 s; the fallback kept 100% safety at p95 3.3 s |
| Medication discrepancy | 3.7 Flash, low | 3.5 Flash-Lite | 95% with correct abstention; clinician-side, so a 3 s p50 is acceptable |
| Symptom and ADR extraction | 3.7 Flash, low | 3.5 Flash-Lite | 98% with every red flag caught; the fallback never needed a retry |
| Document extraction | 3.5 Flash-Lite | 3.5 Flash | No model passed 64%, so accuracy comes from the OCR and evidence pipeline and clinician review, not a larger model |

Not integrated for the expo: MedGemma (below Flash-Lite on every workload, needs a GPU
endpoint at about $2 an hour), Gemma 4 and 3.8 Flash (a fifth of calls failed after retries),
gpt-oss-120b (missed safety checks on patient-facing workloads), 3.1 Pro (preview, slowest,
most expensive, weakest on documents), and 3.1 Flash-Lite as a primary for structured output.

**Expo cost.** At 2,000 chat turns, 300 explanations, 300 documents, 200 discrepancy checks, and
200 symptom reports, the recommended mix costs about $3.90 in tokens. 3.1 Pro across the board
would be about $19.50.

**Demo-day reliability.** 3.5 Flash-Lite and 3.7 Flash run on shared capacity that the spend
tiers do not cover, and the project is below the first tier anyway. Keep the backoff retries
and the fallback wired in the router, warm each workload before visitors arrive, and price
Priority pay-as-you-go for the expo days before enabling it. 3.7 Flash is a short-term model
that retires 45 days after its replacement ships, so recheck its status the week before the freeze.

### 10.1 What the failures actually were, analysed 2026-09-16

The §10 table mixes three unrelated causes. Separated, the picture changes, and the document
column is not yet a fair measurement of the models.

**Cause 1: shared capacity, not answer quality.** Gemini 3.8 Flash lost 16 of 70 calls (9
rate-limited, 7 timed out) and the Gemma 4 managed endpoint 15 (9 and 6). Scored only on calls
that came back and parsed, 3.8 Flash is the strongest model in the field at 96%. It is
unobtainable at our spend tier, not weak.

**Cause 2: truncation from a repetition loop.** 17 of Gemini 3.1 Flash-Lite's 19 failures are
unterminated JSON: it repeats a fragment ("Atorvastatin, Metformin, Atorvastatin, …") until the
token budget runs out. That is a real weakness of the current default model.

**Cause 3: our own harness, on the document workload.**

- The evidence `page` field is a required integer, but 9 of the 10 document fixtures carry no
  page markers, so the model must invent a number it cannot know. Five scenarios produced a
  degenerate digit run — `"page": 10000000…` for thousands of digits — across 3.1 Flash-Lite,
  3.5 Flash-Lite, 3.7 Flash, and 3.1 Pro, and each one scored zero. Python's 4300-digit integer
  limit then surfaced it as a parse error.
- `evidence` is optional in `DocumentExtractionOutput`, and the addendum never requires a quote
  per item, so the Gemini models omitted evidence in 8 of 10 outputs. The score ignores evidence
  entirely, so anchoring was effectively untested for them.
- MedGemma ran with `native_schema: false`, because its vLLM container rejects our nullable
  types, while every Gemini model had constrained decoding. All 7 of its unparsed outputs are
  packaging, not content: `severity: null` against an int field, `symptom` as a list, a
  top-level array, and two JSON blocks in one reply.

**Scored only on calls that returned and parsed:** 3.8 Flash 96%, 3.5 Flash 94%, 3.7 Flash 92%,
3.1 Pro 92%, 3.5 Flash-Lite 89%, 3.1 Flash-Lite 87%, MedGemma 83%, gpt-oss-120b 80%, Gemma 4 77%.

**On documents, MedGemma is the most accurate reader we measured**: 55 of 61 required fields
(90%) against 3.5 Flash's 75% and 3.5 Flash-Lite's 66%, with 21 of 25 evidence quotes verified
in the source against 0 of 27 for 3.5 Flash-Lite. It emitted an evidence field in 9 of 10
outputs; the Gemini models did so in 2 to 4.

**A prompt bug affects every model's severity score.** The symptom extraction prompt shows
`"severity": 1` in its example and never states the 1-to-10 scale. MedGemma, gpt-oss, and
Gemma 4 answered 1 almost every time, including for rhabdomyolysis symptoms whose expected
range is 7 to 10. The larger Gemini models inferred the scale. Part of the measured "medical
weakness" of the small models is our example anchoring them.

**Consequences for §10.** The triage, explanation, discrepancy, and symptom rows stand. The
document row does not: fix the page field, require an evidence quote per item, state the
severity scale, and re-run that workload before choosing a document model. MedGemma belongs in
that re-run, because ingestion is batch work where its 7-to-14-second latency costs little,
against a GPU endpoint at roughly $2 an hour. Gemini 3.8 Flash stays out of the expo for
capacity reasons, not quality.

**Correction, 2026-09-17: documents are not a model choice.** The OCR spike
(`docs/document-intelligence-assessment.md`) already decided this workstream: a
deterministic reader (pypdfium2 plus PaddleOCR PP-OCRv5 via RapidOCR) does the reading,
the model only structures the resulting page-marked text, and deterministic anchoring
verifies every value against the page. Choosing a "document model" from the §10 table is
the wrong question — that column measured a model doing OCR's job under a schema that
forbade evidence. The document row is withdrawn pending the re-run described in
`eval-harness-protocol-2026-09.md` §9.

## 11. Expo decision, measured 2026-09-17 (replaces §10)

§10's table was produced by a harness that charged rate limits, truncation, a lenient drug
matcher and a self-contradicting schema to the models. It is withdrawn. These numbers come
from the rebuilt harness (`eval-harness-protocol-2026-09.md` §14).

| Use case | Integrate | Why, from the measurement |
| --- | --- | --- |
| Triage after the keyword floor | gpt-oss-120b, fall back to Gemini 3.8 Flash | 100% accuracy and no under-triage; ~10x cheaper; 2.2 s median. It occasionally breaks the output schema, so the caller validates and retries |
| Symptom and ADR extraction | gpt-oss-120b or 3.8 Flash | 98% and 96%, no measurable difference, both never missed a red flag |
| Medication discrepancy | **Gemini 3.8 Flash** | The one workload with a real separation from thresholds: 94% recall against gpt-oss's 71%, and both beat MedGemma significantly |
| Patient explanation | Any of them; prefer gpt-oss on cost | 91-98% across all four models, no pair distinguishable |
| Document reading | Not a model decision — see the OCR spike | Deterministic reader plus anchoring; the model only structures page-marked text |

**Not integrated: MedGemma** — for corrected reasons. It under-triaged urgent cases (79%
and 75% against 100%), could not hold the output contract on this serving configuration,
and cost about $3 of GPU for 91 minutes against 7 cents of tokens for the entire cloud leg.
An earlier draft said it "missed every allergy conflict"; that was wrong. Unconstrained it
found both, and lost the points to our own prompt template — it copied the literal enum
menu `"missing_medication | dose_mismatch"` into a `type` field in 4 of 14 answers, which
no other model did. Google publishes MedGemma 1.5 4B at MedQA 69.1 and MMLU-Med 69.6,
well above its own base Gemma 3 4B (50.7, 67.2) but far below MedGemma 1 27B (85.3, 86.2).
Its medical tuning is real; a 4B model simply cannot match a 120B general model at
instruction-following, and our workloads are contract-following and reconciliation rather
than the multiple-choice recall those benchmarks measure.

**Expo reliability.** Both cloud models lose calls to shared capacity (5 and 3 of 70), and
tail latency reaches 77-95 s against medians under 9 s. Keep the retries and per-workload
fallback, warm each path before visitors arrive, and price Priority pay-as-you-go for the
expo days.
