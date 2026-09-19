# NVIDIA Inference Ecosystem as a Hosting Option for MediAgent

Research date: 2026-09-10. All prices in USD unless noted. "Not found" means no
authoritative (preferably NVIDIA-published) number was located in this pass —
it is not a guess.

---

## 1. build.nvidia.com API catalog (hosted NIM endpoints)

### 1.1 Access and free tier

- Sign-up is via the NVIDIA Developer Program (email only, no credit card, no
  company requirement). Confirmed via developer.nvidia.com blog announcing
  free NIM access to Developer Program members (developer.nvidia.com/blog/access-to-nvidia-nim-now-available-free-to-developer-program-members/,
  originally published 2024-07-29, seen 2026-09-10).
- **Credit system status is unclear / apparently changed.** Multiple
  third-party trackers (not NVIDIA-official) report that build.nvidia.com
  historically granted 1,000 free inference credits per personal account
  (5,000 for an enterprise-domain email), and that by 2026 NVIDIA removed the
  credit system in favor of a flat, rate-limited "forever free" tier instead
  (costbench.com/software/llm-api-providers/nvidia-nim/free-plan/;
  yangmao.ai/en/providers/nvidia-build/free-tier/; both seen 2026-09-10). **I
  could not confirm this directly on an official NVIDIA page** — the
  build.nvidia.com sign-up/account pages require an authenticated session and
  did not return usable content to the fetch tool. Treat the "credits are
  gone, replaced by rate limits" claim as medium confidence.
- No credit-card requirement and no published expiry date for the free tier
  itself was found (as opposed to any one-time credit grant, which multiple
  trackers say no longer applies).

### 1.2 Rate limits

- Aggregator/forum consensus (not an official NVIDIA pricing page): free-tier
  key is capped around **40 requests/minute**, shared across all models
  called with that key, with the ability to request an increase to roughly
  **200 RPM** (yangmao.ai/en/providers/nvidia-build/; decodethefuture.org/en/nvidia-nim-api-pricing-limits-guide/;
  both seen 2026-09-10). No official build.nvidia.com rate-limit table was
  reachable via fetch to confirm this first-hand — **medium confidence**.
- The official NIM product FAQ (docs.api.nvidia.com/nim/docs/product, seen
  2026-09-10) does not publish a rate-limit number at all.

### 1.3 Paid tier / per-token pricing

- **No public per-token price list exists for build.nvidia.com hosted
  endpoints.** The official FAQ and model pages I fetched (build.nvidia.com/openai/gpt-oss-120b,
  /openai/gpt-oss-20b, /meta/llama-4-scout-17b-16e-instruct, /meta/llama-guard-4-12b,
  all seen 2026-09-10) show no price field — only license/terms text.
- Third-party trackers describe a "Pay-as-you-go (hosted NIM endpoints)"
  tier that is **quote-only via NVIDIA sales**, with one tracker citing an
  unverified blended range of roughly $0.04–$1.20 per million tokens
  depending on model (pricepertoken.com/pricing-page/provider/nvidia; seen
  2026-09-10). **This is not an NVIDIA-published number — treat as
  illustrative only**, and it is used that way in §6.
- Conclusion for MediAgent: there is currently no self-serve, credit-card,
  pay-as-you-go path with a published price on build.nvidia.com. Any paid
  production use of the hosted catalog requires talking to NVIDIA sales.

### 1.4 Models of interest — hosted-catalog availability

| Model | Hosted on build.nvidia.com? | Evidence | Notes |
|---|---|---|---|
| gpt-oss-120b | Yes | build.nvidia.com/openai/gpt-oss-120b (seen 2026-09-10) | Apache-2.0 weights; NVIDIA API Trial ToS + NVIDIA Community Model License govern the hosted endpoint |
| gpt-oss-20b | Yes | build.nvidia.com/openai/gpt-oss-20b (seen 2026-09-10) | Same licensing stack |
| Gemma 4 (31B-IT confirmed) | Yes (at least the 31B-IT variant) | build.nvidia.com/google/gemma-4-31b-it/modelcard (seen 2026-09-10) | Governed by NVIDIA Open Model License Agreement / Apache-2.0; e4b/12b/26B-A4B variants not individually confirmed hosted — **not found** for those specific sizes |
| Qwen 3.6 (8B–32B) | Partially confirmed | NGC catalog lists Qwen3.6-35B-A3B as a self-host NIM container (catalog.ngc.nvidia.com/orgs/nim/teams/qwen/containers/qwen3.6-35b-a3b, seen 2026-09-10); NVIDIA technical blog says Qwen3-Next family is available "free using NVIDIA-hosted NIM microservice endpoints in the API catalog" | Hosted-catalog presence specifically for the 8B–32B dense Qwen3.6 sizes MediAgent cares about is **not confirmed** — what's clearly documented is self-hosted NIM containers |
| Llama 4 Scout / Maverick | Scout confirmed hosted | build.nvidia.com/meta/llama-4-scout-17b-16e-instruct (seen 2026-09-10) | Fits a single H100 with int4; Maverick page not independently confirmed in this pass — **not found** |
| Llama Guard 4 12B | Yes | build.nvidia.com/meta/llama-guard-4-12b (seen 2026-09-10) | vLLM inference engine; governed by NVIDIA Community Model License + Meta Llama 4 Community License |
| MedGemma 1.5 4B | **Not found on build.nvidia.com** | build.nvidia.com/google/medgemma returned HTTP 404 (checked 2026-09-10); Google distributes MedGemma via Hugging Face and Vertex AI Model Garden under HAI-DEF terms (developers.google.com/health-ai-developer-foundations/medgemma, seen 2026-09-10) | If MediAgent wants MedGemma on NVIDIA infrastructure, it would have to be self-deployed (e.g., via TensorRT-LLM/vLLM) rather than pulled from NVIDIA's catalog — no NVIDIA-packaged MedGemma NIM was found |
| Baichuan-M2 32B | Not checked / **not found** | — | Out of scope for the fetch budget available; no evidence either way |
| Llama Guard 4 12B | (see above) | | |
| PaddleOCR NIM | Yes, self-host container; hosted-API status unclear | build.nvidia.com/baidu/paddleocr/modelcard exists per search index (seen 2026-09-10); NGC container catalog.ngc.nvidia.com/orgs/nim/baidu/containers/paddleocr confirms a downloadable NIM container | Apache-2.0 licensed; "commercial use" ready |
| Nemotron-Parse (2.0) | Yes | build.nvidia.com/nvidia/nemotron-parse/modelcard (seen 2026-09-10) | Nemotron-Parse 1.1 confirmed on catalog (900M-param ViT-H encoder + mBART decoder); "2.0" specifically **not confirmed** — only 1.1 verified in this pass |
| Nemotron OCR v1 | Yes | build.nvidia.com/nvidia/nemotron-ocr-v1/modelcard (seen 2026-09-10) | NVIDIA Open Model License Agreement; **test hardware explicitly lists L4** alongside H100/A100/L40S/A10G — directly relevant to a single-L4 self-host plan (§6) |

### 1.5 Terms of use — data logging, training, PII

Source: NVIDIA API Trial Terms of Service PDF (assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf) and an NVIDIA-staff forum clarification quoting it section-by-section (forums.developer.nvidia.com/t/clarification-on-trial-api-use/334275, seen 2026-09-10). The PDF itself is a compressed binary stream that the fetch tool could not render as text, so the section numbers below come from the forum's direct quotes of it, not a first-hand read of the PDF:

- Per the quoted §2.2–2.3: NVIDIA uses "User Content and Generated Content
  solely to provide users with the API Service" — i.e., the trial terms as
  quoted do **not** describe using prompts/outputs to train NVIDIA's models.
- Per the quoted §3.3: operational data (session metrics, error/execution
  logs) is collected separately from prompt/response content, for security,
  fraud, and abuse monitoring, and may be shared with third-party service
  providers for that purpose.
- Per the quoted §2.7: NVIDIA reserves the right (not an obligation) to
  "block, monitor, scan or review communications or User Content or
  Generated Content."
- **PII/PHI is explicitly prohibited**: the trial terms bar users from
  "collect[ing] or stor[ing] any personal data or personally identifiable
  information through the service." This is an important finding for
  MediAgent: even leaving HIPAA aside, the hosted trial catalog's own terms
  say not to send PII/PHI to it at all. Synthetic-data-only prompts would be
  compliant with this; real patient data would not be, independent of any
  BAA question.
- This is a **trial** service (the terms document is literally titled "API
  Trial Terms of Service"), which is consistent with there being no SLA (see
  §1.6) and no stated retention-period guarantee beyond "as needed to
  provide the service."

### 1.6 SLA

- No SLA is offered on the free/trial build.nvidia.com catalog. Aggregator
  summary: "AI Enterprise becomes the relevant choice ... [when] you need
  SLA-backed uptime ... enterprise SLAs with defined uptime guarantees ...
  24/7 NVIDIA support" (multiple trackers, e.g. decodethefuture.org, seen
  2026-09-10) — i.e., SLA-backed uptime is an AI Enterprise benefit, not a
  build.nvidia.com hosted-catalog benefit. I could not find an NVIDIA-first
  page stating an explicit uptime percentage even for AI Enterprise; only
  that Business Critical support includes a **1-hour response time for
  Severity 1 cases** (docs.nvidia.com/enterprise-support-and-services-user-guide,
  seen 2026-09-10). No SLA at all applies to the trial API.

### 1.7 Endpoint retirement practice

This is a real and documented risk, though the evidence for exact wording
came through search snippets more reliably than through direct page fetches
(the build.nvidia.com model pages are React/SPA and the fetch tool's
markdown conversion sometimes drops JS-rendered banners — flagged in
Confidence and Gaps):

- **nemoretriever-ocr / nemoretriever-ocr-v1**: a search-indexed snippet of
  the live build.nvidia.com model page shows the banner text "**Please
  transition to another model to avoid any service interruptions**" (found
  via web search of build.nvidia.com/nvidia/nemoretriever-ocr-v1 and
  /nemoretriever-ocr, seen 2026-09-10). Direct WebFetch of the same URL did
  not reproduce the banner text (returned only the page title), which is
  consistent with the banner being injected client-side and not part of the
  static/markdown snapshot the fetch tool retrieves.
- **nemoretriever-page-elements-v3**: a third-party tracker states this
  model "was deprecated on 05/18/2026 and is no longer supported after that
  date" (aggregator search snippet, seen 2026-09-10) — **not independently
  confirmed on an NVIDIA page** in this pass; treat the specific date as
  medium confidence.
- **writer/palmyra-med-70b**: search results surfaced a documentation
  reference URL literally named **docs.api.nvidia.com/nim/reference/disabled-writer-palmyra-med-70b**
  (search-indexed title "writer / palmyra-med-70b", seen 2026-09-10),
  strongly suggesting NVIDIA prefixes retired-endpoint reference docs with
  `disabled-`. Direct WebFetch of that exact URL returned HTTP 404 at the
  time of this research, and a WebFetch of the live marketing page
  build.nvidia.com/writer/palmyra-med-70b showed no visible deprecation
  banner and described the model as "ready for non-commercial use." **This
  is contradictory evidence I could not fully resolve**: either the model
  has since been fully removed (404, past the "disabled-" grace period) while
  the marketing/model-card page lingers, or the search engine indexed a
  stale/cached title. Treat "palmyra-med-70b is retired or being retired"
  as medium confidence, corroborated by the model card's own explicit
  disclaimer (see §5) that it must not be used for "direct patient care,
  clinical decision support, or professional medical purposes" — which
  excludes it from MediAgent's use case regardless of hosting status.
- **General retirement policy**: no NVIDIA-published notice-period policy
  (e.g., "N days' notice before an endpoint is retired") was found anywhere
  in developer.nvidia.com, docs.nvidia.com, or the API catalog docs. NVIDIA's
  own "Dynamic Page Retirement" doc (docs.nvidia.com/deploy/dynamic-page-retirement/)
  is about driver/DCH pages, not API endpoints, and is unrelated. **Endpoint
  lifecycle risk on the hosted catalog should be treated as
  short-notice/best-effort, not contractually guaranteed**, consistent with
  it being a "trial" service (§1.5).

---

## 2. NIM self-hosted licensing

| Item | Value | Source | Date seen |
|---|---|---|---|
| Developer Program free self-host limit | Up to **16 GPUs** (2 nodes), for research/application development/experimentation only | developer.nvidia.com/blog/access-to-nvidia-nim-now-available-free-to-developer-program-members/; corroborated by docs.api.nvidia.com/nim/docs/product FAQ | 2026-09-10 |
| Support under free tier | Community support via NVIDIA Developer Forums only, no enterprise SLA | Same sources | 2026-09-10 |
| What counts as "production" | Official FAQ definition: "any use of NIM for purposes other than development, testing, research or evaluation such as conducting business transactions and any non-testing activity including activity serving real end-users" | docs.api.nvidia.com/nim/docs/product | 2026-09-10 |
| AI Enterprise — self-managed, 1 year | $4,500 / GPU | docs.nvidia.com/ai-enterprise/planning-resource/licensing-guide/latest/pricing.html (official NVIDIA docs page) | 2026-09-10 |
| AI Enterprise — self-managed, 2 years | $9,000 / GPU | Same | 2026-09-10 |
| AI Enterprise — self-managed, 3 years | $13,500 / GPU | Same | 2026-09-10 |
| AI Enterprise — self-managed, 4/5 years | $18,000 / GPU (multi-year discount) | Same | 2026-09-10 |
| AI Enterprise — perpetual (5 yrs support) | $22,500 / GPU | Same | 2026-09-10 |
| AI Enterprise — EDU / Inception pricing | ~75% off list, e.g. **$1,125/GPU/year**, perpetual $5,625/GPU | Same page | 2026-09-10 |
| AI Enterprise — CSP marketplace, production | **$1 / GPU-hour** + the cloud provider's instance cost | Same page | 2026-09-10 |
| AI Enterprise — CSP marketplace, development | Free to use, or bring-your-own-license, + instance cost | Same page | 2026-09-10 |
| Free evaluation license | 90-day free NVIDIA AI Enterprise license available | developer.nvidia.com/blog/access-to-nvidia-nim-now-available-free-to-developer-program-members/ | 2026-09-10 |

**Can a student/startup team run NIM in production without AI Enterprise?**
No. NVIDIA's own FAQ defines "production" broadly enough to include serving
any real end users, and states production deployments require an AI
Enterprise license. The Developer Program's free 16-GPU allowance is
explicitly scoped to development, testing, research, and evaluation. A
student capstone or an early startup could legitimately run a demo (Scenario
A, an "expo demo" with no real patients) under the free/dev tier, but the
moment MediAgent serves an actual clinic (Scenarios B/C), NVIDIA's own
definition puts that in "production," triggering the AI Enterprise
requirement — at minimum $1,125/GPU/year (EDU/Inception pricing) or $1/GPU-hour
metered on a CSP marketplace, on top of the underlying GPU compute cost.

---

## 3. DGX Cloud Lepton / NVIDIA Cloud Functions (NVCF) / DGX Cloud serverless inference

- **DGX Cloud Lepton is a marketplace/routing layer, not a priced product
  NVIDIA sells directly.** Its own marketing pages (nvidia.com/en-us/data-center/dgx-cloud-lepton,
  fetched 2026-09-10) describe it as connecting developers to "a global
  network of GPU compute" via NVIDIA Cloud Partners (NCPs), and explicitly do
  not publish a per-GPU rate — each partner (Lambda, CoreWeave, etc.) prices
  independently. A third-party tracker cites a wide range for H100 SXM5 as
  an example — **$3.99/hr (Lambda) to $6.16/hr (CoreWeave)** per GPU
  (spheron.network/blog/dgx-cloud-lepton-pricing-2026/, seen 2026-09-10,
  **not NVIDIA-confirmed**). No L4-specific Lepton pricing was found —
  **not found**.
- **NVCF (NVIDIA Cloud Functions)** is the serverless layer that actually
  powers build.nvidia.com's hosted endpoints. Its official developer page
  (developer.nvidia.com/dgx-cloud/serverless-inference, fetched 2026-09-10)
  confirms **scale-to-zero** ("you can scale down to zero instances during
  periods of inactivity") and states there is "no extra cost for cold-boot
  start times," but discloses **no price** (neither per-GPU-hour nor
  per-request). Self-serve small-team access to NVCF outside of
  build.nvidia.com itself (i.e., deploying your own container on NVCF) is
  not clearly self-service in what I could fetch — it points to NVIDIA
  Cloud Partners or on-prem deployment rather than a public sign-up-and-pay
  flow. **Eligibility/pricing for a small team to deploy their own model on
  NVCF directly: not found — appears to require a sales/partner
  engagement.**
- Net for MediAgent: neither Lepton nor NVCF currently offers a transparent,
  self-serve, published per-GPU-hour rate that a small team can budget
  against without contacting a partner or NVIDIA sales. The one concrete,
  self-serve, published number remains the GCP L4 rate from CONTEXT
  ($0.71/hr g2-standard-4, $0.77/hr Cloud Run all-in), used in §6.

---

## 4. NVIDIA Inception (startup program)

- **Eligibility** (nvidia.com/en-us/startups/, fetched 2026-09-10): free,
  no equity, no fees. Requirements: **officially incorporated**, less than
  10 years old, at least one developer on staff, a working website.
  Explicitly excluded: consulting/outsourced-development firms, cryptocurrency
  companies, cloud service providers, resellers/distributors, public
  companies. **No mention of university capstone or student teams** on the
  official eligibility text I could fetch.
- **Implication for MediAgent**: the "officially incorporated" requirement
  is a hard gate. An unincorporated university capstone team, as such, would
  likely **not** qualify for Inception directly — it would need to
  incorporate (even as a simple LLC) or be sponsored/fronted by an already
  incorporated entity to enroll.
- **Benefits, per the official page**: no dollar amounts are published on
  nvidia.com/en-us/startups/ itself — it lists categories only (free DLI
  self-paced training, discounted expert-led DLI workshops, forum access,
  "preferred pricing on select NVIDIA hardware and software," "exclusive
  partner offers," and "free cloud credits from NVIDIA and partners").
  Third-party trackers (not NVIDIA-confirmed) put numbers on these:
  up to **$100,000** in DGX Cloud credit requests, up to **$100,000** via AWS
  Activate, up to **$150,000** via Nebius AI Lift, **$10,000** in DLI training
  credits, and a **30% DGX Cloud discount** gated behind a 4-node/$75,000
  minimum commitment (radgrants.com/programs/nvidia-inception;
  saastweaks.com/startup-credits/nvidia-inception; both seen 2026-09-10,
  **medium confidence, not independently verified on nvidia.com**). One
  number I could confirm from an official NVIDIA docs page: the **75%
  EDU/Inception discount on AI Enterprise** ($1,125/GPU/year list-equivalent)
  cited in §2, from docs.nvidia.com/ai-enterprise/planning-resource/licensing-guide.
- No build.nvidia.com-specific API-credit benefit for Inception members was
  found on an official page — **not found**.

---

## 5. NVIDIA healthcare offerings and BAA/HIPAA posture

- The current official Clara page (nvidia.com/en-us/clara/, fetched
  2026-09-10) **does not mention "Clara" as a distinct clinical-text/LLM
  product** in the content retrieved — it instead surfaces BioNeMo (drug
  discovery), Nemotron ("the foundation for digital health AI" per the
  page's own phrasing, oriented at "information retrieval, speech, and
  safety"), Isaac for Healthcare, MONAI (medical imaging), Holoscan SDK, and
  Parabricks (genomics). None of these read as a hosted, BAA-covered
  clinical-text LLM service.
- I could not locate any NVIDIA page (official or third-party) stating that
  NVIDIA offers a **Business Associate Agreement (BAA)** for build.nvidia.com,
  NVCF, DGX Cloud Lepton, or any hosted NIM endpoint. **Not found.** This
  matters directly: combined with the API Trial Terms of Service explicitly
  prohibiting PII/PHI submission (§1.5), the hosted catalog is not a viable
  path for real patient data under any plan I found evidence for.
- The only medical-domain LLM confirmed on the hosted catalog,
  writer/palmyra-med-70b, carries an explicit, self-declared restriction on
  its own model card against "direct patient care, clinical decision support,
  or professional medical purposes" and notes it has "not been rigorously
  evaluated in clinical trials or real-world healthcare settings"
  (build.nvidia.com/writer/palmyra-med-70b, fetched 2026-09-10) — i.e., even
  setting aside the retirement question in §1.7, its own terms rule out
  MediAgent's use case.
- MedGemma (Google, HAI-DEF terms) is not NVIDIA-hosted or NVIDIA-packaged
  as far as I could confirm (§1.4); its own HAI-DEF terms of use state the
  models are "not intended to be used without appropriate validation,
  adaptation and/or making meaningful modification by developers for their
  specific use case" (developers.google.com/health-ai-developer-foundations/faqs,
  seen 2026-09-10) — a Google compliance posture, not an NVIDIA one, since
  NVIDIA is not the host.
- **Conclusion**: for HIPAA/BAA purposes, NVIDIA's hosted catalog is not a
  candidate at all under current evidence. The only NVIDIA-adjacent path
  that could plausibly support a future BAA is fully self-hosted NIM on
  infrastructure where **the cloud provider (e.g., Google Cloud) signs the
  BAA**, with NVIDIA software running inside that boundary — NVIDIA itself
  does not appear to be the BAA counterparty in any offering found.

---

## 6. Compute cost for scenarios A/B/C

### 6.1 Workload scope and token totals

Per the task, this section covers **chat turns (classification + reply) +
safety classifier + documents** only (voice, patient explanations, and SOAP
notes are out of scope here). Using the volumes and token sizes from the
shared context:

- Chat turn = classification (400 in / 60 out) + reply (1,500 in / 250 out)
  → 1,900 in / 310 out per turn.
- Safety classifier = 500 in / 10 out per turn (same volume as chat turns).
- Combined per chat turn: **2,400 in / 320 out tokens**.
- Documents: 700 in / 700 out tokens each.

| Scenario | Chat turns/mo | Documents/mo | Total input tokens/mo | Total output tokens/mo |
|---|---:|---:|---:|---:|
| A (expo demo) | 3,000 | 600 | 7,620,000 | 1,380,000 |
| B (one clinic) | 60,000 | 3,000 | 146,100,000 | 21,300,000 |
| C (10 clinics) | 600,000 | 30,000 | 1,461,000,000 | 213,000,000 |

For reference only (not an NVIDIA number), the Gemini 3.5 Flash-Lite baseline
from the shared context ($0.30/$2.50 per 1M in/out tokens) would cost
**≈$5.74/mo (A), ≈$97.08/mo (B), ≈$970.80/mo (C)** for this same workload —
useful as a yardstick for the NVIDIA figures below.

### 6.2 (a) Hosted build.nvidia.com endpoints, paid tier

No NVIDIA-published per-token price exists (§1.3); pay-as-you-go requires a
sales quote. Using the **unverified, third-party-cited** blended range of
$0.04–$1.20 per million tokens (pricepertoken.com, seen 2026-09-10) purely as
an illustrative bound, and applying it to total tokens (in+out) per scenario:

| Scenario | Total tokens/mo | Illustrative low ($0.04/M) | Illustrative high ($1.20/M) |
|---|---:|---:|---:|
| A | 9,000,000 | $0.36 | $10.80 |
| B | 167,400,000 | $6.70 | $200.88 |
| C | 1,674,000,000 | $66.96 | $2,008.80 |

**This table should be treated as a rough plausibility check, not a quote.**
The honest answer to "what would the paid tier cost" is: **not publicly
priced; contact NVIDIA sales for a quote**, and until MediAgent has that
quote, the Gemini Flash-Lite baseline in §6.1 remains the only number with a
real, published price.

### 6.3 (b) Self-hosted NIM on one L4 (Google Cloud)

Self-hosting cost is dominated by GPU-hours and licensing, not token count —
it stays flat until the single L4's throughput ceiling is hit, unlike the
per-token hosted model. Using the GCP reference prices from the shared
context (g2-standard-4, 1×L4: $0.71/hr; Cloud Run L4, scale-to-zero, all-in:
$0.77/hr) and the AI Enterprise licensing tiers from §2:

| Configuration | Hourly rate | Monthly cost if always-on (×730 hr) |
|---|---:|---:|
| Dev/test only (≤16 GPUs, free under Developer Program, no real end users) | $0.71/hr compute, $0 license | **$518.30** |
| Production, self-managed annual license, **list** price ($4,500/GPU/yr ÷ 8,760 hr/yr ≈ $0.514/hr) | $0.71 + $0.514 = $1.224/hr | **$893.52** |
| Production, self-managed annual license, **EDU/Inception** price ($1,125/GPU/yr ÷ 8,760 hr/yr ≈ $0.128/hr) | $0.71 + $0.128 = $0.838/hr | **$611.74** |
| Production, CSP-marketplace metered license ($1/GPU-hr, no annual commitment), on g2-standard-4 | $0.71 + $1.00 = $1.71/hr | **$1,248.30** |
| Production, CSP-marketplace metered license, on Cloud Run L4 (scale-to-zero — only pay for active hours) | $0.77 + $1.00 = $1.77/hr **only while active** | Scales with actual active hours, not a flat 730 |

Because a single L4 (24 GB) is one GPU regardless of how many tokens it
processes per month, **the same table applies to Scenarios A, B, and C** as
long as one L4 has enough throughput headroom for the scenario's volume.
That assumption is safe for Scenario A and very likely fine for Scenario B;
**it is a real open question for Scenario C** (600,000 chat turns + 30,000
documents/month implies roughly 1.67B total tokens/month, or an average of
~640 tokens/sec sustained if spread evenly across a 30-day month) — whether
one L4 running a NIM for an 8–20B-class model can sustain that throughput
depends on the exact model, quantization, and batching, none of which I
benchmarked in this pass. **Not found**: an NVIDIA-published tokens/sec
figure for gpt-oss-20b, Llama Guard 4 12B, or Nemotron-Parse specifically on
an L4. If Scenario C exceeds one L4's capacity, the real cost would need a
second GPU (roughly doubling the compute line, but the license is still
per-GPU so it also doubles), or a move to an A100/L40S tier.

### 6.4 What this means for MediAgent

- At Scenario A's demo volume, self-hosting a dedicated L4 (≈$518–$1,248/mo
  depending on licensing posture) is dramatically more expensive than either
  the Gemini Flash-Lite baseline (≈$5.74/mo) or even the illustrative
  build.nvidia.com paid-tier estimate (≈$0.36–$10.80/mo). Self-hosting only
  starts to look competitive at higher, sustained volume where a flat
  GPU-hour cost is amortized over more tokens — and even at Scenario C's
  volume (~$67–$2,009/mo illustrative hosted vs. $518–$1,248/mo self-hosted),
  the two approaches land in the same order of magnitude, so the deciding
  factors are more likely to be data-residency/PII posture (§1.5, §5) and
  control over the model/version, not raw compute cost.
- The **production-licensing tax is the dominant self-hosting cost lever**:
  EDU/Inception annual pricing ($611.74/mo all-in) vs. list annual pricing
  ($893.52/mo) vs. metered marketplace pricing ($1,248–$1,292/mo) is up to a
  ~2× spread for the exact same GPU and workload, so qualifying for
  EDU/Inception pricing (which itself requires either academic status or
  Inception membership — and Inception requires incorporation, §4) is
  materially worth pursuing before committing to a self-hosted NIM plan.

---

## Confidence and gaps

**High confidence (NVIDIA-official source, directly fetched):**
- AI Enterprise pricing table (§2): docs.nvidia.com/ai-enterprise/planning-resource/licensing-guide.
- Developer Program 16-GPU free self-host limit and production definition
  (§2): developer.nvidia.com blog + docs.api.nvidia.com/nim/docs/product FAQ.
- NVCF scale-to-zero behavior with no cold-boot surcharge (§3):
  developer.nvidia.com/dgx-cloud/serverless-inference.
- Inception eligibility gate requiring incorporation (§4): nvidia.com/en-us/startups/.
- gpt-oss-120b/20b, Llama 4 Scout, Llama Guard 4 12B, Nemotron-Parse,
  Nemotron OCR v1 presence on build.nvidia.com (§1.4): direct model-page
  fetches.
- Structured JSON-schema output support (guided_json / response_format
  json_schema) is documented for NIM LLMs and VLMs: docs.nvidia.com/nim/large-language-models/1.13.0/structured-generation.html
  and docs.nvidia.com/nim/vision-language-models/1.0.0/structured-generation.html
  (seen 2026-09-10) — not broken out into its own section above but directly
  answers the "structured-output support" requirement from the shared
  context: **yes, supported** on self-hosted NIM for LLMs/VLMs via the
  OpenAI-compatible `response_format`/`guided_json` extension.

**Medium confidence (third-party trackers or search snippets, not
independently confirmed on an NVIDIA-first page):**
- Exact free-tier credit numbers (1,000/5,000) and their removal in 2026.
- 40 RPM / 200 RPM rate limits.
- The $0.04–$1.20/M-token blended pay-as-you-go range.
- Inception credit dollar amounts (DGX Cloud, AWS Activate, Nebius, DLI).
- The exact deprecation banners and dates for nemoretriever-ocr,
  nemoretriever-page-elements-v3, and palmyra-med-70b — the underlying
  `disabled-` URL naming convention is real (found via search index), but I
  could not get a clean first-hand fetch of the live banner text because the
  build.nvidia.com model pages appear to be a JS-rendered SPA and the fetch
  tool sometimes returns only static/title content, not the client-rendered
  deprecation banner. This is a tooling limitation, not a claim that the
  banners don't exist.
- Lepton per-GPU-hour rates (H100 SXM5 $3.99–$6.16/hr) — partner-reported,
  no L4 rate found at all for Lepton.

**Not found (explicitly, not guessed):**
- Any per-token price NVIDIA itself publishes for build.nvidia.com paid tier.
- MedGemma availability as an NVIDIA-hosted or NVIDIA-packaged NIM.
- Nemotron-Parse "2.0" specifically (only 1.1 confirmed) and Llama 4 Maverick
  specifically (only Scout confirmed) on the hosted catalog.
- Qwen 3.6 8B–32B dense-model presence specifically on the *hosted* API
  catalog (only self-host NIM containers and the Qwen3-Next MoE family were
  confirmed as catalog-hosted).
- Baichuan-M2 32B on build.nvidia.com — not checked in this pass.
- Any NVIDIA-offered BAA for any hosted service.
- Any published notice-period policy for endpoint retirement.
- A GPU-hour or per-request price for NVCF or DGX Cloud Lepton on L4
  hardware specifically.
- Real-world tokens/sec throughput for a single L4 running any of the
  models of interest (needed to convert the token volumes in §6.1 into
  actual GPU-hours for Scenario C capacity planning).

**Tooling note:** the WebSearch budget for this research session was
exhausted partway through (200/200 calls used across this and other
concurrent work) which capped the number of additional confirmation
searches I could run; the remaining gaps above were investigated as far as
WebFetch alone could reach.

---

## Sources

- developer.nvidia.com/blog/access-to-nvidia-nim-now-available-free-to-developer-program-members/ (fetched 2026-09-10)
- docs.api.nvidia.com/nim/docs/product (fetched 2026-09-10)
- docs.nvidia.com/ai-enterprise/planning-resource/licensing-guide/latest/pricing.html (fetched 2026-09-10)
- developer.nvidia.com/dgx-cloud/serverless-inference (fetched 2026-09-10)
- nvidia.com/en-us/data-center/dgx-cloud-lepton (fetched 2026-09-10)
- nvidia.com/en-us/startups/ (fetched 2026-09-10)
- nvidia.com/en-us/clara/ (fetched 2026-09-10)
- build.nvidia.com/openai/gpt-oss-120b (fetched 2026-09-10)
- build.nvidia.com/openai/gpt-oss-20b (fetched 2026-09-10)
- build.nvidia.com/meta/llama-4-scout-17b-16e-instruct (fetched 2026-09-10)
- build.nvidia.com/meta/llama-guard-4-12b (fetched 2026-09-10)
- build.nvidia.com/writer/palmyra-med-70b (fetched 2026-09-10)
- build.nvidia.com/google/gemma-4-31b-it/modelcard (via search index, seen 2026-09-10)
- build.nvidia.com/nvidia/nemotron-parse/modelcard (via search index, seen 2026-09-10)
- build.nvidia.com/nvidia/nemotron-ocr-v1/modelcard (via search index, seen 2026-09-10)
- build.nvidia.com/baidu/paddleocr/modelcard (via search index, seen 2026-09-10)
- build.nvidia.com/nvidia/nemoretriever-ocr-v1 and /nemoretriever-ocr (via search index, seen 2026-09-10)
- docs.api.nvidia.com/nim/reference/disabled-writer-palmyra-med-70b (found via search index; direct fetch returned HTTP 404 on 2026-09-10)
- docs.nvidia.com/nim/large-language-models/1.13.0/structured-generation.html (seen 2026-09-10)
- docs.nvidia.com/nim/vision-language-models/1.0.0/structured-generation.html (seen 2026-09-10)
- assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf (fetched 2026-09-10, binary; content relayed via forum quote below)
- forums.developer.nvidia.com/t/clarification-on-trial-api-use/334275 (fetched 2026-09-10)
- developers.google.com/health-ai-developer-foundations/medgemma and /faqs (seen 2026-09-10)
- catalog.ngc.nvidia.com/orgs/nim/teams/qwen/containers/qwen3.6-35b-a3b (seen 2026-09-10)
- docs.nvidia.com/enterprise-support-and-services-user-guide (seen 2026-09-10)

Third-party/aggregator sources (used only where explicitly flagged as medium
confidence above, never as the sole basis for a "high confidence" claim):
- costbench.com/software/llm-api-providers/nvidia-nim/free-plan/ (seen 2026-09-10)
- yangmao.ai/en/providers/nvidia-build/ (and /free-tier/, /api-pricing/) (seen 2026-09-10)
- decodethefuture.org/en/nvidia-nim-api-pricing-limits-guide/ (seen 2026-09-10)
- pricepertoken.com/pricing-page/provider/nvidia (seen 2026-09-10)
- spheron.network/blog/dgx-cloud-lepton-pricing-2026/ and /blog/nvidia-nim-pricing-vs-self-hosted-vllm-cost-2026/ (seen 2026-09-10)
- radgrants.com/programs/nvidia-inception (seen 2026-09-10)
- saastweaks.com/startup-credits/nvidia-inception (seen 2026-09-10)
- aicreditmart.com/ai-credits-providers/nvidia-inception-how-to-get-100k-in-startup-credits-2026/ (seen 2026-09-10)
