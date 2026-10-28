# PV-001-D Naranjo answer coverage

> **Status:** Verify deployed. Merged in [#227](https://github.com/sjsu-masters-projects/medi-agent/pull/227)
> (`16f11e2`, October 28, 2026) and deployed: backend revision `mediagent-backend-00195-ch2`, both portals built
> by Vercel. Migration `100_adr_naranjo_answer_coverage.sql` was applied to the hosted medi-agent-staging project
> by the requester on October 28 (ledger row 17:37:34 UTC), before the merge. Backend CI did not run on #227
> (see Verification); the live Elena and Morgan re-test and the peer review remain.
> **Owner:** Jeevan. **Parent:** PV-001 (Ganesh). **Tracker:** `.agent/TASKS.md` → PV-001-D.

## Problem

Live testing on October 27 (synthetic patient Morgan Ellis, clinician Elena Park) found that a
case's Naranjo score could not rise above 4 (Possible) through the product. Only three of the
ten questions could be asked of the patient (`reappeared_on_rechallenge`, `dose_response`,
`similar_previous_reaction`), worth at most +4 together. The patient was never asked
`event_after_drug` (+2) or `improved_on_dechallenge` (+1), although a patient can answer both
from what already happened. The five questions that need clinical judgment had no place to be
answered at all, so they stayed "do not know" (0) unless extraction filled them.

## Who answers which question

The scale's weights and classification bands are unchanged (Definite ≥9, Probable 5–8,
Possible 1–4, Doubtful ≤0). Only the route to an answer changes. The two sets partition all ten
questions and are defined once in `app.pharmacovigilance.models`.

| Answered by | Questions |
| --- | --- |
| Patient, through Request information (always retrospective) | `event_after_drug`, `improved_on_dechallenge`, `reappeared_on_rechallenge`, `dose_response`, `similar_previous_reaction` |
| Assigned clinician, through Clinician answers | `previous_reports`, `alternative_causes`, `reappeared_with_placebo`, `toxic_drug_concentration`, `objective_evidence` |

## Requirements

1. **Patient questions.** Request information offers all five patient questions. Every prompt
   asks about the past and never instructs the patient to start, stop, skip or change a medicine;
   the dechallenge prompt says so explicitly in both locales.
2. **Clinician answers.** An assigned clinician on the acting care team records Yes, No or Not
   known for any of the five clinician questions on a draft assessment. Yes and No need a basis
   of at most 500 characters; Not known needs none. Each question appears at most once per save,
   and the portal sends only the questions changed in that session.
3. **Boundary.** A clinician cannot record a patient question and a patient cannot be asked a
   clinician question. This is enforced in the request models, the service, the
   `adr_information_requests` check constraint, `private.review_adr_assessment` and
   `public.record_adr_clinician_answers`.
4. **Score.** Each save merges the new answers with the stored ones and recalculates the score
   with the existing deterministic `score_naranjo`. The score supports the clinician's review; it
   is not a verdict. Recording answers does not review, close or take ownership of the case.
5. **Evidence and audit.** Each save appends one evidence entry per changed answer (`source:
   "clinician_entry"`, basis, recorder, care team, time); earlier entries are kept. One
   `clinician_naranjo_answers_recorded` audit event records the questions, previous and new
   answers, previous and new score and causality. The basis text is not copied into the audit.
   An answer that is already recorded with the same basis as the clinician's latest entry is
   skipped, so a repeated or retried save adds no evidence and no audit event; when every answer
   in a save is unchanged the case is returned as it stands. The same answer with a new basis,
   or an answer that so far came only from the patient or extraction, is recorded.
6. **Concurrent saves.** Patient and clinician answers can arrive at the same time. Both database
   functions compare the payload with the locked row and refuse a stale one (SQLSTATE 40001).
   The backend rereads and retries once, then returns 409 `ADR_ASSESSMENT_CHANGED` to the
   clinician (the portal keeps the staged answers) or the existing "ADR follow-up is unavailable"
   error to the patient. Neither answer overwrites the other.
7. **Authorization and errors.** An unassigned clinician is refused (403). Another team's case
   and an unknown id are the same 404. A completed review is 422. A clinician on two teams
   must name one (`CARE_TEAM_REQUIRED`). Invalid answers are 422 without database detail. Browser
   roles (`anon`, `authenticated`) cannot execute the new function; the migration fails if they can.
8. **MedWatch.** Clinician-entered evidence is labelled "Clinician-entered Naranjo answer" in the
   Form 3500 draft. A patient `improved_on_dechallenge` answer now fills D "event abated" as a
   patient-confirmed answer.
9. **Locales.** New patient prompts and notification question wording exist in en-US and es-MX.
   The clinician panel is English, like the rest of the clinician portal.

## Interfaces

- `POST /api/v1/clinicians/me/adr-assessments/{id}/naranjo-answers` with
  `{answers: [{question, answer, basis?}], care_team_id?}`; returns the assessment's id, status,
  score, causality, answers, assessment, evidence and `updated_at`.
- Request information (`POST .../review` with `decision: "request_info"`) accepts up to five
  patient questions.
- Patient portal: two new follow-up questions in `adr-follow-up-copy.ts`.
- Clinician portal: Clinician answers panel on the ADR case (`adr-clinician-answers.tsx`); shared
  labels and question sets in `adr-questions.ts`; evidence shows "Clinician-entered". A recorded
  question shows its answer, its latest basis and its points, with Change answer; only questions
  not yet recorded, or being changed, show the Yes / No / Not known choice. In the evidence list a
  clinician answer replaced by a later clinician answer for the same question moves under
  "Earlier clinician answers (N)" with a Replaced label; every entry is kept and patient and
  extracted evidence is never regrouped.

## Rollout and rollback

Migration 100 must be applied to the hosted project **before** this backend is deployed. It was
applied on October 28 (requester, single-file apply through the filename/checksum ledger; the
migration's own check that browser roles cannot execute the new function passed inside the
transaction). Pending 098 and 099 were not touched. The
order matters in one direction only:

- New database, current backend: compatible. The current backend asks at most three questions,
  and the added stale-payload check passes for an unchanged row.
- Current database, new backend: Clinician answers returns 503 (the function is missing), and a
  request for one of the new patient questions is refused by the old check constraint.

Applying the migration, merging and deploying each need the requester's explicit
authorization. Rollback steps are in the migration header. No existing assessment is changed or
backfilled; its stored answers and evidence are untouched until someone answers again.

## Spanish wording

Eight new es-MX strings: six patient follow-up strings (label, prompt and evidence hint for each
new question) and two notification question strings. The requester accepted them on October 28
after the same model-assisted meaning-and-safety review as earlier passes (two wording
corrections were made first; see the
[wording evidence addendum](../../docs/evidence/spanish-interface-wording-2026-10-22.md#addendum-pv-001-d-naranjo-answer-coverage-october-28)).
The two notification strings are in the receipt-gated inventory (650 rows), so the receipt was
regenerated with the project's own `snapshot()` after the corrections; the six follow-up strings
sit outside the inventory and are not bound by the receipt. Not professional translation.

## Verification (local, October 28)

On #227 the frontend checks, CodeQL, the secret scan and the PR checklist passed. Every backend job, including
the new `adr-naranjo-answers` shard, was skipped because the dependency audit job fails (see SEC-004 in
`.agent/TASKS.md`), so the table below is the local record for the backend.

| Command | Result |
| --- | --- |
| `backend/.venv/bin/python backend/scripts/validate_migrations.py` | 116 migration files validated |
| `ruff check src/`, `ruff format --check src/` (backend) | Pass; 322 files formatted |
| `mypy src/` (backend) | No issues in 322 files (after installing the pinned `google-cloud-tasks==2.23.0` missing from the local environment) |
| `LC_ALL=en_US.UTF-8 PYTHONPATH=src pytest tests/` (backend) | 4,986 passed, 866 skipped, 1 failed: `test_voice_live` Spanish voice name, caused by a local `.env` override; passes 38/38 with the default |
| `CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER=1 NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER=1 pytest tests/integration -k postgres` | `test_adr_naranjo_answers_postgres.py` 14/14 pass. 318 passed and 70 failed in four notification-centre files (clinic memberships, clinic scheduling, MedWatch 3500, notification centre); the same four files pass 135/135 in their own session. See below |
| Patient portal `npm run lint`, `typecheck`, `test -- --run`, `build` | Pass; 1,009 tests in 92 files |
| Clinician portal `npm run lint`, `typecheck`, `test -- --run`, `build` | Pass; 834 tests in 87 files |
| `build_spanish_review_pack.py --check` | Pack matches its source snapshot |
| `build_spanish_review_pack.py --check --require-reviewed` | Pass (receipt renewed after the October 28 acceptance; 650 rows) |
| `node scripts/check-docs.mjs` | 0 link or fence errors |

The 70 combined-run failures come from running both PostgreSQL fixtures in one pytest session,
which CI never does. The notification-centre and care-team fixtures each register a global `sql`
fixture, and a test binds the one registered most recently when its file is collected. A
notification-centre suite collected after any care-team file therefore runs against the
whole-ledger database (tracebacks point at `care_team_plan_harness.py`, with errors such as
"relation clinic_memberships already exists"). This is not caused by this change: running only
unchanged files, `test_ai_availability_postgres.py test_care_team_followups_postgres.py
test_clinic_memberships_postgres.py`, reproduces the same failure, while each pair of files,
including the new suite with `test_clinic_memberships_postgres.py`, passes. CI runs each fixture
in its own shard, so the new suite has its own `adr-naranjo-answers` shard (minimum 14 cases),
and `backend/tests/TESTING_GUIDE.md` now says to keep the two groups in separate sessions.

## Remaining before Done

- Peer and safety review (PV-001 owner, Ganesh). Migration 100 is applied, the Spanish wording is accepted and
  the code is merged and deployed (October 28).
- Deployed acceptance: Elena requests all five patient questions for Morgan; Morgan answers in
  en-US and es-MX; Elena records clinician answers with a basis; the score, evidence attribution,
  audit row and MedWatch preview attribution match.

Out of scope: changing scale weights, extraction behavior, backfilling existing assessments, and
asking patients any clinician question.
