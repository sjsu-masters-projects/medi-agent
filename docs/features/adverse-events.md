# Adverse drug event review and MedWatch draft

A supervised pharmacovigilance loop on synthetic data. An assigned clinician reviews a
suspected adverse drug event (ADR) with a Naranjo score, asks the patient what already
happened, records the judgment-only answers, and may prepare a Form FDA 3500 draft to
review, approve and download. MediAgent never files anything with the FDA.

## What it does (behaviour by role)

- **System.** A confirmed symptom report suggesting a medicine reaction yields one draft
  assessment per report (AI-extracted evidence, deterministic score); a re-run returns it.
- **Clinician queue** (`/adr-reviews`, case page, patient-record ADR tab): Awaiting review,
  Information requested, Reviewed, Dismissed. Evidence is labelled AI-extracted,
  Patient-confirmed, Clinician-entered or Other source. Actions: Request information (note
  plus 1 to 5 still-missing patient questions), Mark reviewed, Dismiss (note), Prepare
  MedWatch draft (rationale; also marks the case reviewed and cancels a pending request).
- **Clinician answers panel.** Yes, No or Not known for the five judgment questions; Yes and
  No need a basis (max 500). A recorded answer shows basis and points with Change answer; a
  replaced one moves under Earlier clinician answers, marked Replaced.
- **Patient** (`/chat?view=follow-up`, under Care team messages and Today, never in Nora)
  sees the care team's message and questions in the saved locale. Yes and No need a
  description (max 500); I am not sure needs none. Review, confirm, send. The request then
  reads as answered (own answers) or closed. No score or causality is ever shown.
- **Clinician MedWatch** (`/medwatch/[draftId]`): Complete (missing items first), Preview
  (real filled PDF, watermarked "DRAFT - not for submission"), Approve, Download. A draft, or
  an approved one with no recorded submission, can be discarded with a reason; the case
  returns to draft for review.

## Rules it must keep

1. Weights (`NARANJO_WEIGHTS`, yes/no): previous_reports +1/0; event_after_drug +2/-1;
   improved_on_dechallenge +1/0; reappeared_on_rechallenge +2/-1; alternative_causes -1/+2;
   reappeared_with_placebo -1/+1; toxic_drug_concentration +1/0; dose_response +1/0;
   similar_previous_reaction +1/0; objective_evidence +1/0; Not known 0. Definite 9+,
   Probable 5 to 8, Possible 1 to 4, Doubtful 0 or less. Only `score_naranjo` scores.
2. The patient answers event_after_drug, improved_on_dechallenge, reappeared_on_rechallenge,
   dose_response, similar_previous_reaction. The clinician records previous_reports,
   alternative_causes, reappeared_with_placebo, toxic_drug_concentration, objective_evidence.
   The sets partition all ten, enforced in models, services, the request check constraint and
   both database functions. A patient is never asked a clinician question. Patient prompts
   are retrospective and never say to start, stop, skip or change a medicine; the
   dechallenge prompt says so in both locales.
3. The score is decision support, not a clinician verdict, and is labelled so in the API,
   both portals and the MedWatch review panel. It is never written into a Form 3500 field.
4. Saving clinician answers does not review, dismiss, close or assign the case. Only Mark
   reviewed, Dismiss and Prepare draft end the review. (Request information stamps the
   acting reviewer and team but keeps the case a draft.)
5. Each save merges answers over stored ones, rescores, and appends one evidence entry per
   changed answer (`source: "clinician_entry"`, basis, recorder, team, time). Earlier entries
   stay; patient and extracted evidence are never rewritten. An answer already recorded with
   the same basis as the clinician's latest entry is skipped, so a retry adds no evidence or
   audit event. A new basis, or an answer so far from the patient, is recorded.
6. Concurrent patient and clinician saves cannot overwrite each other: both functions refuse
   a payload that no longer matches the locked row (SQLSTATE 40001). The backend rereads
   once, then returns 409 `ADR_ASSESSMENT_CHANGED` (clinician; staged answers kept) or "ADR
   follow-up is unavailable" (patient).
7. Only a clinician with an active care-team link acts: unassigned gets 403; another team's
   case and an unknown id get the same 404. A pending case is every team's safety item; once
   a team acts, only that team continues. A review or draft with no owning team (older
   records) is visible to no clinician until one active team takes it (409
   `RECORD_ALREADY_TAKEN`); a new one cannot commit without an owner. Several teams need `care_team_id`
   (`CARE_TEAM_REQUIRED`). A finished review gives 422. `anon` and `authenticated` cannot
   execute the review, response or answer functions. Errors never log or return PostgREST
   detail, which can echo patient text or the basis.
8. A patient answers every requested question once and confirms. Another patient's request
   and an unknown id give the same 404; a non-pending one gives 422 `ADR_REQUEST_CLOSED` and
   the form shows answered or closed, never a retry. One request is pending per assessment;
   a new request, Mark reviewed, Dismiss or Prepare draft cancels the old one. Cancelled
   requests and audit are kept.
9. Answering marks that request's notification read and creates no new patient event.
   Assigned clinicians get one History-only, no-email "Patient answered" alert with no
   clinical content.
10. Notification wording is fixed bilingual text keyed by question; raw keys, ids and
    clinician free text never appear. Stored symptom and medicine text is shown as recorded,
    labelled original wording. Clinician UI is English. Unsent patient answers are never
    written to browser storage. Patient save errors show class copy in the saved locale, never
    server text. The patient view carries the care-team emergency and not-continuously-
    monitored notice, never Nora's AI caution. Evidence takes the current response time only
    on an exact request match; no chronology is inferred.
11. A draft is Form FDA 3500 (not 3500A) filled from a vendored, SHA-256-pinned template in
    `backend/src/app/assets/fda/`, never fetched at runtime. A checksum, revision or
    field-name mismatch refuses export with 503 and records no `exported` event.
12. Prefill uses stored sources only; each filled field carries evidence attributed by the
    entry's own `source`. Reporter identity goes only in Section G. Unknown items stay blank (race, ethnicity, weight, reporter phone,
    address, occupation, B6 tests, sex for other genders). Section D abated and reappeared
    fill only from a yes or no Naranjo answer.
13. The A1 identifier defaults to initials plus 4 characters derived from the draft id,
    never a name, email, phone or birth date; a saved identifier matching them gets 422.
    Patient or clinician names in B5, B6, B7 or F give warnings that approval must
    acknowledge exactly; they are recorded in the audit. Matching ignores accents. A value
    outside the template's options, an event or report date after the save date, and a stop
    before its start get 422 naming the field path.
14. One gate, `approval_issues`, runs on the stored revision named by `expected_revision` and
    feeds the missing list, preview and approval. It needs A1, report type, confirmed event
    date, narrative, product 1 name, reporter first and last name, phone or email,
    health-professional answer, occupation and rationale; a death date if Death is ticked; an
    audited non-serious attestation if no outcome is ticked.
15. Approval records the attestation version (the clinician submits; MediAgent does not).
    Approved drafts cannot be edited; edits use optimistic revisions (stale gives 409);
    score and causality are locked.
16. Export needs an approved, non-discarded draft and writes an `exported` audit event
    (format; template revision and hash for PDF) before returning bytes. The PDF is fillable,
    adds no text to official fields, and its filename has `not-submitted` and no patient
    name. The preview PDF is never an export; it writes its own `preview_viewed` event.
    Preview and export responses are `no-store`; the JSON export carries
    `not_submitted_to_fda: true`.
17. Audit tables are append-only (no delete or truncate for `anon`, `authenticated`,
    `service_role`). The clinician-answers event holds questions, old and new answers and
    scores, never the basis. A patient's ADR requests, audit and drafts delete with the
    patient; clinician references stay `RESTRICT`.

18. The PDF is filled with pypdf, never PyMuPDF (AGPL), and both the AcroForm and XFA data
    are written because viewers disagree when only one is; it is not flattened. Past the
    pinned form's expiry the UI warns it may be superseded and export continues.
19. A discarded draft is kept with actor, time, reason and audit; at most one non-discarded
    draft exists per assessment. The case returns to review with one actionable clinician
    item, no actionable patient item and no email.

## Why it was built this way

- Questions are split by who can truthfully answer. Before, three patient questions capped a
  case at 4 (Possible) and the rest stayed unknown.
- The backend rescores and SQL verifies the payload under the row lock; locking alone was
  rejected because score logic would then live in two places.
- Each request is its own notification source (the assessment as source re-fired alerts).
  The preview is the real PDF, since a field table is not what the clinician sends.

## Excluded on purpose

- Transmitting a report to the FDA; Form 3500A; device reporting; Sections C and E.
- Submission recording (`/submission`, `/submission/amend`, `medwatch_external_submissions`,
  Submitted tab) exists but is out of scope. It stores the clinician's attestation that they
  submitted the approved form to the FDA themselves, outside MediAgent: date, method,
  optional FDA reference. It sends nothing and no code path contacts the FDA. Once recorded,
  the draft cannot be edited, approved or discarded; a correction is an audited amendment
  with a reason that keeps the original. The requester ruled it out as a gate and future
  commitment: do not extend it, test it as acceptance or treat it as filing.
- Changing weights, backfilling old cases, request expiry, automatic B6 lab prefill, and
  account deletion as an acceptance test.

## Where it lives

- Backend `backend/src/app/`: `pharmacovigilance/naranjo.py`, `models/adr.py`,
  `models/medwatch_form_3500.py`, `services/{clinician,patient,medwatch}_service.py`,
  `services/medwatch_3500/`, `services/notification_centre_presentation.py`,
  `routers/clinicians.py`, `routers/patients.py`. Migrations in `db/migrations/`: `042`
  auditable ADR, `046` to `048` ADR and MedWatch, `063`, `064`, `070`, `087`, `100`.
- Portals: `apps/patient-portal/src/components/features/adr-follow-up-*.tsx`;
  `apps/clinician-portal/src/app/(dashboard)/adr-reviews` and `medwatch`, and
  `src/components/features/` files `adr-*`, `medwatch-*`, `form-3500-*`.
- Tests: `backend/tests/unit/pharmacovigilance/`, `unit/services/test_medwatch_*.py`,
  `integration/test_adr_loop_postgres.py`, `test_adr_naranjo_answers_postgres.py`,
  `test_medwatch_3500_postgres.py`, and each portal's `src/__tests__/`.

## How to check it

Follow the PV-001-D section of [qa-handoff-2026-10.md](../qa-handoff-2026-10.md) (Elena
clinician, Morgan patient):

1. Elena requests all five patient questions; Morgan answers in en-US and es-MX.
2. Elena records the five clinical questions with a basis, saves again unchanged, then
   changes one. Pass: score follows the weights; the case stays open; a recorded answer shows
   Change answer; the unchanged save adds nothing; the old answer sits under Earlier answers.
3. Prepare a draft, fix the listed items, preview, approve, download. Pass: preview
   watermarked, download not; audit shows `preview_viewed`, `approved`, `exported`.
4. Discard an unsubmitted draft; the case returns to review.

Focused (from `backend/`, CI dummy Supabase env vars): `pytest tests/unit/pharmacovigilance
tests/unit/services/test_medwatch_service.py --no-cov -q`. PostgreSQL suites are opt-in and
split by fixture (see `backend/tests/TESTING_GUIDE.md`). Portals: `npm run lint`,
`typecheck`, `test`.

## Still open

- The inline PDF preview can look blank in some embedded browsers; recheck in Chrome and
  mobile ("Open in new tab" is the fallback).
- The queue filters client-side and caps at 200 cases; notification links still use the old
  `/medwatch?assessment=` redirect.
- The older patient endpoint `/patients/me/adr-information-requests` still returns the Naranjo
  score and causality (`ADRInformationRequestRead`); the portal never renders them, but the
  patient API should not carry them.
- Peer and safety review of the answer coverage; reassessment on new evidence beyond patient
  and clinician saves is not built.
