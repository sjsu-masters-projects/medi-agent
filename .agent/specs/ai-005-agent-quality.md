# AI-005 — Agent quality: documents, explanations, triage and OCR

## Why

On October 12 a synthetic one-page follow-up lab report for Morgan Ellis (HbA1c 7.8%,
fasting glucose 146, lipids, eGFR 98, urine albumin/creatinine, B12) went through the
production upload → review → care-plan path. Every step worked, but the AI steps
understood almost nothing of the document:

- Extraction returned one fact (the diagnosis). The extraction prompt asks only for
  medications, conditions, allergies and obligations, so all 20 results were dropped.
- The patient explanation said the record listed no follow-up steps and suggested asking
  about tests. It is generated from extracted facts only, never from the document text.
- Nora answers about documents from those facts and the explanation, so it could not
  say what the A1c was either.

Evidence: [deployed recheck](../../docs/evidence/deployed-recheck-2026-10-11.md#clinician-flow-for-an-uploaded-lab-report-october-12).

## Current behaviour (origin/main, October 12)

| Step | Where | Inputs | Gap |
| --- | --- | --- | --- |
| Extraction | `agents/ingestion/prompts.py:9-49`, schema `models/document_extraction.py:75-83`, Flash, temperature 0.1 | Text of usable pages (embedded text or OCR) | Four categories only; no lab results, vitals, procedures, immunizations, document date, author or facility; no prompt version stored |
| Grounding | `services/document_intelligence/grounding.py` | Model output + page text | Unknown categories silently dropped |
| Patient explanation | `agents/ingestion/prompts.py:52-82`, `services/document_summary_service.py` (`patient-explanation/4`) | Persisted facts (medication, condition, obligation) | No document text or type; allergies dropped; lab-only documents get no explanation; no faithfulness check |
| Chat triage | `adk/agents/care_coordinator/prompts.py:16` (+ deterministic floor `safety/triage_floor.py`) | Message, history, record tools | The triage eval scores a separate proxy prompt (`services/triage_prompts.py`), not this one |
| OCR | `services/document_intelligence/pipeline.py`, Tesseract eng+spa | Scanned pages and images | Never evaluated end to end; OCR confidence is not given to the model |
| Evals | `services/ai_evaluation.py`, `tests/fixtures/eval/*` | Synthetic cases | Lab case doc-009 expects empty lists; golden lab fixture uses an outdated schema; extraction eval runs at temperature 0.3 vs 0.1 in production |
| Spanish | care-plan translation (`usted`) vs explanation and Nora (`tú`) | | Inconsistent register |

## Documents and workflows covered

| Document | What the agents must get right |
| --- | --- |
| Lab report | Every printed result with value, unit, range and flag on its own row; calculated values; critical flags; no interpretation |
| Discharge / after-visit summary | Medication actions (continue, new, changed, stop, hold); diagnoses; allergies or "no known allergies"; vitals; procedures; vaccines; follow-up visits; patient instructions |
| Prescription, medication list, pharmacy label | Name, dose, frequency, route and directions as printed; one item per line, never merged |
| Imaging, pathology, ECG and other studies | Procedure, date and the printed impression verbatim |
| Referral, clinic note | Problems, instructions, follow-up appointments |
| Immunization record, home logs | Each vaccine dose; each reading |
| Spanish documents | Same as above in Spanish ("Suspender", "Alto", "Sin alergias conocidas") |
| Scanned or photographed copies | Same values through OCR, or clinician-only review with a reason |

| Workflow | Rule |
| --- | --- |
| Clinician review | Every candidate is grounded on the page; results and vitals anchor on their own printed row and need an exact value; a flag that contradicts its range is low confidence |
| Care-plan drafting | Only medications and patient obligations; a stopped or held medication is never publishable and blocks matching active items until a clinician decides; a changed medication needs the new dose confirmed; results-only documents do not open a draft |
| Patient explanation | Built from grounded facts of every type; out-of-range and critical results named with their ranges, no advice; stopped medications described as stopped; every number must exist in the facts, and every number must survive translation, or nothing is shown |
| Assistant (Nora) | Sees results with their flag and range and medication actions; never interprets a result or reminds a patient to take a stopped medication |

## Delivered in the first slice

Branch `feature/document-results-extraction`:

- Model input keeps printed table rows (`PageExtraction.layout_text`), for embedded text
  and OCR alike.
- Extraction prompt `document-extraction/2` (version stored in each fact's provenance):
  document type, medication `status`, lab results, vital signs, immunizations, procedures,
  appointments, "no known allergies"; output validated item by item, so one malformed item
  no longer discards the document; output ceiling 8192 tokens.
- Grounding: row-scoped anchoring, exact values, deterministic `flag_meaning`,
  `range_status`, flag/range contradiction check, critical flag note, `medication_action`.
- An "other" upload records its classified document type; a chosen type is never replaced.
- Care-plan safety: stop/hold, changed-dose blockers; drafts only for medication or
  obligation facts.
- Explanation `patient-explanation/5` with the number check and retry; translation keeps
  numbers and uses no gendered clinician titles.
- Nora: result and action fields, 60 facts per document, prompt rules for results and
  stopped medications.
- Clinician facts dialog per type (lab rows, flag and Critical badges, Stop/Hold badges);
  clinician dates in en-US (UX-004).
- Evaluation measures the production settings and scores lab results.

Verified locally against the production model on synthetic documents: the October 12 lab
report (20 of 20 results, flags and ranges correct), a discharge summary with continue,
stop, increase and new medications, NKDA, vitals, an X-ray impression, a flu vaccine and a
follow-up visit, and a Spanish visit summary with "Suspender". A 200-dpi scan of the lab
report reads at OCR confidence 0.93; its one decimal loss ("4.0 - 5.6" read as "40-56") is
caught by the contradiction check.

## Second slice — follow-ups

Branch `feature/agent-quality-followups` (stacked on the first slice):

- **Critical-result alert** (migration `059_critical_result_alerts.sql`, requester applies):
  when a lab result the report flags critical is cited to its document, the patient's active
  care team gets one Safety notification per document ("Critical test result reported",
  link to that document). Patients never get it; it stays work until read, or until the
  document is rejected. Opted-in clinicians get the grouped review email, subject "Urgent
  review work available", with no health detail. Verified in disposable PostgreSQL 16 with
  the notification suite (53 passed).
  Production check (October 13, synthetic test patient): a basic metabolic panel with
  potassium 6.9 "HH" yielded 7 results and 2 vitals with correct flags, one alert delivered
  only to Elena, no patient alert, no care-plan draft, and an explanation that leads with
  "contact your care team today". The alert showed under History but not Needs attention;
  `060_critical_result_open_work.sql` adds it to open work until acknowledged.
  Patient side (signed in as the test patient): Records → the report shows "Test results"
  by panel with Critical on potassium plus "Contact your care team today", High on BUN,
  creatinine and glucose, measurements listed separately, and "Not yet reviewed by your
  care team" on every row. Nora, asked about the potassium, gave the value and printed
  range, said to contact the care team today (911 for severe symptoms), listed the other
  high results without interpreting them, and cited the report. A synthetic discharge
  summary produced a draft where STOP glipizide is blocked as never publishable and
  "Increase to 20 mg daily" lisinopril carries the changed-dose conflict.
- **Triage evaluation on the production prompt:** the harness now sends the Care
  Coordinator instruction (with record context in place of tool results) instead of a
  stand-in. Eight new cases: a critical potassium, an A1c question, having taken a stopped
  medication, and chest pain, each in English and Spanish. Production model: 36 cases,
  92% accuracy, 100% safety (no under-triage); the six misses are over-triage of urgent
  symptoms as emergency and of mild routine symptoms or low mood as urgent. The coordinator
  now treats taking a medication a document stopped as urgent.
- **Phone-photo OCR:** synthetic degraded photos (rotation, keystone, blur, glare, dim, noise,
  low resolution, unreadable) through the real pipeline, and OCR quality passed to the model
  in each page header.
- **Patient Records results:** `GET /api/v1/documents/{id}/results` returns the patient's own
  results and measurements as printed, with review status and page; Records shows them by
  panel with High/Low/Outside range/Critical chips (Critical adds "contact your care team
  today"), "not yet reviewed" markers and no interpretation, in English and Spanish.
- **One Spanish register (tú):** care-plan translation, explanations, Nora and all patient
  UI copy (31 strings converted). Approved wording is unchanged until its next review.

## Chat results card

Branch `feature/chat-results-card` (migration `062_chat_message_attachments.sql`, requester
applies): when Nora's reply cites one of the patient's documents that has extracted
results, the server snapshots that document's results (the rows Records shows, from the
source-checked facts, never parsed from the reply) onto the saved message as an
attachment. The patient chat renders it as a card under the reply: "Contact your care team
today" and the 911 line first when any result is critical, out-of-range results with their
chips and printed ranges, the rest behind "Show N results in range", and a link to Records.
Nora's instructions are unchanged except one line saying the values are shown in the card.
Older messages keep no card. Before 062 is applied the reply is saved as text and the card
still shows live.

## Result named in a heading (production check, October 13)

A synthetic lipid panel uploaded after #163 printed "LIPID PANEL AND HEMOGLOBIN A1C" above
its rows. The model read all seven results, but grounding matched the A1c name on the
heading first, found no 8.1 on that line, scored the result zero and dropped it without a
warning: the reviewer saw six results and no A1c. Branch `fix/result-row-anchoring`: a
result's name is looked up at every printed occurrence, and the copy whose row also carries
the value, unit, range and flag is chosen; a heading never supplies a value that is not
printed on the row. Items the model proposed but no page could confirm are now counted in
the ingestion run's warnings and logged, instead of disappearing.

## Production check after #164–#166 (October 13)

Verified in both portals with the synthetic test patient and Elena Park: the critical
potassium alert sits under Alerts → Needs attention and leaves it when acknowledged; new
lab uploads quote whole printed rows; the recheck report (after #166) registers all seven
results including A1c; Nora's document answer carries the results card, which survives a
reload, and a general question gets none; the discharge draft was reviewed (glipizide
removed per the STOP line, lisinopril raised to the printed 20 mg, routes chosen, wording
checked in both languages) and published to Today. Three defects found there, fixed on
branch `fix/medication-evidence-and-draft-titles`:

- A medication's dose and action were cited from the first matching line on the page:
  Atorvastatin's "1 tablet" evidence quoted Metformin's "1 tablet by mouth twice daily".
  Every attribute after the name is now taken from the equally good copy nearest the
  name, preferring lines below it.
- Draft titles repeated the dose after a printed strength ("Atorvastatin 20 mg tablet
  1 tablet"); a name that already carries a strength is used alone.
- A report footer ("Discuss with your clinician before changing any medication") was
  extracted as a patient obligation, which queued a care-plan regeneration for a
  results-only report. The extraction prompt (`document-extraction/3`) now leaves report
  boilerplate out.

Follow-up found: asked for general sleep tips, Nora refused instead of giving
bounded general guidance. AI-006 now refines the coordinator/responder instructions;
actual provider behavior remains to be evaluated, not inferred from prompt edits.

## AI-006 follow-up implementation

1. Instructions distinguish mild/stable symptoms and low mood from deterioration,
   preserving deterministic safety floors and urgent medication-reaction rules.
2. The unused ingestion graph/test are removed; golden coverage now exercises the
   current extraction service and FHIR validator.
3. SOAP uses the model registry with explicit operational limits and no-note failure.

[Combined acceptance/rollout](demo-care-loop-followups.md) and [repeatable paired
evaluation](../../docs/demo-ai-evaluation.md) distinguish mocked/dry-run evidence
from outstanding real-provider and deployed acceptance. No measured improvement
in over-triage is claimed by these implementation changes.

## Acceptance

- Results, vitals and medication actions are extracted, grounded and shown to clinicians as
  above; the October 12 lab report yields every result with its printed flag.
- No stopped or held medication can be published as a Today activity.
- Explanations state only numbers present in the facts, in English and Spanish.
- No change to the care-plan eligibility rule and no automatic publication. Synthetic data
  only.
