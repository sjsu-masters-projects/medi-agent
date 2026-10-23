# LOC-001 interface wording review

## Scope and acceptance

Requester decision, October 22: perform a model-assisted English/Mexican Spanish
meaning-and-safety review for the synthetic master's project. A separate fluent
professional reviewer is not required. This is not professional translation or
clinical validation.

Review every pair in the source-linked interface pack, including dynamic branches,
uncertainty, negation, timing, actor identity, privacy, clinical approval, saved
state, emergency guidance and voice/text fallback. Correct source copy where
meaning differs or controls become unclear. Retain placeholders and logic.

Record file-level results and exact source/pair fingerprints. An acceptance record
must become stale if reviewed text changes; regeneration must not silently carry
approval forward. Keep an accessible paired inventory and tests for that gate.

No stored clinical text, human messages, schedules, medications, history, approval
flags or database records are changed by this review. Care-plan bilingual wording
still needs its existing authorized in-app approval. Interface language acceptance
does not claim deployed/mobile/voice acceptance or an expo rehearsal.

Update TASKS.md and affected draft references only for the exact reviewed scope.
Run source-focused tests, generator freshness/staleness tests, lint, type checks
and documentation links. Deliver through a separate branch from merged #222.

## Outcome recorded October 22

The [dated review](../../docs/evidence/spanish-interface-wording-2026-10-22.md)
records a project-scope wording pass after corrections: 553 paired inventory at the first pass, 648 after later addenda
entries, representing 460 distinct source locations across 11 files. The
machine-checkable receipt binds acceptance to all source checksums and the
paired-entry fingerprint. A changed/missing receipt or snapshot fails CI's
`--require-reviewed` check; refreshing the inventory alone cannot approve text.

Nine English-only clinician title/description tuples were removed from the
original inventory. Clinician controls remain English. Patient actor identity,
privacy, original-conversation review, unsent/saved state, emergency guidance and
voice text fallback retain their boundaries. Corrections and review metadata
await this increment's merge; no hosted behavior or clinical record was changed.

Focused checks from `backend`, using only the repository's synthetic Supabase
test settings:

```sh
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/scripts/test_spanish_review_pack.py \
  tests/unit/services/test_notification_centre_presentation.py \
  tests/unit/services/test_appointment_calendar.py \
  tests/unit/services/test_email_service.py -q --no-cov
```

Result: 280 tests pass, including missing/stale acceptance, source/pair changes
and English-only tuple exclusion. From `apps/patient-portal`:

```sh
npx vitest run src/__tests__/interface-wording-review.test.ts \
  src/__tests__/symptom-history.test.tsx src/__tests__/care-team-today.test.tsx \
  src/__tests__/care-team-conditions-privacy.test.tsx \
  src/__tests__/care-team-upload-picker.test.tsx src/__tests__/visits-page.test.tsx
```

Result: 115 tests pass. The six new copy-contract tests preserve actor identity,
language-only presentation, names/date/version/count branches, timer values,
privacy, explicit approval and emergency/text-fallback wording.

Patient lint and type-check pass; clinician type-check also passes for the shared
copy module. Full backend mypy passes across 317 source files. Ruff/format and the
seven extraction/document-checker Node tests pass. The snapshot receipt and CI
YAML parse checks pass. These are local source checks, not a deployed journey.

Full patient suite: `npx vitest run --maxWorkers=2` passes all 989 tests in 91
files. The first run found one old Profile accessible-description expectation;
it was updated to require the reviewed display-language meaning, verified in
isolation, and the full suite was rerun successfully. No failure is suppressed.
