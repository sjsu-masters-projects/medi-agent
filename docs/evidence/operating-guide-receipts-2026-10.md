# Operating-guide receipts, October 2026

These dated notes were moved out of the operating guides on October 30, 2026, so the
guides read as procedures. The Supabase sections are condensed from the setup guide; the
others keep their original wording apart from nested headings and one removed hosted-project
reference. They record what was observed or reported at the time.
They are not instructions and not the current verdict: use
[TASKS.md](../../.agent/TASKS.md) for status and each guide for the procedure. The hosted
migration ledger, not this page, is authoritative for what is applied.

## Supabase Auth and email

Initial dashboard inspection on October 11 found Confirm email **off** and custom SMTP
**off** in the synthetic staging project. After operator setup, a dashboard reload confirmed
SMTP **on**, Resend host/port and a stored hidden password. This verifies saved
configuration, not delivery. With explicit requester approval, Site URL was set to
`https://app.mediagent.live` and the three exact deployed reset destinations were added.
Reload confirmed they persisted. No wildcard redirects or signup-confirmation changes were
made.

`057_email_delivery.sql` and `058_email_delivery_fixes.sql` were applied to the synthetic
project. The Reset password template `docs/email-templates/supabase-password-recovery.html`
was installed October 12.

## Migration application reports

| Migration | Reported application | Provenance |
| --- | --- | --- |
| Through `075_notification_zone_lookup.sql` | October 18, 2026 | Recorded as applied by the requester |
| `071_confirmed_symptom_handoff.sql` and `076_care_conversation_activity_review.sql` | 071 on October 18 | A read-only October 19 ledger check recorded both; application of 077/078 was not checked then |
| `063_adr_information_loop_lifecycle.sql`, `064_medwatch_form_3500.sql` | October 13 | Applied to the hosted project by the requester, before the backend that calls 064 objects deployed |
| `065_clinic_memberships.sql` | October 16 | Applied by the requester before #176 merged |
| `066_clinic_sign_in_once.sql` | October 16 | Applied by the requester before #178 merged |
| `067_clinic_lists_and_roles.sql`, `067_english_display_facts.sql`, `068_message_translations.sql`, `069_clinic_scheduling_and_tags.sql` | October 17 | Applied by the requester. 068 was fixed in #183. 069's backfill tagged 38 appointments in the hosted project. A read-only audit on October 17 found no public table with RLS off and no browser-role SELECT or INSERT on a public table. |
| `080`, `081`, `082`, `088` | October 22 | Operator receipt: the requester supplied successful `COMMIT` and ledger inserts, followed by `Migration ledger is synchronized`. Care-team 083–087 were already applied and skipped. This records the supplied output, not an independent hosted checksum/security audit. #203 merged as `dace6a8d` afterward. |
| `101_patient_document_removal.sql`, `102_document_explanation_presentations.sql` | October 29 | Requester report; target and ledger/checksum receipt not supplied |

Later reports for other migrations are on the relevant [task-board](../../.agent/TASKS.md) rows.

PR #203's proposed 079/083 English-display copies were byte-identical to the applied
`067_english_display_facts.sql` and redundant, so they were removed rather than creating
another ledger identity. Main's 079 remains the applied unlisted-product migration. #203
reserved 080–082 and 088; merged care-team PR #210 owns 083–087.

## Symptom intake (PAT-002-B)

### Safety checkpoint

Private drafts, explicit report confirmation and revoked browser report writes
remained later work at the B2 checkpoint. Migration 027's service-role SELECT grant does
not remove the old owner INSERT policy. No remote migration, seed/reset, deployment, review
or PR #136 migration was authorized or claimed by that checkpoint.

### October 12 rollout recheck

On October 12 the requester reported Ganesh approved the unchanged paired-locale candidate;
the [approval record](../../backend/src/app/intake/question_library/v1-review.md#requester-reported-approval)
states its provenance, date and canonical hash. This is not a formal PR approval.

The requester reported applying the migrations. Read-only `schema_migrations` queries
confirmed both 059/060 ledger entries match the versioned file checksums. The confirmation
column is available and the intake RPC rejects an unknown patient with `42501`. After the
dated approval report, the manifest selected `candidate-1`, matching eligibility metadata
were published via `set_symptom_question_eligibility`, and the local backend was restarted
with `SYMPTOM_INTAKE_ENABLED=true`. An authenticated fictional patient confirmation and
assigned-clinician summary then passed locally, as recorded in the
[acceptance evidence](pat-002-b-acceptance-2026-10-12.md#approved-library-local-acceptance--october-12).
The deployed backend setting and deployed acceptance remained separate.

### October 17 target probe

The October 17 read-only target probe found matching 059/060/065 entries and no
matching symptom-handoff entry. The later October 18 ledger evidence records the exact
071 handoff as applied. The process flags passed only in the explicitly supplied
preflight configuration; neither ledger result attests to deployed service
configuration.

#### Authorized synthetic application — October 18 continuation

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
The stored `candidate-1` release was active at this point; the next release, v2, went live
later under the [question release process](../../backend/src/app/intake/question_library/README.md).
Do not describe the physical microphone path as verified.


The tested continuation is draft PR #193 on `fix/confirmed-intake-integration`.
Concurrent PR #159 now has overlapping ADR/MedWatch changes and a different 076
handoff migration. Choose/reconcile one delivery path before rollout. The exact
applied 071 contract in this document remains authoritative for this continuation;
no 076 execution or applied-file rename is authorized by the earlier 071 approval.


#### October 18 requester verification update

The requester now reports the app, microphone and phone flows verified. Record
those as requester-reported manual acceptance; earlier pending notes are historical.
All 34 checks on implementation commit ca12c39 passed. PR #193 is being prepared
for peer/safety review without changes to its implementation or active library.
Candidate-2 remains inactive and pending genuine wording approval; no eligibility
write or service deployment is authorized by this verification report. Peer/safety
review and explicit merge/deployment authorization remain separate requirements.


#### October 19 integration checkpoint

PR #159 has since merged into main. Main 5d46c30 contains the exact applied 071
handoff file and newer Nora worker/event migrations. PR #193 is now a follow-up
fix/verification change against that base; it does not replay the feature or
rename/remove any applied migration. The old 076 handoff draft is not an operator
instruction. Main's 076 activity-review migration is a different file and is not
applied by this task. Use the current documented worker rollout for worker flags;
this readiness work changes no external configuration. Retain the historical
October 18 manual verification provenance and record any new deployed check
separately. Candidate-2 is still inactive pending genuine wording review.

#### October 19 authorized activation checkpoint

Candidate-1, exact migration checksums, trigger and browser-write restrictions
passed read-only preflight. The requester authorized only the intake flag update:
backend revision `mediagent-backend-00172-vp5` and chat-worker revision
`mediagent-chat-worker-00015-65j` now set `SYMPTOM_INTAKE_ENABLED=true`.
Both services need the flag: Nora intake executes in the chat worker as well as
the API. Do not alter other flags, images or SQL as part of activation.
Morgan's confirmation reached Elena's exact review case, but revealed duplicate
handoff keys (DV-015). PR #202's canonical-key reuse fix needs merge/deployment
and a new single-task confirmation check. Candidate-2 remains unapproved.

#### October 20 post-202 acceptance

#202 merged/deployed automatically; backend `00173-t5q` and worker `00016-29q`
serve the updated code. Morgan's Spanish typed/mobile confirmation produced one
canonical completed task and one exact clinician ADR draft, unlike the preserved
pre-fix duplicate history. Saved region wording/reload and unchecked consent pass.
See [live evidence](deployed-recheck-2026-10-11.md#october-20--post-202-live-acceptance).
Physical voice, forced outage and wider mobile/accessibility checks remain.

## Patient-upload review gate (PAT-005-R)

### Verification update

Backend service/router suite: `pytest tests/unit/services
tests/integration/routers --no-cov -q` — **1,034 passed**. Focused Spanish
cadence/feed suite: **98 passed**. Ruff passed for cadence source/tests; mypy
passed for four changed service files. Clinician suite: **223 passed**, with
typecheck, focused ESLint and webpack production build passing. All **65 real
PostgreSQL tests passed** against isolated PostgreSQL 16 containers; migration
validation accepted 56 SQL files. These local checks do not prove deployed
behavior. No remote migration or deployment performed.

Parallel database review finalized patient-scoped evidence fencing, atomic
generation/publication eligibility rechecks and serialized queue creation. It
filters null patient IDs inside every lineage-discovery loop and adds a bounded
insert/delete regression. Static validation passed for 56 migrations and seven
PL/pgSQL bodies; Ruff, formatting and diff checks passed. Native initdb failed
with macOS shared-memory exhaustion. The opt-in Docker fixture bypassed that
host limitation without changing kernel settings: **65 passed, 3 warnings in
227.76 seconds**. A fixture that accidentally created two open drafts for one
patient was corrected to use a second synthetic patient; the full suite then
passed. No product constraint was weakened.

Reproduce from `backend/` using synthetic CI settings:

```sh
CARE_PLAN_TEST_POSTGRES=1 CARE_PLAN_TEST_POSTGRES_DOCKER=1 PYTHONPATH=src \
  .venv/bin/pytest tests/integration/test_care_plan_postgres.py --no-cov -q -x
```

Docker mode requires an already available official `postgres:16` image. Each
test creates and removes its own network-isolated container, without host
ports, volumes or connection to Supabase.

### Authorized staging application — October 10

The requester separately authorized only
`048_patient_upload_care_plan_review_gate.sql` for the synthetic
staging project. It committed at `2026-10-10 16:18:01.436642+00`
through the advisory-lock and filename/checksum-ledger protocol. Recorded SHA-256:
`2e07f7ef955b0002a3b158f4dae6cc0fe1f0039ec5795f5559d13abac3e0d375`.
Eight read-only checks passed: checksum, six evidence fences, publication/queue
guards, service-role-only public RPCs, invoker-security helpers, pending-evidence
exclusion, unchanged approved V2 and unchanged draft V3. No plan approval or
history rewrite occurred. Backend/UI deployment and live Spanish/non-scheduled-day
acceptance are recorded in [the PAT-005 final acceptance](pat-005-final-acceptance-2026-10-10.md)
(V3 Spanish, Saturday absence; #140 deployed); this is not a production-readiness claim.

October 10 inline-review cleanup extracts the intentional Docker readiness
command from the subprocess argument list, without changing its value or
database behavior. Ruff lint/format and all 65 isolated PostgreSQL tests passed
again (233.36 seconds). No migration change or remote operation was performed.

## Repeatable AI evaluation (AI-006)

### Local verification — October 17, 2026

Final commands and outcomes are recorded below. These are local synthetic checks,
not real-provider or deployed evidence. No credentials or remote operations were
used.

From `backend`:

```bash
PYTHONPATH=src .venv/bin/pytest tests/unit/services/test_soap_note_service.py tests/unit/services/test_demo_evaluation.py tests/unit/adk/test_registry.py tests/unit/adk/test_background_generation.py tests/unit/services/test_ai_evaluation.py tests/unit/services/test_ai_evaluation_fairness.py tests/unit/scripts/test_run_ai_eval_script.py tests/unit/adk/test_chat_runtime.py tests/unit/safety/ tests/unit/adk/test_safety_floor_plugin.py tests/unit/adk/test_care_coordinator.py tests/unit/test_config.py tests/integration/test_golden_set.py tests/unit/agents/test_ingestion_prompt_contract.py tests/unit/services/test_ingestion_candidate_provenance.py tests/unit/services/test_ingestion_translation_scope.py tests/unit/workers/test_document_ingestion_worker.py tests/unit/followup/test_symptom_service.py --no-cov -q
.venv/bin/ruff check src/app/adk/agents/care_coordinator/prompts.py src/app/adk/registry.py src/app/config.py src/app/services/soap_note_service.py src/app/services/ai_evaluation.py src/app/services/demo_evaluation.py scripts/run_ai_eval.py tests/unit/services/test_soap_note_service.py tests/unit/services/test_demo_evaluation.py tests/unit/adk/test_registry.py tests/unit/scripts/test_run_ai_eval_script.py tests/integration/test_golden_set.py
.venv/bin/ruff format --check src/app/adk/agents/care_coordinator/prompts.py src/app/adk/registry.py src/app/config.py src/app/services/soap_note_service.py src/app/services/ai_evaluation.py src/app/services/demo_evaluation.py scripts/run_ai_eval.py tests/unit/services/test_soap_note_service.py tests/unit/services/test_demo_evaluation.py tests/unit/adk/test_registry.py tests/unit/scripts/test_run_ai_eval_script.py tests/integration/test_golden_set.py
.venv/bin/mypy src/app/adk/agents/care_coordinator/prompts.py src/app/adk/registry.py src/app/config.py src/app/services/soap_note_service.py src/app/services/ai_evaluation.py src/app/services/demo_evaluation.py scripts/run_ai_eval.py --ignore-missing-imports
```

Final results: **563 passed, 101 warnings in 1.93 seconds**; Ruff lint passed;
Ruff format check passed for 12 files; mypy passed for all seven checked files,
including the runner. The untyped Google credential-refresh boundary now uses a
narrow `Callable[[Request], None]` cast with a mocked refresh-contract test; no
type suppression or live credential lookup was used for verification. Warnings
are dependency deprecation/experimental-feature notices.

The 35 migrated golden tests pass within that run. The focused suite also covers
production ingestion prompt contracts, candidate provenance, the worker, symptom
no-write failures, SOAP no-note failures, deterministic floors, bilingual outages,
both-locale structured extraction/intake scoring, rejected unverifiable quotes,
complete replay coverage and raw final-response retention. Tests write temporary
stub reports, not live-model reports.

The three demo dry-run commands above each returned exit 0 and selected
**34 / 17 / 17**. Both demo fixture SHA-256 values still match the README.

From the repository root:

```bash
rg -n 'agents[./]ingestion[./]graph|test_ingestion_graph|create_ingestion_graph|IngestionState' backend
git diff --check
```

Consumer search: **no matches (rg exit 1)**. Before deletion, the same import and
symbol searches with only the graph and its dedicated test excluded also had no
matches. Only those two unused files were deleted; ingestion prompts were kept.
`git diff --check`: **passed (exit 0)**. Deleted tracked files remain recoverable
from Git. No commit or remote operation forms part of this verification.
