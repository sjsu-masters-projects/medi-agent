# AI use cases: solution, quality evidence, and cost — one sheet

**Date:** 2026-09-10. **Status:** Decision sheet for the team; nothing below is committed or
wired. **Sources it consolidates:** the routing spike
([`ai-model-routing-spike-2026-09.md`](ai-model-routing-spike-2026-09.md), measured model
quality), the medical-model landscape
([`medical-models-landscape-2026-09.md`](medical-models-landscape-2026-09.md), what exists and
what is licensed), and the OCR and document-intelligence assessment
([`docs/document-intelligence-assessment.md`](../../docs/document-intelligence-assessment.md),
measured reading quality). Every number is on synthetic data and none is clinician-adjudicated.

## 1. How to read the quality numbers

The two benchmarks measure different steps of the same pipeline and must not be added up as
if they were one number.

| Step | What was measured | Best measured result | Where |
| --- | --- | --- | --- |
| Reading the file (text layer, OCR, page and box anchoring) | Does each ground-truth value exist in the recovered page text, on the right page? | 97.8% of required fields found on the correct page (PaddleOCR), 100% page-citation accuracy of found values, CER 0.00–0.02 on clean pages | Assessment §6, 23 synthetic cases |
| Structuring the text (the model) | Given correct text, does the model return the right medications, doses, frequencies, routes, allergies, and a verbatim evidence quote? | 87% required-field accuracy, 95% medication precision, 100% verifiable evidence excerpts (`gemini-3.5-flash-lite`, schema in prompt) | Spike §7, 10 documents |
| End to end (file → text → model → anchored candidate) | Not measured yet | Rough upper bound ≈ 85% if the two error sources are independent | Nobody |

The release gate is 90% required-field accuracy and 95% valid evidence links on adjudicated
cases. Reading is above both; structuring is above the evidence gate and below the accuracy
gate; end to end is unknown. The first joint action is therefore to run the 23-case corpus
through OCR, the model, and anchoring in one pass and score it with the spike's scorer.

## 2. Use case by use case

Costs use Vertex list prices and the measured token usage; monthly figures are for scenario A
(expo: 3,000 chat turns, 600 documents, 600 explanations, 300 SOAP notes, 900 voice minutes)
and scenario B (one clinic: 20× those volumes).

| # | Use case | Solution (deterministic layer → model → gate) | Quality evidence | Unit cost | Monthly A / B | What is still unmeasured or at risk |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Read an uploaded record | pypdfium2 text with boxes; PaddleOCR PP-OCRv5 (RapidOCR) for scans and photos; Tesseract OSD for orientation; page quality and route; then `gemini-3.5-flash-lite` on page-marked text with required evidence; anchoring verifies every value; candidate stays `pending_review` | Reading: 97.8% fields on correct page, 12/12 on fax and phone photo, Spanish scans CER ≤ 0.017, adversarial files rejected 7/7. Structuring: 87% fields, 95% precision, 100% evidence, undocumented doses left empty 4/4 | OCR ≈ $0 (CPU seconds); model ≈ $0.002 per 1–2 page document, ≈ $0.005 for 5 pages | ≈ $3 / $15 model, plus a warm 2 GiB Cloud Run instance during use | End-to-end number; real handwriting (no engine flags it); PaddleOCR confidence is flat so routing needs image-quality signals not yet built; golden lab and diagnostic labels need adjudication; Mexican brand names |
| 2 | Explain a record to the patient | Only clinician-approved facts, with their ids, in; `gemini-3.5-flash-lite` generates directly in `en-US` or `es-MX`; code appends safety wording and the care-team line; fallback `gemini-3.1-flash-lite`, then a template | 8/8 checks in both languages, no prescribing or diagnostic wording; today's default 87% (omits the care-team pointer) | ≈ $0.0009 | ≈ $0.5 / $14 | The approval gate does not exist yet, so today's summary is generated from unreviewed extraction; rubric-style (HealthBench-like) grading not yet adopted |
| 3 | Understand a chat message | Keyword floor (code) → self-harm and emergency classifier (Llama Guard 4 or HaloGuard) → `gemini-3.5-flash-lite` intent and urgency with schema; rule cascade fallback | 28/28 urgency and intent, zero under-triage, all 8 emergencies escalated in both languages including 4 with no keyword; p50 0.8 s | ≈ $0.0003 | ≈ $1 / $18 | Floor is bypassed on the websocket path (P0); floor misses inflected phrasing; classifier layer unmeasured on our data (published self-harm false-negative rate 21.8% for Llama Guard 4) |
| 4 | Answer in the chat | `gemini-3.5-flash-lite` streamed, grounded with retrieved DailyMed chunks, citation ids verified, safety wording appended by code; fallback `gemini-3.1-flash-lite`, then localized templates | Not measured directly; the explanation workload (same prompt family) passed 8/8 | ≈ $0.0011 per reply | ≈ $3.5 / $70 | Needs a reply-quality workload with grounding checks; L3 fallback is English-only |
| 5 | Symptom message → structured report | `gemini-3.5-flash-lite` extracts symptom, onset, suspect medication, red flag; severity from a structured question, not the model; symptom report persisted for the clinician | 87% field checks, red flags 10/10, no invented suspect medication on the non-ADR cases; every model under-rated severity | ≈ $0.0005 | ≈ $0.15 / $1.5 | Severity capture UI does not exist; Spanish symptom NER cross-check not wired |
| 6 | SOAP note draft | Router-authorized; `gemini-3.1-pro-preview` today with row-id citations and a draft state the clinician signs; measure `gemini-3.8-flash` (thinking budget set) and Claude Sonnet 5 on Vertex before switching | Not measured (no SOAP workload yet). Pro was the most accurate model on the hardest measured task (discrepancies 100%) and 5–19 s at p50 is acceptable for an on-demand draft | ≈ $0.013 per note (Pro), ≈ $0.005 (Flash) | ≈ $4 / $20 | Persisted with no `review_state` today; no citations; Pro is a preview model with no GA successor listed |
| 7 | Voice | Deepgram Nova-3 Medical (English STT), Nova-3 multilingual with keyterm prompting (Spanish STT), Aura-2 with `aura-2-javier-es` for Spanish; text-only path always available | Published only: Nova-3 Medical median WER 3.45%, keyword error 6.79% (English); no Spanish medical WER exists; open alternatives measured weak on drug names (24.6% entity CER) | ≈ $0.0043–0.0092 per minute STT + ≈ $0.006 per spoken reply | ≈ $18 / $180 (credits cover A) | Our vocabulary unmeasured in either language; live streaming disabled; transcripts not persisted; no consent flag; Spanish voice unset by default |
| 8 | Find the right label text | `gemini-embedding-001` with task-type hints over DailyMed chunks in pgvector; deterministic citation ids; verify emitted `[n]` exist | Live in production; not benchmarked | ≈ $0.00002 per query | negligible | Spanish queries against English labels untested (BioLORD-2023-M and query translation are the candidates); corpus unfiltered when a patient has no medications; ingest unscheduled |
| 9 | Medication reconciliation (to build) | RxNorm brand→ingredient, RxClass classes for duplicate therapy, parsed dose and frequency, status fields, openFDA label sections for interactions and allergy classes, curated Mexican brand map; abstain when a dose is unparseable; `gemini-3.5-flash-lite` only to explain a flagged item | Model-alone baseline: Pro 100% precision and recall with correct abstention; Flash-Lite 93% precision, 79–82% recall, five false discrepancies on the brand/generic control; every model caught the allergy conflict; none recommended a therapy change | Engine ≈ $0 (free NLM and FDA APIs); explanation ≈ $0.0005 | ≈ $0.15 / $1.5 | No engine exists; the NLM interaction API is gone and DrugBank's free checker retired 2026-03; DDInter licence for redistribution unclear |
| 10 | ADR score and MedWatch draft (to build) | Naranjo from ten structured answers in code; MedWatch field mapping in code; `gemini-3.5-flash-lite` extracts candidates; the SOAP model drafts the narrative; `status = draft` only, no submission path | Extraction as row 5; published evidence (systematic review to March 2026) says model causality scoring is inconsistent | ≈ $0.0005 extraction + ≈ $0.01 narrative | ≈ $3 / $30 at 300 / 3,000 drafts | Tables exist, no producer; no review endpoint |
| 11 | FHIR and SMART import | Deterministic mapping, provenance, binding, field-level audited decision | Existing tests; no model in the path | $0 | $0 | None for AI |

**Totals:** scenario A ≈ $35 a month for all model and voice usage plus Cloud Run; scenario B
≈ $350 a month plus Cloud Run. Cheaper managed lanes exist but are unmeasured on our workloads:
`gpt-oss-120b` on Bedrock (≈ $40 a month for the text workloads at B, AWS BAA) and `gpt-5-nano`
on Azure (≈ $19); see the hosting document for the full comparison, break-even, and compliance
matrix. A single always-on L4 GPU (≈ $560 a month) would cost more
than scenario B's entire model bill and would host a model that scored no higher; the
self-hosted lane is for data locality and evaluation, run scale-to-zero at ≈ $50 a month.

## 3. Assessment of the document-intelligence document

**Agree, and it should be adopted:**

- Deterministic reading first, model only to structure page-marked text, anchoring as the
  proof of evidence, clinician as the reviewer. This is the same conclusion the routing spike
  reached from the model side, so the two workstreams are consistent by construction.
- The stack: pypdfium2 (replaces AGPL PyMuPDF), pdfplumber for ruled tables, PaddleOCR via
  RapidOCR for scans and photos, Tesseract for orientation, react-pdf or EmbedPDF for the
  citation overlay, Document AI as insurance, everything else optional.
- The benchmark is honest: it measures calibration, adversarial rejection, page-citation
  accuracy, and states its own limits (one font, script-font "handwriting", no adjudication).
- The licence findings are material and correct in substance: PyMuPDF is AGPL or paid, and
  Syncfusion is free only within Community License limits.
- In-container CPU OCR as the primary path, with hosted trial endpoints kept out of the
  fallback chain, is the right call after one NVIDIA endpoint returned 410 during the work.

**Corrections and additions before the team relies on it:**

1. Its headline "97–98% of required fields" is the reading step, not extraction. The model
   structuring step measured 87% on clean text. Quote both, and run end to end before
   claiming anything against the 90% gate.
2. "Gemini Flash" is not a pin. Name `gemini-3.5-flash-lite`, schema in the prompt, evidence
   required and non-nullable in the schema; the spike found native JSON-schema mode made
   the model omit evidence when the schema allowed null.
3. "258 tokens per PDF page" is the price of sending a page image; page-marked text is
   billed by its length (typically 500–800 tokens a page). The cost conclusion holds either
   way.
4. PaddleOCR's flat confidence means the two extra deterministic signals it proposes
   (image quality, anchoring failure rate) are prerequisites, not follow-ups; without them the
   `review_with_caution` route rarely fires on bad scans.
5. Add the Spanish medication NER model (`bsc-bio-ehr-es-pharmaconer`, Apache 2.0) as a
   deterministic cross-check in the anchoring step; it costs nothing and covers the
   Spanish-specific failure modes the corpus cannot.
6. Compute the duplicate-file hash server-side from the stored bytes; today it is
   client-supplied.
7. The Nemotron-Parse "second opinion" button is a demo feature that sends pages to a
   logged, non-BAA trial endpoint. Keep it behind a flag labelled synthetic-only, or drop it;
   it is not on the path to any gate.
8. Two evaluators now exist for documents: its recorded-extraction scorer
   (`scripts/evaluate_document_extraction.py`) and the spike's workload scorer
   (`scripts/run_ai_eval.py`). Merge them into one end-to-end run over its corpus.
9. Process: the workstream has no `.agent/TASKS.md` entry, 3 of its 57 tests fail, and its
   week-2 plan depends on the third session's uncommitted ingestion rewrite landing first.
   Add the tracker entry and fix the tests before any wiring PR.

## 4. Decisions ready to take

| Decision | Recommended default | Why now |
| --- | --- | --- |
| Model pins | `gemini-3.5-flash-lite` for rows 1–5 and 9–10, `gemini-3.1-flash-lite` fallback, Pro only for row 6 until measured | Measured, GA, cheapest current generation |
| Document stack | Adopt assessment §8 with the corrections above | Measured reading quality, $0 licence, removes AGPL |
| Hosting | Vertex for serving; Cloud Run CPU for OCR (2 GiB, CPU always allocated); one Cloud Run L4 scale-to-zero (≈ $46/month) for the classifier, local extraction, and evaluations; measure `gpt-oss-120b` on Bedrock and `gpt-5-nano` on Azure before any switch; NVIDIA hosted catalogue for synthetic evaluation only | [`inference-hosting-options-2026-09.md`](inference-hosting-options-2026-09.md): managed APIs are 5–100× cheaper than owned GPUs below ten-clinic scale; only scale-to-zero breaks even at one clinic |
| Safety | Ship the websocket floor fix and the keyword gap fix (SAFE-002) before any re-routing; add the classifier layer next | P0 |
| Reconciliation | Build the deterministic engine; pick openFDA + RxClass as the data source | No engine exists; model-only fails brand/generic |
| Evaluation | One end-to-end document run; grow to 120 scenarios; 40 adjudicated high-risk cases; add SOAP, chat-reply, and voice workloads | Every gate depends on it |
| Credentials | Groq free tier for `gpt-oss-120b`; build.nvidia.com trial or DeepInfra for Llama Guard 4 (Groq does not serve it); all synthetic only; enable Claude on Vertex if the team wants page-citation PDF reading measured | Cheapest way to widen the comparison |
