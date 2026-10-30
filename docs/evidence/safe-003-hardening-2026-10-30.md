# SAFE-003 safety gap hardening

October 30, 2026. The requester chose a separate follow-up PR for the
[review comment on #232](https://github.com/sjsu-masters-projects/medi-agent/pull/232#issuecomment-6532939812)
and explicitly kept unsupported-dose detection monitoring-only. Blocking remains
an open future decision. No clinical validation, peer approval or live acceptance
is claimed.

## Behavior and review

- Migration 103 accepts every deterministic floor rule during intake, derives its
  urgency and gives medication errors a distinct alert key from severity reviews.
  Its status-capture trigger derives the same key, avoiding a duplicate default
  emergency alert. Private draft answers never enter the alert. Existing applied
  migrations are unchanged.
- The floor event uses the verdict's urgency. Model/override escalations register
  rule, urgency and saved message links before terminal socket events, with one
  registration retry. Migration 104 reuses the existing pending alert queue and
  worker; delivery is idempotent and remains pending after an outage. Failure to
  register is reported uncertain, never delivered. Saved links are immutable and
  cross-patient/session links are rejected. Delivery retains the saved assistant
  intent rather than labelling every model escalation as a symptom.
- Patient ADR list and answer receipts omit score/causality at the response schema;
  the list service does not select those fields. Migration 106 also removes the
  legacy patient read policy on assessments; assigned-clinician policies remain.
- Failed fact batches log count and exception class only. Synthetic model-output
  validation errors and provider exceptions prove no text or traceback is logged.
- Migration 105 edits visits and appends field changes with actor in one transaction,
  rechecking lifecycle/access under locks. Grouped open slots share details; no-op
  saves add no audit. An audit failure rolls all edits back; browser roles cannot
  call the function or alter audit history.

## Verification

The separate worktree uses the original checkout's locked Python 3.12 environment.
Tests receive the same synthetic Supabase values as CI; no secret file was copied.
From its `backend` directory (substitute the existing venv executable):

```sh
DEEPGRAM_TTS_MODEL_ES=aura-2-estrella-es PYTHONPATH=src .venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check src/ scripts/
.venv/bin/ruff format --check src/ scripts/
.venv/bin/mypy src/ --ignore-missing-imports
.venv/bin/python scripts/validate_migrations.py
```

Full backend: **5,048 passed, 946 skipped, 91.08% coverage**. Ruff, mypy and all
122 migration parses pass. Default skips do not establish database acceptance.
The focused API/service run passed **259 tests** before the additional ADR response
boundary change; the full suite includes that change. Final review also rejects malformed
model-alert receipts rather than claiming persistence. After that small guard change,
`pytest tests/unit/services/test_chat_safety_service.py
tests/integration/routers/test_chat_api.py
tests/integration/routers/test_chat_emergency_copy.py --no-cov -q` passes **74 tests**,
including three new malformed-receipt cases. Full backend CI will exercise the final tree.

Patient: `npm run lint`, `npm run typecheck` and
`NODE_OPTIONS=--no-experimental-webstorage npm test -- --run adr-follow-up` pass
(six files, 102 tests). The portal change removes obsolete response type fields;
there is no visual change. Its full build is left to CI.

Repository root: `node scripts/check-docs.mjs --all` and
`python3 backend/scripts/build_spanish_review_pack.py --check --require-reviewed`
pass. No static bilingual pair changed or acceptance receipt was renewed.

The local PostgreSQL run uses only disposable Docker containers, with
`CHAT_SAFETY_TEST_POSTGRES=1 CHAT_SAFETY_TEST_POSTGRES_DOCKER=1
SYMPTOM_INTAKE_TEST_POSTGRES=1 NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER=1`:

```sh
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/integration/test_chat_safety_postgres.py \
  tests/integration/test_symptom_handoff_postgres.py \
  tests/integration/test_clinic_scheduling_postgres.py \
  tests/integration/test_adr_loop_postgres.py::test_patient_cannot_read_raw_adr_scores_but_assigned_clinician_can \
  --no-cov -q
```

Final combined database run: **84 passed, zero skipped**. Initial regressions caught the old status
capture trigger's default emergency row and corrected the medication-error subject.
They were fixed before the final run. An initial worktree test invocation lacked
synthetic configuration; the corrected runs use CI's synthetic values.

## Rollout limits

Migrations **103–106 are not remotely applied**. Apply them through the existing
ledger procedure only after explicit authorization for the exact target, before
merging/deploying dependent backend code. Keep the retry worker enabled. Safety/peer
review and synthetic deployed checks in both locales remain. No remote SQL,
deployment or merge was performed, and unrelated local files remain excluded.


## Final review and dependency follow-up

The fresh CI audit found newly reported pyasn1/pypdf advisories. The
[shared security patch](sec-004-pr233-ci-2026-10-30.md) updates just those versions,
passes the unchanged audit and reproduces both locks. Full backend under the patched
lock: **5,051 passed, 946 skipped, 91.08% coverage**; Ruff/mypy pass.

Final SQL review preserves the saved assistant intent in model notifications.
All eight model-alert PostgreSQL regressions passed again after that dispatcher
change (`test_chat_safety_postgres.py -k model_ --no-cov -q`, zero skipped).
The earlier 84-contract run covers the other authorization, intake and audit paths.
The replacement remote CI run will validate the complete final tree.
