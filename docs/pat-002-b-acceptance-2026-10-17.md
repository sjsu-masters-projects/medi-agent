# PAT-002-B review closure — October 17, 2026

Scope: requester-authorized chat questions and typed/spoken answers, explicit
confirmation button, unverified product testimony, durable handoff to existing ADR
screen/review notices, source-message locale and independent urgent handling.
PAT-002-C and ADR follow-up lifecycle implementation remain outside this change.

## Recorded automated evidence

- Backend owning suite: **79 passed**:
  `PYTHONPATH=src .venv/bin/pytest tests/unit/intake tests/integration/routers/test_symptom_intake_api.py tests/integration/routers/test_chat_voice_api.py tests/unit/services/test_a2a_task_service.py -q --no-cov`
- Disposable PostgreSQL: **25 passed**:
  `PYTHONPATH=src SYMPTOM_INTAKE_TEST_POSTGRES=1 CHAT_SAFETY_TEST_POSTGRES_DOCKER=1 .venv/bin/pytest tests/integration/test_symptom_handoff_postgres.py tests/integration/test_symptom_intake_postgres.py -q --no-cov`
  This covers real confirmation transactions, idempotency, authorization, stale
  context, cancellation/safety races, known/unlisted products, notice failure
  rollback, urgent plus emergency delivery and exact readiness metadata. The real
  A2A retry service creates one ADR draft through a local SQL transport shim and
  preserves a synthetic clinician-reviewed status on repeat delivery. This is not
  hosted PostgREST, deployed worker or professional review evidence.
- Patient focused suite: **87 passed**:
  `NODE_OPTIONS=--no-experimental-webstorage npm exec vitest run src/__tests__/voice-pause-monitor.test.ts src/__tests__/chat-page.test.tsx src/__tests__/symptom-intake.test.tsx`
  Includes private typed/STT answers, private TTS without chat message ID,
  hands-free resume/pause detection, source suggestion acceptance, blocked spoken assent,
  consent invalidation, preview privacy and stable mutation identity on token refresh. Answer locale retains STT metadata or the existing written-language detector without switching the pinned draft language.
- Patient typecheck and lint passed. Changed Python Ruff checks passed; mypy
  passed for eight changed source/script files. Migration parser validated **86 files**.
- Initial full patient run: **716 passed, 1 failed**. The unchanged ADR follow-up
  storage-spy control failed under Node 22.17.1 with experimental native Web Storage
  enabled. Final run with `NODE_OPTIONS=--no-experimental-webstorage npm exec vitest run`: **721 passed**, 68 files. This uses jsdom Web Storage for the browser test environment.
- Both portal production builds passed. The patient build needed its generated Turbopack cache moved aside after the sandboxed build cached a worker-port error; no source change was needed. Clinician lint/typecheck and 49 ADR/deep-dive/load-state tests passed.
- `pip install -r requirements-dev.txt` and `pip check` succeeded; no dependency or
  lockfile changes were made. The locked install supplied the previously missing
  `pypdf` dependency. PostgreSQL uses the official disposable `postgres:16-alpine`
  image. An intermediate Docker transport failure was resolved; the final 25-test
  suite passed without skips.

## Target and approval facts

The October 17 read-only preflight found exact 059/060/065 ledger matches and no
symptom-handoff migration. A later read-only ledger check records the exact
`071_confirmed_symptom_handoff.sql` identity as applied on October 18 with SHA-256
`f690b788d5f29c3d7583f2fe8cc43b7a51a6af817c276d6839cc9c9ab2ded36b`.
The migration directory also contains `071_clinician_visit_management.sql`; this exact
historical pair is intentional because the ledger keys by filename and checksum, not only
the numeric prefix. Preserve both applied identities and do not rename or replay either.
This review did not itself apply remote SQL.
The CLI has no database URL configured; the Supabase SQL editor requires sign-in.

Approved candidate-1 and its recorded October 12 requester-reported approval remain
unchanged. Candidate-2 is **pending review** for its exact new severity anchors and
unconditional concomitant-product question. No approval is invented or inherited.
See [rollout procedure](pat-002-b-rollout.md) for the exact migration checksum,
review package and separate eligibility/deployment/merge actions.

## Follow-along acceptance path

Use the existing fictional patient and assigned fictional clinician from
[demo environment](demo-environment.md). Obtain credentials from the team's secret
store; do not copy them into documentation. A fresh seed/reset is unnecessary.

1. Open `http://localhost:3000/chat`, then Nora. Type
   `I have a mild headache since this morning, about 3/10.` The initial message
   stays in ordinary chat; the guided answers remain private.
2. Accept the quoted description with **Use this answer**. Answer location in the
   main composer. Accept quoted onset and explicit numeric severity separately;
   no candidate is automatically saved. Say/type **not sure** or **skip** to
   verify distinct unknown/declined states. Refresh and reopen the conversation
   to recover the next unanswered question.
3. Use the microphone for dictation, review its transcript and Send. Enable
   hands-free to hear the current question, speak an answer and continue. Review
   preview playback, then say `confirm`: it must request the explicit controls
   and save no report. Physical microphone/provider checks need actual speech;
   the mocked transport tests above do not establish audio quality.
4. Report a product name exactly matching one active medication for the ADR
   path. In a separate draft, name an unlisted OTC product; the preview and
   clinician summary must label it patient-reported/unverified and the medication
   list must remain unchanged. Under approved candidate-1, concomitant products
   are conditional; candidate-2 makes that question unconditional only after review.
5. Press **Review before sharing**, inspect answers and record context, edit an
   answer and verify consent resets. Review again, check consent and press
   **Confirm and share** once. Refresh: it recovers the same saved report.
6. At `http://localhost:3001`, open the assigned patient's Symptoms and existing
   ADR workspace. After the exact `071_confirmed_symptom_handoff.sql` identity and the
   retry worker are active, verify the
   confirmed summary, one review notice and the eligible medication's ADR draft.
   A draft assessment is decision support awaiting clinician review, not causality.
7. Cancel a separate draft. No symptom report or ordinary ADR task should be
   created. A high-severity answer can still generate a minimal safety notice;
   emergency wording must interrupt ordinary intake independently.
8. Repeat with a Spanish source message and `es-MX` prompts. The source message's
   locale governs new drafts after the 071 handoff, even when the profile differs. Verify
   mobile width, keyboard/controls, no raw database IDs/JSON, and refresh recovery.
9. Verify another patient cannot read the draft/report and an inactive/unassigned
   clinician cannot read it. Interrupt connectivity and retry the same action;
   do not create a second report. Automated denial/transaction/retry evidence is
   above; authenticated browser observations must be recorded explicitly.

## Browser observations and remaining acceptance

The local patient portal is authenticated. On October 17, Nora displayed Connected,
accepted the natural headache message, opened its private description question,
showed the exact source quote and advanced to location after explicit acceptance.
Typed location used the main composer and did not add an ordinary user chat bubble.
The existing coordinator classified the initial turn urgent; its urgent notice was
preserved. This observation does not validate the coordinator's clinical classification.
The same browser journey completed all twelve questions using the main composer:
quoted description/onset/severity separately accepted, unknown course, declined
history, explicit metformin concern and unlisted herbal-tea testimony. Ambiguous
severity “mild” produced clarification without saving a number. The preview showed
canonical metformin context separately from unverified testimony and no database
IDs/JSON. Typing “confirm” did not submit. Checking consent enabled the separate
button; unchecking disabled it. Refresh plus reopening the saved conversation
recovered the same preview with consent reset. A button contrast issue found by
visual inspection was fixed using the shared primary Button.

Screenshots are local untracked verification artifacts under
`output/verification/pat002b-oct17/`; `chat-preview-desktop.png` shows the current
unsubmitted preview. A requested 375-pixel browser override did not change the
observed 1512-pixel viewport, so **no 375-pixel acceptance is claimed**; the temporary
override was reset. Physical microphone, bilingual/source-locale, authenticated
access-denial, connectivity interruption, new SQL handoff and deployed acceptance
remain pending until recorded. No new screenshot is evidence of a completed path
unless its corresponding state is described here.


## October 18 continuation — authorized SQL and authenticated handoff

The requester authorized only `071_confirmed_symptom_handoff.sql` with SHA-256
`f690b788d5f29c3d7583f2fe8cc43b7a51a6af817c276d6839cc9c9ab2ded36b`.
It was applied in the authenticated synthetic-project SQL editor with prerequisite
checksum guards, the existing advisory transaction lock and its ledger insert in
one transaction. The returned ledger row and a separate read-only preflight match.
Preflight passes 059/060/065/071, candidate-1 eligibility, trigger presence and
browser report/task write denial. No other remote migration, seed/reset, manual
deployment or merge was performed. There were zero existing due ADR retry tasks
before starting the local backend with both intake and retry flags enabled.

The patient confirmed the prepared preview through the checkbox/button. Report
`6675bec7-c256-4c1f-ae29-ad06f24e2ea6` has exactly one completed task
`c35c66d2-3065-4639-b7d7-8b8fc2489726`, ADR draft
`c6860843-bf91-4bfb-b4bf-5a781d112c7f` and one Elena review notice. Its exact
active-list product is Metformin. The unlisted herbal tea is absent from medications.
These are synthetic application records, not a professional clinical judgment.

Authenticated Elena → Maya → Symptoms shows the new Patient-confirmed summary,
3/10 severity and unverified testimony. ADR opens the new Metformin case awaiting
review. Its score is 0 with all ten Naranjo inputs missing, visibly labelled decision
support; no reviewer decision or causality evidence was fabricated. The canonical
unassigned José fixture shows Access denied with no patient record content. Its
normal authorization audit records `ASSIGNMENT_EXISTS_FOR_DIFFERENT_PATIENT_ONLY`.

Screenshots: `migration-071-applied.png`, `clinician-confirmed-summary.png`,
`clinician-adr-draft.png` under the local verification directory. The patient session
expired during the next refresh and a sign-in tab is prepared; further authenticated
patient recovery, Spanish and physical voice checks await sign-in.

All PR checks on code commit `708403c` passed, including full backend coverage and
shards, both portals, migration syntax and security checks. The PR description's
required checklist was restored and its policy job passed on rerun. The new intake
SQL suites are now added to the required PostgreSQL CI matrix with 17/8 minimum
case counts and zero-skips enforcement; workflow YAML and the required-summary
edge parse correctly. A new CI result is needed for that addition.

Main advanced to `582c397` with merged Nora recovery/session/notification work.
Integration and post-integration verification are in progress; earlier results
remain evidence for their named commit. The already applied intake 071 file will
not be renamed even though main independently added another 071 filename.


### Post-main integration checks

Main `582c397` is integrated with private composer routing, stable reconnect history
and the verified durable handshake retained. Emergency direction bypasses ordinary
turn work. A saved safety-outbox acknowledgement clears only its correlated
in-memory client request; retries derive a stable patient/session-scoped safety
identity, and uncertain persistence cannot acknowledge success. The symptom route
checks the existing action fence before opening the owned draft; no direct symptom
report writer or unconfirmed ADR delegation was restored.

Checks: **175** backend chat/intake/ADR-service cases; **116** focused UI cases;
**767** patient and **607** clinician tests; both portal lint/typecheck/builds;
Ruff checks/format for 288 files, mypy for 268 source files, and **91** migration
files parsed. The exact required SQL job passed **25** cases with XML-verified
17/8 counts and zero skipped/failed/error cases. Applied 071 still hashes to its
authorized checksum. Read-only readiness also passes existing Nora 072/073/074.

Live Spanish-source check used the patient's unchanged English profile and showed
the approved Spanish prompts. A Spanish private answer advanced while the chat
socket was unavailable during a local restart, then explicit Reconnect restored
Connected. The draft was cancelled, preserving chat and creating no report.

That first integrated turn exposed an upstream completion identity collision:
`TurnExecution.finish` allowed the staged assistant message's `id` to replace the
claimed turn `id`, producing immediate `CHAT_TURN_EXPIRED` despite time remaining.
The merge now preserves the claimed id/lease after merging the message payload.
The regression asserts the actual RPC identity and separate message id. The failed
attempt remains failed and was dismissed only through the normal UI; no row was
rewritten to manufacture a successful result. The fresh live turn completed; see the authenticated checks below.


### Final authenticated continuation — October 18

A fresh Spanish-source turn `80cbeac0-48aa-4524-895d-3e50c3bf2f8a` completed normally
with the identity fix. The patient's profile remained English; prompts, source
suggestions, review and confirmation used Spanish. Typed private answers, unknown
course/severity and declined history were preserved. During a deliberate local
backend stop, the final answer remained visibly unverified. After restart, reload
and **Retry the same action** saved it; explicit Reconnect restored Connected.
Refresh recovered the exact preview with the consent checkbox cleared.

The patient explicitly confirmed through the Spanish checkbox/button. Report
`8c3310e8-1cf0-4c1f-be6d-1ff9297f5635` exists once, has null severity and null
related-medication FK. Its one handoff task
`f0dc00e9-bcc6-407a-9b5a-bdbcfbbd7811` completed; one same-transaction Elena notice
exists (`17a53c16-2cca-4819-9258-e4559e5c92d7`). The unlisted tea has zero medication
rows. Elena → Maya → Symptoms shows the new Patient-confirmed report, unknown
severity and the full Spanish unverified-product summary. No clinical decision was
submitted. The earlier cancelled Spanish draft
`5e35cadc-5bd1-4c5d-8829-120aecddb216` has zero reports; its failed chat turn remains
failed rather than being rewritten. Reads used the existing owned intake RPC;
direct service-role table SELECT was denied as designed. No grants were changed.

The browser found a second display issue: an unsaved answer from a previous draft
could appear at the same revision in a new draft. Pending-answer display now checks
draft identity, question identity and revision. A regression reproduces same-revision
draft replacement and verifies the previous answer disappears.

The patient portal's inherited Permissions-Policy disabled microphones entirely.
It now permits `microphone=(self)` while retaining camera/geolocation denial and
browser permission. The actual local `/chat` response was HTTP 200 with that header.
A fresh English nausea draft is left at the location question for a human speech
check. **The requester chose to keep physical microphone verification pending.**
Automated audio events and the working HTTP policy are not actual speech evidence.
The ordinary new-symptom urgency banner follows the existing coordinator policy;
no clinical urgency downgrade was introduced by intake.

Final patient suite: **768 passed**, 71 files; focused chat/intake/recovery/voice
suite: **117 passed**. Patient lint/typecheck and production build pass. The first
build hit a sandbox worker-port failure; after moving generated Turbopack cache
aside, the build passed outside the sandbox. No source workaround was used.
Backend **175**, clinician **607**, real SQL **25**, Python checks and migration
parse results above remain applicable; only patient presentation/configuration and
docs changed afterward. Current-head CI is recorded separately once returned.

Screenshots under `output/verification/pat002b-oct17/`:
`spanish-answer-outage.png`, `spanish-preview-recovered.png`,
`spanish-confirmed.png`, `clinician-spanish-summary.png`, `voice-check-ready.png`.
These are local, untracked synthetic verification artifacts. A requested viewport
override did not change the observed desktop size; physical phone acceptance,
physical speech, candidate-2 approval/activation, peer review, merge and authorized
deployed configuration remain pending. No additional migration, seed/reset,
manual deployment or merge was performed.


### Delivery coordination

The first push was rejected without changing remote history: PR #159 had advanced
to Ganesh's `67aadefa`, merging ADR/MedWatch follow-up work and replacing the handoff
file with a different `076_confirmed_symptom_handoff.sql` checksum. That file is not
the exact 071 authorized and applied above. It was not run here.

To preserve the requested intake scope and the collaborator's work, the tested
continuation is published separately on `fix/confirmed-intake-integration`, draft
[PR #193](https://github.com/sjsu-masters-projects/medi-agent/pull/193). PR #159 is
unchanged. These are alternative review candidates for overlapping feature work;
maintainers must choose/reconcile the delivery path before merging. This is not
permission to apply 076, drop/rename applied 071, or merge both feature copies.
The working tree retains the unrelated task-board, scheduling, team, map and local
script edits. Physical microphone verification remains pending by requester choice.


### Final correction-selection regression and CI receipt

All **34 PR checks passed on `0855608fc678c59f4440e0662d21117fcdfd8466`**:
[CI run](https://github.com/sjsu-masters-projects/medi-agent/actions/runs/39180537308).
The full backend run reported **3,700 passed / 400 skipped**, **89.08% coverage**
(80% required), and 31 real appointment transaction cases with zero skips. The
separate required symptom SQL job reported **25 passed**, verified as 17 intake
and 8 handoff cases with zero skips. All four PostgreSQL matrix jobs passed.
Both portal builds/tests, migration syntax, secret scan and CodeQL passed.

A final state inspection found correction-question selection also needed draft
identity binding. Selection now belongs to its intake, so a new draft uses its
own current question. The regression replaces an edited draft with a new one and
asserts the new description question appears. After this patient-only change,
**769 patient tests / 71 files**, the 21 intake cases, lint, typecheck and patient
production build pass locally. This follow-up needs its own current-head CI result;
the preceding 34 green checks are evidence for the named commit, not a fabricated
result for a later head. No backend/SQL code changed after that green run.

A final read-only privacy check found exactly two messages in the confirmed Spanish
conversation (source and assistant acknowledgement); the tested private answers
were absent from ordinary chat content. The requester explicitly chose separate
intake delivery preserving #159, and elected to leave physical microphone
verification pending. Existing release prerequisites above remain in force.


### Requester-reported manual acceptance and review readiness — October 18

Tushar reported, “I have verified the remaining things,” and clarified:
“App, microphone and phone flows verified.” This closes those manual checks as
**requester-reported verification**. No new device, browser, locale, audio-provider
trace, screenshot or independent clinical validation is asserted. Earlier pending
notes above describe the earlier checkpoints, not the current manual-check status.

All **34 checks passed on final implementation commit
`ca12c395d23344894386fca368137486d5db90e2`**:
[CI run](https://github.com/sjsu-masters-projects/medi-agent/actions/runs/39182054190).
The run reports 3,700 backend passes / 400 skips and 89.08% coverage. The separate
required symptom SQL job passed 25 cases (17 intake / 8 handoff), zero skips.
All four SQL matrix jobs, portal tests/builds, typechecks, migration syntax and
security checks passed. `origin/main` is already an ancestor; no rebase, conflict
resolution or implementation change is needed. GitHub reports MERGEABLE/CLEAN.

The requester did **not** report candidate-2 wording approval. Its manifest entry
remains pending, active_version stays candidate-1, and no remote eligibility write
is authorized or performed. Candidate-2 requires Ganesh's genuine paired-wording
review before activation. Manual verification is not a GitHub PR approval: only a
code-quality bot comment is recorded at this checkpoint. The committed team
contract still requires one peer approval plus safety review before merge.

PR #193 is being moved from draft to ready for review; #159 is preserved, and its
concurrent 076 migration remains outside this delivery. Do not merge both copies
without reconciling their overlap. The documentation-only evidence update needs
its own CI result, available on the PR. No source, dependency, migration, library
selection, remote configuration, deployment or merge changes are part of this step.


### October 19 — integration after PR #159 merged

The previous readiness head `34f34d3` passed all 34 checks. On continuation, GitHub
reported conflicts because main advanced to `5d46c30` and independently merged #159
through `20ea7ac`. The earlier separate/unmerged #159 notes above are historical.
Integration uses an isolated worktree so the requester's unrelated board, team,
scheduling, map and locally edited scripts stay untouched in the original checkout.

Main now contains the intake implementation and the exact historical 071 migration
with SHA-256 `f690b788d5f29c3d7583f2fe8cc43b7a51a6af817c276d6839cc9c9ab2ded36b`.
No migration bytes, names or ledger rows change here. PR #193 now carries the
remaining fixes and evidence rather than another copy of the feature. Retain main's
server-owned turns, worker/event protocol, conditional ADR claim, locale/feed fixes
and split SQL CI jobs. Its completion identity fix already covers the earlier fix;
its standard terminal recovery replaces the superseded private acknowledgement
helper. No ADR follow-up implementation is added or reverted by this PR.

Retained fixes: pending answer and correction selection belong to their draft;
the microphone policy permits only the portal's own origin; a private REST reply
uses its intake's own busy state while an ordinary Nora turn is outstanding;
source-bound draft opening checks the durable action fence first. The voice route
also now forwards the recognizer locale through the page wrapper. A Spanish
`cinco` regression checks that locale in the private answer request; this is an
automated transport test, not new physical speech evidence.

The real-worker SQL transport adapter now supports main's conditional status filter.
Its retry case requeues the task after a simulated failed completion write and
verifies the actual database assessment keeps the clinician's reviewed state.
The runtime ADR worker itself is unchanged. The required 17/8 intake SQL counts
remain enforced alongside all six main SQL jobs.

Post-integration local verification:

- Backend chat/worker/intake API and library/service cases: **229 passed**.
- Patient suite: **818 passed**, 75 files; final chat-page regression: **99 passed**.
- Clinician suite: **617 passed**, 69 files.
- Both portal lint/typecheck and production builds pass.
- Ruff and format pass across **298** source/script files; changed router/preflight
  mypy passes; parser validation passes **94** migration files.

The first local backend launch lacked synthetic CI settings; rerun used explicit
fake test settings. Docker was stopped, so the initial SQL fixture setup could not
start; the installed local daemon was started. Turbopack rejected dependencies
symlinked outside the isolated worktree, so dependencies were copied locally and
both normal builds passed. No application configuration workaround was introduced.
The corrected SQL rerun passed **25** cases (17 intake / 8 handoff), with XML-verified
zero skips/failures/errors. Its first application-level failure identified the local
adapter's outdated status filter and upsert operation; the adapter now executes
main's actual insert and conditional claim. A separate setup timeout occurred under
parallel build load; the completed rerun changed no timeout or runtime behavior.
New-head CI results are recorded on PR #193 when available.

Requester-reported October 18 app/microphone/phone acceptance remains evidence for
its named prior implementation. No new authenticated deployed journey is claimed
for this integration. Candidate-1 stays active; candidate-2 remains pending actual
wording review. Genuine peer/safety review is still required. No remote migration,
seed/reset, service configuration, deployment or merge is performed by this step.
