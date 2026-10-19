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
