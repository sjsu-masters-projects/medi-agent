# GPU-hour and serverless-GPU hosting options for self-managed open models (MediAgent)

Research date: 2026-09-10. All prices are list/on-demand US prices unless noted; all
figures were pulled from secondary aggregator sites and search-engine summaries of
official pages during this session (official pricing pages returned JS-rendered
content that WebFetch could not parse in most cases — see "Confidence and gaps").
Every number below is tagged with its source and the date it was retrieved
(2026-09-10 for everything in this report unless the source text carried its own
dated claim, which is noted). Where I could not find a number, it says "not found."

This report evaluates self-hosting vLLM/Ollama/ONNX-served open models (MedGemma
1.5 4B, Gemma 4 variants, gpt-oss, Qwen 3.6, etc.) as an alternative/supplement to
the Gemini 3.5 Flash-Lite baseline ($0.30/$2.50 per 1M in/out tokens on Vertex,
~$0.0015/chat turn) described in CONTEXT.md.

---

## 1. Master comparison table

### 1a. Google Cloud

| Option | GPU / $ per hour | Per-second billing & minimum | Scale-to-zero / cold start | HIPAA/BAA | Regions | Min. commitment | MedGemma/Gemma one-click |
|---|---|---|---|---|---|---|---|
| **Cloud Run GPU** | L4 24GB: **~$0.77/h all-in** (CPU+mem+GPU, scale-to-zero config; CONTEXT.md baseline, previously verified). Independent check: GPU portion alone ≈ **$0.0001867/s ≈ $0.67/h** without zonal redundancy, **$0.0002909/s ≈ $1.05/h** with zonal redundancy — this is GPU-only, billed on top of separate CPU/memory charges [cloudchipr.com/blog/cloud-run-pricing, accessed 2026-09-10]. No H100/B200 GPU type found on Cloud Run in this pass — only L4 is documented for Cloud Run; Cloud Run's own pricing page (cloud.google.com/run/pricing) did not render for WebFetch to confirm, so treat "L4 only" as **not fully confirmed** rather than definitive. | Billed per second, no separate minimum found (standard Cloud Run per-100ms style billing is documented behavior generally, not confirmed specifically for GPU in this pass). **True scale-to-zero is a first-class Cloud Run feature.** Cold start for a 4B–12B model: not directly found for Cloud Run specifically; general serverless-GPU cold-start data (see §3) suggests 15–90s depending on whether weights are cached on the container image vs. pulled from a registry. | Cloud Run is on Google's HIPAA BAA-covered services list, alongside Compute Engine, GKE, and Vertex AI [tcsa.in/frameworks/hipaa-sra/gcp-hipaa-compliance, accessed 2026-09-10]. | Limited to Tier-1 regions for GPU (exact list not retrieved this pass — not found). | None (pay-as-you-go). | Not found directly for Cloud Run GPU; Vertex Model Garden and GKE are the documented one-click paths (see below), and a Cloud-Run-GPU deployment of Gemma/MedGemma would be a manual container build, not a vendor "1-click" flow. |
| **GKE Autopilot (GPU pods)** | L4: **≈$0.70/GPU-h** in us-central1 (same underlying Compute Engine G2 rate) [thundercompute.com/blog/google-cloud-gpu-instances; qovery.com/blog/google-cloud-gpu-instances-by-workload, accessed 2026-09-10]. A100 40GB/80GB: Autopilot publishes separate "Premium SKUs" on top of the base A2 rate — exact premium percentage **not found**. Starting **Oct 1, 2026**, Autopilot will also bill a node-management premium for G4 (RTX PRO 6000) pods [cloud.google.com/skus/sku-groups/gke-autopilot-accelerator-premiums, accessed 2026-09-10]. | Standard Kubernetes billing (per-second underlying VM billing), no built-in request-level minimum. | No native scale-to-zero for GPU pods; achievable only via a custom KEDA/HPA-based autoscaler that scales the Deployment to 0 replicas when idle — this is engineering effort, not a platform feature. Cold start = pod scheduling + node provisioning (often 60–120s for a fresh GPU node) + model load. | Covered under the same GCP BAA as Compute Engine/GKE [tcsa.in, accessed 2026-09-10]. | Same as Compute Engine GPU region list (not enumerated this pass). | None. | Not a vendor one-click flow; would require a manual vLLM/Ollama Helm chart or KServe deployment. |
| **Vertex AI Model Garden (dedicated endpoint)** | L4 ≈ **$0.64/h compute**; A100 40GB ≈ **$2.93/h compute + ~$0.44/h management fee ≈ $3.37/h all-in**; H100 80GB ≈ **$9.80/h compute + ~$1.47/h management fee ≈ $11.27/h all-in** [spheron.network/blog/vertex-ai-model-garden-pricing-2026-cost-vs-self-hosted, accessed 2026-09-10]. Management fee is consistently ≈15% of the compute rate across the two confirmed data points; the same ratio applied to L4 gives an **estimated** ≈$0.10/h fee, ≈$0.74/h all-in (not independently confirmed for L4). | Not found specifically; billed hourly once deployed. | **Minimum replica count must be ≥1** by default — the endpoint runs (and bills) continuously once deployed [Terraform provider docs, registry.terraform.io/providers/hashicorp/google, accessed 2026-09-10]. A newer "Scale To Zero" feature is documented for "eligible" online-prediction deployments, but the first request after scale-down gets an HTTP 429 while the model server restarts [oneuptime.com/blog/2026-02-17-how-to-enable-scale-to-zero-for-vertex-ai-prediction-endpoints, accessed 2026-09-10]. Whether MedGemma/Gemma Model-Garden deployments qualify for this "eligible" scale-to-zero tier is **not found** — treat as uncertain. | Vertex AI is on Google's BAA product list, though one source flags that the *named product* "Vertex AI" itself is sometimes absent from Google's self-serve BAA product list and only "Vertex AI Workbench" is explicitly named — **conflicting information, verify directly with Google before relying on this for PHI** [authentech.ai/healthcare/is-google-vertex-ai-hipaa-compliant, accessed 2026-09-10]. | us-central1 confirmed for pricing; broader list not enumerated. | None (pay-as-you-go per deployed replica-hour). | **Yes** — MedGemma (part of HAI-DEF) documents 1-click deploy to a Vertex Endpoint directly from Model Garden [developers.google.com/health-ai-developer-foundations/medgemma; cloud.google.com/blog/topics/developers-practitioners/integrating-medgemma-into-clinical-workflows-just-got-easier, accessed 2026-09-10]. Gemma models (3 and 4 series) are likewise documented with a Model-Garden "Deploy" tutorial [docs.cloud.google.com/vertex-ai/generative-ai/docs/model-garden/deploy-and-inference-tutorial]. |
| **Compute Engine — G2 (L4)** | On-demand: **$0.707–$0.71/h** (g2-standard-4, us-central1) [thundercompute.com; CONTEXT.md, accessed 2026-09-10]. Spot: reports disagree sharply — one figure is **$0.619/h** (only ~12–13% off on-demand) [economize.cloud, accessed 2026-09-10], another cites a much lower **$0.0881/h** that looks like a data error or a different SKU — **treat the low figure as unreliable**; the ~12% discount figure is consistent with the separately-reported claim that "g2-standard-4 drops only 12% on Spot vs 72% for n2-standard-4" [usage.ai/blogs/gcp/compute-engine, accessed 2026-09-10]. 1-year CUD: **only ≈8% off** on-demand (≈$0.65/h); 3-year CUD: **≈11% off** (≈$0.63/h) — L4/G2 gets unusually weak CUD discounts versus other GCP GPU families [usage.ai/blogs/gcp/compute-engine, accessed 2026-09-10]. GPUs are **not eligible** for GCP's flexible CUDs — must use resource-based CUDs. | Per-second billing, standard GCE billing model (no GPU-specific minimum found). | No native scale-to-zero; requires a stop/start automation (Cloud Scheduler + instance API) to approximate it. Cold start = full VM boot (typically 20–60s) + model load. | Compute Engine is HIPAA BAA-eligible [tcsa.in, accessed 2026-09-10]. | Wide (most GCP regions with G2 capacity). | None. | No — manual vLLM/Ollama install on the VM. |
| **Compute Engine — A2 (A100 40GB/80GB)** | A100 40GB (a2-highgpu-1g) on-demand: **$3.67/h** (CONTEXT.md baseline, cross-checked as internally consistent with other figures found this pass). A100 80GB on-demand: **≈$5.03/h** (CONTEXT.md baseline). 1-year/3-year CUD discounts for A2 generally run **≈25–37% (1yr)** and **≈50–57% (3yr)** off on-demand, per aggregate GCP GPU CUD guidance — these are family-wide figures, not A2-specific confirmed numbers [usage.ai/blogs/gcp/compute-engine, accessed 2026-09-10]. | Per-second. | Same caveats as G2 — no native scale-to-zero. | Covered under GCP BAA. | Wide. | None. | No. |
| **Compute Engine — A3 (H100)** | On-demand: **≈$11.06/GPU-h** (a3-highgpu-8g, priced per-GPU-equivalent; the 8-GPU instance itself is ≈$88/h total) [gmicloud.ai/en/blog/google-cloud-gpu-cost-explained, accessed 2026-09-10]. Spot and CUD discounts for A3 were reported as generally smaller than for A2 — no specific A3 percentage found. | Per-second. | No native scale-to-zero. | Covered under GCP BAA. | Limited regions (not enumerated). | None. | No. |

### 1b. AWS

| Option | GPU / $ per hour | Per-second billing & minimum | Scale-to-zero / cold start | HIPAA/BAA | Regions | Min. commitment | MedGemma/Gemma one-click |
|---|---|---|---|---|---|---|---|
| **SageMaker real-time inference** | ml.g5.xlarge (A10G 24GB): **$1.01/h** [cloudchipr.com/blog/amazon-sagemaker-pricing, accessed 2026-09-10]. ml.g6.48xlarge (8×L4): **$16.688/h** (≈$2.09/GPU-h-equivalent, not a confirmed single-GPU SKU) [cloudchipr.com, accessed 2026-09-10]. A single-GPU ml.g6.xlarge exact rate: **not found** this pass. G6 (L4) instances just expanded to AWS GovCloud (US-East) for SageMaker inference [aws.amazon.com/about-aws/whats-new/2026/07/g6-sagemaker-ai-inference, accessed 2026-09-10]. | Real-time endpoints run continuously and bill per instance-hour; **no scale-to-zero** — endpoints bill 24/7 regardless of traffic [cloudchipr.com, accessed 2026-09-10]. | No scale-to-zero. Cold start only applies to endpoint *creation*, not per-request (already-warm instances serve immediately). | SageMaker is on AWS's HIPAA-eligible services list; BAA is accepted self-serve via AWS Artifact at no extra cost [patient-protect.com/aws-hipaa-eligible-services; baagenerator.com/blog/does-aws-sign-a-baa, accessed 2026-09-10]. | Wide (multi-region); G6 now includes GovCloud (US-East). | None. | **Yes for Gemma** — Gemma 4 (E4B, 26B-A4B, 31B) shipped in SageMaker JumpStart with documented one-click / few-click deploy via SageMaker Studio or the Python SDK [aws.amazon.com/about-aws/whats-new/2026/04/gemma-4-models-on-sagemaker-jumpstart, accessed 2026-09-10]; Gemma-4-E2B followed in July 2026 and gemma-4-12B-it in January 2026 [aws.amazon.com/about-aws/whats-new/2026/07/..., 2026/01/..., accessed 2026-09-10]. **MedGemma on SageMaker JumpStart: not found** — no evidence located that Google's HAI-DEF/MedGemma models are in the JumpStart catalog; MedGemma's documented one-click paths are Vertex Model Garden and Hugging Face. |
| **SageMaker Serverless Inference** | GPU support status is **disputed in the sources found**: one set of 2026 secondary blog posts claims GPU serverless "matured into a production-ready service" by March 2026 with A100 available (H100 not offered) [deploybase.ai/articles/sagemaker-serverless-inference-gpu, accessed 2026-09-10]; other sources and a live GitHub feature-request thread suggest GPU/CUDA support for Serverless Inference remains a request, not a shipped feature [github.com/aws/amazon-sagemaker-feedback/issues/233, accessed 2026-09-10]. **I could not confirm this against an official AWS page in this pass — treat GPU-backed SageMaker Serverless Inference as unconfirmed/not found, and verify directly against docs.aws.amazon.com before planning around it.** | If it exists, billed per-inference-duration-second with a stated 150,000-second monthly free tier [deploybase.ai, accessed 2026-09-10] — not independently confirmed. | Serverless is scale-to-zero by design when it applies to CPU workloads; cold starts cited at **30–60s average** for the GPU variant in the secondary sources [deploybase.ai, accessed 2026-09-10] — unconfirmed. | Same AWS BAA umbrella as other SageMaker features, contingent on the feature actually existing as described. | Not found. | None claimed. | Not found. |
| **EC2 g5 (A10G)** | g5.xlarge on-demand: **$1.006/h**; spot: **$0.671/h** [instances.vantage.sh/aws/ec2/g5.xlarge, accessed 2026-09-10]. 1× A10G, 24GB GPU memory, 16GB instance RAM. | Per-second billing, 60-second minimum [aws.amazon.com/ec2/pricing/on-demand, accessed 2026-09-10]. | No platform scale-to-zero (raw EC2); requires custom automation. Cold start = EC2 boot (~30–60s) + model load. | EC2 (shared-tenancy) is fully HIPAA-eligible [patient-protect.com, accessed 2026-09-10]. | Wide. | None. | No (raw compute; you install vLLM/Ollama yourself). |
| **EC2 g6 (L4)** | g6.xlarge on-demand: **$0.805/h** (also cited as $0.8048/h); spot: **$0.685/h** [instances.vantage.sh/aws/ec2/g6.xlarge; search aggregate of devzero.io, economize.cloud, accessed 2026-09-10]. 1× L4, 24GB GPU memory, 16GB instance RAM. G6 delivers up to 2x G4dn's inference performance [cloudchipr.com, accessed 2026-09-10]. | Per-second, 60-second minimum. | No native scale-to-zero. | HIPAA-eligible under the standard EC2 umbrella. | Wide, plus new GovCloud availability for the SageMaker-managed variant. | None. | No. |
| **EC2 g6e (L40S)** | g6e.xlarge on-demand: **$1.861/h**; g6e.4xlarge on-demand: **$3.004/h** (both us-east-1) [devzero.io/instances/aws/g6e.xlarge, g6e.4xlarge, accessed 2026-09-10]. 1× L40S, 48GB GPU memory. | Per-second, 60-second minimum. | No native scale-to-zero. | HIPAA-eligible under EC2. | Wide. | None. | No. |
| **Bedrock Custom Model Import (CMI)** | **$0.05718 per Custom-Model-Unit (CMU) per minute** in us-east-1/us-west-2; **$0.07144/CMU-min** in eu-frankfurt [aws.amazon.com/bedrock/pricing, accessed 2026-09-10 — official page]. A Llama-3.1-8B/128K model needs **2 CMUs** → **$0.1144/min ≈ $6.86/h** while active. Storage: **$1.95/CMU-month**. No charge to import the model itself; you only pay once invocations start. | **Billed in 5-minute windows** starting from the first successful invocation after a period of inactivity — this is a coarser billing granularity than true per-second [aws.amazon.com/bedrock/pricing, accessed 2026-09-10]. | Scales down between windows of inactivity (functionally close to scale-to-zero, gated at 5-minute granularity rather than per-second). Cold-start figure specific to CMI: **not found**. | Bedrock foundation-model access (including presumably CMI) became HIPAA-eligible in 2024 per secondary sources [qualixsolutions.com/aws-bedrock-consultants/hipaa-eligible-baa, accessed 2026-09-10] — verify current CMI-specific eligibility directly with AWS before use with PHI. | Not found (region list for CMI specifically). | None. | CMI supports importing your own weights for supported architectures (Llama-family, Mistral-family confirmed in AWS docs generally) — whether **Gemma or MedGemma architectures are importable via CMI is not found** in this pass; CMI's supported-architecture list should be checked directly. |

### 1c. Azure

| Option | GPU / $ per hour | Per-second billing & minimum | Scale-to-zero / cold start | HIPAA/BAA | Regions | Min. commitment | MedGemma/Gemma one-click |
|---|---|---|---|---|---|---|---|
| **Azure ML managed online endpoints / Azure AI Foundry** | Billing = the underlying NC-series VM rate; no separate per-token or per-request platform fee was found (unlike Vertex's stacked management fee) — Foundry documentation states models "run inside your Azure environment" under managed online endpoints which "handle serving, scaling, and monitoring" [techcommunity.microsoft.com/blog/azure-ai-foundry-blog/gemma-4-now-available-in-microsoft-foundry, accessed 2026-09-10]. No explicit extra management-fee line item was found — **treat this as "no separate fee found," not confirmed absence.** | Not found specifically; standard Azure VM per-second billing generally applies to compute. | No native scale-to-zero documented for managed online endpoints in what was found; would need Azure Container Apps or a similar serverless-GPU layer instead. Cold start: not found. | Azure ML is HIPAA-eligible "when configured properly" [simbo.ai blog, accessed 2026-09-10]. For Foundry model consumption, the HIPAA BAA is provided automatically via the Microsoft Products and Services DPA for customers on an Enterprise Agreement, Microsoft Customer Agreement, or CSP — **no separate per-model BAA needed** [learn.microsoft.com/en-us/answers/questions/5942711, accessed 2026-09-10]. | Wide (standard Azure region footprint for NC-series, subject to quota). | New subscriptions start with **zero N-series vCPU quota** and must request a quota increase (approval can take hours to days) [thundercompute.com/blog/azure-nc-a100-vs-thunder-compute, accessed 2026-09-10] — an operational lead-time cost worth planning around. | **Yes for Gemma 4** — Microsoft added Gemma 4 to the Foundry model catalog in April 2026, deployable via managed online endpoints with the org's existing network/identity/audit policies [redmondmag.com/blogs/redmond-dispatch/2026/04; techcommunity.microsoft.com, accessed 2026-09-10]. **MedGemma in Azure AI Foundry: not found** — no MedGemma entry located in the catalog search results (only community fine-tunes of unrelated "gemma-ft-medical" style listings turned up, which are third-party, not Google's official MedGemma). |
| **Azure NC A10 v4** | NV12ads A10 v5 (closest A10 SKU found): **$1.117/h** [thundercompute.com, accessed 2026-09-10]. Note: this is an "NV" not "NC" series designation in the source — naming may differ slightly from what CONTEXT.md/task expected; treat as the closest available data point. | Standard Azure VM per-second billing (generally). | No native scale-to-zero (raw VM). | HIPAA-eligible under Azure ML/Compute umbrella when configured per Microsoft's guidance. | Subject to quota. | None. | No (raw VM). |
| **Azure NC A100 v4** | NC24ads A100 v4 (1× A100 80GB, 24 vCPU, 220 GiB RAM): **$3.673/h on-demand** [instances.vantage.sh/azure/vm/nc24ads-v4; cloudprice.net/vm/Standard_NC24ads_A100_v4, accessed 2026-09-10]. Spot: **≈$1.15/h average** for the single-GPU SKU [thundercompute.com, accessed 2026-09-10]. | Standard Azure VM billing. | No native scale-to-zero. | Same as above. | Subject to quota; zero N-series quota by default on new subscriptions. | None. | No. |

### 1d. Specialized GPU clouds and serverless-GPU platforms

| Provider | L4 (24GB) | A10G/L40S (24–48GB) | A100 40/80GB | H100 | Per-second billing / min | Scale-to-zero & cold start | HIPAA/BAA | Notes |
|---|---|---|---|---|---|---|---|---|
| **Modal** | **$0.000222/s ≈ $0.80/h** base rate | Not found (Modal's published GPU list did not surface L40S/A10G rates in this pass) | A100 40GB: **$0.000583/s ≈ $2.10/h**; A100 80GB: **$0.000694/s ≈ $2.50/h** | **$0.001097/s ≈ $3.95/h** [all Modal figures: spheron.network/blog/modal-gpu-pricing-2026-per-second-billing, accessed 2026-09-10] | True per-second, **no minimum increment**. Note: a broad-region selection applies a **1.5×** multiplier, a narrower region **1.75×**, and non-preemptible instances a further **3×** — base rates above are before these multipliers, so effective cost can be materially higher [same source]. | Scale-to-zero is core to Modal's model. With NVMe/S3 memory snapshots, cold start for a 7B–13B model drops from a **50–90s full cold start to 2–9s** [runpod.io/blog/cut-vllm-cold-starts-runpod-serverless discussing general technique; Modal-specific figures also reported at "2-5 seconds... from a 9 GiB checkpoint" via snapshot restore, accessed 2026-09-10]. Without snapshotting, expect a **50–90s** cold start dominated by weight download/load. | Modal supports HIPAA workloads with a BAA available on its **Enterprise plan** (contact security@modal.com); Modal completed **SOC 2 Type II** (Feb 2025) [modal.com/blog/soc2type2, accessed 2026-09-10]. | No confirmed one-click MedGemma/Gemma deploy — Modal is code-first (you write the serving script). |
| **RunPod — Serverless** | **≈$0.69/h** equivalent, billed per-second of active execution [runpod.io/pricing, accessed 2026-09-10] | A10 not found; L40S not found in Serverless list | A100 80GB: **≈$2.72/h** equivalent | H100 80GB: **≈$4.55–4.79/h** equivalent (two sources gave $4.55 and $4.79) [thundercompute.com/blog/runpod-pricing-vs-thunder-compute; runpod.io/pricing, accessed 2026-09-10] | Per-second billing on active worker time; specific minimum increment not found. | Scale-to-zero is the point of Serverless. With **FlashBoot** optimizations, cold starts drop from **~60s to 10–15s**; a documented case study took a 32B FP8 model on 2×H200 from a 324s to a 91s cold start via four configuration changes [runpod.io/blog/cut-vllm-cold-starts-runpod-serverless, accessed 2026-09-10]. | RunPod achieved independently-audited **HIPAA and GDPR compliance** (Feb 6, 2026) and offers **SOC 2 Type II** (Oct 2025) for **Secure Cloud** [runpod.io/press/runpod-meets-hipaa-and-gdpr-standards, accessed 2026-09-10]. BAAs/custom legal agreements require a **committed monthly spend of $3,000+** [contact.runpod.io/hc/en-us/articles/50120688006163, accessed 2026-09-10] — this is a meaningful gate for a small MediAgent deployment. | No confirmed one-click MedGemma/Gemma deploy; RunPod ships vLLM worker templates you configure yourself. |
| **RunPod — Pods (persistent)** | Community Cloud **$0.44/h**; Secure Cloud **$0.49/h** | Not found for A10; not found for L40S in Pods list | A100 80GB PCIe: Community **$1.19/h** / Secure **$1.59/h**; A100 80GB SXM: Community **$1.39/h** / Secure **$1.59/h** | H100 PCIe: Community **$1.99/h** / Secure **$2.89/h**; H100 SXM: Community **$2.69/h** / Secure **$3.49/h**; H100 NVL: Community **$2.59/h** / Secure **$3.19/h** [all: runpod.io/pricing, accessed 2026-09-10] | N/A — Pods are billed per-hour like a rented VM (per-second granularity available per RunPod but exact minimum not extracted from the fetch). | No scale-to-zero (Pods are persistent, like a VM); you start/stop manually or via API. | Community Cloud is **not** the HIPAA/SOC2-eligible tier; only **Secure Cloud** (Tier 3/4 data centers, single-tenant hardware) is positioned for regulated workloads [runpod.io/legal/compliance, accessed 2026-09-10]. | Same HIPAA/BAA caveat as Serverless above. |
| **Replicate** | **Not found** — Replicate's published per-second rates in this pass covered L40S/A100/H100 only, no L4 SKU located. | L40S: **$0.000975/s ≈ $3.51/h** | A100 80GB: **$0.001400/s ≈ $5.04/h** | H100: **$0.001525/s ≈ $5.49/h** [replicate.com/pricing via spheron.network/blog/replicate-pricing-2026-per-second-cost, dated in-source "July 30, 2026", accessed 2026-09-10] | True per-second, public hosted-model billing. | Scale-to-zero is native to Replicate's "run a public/private model" product; cold-start figures specific to Replicate: **not found** in this pass — apply the general serverless range from §3 as a proxy. | **Not found** — no HIPAA/BAA information located for Replicate in this pass. | Replicate hosts many community Gemma checkpoints "as-is" (browsable, run via API) but a documented vendor **one-click MedGemma/Gemma deploy flow was not found** — treat as unconfirmed. |
| **Baseten (dedicated)** | **$0.01414/min ≈ $0.85/h** | A10G: **$0.02012/min ≈ $1.21/h**. L40S: not found. | A100 80GB: **$0.06667/min ≈ $4.00/h** | H100 80GB: **$0.10833/min ≈ $6.50/h**; H100 MIG 40GB: **$0.0625/min ≈ $3.75/h**; B200 180GB: **$0.16633/min ≈ $9.98/h** [costbench.com/software/ai-model-hosting/baseten; valueaddvc.com "how-does-baseten-make-money", accessed 2026-09-10] | Per-minute billing (per-GPU-minute per replica); "no need to reserve GPUs — customers are only charged when they use their compute" [valueaddvc.com, accessed 2026-09-10]. **Important**: rate is per *running replica* — most production deployments run 2+ replicas, each billing at full rate. | Baseten markets usage-based, no-reservation billing consistent with autoscale-to-zero behavior, but an explicit scale-to-zero SLA/cold-start figure was **not found** in this pass. | Baseten **announced HIPAA compliance**, is **SOC 2 Type II** certified, and supports GDPR by default; reports available to customers on request [baseten.co/blog/baseten-announces-hipaa-compliance, accessed 2026-09-10]. Baseten states it serves OpenEvidence's medical-information workload at scale, evidencing production healthcare use [same source]. | No confirmed vendor one-click MedGemma/Gemma deploy found (Baseten supports custom model deployment generally). |
| **Lambda Labs** | **Not found** — Lambda's public GPU line-up in the sources found was A10/A100/H100/RTX-class; no L4 SKU or price located. | A10: not found this pass (Lambda historically offers A10 but no current $/h figure surfaced). | A100 40GB: **$1.99/h**; A100 80GB SXM: **$2.79/h** | H100 PCIe: **$3.29/h**; H100 SXM: **$3.99/h** (raised from $2.99 through 2025–2026 amid demand pressure) [synpixcloud.com/blog/lambda-labs-gpu-pricing-2026; gpucost.org/provider/lambda, accessed 2026-09-10] | Billed "in per-minute increments," described as "pure usage-based" — not confirmed as true per-second [checkthat.ai/brands/lambda-labs/pricing, accessed 2026-09-10]. | Lambda instances are persistent VMs, not serverless — no scale-to-zero; you provision and terminate manually. Zero egress fees are a stated differentiator. | **Not found** — no HIPAA/BAA information located for Lambda Labs in this pass. | No confirmed one-click MedGemma/Gemma deploy found; Lambda ships pre-configured ML environments, not a model catalog with 1-click serving. |
| **Vast.ai** | **$0.20/h** (marketplace rate as advertised) [vast.ai/pricing/gpu/L4, accessed 2026-09-10] | Not directly found for A10/L40S in this pass. | A100 SXM4: **from $0.13/h**; A100 PCIe: **from $0.27/h**; broader marketplace average for A100 80GB **≈$0.72/h** in early 2026 [vast.ai/pricing/gpu/A100-SXM4, A100-PCIE; medium.com/@velinxs/cheap-a100-rentals-find-the-best-deals-in-2026, accessed 2026-09-10] | Not found specifically (Vast.ai's catalog spans many H100 listings but no single quoted figure was extracted this pass). | Marketplace-style; per-second/per-minute billing generally supported, exact minimum not found. Prices are **spot/marketplace**, set by supply and demand, and interruption is possible on some listings. | No platform scale-to-zero abstraction — you rent and release instances yourself; cold start = however long the specific host takes to hand off the instance plus your model load. | **Not found — almost certainly no BAA available.** Vast.ai is a peer-to-peer GPU marketplace; do not plan to put PHI here without independently confirming compliance posture, which was not found in this research. | No vendor one-click model catalog found; you bring your own image. Cheapest raw compute in this survey by a wide margin, at the cost of reliability/compliance guarantees. |
| **Fly.io** | Not found (no L4 SKU located). | L40S: **$1.25/h** ("cutting L40S prices in half" post) [fly.io/blog/cutting-prices-for-l40s-gpus-in-half, accessed 2026-09-10] | A100 80GB SXM: **$3.50/h** [fly.io/blog/fly-io-has-gpus-now, accessed 2026-09-10] | Not found. | Not found — Fly.io GPU billing model details not retrieved this pass. | **Status is uncertain/conflicting**: a secondary source states "as of June 2026, Fly.io GPU service is deprecated and was unavailable through 2025" [source found via search, exact URL not individually captured — treat with caution], while Fly's own docs page (fly.io/docs/gpus/) still appeared indexed. **Recommend confirming directly with Fly.io before planning around this option** — do not treat Fly.io GPUs as a reliable current option based on this research. | Not found. | Given the deprecation signal, Fly.io GPUs should be treated as **high risk / possibly discontinued** for new MediAgent planning. |
| **Hugging Face Inference Endpoints (dedicated)** | GCP-hosted: **$0.70/h**; AWS-hosted: **$0.80/h** [eesel.ai/blog/hugging-face-pricing; privacyai.acmeup.com API pricing page, accessed 2026-09-10] | Not found specifically for A10/L40S. | GCP-hosted A100: **$3.60/h**; AWS-hosted A100: **$2.50/h** | Not found. | Billed hourly while the endpoint is in "initializing" or "running" state, **regardless of request volume** — this is not true per-second/per-request billing [eesel.ai, accessed 2026-09-10]. | Autoscale-to-zero is configurable on dedicated Endpoints (idle timeout triggers scale-down); the platform still bills for the "initializing" period on every cold start. Specific cold-start seconds for a 4B–12B model: **not found**, though general community reports place it in the tens of seconds once the image/weights are cached. | **Not found for standard Inference Endpoints** — one source notes HF Endpoints has "helped platforms... simplify HIPAA-compliant Transformer deployments" but explicitly states **"native HIPAA regions are not currently available"** [techjacksolutions.com/ai-tools/hugging-face/hugging-face-inference-api, accessed 2026-09-10]. HF's **Enterprise** plan may offer more (24/7 SLA, dedicated support) but a BAA was not confirmed. | **Yes** — Gemma models have a documented one-click "Deploy → Inference Endpoints" button on the model page, and a curated **Gemma Collection** in the Inference Endpoints Catalog lets you deploy gemma-3-12b-it/27b-it with pre-set optimized TGI configs in one click [endpoints.huggingface.co/catalog/collection/gemma; endpoints.huggingface.co/new?repository=google%2Fgemma-7b-it, accessed 2026-09-10]. **MedGemma one-click on HF: not explicitly found**, though MedGemma model cards are hosted on HF and the same generic "Deploy" button mechanism likely applies — not independently confirmed for MedGemma specifically. |
| **Nebius (AI Cloud)** | **Not found** — no L4 SKU located in Nebius's published lineup; Nebius's catalog in this pass skewed to L40S/H100/H200. | L40S (Intel CPU host): **$0.90–$1.82/h**; L40S (AMD CPU host): **$0.74–$1.55/h** [computeprices.com/providers/nebius; gpuperhour.com/providers/nebius, accessed 2026-09-10] | A100: figures conflicted between sources — **$2.10–$2.50/h** in one 2026 aggregator vs. an older **$1.00–$1.20/h** figure that looks stale; **treat $2.10–2.50/h as the more current estimate but verify directly against nebius.com/prices**, which did not render fully in this pass. | H100 SXM5: **from $1.25/h**; HGX H100: **$2.15/h on-demand**, up to **$3.85/h** for higher tiers; H200 SXM5: **$4.50/h** [spheron.network/blog/gpu-cloud-pricing-comparison-2026; computeprices.com, accessed 2026-09-10] | Not found specifically. | Not found for Nebius's core GPU-cloud product; scale-to-zero appears to apply to Nebius's separate "Token Factory" managed-inference product rather than raw GPU rental. | Nebius (core AI Cloud) holds **SOC 2 Type II including HIPAA, ISO 27001, and ISO 27799**; for the **Nebius Token Factory** managed-inference product specifically, PHI use **requires an executed BAA**, after which supported endpoints with proper configuration become eligible to carry PHI [docs.tokenfactory.nebius.com/legal/hipaa-guideline; nebius.com/solutions/life-sciences-and-healthcare, accessed 2026-09-10]. | No confirmed one-click MedGemma/Gemma deploy on raw Nebius GPU rental found; Token Factory is a managed-inference layer that may support open models, but 1-click Gemma/MedGemma support was not confirmed. |
| **Together AI (dedicated endpoints)** | **Not found.** | **Not found** (A10G/L40S not in Together's published dedicated-endpoint lineup found this pass). | **Not found** (A100 not listed in the dedicated-endpoint figures surfaced — Together's dedicated tier in this pass skewed to H100/B200 only). | H100 80GB: **$6.49/h** (single); HGX H100 cluster: **$5.49/h/GPU**; reserved H100: **from $2.55/h**; on-demand B200: **up to $7.49/h**; HGX B200 180GB: **$11.95/h** [cloudzero.com/blog/together-ai-pricing; pricepertoken.com/endpoints/together, accessed 2026-09-10] | Not found specifically. | Not found for dedicated endpoints. | **Not found** — attempting to fetch Together's trust/security page returned a 404 in this pass, and no other source confirmed or denied a Together AI BAA. **Explicitly unconfirmed — do not assume HIPAA support.** | No confirmed one-click MedGemma/Gemma deploy found for Together's dedicated tier; Together is generally positioned around its own curated serverless model list rather than open one-click BYO-model hosting for Gemma/MedGemma specifically. |
| **Oracle Cloud Infrastructure (OCI)** | Not found for L4 specifically. | A10 (VM.GPU.A10.1): **from ≈$1.27/h** pay-as-you-go [oraclelicensingexperts.com/blog/oracle-cloud-gpu-skus-pricing, accessed 2026-09-10] | A100: **$4.00/h** | H100: **$10.00/h** flat regardless of region; AMD MI300X (192GB): **$6.00/GPU-h**; spot/interruptible from **$1.09/h** [thundercompute.com/blog/oracle-cloud-oci-gpu-pricing; oraclelicensingexperts.com, accessed 2026-09-10] | Not found specifically. | No native serverless/scale-to-zero abstraction found for OCI GPU compute — it is IaaS VM/bare-metal rental. | Not found in this pass — Oracle is generally understood to offer enterprise BAAs across its cloud portfolio, but this was **not independently confirmed** here. | No confirmed one-click MedGemma/Gemma deploy found on OCI. |

---

## 2. Cost scenarios

All monthly figures use **730 hours/month** (8,760 h/yr ÷ 12) for "24/7," **60 hours/month** for "2 hours/day," and **360 hours/month** for "12 hours/day." These are **compute-only** costs; they exclude storage, networking/egress, and any management/orchestration overhead, and (except where a management fee is explicitly stacked, e.g. Vertex) exclude platform fees not captured in the hourly GPU rate.

### Scenario 1 — One L4-class instance, 24/7 (730 h/month)

| Provider / SKU | Rate | Monthly cost | Source |
|---|---|---|---|
| GCP Compute Engine g2-standard-4 (on-demand) | $0.71/h | **$518** | CONTEXT.md; thundercompute.com |
| GCP Compute Engine g2-standard-4 (spot, ~12% off) | $0.62/h | **$453** | usage.ai (unreliable — eviction risk, only ~12% discount) |
| GCP Compute Engine g2-standard-4 (1-yr CUD, ~8% off) | $0.65/h | **$477** | usage.ai |
| GCP Cloud Run GPU (kept warm 24/7, all-in) | $0.77/h | **$562** | CONTEXT.md |
| GCP Vertex Model Garden (L4 + est. mgmt fee) | ~$0.74/h (estimated) | **~$540** | spheron.network, extrapolated mgmt-fee ratio |
| AWS EC2 g6.xlarge (on-demand) | $0.805/h | **$588** | instances.vantage.sh |
| AWS EC2 g6.xlarge (spot) | $0.685/h | **$500** | instances.vantage.sh |
| AWS SageMaker real-time (closest confirmed: ml.g5.xlarge, A10G) | $1.01/h | **$737** | cloudchipr.com |
| Azure NV A10 v5 | $1.117/h | **$815** | thundercompute.com |
| HF Inference Endpoints (GCP-hosted L4) | $0.70/h | **$511** | eesel.ai |
| HF Inference Endpoints (AWS-hosted L4) | $0.80/h | **$584** | eesel.ai |
| RunPod Pod, Secure Cloud (L4) | $0.49/h | **$358** | runpod.io/pricing |
| RunPod Pod, Community Cloud (L4, no HIPAA) | $0.44/h | **$321** | runpod.io/pricing |
| Baseten dedicated (L4) | $0.85/h | **$619** | costbench.com |
| Modal (L4, base rate, no region multiplier) | $0.80/h | **$583** | spheron.network |
| Modal (L4, broad-region 1.5× multiplier) | $1.20/h | **$875** | spheron.network |
| Vast.ai marketplace (L4, no HIPAA/SLA) | $0.20/h | **$146** | vast.ai/pricing/gpu/L4 |

**Read:** for an always-on single GPU, GCP Compute Engine on-demand (~$518/mo) and RunPod Secure Cloud (~$358/mo) bracket the realistic "compliant, reliable" range; Vast.ai is far cheaper (~$146/mo) but carries no confirmed HIPAA posture and marketplace/eviction risk.

### Scenario 2 — Scale-to-zero, 2 hours/day active use (60 h/month)

| Provider / SKU | Rate | Monthly cost (compute only) | Notes |
|---|---|---|---|
| Cloud Run GPU (all-in) | $0.77/h | **$46.20** | True platform scale-to-zero; best fit for this pattern |
| Cloud Run GPU (GPU-only portion, non-zonal) | $0.67/h | **$40.20** | Lower-bound if CPU/mem portion counted separately |
| RunPod Serverless (L4) | $0.69/h | **$41.40** | Per-second billing on active time |
| Modal (L4, base rate) | $0.80/h | **$48.00** | Before region multiplier |
| Modal (L4, 1.5× region multiplier) | $1.20/h | **$72.00** | |
| Vertex Model Garden (L4, if "Scale To Zero eligible") | ~$0.74/h | **~$44.40** | **Unconfirmed for Model Garden/MedGemma-Gemma deployments** — default behavior is ≥1 replica always on, i.e. Scenario 1 cost, not this one |
| GKE Autopilot (manual scale-to-0 via custom autoscaler) | ~$0.70/h | **~$42.00** | Requires engineering effort; not a native feature |
| Compute Engine (manual stop/start automation) | $0.71/h | **$42.60** | Requires a scheduler/automation layer + tolerates 20–60s VM boot on each cold start |

**Read:** true serverless-GPU platforms (Cloud Run GPU, RunPod Serverless, Modal) turn a 2-hour/day usage pattern into a **~$40–75/month** bill — roughly an order of magnitude cheaper than keeping a dedicated instance warm 24/7. Vertex Model Garden's default behavior does **not** give you this benefit unless the (unconfirmed) new scale-to-zero tier applies to your deployment.

### Scenario 3 — Warm 12 hours/day (360 h/month)

| Provider / SKU | Rate | Monthly cost | Notes |
|---|---|---|---|
| Cloud Run GPU (all-in) | $0.77/h | **$277.20** | |
| GCP Compute Engine (started/stopped daily) | $0.71/h | **$255.60** | Plus automation overhead |
| Vertex Model Garden (L4 + est. mgmt fee) | ~$0.74/h | **~$264.96** | Only if scale-to-zero honored off-hours; otherwise this reverts to the Scenario 1 24/7 figure (~$540/mo) since the documented default is ≥1 replica always on |
| RunPod Pod, Secure Cloud (L4) | $0.49/h | **$176.40** | Persistent pod started/stopped around the 12h window |
| Modal (L4, base rate) | $0.80/h | **$288.00** | |
| HF Inference Endpoint (GCP L4, autoscale outside window) | $0.70/h | **$252.00** | |

**Read:** for a "business hours" usage pattern, RunPod Secure Cloud Pods (manually scheduled) are the cheapest compliant-tier option found (~$176/mo); Cloud Run GPU is a close, lower-effort alternative (~$277/mo, no automation needed) because it is priced and billed per-second natively rather than requiring a stop/start script.

### Scenario 4 — A100-80GB, 24/7, for a 32B bf16 model (730 h/month)

A 32B model in bf16 needs ~64GB of weights alone, so it requires an 80GB-class GPU (A100 80GB or better); L4/A10G (24GB) and even A100 40GB cannot hold it comfortably with KV cache headroom.

| Provider / SKU | Rate | Monthly cost | Notes |
|---|---|---|---|
| GCP Compute Engine (a2-ultragpu-1g, A100 80GB, on-demand) | $5.03/h | **$3,672** | CONTEXT.md baseline |
| GCP Vertex Model Garden (A100 80GB + mgmt fee, estimated ~15%) | ~$5.78/h | **~$4,219** | Extrapolated from the confirmed A100-40GB/H100 fee ratio |
| Azure NC A100 v4 (80GB, on-demand) | $3.673/h | **$2,681** | Cheapest confirmed hyperscaler on-demand A100 80GB in this survey |
| Azure NC A100 v4 (spot) | ~$1.15/h | **~$840** | Eviction risk |
| Lambda Labs (A100 80GB SXM, on-demand) | $2.79/h | **$2,037** | Availability can be capacity-constrained/waitlisted |
| RunPod Pod, Secure Cloud (A100 80GB) | $1.59/h | **$1,161** | HIPAA/SOC2-eligible tier |
| RunPod Pod, Community Cloud (A100 80GB, no HIPAA) | $1.19–$1.39/h | **$868–$1,015** | Not the compliant tier |
| Baseten dedicated (A100 80GB) | $4.00/h | **$2,920** | HIPAA-compliant, SOC 2 Type II |
| Nebius (A100, estimated) | $2.10–$2.50/h | **$1,533–$1,825** | Range unconfirmed against Nebius's own pricing page directly |
| HF Inference Endpoints (AWS-hosted A100) | $2.50/h | **$1,825** | No confirmed HIPAA/BAA for standard Endpoints |
| HF Inference Endpoints (GCP-hosted A100) | $3.60/h | **$2,628** | Same caveat |
| Vast.ai marketplace (A100 80GB, no HIPAA/SLA) | ~$0.72/h | **~$526** | Cheapest by far; no compliance guarantee |
| Oracle OCI (A100, generic) | $4.00/h | **$2,920** | Region/SKU-specific rate not fully broken out |

**Read:** for a 24/7 A100-80GB commitment, **Azure NC A100 v4 on-demand (~$2,681/mo)** and **RunPod Secure Cloud (~$1,161/mo)** are the cheapest options that carry a plausible compliance story; GCP's own on-demand rate (~$3,672/mo, CONTEXT.md baseline) is among the most expensive hyperscaler options for this exact SKU in this survey. Vast.ai is dramatically cheaper (~$526/mo) but with no confirmed HIPAA posture.

---

## 3. Throughput analysis (tokens/second on one L4, vLLM)

**No directly-published vLLM benchmark for Gemma-class 4B or 12B models specifically on an L4 GPU was located in this research pass** (the WebSearch budget for this session was exhausted before a targeted L4 result could be found — see §4). The figures below are therefore an **estimate**, derived by scaling a measured A100 40GB vLLM benchmark by the L4-vs-A100 memory-bandwidth ratio, and should be treated as directional, not authoritative.

**Measured baseline (A100 40GB, vLLM, 50 concurrent requests):**
- Gemma3-4B: **3,976.92 tok/s total throughput**, of which **3,385.72 tok/s is output/decode** [databasemart.com/blog/vllm-gpu-benchmark-a100-40gb, accessed 2026-09-10].
- Gemma3-12B: **477.49 tok/s total throughput**, of which **401.91 tok/s is output/decode**, at the same 50-concurrency setting [same source].
- A100 40GB memory bandwidth: **~1.5 TB/s** (1,555 GB/s) per the same source's own hardware description.

**NVIDIA L4 spec (official):** 24GB memory, **300 GB/s memory bandwidth**, 242 TFLOPS FP16/BF16 tensor *with sparsity* (≈121 TFLOPS dense) [nvidia.com/en-us/data-center/l4, accessed 2026-09-10].

L4-to-A100 memory-bandwidth ratio: 300/1,555 ≈ **0.193**. Small-model batched decode on these architectures is generally closer to memory-bandwidth-bound than compute-bound (weights and KV-cache must be re-read from HBM on every decode step), so bandwidth ratio is used as the primary scaling factor, with the caveat that L4's dense-compute ratio to A100 (≈121/312 ≈ 0.39) is roughly double the bandwidth ratio — meaning the true L4 number could land anywhere between these two scaling factors depending on how compute- vs. bandwidth-bound the actual batch mix is.

**Estimated L4 output/decode throughput (at similar ~50-request concurrency):**
- **4B model: ≈ 3,385.72 × 0.193 ≈ 650 tokens/second** (estimated range, using bandwidth-only scaling as the conservative floor: ~650–1,300 tok/s if compute-ratio scaling applies instead).
- **12B model: ≈ 401.91 × 0.193 ≈ 78 tokens/second** (estimated range: ~78–155 tok/s).

A material caveat for the 12B case specifically: a 12B model in bf16 needs **~24GB just for weights**, which is the entire capacity of an L4 — there is little to no room left for KV cache at any meaningful concurrency. In practice, running a 12B model on a single L4 with vLLM would likely require **int8 or int4 quantization** to leave headroom for KV cache and batching, which would change the throughput math (quantization can *increase* achievable throughput on bandwidth-bound hardware, partially offsetting the capacity squeeze) — this was not separately modeled here.

### Does one L4 cover scenario B and C chat volumes?

Using CONTEXT.md's monthly workload numbers and treating the higher-quality, higher-token tasks (chat replies, patient explanations, SOAP notes, document structuring) as candidates for a **12B-class** model, and the lightweight tasks (chat classification, safety classifier) as candidates for a **4B-class** model:

**Scenario B (one clinic) — 12B-relevant output tokens/month:**
- Chat replies: 60,000 × 250 = 15,000,000
- Patient explanations: 15,000 × 350 = 5,250,000
- SOAP notes: 1,500 × 600 = 900,000
- Documents: 3,000 × 700 = 2,100,000
- **Total ≈ 23.25M output tokens/month**

**Scenario C (10 clinics) — same mix ×10 ≈ 232.5M output tokens/month.**

One L4 running a 12B model continuously (100% duty cycle, which is unrealistic but useful as a ceiling) at the estimated ~78 tok/s would generate:
78 tok/s × 2,592,000 s/month (730h×3600, approximating 24/7) ≈ **~202M output tokens/month theoretical ceiling.**

- **Scenario B (23.25M tokens) uses only ≈11–12% of that ceiling** — one L4 comfortably covers scenario B's 12B-class workload even accounting for bursty, non-uniform traffic across the day.
- **Scenario C (232.5M tokens) is at ≈115% of the estimated ceiling** — one L4 running a 12B model in bf16 is **likely insufficient** for scenario C on a naive 24/7-average basis, and would be substantially more insufficient once you account for real traffic being concentrated in clinic hours (roughly 8–10 hours/day) rather than spread evenly across 24 hours — effective usable capacity in that case drops to roughly a third to a half of the theoretical ceiling. Scenario C would need either: a bigger GPU (A100/L40S-class), a quantized 12B model to raise throughput, or multiple L4 instances behind a load balancer.

The 4B-class classification/safety-classifier workload (60,000 × 2 calls/month for scenario B, both well under 100 output tokens each) is tiny by comparison — well under 1% of a single L4's estimated ~650 tok/s ceiling for scenario B, and still comfortably inside it for scenario C — so the binding constraint is the 12B-class generation workload, not the lightweight classification calls.

**Bottom line:** on these (estimated, unverified) throughput numbers, **one L4 plausibly covers scenario B's higher-quality generation workload with meaningful headroom, but not scenario C's**, which would need either a larger GPU tier or horizontal scaling.

---

## 4. Break-even vs. the Gemini 3.5 Flash-Lite baseline

CONTEXT.md's measured baseline is **~$0.0015 per chat turn** on Gemini 3.5 Flash-Lite. Using that as the yardstick, the monthly chat-turn count at which a fixed-cost self-hosted GPU becomes cheaper than paying per-turn to Gemini is:

**break-even turns/month = (monthly GPU cost) ÷ $0.0015**

| Hosting option (chat-serving only) | Monthly cost | Break-even chat turns/month |
|---|---|---|
| Cloud Run GPU, scale-to-zero @ 2h/day (Scenario 2) | ~$46 | **~31,000** |
| Vast.ai marketplace L4, 24/7 (no HIPAA/SLA) | ~$146 | **~97,000** |
| Cloud Run GPU, warm 12h/day (Scenario 3) | ~$277 | **~185,000** |
| RunPod Secure Cloud L4, 24/7 (HIPAA-eligible tier) | ~$358 | **~239,000** |
| GCP Compute Engine on-demand L4, 24/7 | ~$518 | **~345,000** |
| AWS EC2 g6.xlarge on-demand, 24/7 | ~$588 | **~392,000** |

Set against CONTEXT.md's chat-turn volumes (A = 3,000/mo, B = 60,000/mo, C = 600,000/mo):

- **Scenario A (3,000 turns/month)** never clears even the cheapest break-even point (~31,000 turns) — stay on the Gemini API for the demo.
- **Scenario B (60,000 turns/month)** clears the Cloud-Run-scale-to-zero break-even (~31,000) comfortably, but **falls short of every "always-warm" or dedicated-instance break-even** (~97,000 and up). This means: **a true scale-to-zero deployment (Cloud Run GPU or RunPod Serverless) can already be cheaper than Gemini for chat alone at clinic scale**, but a persistently-warm dedicated GPU (Compute Engine, RunPod Pod, EC2) would not pay for itself on chat volume alone at this scale.
- **Scenario C (600,000 turns/month)** clears every break-even point in the table, including the most expensive dedicated-instance options (~345,000–392,000) — self-hosting chat inference is unambiguously cheaper than the Gemini baseline at 10-clinic scale, on chat-turn cost alone.

**Important caveat on this comparison:** this break-even treats the GPU as serving **only** chat turns. In reality the same GPU/model would also serve some mix of document structuring, patient explanations, SOAP notes, and the safety classifier — all of which have their own Gemini-baseline cost-per-call (~$0.002–0.005/document per CONTEXT.md) that should be added to the "Gemini-cost-avoided" side of the ledger, which would **improve** the economics of self-hosting relative to the numbers above (i.e., these break-even points are conservative/pessimistic for self-hosting, since they ignore the other workloads a shared GPU would also offload from Gemini). A fuller model should sum all workload types' Gemini-avoided cost against the shared GPU's fixed monthly cost, rather than analyzing chat turns in isolation.

---

## 5. Confidence and gaps

- **WebSearch budget exhausted mid-research.** This session's WebSearch tool hit a hard 200-call session cap before a few planned follow-up queries could run (notably: a direct L4-specific vLLM throughput benchmark, and Lambda Labs/Nebius/Together AI list-price confirmation via their own pricing pages). Every number flagged "estimated" or "not found" above should be treated as lower-confidence than numbers with a direct official-page citation.
- **Official pricing pages largely did not render via WebFetch.** Google Cloud's `cloud.google.com/run/pricing`, `cloud.google.com/products/compute/gpus-pricing`, and `cloud.google.com/products/compute/pricing/accelerator-optimized`, and AWS's `aws.amazon.com/ec2/pricing/on-demand`, all returned truncated/JS-shell content that the fetch tool could not extract pricing tables from. The one clean exception was **AWS Bedrock's pricing page** (`aws.amazon.com/bedrock/pricing`), which rendered fully and is the single most authoritative number in this report (Custom Model Import at $0.05718/CMU-min). Every other Google/AWS/Azure number here is sourced from third-party aggregator sites (instances.vantage.sh, cloudprice.net, DevZero, etc.) that scrape or mirror official pricing — generally reliable but one hop removed from the primary source, and could drift out of date faster than the official page.
- **L4 vLLM throughput for Gemma-class 4B/12B models is an estimate, not a measurement.** No published benchmark specifically for L4 + these model sizes was located; the figures in §3 were derived by scaling a measured A100 40GB benchmark by the L4/A100 memory-bandwidth ratio (0.193), with a noted alternative compute-ratio scaling factor (0.39) that would roughly double the estimate. Real-world throughput will also depend heavily on quantization choice, batch/concurrency tuning, and whether the 12B model fits in L4's 24GB with adequate KV-cache headroom in bf16 at all (borderline) — treat the throughput-based capacity conclusions in §3 as directional guidance for further load testing, not a procurement-grade number.
- **HIPAA/BAA status is confirmed for Google Cloud (Compute Engine/GKE/Cloud Run/Vertex AI), AWS (EC2/SageMaker/Bedrock), Azure (ML/Foundry), Modal, RunPod, Baseten, and Nebius (with caveats on which product tier).** It is **explicitly unconfirmed** for Together AI (site fetch 404'd, no other source found), Replicate, Lambda Labs, Vast.ai, Fly.io, and Oracle OCI — do not plan to route PHI to any of these six without direct, current confirmation from the vendor.
- **Google's own Vertex AI BAA coverage has a documented ambiguity in the sources found**: one authentech.ai analysis specifically flags that the *named* product "Vertex AI" may not appear on Google's self-serve BAA list, only "Vertex AI Workbench." This directly matters for MediAgent's plan to use Vertex AI Model Garden with PHI and should be verified against Google's current, authoritative HIPAA-included-services page before relying on Vertex Model Garden for any real patient data.
- **Vertex AI Model Garden's scale-to-zero behavior is unresolved.** One source states dedicated endpoints require ≥1 replica always on and bill continuously; another describes a newer "Scale To Zero" capability for "eligible" online-prediction deployments. Whether a MedGemma or Gemma Model Garden deployment qualifies for the newer behavior was not determined — this materially changes Scenario 2/3 economics for Vertex specifically and should be tested directly in a GCP project before budgeting around it.
- **SageMaker Serverless Inference's GPU support is actively disputed across sources** found in this pass — some 2026 blog content describes it as production-ready with A100 support, while an AWS GitHub feedback thread suggests GPU/CUDA support for Serverless Inference remains a feature request rather than a shipped capability. This should be verified directly against `docs.aws.amazon.com` before any planning assumes GPU-backed SageMaker Serverless Inference exists.
- **Fly.io GPU availability is a live conflict in the sources**: one source calls it deprecated as of 2026; Fly's own docs URL for GPUs still appeared indexed. Treat Fly.io as unreliable for planning purposes until directly confirmed.
- **Spot/CUD discount figures for GCP's G2 (L4) family look anomalously weak** compared to other GPU families (only ~12% spot discount, ~8–11% CUD discount, vs. 60–91% spot and 25–57% CUD typically cited for other machine families) — this was corroborated by two independent secondary sources, so it is likely a real characteristic of G2/L4 capacity economics rather than a data error, but it was not confirmed against Google's own rate card directly.
- **MedGemma's presence (or absence) in SageMaker JumpStart and Azure AI Foundry could not be confirmed either way with high confidence.** Gemma (non-medical) is clearly present in both catalogs with one-click deploy. MedGemma's confirmed one-click paths are Vertex AI Model Garden and (with lower confidence) Hugging Face's generic "Deploy" button mechanism.
- **SLA percentages were not captured for any provider in this pass** — every provider's specific uptime SLA (e.g., "99.9%") was out of scope for the searches run and should be pulled from each vendor's SLA page directly before a procurement decision, rather than assumed from this report.
- **Region/data-residency lists were largely not enumerated** beyond "wide" or "us-central1/us-east-1 confirmed" — if es-MX/California data-residency requirements are strict, each shortlisted provider's exact region list should be checked directly.
- **Endpoint lifecycle/retirement risk**: as a point of comparison, Google's own Gemini 2.5 Flash-Lite on Vertex has a retirement date that has already moved once and depends on Gemini 3 GA timing, with a stated minimum-six-months-notice policy once locked [discuss.ai.google.dev/t/gemini-2-5-flash-lite-retirement-date, docs.cloud.google.com/vertex-ai/generative-ai/docs/deprecations, accessed 2026-09-10]. No equivalent open-weights retirement-risk data point was found for MedGemma/Gemma itself (open weights you host yourself do not get "retired" by a vendor in the same way a hosted API model does — this is actually a structural argument in favor of self-hosting open weights for long-lived clinical workflows, since you control the model lifecycle rather than a vendor's deprecation calendar).

---

## 6. Sources

All accessed 2026-09-10 unless a different date is explicitly carried in the cited text.

- [Cloud Run pricing (cloudchipr summary)](https://cloudchipr.com/blog/cloud-run-pricing)
- [Google Cloud GPU Instances 2026 — Thunder Compute](https://www.thundercompute.com/blog/google-cloud-gpu-instances)
- [Compute Engine pricing 2026 (CUDs/SUDs/Spot) — usage.ai](https://www.usage.ai/blogs/gcp/compute-engine/)
- [L4 Cloud Pricing comparison — getdeploying.com](https://getdeploying.com/gpus/nvidia-l4)
- [Cloud Run pricing — official](https://cloud.google.com/run/pricing)
- [Cloud Run GPU pricing explained — gmicloud.ai](https://www.gmicloud.ai/en/blog/cloud-run-gpu-pricing-explained)
- [Deploy GPU workloads in Autopilot — GKE official docs](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/autopilot-gpus)
- [Which GPU instances are best on Google Cloud — Qovery](https://www.qovery.com/blog/google-cloud-gpu-instances-by-workload)
- [GKE Autopilot Accelerator Premiums — official SKU page](https://cloud.google.com/skus/sku-groups/gke-autopilot-accelerator-premiums)
- [Vertex AI Model Garden Pricing 2026 — Spheron](https://www.spheron.network/blog/vertex-ai-model-garden-pricing-2026-cost-vs-self-hosted/)
- [Vertex AI Pricing Complete 2026 Guide — nOps](https://www.nops.io/blog/vertex-ai-pricing/)
- [Google Compute Engine pricing guide 2026 — CloudZero](https://www.cloudzero.com/blog/google-cloud-compute-engine-pricing-guide/)
- [GPU pricing — Google Cloud official](https://cloud.google.com/products/compute/gpus-pricing)
- [Google Cloud GPU cost explained (A2/A3/G2) — gmicloud.ai](https://www.gmicloud.ai/en/blog/google-cloud-gpu-cost-explained)
- [Accelerator-optimized VM pricing — Google Cloud official](https://cloud.google.com/products/compute/pricing/accelerator-optimized)
- [g2-standard-4 pricing/specs — Vantage](https://instances.vantage.sh/gcp/g2-standard-4)
- [g2-standard-4 pricing — Holori calculator](https://calculator.holori.com/gcp/vm/g2-standard-4)
- [G6 SageMaker AI Inference region expansion — AWS official](https://aws.amazon.com/about-aws/whats-new/2026/07/g6-sagemaker-ai-inference/)
- [Amazon SageMaker AI pricing breakdown — CloudChipr](https://cloudchipr.com/blog/amazon-sagemaker-pricing)
- [g6e.4xlarge pricing/specs — DevZero](https://www.devzero.io/instances/aws/g6e.4xlarge)
- [g6e.xlarge pricing/specs — DevZero](https://www.devzero.io/instances/aws/g6e.xlarge)
- [g6.xlarge pricing/specs — Vantage](https://instances.vantage.sh/aws/ec2/g6.xlarge)
- [g5.xlarge pricing/specs — Vantage](https://instances.vantage.sh/aws/ec2/g5.xlarge)
- [EC2 On-Demand Instance Pricing — AWS official](https://aws.amazon.com/ec2/pricing/on-demand/)
- [SageMaker Serverless Inference GPU support 2026 — DeployBase](https://deploybase.ai/articles/sagemaker-serverless-inference-gpu)
- [GPU/CUDA for Serverless Inference — AWS GitHub feedback issue #233](https://github.com/aws/amazon-sagemaker-feedback/issues/233)
- [Amazon Bedrock pricing — AWS official](https://aws.amazon.com/bedrock/pricing/)
- [Amazon Bedrock Custom Model Import GA announcement — AWS official](https://aws.amazon.com/about-aws/whats-new/2024/10/amazon-bedrock-custom-model-import)
- [AWS Bedrock HIPAA eligibility — Qualix Solutions](https://qualixsolutions.com/aws-bedrock-consultants/hipaa-eligible-baa/)
- [AWS HIPAA-eligible services 2026 — Patient Protect](https://patient-protect.com/aws-hipaa-eligible-services)
- [AWS HIPAA BAA self-serve via Artifact — baagenerator.com](https://baagenerator.com/blog/does-aws-sign-a-baa)
- [Azure NC A100 vs Thunder Compute — Thunder Compute](https://www.thundercompute.com/blog/azure-nc-a100-vs-thunder-compute)
- [NC24ads A100 v4 pricing/specs — Vantage](https://instances.vantage.sh/azure/vm/nc24ads-v4)
- [Standard_NC24ads_A100_v4 pricing — CloudPrice](https://cloudprice.net/vm/Standard_NC24ads_A100_v4)
- [What AI models are covered under the BAA — Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/5942711/what-ai-models-are-covered-under-the-baa)
- [Comprehensive overview of HIPAA-eligible Azure AI services — Simbo AI](https://www.simbo.ai/blog/a-comprehensive-overview-of-hipaa-eligible-azure-ai-services-and-how-to-properly-configure-them-for-compliance-755427/)
- [Gemma 4 now available in Microsoft Foundry — Microsoft Community Hub](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/gemma-4-now-available-in-microsoft-foundry/4510984)
- [Microsoft adds Gemma 4 to Azure AI Foundry — Redmondmag](https://redmondmag.com/blogs/redmond-dispatch/2026/04/microsoft-adds-gemma-4-model.aspx)
- [Modal GPU pricing 2026 per-second billing — Spheron](https://www.spheron.network/blog/modal-gpu-pricing-2026-per-second-billing/)
- [Modal is SOC 2 Type II compliant — Modal official blog](https://modal.com/blog/soc2type2)
- [Security and privacy at Modal — Modal official docs](https://modal.com/docs/guide/security)
- [RunPod GPU Cloud Pricing — official](https://www.runpod.io/pricing)
- [Cut vLLM cold starts to 90 seconds on RunPod Serverless — RunPod official blog](https://www.runpod.io/blog/cut-vllm-cold-starts-runpod-serverless)
- [Runpod achieves HIPAA and GDPR compliance — RunPod official press](https://www.runpod.io/press/runpod-meets-hipaa-and-gdpr-standards)
- [AI infrastructure security & compliance — RunPod official](https://www.runpod.io/legal/compliance)
- [How to find HIPAA/GDPR-compliant GPUs on RunPod and understand BAA policy — RunPod help](https://contact.runpod.io/hc/en-us/articles/50120688006163-How-to-Find-HIPAA-GDPR-Compliant-GPUs-on-Runpod-and-Understand-BAA-Policy)
- [Replicate pricing 2026 per-second cost — Spheron](https://www.spheron.network/blog/replicate-pricing-2026-per-second-cost/)
- [Replicate pricing — official](https://replicate.com/pricing)
- [Baseten pricing 2026, GPU inference from $0.63/hour — CostBench](https://costbench.com/software/ai-model-hosting/baseten/)
- [How does Baseten make money: GPU-minute pricing — ValueAddVC](https://valueaddvc.com/blog/how-does-baseten-make-money-gpu-minute-pricing-600m-arr-and-the-13b-valuation-breakdown)
- [Baseten announces HIPAA compliance — Baseten official blog](https://www.baseten.co/blog/baseten-announces-hipaa-compliance/)
- [Lambda Cloud H100 pricing 2026 — Spheron](https://www.spheron.network/blog/lambda-cloud-h100-pricing-2026/)
- [Lambda Labs GPU pricing 2026, A100/H100 costs — SynpixCloud](https://www.synpixcloud.com/blog/lambda-labs-gpu-pricing-2026)
- [Lambda Labs pricing 2026 — CheckThat.ai](https://checkthat.ai/brands/lambda-labs/pricing)
- [Rent A100 SXM4 GPUs on Vast.ai — official](https://vast.ai/pricing/gpu/A100-SXM4)
- [Rent A100 PCIE GPUs on Vast.ai — official](https://vast.ai/pricing/gpu/A100-PCIE)
- [Rent L4 GPUs on Vast.ai — official](https://vast.ai/pricing/gpu/L4)
- [Cheap A100 rentals 2026 — Medium](https://medium.com/@velinxs/cheap-a100-rentals-find-the-best-deals-in-2026-ddeae320a324)
- [We're cutting L40S prices in half — Fly.io official blog](https://fly.io/blog/cutting-prices-for-l40s-gpus-in-half/)
- [Fly.io has GPUs now — Fly.io official blog](https://fly.io/blog/fly-io-has-gpus-now/)
- [Fly GPUs — Fly.io official docs](https://fly.io/docs/gpus/)
- [Hugging Face pricing explained 2026 — eesel AI](https://www.eesel.ai/blog/hugging-face-pricing)
- [Inference Endpoints GPU L4 pricing — privacyai.acmeup.com](https://privacyai.acmeup.com/api/huggingface_huggingface_inference-endpoints-gpu-l4.html)
- [Inference Endpoints (dedicated) documentation — Hugging Face official](https://huggingface.co/docs/inference-endpoints/main/guides/access)
- [Deploy google/gemma-7b-it — Hugging Face Inference Endpoints official](https://endpoints.huggingface.co/new?repository=google%2Fgemma-7b-it)
- [Gemma Collection — Hugging Face Inference Endpoints Catalog](https://endpoints.huggingface.co/catalog/collection/gemma)
- [Hugging Face Inference API pricing 2026 — TechJack Solutions](https://techjacksolutions.com/ai-tools/hugging-face/hugging-face-inference-api/)
- [NVIDIA GPU pricing — Nebius official](https://nebius.com/prices)
- [GPU cloud pricing comparison 2026 — Spheron](https://www.spheron.network/blog/gpu-cloud-pricing-comparison-2026/)
- [Nebius GPU pricing — ComputePrices.com](https://computeprices.com/providers/nebius)
- [Nebius GPU pricing — GPUPerHour](https://gpuperhour.com/providers/nebius)
- [HIPAA & BAA support for Nebius Token Factory — Nebius official docs](https://docs.tokenfactory.nebius.com/legal/hipaa-guideline)
- [Cloud for scientific AI and healthcare — Nebius official](https://nebius.com/solutions/life-sciences-and-healthcare)
- [Together AI pricing 2026 — CloudZero](https://www.cloudzero.com/blog/together-ai-pricing/)
- [Together AI pricing, serverless & dedicated endpoints — Price Per Token](https://pricepertoken.com/endpoints/together)
- [Oracle Cloud (OCI) GPU pricing 2026 — Thunder Compute](https://www.thundercompute.com/blog/oracle-cloud-oci-gpu-pricing)
- [Oracle Cloud GPU SKU pricing 2026 — Oracle Licensing Experts](https://oraclelicensingexperts.com/blog/oracle-cloud-gpu-skus-pricing/)
- [MedGemma — Vertex AI Model Garden (official console listing)](https://console.cloud.google.com/vertex-ai/publishers/google/model-garden/medgemma)
- [MedGemma: our most capable open models for health AI development — Google Research official blog](https://research.google/blog/medgemma-our-most-capable-open-models-for-health-ai-development/)
- [MedGemma quick start with Model Garden — Google-Health GitHub official](https://github.com/google-health/medgemma/blob/main/notebooks/quick_start_with_model_garden.ipynb)
- [Deploy and inference Gemma using Model Garden — Google Cloud official docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-garden/deploy-and-inference-tutorial)
- [Integrating MedGemma into clinical workflows — Google Cloud official blog](https://cloud.google.com/blog/topics/developers-practitioners/integrating-medgemma-into-clinical-workflows-just-got-easier)
- [MedGemma get started — Google Health AI Developer Foundations official](https://developers.google.com/health-ai-developer-foundations/medgemma/get-started)
- [MedGemma 1.5 model card — Google Health AI Developer Foundations official](https://developers.google.com/health-ai-developer-foundations/medgemma/model-card)
- [google/medgemma-1.5-4b-it — Hugging Face official model card](https://huggingface.co/google/medgemma-1.5-4b-it)
- [Gemma 4 models now available in Amazon SageMaker JumpStart — AWS official](https://aws.amazon.com/about-aws/whats-new/2026/04/gemma-4-models-on-sagemaker-jumpstart/)
- [SageMaker JumpStart optimized deployments — AWS official](https://aws.amazon.com/about-aws/whats-new/2026/04/sagemaker-jumpstart-optimized-deployments/)
- [Gemma-4-E2B on SageMaker JumpStart — AWS official](https://aws.amazon.com/about-aws/whats-new/2026/07/gemma-4-e2b-on-sagemaker-jumpstart/)
- [FLUX.2/gemma-4-12B-it on SageMaker JumpStart — AWS official](https://aws.amazon.com/about-aws/whats-new/2026/01/flux.2-small-decoder-gemma-4-12B-it-on-sagemaker-jumpstart/)
- [GCP HIPAA compliance guide — TCSA](https://www.tcsa.in/frameworks/hipaa-sra/gcp-hipaa-compliance)
- [Is Google Vertex AI HIPAA compliant? The naming trap — Authentech](https://authentech.ai/healthcare/is-google-vertex-ai-hipaa-compliant/)
- [Enable Scale-to-Zero for Vertex AI prediction endpoints — OneUptime blog](https://oneuptime.com/blog/post/2026-02-17-how-to-enable-scale-to-zero-for-vertex-ai-prediction-endpoints-to-reduce-costs/view)
- [google_vertex_ai_endpoint_with_model_garden_deployment — Terraform Registry official](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/vertex_ai_endpoint_with_model_garden_deployment)
- [A100 40GB vLLM benchmark — DatabaseMart](https://www.databasemart.com/blog/vllm-gpu-benchmark-a100-40gb)
- [NVIDIA L4 GPU — official product page](https://www.nvidia.com/en-us/data-center/l4/)
- [Gemini 2.5 Flash-Lite retirement date discussion — Google AI Developers Forum](https://discuss.ai.google.dev/t/gemini-2-5-flash-lite-retirement-date-different-for-gemini-api-vs-vertex-ai/177897)
- [Generative AI on Vertex AI deprecations — Google Cloud official docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/deprecations)
