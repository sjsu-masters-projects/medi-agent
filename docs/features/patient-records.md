# Patient records, imports and review

How a patient's documents and imported external records become reviewed clinical
information. Patients read and upload records; assigned clinicians review candidates,
reconcile them with the local chart and ask the patient to confirm medicines.

## What it does

- **Patient Records:** documents with the recorded source-review status in words, an AI
  explanation in the saved locale (short opening, readable bullets, supplied questions
  kept apart), read-aloud, a source viewer, Refresh and upload. Processing documents are
  watched and announced when done. A patient can remove their own pending, unused upload;
  otherwise the record offers a message to the care team. Clinician medicine questions
  appear on Today.
- **Document pipeline:** upload queues work; a Cloud Run Job reads embedded text or OCRs
  scans (English, Spanish), anchors each candidate to a page and exact excerpt, and stores
  candidate facts. The HTTP service never does OCR or model work in a request.
- **Clinician review:** the patient's External records tab lists pending candidates
  (document and SMART) with mapped fields, source, version and uncertainty; raw FHIR JSON
  only behind "Source". A reconcile modal compares a candidate with the matched local
  record, an optional public medication reference and the patient's answer. Alerts and the
  upload review queue list the work. A bounded Timeline tab and a clinical-core FHIR
  download give context.
- **SMART sandbox:** `/smart-import` launches the public SMART Health IT R4 sandbox (EHR
  or standalone) and imports a bounded synthetic record as pending candidates.

## Rules it must keep

1. **Imports are candidates.** Document and SMART data start `pending_review` with
   resource-level provenance ([clinical facts](../clinical-facts-provenance.md)) and never
   overwrite approved medications, conditions or allergies. Only an assigned clinician's
   explicit, audited, atomic decision can: add, update selected non-empty fields, keep
   existing, defer or reject. Demographics never update the profile; other resource types
   are evidence-only. A reconciled candidate is immutable; a newer source version makes a
   new pending one. Medication updates keep the medication ID (reminders, adherence and
   ADR links hold); imports never create reminders.
2. **Identity is explicit.** An issuer plus external patient ID must be bound to one local
   patient by a clinician before candidates can affect local truth. A SMART token is not a
   local credential and bypasses no care-team check.
3. **Grounded or nothing.** A document candidate needs one page, an exact excerpt found on
   it and bounded confidence. Ungrounded output is kept as `needs_evidence_review`, a
   text-less scan as `needs_ocr`, both with no candidate. Uploads dedupe by content hash.
   Originals, storage keys, source IDs, excerpts and audit history are never altered; no
   mapper backfill.
4. **Evidence is not a conclusion.** Exact "no known allergies" statements stay evidence.
   Source differences are review flags, not equivalence or safety claims; interaction
   coverage is shown as unchecked. A free-text product without a canonical link creates no
   medication, ADR or Naranjo score.
5. **Public references on demand.** Only on an explicit click, only the drug name, after
   assignment, patient and fact checks; at most three DailyMed or MedlinePlus items with
   dates; never applied automatically.
6. **Unlisted-product alert** (079): only for an explicitly answered concern with a name
   and no unique canonical link. Acknowledging means seen, not resolved or a confirmed ADR.
7. **Patient confirmation** (093, 099). A clinician on an active link asks one question
   about one pending medication fact; the patient answers Yes, No I stopped, It changed
   (note required, 500 characters) or Not sure. The answer is testimony: it writes to no
   medication, fact, plan or reminder; the clinician decides via the usual decision.
   Idempotent by client ID, one open ask per fact and link, ten open per patient, one
   answer each (a different second answer is 409), 14-day expiry on the database clock,
   append-only audit. Unauthorized access returns not found. The alert event carries only
   the clinician name and care team.
8. **Source review in words.** Pending, approved and rejected describe the uploaded
   source, never treatment approval. A clinician upload is an origin, not a review;
   missing is unknown; completed parsing is neutral. Explanations are labelled
   AI-generated and the care-plan boundary stays after them.
9. **Explanations are derivatives.** The request path never generates a summary (the
   worker does). A structured presentation (`structured: true`) is built in the saved
   locale from the stored summary, with at most two attempts, and must keep numbers, units
   and negation; wrong-language, malformed or changed output is refused, never replaced by
   stale text. Cached by document, locale, summary fingerprint and version (102) after an
   ownership check; failures are not cached. Pending or failed presentations never reach
   speech or document chat; late responses after a document, locale or account change are
   dropped; playback stops on close.
10. **Patient removal fails closed** (101). Only the patient's own upload with pending
    review, no clinician decision or note, no use in medications, plans, obligations or
    visits, no shared storage object and no active processing, with only untouched
    candidates. Rechecked under the evidence fence and document lock; candidates and
    metadata go atomically with a minimal audit; storage cleanup is best effort after;
    replay is idempotent; a refusal changes nothing. Other cases draft a message the
    patient must address and send; nothing sends or withdraws automatically.
11. **SMART flow.** OAuth code with PKCE (S256); allowlisted issuer; state, verifier,
    scopes and issuer bound to one single-use session (10 min); verifier and launch handle
    encrypted; read-only patient scopes. The callback refuses provider errors, bad or
    replayed state, wrong audience and missing scope; error text is sanitized (200
    characters). The browser gets only a single-use five-minute ticket, never a token. A
    local clinician session and an assigned patient are required.
12. **Bounded, atomic import.** At most 20 pages per query, 50 requests, 2 MiB per
    response, 8 MiB and 1,000 resources per import, Bundle depth 8; next links stay on the
    trusted issuer. A breach fails before anything is saved; nothing is truncated.
    Supported: Patient, Encounter, Condition, AllergyIntolerance, MedicationRequest,
    MedicationStatement, Observation, DiagnosticReport, Procedure, CarePlan,
    DocumentReference, Bundle; others become warnings. Dedup key is issuer, type, ID and
    version (or content hash). Raw JSON and identifiers are stored verbatim.
13. **FHIR download is canonical-only.** Active medicines (MedicationStatement, never
    MedicationRequest), visible Conditions and Allergies, a minimal Patient. It re-checks
    assignment and sensitive-condition visibility each call, validates before returning (no
    partial file), is `no-store`, and re-imports as candidates only.
14. **Withdrawal and re-projection.** An untouched pending import can be removed; after
    any decision or re-projection it is kept as withdrawn evidence. Re-projection touches
    only untouched pending candidates, needs a reviewed dry-run hash, matching source
    version and an assigned clinician, and appends a revision.
15. **Bounded, honest context.** The timeline checks assignment first: twelve buckets, at
    most 40 newest dated rows each, messages only from the actor's ten most recent own
    threads and without text, no invented dates, gaps reported, not an audit trail. The
    external-record workload reads assigned patients' pending candidates ten patients per
    page (200 candidates, 20 citations), excludes rejected, withdrawn, uncited and private
    sources, and keeps counts separate from unread counts.
16. **Motion never carries meaning.** Reduced motion keeps the status text; no safety
    wording is animation-gated.

## Why it was built this way

- Provenance first: a fluent extraction is not evidence, so a reviewer can always check
  a candidate against its page and excerpt.
- One reconciliation path for documents, SMART and patient answers; evidence-only types
  stay out of canonical tables. Rejected: automatic approval, patient deletion of reviewed
  records, a combined patient/clinician/document/FHIR comparison matrix.
- The worker is bounded (one task, five documents, 2 GiB, 30 minutes).

## Excluded on purpose

Production EHR connectivity and real PHI; FHIR conformance certification; refresh or
offline tokens; Practitioner, Organization and CareTeam import; generating orders;
interaction or equivalence checking; permanent clinician deletion; email or push for the
patient question.

## Where it lives

- Backend `backend/src/app/`: `routers/` `documents.py`, `smart.py`, `clinicians.py`,
  `medication_confirmations.py`; `services/` `document_*`, `ingestion_service.py`,
  `document_intelligence/`, `fhir_*`, `smart_launch_service.py`, `clinical_fact_service.py`,
  `clinical_reconciliation_service.py`, `external_record_review_service.py`,
  `external_patient_binding_service.py`, `medication_confirmation_service.py`,
  `medication_reference_service.py`, `patient_timeline_service.py`;
  `workers/document_ingestion.py`.
- Migrations `018`, `029` to `032`, `034` to `037`, `079`, `093`, `099`, `101`, `102`.
  See [ingestion worker](../document-ingestion-worker.md) and
  [SMART review mapping](../smart-fhir-review-mapping.md).
- Patient portal: `app/(app)/records/page.tsx`, `components/features/` `record-*`,
  `document-source-viewer`, `hooks/use-document-explanation.ts`.
- Clinician portal: `app/(dashboard)/smart-import/page.tsx`, `components/features/`
  `smart-import-review-panel`, `external-record-reviews`, `patient-timeline`,
  `medication-confirmation-request`.
- Tests: `backend/tests/integration/test_{reconciliation,patient_document_removal,
  patient_timeline,medication_confirmations,unlisted_product_review}_postgres.py`,
  `tests/unit/services/test_fhir_*.py`, `routers/test_smart_api.py`; portal `record-*`,
  `smart-import-*`, `external-record-reviews`, `patient-timeline` tests.

## How to check it

1. [QA handoff](../qa-handoff-2026-10.md) section 3.8 (records, FHIR, SMART) including its
   REC-001 patient Records checks, and section 3.5 for patient confirmation.
2. Upload a synthetic file, watch it process, open its explanation in both locales
   (reopening makes no new model call), remove it; a reviewed document must refuse.
3. As the assigned clinician choose Keep existing on a candidate: one audit row, approved
   medicines and reminders unchanged. Download the FHIR file and re-import: pending only.
4. Run a SMART sandbox launch; standalone must reach the sandbox patient login.
5. `cd backend && PYTHONPATH=src python -m pytest tests -k "fhir or smart or reconcil
   or document or timeline or medication_confirmation" -q`; `npm run test` per portal.

## Still open

- Standalone SMART: one recorded run past sandbox login and consent into review hand-off.
- ID token validation (signature, issuer, audience, nonce, expiry) is not built: no
  `openid` scope is requested and the stored nonce is never checked. Needed before any
  scope that returns an ID token is added.
- SMART conformance: no Inferno run or R4 sandbox profile check; only installed R4B models.
- A clinician list of all open medicine questions, and clinician cancel of a question.
