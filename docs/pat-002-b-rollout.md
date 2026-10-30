# PAT-002-B coordinated rollout

This is an operator procedure, not authorization or proof of deployment. It changes no
remote data until separately authorized. Current status is on the
[task board](../.agent/TASKS.md). Past applications and acceptance are in the
[operating-guide receipts](evidence/operating-guide-receipts-2026-10.md#symptom-intake-pat-002-b).

## Exact additive change

The historical identity is `071_confirmed_symptom_handoff.sql`, SHA-256
`f690b788d5f29c3d7583f2fe8cc43b7a51a6af817c276d6839cc9c9ab2ded36b`. Preserve its
filename and bytes; do not rename, replay or insert a second ledger identity for it.
Applied `059_chat_safety_alerts.sql` and `060_confirmed_symptom_intake.sql` must likewise
keep their filenames and checksums. Migration 065 clinic memberships is also required.
In a fresh or explicitly authorized environment where the exact 071 handoff is missing,
apply only that exact file after verifying the ledger. Do not run a catch-all migration
command that could apply unrelated pending SQL.

The 071 handoff makes confirmation atomically queue the existing ADR screen, preserve a
patient-named product without adding medication, notify active assigned clinic
members and retain independent urgent/emergency notices. It adds a service-only,
read-only readiness probe. It does not backfill old reports, approve a library,
reset/seed data or implement ADR follow-up.

## Release order

1. Verify the selected synthetic database ledger against the exact 071 filename and
   checksum above. If it already matches, run no SQL and do not rewrite the ledger. For a
   fresh or missing environment, obtain explicit authorization before applying the exact
   file. Use the team's ledger procedure, one transaction and advisory lock; insert its
   filename/checksum only on successful commit. Never print the connection string. Do not
   execute a locally modified migration runner that embeds credentials. Inspect its
   committed source or use a clean checkout.
2. Follow the [question release process](../backend/src/app/intake/question_library/README.md).
   Publish the active version with `scripts/publish_symptom_questions.py` only with
   authorization for that eligibility write. Existing drafts keep their pinned version.
3. Authorize backend and portal deployment separately. Drain old backend
   instances/direct report writers: migration 060 blocks unconfirmed insertion.
   Do not restore automatic insertion to work around a disabled feature.
4. Start the intended runtime with `SYMPTOM_INTAKE_ENABLED=true` and
   `A2A_RETRY_WORKER_ENABLED=true`. The latter drives durable ADR and safety work.
   Set the intake flag on both the API and the chat worker: Nora intake runs in both.
   Do not alter other flags, images or SQL as part of activation.
   Run from `backend` in that runtime configuration:

   ```sh
   PYTHONPATH=src .venv/bin/python scripts/preflight_symptom_intake.py --check-target
   ```

   Require every result to pass. The default invocation without `--check-target`
   only validates the packaged library and prints required migration checksums.
   It neither contacts the target nor claims that a running service has the flags.
5. Follow the [acceptance journey](evidence/pat-002-b-acceptance-2026-10-17.md) in patient and
   assigned clinician portals. Confirm one report, one durable task, one notice,
   owned visibility, refresh recovery and the existing ADR draft for an exact
   active-list product. Exercise both languages and actual microphone playback/
   dictation. Automated STT/TTS event mocks are not physical microphone evidence.
6. Review CI and peer findings, then obtain explicit merge/deployment authorization.
   A green test run is not clinical approval or deployed acceptance.

## Pause and recovery

If preflight fails, leave intake unavailable with its truthful no-report-saved
response. Preserve private drafts, immutable reports and queued work. Disable the
intake flag to pause new ordinary intake; keep safety alert delivery operational.
Do not roll back by dropping guards or restoring unconfirmed writers. Fix forward
with an additive migration if SQL changes are needed. Inspect retry/dead-letter
state through the existing operational path; never fabricate successful processing.

## Question library state

v2 is the active release and v1 stays available for pinned drafts and reports. The
[question release process](../backend/src/app/intake/question_library/README.md) records each
release and its approval. A passing test or a SQL change does not approve a question bundle.
