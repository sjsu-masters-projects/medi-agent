# Implementation Plan: ADR information-loop gap fixes

## Overview

PR 1 (no migration) and then PR 2 (migration 063, written and not applied), on branch
`fix/adr-information-loop-gaps` in `.worktrees/adr-loop-gaps`. Languages are Python 3.12 (FastAPI, pytest),
TypeScript (Next.js, Vitest) and PostgreSQL 16 SQL. Each task names the requirements it satisfies. Verification
commands are V1 to V11 in requirements.md.

No task applies a migration remotely, deploys, pushes, opens a pull request or merges. Every test sub-task is
required evidence (V3, V5, V6, V10), so none is marked optional.

## Tasks

### PR 1: patient and clinician surfaces (no migration)

- [x] 1. Scope the work in the tracker
  - [x] 1.1 Add the `PV-001-C` row and correct stale rows in `.agent/TASKS.md`
    - Add a scoped `PV-001-C — ADR loop gap fixes` row (P1, In progress) that links this spec and lists PR 1 (G1 to
      G5) and PR 2 (G6 to G10, 063 written, not applied).
    - Update the "Synthetic database schema" row: 048 MedWatch was applied by the requester to `mediagent-staging`
      on 2026-10-12, and the ledger is synchronized through 058. 063 is not applied anywhere. Drop "adds an unapplied
      `048_medwatch_draft_lifecycle.sql`".
    - Update the PV-001, PV-001-B, PV-002 and NOT-003 rows to reference PV-001-C. NOT-003 keeps D1 open.
    - _Requirements: 2.5, 2.7_

- [x] 2. Patient ADR read model and respond error mapping (backend)
  - [x] 2.1 Add read models in `backend/src/app/models/adr.py`
    - Add `ADRFollowUpResponseItem` (`question`, `answer`, `evidence`), `ADRFollowUpRequestRead` (fields per the
      design; no score or causality fields) and `ADRFollowUpOverviewRead` (`selected`, `pending`, `recent`).
    - _Requirements: 6.1, 6.2, 6.5_
  - [x] 2.2 Implement the overview and harden respond in `backend/src/app/services/patient_service.py`
    - Add `get_adr_follow_up_overview(patient_id, request_id=None, assessment_id=None)`. Every query filters
      `patient_id`. `pending` returns pending rows newest first. `recent` returns `answered` and `cancelled` rows from
      the last 90 days, newest first, `limit(5)`. `selected` is looked up by request ID, or the newest request for an
      assessment, and raises `NotFoundError` when absent or another patient's. Fill `replacement_request_id` and
      `closed_at`. Keep only allowlisted Question_Keys.
    - In `respond_to_adr_information_request`, replace `.single()` with `.eq("patient_id").limit(1)`, raise
      `NotFoundError` on zero rows, and raise `ValidationError(code="ADR_REQUEST_CLOSED")` on a non-pending request or
      non-draft assessment.
    - Wrap the RPC call in `except APIError`: `P0002` becomes `NotFoundError`, `23514` becomes `ADR_REQUEST_CLOSED`,
      `22023` becomes `ValidationError(code="ADR_RESPONSE_INVALID")`, and anything else becomes
      `ExternalServiceError`. Log no PostgREST detail.
    - _Requirements: 3.7, 6.3, 6.4, 6.5_
  - [x] 2.3 Add the route in `backend/src/app/routers/patients.py`
    - Add `GET /me/adr-information-requests/overview` with optional `request_id: UUID` and `assessment_id: UUID`.
      Return 422 when both are given. Keep the router thin (delegate to the service) and declare the route before any
      `/{request_id}` path. The existing list and respond routes are unchanged.
    - _Requirements: 4.1, 6.1, 6.2, 6.3_
  - [x] 2.4 Write backend tests for the read model and error mapping
    - `tests/unit/services/test_patient_service.py`:
      - `patient_id` is applied on every overview query;
      - the status, 90-day and `limit(5)` bounds and ordering;
      - selection by request and by assessment;
      - the same `NotFoundError` for missing and foreign IDs;
      - closed and invalid code mapping for service checks and each RPC `APIError` code.
    - `tests/integration/routers/test_patient_api.py`: the route exists, both parameters give 422, 404 returns the
      error envelope, and the response has no `current_naranjo_score` or `causality` keys.
    - _Requirements: 3.7, 6.1, 6.3, 6.4, 6.5_

- [x] 3. Deterministic bilingual request notification (backend presentation)
  - [x] 3.1 Update `backend/src/app/services/notification_centre_presentation.py`
    - Add `_QUESTION_WORDING` with exactly the R5 table. Rewrite `_questions` (allowlist, first-seen order,
      duplicates removed, at most 3, "• " lines under the localized heading, "" when none remain).
    - Replace the `adr_information_requested` body with the design wording; keep the titles.
    - Change the patient destination to `/chat?view=follow-up&assessment=<source_id>` (or `/chat?view=follow-up` when
      `source_id` is not a UUID), labelled "Answer questions" / "Responder preguntas".
    - _Requirements: 4.2, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  - [x] 3.2 Write presentation tests in `backend/tests/unit/services/test_notification_centre_presentation.py`
    - Migrate the assertions for "shown as written" and for the `view=care-team&recipient=` link (R5.7).
    - Add all three keys in both locales and a History "View" / "Ver" case.
    - **Property 1: Request wording is fixed, ordered and leak-free.** Exhaustive `itertools` corpus per the design,
      both locales, compared with a reference model.
    - **Property 2 (patient part): Notification links stay inside the allowlist.** Arbitrary `source_id` and
      metadata.
    - _Requirements: 4.2, 5.1, 5.2, 5.3, 5.7, 10.3_

- [x] 4. Patient copy module and client service
  - [x] 4.1 Create `apps/patient-portal/src/content/adr-follow-up-copy.ts`
    - Add the typed `ADRFollowUpCopy`, `EN` and `ES` constants, `getADRFollowUpCopy(locale)` and
      `formatFollowUpDate(iso, locale, timeZone)`, with the key groups from the design. Keep the en-US selector
      strings exactly ("Yes", "No", "I’m not sure", "Review answers", "Send to care team", "Edit"), keep the three
      safety statements and the confirmation meaning, and use the "tu equipo de atención" register.
    - _Requirements: 3.1, 3.2, 3.5, 3.6, 1.18_
  - [x] 4.2 Write the copy parity test (`apps/patient-portal/src/__tests__/adr-follow-up-copy.test.ts`)
    - **Property 3: Copy parity across locales.** Recursive key-path equality, non-empty strings and non-empty output
      of each function for sample arguments.
    - _Requirements: 3.1, 3.2, 1.18_
  - [x] 4.3 Extend `apps/patient-portal/src/services/adr-follow-up.ts`
    - Add the types for the overview, `fetchADRFollowUpOverview(token, { requestId } | { assessmentId } | {})` and
      `classifyADRFollowUpError(error)`, which reads `ApiClientError.status` and `details.error.code` and returns
      `closed`, `notFound`, `unavailable` or `other`.
    - _Requirements: 3.7, 6.3, 6.4_
  - [x] 4.4 Write the classifier test (`apps/patient-portal/src/__tests__/adr-follow-up-service.test.ts`)
    - **Property 4: Error classification is total and never shows server text.** A generated table over status 0 to
      599, the known codes plus arbitrary text, plain `Error` and non-error values.
    - _Requirements: 3.7, 6.3, 6.4_

- [x] 5. Follow-up form and host view (patient portal)
  - [x] 5.1 Create `apps/patient-portal/src/components/features/adr-follow-up-form.tsx`
    - Build `ADRFollowUpForm` from tokens and primitives as in the design table (exemplars `visit-offer-card.tsx`
      and `notification-centre.tsx`):
      - fieldsets with sr-only radios inside 44 px labels showing a `has-[:focus-visible]` ring and a check glyph;
      - labelled textarea with a counter;
      - review step and a 44 px confirmation label;
      - `role="alert"` errors from `classifyADRFollowUpError` and the copy;
      - the unsent note near Send, and `ProcessingDots` while sending.
    - Do not write to any storage and render no `AiChip` or `ApprovalSeal`. Keep validation and the payload unchanged.
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.7, 1.9, 1.14, 1.15, 3.1, 3.4, 3.5, 3.7, 3.8, 3.9, 3.10, 6.8_
  - [x] 5.2 Migrate and extend the form tests
    - Move `src/__tests__/adr-follow-up-panel.test.tsx` to `src/__tests__/adr-follow-up-form.test.tsx`, keeping the
      existing selectors (R1.17), and list the migration for the PR.
    - Add es-MX rendering, verbatim stored text, the `min-h-11` and focus-ring classes, the check glyph, localized
      error per class, and storage spies showing no `localStorage` / `sessionStorage` writes.
    - **Property 5: Review is enabled exactly for complete answers, with an unchanged payload.** An exhaustive table
      over 1 to 3 questions with every answer and evidence option.
    - _Requirements: 1.5, 1.7, 1.17, 3.1, 3.4, 3.7, 3.8, 3.9, 6.8_
  - [x] 5.3 Create `apps/patient-portal/src/components/features/adr-follow-up-view.tsx`
    - `ADRFollowUpView({ locale, requestId, assessmentId })` loads the overview and renders:
      - `Skeleton` while loading, with no default-locale text before the profile resolves;
      - `ErrorState` with retry, and the not-found `EmptyState`;
      - forms for pending requests;
      - the read-only answered summary, with the date in the patient's timezone and no score;
      - the closed state with an `openNewer` link;
      - the empty state;
      - a persistent, focused `role="status"` confirmation after sending, followed by a refetch;
      - a collapsed recent-history disclosure of up to 5 items.
    - _Requirements: 1.13, 3.3, 6.1, 6.2, 6.3, 6.4, 6.6, 6.7, 13.1_
  - [x] 5.4 Write view tests (`apps/patient-portal/src/__tests__/adr-follow-up-view.test.tsx`)
    - Cover every state in both locales, focus moving to the confirmation, closed-on-submit switching to the
      answered or closed state without a retry, and no score text.
    - _Requirements: 3.3, 6.1, 6.2, 6.3, 6.4, 6.6, 6.7_

- [x] 6. Routes and entry rows (patient portal)
  - [x] 6.1 Add the pending hook and the entry row
    - Add `apps/patient-portal/src/hooks/use-pending-adr-follow-ups.ts`, which uses the existing pending list
      endpoint, and `components/features/adr-follow-up-entry-row.tsx`, a `Link` to `/chat?view=follow-up` built like
      Today's symptom row (`IconTile icon="note" tone="note"`, count in `font-mono`, `min-h-11`). The row renders
      nothing while loading, on error or with zero pending requests.
    - _Requirements: 4.4, 4.7, 13.5_
  - [x] 6.2 Integrate the follow-up mode and rows in `apps/patient-portal/src/app/(app)/chat/page.tsx`
    - Add `view=follow-up` mode, which reads `request` / `assessment` and renders the thread-style header with a back
      button (`router.replace("/chat")`), the `controls.caution` strip and `ADRFollowUpView`. Hide the inbox, the
      Nora card and the composer, set `setConversationOpen(true)` and use safe-area bottom padding.
    - Add the entry row in the inbox after the Nora card, and replace `<ADRFollowUpPanel />` in the Nora thread with
      the entry row.
    - Delete `components/features/adr-follow-up-panel.tsx`.
    - _Requirements: 1.11, 4.1, 4.3, 4.4, 4.5_
  - [x] 6.3 Add the Today entry row in `apps/patient-portal/src/app/(app)/today/page.tsx`
    - Place it at the top of the content stack, rendered only while a request is pending.
    - _Requirements: 4.4, 4.7_
  - [x] 6.4 Write routing and entry-row tests
    - `chat-page.test.tsx`: `view=follow-up` with request, assessment or neither shows the view without a thread;
      the caution is shown; the Nora thread shows the row; the inbox row appears with 0, 1 and 2 pending.
    - `today-page.test.tsx`: the row appears only while pending.
    - `notifications-service.test.ts`: `notificationDestination` accepts the new links.
    - A `redirectToLogin` test shows the `?view=follow-up&request=` return path is kept.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 13.5_

- [x] 7. Evidence provenance on the clinician ADR card
  - [x] 7.1 Update the type, the formatter and `adr-review-card.tsx`
    - In `apps/clinician-portal/src/services/clinicians.ts`, add `source?` and `information_request_id?` to
      `ADRReviewEvidence`.
    - Move the card's `en-US` date formatter into a shared module next to it (for example
      `components/features/review-time.ts`).
    - In `adr-review-card.tsx`, remove the list-level `AiChip`, add per-entry labels (`AiChip` "AI-extracted",
      neutral `Badge` "Patient-confirmed" with the date when the request ID matches, neutral `Badge` "Other source")
      and set keys to `${index}:${question}:${source}`. Keep the caveat and footer text.
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 1.15_
  - [x] 7.2 Write `apps/clinician-portal/src/__tests__/adr-review-card.test.tsx`
    - Cover all-AI, all-patient and mixed evidence, the date shown, and the caveat text present.
    - **Property 6: Each evidence entry carries exactly one truthful provenance label.** A generated table of
      evidence lists with repeated questions and arbitrary `source` values; spy on `console.error` for duplicate-key
      warnings.
    - _Requirements: 7.1, 7.2, 7.4, 7.5, 7.6, 7.7, 1.15_

- [x] 8. MedWatch page and draft defects (clinician portal)
  - [x] 8.1 Rebuild `apps/clinician-portal/src/components/features/medwatch-draft-card.tsx`
    - Use `fieldClass`, `Badge`, `Button` and `ApprovalSeal` with tokens only:
      - a warning `Badge` "Not submitted to FDA";
      - a seal only when `reviewed`;
      - `risk-*` and `ok-*` tokens;
      - `font-mono break-all` for IDs and wrapping for paths and citations.
    - Replace the reset effect with the revision-keyed sync that keeps dirty edits and shows "Unsaved changes".
    - Use the shared `en-US` formatter from 7.1.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.6, 8.7, 8.9, 1.2, 1.6_
  - [x] 8.2 Fix `medwatch-preparation-action.tsx` and `app/(dashboard)/medwatch/page.tsx`
    - Rebuild the action from tokens and `fieldClass`. Catch `onPrepare` failures into an inline `role="alert"` and
      keep the rationale.
    - In the page, stop setting the page-level error for prepare, and change the `Suspense` fallback to
      `LoadingQueue`. Keep every existing action, label and region selector.
    - _Requirements: 8.1, 8.5, 8.8, 8.9, 1.13, 1.17_
  - [x] 8.3 Write MedWatch tests
    - Add `medwatch-draft-card.test.tsx` covering:
      - a rerender with a new draft object at the same and at a new revision while dirty or clean;
      - the seal shown for `reviewed` and absent for `draft`;
      - the formatter output.
    - Add `medwatch-preparation-action.test.tsx` covering the inline alert with no unhandled rejection.
    - Update `adr-review-page.test.tsx` for the fallback and selectors.
    - _Requirements: 8.3, 8.4, 8.5, 8.6, 8.8, 8.9_

- [x] 9. Patient-portal documentation
  - [x] 9.1 Update the "ADR care-team follow-up" section of `apps/patient-portal/README.md`
    - Cover the `/chat?view=follow-up` route and parameters, the overview endpoint, the entry rows, the states and
      the no-draft-persistence rule.
    - _Requirements: 2.5_

- [x] 10. Checkpoint: PR 1 verification
  - Re-read `backend/README.md`, `CONTRIBUTING.md`, `.github/workflows/ci.yml` and both apps' `package.json`. Fix the
    V1 to V11 commands in requirements.md if anything differs.
  - Create the environment if missing: `cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r
    requirements-dev.txt`, then `npm ci` in `apps/patient-portal` and in `apps/clinician-portal`.
  - Run V1, V2, V3, V7, V8 and V9, and the V10 tests (included in V3, V7 and V8).
  - Produce the V11 contrast table for every text and background token pair used on the changed surfaces, using a
    temporary script that is deleted afterwards.
  - Confirm the change adds no `*.sql`: `git status --short | grep -i '\.sql'` prints nothing. Do not diff against
    `origin/main` itself once it has moved; use `git merge-base HEAD origin/main`. Record each command and outcome
    in the `PV-001-C` row evidence.
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 1.8, 2.1, 2.6, 14.1_

### PR 2: notification lifecycle and data deletion (migration 063, not applied)

- [x] 11. Contract-test fixture and reproductions against unmodified behaviour (first)
  - [x] 11.1 Extend the PostgreSQL fixture in `backend/tests/integration/test_notification_centre_postgres.py`
    - In the base `sql` fixture:
      - add `042_auditable_adr_assessments.sql` before 046;
      - add `047_adr_patient_information_loop.sql`, `047_care_plan_private_rls_helpers.sql`,
        `048_care_team_conversations.sql` and `048_medwatch_draft_lifecycle.sql` in ledger order;
      - after 056, move in the `057_email_delivery.sql`, auth-privilege revoke and `058_email_delivery_fixes.sql` steps
        from `email_sql`;
      - finally apply `063_*.sql` only when the file exists and `ADR_LOOP_GAP_BASELINE` is not `1`.
    - Make `email_sql` in `test_email_postgres.py` return `sql`.
    - Migrate `test_adr_reviewed_questions_only_and_current_status` to `["dose_response"]`.
    - Run the notification and email suites (V6 regression commands) on this baseline. They must pass, which shows
      047 ADR and 048 MedWatch apply on a fresh database.
    - _Requirements: 14.6, 14.7_
  - [x] 11.2 Write the reproduction tests in `backend/tests/integration/test_adr_loop_postgres.py` and run the baseline
    - Use the same opt-in skip (`NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER`) and `pytest_plugins` reuse as the email
      suite, with helpers for assessment, request, answer (valid RPC payload) and MedWatch draft set-up on synthetic
      IDs.
    - Write:
      - `test_answer_creates_no_new_patient_request_event` (R9.1);
      - `test_answered_request_item_is_history` (R9.2);
      - `test_one_patient_item_per_request` (R10.1);
      - `test_patient_deletion_after_answer_with_medwatch_draft` (R12.1, R12.2; also asserts another patient and the
        clinician are untouched);
      - `test_superseded_request_is_history` (R13.2).
    - Run V6 baseline (`ADR_LOOP_GAP_BASELINE=1`, before any 063 file exists) and record in the `PV-001-C` evidence
      which tests fail and the exact error, especially whether G9 fails with an FK violation.
    - _Requirements: 9.1, 9.2, 10.1, 12.1, 12.2, 12.3, 13.2, 14.8, 14.9_

- [x] 12. Migration 063
  - [x] 12.1 Write `backend/src/app/db/migrations/063_adr_information_loop_lifecycle.sql` (design order, steps 1 to 7
    and 9 to 11)
    - Steps:
      - extend `notification_events_event_type_check` and `notification_events_source_type_check`;
      - redefine `private.notification_source` (051 copy), `private.notification_actionable` (054 copy, with the
        request-sourced, legacy rule L and `adr_information_answered` branches) and
        `private.capture_notification_source` (055 copy; the `adr_assessments` branch no longer emits patient
        request events; add the `adr_information_requests` branch with the two keyed events);
      - add the capture trigger on `adr_information_requests`;
      - redefine `public.review_adr_assessment` (047 copy without the `public.notifications` insert) and
        `public.respond_to_adr_information_request` (047 copy plus `notification_prepare`, receipt `read_at` and read
        audit);
      - revoke DELETE and TRUNCATE on both audit tables;
      - restate the grants;
      - add the fail-closed `DO $$` block with checks (b) to (e).
    - Do not edit any existing migration.
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.6, 9.7, 10.2, 10.4, 10.5, 11.1, 11.3, 11.4, 11.5, 11.7, 11.8, 11.9, 12.4, 12.5, 14.1, 14.3, 14.4_
  - [x] 12.2 Add the patient-deletion foreign-key change only if 11.2 reproduced G9
    - If the baseline failed: recreate `adr_assessment_audit_events_patient_actor_id_fkey` with `ON DELETE CASCADE`
      and add verification check (a). If it passed: leave the FK and check (a) out, and record the reason in
      `PV-001-C`.
    - Clinician-side `RESTRICT` references stay unchanged.
    - _Requirements: 12.1, 12.2, 12.5, 12.6, 14.9_
  - [x] 12.3 Write `backend/tests/unit/db/test_adr_loop_gap_fixes_migration.py`
    - Assert at text level:
      - both CHECK extensions and the source allowlist;
      - the request-sourced actionability, rule L and the answered branch;
      - the capture keys;
      - `review_adr_assessment` has no `INSERT INTO public.notifications`;
      - respond marks receipts read and writes read audit;
      - the DELETE / TRUNCATE revoke and `service_role`-only RPC grants;
      - the verification block;
      - the FK clause when shipped, and no change to clinician RESTRICTs.
    - Run V4 and V5.
    - _Requirements: 10.2, 12.4, 12.5, 14.1, 14.3, 14.4, 14.10_

- [x] 13. Make the reproductions pass and complete contract coverage
  - [x] 13.1 Apply 063 in the fixture and rerun the reproductions
    - Change the fixture so 063 always applies unless `ADR_LOOP_GAP_BASELINE=1`.
    - Run V6 (fixed). Every reproduction test from 11.2 passes; fix 063 (not the tests) until they do.
    - _Requirements: 9.1, 9.2, 10.1, 12.1, 12.2, 13.2, 14.9_
  - [x] 13.2 Add the remaining contract tests to `test_adr_loop_postgres.py`
    - R9: the receipt is read with a read audit row (including an undelivered item); an assessment `updated_at`
      touch creates no patient event; no repeated `email_outbox` row after an answer with a verified, consenting
      contact; earlier events are unchanged; the event metadata carries `information_request_id`.
    - R10: no new `notifications` row; existing legacy rows and events are unchanged; respond succeeds without a
      legacy row.
    - R11: one `adr_information_answered` event per request, also on a retried answer; it is delivered to every
      assigned clinician and lost after the assignment is revoked; it is denied to the patient and an unassigned
      clinician; it is absent from `action_items`, History and unread; it creates no email; a forced capture failure
      rolls back the answer.
    - R12: no role holds DELETE on the audit tables; clinician deletion is still blocked (D1 guard).
    - R13: mark reviewed, dismiss and prepared draft each make the item History with its unread state kept; nothing
      is deleted.
    - **Property 7: At most one actionable patient request item, and it belongs to the pending request.** About 12
      enumerated operation sequences.
    - _Requirements: 9.3, 9.4, 9.5, 9.6, 9.7, 10.2, 10.4, 10.5, 11.1, 11.3, 11.4, 11.5, 11.7, 11.8, 11.9, 12.3, 12.4, 12.5, 13.1, 13.3, 13.4, 14.8_
  - [x] 13.3 Run the regression suites on the 063 schema
    - Run the V6 regression commands (notification centre and email suites). Both pass with 063 applied and in the
      baseline.
    - _Requirements: 14.3_

- [x] 14. Presentation for request-sourced events and the clinician alert
  - [x] 14.1 Update `backend/src/app/services/notification_centre_presentation.py`
    - Request-sourced patient items link to `/chat?view=follow-up&request=<source_id>`; assessment-sourced items keep
      the PR 1 link.
    - Add `_COPY["adr_information_answered"]` with the design wording, which carries no clinical content and states
      that it is not a clinical decision.
    - Make `_safety_link` prefer a valid `metadata.adr_assessment_id`.
    - _Requirements: 4.2, 11.2, 11.6, 11.10_
  - [x] 14.2 Extend the presentation tests
    - Cover the answered-alert title, body, category, link and label, the request-sourced link, and History labels.
    - **Property 2 (full): Notification links stay inside the allowlist.** Extend the table to `source_type` values
      and `adr_information_answered` / `adr_review` clinician links.
    - _Requirements: 4.2, 11.2, 11.6_

- [x] 15. Tracker and NOT-001 documentation for PR 2
  - [x] 15.1 Update `.agent/TASKS.md` and the NOT-001 specification
    - `PV-001-C` and "Synthetic database schema": 063 written, not applied, plus the baseline and fixed evidence and
      the deploy-order conclusion (merge PR 2, then apply 063 on explicit authorization).
    - NOT-001 spec: the `adr_information_requests` source, the `adr_information_answered` type (History-only, no
      email), rule L and answer-marks-read.
    - _Requirements: 2.5, 2.6, 14.2, 14.5_

- [x] 16. Checkpoint: PR 2 verification
  - Re-check the commands against `backend/README.md`, `CONTRIBUTING.md` and CI as in task 10.
  - Run V1, V2, V3, V4, V5 and V6: the baseline (expected failures as recorded in 11.2), the fixed run and the
    regression commands.
  - Confirm `git diff --name-only <PR 1 head>` adds exactly one migration, `063_adr_information_loop_lifecycle.sql`,
    and edits no existing migration. Record every command and outcome in `PV-001-C`.
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 2.1, 2.6, 14.1, 14.2, 14.9_

### PR 3: MedWatch Form 3500 (migration 064, not applied)

- [x] 17. Tracker for PR 3
  - [x] 17.1 Update `.agent/TASKS.md` when PR 3 implementation starts
    - `PV-002`: owner override to Rajeev, per the requester on 2026-10-12.
    - `PV-001-C`: add PR 3 scope (R15 to R24, D12 to D17 decided) and an evidence placeholder for task 33.
    - "Synthetic database schema": add a 064 row, `064_medwatch_form_3500.sql` written, not applied anywhere.
    - Do not touch PR 1 or PR 2 rows beyond these additions.
    - _Requirements: 24.8_

- [x] 18. PDF dependency
  - [x] 18.1 Pin `pypdf==6.20.1`, regenerate both lockfiles and audit
    - Add `pypdf==6.20.1` to `backend/requirements.in` (exact pin; not PyMuPDF).
    - Regenerate with the exact CI commands from `.github/workflows/ci.yml`, run in `backend/`:
      `uv pip compile requirements.in --universal --python-version 3.12 --output-file requirements.txt` and
      `uv pip compile requirements-dev.in --universal --python-version 3.12 --output-file requirements-dev.txt`.
    - Install into `backend/.venv` from the regenerated `requirements-dev.txt` and confirm
      `.venv/bin/python -c "import pypdf; print(pypdf.__version__)"` prints `6.20.1`.
    - Run `uvx --from pip-audit==2.10.1 pip-audit -r requirements-dev.txt` as CI does; it must pass. Record
      `git diff --stat -- requirements.txt requirements-dev.txt` for task 33.
    - Create the empty package marker `backend/src/app/services/medwatch_3500/__init__.py` so later sub-tasks add
      modules to it without file conflicts.
    - _Requirements: 21.8, 24.5_

- [x] 19. Official Form 3500 template asset
  - [x] 19.1 Re-download, verify and vendor the template with its records
    - `mkdir -p /tmp/fda3500 && curl -sSL -o /tmp/fda3500/fresh.pdf https://www.fda.gov/media/76299/download`.
    - Compare `shasum -a 256` with the pinned
      `1147d7c86bb002cba7fb9352ca8e3402524d8fa0236916b7bf7e5dcdcf88bf9c` and the size with 921,232 bytes. If either
      differs, stop and ask the requester; do not re-pin silently.
    - V23: check the PDF text and metadata for a copyright notice. Record the result; if a notice exists or the
      result is unclear, leave the "no copyright claimed" sentence out and flag it for the requester.
    - Copy the file byte-identically to `backend/src/app/assets/fda/form-3500-2025-09.pdf`.
    - Write `TEMPLATE.json` (title, revision, OMB, expiry, 8 pages, 239 fields as 142 text / 83 checkbox / 14
      choice, `field_inventory_sha256` of the sorted names, `choice_options` with display and export values,
      `encrypt_p` -1084, source URL, download date, SHA-256), generated from the file with pypdf, not typed by hand.
    - Write `README.md` (provenance, V23 result, re-pin steps). Delete `/tmp/fda3500` afterwards.
    - _Requirements: 15.2, 15.3, 15.6_
  - [x] 19.2 Ship the asset with the backend package
    - Add the `assets/fda/*` files to package data in `backend/pyproject.toml` and confirm `backend/Dockerfile`
      copies `src/` so the asset reaches the image; change the Dockerfile only if it does not.
    - Add `backend/tests/unit/services/test_medwatch_form_3500_packaging.py` asserting at text level that the
      package-data glob and the Docker copy cover `app/assets/fda/`.
    - _Requirements: 15.2_
  - [x] 19.3 Write `backend/src/app/services/medwatch_3500/template.py` and its pin tests
    - Load the PDF and `TEMPLATE.json` once per process via `importlib.resources` (no network); check SHA-256, page
      count, field counts, inventory hash and an optional set of required field names (the `FIELD_MAP` names, wired
      in 24.2).
    - Any mismatch raises `TemplateMismatchError` (mapped to 503 `FORM_3500_TEMPLATE_MISMATCH` in 27).
    - Tests in `backend/tests/unit/services/test_medwatch_form_3500_template.py`: the pinned checksum, revision
      record, counts and inventory hash; a tampered-bytes fixture, a changed record and a missing required name each
      raise; no network call is made.
    - _Requirements: 15.2, 15.4, 15.7_

- [x] 20. Form 3500 data model v2
  - [x] 20.1 Write the v2 model, date encoding and validators with their tests
    - `backend/src/app/services/medwatch_3500/dates.py`: `fda_date` / `parse_fda_date` (`03-Oct-2026`, `Oct-2026`)
      from a fixed English month tuple, not `strftime`.
    - `backend/src/app/models/medwatch_form_3500.py`: `MedWatchFormDataV2` with sections A, B, D, F, G,
      `mediagent_review` and `legacy`; `FdaDate`; enumerations as `Literal`s with display text; no C, E,
      purchase-place or product-address fields.
    - Validators: real dates; event, report, death and therapy dates not after the save date in
      America/Los_Angeles; `therapy_stop >= therapy_start`; future `expiration_date` allowed; `frequency_other` /
      `route_other` required exactly when `Other`; at most 8 test rows and 10 F rows. Errors name the path (422).
    - Tests in `backend/tests/unit/services/test_medwatch_form_3500.py`: each validator and an out-of-list value
      per enumeration.
    - **Property 9: Save then load returns equal data** (model part: JSON dump then validate is equal; the service
      part is in 27.1).
    - **Property 13: Date encoding round-trips and rejects bad dates** (1900 to 2100, full and month-and-year, under
      a non-English process locale).
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.7, 16.8, 21.3_
  - [x] 20.2 Write `upgrade_legacy_form` and its tests
    - `backend/src/app/services/medwatch_3500/legacy.py`: pure and idempotent; v2 input returned unchanged;
      applies the design's 048-to-v2 table (identifier replaced by `default_code` when it fails
      `identifier_violations`; sex and date parsing; frequency / route option match or `Other`; dose split only on
      `<number> <unit>`; F split with the more-than-10 fallback; reporter names only on exactly two tokens; every
      unmapped value into `legacy`).
    - Tests in `backend/tests/unit/services/test_medwatch_form_3500_legacy.py`.
    - **Property 8: Legacy upgrade is idempotent and lossless** (empty, valid, unparseable and accented payloads).
    - _Requirements: 16.5, 16.8, 17.3_

- [x] 21. Non-identifying identifier and name warnings
  - [x] 21.1 Write `backend/src/app/services/medwatch_3500/identifier.py` with its tests
    - `default_code(first, last, draft_id)`: NFKD accent-stripped upper-case initials (`X` when missing), `-`, and
      the first base32 SHA-256 window of `draft_id.bytes` that passes `identifier_violations`.
    - `identifier_violations(value, patient)`: casefold, accent-strip, tokenise; reject full name, a name token,
      email or local part, and DOB as ISO, `MM/DD/YYYY`, `DD-Mon-YYYY` or digits.
    - `name_warnings(form, names)`: the same matcher over B5, B6, B7 and F text against patient, assigned clinician
      and clinic names; returns `{path, kind}`.
    - Tests in `backend/tests/unit/services/test_medwatch_identifier.py`, including name warnings per path.
    - **Property 11: The identifier never contains a name, email or date of birth** (ASCII, accented, hyphenated,
      single-letter names and a name equal to a base32 window).
    - _Requirements: 17.1, 17.2, 17.3, 17.4_

- [x] 22. Prefill with provenance
  - [x] 22.1 Replace `_build_form_data` with `build_form_3500` in `backend/src/app/services/medwatch_service.py`
    - Return `(form, source_evidence)` with one evidence entry per filled path and its source.
    - Fixed attribution: assessment evidence keeps its own `source`; nothing is labelled AI-extracted unless its
      source is.
    - Rules: A from the patient profile (`female` / `male` only); B3 from `onset` when it parses, else the
      `created_at` date, unconfirmed "Best estimate, confirm"; B4 blank until approval; B5 narrative; B6 rows blank
      (K-P8), B6 comments and B7 from stored text; D from medications; D abated / reappeared from Naranjo answers; F
      from other active medications; G names and email only, health professional and occupation blank; no invented
      values. Reporter identity only in Section G.
    - Tests in `backend/tests/unit/services/test_medwatch_service.py`: each source mapping, a blank-source item stays
      blank, the attribution fix, and B6 left blank for observation facts.
    - _Requirements: 17.6, 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 18.7, 18.8_

- [x] 23. Approval gate
  - [x] 23.1 Write `backend/src/app/services/medwatch_3500/gate.py` with its tests
    - `approval_issues(form, ctx) -> list[GateIssue(path, code)]`: one code per R19.1 item plus
      `identifier_identifies`, `death_date_missing` and `non_serious_attestation_required` (cleared only when no B2
      outcome is set and `non_serious_attested` is true).
    - Tests in `backend/tests/unit/services/test_medwatch_gate.py`.
    - **Property 12: The approval gate is total and shared** (reference model over every presence / absence
      combination, each B2 outcome, death date and D12 attestation).
    - _Requirements: 17.3, 19.1, 19.2, 19.3, 19.4, 19.5_
  - [x] 23.2 Extend the approval request model and the attestation constant
    - In `backend/src/app/models/adr.py`, add `attestation_version: Literal["medwatch-3500-approval-v1"]`,
      `non_serious_attested` and `acknowledged_warnings` to `MedWatchDraftApprovalRequest`.
    - Add the single backend attestation text constant keyed by that version (returned with the draft in 27.1).
    - Tests in `backend/tests/unit/models/test_medwatch_approval_request.py`: a wrong version, a missing field and
      a valid payload.
    - _Requirements: 17.5, 19.3, 19.6_

- [x] 24. Field map and PDF fill
  - [x] 24.1 Write `backend/src/app/services/medwatch_3500/field_map.py` and `map_form` with tests
    - One explicit entry per mapped field (AcroForm name, XFA `datasets` path, model path, kind), following the
      design table and quirks (root-level `Prod1Name` / `Prod1Dose` / `Prod1Diagnosis`, irregular B6 and F nesting,
      `WeightKG` / `WeightLB` by printed label, `pdt2CosmProf` casing).
    - `map_form(form)` returns AcroForm and XFA dicts: dates via `dates.fda_date`, checkboxes `/1` / `/Off` (XFA `1`
      / `0`), choice display text to the export value from `TEMPLATE.json`, excluding pairs that cannot round-trip.
    - Tests in `backend/tests/unit/services/test_medwatch_form_3500_field_map.py`: every name exists in the template,
      every model `Literal` equals the `TEMPLATE.json` option list, no C, E, Header or Advice field is mapped,
      `mediagent_review` is never mapped.
    - _Requirements: 16.2, 16.3, 21.2, 21.3_
  - [x] 24.2 Write `backend/src/app/services/medwatch_3500/pdf.py` `render_form_3500` with its tests
    - Load via `template.py` with the `FIELD_MAP` names required; decrypt with `""`, `PdfWriter(clone_from=...)`,
      fill each page with `auto_regenerate=False`, set `/NeedAppearances true`.
    - Write the XFA `datasets` stream with `xml.etree.ElementTree` (exactly one element per path).
    - Metadata only: `/Subject` note and `/Keywords` "fda-3500; not-submitted"; no official field, page or XMP change.
    - Re-encrypt AES-256 with an empty user password, a random owner password never logged or stored, and the
      template `/P`; not flattened.
    - Tests in `backend/tests/unit/services/test_medwatch_form_3500_pdf.py`: 239 fields kept, XFA kept, `/P` equals
      -1084, empty user password opens, AES-256, metadata note present, fields still fillable, fill failure raises
      the render error.
    - **Property 10: PDF read-back equals the mapping** (about 25 forms that set every mapped field and option at
      least once; marked slow).
    - _Requirements: 15.4, 16.2, 21.1, 21.2, 21.3, 21.4, 21.5, 21.7, 21.8_

- [x] 25. Migration 064
  - [x] 25.1 Write `backend/src/app/db/migrations/064_medwatch_form_3500.sql` (design steps 1 to 9)
    - Steps: discard columns and `patient_reference`, `export_version` default and legacy relabel, 001 comment fix;
      partial unique index `WHERE discarded_at IS NULL`; append-only `medwatch_external_submissions` with CHECKs,
      index, RLS, grants and the `BEFORE UPDATE` trigger; the replacement status CHECK and
      `medwatch_drafts_submission_guard`; extended audit types; the RPCs (create overload, approve, 5-argument
      export with the 2-argument delegate, discard, record and amend submission); discard returns the assessment to
      `draft` in one transaction with both audit rows; grants and DELETE / TRUNCATE revokes; the fail-closed
      `DO $$` block.
    - Every new patient FK is `ON DELETE CASCADE`; no enum value is added. Do not edit any existing migration.
    - _Requirements: 15.1, 21.6, 22.4, 22.6, 23.2, 23.3, 23.4, 23.7, 24.2, 24.3, 24.4, 24.9_
  - [x] 25.2 Write `backend/tests/unit/db/test_medwatch_form_3500_migration.py` and run the validator
    - Assert at text level each of steps 1 to 9, the CASCADE patient FKs, `service_role`-only grants, no
      `ALTER TYPE ... ADD VALUE`, and the 2-argument export calling the 5-argument one.
    - Run V4 (`cd backend && .venv/bin/python scripts/validate_migrations.py`) and V19.
    - _Requirements: 22.4, 22.6, 23.2, 23.3, 23.4, 23.7, 24.2, 24.3, 24.4, 24.9_

- [x] 26. PostgreSQL contract tests for 064
  - [x] 26.1 Write `backend/tests/integration/test_medwatch_3500_postgres.py`
    - Reuse the notification-centre fixture (`pytest_plugins`, opt-in Docker skip) with 048 to 064 in ledger order.
    - Cover: discard returns the assessment to `draft` with one actionable clinician `adr_review` item, no
      actionable patient item and no email (pin new event versus re-activated original); one active draft, another
      allowed after discard; the guard rejects `submitted` without a submission row, also as `service_role`;
      submission UPDATE fails and no role can DELETE / TRUNCATE it; amendment keeps the original; patient deletion
      cascades; audit tables stay append-only; the 2-argument export delegates.
    - Run V20 (V6 commands with 063 and 064 applied).
    - _Requirements: 22.4, 22.5, 22.6, 22.7, 23.2, 23.3, 23.4, 23.6, 24.2, 24.7_

- [x] 27. MedWatch service and routes
  - [x] 27.1 Extend `backend/src/app/services/medwatch_service.py` with its tests
    - Upgrade on read; create with a service-generated UUID, `default_code` and the 064 create overload; approve
      with stale-revision conflict, gate on the stored form, 422 `MEDWATCH_APPROVAL_INCOMPLETE` and the three
      approval values; `PUT` rejects submitted or discarded drafts.
    - List with `state` filter (`active` default, `submitted`, `discarded`) and `missing_for_approval`,
      `name_warnings`, `current_submission`, attestation text per item.
    - Preview read model (sections in form order, labels from `field_map.py`, provenance, C and E as
      `not_completed_by_mediagent`, `mediagent_review`, template revision / expiry / `may_be_superseded`).
    - PDF export: allowed only for `reviewed` with `approved_at` or `submitted`, not discarded; failing legacy draft
      422 `MEDWATCH_LEGACY_DRAFT_INCOMPLETE`; render, record the 5-argument `exported` event, return bytes only after
      it succeeds; `TemplateMismatchError` 503 with no audit; render failure 502 `FORM_3500_RENDER_FAILED`. JSON
      export relabelled `artifact_type: "fda_3500_draft"` with `form_version`, recording `'json'`.
    - Discard, record submission and amend via the 064 RPCs; `_get_authorized_draft` / `_get_assessment` use
      `.limit(1)` (404 on zero rows, 403 unassigned); RPC error mapping `P0002` 404, `42501` 403, `23514` 422 / 409,
      `22023` 422, else 502 without PostgREST detail. No call to any FDA system; form values never logged.
    - Tests in `backend/tests/unit/services/test_medwatch_service.py`, including audit-before-bytes, no audit on
      mismatch, and **Property 9** service part (save then load through the fake client returns equal `form_data`).
    - _Requirements: 15.4, 15.5, 16.5, 16.6, 19.4, 19.5, 20.1, 20.2, 20.3, 21.1, 21.6, 21.9, 22.1, 22.2, 22.3, 22.5, 22.7, 23.1, 23.5, 23.8, 24.1_
  - [x] 27.2 Add the routes to the clinician MedWatch router with router tests
    - Under `/api/v1/clinicians/me/medwatch-drafts`, thin, `require_role("clinician")`: `GET ?state=`,
      `GET /{id}/preview`, `GET /{id}/export.pdf`, `GET /{id}/export` (relabelled), `POST /{id}/discard`,
      `POST /{id}/submission`, `POST /{id}/submission/amend`.
    - PDF response: `application/pdf`, `Content-Disposition: attachment;
      filename="fda-3500-<first 8 of draft id>-not-submitted.pdf"`, `Cache-Control: no-store`.
    - Tests in `backend/tests/integration/routers/test_clinician_api.py`: 404 / 403, each error code, headers and
      filename, invalid `state`, no bytes when the audit call fails.
    - _Requirements: 15.4, 20.1, 21.1, 21.6, 21.9, 22.1, 22.2, 22.7, 23.1, 23.5, 23.8, 24.1_

- [x] 28. Clinician portal types and services
  - [x] 28.1 Extend `apps/clinician-portal/src/services/clinicians.ts` with its tests
    - Types for the v2 form, `missing_for_approval`, `name_warnings`, `current_submission`, attestation, preview,
      list `state`, discard, submission and amendment payloads.
    - Functions: list by state, get preview, download PDF as a blob with the server filename, discard, record and
      amend submission, approve with the new fields; error codes surfaced without server text.
    - Tests in `apps/clinician-portal/src/__tests__/clinicians-medwatch-3500.test.ts`.
    - _Requirements: 19.5, 20.1, 21.1, 22.1, 22.7, 23.1, 23.8_

- [x] 29. Read-only Form 3500 preview
  - [x] 29.1 Write `apps/clinician-portal/src/components/features/form-3500-preview.tsx` with its tests
    - One `section` per Form 3500 section with an `h3` and a `dl` (mono item number, label, wrapped value or "Not
      provided" in `text-muted`), provenance chips (`AiChip` only for AI-extracted), "Missing for approval" warning
      `Badge` with `Icon` while `draft`, C and E "Not completed by MediAgent", a separate "MediAgent review (not
      part of Form 3500)" panel, the superseded-revision warning, and the fixed footer "Not submitted to FDA by
      MediAgent". No input controls; tokens and primitives only.
    - Tests in `apps/clinician-portal/src/__tests__/form-3500-preview.test.tsx`: section order, "Not provided",
      missing labels, no inputs, review panel, superseded warning.
    - _Requirements: 1.1, 1.2, 1.4, 1.8, 1.15, 15.5, 20.1, 20.2, 20.3, 20.4, 20.5, 20.7_
  - [x] 29.2 Add the print stylesheet with its test
    - `@media print` rules in the clinician portal global stylesheet: `@page { size: Letter; margin: 0.5in }`,
      navigation and actions hidden, `break-inside: avoid` per section, fixed bottom footer.
    - Test in `apps/clinician-portal/src/__tests__/form-3500-print.test.ts` asserting those rules at text level.
    - _Requirements: 20.6, 1.2_

- [x] 30. Edit card for v2 and the approval dialog
  - [x] 30.1 Extend `apps/clinician-portal/src/components/features/medwatch-draft-card.tsx` for v2 sections
    - A, B, D, F and G with the 8.1 patterns (`fieldset` / `legend` groups, selects from API options, B3 "Best
      estimate, confirm", up to 10 F rows, optional product 2) and name warnings beside fields; keep existing
      handlers, `aria-*` and selectors.
    - Extend `apps/clinician-portal/src/__tests__/medwatch-draft-card.test.tsx`.
    - _Requirements: 1.1, 1.2, 1.6, 1.17, 16.1, 17.4, 18.8_
  - [x] 30.2 Add the approval dialog and wire it into the card
    - `apps/clinician-portal/src/components/features/medwatch-approval-dialog.tsx` on the shared `Modal`: missing
      item list, warnings to acknowledge, the D12 checkbox, and the attestation text from the API; sends
      `attestation_version`, `non_serious_attested` and `acknowledged_warnings`; inline `role="alert"` errors.
    - Tests in `apps/clinician-portal/src/__tests__/medwatch-approval-dialog.test.tsx`.
    - _Requirements: 1.16, 17.5, 19.1, 19.3, 19.5, 19.6_

- [x] 31. Download, submission, amendment, discard and states
  - [x] 31.1 Write the download confirmation modal with its tests
    - `apps/clinician-portal/src/components/features/form-3500-download-dialog.tsx` on `Modal`: "MediAgent did not
      submit this report. You submit it to FDA.", then saves the blob under the server filename; JSON stays a
      secondary action.
    - Tests in `apps/clinician-portal/src/__tests__/form-3500-download-dialog.test.tsx`.
    - _Requirements: 1.16, 21.5, 21.9_
  - [x] 31.2 Write the submission, amendment and discard dialogs with their tests
    - `apps/clinician-portal/src/components/features/medwatch-record-dialogs.tsx` on `Modal`: date (max today),
      method, detail for Other, optional reference, attestation; amendment adds a reason; discard asks for a reason
      and says the assessment returns to review; inline `role="alert"` errors; `expected_revision` sent.
    - Tests in `apps/clinician-portal/src/__tests__/medwatch-record-dialogs.test.tsx`.
    - _Requirements: 1.16, 22.1, 22.2, 22.7, 23.1, 23.8_
  - [x] 31.3 Add the Active / Submitted / Discarded switch and read-only states
    - In the `apps/clinician-portal/src/app/(dashboard)/medwatch` page and the draft card: segmented control bound
      to `?state=`; submitted drafts read-only with "Submitted by <clinician> outside MediAgent on <date>",
      amendment history and "Amend record"; discarded drafts read-only with reason and date; wire 29.1, 31.1 and
      31.2.
    - Tests in `apps/clinician-portal/src/__tests__/medwatch-states.test.tsx`.
    - _Requirements: 1.17, 22.5, 22.7, 23.1, 23.5, 23.8_

- [x] 32. Documentation for PR 3
  - [x] 32.1 Update `backend/README.md` and `docs/supabase_setup_guide.md`
    - New routes and codes, the vendored template and re-pin steps, `pypdf` pin, migration 064 (written, not
      applied), and the deploy order: the branch now ships as one pull request, so apply 063, then 064, before
      it merges; its backend is not safe before 064.
    - _Requirements: 24.6_
  - [x] 32.2 Update the clinician portal `README.md`
    - Preview, print, PDF download notice, submission record, amendment, discard and the state switch.
    - _Requirements: 24.6_
  - [x] 32.3 Update the NOT-001 and PV notes
    - NOT-001 specification: discard returns the assessment to review with one clinician `adr_review` item and no
      patient item or email. `.agent/TASKS.md` `PV-001-C` / `PV-002`: PR 3 scope, deploy order and open requester
      checks (V22 to V24).
    - _Requirements: 23.6, 24.6, 24.8_

- [ ] 33. Checkpoint: PR 3 verification
  - [ ] 33.1 Run the PR 3 verification and record outcomes in `PV-001-C`
    - Re-check commands against `backend/README.md`, `CONTRIBUTING.md` and CI. Run V1 to V11 (automatable parts;
      V11 as a computed contrast table) and V16 to V21, plus V23 as the recorded note: lock diff (`git diff --stat
      -- backend/requirements.txt backend/requirements-dev.txt`), `pip-audit` as CI, the V9 palette grep.
    - PDF smoke: a temporary script outside the repository builds a synthetic approved v2 draft, calls
      `render_form_3500`, re-reads the bytes with pypdf (field count, a few `/V` values, XFA present, `/P`, empty user
      password opens), then the script and its output are deleted.
    - Confirm `git diff --name-only <PR 2 head>` adds exactly one migration, `064_medwatch_form_3500.sql`, and edits
      no existing migration. No remote apply, deploy, push, PR or merge.
    - Record every command and outcome in `PV-001-C`. Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 21.7, 24.3, 24.5, 24.8, 24.9_

## Notes

- **Requester verification (not executable tasks):**
  - V12: authenticated manual checks with synthetic accounts and screenshots per R1.19 (patient en-US / es-MX at 320,
    360 and 430 px; clinician at 1024, 1280 and 1536 px; keyboard, 200% zoom, reduced motion, safe areas).
  - V13 / D9: Spanish-fluent sign-off of the es-MX question, caution, confirmation and notification wording.
  - V14: applying 063 to any remote environment, which needs explicit authorization naming that action.
  - D1, the clinician-deletion policy, stays open.
- No new dependencies. The properties run as exhaustive or table-driven tests, because neither Hypothesis nor
  fast-check is installed.
- Before PR 2's description is written, record whether the G9 FK change shipped, based on the baseline.
- **PR 3 requester verification (not executable tasks):**
  - V22: open a downloaded PDF from a synthetic draft in Adobe Acrobat Reader and macOS Preview; confirm values show
    in both, including weight units, checkboxes and dates, the form stays fillable and printable, and no official
    field carries added text.
  - V23: confirm the copyright position if task 19.1 left it unsettled.
  - V24: apply 064 to any remote environment only with explicit authorization naming that action.
- Deploy order: PR 1 to PR 3 ship as one pull request (decided 2026-10-13). Merging deploys the backend, and the
  backend calls 063 and 064 objects, so the requester applies 063, then 064, on explicit authorization before the
  pull request merges. The deployed backend keeps working on 064 (every 048 function keeps its signature).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "3.1", "4.1", "7.1"] },
    { "id": 1, "tasks": ["2.2", "3.2", "4.2", "4.3", "7.2", "8.1"] },
    { "id": 2, "tasks": ["2.3", "4.4", "5.1", "8.2"] },
    { "id": 3, "tasks": ["2.4", "5.2", "5.3", "8.3"] },
    { "id": 4, "tasks": ["5.4", "6.1"] },
    { "id": 5, "tasks": ["6.2", "6.3"] },
    { "id": 6, "tasks": ["6.4", "9.1"] },
    { "id": 7, "tasks": ["11.1"] },
    { "id": 8, "tasks": ["11.2"] },
    { "id": 9, "tasks": ["12.1"] },
    { "id": 10, "tasks": ["12.2"] },
    { "id": 11, "tasks": ["12.3", "13.1"] },
    { "id": 12, "tasks": ["13.2", "14.1"] },
    { "id": 13, "tasks": ["13.3", "14.2"] },
    { "id": 14, "tasks": ["15.1"] },
    { "id": 15, "tasks": ["17.1", "18.1"] },
    { "id": 16, "tasks": ["19.1", "19.2", "20.1", "21.1", "28.1"] },
    { "id": 17, "tasks": ["19.3", "20.2", "22.1", "23.1", "23.2", "24.1", "29.1"] },
    { "id": 18, "tasks": ["24.2", "25.1", "29.2", "30.1"] },
    { "id": 19, "tasks": ["25.2", "26.1", "27.1", "30.2", "31.1", "31.2"] },
    { "id": 20, "tasks": ["27.2", "31.3", "32.1", "32.2", "32.3"] },
    { "id": 21, "tasks": ["33.1"] }
  ]
}
```
