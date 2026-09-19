# Shared context for hosting research agents (MediAgent, 2026-09-10)

Product: supervised clinical decision support, synthetic data only today, may need BAA/HIPAA later.
Locales: en-US and es-MX. Backend: FastAPI on Google Cloud Run (1 vCPU, 512 MiB today), Supabase, Vertex AI works.
No GPU host exists. Gemini API key project is out of prepaid credit (free tier unusable). Deepgram credits exist.

Workloads and monthly volumes (scenario A = expo demo, B = one clinic, C = 10 clinics):
- Chat turns (classification ~400 in/60 out tokens + reply ~1500 in/250 out): A 3,000 / B 60,000 / C 600,000
- Documents to structure (~700 in / 700 out tokens per 1-2 pages; 5 pages avg): A 600 / B 3,000 / C 30,000
- Patient explanations (~600 in / 350 out): A 600 / B 15,000 / C 150,000
- SOAP notes (~3,000 in / 600 out): A 300 / B 1,500 / C 15,000
- Voice minutes: A 900 / B 9,000 / C 90,000
- Safety classifier calls (one per chat turn, ~500 in / 10 out): same as chat turns

Models of interest (open weights): gpt-oss-120b, gpt-oss-20b, Gemma 4 (e4b, 12b, 26b MoE, 31b), Qwen 3.6 (8B-32B), MedGemma 1.5 4B (HAI-DEF terms), Baichuan-M2 32B, Llama Guard 4 12B, Llama 4 Scout/Maverick; OCR: PaddleOCR PP-OCRv5, Nemotron-Parse 2.0, Nemotron OCR v1.
Baseline to beat on cost: Gemini 3.5 Flash-Lite on Vertex at $0.30 / $2.50 per 1M tokens (measured ~$0.0015 per chat turn, ~$0.002-0.005 per document); Gemini 3.1 Flash-Lite $0.125 / $0.75.
Google Cloud GPU reference: Cloud Run L4 ~$0.77/h all-in scale-to-zero; g2-standard-4 (1xL4) $0.71/h; a2-highgpu-1g (A100 40GB) $3.67/h; A100 80GB ~$5.03/h.

Required output for every provider: exact price (per 1M tokens in/out, or per GPU-hour, or per minute), free tier or credits, rate limits, cold start / scale-to-zero, SLA, data retention and training policy, HIPAA/BAA availability and on which plan, region/data residency, which of the models above are available, structured-output (JSON schema) support, endpoint lifecycle/retirement risk, and a computed monthly cost for scenarios A, B, C for the workloads that provider would serve. Mark every number with its source URL and the date seen. Say "not found" rather than guessing.
