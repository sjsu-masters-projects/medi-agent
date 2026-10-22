# Historical acceptance checkpoints, October 10 to 13, 2026

These checkpoints were moved out of the task board during documentation cleanup.
They preserve their original dates, counts and unchecked items. They are historical
observations, not the current task verdict. Later acceptance and scope changes in
[TASKS.md](../../.agent/TASKS.md) and the [deployed rechecks](deployed-recheck-2026-10-11.md)
take precedence. No requirement is closed or reopened by this move.

### LOC-001 acceptance

- [x] A draft from Spanish sources shows Spanish (from source) and English (AI translation) side by side; approval stays blocked until every item is checked in both languages.
- [x] A translation that changes a number, dose or medication name is discarded and leaves the item untranslated for retry or manual wording.
- [x] Approval projects both languages and the audit event records each item's source language and wording origin.
- [x] Today and Reminders render approved wording in the saved language with identical completion state; reminder scheduling is unchanged.
- [x] Older single-language items are labelled with their language instead of mixing silently.
- [x] Existing plans refreshed by review only: open draft translated, approved single-language plan re-drafted; no approved row edited.
- [x] Local checks (backend, PostgreSQL contract, both portals and builds) and synthetic-environment verification ([evidence](../../.agent/specs/loc-001-bilingual-approved-wording.md#verification--2026-10-10-synthetic-environment)).
- [x] Record titles: drafted per language from the existing summary/topics (no numbers, no patient name, bounded attempts); Records and clinician lists show them with the file name kept; missing column tolerated before migration 050.
- [x] Clinician patient detail shows approved English wording; reconciliation still compares source text.
- [x] Migration 050 applied (authorized); worker backfill titled 18/18 eligible documents; Records (English) and clinician Documents verified in the browser. Spanish titles verified in data, not yet through a saved-language switch.
- [x] #145 merged (`0cf4c93`); CI, backend Cloud Run and both Vercel production deployments succeeded.
- [x] Deployed: switch the patient's saved language in Profile and observe Today change ([deployed recheck](deployed-recheck-2026-10-11.md)).
- [x] Deployed: approve a new bilingual draft from the clinician portal. October 13, Elena Park approved the synthetic test patient's discharge draft after checking every item in English and Spanish and re-translating the changed lisinopril item ([deployed recheck](deployed-recheck-2026-10-11.md#ai-005-production-check-october-13)).
- Optional, not part of acceptance: clinician review of the second synthetic patient's bilingual V3 draft (a clinician decision).

### PAT-005-L acceptance

- [x] Saved es-MX updates Today chrome/actions/barriers and, since LOC-001, approved bilingual wording; reminder times stay unchanged ([deployed recheck](deployed-recheck-2026-10-11.md)).
- [x] The retained October 14 byte-identical synthetic copy displays skipped extraction in Rajeev's patient Records and Elena's clinician Documents/Review Queue; patient detail opens the original preview and download control, without a false empty-facts review.
- [x] Record these observations in the [deployed acceptance report](deployed-recheck-2026-10-11.md#task-verdicts), then close this slice.

#140 is deployed. No new migration/reset/publication needed. V4 is now active,
approved in both languages under LOC-001; V3 history is preserved.

### PV-001-B acceptance

- [x] Implementation and author-reported staging/local-branch acceptance in #136.
- [x] Resolve conflicts and integrate with current human/Nora separation and language controls (merged October 12).
- [x] Review and required CI; main CI and deployment succeeded for the merge.
- [x] Authorized rollout: migration 047 applied.
- [x] Patient answers → clinician evidence/score through the deployed portals (Hannah's synthetic en-US answer, October 18; [evidence](deployed-recheck-2026-10-11.md#task-verdicts)).
- [ ] Preserve patient attribution, unknown answers, prior clinician judgment and audit.

Three safe retrospective questions only: no medication experiments, new treatment
or MedWatch submission. Author records score 3 → 6 with three patient responses;
this is not independent canonical-app proof or full PV-001 completion.
### PV-001-C acceptance (PR 1)
Run on 2026-10-13 on branch `fix/adr-information-loop-gaps` (base `87a466d`, before the later merges of `main`), Python 3.12.11, Node 24.3.0 (CI uses Node 20), `uv` 0.9.24.
- [x] Backend, from `backend/`: `ruff check src/ scripts/` passed; `ruff format --check src/ scripts/` 256 files formatted; `ruff check` and `ruff format --check` on the 6 touched test files passed; `mypy src/ --ignore-missing-imports` no issues in 238 files; `scripts/check_production_placeholders.py` passed; `scripts/validate_migrations.py` validated 70 files and this PR adds none (`git status --short | grep -i '\.sql'` is empty).
- [x] Focused backend tests (not the full suite): presentation, patient service, clinician service, `tests/unit/db`, patient and clinician API routers, `--no-cov`: 246 passed.
- [x] Full backend suite as CI's coverage job runs it, without the Docker opt-ins: 2559 passed, 187 skipped (the opt-in PostgreSQL suites), 0 failed; coverage 88.47% against the 80% threshold.
- [x] Locks: recompiling both with CI's `uv pip compile` commands leaves `requirements.txt` and `requirements-dev.txt` byte-identical; `pip-audit==2.10.1 -r requirements-dev.txt`: no known vulnerabilities. The pin adds `pypdf==6.20.1` (2 lines per lock). CI's `git diff --exit-code` only proves this once the locks are committed.
- [x] Patient portal: `npm run lint`, `typecheck` clean; `npm run test` 64 files, 637 tests passed; `npm run build` succeeded.
- [x] Clinician portal: `npm run lint`, `typecheck` clean; `npm run test` 49 files, 368 tests passed; `npm run build` succeeded.
- [x] Token check: no hex literal or raw palette class in the changed ADR and MedWatch components; the MedWatch page keeps its two earlier disabled-state `text-[#94A3B8]` values.
- [x] Exhaustive-table tests (the repository has no property-testing library): wording 45,242 request sequences plus 22 non-list cases (Property 1), links 532 cases (2), copy parity 51 key paths per locale (3), error classification 5,414 cases (4), form 13 + 169 + 314 review-state combinations and 8 + 32 + 47 payload combinations (5), evidence provenance 312 lists (6).
- [x] Contrast: 65 text and background pairs on the changed surfaces computed from both apps' `globals.css`; all pass 4.5:1 except disabled controls, which are exempt. Two defects were fixed locally: the shared input placeholder (2.56:1) on the MedWatch preparation form, and three muted status lines on the page background (4.40:1) on the MedWatch page. No global token changed.
- [x] Docker suites, verified earlier and not rerun: notification centre 50 passed, email 31 passed, on the ledger through 058.
- [ ] Complete the full authenticated visual/accessibility matrix (patient 320, 360 and 430 px; clinician 1024, 1280 and 1536 px; keyboard, 200% zoom, reduced motion). Sampled deployed journeys do not establish that full matrix.
- [x] D9: requester accepted LLM-assisted en-US/es-MX meaning-and-safety review for the synthetic demo on October 19; professional translation validation is not claimed.
- [x] Before merge: `main` was merged into the branch twice (at `f143bf4` and `5e426d8`; only this tracker conflicted) and every check was rerun on the merged tree (see the PR 3 checkpoint).

### PV-001-C acceptance (PR 2)
Run on 2026-10-13 on branch `fix/adr-information-loop-gaps`, Python 3.12.11, Docker `postgres:16` (`--network=none`). 063 is applied only inside disposable local containers; no remote database was touched. Every backend command below ran from `backend/` with the unit-test variables `SUPABASE_URL=https://test.supabase.co SUPABASE_ANON_KEY=test-anon-key SUPABASE_SERVICE_ROLE_KEY=test-service-role-key SUPABASE_JWT_SECRET=test-jwt-secret-for-ci` (without them `tests/conftest.py` cannot import settings, so the V5 and V6 commands in requirements.md need them as V3 does).
- [x] Baseline first (V6, `NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER=1 ADR_LOOP_GAP_BASELINE=1 PYTHONPATH=src .venv/bin/pytest tests/integration/test_adr_loop_postgres.py --no-cov -v`, before 063 existed, reproduction tests only): 4 failed, 1 passed. G6 `test_answer_creates_no_new_patient_request_event`: 2 request events after the answer, not 1. G6 `test_answered_request_item_is_history`: the re-captured item is actionable and unread. G7 `test_one_patient_item_per_request`: the request adds `adr_information_requested` and `legacy_update`. **G9 `test_patient_deletion_after_answer_with_medwatch_draft`: `update or delete on table "patients" violates foreign key constraint "adr_assessment_audit_events_patient_actor_id_fkey"`, so the FK change ships (R12.6).** G10 `test_superseded_request_is_history` passed (the 054 newest-receipt rule); kept as a regression guard. Re-running the finished file on the baseline: 33 failed, 5 passed (the added contract tests assert 063 behaviour, such as request-sourced items, so they fail by design).
- [x] Fixed (V6 without `ADR_LOOP_GAP_BASELINE`): `test_adr_loop_postgres.py` 38 passed, covering R9 to R13 and Property 7 (14 operation sequences).
- [x] Regression (V6): notification centre 54 passed with 063 and 54 passed on the baseline; email 31 passed with 063 and 31 passed on the baseline. `test_adr_reviewed_questions_only_and_current_status` now finds the patient item by receipt ID instead of by assessment source, because after 063 the source is the request; the critical-result tests are unchanged and pass.
- [x] V1: `ruff check src/ scripts/` passed; `ruff format --check src/ scripts/` 266 files formatted; `ruff check` on the 4 touched test files passed; `ruff format --check` passes for 3 of them, and `test_notification_centre_postgres.py` would only reformat the critical-result tests that came from `main` (left unchanged).
- [x] V2: `mypy src/ --ignore-missing-imports` no issues in 247 files (includes PR 3 modules being written in the same working tree).
- [x] V3 (focused, not the full suite): presentation, patient service, clinician service, `tests/unit/db`, patient and clinician API routers, `--no-cov`: 322 passed.
- [x] V4: `scripts/validate_migrations.py` validated 75 files; the only migration this work adds is `063_adr_information_loop_lifecycle.sql` and no existing migration is edited (`git diff --name-only -- src/app/db/migrations` is empty).
- [x] V5: `tests/unit/db/test_adr_loop_gap_fixes_migration.py` 10 passed.
- [x] Presentation: request-sourced items link to `/chat?view=follow-up&request=<id>`, older items keep `assessment=<id>`; `adr_information_answered` copy and `/medwatch?assessment=<metadata assessment id>`; Property 2 extended to source types and clinician safety links. `test_notification_centre_presentation.py` 147 passed. Deviation: the answered alert has Spanish copy rather than repeating the English, because the existing template test requires every template to be bilingual; clinicians always see the English.
- [x] Requester applied 063 (then 064) on October 13 before #171 merged.
- [x] Deployed checks: both-language answers, clinician answered alert, exact audit and source labels verified. Disposable-account deletion is excluded from live acceptance by the requester October 20; automated safeguards remain.

### PV-001-C acceptance (PR 3)
Backend part, run on 2026-10-13 on branch `fix/adr-information-loop-gaps`, Python 3.12.11, Docker `postgres:16` (`--network=none`), with the four unit-test variables. 063 and 064 are applied only inside disposable local containers. The task 33 checkpoint below covers the whole branch, clinician portal included.
- [x] V4: `scripts/validate_migrations.py` validated 76 files; the only migration PR 3 adds is `064_medwatch_form_3500.sql`; no existing migration is edited.
- [x] V19: `tests/unit/db/test_medwatch_form_3500_migration.py` 13 passed.
- [x] V20: `tests/integration/test_medwatch_3500_postgres.py` 13 passed with 063 and 064 applied in ledger order (discard to review with one new actionable clinician `adr_review` event and no patient item or email, one non-discarded draft, the guard as `service_role`, append-only submissions, amendment, patient deletion, audit, 2-argument export delegation). `test_adr_loop_postgres.py` 38 passed with 063 and 064 applied (the 048 5-argument create still works).
- [x] Regression with 063 and 064 applied (after freeing local Docker space): notification centre 54 passed, email 31 passed, `test_adr_loop_postgres.py` 38 passed, `test_medwatch_3500_postgres.py` 13 passed; notification centre with `ADR_LOOP_GAP_BASELINE=1` 54 passed. The notification-centre fixture now removes its container with `--volumes`.
- [x] V1 `ruff check`/`format --check` on `src/ scripts/` (267 files) and the touched tests; V2 mypy no issues in 248 files; V17 focused 243 passed; full `tests/unit tests/integration/routers` plus middleware 3185 passed (`--no-cov`).
- [x] Task 33 checkpoint (after merging `main` at `5e426d8`): V1 ruff and format clean; V2 mypy no issues in 248 files; V4 76 files, the branch adds only 063 and 064 and edits no existing migration; V3a full backend suite 3293 passed, 242 skipped (Docker opt-ins), coverage gate met; V7 patient portal lint, typecheck, 667 tests and build; V8/V21 clinician portal lint, typecheck, 443 tests and build; V9 prints nothing; V16 lock diff 4 insertions (pypdf) and `pip-audit` found no known vulnerabilities; the PDF read-back corpus (35 synthetic drafts) re-reads every mapped field, XFA, `/P` -1084 and the empty user password.
- [x] V24: requester applied 063 then 064 on October 13 (both self-checks passed), then merged #171 (`13051d8`), deployed as `mediagent-backend-00143`.
- [ ] Requester: V12 authenticated screens, V13 Spanish review, V22 open a downloaded synthetic PDF in Acrobat Reader and macOS Preview.
