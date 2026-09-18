# Medical AI models: landscape and decisions for MediAgent — September 2026

**Status:** Research complete; decisions proposed. Companion to
[`ai-model-routing-spike-2026-09.md`](ai-model-routing-spike-2026-09.md) (routing evidence) and
[`../../docs/document-intelligence-assessment.md`](../../docs/document-intelligence-assessment.md)
(OCR and document tooling). **Date:** 2026-09-10. **Tracker:** `AI-002`.
**Scope:** every model class MediAgent touches, medical-specialised or not, judged for our nine
workloads, our two locales (`en-US`, `es-MX`), our licence position (a product, not a paper), and
our hosting reality (Vertex works, the free tier does not, no GPU host).

## 1. The two-minute answer

1. **There is no "medical LLM" upgrade waiting for us.** On the two benchmarks that use physician
   rubrics, the leaders are general frontier models: MedHELM Q2 2026 is led by Gemini 3.1 Pro
   (0.652) and Gemini 3.5 Flash (0.642); HealthBench (updated 2026-09-10) is led by Qwen3.8 Max
   (0.602) with the open-weight `gpt-oss-120b` (0.576) level with GPT-5.6 Sol (0.570). No
   medical fine-tune appears on either. The best open medical model with a verified score,
   Baichuan-M2 32B, self-reports 0.601 on HealthBench, which is level with, not above, those
   general models. Our own harness (spike §7) reached the same conclusion from the other side:
   `gemini-3.5-flash-lite` met every interactive-workload safety check we could measure.
2. **Medical specialisation pays off in four places, none of them the chat model:**
   deterministic drug terminology (RxNorm, RxClass, openFDA labels), Spanish clinical NER and
   SNOMED linking (free, Apache-licensed, from Spain's Plan-TL and BSC), medical speech
   (Deepgram Nova-3 Medical for English; Nova-3 multilingual with keyterms for Spanish), and a
   self-harm and emergency classifier as a second deterministic layer under the keyword floor.
3. **Licences rule most open medical LLMs out of a product.** Aloe (CC-BY-NC), Palmyra-Med
   (non-commercial), Meditron-3 ("research-only"), OpenBioLLM ("strongly advise against clinical
   use"), Med42 (M42 licence) are research assets. Commercially clean open medical models are
   MedGemma (HAI-DEF, with obligations), Baichuan-M2 (Apache 2.0), II-Medical (Apache 2.0),
   HuatuoGPT-o1 (Apache 2.0), and Lingshu (MIT). Clean general open models are Gemma 4 and Qwen
   (Apache 2.0) and `gpt-oss` (Apache 2.0).
4. **Spanish is the gap in every medical model family.** MedGemma's evaluations are "primarily
   English", MedASR is English-only, Nova-3 Medical documents English, Meditron, OpenBioLLM and
   Aloe evaluate in English. The multilingual medical retrieval benchmark published in June 2026
   (MMed-Bench-IR) states outright that no embedding model covers both multilingual and
   biomedical specialisation. Bilingual parity therefore comes from the general models plus the
   Spanish clinical NLP resources, and from our own paired scenarios, not from a medical model.

## 2. Landscape by model class

Prices and dates are as published on 2026-09-10. "Product OK" means the licence permits use in a
commercial supervised decision-support product without a separate agreement.

### 2.1 Open-weight medical LLMs

| Model | Base, size | Licence | Product OK | Languages evaluated | Evidence of quality | Fit for us |
| --- | --- | --- | --- | --- | --- | --- |
| **MedGemma 1.5** (`google/medgemma-1.5-4b-it`, 2026-01-13) | Gemma 3, 4B multimodal | HAI-DEF terms | Yes, with obligations: keep the use restrictions downstream, seek regulatory authorisation where applicable, never make Google a "device manufacturer"; fine-tunes inherit the terms | Primarily English | Google reports EHR interpretation and PDF-to-JSON lab extraction evaluations; ~91% MedQA | The one open medical model built for our extraction task and small enough to run locally; the zero-cost extraction lane once a host exists |
| MedGemma 1 27B (text, multimodal) | Gemma 3, 27B | HAI-DEF | Same | Primarily English | What the router names today; the endpoint is gone | Not worth re-deploying: a 27B GPU endpoint costs more per month than a year of Flash-Lite calls at our volume |
| **Baichuan-M2 32B** (2025-09) | Qwen2.5-32B | Apache 2.0 | Yes | English, Chinese | HealthBench 60.1 self-reported, "consensus" subset 91.5; runs 4-bit on one 24 GB GPU | Strongest open medical reasoning model with a clean licence; no Spanish evidence |
| II-Medical-8B / 8B-1706 | Qwen3-8B | Apache 2.0 (MIT for some releases) | Yes | English | Vendor HealthBench claims | Small, clean licence, unverified independently |
| HuatuoGPT-o1 (7B–72B) | Qwen2.5 / Llama 3.1 | Apache 2.0 | Yes | English, Chinese | Medical chain-of-thought reasoning research model | Reasoning-style outputs conflict with our no-chain-of-thought rule |
| Lingshu 7B / 32B | Qwen2.5-VL | MIT | Yes | English, Chinese | Multimodal medical MLLM | Imaging-oriented; not our need |
| Meditron-3 70B (EPFL) | Llama 3.1 70B | Llama 3.1 Community | "Research-only model", no clinical validation, per its own card | English | Guidelines + PubMed + MIMIC-derived training | Out for a product |
| OpenBioLLM 70B / 8B | Llama 3 | Meta Llama licence | Card "strongly advises against" clinical decision support | English | Self-reported 86% average on QA sets | Out for a product |
| Med42-v2 70B / 8B (M42) | Llama 3 | M42 Health licence | Check before use | English | Clinical QA suite | Out unless the licence is cleared |
| Aloe Beta 7B–72B (BSC, Barcelona) | Llama 3.1 / Qwen2.5 | CC-BY-NC-4.0 | No (non-commercial) | English; "capable but not evaluated" in others; CareQA is derived from Spanish MIR exams | Strong safety alignment work | Research reference for Spanish evaluation only |
| Palmyra-Med 70B (Writer) | Palmyra | Writer open-model, non-commercial | No | English | 85.9% average QA | Out; its NVIDIA NIM endpoint is listed as disabled |
| John Snow Labs Medical LLMs (1B–10B and larger) | Proprietary | Commercial Healthcare NLP licence | Yes, paid | English, "250+ languages" for Spark NLP | Vendor claims MedHELM mean win rate 77.78 | Commercial option if a licence budget exists; CPU-runnable small models |

### 2.2 General frontier models with healthcare programmes

| Model | Where it runs for us | Healthcare posture | Medical benchmark standing | Fit |
| --- | --- | --- | --- | --- |
| Gemini 3.1 Pro (preview), 3.5 Flash, 3.5 Flash-Lite, 3.8 Flash | Vertex AI (works today) | Vertex is BAA-eligible; no training on inputs | MedHELM Q2 2026: 3.1 Pro 0.652 (1st), 3.5 Flash 0.642 (2nd) | Measured in the spike; current recommendation |
| GPT-5.6 Sol / Terra / Luna; `gpt-oss-120b` | OpenAI API (no credentials); `gpt-oss` on Groq free tier or self-hosted | BAA only on zero-retention endpoints; ChatGPT for Healthcare is a GPT-5.2-based product | HealthBench: 0.570 / 0.570 / 0.558; `gpt-oss-120b` 0.576 | `gpt-oss-120b` is the notable one: Apache 2.0, frontier-level HealthBench, free on Groq for synthetic evaluation, self-hostable |
| Claude Opus 5 / Sonnet 5 / Haiku 4.5 | Anthropic API (no credentials) or Vertex AI | Claude for Healthcare (Jan 2026): HIPAA-ready, BAA via Bedrock, Vertex, Azure; connectors to CMS coverage, ICD-10, PubMed; PDF input with page citations | MedHELM Q2 2026: 8th and 9th (0.456, 0.45) | Strongest fit for document evidence (page-level citations); weaker MedHELM standing; needs credentials to measure |
| Qwen3.8 Max, Qwen 3.6 open weights | Alibaba Cloud API; open weights self-hosted (Apache 2.0) | No healthcare programme; data posture of the hosted API unclear for us | HealthBench 0.602 (1st) | Open Qwen weights are a legitimate zero-cost candidate; the hosted API is not |
| Microsoft Dragon Copilot | Product, not an API | Ambient documentation for clinicians | — | Competitor reference for SOAP drafting, not a component |

### 2.3 Clinical NLP: NER, entity linking, terminology

| Resource | Language | Licence | What it gives us |
| --- | --- | --- | --- |
| **RxNorm / RxNav** (NLM) | US drug vocabulary | Free, public | Ingredient and brand normalisation, already in `rxnorm_service.py`; the **drug-interaction API was discontinued 2024-01** and has not returned |
| **RxClass** (NLM) | US | Free, public | ATC / EPC / MoA classes: the deterministic basis for duplicate-therapy detection |
| **openFDA drug label** `drug_interactions`, `warnings`, `contraindications` | US labels | Public domain | Interaction and allergy-class text per label; pairs with DailyMed already ingested |
| DDInter 2.0 | Curated DDI database, 2,310 drugs, therapeutic duplications | Free web access; redistribution terms unclear, academic origin | Reference for the discrepancy engine's rules; verify licence before bundling |
| DrugBank | Commercial | Paid; free checker and DDI endpoint retired 2026-03-25 | Only if a budget exists |
| TwoSIDES (FAERS-mined) | Research | Research | Pharmacovigilance signal reference, not a rules source |
| SNOMED CT (Spanish edition exists), ICD-10-CM, UMLS | Terminology | UMLS licence via NLM (free for US users, registration) | Condition and allergy coding; SNOMED Spanish for `es-MX` |
| **PlanTL `bsc-bio-ehr-es`** + `bsc-bio-ehr-es-pharmaconer` | Spanish clinical | Apache 2.0 | Spanish clinical encoder; medication NER at F1 0.89 on PharmaCoNER; CPU-runnable |
| **ClinLinker / ClinLinker-KB** (ICB-UMA, BSC) | Spanish | Check model card | SNOMED-CT entity linking for Spanish clinical mentions (SapBERT bi-encoder + cross-encoder) |
| RigoBERTa Clinical (IIC), ClinText-SP | Spanish clinical | Check model card | Larger Spanish clinical encoder and corpus; also on AWS Marketplace |
| GLiNER-BioMed | English biomedical | Apache 2.0 (verify per checkpoint) | Zero-shot biomedical NER, small and fast; good candidate for English documents |
| MedCAT v2 (King's College London) | English (UMLS/SNOMED) | Elastic License 2.0, source-available | NER+linking to UMLS; not OSI-open, check terms |
| scispaCy, medspaCy, cTAKES | English | Apache 2.0 / MIT / Apache 2.0 | Classic pipelines; cTAKES is heavy; scispaCy has UMLS linking |
| SapBERT | English (multilingual variant exists) | Apache 2.0 | UMLS concept linking embeddings |
| Amazon Comprehend Medical, Azure Text Analytics for health, Google Healthcare NL API | English (limited Spanish) | Metered | ≈100× the cost of doing NER in-house at our volume (assessment §5.6) |

**Mexican brand names are not in RxNorm.** RxNorm covers US products; a Mexican prescription
naming a local brand needs ingredient-level matching plus a small curated MX brand map. This is a
data task, not a model task, and it is the single largest Spanish-specific gap in reconciliation.

### 2.4 Medical speech

| Option | Languages | Medical vocabulary | Cost | Fit |
| --- | --- | --- | --- | --- |
| **Deepgram Nova-3 Medical** (batch upgrade 2026-05) | Documented for English; Spanish availability not documented, verify with Deepgram | Median WER 3.45%, keyword error rate 6.79%, keyterm prompting up to 100 terms | $0.0043/min batch; owner has credits | English STT primary |
| Deepgram Nova-3 multilingual | 10-language code-switching incl. Spanish; 36+ monolingual | Keyterm prompting | $0.0092/min multilingual | Spanish STT primary until a Spanish medical model exists |
| Google MedASR (open, HAI-DEF) | English only | 4.6% WER radiology dictation | $0 | Not usable for `es-MX`; could serve English dictation locally |
| Gemini 3.5 Transcribe / Transcribe-Live | 85+ incl. Spanish; custom vocabulary biasing | Biasing only | $0.005 / $0.009 per min; free tier | Second hosted option under the GCP account |
| Parakeet TDT 0.6B v3, Whisper large-v3 | Spanish yes | Weak on drug names (24.6% entity CER measured for Parakeet) | $0 | Open fallback; expect drug-name errors |
| Aura-2 (Deepgram TTS) | Spanish voices incl. code-switching | — | $0.030 per 1k chars | Current TTS; set the Spanish voice by default |

### 2.5 Embeddings for retrieval

| Model | Medical | Multilingual | Licence | Note |
| --- | --- | --- | --- | --- |
| `gemini-embedding-001` (current) | General | 100+ languages | Google API | Supported to 2028-05-14; 768-d contract in place |
| MedCPT (NCBI) | Yes, PubMed search logs | English | Public domain | Best open medical retriever for English literature; not our DailyMed use |
| BioLORD-2023-M | Yes, UMLS-grounded | 7 languages incl. Spanish | Check model card | The one medical multilingual embedding worth testing for `es-MX` DailyMed retrieval |
| MedEmbed | Yes | English | Apache 2.0 | Fine-tuned general encoders |
| BGE-M3, Qwen3-Embedding, nomic-embed-v2 | General | Yes | MIT / Apache 2.0 | Zero-cost self-hosted alternatives |

MMed-Bench-IR (June 2026) finds no model that is both multilingual and biomedically grounded; for
a DailyMed corpus that is English label text queried in Spanish, a general multilingual embedding
with query translation, or BioLORD-2023-M, are the two candidates to measure.

### 2.6 Safety classifiers (second layer under the keyword floor)

| Model | Self-harm category | Multilingual | Licence | Note |
| --- | --- | --- | --- | --- |
| **Llama Guard 4 12B** | Yes (S11 suicide and self-harm) | Yes | Llama 4 licence | Lowest self-harm false-negative rate (21.8%) in the ICLR 2026 guard-model benchmark; still 1 in 5 misses, so a layer, not a floor |
| ShieldGemma / ShieldGemma 2 | No self-harm category | Limited | Gemma | Not useful for our floor |
| HaloGuard 1.0 (2026) | Yes | 23 languages incl. Spanish | Open weights | New; evaluate |
| OpenAI moderation endpoint | Yes (`self-harm`, `self-harm/intent`) | Yes | Free API | Zero cost, sends the message to OpenAI: synthetic only |

The spike showed the keyword floor misses inflected English ("ending my life") and anything
without a keyword (anaphylaxis, stroke signs). A classifier layer catches phrasing the keywords
miss; the LLM classification remains the third layer. None of the three may be the only one.

### 2.7 Benchmarks worth using

| Benchmark | What it measures | Use for us |
| --- | --- | --- |
| HealthBench (+ Professional, 2026) | 5,000 multilingual conversations, 48,562 physician rubric criteria | Rubric style for patient-communication scoring; Spanish conversations included |
| MedHELM v0.7 (37 benchmarks, 5 categories) | Clinical decision support, patient communication, note generation, research, admin | Model selection reference; per-scenario breakdown matters more than the mean |
| MedArena | Physician pairwise preference | Reference only |
| LiveMedBench (2026) | Contamination-free rubric evaluation | Reference for fresh cases |
| CareQA / CareQA-Vision (Aloe) | Spanish MIR/EIR-derived questions | The one Spanish medical knowledge set; sanity check for `es-MX` |
| PhysicianBench (2026) | Agents in EHR environments | Future, if we ever automate actions (we do not) |
| Our harness (`backend/scripts/run_ai_eval.py`) | Our prompts, our schemas, our thresholds, paired locales | The only one that measures MediAgent |

## 3. Use case by use case

| MediAgent workload | What kind of model it needs | Best paid | Best zero-cost | Spanish path | Decision |
| --- | --- | --- | --- | --- | --- |
| 1. Document extraction (text already anchored by OCR) | Structured extraction with evidence | `gemini-3.5-flash-lite` (measured 87%, 100% evidence); Claude Sonnet 5 on Vertex for page citations (unmeasured) | MedGemma 1.5 4B local; `gpt-oss-120b` on Groq for evaluation only | General model; Spanish NER (`bsc-bio-ehr-es-pharmaconer`) as a deterministic cross-check on medication mentions | Keep general; add the Spanish NER cross-check to the anchoring step |
| 2. FHIR import | None | — | — | — | No model |
| 3. Medication reconciliation | Deterministic engine + explanation | RxNorm + RxClass + openFDA labels (free); explanation `gemini-3.5-flash-lite` | Same engine | Ingredient matching plus a curated MX brand map; SNOMED Spanish for conditions | Build the engine; no medical LLM; decide the interaction data source (openFDA labels now, DrugBank if budget) |
| 4. Patient communication | Bilingual plain-language generation from approved facts | `gemini-3.5-flash-lite` (8/8 both locales) | Gemma 4 e4b local | Generate in locale; HealthBench-style rubric | Keep general |
| 5. Triage conversation | Classification + safety layers | Floor → Llama Guard 4 or HaloGuard → `gemini-3.5-flash-lite` | Floor → open classifier → Gemma 4 / `gpt-oss` | All layers bilingual; paired scenarios | Add the classifier layer; keep general LLM |
| 6. ADR and MedWatch | Extraction + deterministic Naranjo | `gemini-3.5-flash-lite` extraction (red flags 10/10); Naranjo in code | MedGemma 1.5 4B extraction | Spanish symptom NER (`HUMADEX/spanish_medical_ner` or bsc models) as cross-check | No LLM causality scoring: the 2026 systematic review finds LLM Naranjo outputs inconsistent |
| 7. SOAP drafting | Long-context clinical writing with citations | `gemini-3.1-pro-preview` today; measure `gemini-3.8-flash` and Claude Sonnet 5 | Baichuan-M2 32B or Gemma 4 31B on a GPU host | General | Measure before changing; medical fine-tunes offer no measured advantage here |
| 8. Voice | Medical STT, TTS | Nova-3 Medical (en), Nova-3 multilingual + keyterms (es), Aura-2 | MedASR (en only), Parakeet/Whisper (es, weaker), Kokoro/Piper TTS | Nova-3 multilingual is the only medical-adjacent Spanish option | Keep Deepgram; set `aura-2-javier-es`; verify Nova-3 Medical Spanish |
| 9. Retrieval | Embeddings for DailyMed | `gemini-embedding-001` | BGE-M3 / Qwen3-Embedding | Test BioLORD-2023-M and query translation | Keep; add task-type hints |

## 4. Decisions to take now

1. **Stop treating "medical model" as a routing goal.** Adopt the spike's per-workload pins; drop
   the 27B MedGemma endpoint; keep MedGemma 1.5 4B as the local extraction candidate only.
2. **Choose the interaction and class data source for the reconciliation engine.** Default:
   RxClass for duplicate therapy, openFDA label sections for interaction and allergy-class text,
   DailyMed already ingested; DrugBank only if a budget appears. The NLM interaction API is gone.
3. **Fund Spanish terminology work, not a Spanish model.** Curated Mexican brand-to-ingredient map,
   SNOMED Spanish edition access through UMLS registration, `bsc-bio-ehr-es-pharmaconer` as a
   deterministic cross-check in the anchoring step.
4. **Add a classifier layer to the triage floor** (Llama Guard 4 or HaloGuard, self-hosted or via a
   free tier for synthetic evaluation), measured with the paired scenarios, before any LLM change.
5. **Decide the evaluation credentials.** `gpt-oss-120b` on Groq's free tier gives a frontier-level
   open comparison at $0 for synthetic data; Claude on Vertex needs enabling in the GCP project;
   OpenAI needs an account. Without at least one, the document and SOAP workloads stay
   Google-only.
6. **Decide the self-hosted lane.** A 24 GB GPU host runs Baichuan-M2 (4-bit), Gemma 4 26B, or
   MedGemma 1.5 4B comfortably; without it, the zero-cost lane is 4B-class models on CPU and the
   free tiers for evaluation.
7. **Keep MedWatch and Naranjo deterministic.** Published evidence through March 2026 says LLM
   causality assessment is inconsistent; our own ADR results show severity under-calibration.
8. **Licence hygiene.** Record every model's licence in the registry the spike proposes; refuse
   research-only and non-commercial models outside evaluation runs; keep HAI-DEF obligations in
   the deployment docs if MedGemma ships anywhere.

## 5. What this does not settle

- No Spanish medical STT has a measured word error rate for our vocabulary; the voice workload
  needs its own paired evaluation before any provider change.
- BioLORD-2023-M, ClinLinker, and RigoBERTa Clinical licences must be read from their model cards
  before adoption; this document flags them as "check".
- Baichuan-M2's HealthBench score is self-reported; the Q2 2026 MedHELM leaderboard contains no
  open medical model at all. Independent numbers for open medical models on physician-rubric
  benchmarks do not exist yet.
- Nova-3 Medical's Spanish availability is undocumented; assume English until Deepgram confirms.

## Sources

- HealthBench leaderboard (2026-09-10): https://llm-stats.com/benchmarks/healthbench
- HealthBench Professional: https://arxiv.org/pdf/2604.27470
- MedHELM Q2 2026 leaderboard summary: https://pacific.ai/evaluating-frontier-llms-for-healthcare-with-medhelm-40-clinical-scenarios-and-a-new-q2-2026-leaderboard/
- MedHELM overview: https://huggingface.co/blog/leaderboard-medicalllm
- LiveMedBench: https://arxiv.org/html/2602.10367v1 · Medmarks: https://arxiv.org/html/2605.01417v1 · PhysicianBench: https://arxiv.org/html/2605.02240v1
- MedGemma 1.5 model card: https://developers.google.com/health-ai-developer-foundations/medgemma/model-card
- HAI-DEF terms: https://developers.google.com/health-ai-developer-foundations/terms
- MedGemma 1.5 and MedASR announcement: https://research.google/blog/next-generation-medical-image-interpretation-with-medgemma-15-and-medical-speech-to-text-with-medasr/
- Baichuan-M2-32B: https://huggingface.co/baichuan-inc/Baichuan-M2-32B
- II-Medical-8B: https://huggingface.co/Intelligent-Internet/II-Medical-8B
- HuatuoGPT-o1: https://huggingface.co/FreedomIntelligence/HuatuoGPT-o1-72B
- Lingshu: https://huggingface.co/lingshu-medical-mllm/Lingshu-32B
- Meditron-3: https://huggingface.co/OpenMeditron/Meditron3-70B
- OpenBioLLM: https://huggingface.co/aaditya/Llama3-OpenBioLLM-70B
- Med42-v2: https://huggingface.co/m42-health/Llama3-Med42-70B
- Aloe Beta: https://huggingface.co/HPAI-BSC/Llama3.1-Aloe-Beta-8B · Aloe recipe: https://pubmed.ncbi.nlm.nih.gov/42115745/ · Aloe-Vision and CareQA-Vision: https://arxiv.org/html/2606.27500
- Palmyra-Med: https://huggingface.co/Writer/Palmyra-Med-70B-32K · disabled NIM endpoint: https://docs.api.nvidia.com/nim/reference/disabled-writer-palmyra-med-70b-32k
- John Snow Labs Medical LLMs: https://nlp.johnsnowlabs.com/docs/en/LLMs/medical_llm
- Claude for Healthcare: https://www.fiercehealthcare.com/ai-and-machine-learning/jpm26-anthropic-launches-claude-healthcare-targeting-health-systems-payers
- ChatGPT for Healthcare and HealthBench: https://openai.com/index/improving-health-intelligence-in-chatgpt/
- Microsoft Dragon Copilot: https://www.microsoft.com/en-us/health-solutions/clinical-workflow/dragon-copilot
- NLM interaction API discontinuation: https://blog.drugbank.com/nih-discontinues-their-drug-interaction-api/ · migration guide: https://www.rxlabelguard.com/blog/nlm-rxnav-drug-interaction-api-discontinued-migration-guide
- openFDA drug label API: https://open.fda.gov/apis/drug/label/
- DDInter 2.0: https://academic.oup.com/nar/article/53/D1/D1356/7740584
- PlanTL Spanish biomedical models: https://github.com/PlanTL-GOB-ES/lm-biomedical-clinical-es · PharmaCoNER model: https://huggingface.co/PlanTL-GOB-ES/bsc-bio-ehr-es-pharmaconer
- ClinLinker: https://arxiv.org/abs/2404.06367 · https://huggingface.co/ICB-UMA/ClinLinker
- RigoBERTa Clinical and ClinText-SP: https://arxiv.org/pdf/2503.18594
- GLiNER-BioMed: https://academic.oup.com/bioinformatics/article/42/6/btag322/8690923
- MedCAT v2: https://aclanthology.org/2026.bionlp-1.17/
- Deepgram Nova-3 Medical: https://deepgram.com/learn/introducing-nova-3-medical-speech-to-text-api · languages overview: https://developers.deepgram.com/docs/models-languages-overview · code-switching: https://developers.deepgram.com/docs/multilingual-code-switching
- MedASR: https://huggingface.co/google/medasr
- Gemini 3.5 Transcribe: https://ai.google.dev/gemini-api/docs/models/gemini-3.5-transcribe
- MedCPT: https://huggingface.co/ncbi/MedCPT-Query-Encoder · BioLORD-2023-M: https://huggingface.co/FremyCompany/BioLORD-2023-M · MedEmbed: https://github.com/abhinand5/MedEmbed
- MMed-Bench-IR: https://arxiv.org/html/2606.24200
- Llama Guard 4: https://huggingface.co/meta-llama/Llama-Guard-4-12B · guard-model benchmark (ICLR 2026 workshop): https://arxiv.org/html/2605.28830v1 · HaloGuard 1.0: https://arxiv.org/pdf/2607.02079 · ShieldGemma: https://ai.google.dev/gemma/docs/shieldgemma/model_card
- LLMs in pharmacovigilance, systematic review (2026): https://pmc.ncbi.nlm.nih.gov/articles/PMC13465311/ · LLMs for ADEs, clinical perspective: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12347610/
