# MediAgent — OCR and document-intelligence assessment

**Date:** 2026-09-10 · **Author:** engineering assessment for the December expo · **Status:** decision proposal, nothing wired into production · **Data:** synthetic only

This is the single reference for the OCR / document-intelligence workstream: what the
product needs, what the code does today, which tools were evaluated (with licences,
prices and measured quality), how the proposed pipeline works step by step, what it
costs, what the risks are, and how to roll it out before the expo. It consolidates and
replaces the earlier draft notes.

**Read this first if you have two minutes**

- The app cannot read scanned or photographed documents today. Images typed as lab
  reports are opened with the PDF parser, scanned PDFs return empty text, and the Cloud
  Run image has no OCR binary at all. An in-flight rewrite stops such uploads at a
  `needs_ocr` status "until a reviewed OCR capability exists". This document is that
  capability.
- Recommended architecture: deterministic reading first (embedded text or OCR with
  per-word coordinates), an LLM only to structure the text, a deterministic anchoring
  step that ties every extracted value back to a page, box and quote, and a clinician
  who approves. Never a language or vision model as the sole evidence source.
- Recommended stack for the expo, $0 licence, all local: **pypdfium2** for PDFs,
  **pdfplumber** for ruled tables, **PaddleOCR PP-OCRv5 through RapidOCR** for scans and
  photos, **Tesseract** kept only as a 200 ms orientation detector, **Gemini Flash on
  Vertex** for structuring, a **pdf.js / EmbedPDF** viewer with highlight boxes, and an
  optional hosted **Nemotron-Parse** "second opinion" button for the demo.
- Measured on a 23-case synthetic corpus: the local stack recovers 97–98% of required
  fields on the correct page with 100% page-citation accuracy for anchored values;
  PaddleOCR reads faxes and phone photos 12/12 where Tesseract reads 9/12 and 10/12.
- Two licence findings: PyMuPDF (in the lockfile) is AGPL-3.0 and conflicts with a
  proprietary product; Syncfusion's viewer is free only under its Community License
  terms. Both have free, Apache-licensed replacements.

---

## 1. Product context and use cases

MediAgent is supervised clinical decision support for outpatient chronic-care and
polypharmacy patients (diabetes, hypertension, hyperlipidaemia), bilingual in American
English and Mexican Spanish, deployed on Supabase, FastAPI on Cloud Run, and Next.js on
Vercel. The demonstrated loop is: import a record with provenance → reconcile
medications and surface a discrepancy → collect symptoms and adherence → route an
evidence-backed candidate action to a clinician → execute the approved follow-up →
retain it in the patient's timeline.

Document intelligence sits at the first step. The concrete use cases:

| Use case | Who | What arrives | What must come out |
| --- | --- | --- | --- |
| Outside records upload | Patient (records page) and clinician (patient upload page) | PDF, JPEG, PNG, WebP, TIFF into the private `documents` bucket; types lab report, discharge summary, prescription, diagnostic report, referral, insurance, other | Medications, conditions, allergies, follow-up obligations, lab observations, dates, each as a **pending** clinical-fact candidate with a page, region and quote |
| Medication reconciliation | Medication Safety worker, clinician | Document-extracted medications alongside patient-reported, clinician-entered and imported FHIR medications | Duplicate therapy, dose changes, missing medications, allergy conflicts, never fabricated values |
| Clinician review | Assigned clinician in the external-records workspace | Candidate list with confidence band, uncertainty notes and a "Source" view | Approve / correct / reject with an audit trail; only reconciliation writes canonical tables |
| Patient explanation | Patient, en-US or es-MX | Readable document text | Plain-language explanation (today generated from unreviewed extraction, see risks) |
| Viewing the file | Patient and clinician ("eye icon") | The original PDF or image | Rendered pages with the citation box drawn where a value was read |

What arrives in practice is mostly born-digital e-discharge summaries and e-prescriptions
(exact text, zero OCR error), plus the hard cases that justify OCR at all: scanned or
faxed pages from other clinics, phone photos of prescriptions, pharmacy labels, lab
printouts with tables, and Spanish documents with decimal commas (`0,1 mg`) and
abbreviations (`c/12 h`, `VO`, `PRN`).

Release gates from the plan that depend on this workstream: required-field extraction
accuracy ≥ 90 %, evidence-to-source link validity ≥ 95 %, no material English/Spanish
safety disparity, and nothing extracted may update canonical clinical data
automatically.

## 2. What the code does today (verified on `main` at a2b331e, plus in-flight changes)

| Area | Finding | Consequence |
| --- | --- | --- |
| `backend/src/app/agents/ingestion/graph.py`, `receive_document` | Any upload whose `document_type` is lab report, discharge summary, prescription or diagnostic report is opened with the PDF parser regardless of MIME type; images typed that way fail. Scanned PDFs return an empty text layer and are still sent to the model. | Wrong-parser failures; model extraction from nothing. |
| OCR | One `pytesseract.image_to_string` call for image uploads: no page classification, no confidence, no coordinates, no rotation or resolution handling, English only. | Cannot satisfy any of the required behaviours in section 4. |
| Citations | `IngestionService._register_candidates` writes `document_location={"scope":"document","index":i}` and an excerpt the code composes itself. | No page, region or quote; the ≥ 95 % evidence-link gate is unreachable. |
| Deployment | `backend/Dockerfile` is `python:3.12-slim` + pip: no Tesseract binary or language data. Cloud Run runs with `--cpu 1 --memory 512Mi --min-instances 0`, request-scoped CPU, and ingestion runs in FastAPI `BackgroundTasks` after the response is sent. | Image OCR fails in staging; background OCR is CPU-throttled and memory-tight. |
| Locales | Local Tesseract has `eng` only; no Spanish data anywhere. | Spanish OCR impossible today. |
| Schema | `source_provenances.document_location` and `evidence_citations.location` are `jsonb`; `clinical_facts` has `confidence_score` / `confidence_band` / `uncertainty`; `document_ingestion_runs` has `extractor_version` and `source_hash`. | No migration needed for page/region/quote citations or versioned runs. |
| Retention | `DocumentService.delete_document` removes the storage object when no candidate was applied. | Conflicts with "preserve source files and extraction versions permanently". |
| Viewer | Patient portal renders PDFs with Syncfusion `ej2-react-pdfviewer`; images are not rendered inline; the clinician portal has no viewer at all. | The "eye icon" and citation overlay do not exist for clinicians. |
| Licences | PyMuPDF (MuPDF) is AGPL-3.0 or a paid Artifex licence; the README says "Proprietary, all rights reserved". Syncfusion is free only under its Community License (< $1 M revenue, ≤ 5 developers, ≤ 10 employees, < $3 M outside capital). | Removing the README line does not remove the AGPL obligation; swap the library or open-source the backend. |
| In-flight rewrite (third session, uncommitted) | Candidate-only ingestion graph; images and text-less PDFs stop at `needs_ocr`; model-cited `{page, excerpt, confidence}` must match page text verbatim; migration 034 adds a claim RPC, `parse_failure_code`, and a clinician retry endpoint. | This assessment plugs into that `needs_ocr` branch. Note: `ClinicalFactCreate(confidence=…)` in that rewrite uses a field that does not exist, so the score is silently dropped. |
| Model availability (from the AI routing spike) | The Vertex MedGemma 27B endpoint does not resolve and the Gemini API key's project is out of credit. | Model extraction currently runs on fallbacks; the deterministic layer is unaffected. |

## 3. Required behaviours and how the design meets them

| Requirement | Mechanism | Evidence |
| --- | --- | --- |
| Classify each page/document as born-digital, scanned, mixed, unreadable, encrypted or unsupported | Magic-byte container sniffing; per-page signals (text characters, text-layer sanity, image coverage, rendered ink ratio); document class derived from page classes; encrypted via `needs_pass`; repaired/truncated PDFs flagged. | 23/23 cases classified correctly, including an invisible garbage text layer over a scan, a truncated PDF that the parser silently repairs, and blank and scanner-noise pages. |
| OCR only when needed; never an LLM as primary OCR | OCR runs only for scanned pages, image regions of mixed pages, and raster uploads. No model is called anywhere in the deterministic layer. | Born-digital pages: 6–55 ms, zero OCR calls. |
| Preserve page number, source excerpt and coordinates | Every word carries a bounding box in PDF points (or pixels for rasters), a line id and the method; anchors return page, box union, quote line and matched text. | 100 % of anchored fields cited the correct page across all engines. |
| Measure confidence; route low confidence to review; never invent values | Per-word engine confidence, character-weighted page confidence, page quality (usable / low / unusable), document route; a value not found on any page scores 0 and is flagged, never filled in. | Tesseract words ≥ 0.90 are 99.3 % correct, < 0.50 are 50 %; the fax page (0.71) routed to review. |
| Preserve source files and extraction versions permanently | `DocumentExtraction` is a versioned JSON artifact (extractor and engine versions, source SHA-256, per-page words); retention policy in section 9. | Policy decision needed on deletion. |
| English and Spanish; abbreviations, tables, dosages, dates, units, labels | Latin-script OCR models; accent- and decimal-comma-aware anchoring (`0,1 mg` ↔ `0.1 mg`, `500mg` ↔ `500 mg`, `µg` ↔ `ug`, `q.d.` ↔ `qd`); ruled-table extraction; corpus cases for each item. | Spanish scans CER 0.000–0.017; abbreviation page 11/11 fields; lab table 35/35 cells. |
| Rotation, low resolution, fax, handwriting, multi-column, blank pages | Orientation detection verified against an unrotated pass plus a confidence-driven search; ≥ 2× upscaling below 1000 px; column-band reading order; ink-ratio blank detection; handwriting routed by confidence or a second reader. | Rotated Spanish lab page corrected, 7/7 fields; 72 dpi list 6/6; two-column page CER 0.000. |
| Every fact links to page/region/quote | `ground_item()` emits `{page, excerpt, confidence}` in the shape the ingestion rewrite validates, plus a location payload with the box for `evidence_citations.location`. | Format in section 9.6. |
| No automatic canonical update | Candidates go only through `ClinicalFactService.create_candidate` (always `pending_review`); reconciliation remains the sole canonical write path. | Existing INT-001 / REC-002 boundary, unchanged. |

## 4. Architecture decision: why deterministic-first, and where models belong

### 4.1 The shape of the pipeline

```
upload (PDF / image) in private bucket
   │
   ▼
[1] classify container and every page  ── encrypted / unreadable / unsupported / blank → REJECTED (permanent reason)
   │
   ├─ born-digital page ──► [2a] embedded words + boxes (pypdfium2), ruled tables (pdfplumber)
   ├─ scanned page / raster ► [2b] render 300 dpi grayscale → upscale if small → orientation check → OCR (words, boxes, confidence)
   └─ mixed page ──────────► [2a] for the text + [2b] on each embedded image region ≥ 2 % of the page
   │
   ▼
[3] page quality (usable / low / unusable) and document route
   │      automated_candidates · review_with_caution · clinician_only · rejected
   ▼
[4] LLM structuring (Gemini Flash on Vertex) over page-marked TEXT of usable/low pages only
   │      → medications / conditions / allergies / obligations as JSON, each with {page, excerpt, confidence}
   ▼
[5] deterministic anchoring: every value must be found in the page words → page, bbox, quote, similarity, word confidence
   │      not found → confidence 0, uncertainty note, low band (never filled in)
   ▼
[6] pending clinical-fact candidates with citations (ClinicalFactService.create_candidate)
   │
   ▼
[7] clinician review in the external-records workspace; "Source" opens the page with the box drawn
   │
   ▼
[8] reconciliation (existing, transactional, audited) is the ONLY path into medications / conditions / allergies
```

Optional [4b]: for pages the deterministic layer flagged (low quality, unanchored values,
handwriting), send the page image to a vision model as a **second reader**; agreement
with OCR raises confidence, disagreement is shown to the clinician with both readings.

### 4.2 Why not point an LLM or vision model at the file and skip OCR

- **They invent text where the page is unreadable.** The KIE-HVQA benchmark (2025),
  built from degraded identity cards, invoices and prescriptions, shows current
  multimodal models "fail to adequately perceive visual degradation" and fall back on
  language priors, producing plausible but false text. For a dose on a faxed
  prescription that is the worst failure mode; our fax case is exactly where Tesseract's
  confidence dropped to 0.71 and routed the page to review.
- **No calibrated per-word confidence.** Generative models give a self-reported score at
  best, and the hallucination literature shows it is not trustworthy under degradation.
  Without calibrated confidence there is nothing to route on. Nemotron-Parse, the most
  accurate reader we measured, reports no confidence at all.
- **Provenance is a release gate.** The plan requires ≥ 95 % valid evidence-to-source
  links. Gemini 2.5 returns boxes (IoU ≈ 84 on a document task) and Qwen3-VL grounds text
  on a 0–999 grid: good enough to point at a region, not to prove a word was read.
  Deterministic OCR gives exact word boxes for free.
- **Determinism and versioning.** OCR output is reproducible and pinnable; model output
  drifts across versions and temperatures, which weakens regression fixtures and audit
  history.
- **Cost and hosting.** Gemini on Vertex is cheap per page (258 tokens per PDF page,
  roughly $1–2 per 1,000 pages) and BAA-eligible. Claude charges 1,500–3,000 tokens per
  page; OpenAI similar, with BAAs only on specific API tiers. Open-weight vision OCR
  models (GLM-OCR 94.6, PaddleOCR-VL-1.5 94.5, DeepSeek-OCR v2 87.7 on OmniDocBench;
  Nemotron-Parse 2.0; Qwen3-VL) need a GPU: about $0.70 per L4-hour on Google Cloud,
  which fights scale-to-zero. Hosted NVIDIA NIM trial endpoints and Hugging Face
  serverless carry no BAA and can be retired (one did during this work).

Where the LLM earns its place is structuring: GPT-4 reached > 90 % exact match on
medication snippets from the n2c2 dataset, and a 2026 hybrid rules-plus-LLM system hit
F1 0.91 on deprescribing recommendations in discharge summaries. On post-discharge
action extraction the best models score F1 ≈ 0.55, which is why the clinician stays in
the loop.

### 4.3 Scenario by scenario

| Document class | Best reader | Role of LLM / vision model | Why |
| --- | --- | --- | --- |
| Born-digital PDF (e-discharge, e-Rx) | Embedded text with boxes | LLM structures the text; no image pass | CER 0.000 measured; images add cost and risk, nothing else |
| Clean scan, fax at 300 dpi | Local OCR (PaddleOCR or Tesseract) | LLM structures; anchoring verifies | CER 0.00–0.02, cheap, auditable |
| Degraded scan, phone photo, pharmacy label | PaddleOCR PP-OCRv5 (reads them), Tesseract only as a fallback | Optional vision second reader on flagged pages | PaddleOCR 12/12 on fax and photo vs Tesseract 9/12 and 10/12 |
| Handwriting | Vision model or managed OCR as reader | Always clinician-verified against the image | Traditional OCR 50–70 % on prescriptions, AI OCR 82–95 %, hallucination risk highest |
| Ruled tables (labs) | pdfplumber on born-digital; layout model or Document AI Layout on scans | LLM maps rows to observations | Structure tools beat plain OCR and free-form model output |
| Multi-column, rotated, low-res, blank, encrypted | Deterministic classifier | None | Cheap, deterministic, measured |
| Demo / prototype speed | LLM-only is fine | Everything | Fails the evidence and calibration gates for a release |

### 4.4 What "AI review" should mean

The reviewer is the clinician. The LLM's job is structuring text into candidates and
normalising names, doses and frequencies for RxNorm; the deterministic layer verifies
its output against the page; a vision model, if used at all, is a second reader on
flagged pages whose output must also anchor to the page text. Confidence for a vision
reading comes from agreement with OCR and self-consistency across passes, never from
the model's own claim.

## 5. Tool landscape (licence, price, quality)

Prices are list prices found on 2026-09-10; verify before purchase. "Measured" means
run on our synthetic corpus in this workstream.

### 5.1 Viewing documents (the "eye icon" and the citation overlay)

| Option | Licence / price | Fit | Verdict |
| --- | --- | --- | --- |
| Browser-native `<iframe>` / `<object>` for PDF, `<img>` for images | Free | No control inside the PDF frame, so no highlight overlay | Fine for a plain viewer only |
| react-pdf (Mozilla pdf.js) | Apache-2.0, free | Canvas render at any scale; draw boxes from page-relative coordinates; highlight libraries exist (react-pdf-highlighter-extended, MIT) | **Recommended** for the overlay |
| EmbedPDF | Apache-2.0, free | PDFium compiled to WebAssembly (same engine as pypdfium2, so coordinates line up), built-in highlight / ink annotations, React bindings | Strong alternative; newer project |
| Syncfusion PDF Viewer (installed in the patient portal) | Free only under Community License: < $1 M revenue, ≤ 5 developers, ≤ 10 employees, < $3 M outside capital; otherwise per-developer subscription | Mature; annotation API can draw rectangles; heavy bundle | Keep while eligible, or replace with react-pdf |
| Adobe PDF Embed API | Free with Adobe credentials | Adobe viewer in-page | Adds a third-party client on PHI-bearing pages; not needed |
| Nutrient (PSPDFKit) | 30-day trial only, watermark; annual component licences, self-hosted entry ≈ $25k–$40k/yr | Excellent editor; OCR is a server add-on | Not justified |
| Apryse WebViewer | Entry packages from ≈ $1,500, quoted | Excellent editor | Not justified |
| Images: `<img>` + zoom/pan (react-zoom-pan-pinch, MIT) + absolutely positioned boxes | Free | OCR emits pixel coordinates for rasters, so the overlay is trivial | **Recommended** |

### 5.2 PDF parsing and rendering (backend)

| Option | Licence / price | Quality evidence | Verdict |
| --- | --- | --- | --- |
| PyMuPDF (MuPDF), currently in use | AGPL-3.0, or commercial from Artifex (≈ $10k–$50k/yr reported) | Fast; ruled-table finder; measured CER 0.000 on born-digital pages | Licence conflict for a proprietary product; replace |
| **pypdfium2** (Google PDFium) | Apache-2.0 / BSD-3, free | **Measured**: CER 0.000 on every born-digital case, correct two-column reading order without extra code, char boxes → word boxes, image objects with bounds, 25–100 ms per page grayscale render at 300 dpi, OCR on its renders matched PyMuPDF's numbers, and it rejects encrypted / corrupt / truncated files with typed errors instead of silently repairing them | **Recommended replacement** |
| pdfplumber (pdfminer.six) | MIT, free | Rated the most accurate open-source coordinate tool on digital PDFs with ruled lines (arXiv 2410.09871); slower than PDFium | Ruled tables on born-digital pages |
| Camelot / tabula-py | MIT | Good on lattice tables; extra runtime deps | Not needed |
| Poppler / pdf2image, Ghostscript | GPL / AGPL binaries | Fine as external processes but adds copyleft binaries | Avoid; pypdfium2 covers rendering |

### 5.3 OCR engines, open source (run in our container or a worker)

| Option | Licence, size, speed (CPU) | Quality evidence | Handwriting | Verdict |
| --- | --- | --- | --- | --- |
| Tesseract 5.5 (+ `spa` pack) | Apache-2.0; ≈ 10 MB; 0.4–1 s/page | **Measured**: 96.9 % fields on correct page, CER 0.020 overall, 0.174 on the fax; best-calibrated confidence (≥ 0.90 → 99.3 % correct, < 0.50 → 50 %); orientation detection built in | None (routes to review) | Keep as orientation detector and fallback |
| **PaddleOCR PP-OCRv5 via RapidOCR (ONNX Runtime)** | Apache-2.0; server detector ≈ 100 MB, mobile Latin recogniser ≈ 8 MB; 2–4 s/page with the server detector | **Measured**: 97.8 % fields, 12/12 on fax and phone photo, 6/6 on the 72 dpi list, Spanish 11/11; confidence flat (99.6 % of words ≥ 0.90 regardless of quality); drops an occasional very long line; mobile detector needs 200 dpi input or it drops long lines | Some | **Recommended reader for scans and photos** |
| OCRmyPDF (wraps Tesseract) | MPL-2.0; needs Ghostscript (AGPL) as an external process | Deskew, auto-rotate, clean, writes a searchable PDF text layer | None | Optional packaging only |
| EasyOCR | Apache-2.0; ≈ 500 MB models; ≈ 8 pages/min CPU | 7–10 points more accurate than Tesseract on non-clean documents; better with accents | Some | Too heavy for 512 MiB; worker only |
| docTR / OnnxTR | Apache-2.0; backbone-dependent | CER 0.197 ties Surya on a hard printed-text set | Limited | Alternative to PaddleOCR |
| Docling (IBM) | MIT (Granite-Docling 258M is Apache-2.0); CPU-capable | Layout, reading order, TableFormer table structure over scans; pluggable OCR | Via backend | Best open-source answer for scanned tables and forms, later |
| TrOCR (Microsoft) | MIT | Fine-tuned CER 1.4 % on a handwritten-prescription dataset (IEEE 2025) but needs labelled lines and a line detector | Yes | Research option, not near-term |
| Surya / Marker (Datalab) | Code Apache / GPL; weights non-commercial above $5 M revenue or funding, plus a non-compete | Strong layout/OCR | Some | Excluded for a product |
| Vision-model OCR (PaddleOCR-VL-1.5 94.5, GLM-OCR 94.6, DeepSeek-OCR v2 87.7 on OmniDocBench; olmOCR, dots.ocr, MinerU) | Mostly Apache / MIT (MinerU AGPL); need a GPU | Best document parsing scores today | Good | Second reader on a GPU worker later; no calibrated per-word confidence |

### 5.4 NVIDIA models (build.nvidia.com), measured through the trial key

| Model | What it is | Terms | Measured (section 6) | Verdict |
| --- | --- | --- | --- | --- |
| `baidu/paddleocr` NIM | PaddleOCR detection + recognition packaged as a NIM; text lines with boxes and confidence | Hosted trial: logged, no personal data, no BAA; self-hosted NIM free for development under the Developer Program (≤ 16 GPUs), production needs NVIDIA AI Enterprise ($4,500 per GPU per year) or $1 per GPU-hour via a cloud marketplace | 98.7 % fields, CER 0.028, but the hosted payload cap forced a 0.33× downscale of the fax page and dropped accents; confidence poorly calibrated (≥ 0.90 band only 94 % correct) | Run the same model locally with RapidOCR instead |
| `nvidia/nemotron-ocr-v1` | NVIDIA's own OCR (detector + recogniser + relational model); replaces `nemoretriever-ocr-v1`, which answered **410 Gone, end of life 2026-05-18** during this work | Hosted trial; weights on Hugging Face, GPU to self-host | 98.2 % fields, **best CER 0.013**, well-calibrated confidence (≥ 0.90 → 99.5 %, 0.75–0.90 → 90 %), Spanish accents kept | Excellent, but hosted-only for us; endpoint lifecycle risk |
| `nvidia/nemotron-parse` (2.0) | Document parser: returns text elements with semantic class (Title, Section-header, Text, Table) and boxes via a `markdown_bbox` tool call; image only, no text prompt, no confidence | Hosted trial; 0.9 B open weights, GPU to self-host | **100 % fields, CER 0.014, WER 0.021**; perfect on fax, photo, low-res and the script-font handwriting | Best reader measured; use as the demo "second opinion", never as the evidence layer |
| `nvidia/nemotron-nano-12b-v2-vl`, `meta/llama-3.2-90b-vision-instruct`, `google/gemma-3-12b-it`, `microsoft/phi-3-vision` | General vision-language models on the hosted catalogue | Hosted trial, per-token | Not measured: same category as Gemini page-image reading (section 4.2) | Only as second readers |
| NVIDIA AI Enterprise / self-hosted NIM | Containers with TensorRT acceleration | $4,500 per GPU per year for production | n/a | Not needed at expo volume |

### 5.5 Managed OCR / document AI (per-page metered)

| Option | Price (list) | Quality / fit | PHI posture | Verdict |
| --- | --- | --- | --- | --- |
| Google Document AI, Enterprise Document OCR | $1.50 per 1,000 pages (≤ 5 M/mo) | Per-token confidence and boxes, handwriting, 200+ languages | HIPAA-eligible under Google's BAA; same project as Cloud Run | Stable managed option; not needed before the expo |
| Google Document AI Layout Parser / Form Parser | $10 / $30 per 1,000 pages | Tables, reading order, key-value forms | Same | Only if scanned tables/forms need it |
| Google Cloud Vision, `DOCUMENT_TEXT_DETECTION` | $1.50 per 1,000 (first 1,000/month free) | Dense-text OCR with boxes and confidence; no layout | Same | Cheaper trial of the same family |
| AWS Textract | $1.50 text; $15 tables; $50 forms per 1,000 pages | Strong forms/tables | HIPAA-eligible; second cloud | Not for us |
| Azure AI Document Intelligence | $1.50 read; $10 layout; $10 prebuilt per 1,000 pages | Strong prebuilt/layout | BAA via Microsoft; second cloud | Not for us |
| Mistral OCR 3 | $2 per 1,000 pages ($1 batch); self-host by contract | Vendor claims wins over Document AI / Textract | HIPAA / SOC 2 status undocumented | Not for PHI paths |
| ABBYY Vantage | ≈ $0.02–$0.10 per page, 5–6 figure annual contracts | Enterprise IDP | BAA available | Out of budget |
| Nanonets / Veryfi / Klippa / Rossum | ≈ $0.30 per page (Nanonets); Veryfi from $500/mo; others quote-only | Invoice/form-centric | Veryfi and Nanonets advertise HIPAA options | Out of scope |

### 5.6 Extraction and medical NLP after OCR

| Option | Price | Fit | Verdict |
| --- | --- | --- | --- |
| Gemini Flash on Vertex (text of usable pages; page image as second pass) | 258 tokens per PDF page; at $0.30/M input and $2.50/M output ≈ $1–2 per 1,000 pages | Already the project's provider; Vertex is BAA-eligible; output must be anchored | **Keep** as extractor and second-pass reviewer |
| Claude (Anthropic API) / GPT-4.1 (OpenAI) | 1,500–3,000 tokens per PDF page (Claude); per-token | BAAs only on specific API tiers | Not needed; second cloud |
| MedGemma 1.5 4B (multimodal, open weights) | Self-hosted compute; HAI-DEF terms | Google states it targets structured extraction from lab reports; "not yet clinical-grade" | Evaluate in the AI routing spike, not as OCR |
| Amazon Comprehend Medical (NER + RxNorm linking) | $0.01 per 100 characters first tier → ≈ $0.30 per 3,000-character page ≈ $300 per 1,000 pages | Medication attributes and RxNorm codes out of the box | 100× the cost of Gemini; RxNorm normalisation is already in-house via the free NLM API |
| Azure Text Analytics for health / Google Healthcare NL API | Per 1,000-character record, tiered (verify) | Medical entity extraction | Second cloud or extra cost for something in-house already does |

## 6. Evidence: the synthetic benchmark

### 6.1 Corpus

23 fictional, clearly labelled synthetic cases generated deterministically by
`backend/scripts/document_intelligence_corpus.py` (seed 20260909). Each case carries
ground-truth page text, required fields with the page they appear on, expected page
classes, acceptable routes, and table cells where relevant. Nothing is derived from a
real record.

| Category | Cases |
| --- | --- |
| Born-digital PDFs (5) | two-page discharge summary; ruled lab table; two-column visit summary; Spanish prescription with decimal commas, accents and `c/24 h`; difficult dosages and three date formats |
| Simulated scans (7) | 300 dpi discharge; 150 dpi fax with 1.5° skew, hard threshold, speckle and streaks; 90°-rotated Spanish lab page; 72 dpi JPEG medication list; Spanish abbreviations (`VO`, `c/8 h`, `PRN`, `mcg/inh`); 200 dpi dosages; two-frame TIFF (English + Spanish) |
| Prescription images (4) | PNG pharmacy label; Spanish JPEG label; skewed, blurred, unevenly lit phone photo; script-font "handwriting" with warp |
| Adversarial (7) | born-digital header plus an embedded scanned attachment (mixed page); content page + blank page + scanner-noise page; scan with an invisible garbage text layer from a prior bad OCR; AES-256 encrypted PDF; random bytes named `.pdf`; PDF truncated at 55 %; DOCX bytes |

### 6.2 Metrics

- **Class / page-class accuracy**: document and per-page classification against the expectation.
- **Route acceptable**: the route is one the case allows (for example the fax may be automated or review, the encrypted file must be rejected, the handwriting note must not be automated).
- **CER / WER**: character and word error rate of the reading-ordered page text against ground truth, after case folding and whitespace normalisation, accents kept.
- **Fields found on correct page**: each required value (medication name, dose, frequency, allergen, reaction, condition, obligation, date, lab analyte or unit) is anchored by the deterministic anchoring step and lands on its ground-truth page.
- **Page-citation accuracy of found**: among anchored fields, the share whose page is right (a wrong-page anchor would be a fabricated citation).
- **Table cell accuracy**: recovered ruled-table cells matching row, column and text.
- **Calibration**: each OCR word's confidence paired with whether it appears in the page's ground-truth tokens; 10 bins, expected calibration error, and accuracy per policy band.
- **Latency** per page on an Apple-silicon laptop (hosted engines include network time) and **peak memory** of the benchmark process.
- **Rejected cleanly**: adversarial files must be rejected with a permanent reason and zero extracted words.

### 6.3 Engine results (same pipeline, only the OCR engine changed)

Full tables: `backend/reports/document_intelligence_benchmark_2026-09-10.md` and the
JSON next to it.

| Metric | Tesseract eng+spa | PaddleOCR (RapidOCR, server det.) | NIM PaddleOCR (hosted) | NIM Nemotron OCR v1 (hosted) | NIM Nemotron-Parse (hosted) | Embedded text only (today) |
| --- | --- | --- | --- | --- | --- | --- |
| Class accuracy | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| Route acceptable | 1.000 | 0.957 | 0.957 | 0.957 | 0.957 | 0.652 |
| Mean CER | 0.020 | 0.070* | 0.028 | **0.013** | 0.014 | 0.657 |
| Mean WER | 0.060 | 0.102 | 0.168 | 0.045 | **0.021** | 0.659 |
| Fields found on correct page | 0.969 | 0.978 | 0.987 | 0.982 | **1.000** | 0.359 |
| Page-citation accuracy of found | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| Table cell accuracy (born-digital) | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| Latency per page | **0.42 s** | 2.1 s | 0.87 s + net | 0.85 s + net | 1.4 s + net | 0.03 s |
| Adversarial rejected cleanly | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

\* dominated by two pages where a wrong orientation guess was accepted because the
engine's confidence is flat; elsewhere at or near 0.00.

Hard cases (fields found / total, CER):

| Case | Tesseract | PaddleOCR local | NIM PaddleOCR | Nemotron OCR | Nemotron-Parse |
| --- | --- | --- | --- | --- | --- |
| Fax 150 dpi, skew, speckle | 9/12, 0.174, **routed to review** | 12/12, 0.017 | 10/12, 0.064 | 10/12, 0.057 | 12/12, 0.002 |
| Phone photo, 4° skew, blur, gradient | 10/12, 0.121 | 12/12, 0.000 | 12/12, 0.083 | 12/12, 0.024 | 12/12, 0.000 |
| 72 dpi JPEG list | 5/6, 0.006 | 6/6, 0.006 | 6/6, 0.025 | 5/6, 0.031 | 6/6, 0.000 |
| Rotated 90° Spanish lab | 7/7, 0.010 | 7/7, 0.000 | 7/7, 0.137 | 7/7, 0.007 | 7/7, 0.017 |
| Spanish abbreviations | 11/11, 0.010 | 11/11, 0.000 | 11/11, 0.037 | 10/11, 0.017 | 11/11, 0.068 |
| Pharmacy label PNG / JPEG-es | 6/6, 0.007 / 5/5, 0.011 | 6/6, 0.010 / 5/5, 0.733† | 6/6, 0.000 / 5/5, 0.047 | 6/6, 0.007 / 5/5, 0.011 | 6/6, 0.000 / 5/5, 0.101 |
| Script-font "handwriting" | 2/3, routed to review | 3/3 (not flagged) | 2/3 (not flagged) | 3/3 (not flagged) | 3/3 (not flagged) |
| Garbage invisible text layer over scan | 12/12, 0.000 | 12/12, 0.000 | 12/12, 0.026 | 12/12, 0.026 | 12/12, 0.000 |
| Difficult dosages 200 dpi | 20/20, 0.000 | 18/20, 0.110 (drops one long line) | 20/20, 0.011 | 20/20, 0.007 | 20/20, 0.000 |

† wrong 180° orientation accepted; the label itself reads at CER 0.01 when upright.

Confidence calibration (accuracy of OCR words per policy band):

| Band | Tesseract | PaddleOCR local | NIM PaddleOCR | Nemotron OCR | Nemotron-Parse |
| --- | --- | --- | --- | --- | --- |
| ≥ 0.90 | 0.993 (863 words) | 0.987 (967) | 0.941 (904) | 0.995 (854) | 0.978 (all 1,006 at the 0.90 placeholder) |
| 0.75–0.90 | 0.860 (57) | 0.000 (1) | 0.526 (19) | 0.896 (77) | n/a |
| 0.50–0.75 | 0.865 (37) | 0.000 (3) | n/a | n/a | n/a |
| < 0.50 | 0.500 (28) | n/a (0) | n/a | n/a | n/a |

Reading: Tesseract and Nemotron OCR produce a confidence you can route on; PaddleOCR's
confidence is nearly always ≥ 0.90 and says nothing about page quality; Nemotron-Parse
reports none. Any stack built on PaddleOCR or a parser must take its routing signal
from the deterministic layer (anchoring success, image quality), not from the engine.

### 6.4 pypdfium2 versus PyMuPDF (PDF layer)

| Check | pypdfium2 5.13 (PDFium build 7999) | PyMuPDF 1.27 |
| --- | --- | --- |
| Embedded text, 6 born-digital cases | CER 0.000 on every page; two-column order correct natively | CER 0.000; column order needed custom code |
| Word boxes | Built from character boxes (≈ 20 lines of code) | Native |
| Image regions on a page | `get_objects()` with bounds | Native |
| Render 300 dpi grayscale | 25–100 ms per page; OCR on the render gave the same CER as on PyMuPDF renders | similar |
| Encrypted / random bytes / truncated file | Typed `PdfiumError` ("Incorrect password", "Data format error"): rejected | Opens and silently repairs the truncated file; must check `is_repaired` |
| Ruled tables | Not built in → pdfplumber | `find_tables()` |
| Licence | Apache-2.0 / BSD-3 | AGPL-3.0 / commercial |

### 6.5 Caveats about the evidence

- One rendering font (Helvetica) produced by the same libraries used to read it; real
  uploads vary more.
- "Handwriting" is a script font plus warp. Every learned engine read it perfectly and
  confidently; real handwriting will be far worse, and none of these engines' confidence
  will flag it. That is a corpus limitation, not a pass.
- No real fax hardware; Spanish gains are small because the script is Latin and
  anchoring folds accents.
- No clinician has adjudicated any output; managed Google engines and Gemini page
  reading were not measured (no credentials, and the Gemini key is out of credit).
- Two corpus bugs were found and fixed during the work (label crops cut off lines; a
  truncated PDF expectation), which is why early runs showed lower label scores.

## 7. Hosting: where each part runs, and what an API key buys you

Hosting decides more than accuracy at expo volume. Four ways to run the OCR layer,
compared for our Cloud Run deployment (1 vCPU, 512 MiB, scale to zero today):

| Option | What runs there | Monthly cost at 5,000 pages | Latency and cold start | Reliability on demo day | PHI / BAA | Ops burden |
| --- | --- | --- | --- | --- | --- | --- |
| **H1. In our container (CPU)**: pypdfium2 + RapidOCR (PP-OCRv5 server detector ≈ 100 MB) + Tesseract for orientation | Everything | $0 licence; Cloud Run compute only, a few dollars if the instance is warm during the demo | 2–4 s per scanned page on 1 vCPU (more on a throttled instance); model load adds ≈ 5 s to a cold start; needs 1–2 GiB memory and CPU always allocated or a Cloud Run Job | Depends only on our own service | Inside our GCP boundary; no third party | Dockerfile (apt `tesseract-ocr tesseract-ocr-spa`, pip `rapidocr onnxruntime`), memory bump, CPU setting |
| **H2. Same-cloud managed API (key or service account)**: Google Document AI OCR or Cloud Vision | OCR only; rest stays in H1 | ≈ $7.50 (Document AI OCR) or ≈ $6 (Vision, first 1,000 free) | ≈ 1–2 s per page, no cold start, no memory pressure | Google SLA; same project as everything else | HIPAA-eligible under Google's BAA when that matters | Enable API, service-account role, one adapter |
| **H3. Third-party hosted inference by API key**: NVIDIA build.nvidia.com trial (Nemotron-Parse, Nemotron OCR, PaddleOCR), Mistral OCR, OpenRouter / Together / Fireworks for open vision models | Reader or second reader | Free trial credits (NVIDIA), $1–2 per 1,000 pages (Mistral), per-token elsewhere | 1–7 s per page plus network; rate limits (NVIDIA trial ≈ 40 requests/min); payload caps (≈ 170 KB inline on NIM) | **Risky**: endpoints get retired (a NeMo Retriever OCR endpoint answered 410 Gone during this work), trial credits expire, no SLA | Requests logged; no BAA; synthetic data only | Just a key, but every call leaves our boundary |
| **H4. Serverless GPU we control**: Cloud Run GPU (L4 ≈ $0.70/h, scales to zero), Modal / RunPod / Replicate per-second GPU | Open vision-OCR models (Nemotron-Parse 2.0, PaddleOCR-VL, Qwen3-VL) | ≈ $0.001–0.01 per page in GPU time, but cold starts of 30–90 s and a warm GPU during the demo ≈ $0.70–1.00 per hour | Best accuracy, worst cold start | Cloud Run GPU is under Google's BAA; the others are not | Container with weights (1–4 GB), vLLM or ONNX runtime, GPU quota |
| **H5. Hugging Face Inference Endpoints (dedicated)** | Any Hub model | GPU hourly (≈ $0.50–1.00+/h), scale-to-zero optional | Same cold-start profile as H4 | Vendor SLA | BAA only on the Enterprise plan with private networking | Low code, but a second vendor and account |

What this means for us:

- The app already depends on one hosted API for extraction (Gemini on Vertex), so a
  hosted OCR API is not a new class of dependency; the question is which one.
- For the expo, **H1 as the primary path** keeps the demo independent of trial credits
  and endpoint retirements, costs nothing in licences, and needs only a bigger Cloud Run
  configuration. It is the only option that keeps working if a third-party key or
  endpoint dies the night before.
- **H2 is the drop-in insurance policy**: if hosting RapidOCR in the container proves
  awkward (memory, cold starts), Document AI or Cloud Vision plug into the same
  `OcrEngine` call shape through a service account, cost under $10 a month at demo
  volume, and are the only hosted engines with a BAA path.
- **H3 is a demo feature, not a dependency**: hosted Nemotron-Parse is the most accurate
  reader we measured and free on trial credits, so a "second opinion" button that shows
  its reading over the page image is worth having, labelled synthetic-only, with the
  app fully functional when it is unavailable.
- **H4/H5 are not worth the ops before the expo**; revisit if the team decides to run an
  open vision model as the second reader later.

## 8. Decision: the recommended stack for the December expo

One stack, $0 licence, everything on the laptop or the existing Cloud Run service,
with a managed engine as insurance and a hosted model as a demo feature.

| Layer | Choice | Why this one | Runner-up |
| --- | --- | --- | --- |
| PDF rendering and embedded text | **pypdfium2** (Apache-2.0 / BSD-3) | Measured CER 0.000 and correct column order on every born-digital page; typed rejection of encrypted/corrupt files; removes the AGPL problem | PyMuPDF with a paid licence |
| Ruled tables on born-digital pages | **pdfplumber** (MIT) | Best-rated open-source coordinate tool for ruled tables | Heuristic row clustering |
| OCR for scans, photos, labels, image regions | **PaddleOCR PP-OCRv5 via RapidOCR**, server detector + mobile Latin recogniser, CPU | Measured 12/12 on fax and phone photo, 6/6 on 72 dpi, Spanish 11/11, $0; the engine that makes judges' phone photos work | Tesseract eng+spa (simplest, best calibrated, weaker on hard images) |
| Orientation | **Tesseract OSD** (200 ms) | PaddleOCR reads sideways text confidently; OSD corrected every rotated page in the benchmark | Geometry heuristic on detected boxes |
| Confidence and routing | **Deterministic layer**: anchoring success, page quality, image-quality signals | PaddleOCR's confidence is uninformative (99.6 % of words ≥ 0.90); routing must not depend on it | Tesseract as a calibrated second pass |
| Structuring | **Gemini Flash on Vertex** over page-marked text | Already the provider; 258 tokens per page; BAA-eligible | Gemini page-image second pass on flagged pages |
| Viewer with citation overlay | **react-pdf (pdf.js)** or **EmbedPDF**, `<img>` + overlay for images | Free; draws boxes from citation coordinates; clinician portal currently has no viewer | Syncfusion while Community-License eligible |
| Managed insurance | **Google Document AI OCR** via service account | $1.50 per 1,000 pages, BAA path, same project; same call shape | Cloud Vision |
| Demo feature | Hosted **Nemotron-Parse** "second opinion" on flagged pages | Most accurate reader measured; free trial credits | Nemotron OCR v1 (calibrated confidence) |
| Hosting | **H1** (in the container) with 1–2 GiB memory and CPU always allocated or a Cloud Run Job | Independent of trial credits and endpoint retirements | H2 if the container path is awkward |

What this replaces: PyMuPDF and the ad-hoc `receive_document` branch; the composed
"citation" sentence; the missing clinician viewer.

## 9. How it works: the logic in detail

This is the behaviour of the prototype under `backend/src/app/services/document_intelligence/`
(built with PyMuPDF for measurement; the pypdfium2 swap changes only the PDF calls).

### 9.1 Container and page classification

1. **Sniff bytes before trusting the declared MIME type.** `%PDF-` → PDF; PNG / JPEG /
   TIFF / WebP magic → raster; a supported MIME type whose bytes match nothing →
   *unreadable* (corrupt or mislabelled); anything else → *unsupported*. A renamed file
   is never opened with the wrong parser.
2. **PDF open.** Password required → *encrypted* (rejected, permanent). Parser failure →
   *unreadable*. A PDF the parser had to repair is flagged `repaired`; its content may be
   incomplete, so the route is capped at `review_with_caution`. Parser warnings are kept
   (first three distinct lines). More than 50 pages → the first 50 are processed and a
   warning says the rest need a clinician.
3. **Per-page signals**: number of text characters; a *text-layer sanity* score (share
   of alphabetic tokens that look like words: short tokens are abbreviations, long
   consonant clusters are OCR debris); image coverage (sum of embedded image areas ÷
   page area); and, only when there is neither text nor images, an *ink ratio* from a
   50 dpi render (share of pixels darker than 200/255).
4. **Page class rules** (defaults in `DocumentIntelligencePolicy`):
   - ≥ 20 text characters and sanity ≥ 0.60 → **born-digital**; if images cover ≥ 10 %
     of the page → **mixed**.
   - text present but sanity < 0.60 → **scanned** with a warning ("embedded text layer
     failed the sanity check; OCR used"), which catches invisible garbage layers from a
     prior bad OCR.
   - no usable text, image coverage ≥ 5 % → **scanned**.
   - no text, no images, ink ratio < 0.002 → **blank**; ink present → **scanned**
     (vector-drawn text).
5. **Document class**: all content pages born-digital → born-digital; all scanned →
   scanned; otherwise mixed; no content pages → blank (rejected).

### 9.2 Reading born-digital pages

Words with boxes come from the PDF text layer; lines are grouped by block and line;
blocks are ordered top to bottom with a **column band**: where right-hand blocks exist,
the vertical band they span is read left column first, then right, while headings
above and footers below the band are emitted in plain order. (pypdfium2 returned the
correct order natively on the test page; keep the band logic as a safety net.) Ruled
tables are extracted as cells with row, column, text and box. Every embedded word has
confidence 1.0.

### 9.3 Reading scanned pages and rasters

1. Render the page in **grayscale at 300 dpi** (≈ 8 MB for a letter page instead of
   ≈ 25 MB in RGB). If the rendered page has ink ratio < 0.002 it is **blank**; skip OCR.
2. **Prepare the raster**: autocontrast; if the shorter side is under 1,000 px, upscale
   2× or more with Lanczos (a 72 dpi list went from unreadable to 6/6 fields).
3. **Orientation**: recognise the page as-is, ask the orientation detector (Tesseract
   OSD) for a suggestion, recognise the rotated copy, and keep the rotation if its score
   is within 0.05 of the upright score and it reads at least as many characters. If the
   best score is still below 0.60, try the remaining rotations. An upright page never
   pays for four OCR passes; a sideways page is corrected even when the engine is
   confident on sideways text.
4. **Recognise**: words with pixel boxes and confidence; convert pixels to PDF points
   (72 ÷ dpi) or keep pixels for image uploads (`coordinate_unit` says which). Line-level
   engines (PaddleOCR, NIM) return one box per line; words are split proportionally by
   character count and marked approximate.
5. **Mixed pages**: keep all embedded words; OCR each embedded image region ≥ 2 % of the
   page as a clip, offsetting boxes into page coordinates; drop OCR words that overlap
   an embedded word by more than 50 %.
6. **Multi-frame TIFF** becomes one page per frame. Undecodable image bytes are
   *unreadable*.

### 9.4 Page quality and document route

- Page confidence = character-weighted mean of word confidence (a long garbled token
  counts more than a stray dot).
- Page quality: **usable** ≥ 0.75, **low** 0.50–0.75, **unusable** < 0.50, **empty**
  when no words. Unusable pages are excluded from model input entirely: garbled OCR is
  the input most likely to make a model invent a dose.
- Route: `rejected` for encrypted / unreadable / unsupported / all-blank (permanent
  failure, no retry, user re-uploads); `clinician_only` when no page has usable text
  (also when the OCR engine is missing or disabled, then marked transient so a retry is
  sensible after deployment is fixed); `review_with_caution` when any page is low
  quality or the PDF was repaired; `automated_candidates` when every content page is
  usable. All routes still end in clinician review; the route only decides whether
  model extraction may run and how loudly the result is flagged.
- With PaddleOCR as the engine, its confidence stays high on bad pages, so the low /
  unusable bands rarely trigger. Add two deterministic signals before rollout: an
  image-quality score (blur via Laplacian variance, contrast, effective dpi) and the
  **anchoring failure rate** of the model's output on that page. Either can lower the
  page quality independently of the engine's score.

### 9.5 Structuring and anchoring

- The model receives **page-marked text** (`[[page 2]]` headers) of usable and low pages
  only, never images by default, and must return items with `{page, excerpt,
  confidence}` evidence (the shape the ingestion rewrite already validates).
- **Anchoring** (`anchor_value`) normalises both sides the same way: NFKD accent
  stripping, case folding, `µ`/`μ` → `u`, decimal comma between digits → dot, dots
  adjacent to letters removed (`q.d.` → `qd`, `Dr.` → `dr`), a space inserted between
  digits and letters (`500mg` → `500 mg`, `q12h` → `q 12 h`), punctuation other than
  `. / % -` dropped. It then slides token windows of the value's length (±1) over the
  page words: an exact window scores 1.0; otherwise the best SequenceMatcher ratio
  ≥ 0.85 wins (so `Metfornin 500 mg` still anchors `Metformin 500 mg` at ≈ 0.94). The
  anchor records page, union box of the matched words, the full line as the quote,
  matched text, similarity, the **lowest** word confidence among matched words, method,
  and line ids. The best-scoring page wins; unusable pages are never searched.
- **Per item** (`ground_item`): medication anchors name (primary), dosage and
  frequency; condition anchors name; allergy anchors allergen and reaction; obligation
  anchors description. Placeholders (`as directed`, `unknown`, `active`) are skipped.
  Candidate confidence = min over anchored attributes of (similarity × lowest word
  confidence); no primary anchor → 0. Bands: high ≥ 0.90, medium ≥ 0.75, low otherwise.
  Uncertainty notes are appended for every miss ("the dosage '500 mg' was not found in
  the source text; it may have been inferred rather than read"), every approximate match,
  every low-quality page used, and every model-cited excerpt that is not on the page it
  claims.
- Values the model returned but the page does not contain are **kept as low-band
  candidates with an explicit note, never silently corrected and never dropped**, so the
  clinician sees what the model claimed and can reject it.

### 9.6 Evidence and citation format

`evidence_citations.excerpt` is the quote line(s); `evidence_citations.location`:

```json
{"scope": "page", "page": 2,
 "bbox": {"x0": 48.0, "y0": 112.3, "x1": 168.9, "y1": 124.8}, "unit": "pt",
 "field": "dosage", "matched_text": "50 mg", "match_score": 1.0,
 "word_confidence": 0.96, "method": "ocr", "line_ids": [3], "anchored": true}
```

`source_provenances.document_location` carries `{scope: document, document_class,
route, pages, source_sha256}`; `extractor_version` is the pipeline + engine version
string (for example `document-intelligence/1;pymupdf/1.27.2;tesseract/5.5.1`);
`external_source_version` is the file's SHA-256 so a re-extraction of the same bytes is
detectable. An unanchored value gets `{"scope": "document", "anchored": false}` and a
low band. The viewer draws `bbox` on `page` (points for PDFs, pixels for images).

### 9.7 Retry, retention, provider lifecycle

- **Retry** only transient failures (download, OCR timeout or crash, engine missing) up
  to the existing three attempts through the claim RPC; permanent failures never retry.
  A new extractor version creates a new run and new candidates; it never rewrites an
  old run.
- **Retention**: keep the original object permanently (soft-delete with a `deleted_at`
  marker instead of `storage.remove`); write every `DocumentExtraction` JSON to
  `documents/{patient_id}/{document_id}/extractions/{run_id}.json`; retain every
  version. This needs a change to `DocumentService.delete_document` and a decision on
  patient-deletion rights (synthetic data today).
- **Provider lifecycle**: pin engine versions and model checksums in the image (for
  example tessdata `spa` sha256 `6f2e04d0…ea3b464`, RapidOCR model files) and record
  them on every run; a new engine must beat the incumbent on the corpus before it is
  switched on; keep two versions of stored artifacts readable; fallback order embedded
  text → local OCR → managed OCR (if configured) → `clinician_only`. Hosted trial
  endpoints are never in the fallback chain.

### 9.8 Viewer and the clinician acceptance flow

- **Patient portal**: keep the PDF viewer (Syncfusion while eligible, or react-pdf),
  add inline `<img>` rendering for image uploads.
- **Clinician portal** (no viewer today): add a document viewer next to the external-
  records workspace; when the clinician clicks "Source" on a candidate, open the cited
  page and draw the citation box(es) from `evidence_citations.location`, scaled from
  points or pixels to the rendered page; show the quote and the uncertainty notes
  beside it. For a second-reader disagreement, show both readings.
- **Acceptance flow before rollout** (synthetic scanned prescription): upload → document
  shows `review_with_caution` or `automated_candidates` with the reason → candidates
  appear with bands and notes → "Source" opens page N with the box → clinician corrects
  the `500 ma` dosage, approves the rest, rejects one → canonical medications unchanged
  until reconciliation → audit events present. Acceptance: 100 % of candidates cite a
  page/region/quote; zero canonical writes; low-band candidates visibly flagged;
  rejected uploads show the permanent reason; a document deleted by the patient keeps
  its extraction history.

### 9.9 Deployment steps

1. Dockerfile: `apt-get install tesseract-ocr tesseract-ocr-spa`; `pip install
   pypdfium2 pdfplumber rapidocr onnxruntime`; bake the RapidOCR models into the image
   (they download on first use otherwise) and pin versions in the lockfile.
2. Cloud Run: 1–2 GiB memory, `--no-cpu-throttling` (CPU always allocated) for the
   ingestion service, or move extraction to a Cloud Run Job; keep `--min-instances 1`
   only during the demo window.
3. CI: the same apt packages in the backend test jobs so the corpus regression suite
   runs OCR; the suite skips OCR assertions when the binary is absent.
4. Secrets: `NVIDIA_API_KEY` (demo feature only) in Secret Manager and `.env`, never in
   the repo; Document AI via the Cloud Run service account if H2 is enabled.
5. Wire `DocumentIntelligenceService.extract` into the ingestion graph's
   `receive_document` (replacing the PDF/image branch) and `ground_item` into
   `_register_candidates`; pass `route` through to `parse_status` /
   `parse_failure_code`.

## 10. Cost picture at expo volume (5,000 pages per month)

| Stack | Monthly licence / API cost | Notes |
| --- | --- | --- |
| H1: pypdfium2 + pdfplumber + RapidOCR + Tesseract OSD; react-pdf viewer | $0 | Cloud Run compute only; a warm 2 GiB instance for a demo day is a few dollars |
| + Gemini Flash structuring on usable pages | ≈ $5–10 | Existing provider; 258 tokens per page plus output |
| H2 insurance: Document AI OCR on scanned/photo pages only (say 40 % of pages) | + ≈ $3 | + $20 if Layout Parser is added for scanned tables |
| H3 demo feature: hosted Nemotron-Parse on flagged pages | $0 on trial credits | No SLA; expect changes |
| H4: open vision model on Cloud Run GPU | ≈ $0.001–0.01 per page in GPU time; ≈ $0.70–1.00 per warm hour | Cold starts 30–90 s |
| Commercial viewer or OCR SDK (Nutrient, Apryse, ABBYY) | $1,500 to $40k+ per year | Not justified by any use case here |
| Medical NLP APIs (Comprehend Medical) | ≈ $300 per 1,000 pages | Not justified; RxNorm normalisation exists in-house |

## 11. Risks, limitations and open questions

1. **Handwriting.** No local engine reads real handwriting reliably, and the learned
   engines will not flag it by confidence. Options: route pages with an image-quality
   or "handwriting-likelihood" signal to `clinician_only`; use Nemotron-Parse or
   Document AI as the reader for those pages with mandatory image-side verification.
   Do not promise handwriting at the expo.
2. **PaddleOCR drops an occasional long line** (one 64-character line on the dosages
   page with both detectors; the mobile detector drops more at 300 dpi). Mitigation:
   server detector at 300 dpi (measured best), and the anchoring failure rate catches a
   dropped line as an unanchored value rather than a silently missing one; a Tesseract
   fallback pass on pages where the model's values fail to anchor is cheap.
3. **Hosted trial endpoints are not dependable**: one NVIDIA OCR endpoint reported end
   of life during this work; payload caps and rate limits apply; requests are logged; no
   BAA. Keep them out of the primary path.
4. **Synthetic corpus**: one font, simulated degradations, script-font handwriting, no
   clinician adjudication. Real-layout synthetic documents and 40+ adjudicated cases are
   still needed before any accuracy claim outside the demo.
5. **Cloud Run constraints**: request-scoped CPU throttles background OCR; 512 MiB is
   tight for the server detector. Needs the configuration change in section 9.9.
6. **Licensing**: PyMuPDF (AGPL) must go or be licensed; Syncfusion is free only under
   the Community License; NIM containers are free for development only.
7. **Retention versus deletion**: "preserve permanently" conflicts with today's
   delete path and, eventually, with patient deletion rights; decide the policy.
8. **Patient-facing summary** is generated from unreviewed extraction today; the plan
   says only approved records are explained. Out of this workstream's scope but blocking
   for anything beyond a demo.
9. **Concurrent rewrite**: the ingestion graph is being rewritten in the same working
   tree (uncommitted, another session). The seam is designed for it; wiring should wait
   until that lands. Its `ClinicalFactCreate(confidence=…)` drops the score silently.
10. **PHI**: everything here assumes synthetic data. A real-PHI deployment needs the
    BAA-eligible paths only (H1 or H2, Vertex), the retention policy, and the legal
    review the tracker already lists.

## 12. Suggested plan to the expo

| Week | Work | Outcome |
| --- | --- | --- |
| 1 | Swap PyMuPDF → pypdfium2 (+ pdfplumber) in the prototype; add RapidOCR as the engine with Tesseract OSD; add image-quality signals to page quality; fix the three prototype tests | Local stack passes the corpus regression suite |
| 2 | Wire into the ingestion graph after the rewrite lands: `receive_document` → `extract`, `_register_candidates` → `ground_item`; `route` → `parse_status`; Dockerfile, Cloud Run memory/CPU, CI packages | Uploads of scans and photos produce page-cited candidates in staging |
| 3 | Clinician-portal viewer with citation overlay; inline images in both portals; "Source" opens page + box; retention change | Clinician acceptance flow passes end to end |
| 4 | Document AI adapter behind a flag (insurance); Nemotron-Parse "second opinion" button on flagged pages (synthetic only); 40 real-layout synthetic documents adjudicated by the clinical reviewer; re-tune thresholds | Demo script rehearsed with photos, faxes and a Spanish prescription |

## 13. Prototype inventory, how to reproduce, and repository state

**Files created in this workstream (uncommitted, untracked):**

- `backend/src/app/services/document_intelligence/` — `models.py` (contracts and policy),
  `classification.py` (container sniffing, page signals, page class rules),
  `embedded_text.py` (words, lines, column-band order, ruled tables),
  `ocr.py` (`OcrEngine` contract, Tesseract adapter with word confidence and OSD),
  `pipeline.py` (`DocumentIntelligenceService.extract`), `anchoring.py`
  (normalisation and window matching), `grounding.py` (`ground_item`,
  `candidate_from_grounded`, `DocumentEvidenceCandidateService.register`).
- `backend/scripts/document_intelligence_corpus.py` — the 23-case synthetic corpus builder.
- `backend/scripts/benchmark_document_intelligence.py` — metrics, engines, report writer.
- `backend/scripts/document_intelligence_engines.py` — benchmark-only engines: RapidOCR,
  NIM PaddleOCR, NIM Nemotron OCR, Nemotron-Parse.
- `backend/tests/unit/services/document_intelligence/` — 57 tests (54 pass; 3 fail on
  test construction: a truncation the parser cannot repair, a header under the 20-char
  minimum, a helper drawing outside a small image).
- `backend/reports/document_intelligence_benchmark_2026-09-10.{md,json}` — the run.
- `.env.example` gained `NVIDIA_API_KEY` (evaluation only); the local `.env` holds a key.
- This document replaces the earlier drafts `rec-003-document-intelligence-plan.md` and
  `rec-003-ocr-tool-options.md`.

**Reproduce the benchmark** (from `backend/`, project virtualenv; Tesseract 5 with
`eng`, `spa`, `osd` data; RapidOCR and ONNX Runtime installed somewhere on
`PYTHONPATH`; `NVIDIA_API_KEY` in `.env` for the hosted engines):

```bash
export SUPABASE_URL=https://test.supabase.co SUPABASE_ANON_KEY=x \
       SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_JWT_SECRET=x
PYTHONPATH=src:/path/with/rapidocr python scripts/benchmark_document_intelligence.py \
  --engines baseline,rapidocr,nim_paddleocr,nim_nemotron_ocr,nim_nemotron_parse \
  --tessdata-dir /path/with/eng-spa-osd --report-dir reports
```

`python scripts/document_intelligence_corpus.py --out-dir /tmp/corpus` writes the
corpus and a manifest on its own.

**Repository state to be aware of.** Three sessions were editing the same working
tree. My checkout briefly moved the tree to `feature/document-intelligence-assessment`,
so commit 502a986 (Gemini model fix) sits on that branch; the tree is now on
`codex/fix-gemini-document-parsing`. Uncommitted changes from the other sessions
include the ingestion rewrite, migration 034, an AI evaluation harness, and tracker and
docs edits. Nothing in this workstream is committed; no production file, CI workflow,
Dockerfile, migration or tracker entry was modified.

## 14. Sources

Nutrient [trial](https://www.nutrient.io/sdk/try/) and [pricing](https://www.nutrient.io/sdk/pricing/); [Vendr PSPDFKit guide](https://www.vendr.com/buyer-guides/pspdfkit); [Apryse pricing](https://verdocs.com/apryse-pricing/); [Syncfusion Community License](https://www.syncfusion.com/products/communitylicense); [react-pdf](https://www.npmjs.com/package/react-pdf); [react-pdf-highlighter-extended](https://github.com/DanielArnould/react-pdf-highlighter-extended); [EmbedPDF](https://github.com/embedpdf/embed-pdf-viewer); [pypdfium2](https://github.com/pypdfium2-team/pypdfium2); [Artifex licensing](https://artifex.com/licensing); [PDF parsing tools comparative study](https://arxiv.org/html/2410.09871v1); [Python OCR engines compared](https://invoicedataextraction.com/blog/python-ocr-library-comparison-invoices); [Tesseract vs EasyOCR](https://imagetotable.ai/blog/tesseract-vs-easyocr-2026); [PaddleOCR 3.0 report](https://arxiv.org/html/2507.05595v1); [PP-OCRv5 multilingual models](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.en.md); [RapidOCR model list](https://rapidai.github.io/RapidOCRDocs/main/model_list/); [Docling](https://github.com/docling-project/docling); [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF); [Tesseract handwriting](https://joseurena.medium.com/tesseract-ocr-evaluating-handwritten-text-recognition-1c6db85b2e7f); [TrOCR prescriptions](https://ieeexplore.ieee.org/document/10894218/); [Surya licence](https://github.com/datalab-to/surya); [OmniDocBench](https://github.com/opendatalab/OmniDocBench); [OCR hallucination benchmark KIE-HVQA](https://arxiv.org/pdf/2506.20168); [Gemini document boxes](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/bounding-box-detection); [Qwen3-VL](https://github.com/qwenlm/qwen3-vl); [Document AI pricing](https://cloud.google.com/document-ai/pricing); [Cloud Vision pricing](https://cloud.google.com/vision/pricing); [Textract pricing](https://lenscopy.com/compare/aws-textract/); [Azure Document Intelligence pricing](https://docuocr.com/blog/azure-document-intelligence-pricing); [Mistral OCR 3](https://mistral.ai/news/mistral-ocr-3/); [ABBYY pricing](https://www.vendr.com/marketplace/abbyy); [Nanonets pricing](https://www.extend.ai/resources/nanonets-review-features-pricing-alternatives); [Gemini document processing](https://ai.google.dev/gemini-api/docs/document-processing); [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing); [Claude PDF support](https://platform.claude.com/docs/en/build-with-claude/pdf-support); [Anthropic BAA](https://privacy.claude.com/en/articles/8114513-business-associate-agreements-baa-for-commercial-customers); [OpenAI file inputs](https://platform.openai.com/docs/guides/pdf-files); [AI vendors and BAAs](https://aiprovidertrust.com/questions/hipaa-baa/); [Comprehend Medical pricing](https://aws.amazon.com/comprehend/medical/pricing); [MedGemma 1.5](https://developers.google.com/health-ai-developer-foundations/medgemma); [Healthcare OCR handwriting accuracy](https://www.llamaindex.ai/insights/healthcare-ocr-tools); [GPT-4 medication extraction and ADR reviews](https://pmc.ncbi.nlm.nih.gov/articles/PMC13465311/); [Hybrid NLP-LLM deprescribing extraction](https://www.medrxiv.org/content/10.64898/2026.04.29.26352010v1.full); [Post-discharge action extraction](https://arxiv.org/html/2605.06191); [NIM Image OCR API](https://docs.nvidia.com/nim/ingestion/image-ocr/latest/api-reference.html); [Nemotron-Parse API](https://docs.nvidia.com/nim/vision-language-models/1.7.0/examples/nemotron-parse/api.html); [Nemotron-Parse 2.0](https://huggingface.co/nvidia/NVIDIA-Nemotron-Parse-2.0); [Nemotron OCR v1](https://huggingface.co/nvidia/nemotron-ocr-v1); [NIM for Developers](https://developer.nvidia.com/nim); [NVIDIA AI Enterprise pricing](https://docs.nvidia.com/ai-enterprise/planning-resource/licensing-guide/latest/pricing.html); [NIM pricing overview](https://costbench.com/software/llm-api-providers/nvidia-nim/); [Nemotron Nano 2 VL](https://arxiv.org/pdf/2511.03929); [Hugging Face endpoints and HIPAA](https://discuss.huggingface.co/t/hipaa-compliance/77922); [Cloud Run CPU allocation](https://docs.cloud.google.com/run/docs/configuring/billing-settings); [Cloud Run background tasks and throttling](https://walter-tscharf-development.medium.com/cloud-run-problems-with-background-tasks-and-cpu-allocation-29a7bf02ca54); [Cloud Run pricing](https://cloud.google.com/run/pricing); [L4 GPU pricing](https://getdeploying.com/gpus/nvidia-l4); [self-hosted OCR VLM cost](https://www.spheron.network/blog/best-open-source-ocr-vlm-self-host-gpu-cloud-2026/).
