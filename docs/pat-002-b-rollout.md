# PAT-002-B coordinated rollout

Prepared October 17, 2026. This is an operator procedure, not authorization or
proof of deployment. It changes no remote data until separately authorized.

## Exact additive change

The historical identity is `071_confirmed_symptom_handoff.sql`, SHA-256
`f690b788d5f29c3d7583f2fe8cc43b7a51a6af817c276d6839cc9c9ab2ded36b`. A read-only
hosted-ledger check records that exact file as applied on October 18. Preserve its
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

The October 17 read-only target probe found matching 059/060/065 entries and no
matching symptom-handoff entry. The later October 18 ledger evidence records the exact
071 handoff as applied. The process flags passed only in the explicitly supplied
preflight configuration; neither ledger result attests to deployed service
configuration.

## Release order

1. Verify the selected synthetic database ledger against the exact 071 filename and
   checksum above. If it already matches, run no SQL and do not rewrite the ledger. For a
   fresh or missing environment, obtain explicit authorization before applying the exact
   file. Use the team's ledger procedure, one transaction and advisory lock; insert its
   filename/checksum only on successful commit. Never print the connection string. Do not
   execute a locally modified migration runner that embeds credentials. Inspect its
   committed source or use a clean checkout.
2. Keep the existing approved `candidate-1` immutable. Review the exact paired
   `candidate-2` package and [review record](../backend/src/app/intake/question_library/candidate-2-review.md)
   before recording any approval or selecting it. New applicability and severity
   wording cannot inherit candidate-1 approval. Publish matching version/hash/
   actual approval metadata only with authorization for that eligibility write.
   Existing drafts keep their pinned version.
3. Authorize backend and portal deployment separately. Drain old backend
   instances/direct report writers: migration 060 blocks unconfirmed insertion.
   Do not restore automatic insertion to work around a disabled feature.
4. Start the intended runtime with `SYMPTOM_INTAKE_ENABLED=true` and
   `A2A_RETRY_WORKER_ENABLED=true`. The latter drives durable ADR and safety work.
   Run from `backend` in that runtime configuration:

   ```sh
   PYTHONPATH=src .venv/bin/python scripts/preflight_symptom_intake.py --check-target
   ```

   Require every result to pass. The default invocation without `--check-target`
   only validates the packaged library and prints required migration checksums.
   It neither contacts the target nor claims that a running service has the flags.
5. Follow the [acceptance journey](pat-002-b-acceptance-2026-10-17.md) in patient and
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


## Authorized synthetic application — October 18 continuation

The requester explicitly authorized only the exact 071 file above. It was applied
through the authenticated synthetic project's SQL editor in a guarded transaction;
the resulting ledger and read-only target preflight pass. The local backend now
runs intake and the existing retry worker. One patient-confirmed synthetic report
reached Elena's Symptoms and ADR workspace, with one completed task and one review
notice. No deployed service configuration or other remote migration changed.
Candidate-2 approval/activation remains pending. See the October 18 continuation
in the acceptance record for IDs and actual observations. New main's independent
071 filename does not authorize renaming this already applied file.


The October 18 Spanish browser journey also reached the assigned clinician with
unknown severity and an unlisted product retained only as testimony; cancellation
saved no report and a deliberate local backend outage recovered through reload/retry.
The portal now sends `microphone=(self)` so user-granted dictation can work; camera
and geolocation stay disabled. This needs the normal separately authorized portal
rollout. The requester elected to keep physical speech verification pending.
Candidate-2 remains inactive pending genuine review. The active candidate-1 can be
verified now using the steps in the acceptance record; do not describe the revised
candidate or physical microphone path as approved/verified.


The tested continuation is draft PR #193 on `fix/confirmed-intake-integration`.
Concurrent PR #159 now has overlapping ADR/MedWatch changes and a different 076
handoff migration. Choose/reconcile one delivery path before rollout. The exact
applied 071 contract in this document remains authoritative for this continuation;
no 076 execution or applied-file rename is authorized by the earlier 071 approval.


## October 18 requester verification update

The requester now reports the app, microphone and phone flows verified. Record
those as requester-reported manual acceptance; earlier pending notes are historical.
All 34 checks on implementation commit ca12c39 passed. PR #193 is being prepared
for peer/safety review without changes to its implementation or active library.
Candidate-2 remains inactive and pending genuine wording approval; no eligibility
write or service deployment is authorized by this verification report. Peer/safety
review and explicit merge/deployment authorization remain separate requirements.


## October 19 integration checkpoint

PR #159 has since merged into main. Main 5d46c30 contains the exact applied 071
handoff file and newer Nora worker/event migrations. PR #193 is now a follow-up
fix/verification change against that base; it does not replay the feature or
rename/remove any applied migration. The old 076 handoff draft is not an operator
instruction. Main's 076 activity-review migration is a different file and is not
applied by this task. Use the current documented worker rollout for worker flags;
this readiness work changes no external configuration. Retain the historical
October 18 manual verification provenance and record any new deployed check
separately. Candidate-2 is still inactive pending genuine wording review.
