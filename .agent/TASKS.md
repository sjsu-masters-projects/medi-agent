# MediAgent — Project task board

> **Active plan:** [October 18 deployed-verification campaign](../docs/deployed-recheck-2026-10-11.md#october-18-deployed-verification-campaign) for the remaining `Verify deployed` rows, including #191’s merged features; resolve its recorded appointment and provenance defects, then continue CLN-003 slice G, PLAN-002 and DEMO-001 · [accepted PAT-005 contract](specs/pat-005-clinician-approved-today-feed-plan.md)
>
> **Updated:** October 20, 2026 · **Feature freeze:** December 4, 2026
>
> **Target:** A working, polished university-expo master's project using fictional patient and clinician accounts. No real-patient or real-clinician recruitment, VC pitch, or production qualification is required.

This is a Jira-style execution board, not a chronological work log. Detailed
requirements are mandatory context: read the selected issue in its dedicated
specification or [backlog acceptance requirements](specs/project-backlog-acceptance.md)
before changing code. Product boundaries remain in [PROJECT.md](PROJECT.md),
architecture in [ARCHITECTURE.md](ARCHITECTURE.md), ownership in [TEAM.md](TEAM.md).

## Status rules

| Status | Meaning |
| --- | --- |
| Backlog | Not scheduled; scope/dependencies remain recorded. |
| Ready | Bounded next increment can start; unassigned work needs a claim. |
| In progress | Implementation or acceptance underway. |
| In review | Implemented/locally checked; PR review, CI or merge remains. |
| Verify deployed | Merged/deployed; specified live check not yet recorded. |
| Blocked | Named dependency or failure prevents the next step. |
| Done | The stated slice is merged and agreed verification is recorded. |

Done applies to the named slice, not every future feature in an epic. Branch tests,
deployment success and live functional acceptance are different evidence levels.
P1 = next demo increment; P2 = subsequent demo work; P3 = optional extension, not an expo blocker.
No remote migration, deployment, merge or clinical publication is authorized by
editing this board.

MedWatch scope is draft, clinician review/approval, preview/export and retained
discard history only. Actual FDA submission and recording an external submission
are out of scope for this project; neither is an expo acceptance requirement.
Disposable-account deletion testing is excluded by the requester October 20;
retain existing deletion safeguards and automated regression coverage.

## Current release and live status

PR #205 continuation: disposable-account deletion testing is excluded. Actual
Wi-Fi outage reproduced **DV-017**: the server saved one completed reply, while
the browser stayed Connected/typing until reload. #205 adds offline/online
re-subscription and a visible-socket heartbeat; tests pass locally, **not deployed**.
Accessibility checks found **DV-018** false initial Records zero count,
**DV-019** 40px chat/agenda targets, and **DV-020** low-contrast clinician secondary
text; local fixes and regression tests are in the same PR. The untouched deployed
Nora session began at 13:20:29 Pacific; one-time renewal recheck is scheduled for
14:25 October 20. No completed live-renewal result is claimed yet.

October 20: #202 merged as `7c4d9f9`; main CI, both Vercel deployments and the
backend deployment succeeded. Serving revisions: backend `00173-t5q`, chat worker
`00016-29q`. **DV-007, DV-008, DV-014, DV-015 and DV-016 pass their recorded live rechecks.**
Morgan completed a Spanish typed intake at 390px: private answers/preview survived
reload, consent remained unchecked until explicitly accepted, and confirmation
produced exactly one canonical completed task and one clinician-review ADR draft.
Spanish saved status/accessible region persisted after reload. English preference
was restored. Hannah's en-US/es-MX original-symptom/recorded-medicine labels and
read-only unknown answers persist after reload. Physical voice, forced outage,
quiet socket renewal remain; no all-feature completion claim.
[Post-merge evidence](../docs/deployed-recheck-2026-10-11.md#october-20--post-202-live-acceptance).

PR #202 [grouped acceptance continuation](../docs/deployed-recheck-2026-10-11.md#pr-202-grouped-acceptance-continuation--october-19):
PV-001-B/C Spanish “No sé” answers persisted in Hannah's history and Elena's
patient-attributed evidence with score 4 / Possible unchanged. Exact audit events
and requester-approved LLM-assisted Spanish demo wording review pass. ADR answer
acceptance and MedWatch draft/export acceptance are Done; disposable-account
deletion is not an acceptance requirement.
PAT-001-A competing-tab busy/recovery and navigation-disconnect completion pass;
the later English and Spanish unfocused wellness replies did not inherit PAT-004's
dismissed document. A 306-second connected-view observation followed by a successful
turn passes (not server-proven socket identity); forced network outage and
unavailable/deleted-source live tests remain. Morgan's clinician calendar export
passes; a later patient-side recheck also loaded Pacific time correctly, retained
it after reload and exported the matching calendar file. The earlier intermittent
failure's cause remains open. PAT-002-B is activated on both authorized services;
Morgan's first confirmed report revealed DV-015 duplicate keys; the post-#202
Spanish confirmation now verifies one task and one case. Typed Spanish/390px and
saved-state checks pass; physical voice, denial/outage and the wider mobile matrix
remain. DV-014 range/clinic transitions show loading before scope-matched data.

October 19 evening recheck after merged #196: **DV-010 and DV-013 pass live**.
The exact glucose draft editor receives focus; a fresh private-message notification
changes unread 37 → 38 → 37 on destination opening and stays read after reload.
DV-012 has successful Rajeev/Morgan risk-detail loads and a clean bounded revision
log window; direct null-row execution remains unproven. These results supersede
the earlier pending statements below. COM-002 remains Verify deployed for its
remaining audit, authorization, retry, reminder and bilingual acceptance checks.
See [the recorded recheck](../docs/deployed-recheck-2026-10-11.md#pr-196-deployed-recheck--october-19-evening).

| Area | Current state | Remaining boundary |
| --- | --- | --- |
| Main deployment | Main `7c4d9f9` (#202): CI, both Vercel apps, backend `00173-t5q` and worker `00016-29q` deployed successfully October 20. Spanish confirmation and DV-007/014/015/016 sampled live checks pass. | Remaining acceptance paths stay tracked individually. [Evidence](../docs/deployed-recheck-2026-10-11.md#october-20--post-202-live-acceptance). |
| PAT-005 core | Synthetic Morgan/Elena loop verified live, including V2 continuity, six barriers, audit, Spanish V3 and non-scheduled-day absence. A second loop ran October 13 for the synthetic test patient: a discharge summary was extracted, its draft reviewed (STOP medication removed, changed dose applied, routes chosen, both languages checked) and published, and Today shows the four activities ([deployed recheck](../docs/deployed-recheck-2026-10-11.md#ai-005-production-check-october-13)). | V4 approved October 10 in English and Spanish under LOC-001 after removing a duplicate-upload overlap ([evidence](specs/loc-001-bilingual-approved-wording.md#verification--2026-10-10-synthetic-environment)). Presentation follow-up PAT-005-L passed October 18. |
| Patient-upload review | [#138](https://github.com/sjsu-masters-projects/medi-agent/pull/138) deployed; pending/rejected exclusion, approval eligibility/queue handoff and exact-document link verified | Negative preview/publication guards have API/PostgreSQL evidence, not a newly repeated live blocked publication. |
| Human messaging | [#139](https://github.com/sjsu-masters-projects/medi-agent/pull/139) deployed; migration checked; bilingual replies, actual sender/clinic, unread and reload persistence verified | Concurrency/reassignment/multiple-recipient isolation tested in isolated PostgreSQL, not repeated by the four-message live run. |
| Synthetic database schema | #159 restores canonical local files 059/060 and `071_confirmed_symptom_handoff.sql`, accounting for the previously unexplained 071 filename (DV-009). Prior application records remain; 076 was observed independently in the hosted ledger. | Complete filename/checksum reconciliation, including 077/078, remains unverified. Preserve applied bytes; no remote SQL is authorized by this board. |
| Scheduled jobs | Three Cloud Scheduler triggers, all enabled: document ingestion (every 5 minutes), weekly reference refresh (Sundays 03:00 America/Los_Angeles) and reminder dispatch (every 15 minutes UTC, resumed October 11). EMAIL-001's `email_dispatch` runs after each reminder run with its own run record; all 90 recorded email runs and the latest 110 reminder runs succeeded (checked October 12). The nightly ADR scan trigger was deleted October 11. After [#151](https://github.com/sjsu-masters-projects/medi-agent/pull/151) deployed, each job logged a successful `scheduled_job.finished` line ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). | The first Sunday October 18 weekly refresh passed (OPS-004); the first reminder actually due still needs observation. |
| Patient symptoms | #202 deployed; flags retained. Morgan's Spanish typed confirmation produced one completed canonical task and one exact ADR draft, verified read-only; saved Spanish status and 390px layout pass. | Physical voice, denial/outage and wider mobile matrix remain. Candidate-2 stays separate. [Rollout](../docs/pat-002-b-rollout.md). |
| ADR patient information loop | Hannah en-US/es-MX answers, exact patient-attributed audit, demo wording review and MedWatch lifecycle/export/audit pass. #202 DV-007/008 evidence attribution and source labels pass live. | Disposable-account deletion excluded; inline viewer DV-005 is a separate presentation issue. |

Evidence: [deployed recheck](../docs/deployed-recheck-2026-10-11.md),
[PAT-005 acceptance](../docs/pat-005-final-acceptance-2026-10-10.md),
[portal review](../docs/portal-ui-ux-review-2026-10-10.md),
[scheduling contract](specs/sch-001-appointment-scheduling.md),
[conversation contract](specs/com-001-two-way-conversations.md).
This is prototype acceptance, not clinical/compliance/production certification.

## Current sprint

PAT-002-B local implementation, activation prerequisites and verification are in
[the plan](specs/pat-002-b-confirmed-symptom-intake-plan.md) and
[October 12 evidence](../docs/pat-002-b-acceptance-2026-10-12.md).

| Issue | Priority | Status | Owner | Next observable result |
| --- | --- | --- | --- | --- |
| PAT-005-L — Presentation recheck | P1 | Done | Rajeev | Saved-locale Today controls already verified. October 18: Rajeev's retained byte-identical synthetic copy was visible in patient Records and Elena's Documents/Review Queue, with a clear duplicate-extraction-skip explanation, no false empty-facts review, original preview/download control, and a fitted 390 px patient sheet. No new upload needed. [Deployed evidence](../docs/deployed-recheck-2026-10-11.md#task-verdicts). |
| PV-001-B — ADR patient answers | P1 | Done | Ganesh | Both-language answers, exact patient audit and demo wording review pass. October 20 DV-007 live: repeated evidence retained, current/different follow-up labels and truthful date scope visible; score 4 / Possible unchanged. [Evidence](../docs/deployed-recheck-2026-10-11.md#october-20--post-202-live-acceptance). |
| PV-001-C — ADR loop gap fixes | P1 | Done | Rajeev | [Requirements](specs/pv-001-c-adr-loop-gap-fixes/requirements.md). Answer/audit/demo wording and MedWatch lifecycle/export checks pass. #202 DV-007/008 pass live in both languages after reload. Disposable-account deletion and FDA submission/recording excluded by requester. DV-005 viewer and DV-006 reads remain separate UX/operations issues, not missing ADR-loop implementation. [Evidence](../docs/deployed-recheck-2026-10-11.md#october-20--post-202-live-acceptance). |
| PAT-002-B — Confirmed symptom intake | P1 | Verify deployed — remaining voice/outage | Tushar + Ganesh lanes | #202 deployed on backend `00173-t5q` / worker `00016-29q`. Spanish private draft/preview, unknown versus declined, unchecked consent, confirmation and reload passed at 390px. Read-only counts prove one completed canonical task and one exact ADR case; DV-015 and saved-region DV-016 closed for this scenario. Remaining: physical voice, denial/outage and wider mobile/accessibility matrix; candidate-2 pending. [Live evidence](../docs/deployed-recheck-2026-10-11.md#october-20--post-202-live-acceptance). |
| PAT-002-C — Real symptom timeline | P2 | Blocked | Unassigned; Tushar + Jeevan lanes | Confirmed-report contract from B, then actual saved reports and authorized clinician detail; no invented history. |
| SCH-001-V — Canonical scheduling acceptance | P2 | Verify deployed | Tushar + Jeevan | Prior confirmed visits and calendar exports pass. October 20 DV-014: Today→week and All→Willow show loading without stale visits; week lists Rajeev Oct 20/Morgan Oct 22, then Willow finishes with its scoped empty result. Earlier intermittent DV-001–003/006 root cause remains open; a clean new-revision error window is not RCA. [Evidence](../docs/deployed-recheck-2026-10-11.md#october-20--post-202-live-acceptance). |
| PAT-001-A — Terminal chat-turn recovery | P2 | In review — DV-017 outage fix | Integration + patient lane | Prior reload/busy/navigation/Spanish checks pass. October 20 actual Wi-Fi outage: one server-completed turn (attempt 1) remained typing in browser until reload. #205 adds offline/online handling and stale-OPEN heartbeat without resending; 102 focused chat tests pass locally, including hidden-tab and simulated 3500-second renewal. Live untouched session renewal recheck scheduled 14:25 Pacific; fix still needs merge/deploy/retest. Retry-exhaustion/legacy deployed acceptance remains separate. [Evidence](../docs/deployed-recheck-2026-10-11.md#october-20--pr-205-outage-accessibility-and-rca). |
| PAT-004 — Focused-document chat | P2 | Verify deployed | Rajeev + Ganesh/Tushar | October 19: exact lipid-panel answer grounded in report values/page/source survived in-flight reload and agreed across tabs. Original → recheck context replacement and dismissal persisted after reload. Later unfocused English/Spanish sleep-habit replies did not inherit lipid values or source citations. Remaining: deleted/unavailable sources and Spanish document-grounded acceptance. [Contract](specs/pat-001-a-nora-turn-recovery.md) · [grouped evidence](../docs/deployed-recheck-2026-10-11.md#pr-202-grouped-acceptance-continuation--october-19). Saved source lines are plain text; clickable per-message citations are not asserted. |
| CLN-003 — Clinicians across multiple clinics | P1 | In progress | Rajeev | A–F merged (#176/#178/#182/#183); prior requester live checks covered Elena's two-clinic membership, clinic roles/codes, patient links, roster filters and invite clinic selection. #186/#187 include authorization, hosted-grant harness and schedule/settings consistency fixes; recheck current screens rather than repeat obsolete branch handoffs. Remaining: **G** shared clinical core and **H** per-link plans (PLAN-002); deployed cross-clinic conflict/authorization and handover boundaries in the [spec](specs/clin-003-multi-clinic-clinicians.md). No handover tool is claimed. Settings uses shared confirmation UI; native-confirm and missing harness claims are retired. Migration 070's receipt is not independently re-audited here. **Pending es-MX drafts, not approved:** `en {clinic}` on visits/offers and `Clínica` in ICS; LOC-001 review remains. |
| LOC-003 — English-first clinician review of Spanish content | P1 | Verify deployed | Jeevan (assigned by the requester October 16) | #181/#186/#187 merged; 067/068 applied per prior records. English display facts, guarded back-translation, attestation and non-blocking per-message translation implemented. [Contract, remaining scope and draft copy](specs/loc-003-english-first-clinician-review.md); clinical names/numbers/negations remain guarded. Remaining: deployed acceptance; environment-independent translation mocks; patient preview, evidence glosses, Nora transcript translation, reply preview, model-info treatment and translation storage/retention refinements as specified. No new background-send translation task: #187 already removes model calls from send/read paths. **Pending es-MX wording drafts (not approved; LOC-001 bilingual review), patient Profile care-team flow:** `Agregar un miembro del equipo de atención`, `Ingresa el código de invitación que te dio tu clínico.`, `Agregar tu equipo de atención`, `Código de invitación`, `Usa el código que te dio tu clínico.`, `Agregar a mi equipo`, `Agregando...`, `Se agregó a tu equipo de atención. Ya está disponible.`, plus the reworded empty-state, error and onboarding lines in `profile-copy.ts`. | See DV-004 for the October 18 deployed source-label mismatch.
| AUTH-002 — Sign-in session handling across tabs, inactivity limits | P1 | Verify deployed | Rajeev | Cause of the second-tab sign-out: two tabs refreshed with the same rotating refresh token, the loser failed, and the failure cleared the shared session. Now: one refresh across tabs (`navigator.locks`, localStorage-timestamp fallback) that re-reads storage and adopts a newer session; a failed refresh re-reads storage and signs out only on a confirmed rejection (network and 5xx keep the session); a 401 adopts the stored session or does one refresh and retries once; storage-event and BroadcastChannel sync (a sign-out in any tab signs out all); 5-minute floor between refreshes kept in both refresh hooks. Limits enforced in the browser only: clinician 2 h idle (warning modal 2 minutes before, "Stay signed in") and 12 h absolute; patient 30 days idle and 90 days absolute, silent, with a login notice. Shared `lastActivityAt` (one write per 30 s), `signedInAt` kept across refreshes. Defaults in `packages/shared/src/utils/session-limits.ts`, optional `NEXT_PUBLIC_*` overrides in both `.env.example` files. Backend: 30 s JWT leeway; a session response never carries `expires_at` 0 (falls back to `expires_in`, then the token `exp`), and the client derives a missing expiry from the token. Legacy `access_token` localStorage fallbacks removed. **Evidence:** patient portal 713 and clinician portal 604 vitest tests pass, lint and `tsc --noEmit` clean; backend `test_security.py` and `test_auth_service_session_expiry.py` pass with ruff, format and mypy. [#190](https://github.com/sjsu-masters-projects/medi-agent/pull/190) merged. Deployed recheck pending: two clinician tabs stay signed in across a refresh; sign-out in one tab signs out the other; MFA (aal2) survives a second tab; the idle warning appears. **Pending es-MX wording draft (not approved; LOC-001 bilingual review):** `Cerraste sesión por un periodo de inactividad.` (patient login notice, `auth-entry-copy.ts`). October 19 deployed check: two Elena tabs loaded and remained signed in after concurrent reload; forced token-rotation race, sign-out sync, MFA survival and idle warning remain. [Live evidence](../docs/deployed-recheck-2026-10-11.md#task-verdicts). |
| PLAN-002 — Care plans per care team | P1 | Backlog | Jeevan (assigned by the requester October 16) | Decided October 13: each care team (patient, clinician, clinic) owns its own plan, versions, draft and approval, replacing one combined plan per patient. Shared reviewed medications, allergies and conditions; patient uploads routed to a chosen care team ("Not sure" uploads are claimed whole by any of the patient's care teams); Today merges every approved plan, labelled by care team; cross-plan duplicate, conflict, stop and interaction checks block publication. The reviewing clinician can change or remove their own item, keep both with a written reason, ask the other care team through a review item and message, or publish without the item; the other team is always told and the patient's current Today is unchanged until it is resolved. When a care team ends (decided), its activities stay in Today as unowned until a clinician adopts or retires them; existing plans migrate to their approving care team. [Spec and open decisions](specs/plan-002-care-plans-per-care-team.md). Depends on CLN-003 slice A. |
| DEMO-001 — Expo patient/clinician journey | P1 | Backlog | Rajeev + team | After selected features pass, create a fresh fictional patient and clinician, link them, build an attributable history through supported flows, and rehearse the same accounts. No account creation/reset is authorized by this row. |

### DEMO-001 acceptance

- Start with one blank fictional patient and one blank fictional clinician; record the intended clinic and assignment. No real people or health records are required.
- Build a coherent synthetic history: appointments, clinician documents, patient-upload review, approved care-plan revisions, Today reminders/completions/barriers, confirmed symptoms/ADR review where implemented, and private two-way messages.
- Use normal application flows for approvals, responses and audit events. Do not fabricate completed features, clinician signatures, audit history or backdated encounters through ad hoc SQL.
- Prepare a stable historical baseline plus a small live demonstration segment; show which events happened during rehearsal versus the live expo.
- Rehearse patient mobile and clinician desktop, English/Spanish UI and reviewed clinical content, persistence and source links. Clearly label any unavailable/optional flow.
- Keep a demo script, expected screen states, recovery steps and fallback recording in the linked demo guide. Preserve existing QA accounts/history; any remote creation/reset needs separately scoped authorization.

The demonstrator operates both fictional roles. Portal approval boundaries remain;
this is functional demonstration, not independent clinical validation.

### LOC-001 acceptance

- [x] A draft from Spanish sources shows Spanish (from source) and English (AI translation) side by side; approval stays blocked until every item is checked in both languages.
- [x] A translation that changes a number, dose or medication name is discarded and leaves the item untranslated for retry or manual wording.
- [x] Approval projects both languages and the audit event records each item's source language and wording origin.
- [x] Today and Reminders render approved wording in the saved language with identical completion state; reminder scheduling is unchanged.
- [x] Older single-language items are labelled with their language instead of mixing silently.
- [x] Existing plans refreshed by review only: open draft translated, approved single-language plan re-drafted; no approved row edited.
- [x] Local checks (backend, PostgreSQL contract, both portals and builds) and synthetic-environment verification ([evidence](specs/loc-001-bilingual-approved-wording.md#verification--2026-10-10-synthetic-environment)).
- [x] Record titles: drafted per language from the existing summary/topics (no numbers, no patient name, bounded attempts); Records and clinician lists show them with the file name kept; missing column tolerated before migration 050.
- [x] Clinician patient detail shows approved English wording; reconciliation still compares source text.
- [x] Migration 050 applied (authorized); worker backfill titled 18/18 eligible documents; Records (English) and clinician Documents verified in the browser. Spanish titles verified in data, not yet through a saved-language switch.
- [x] #145 merged (`0cf4c93`); CI, backend Cloud Run and both Vercel production deployments succeeded.
- [x] Deployed: switch the patient's saved language in Profile and observe Today change ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)).
- [x] Deployed: approve a new bilingual draft from the clinician portal. October 13, Elena Park approved the synthetic test patient's discharge draft after checking every item in English and Spanish and re-translating the changed lisinopril item ([deployed recheck](../docs/deployed-recheck-2026-10-11.md#ai-005-production-check-october-13)).
- Optional, not part of acceptance: clinician review of the second synthetic patient's bilingual V3 draft (a clinician decision).

### PAT-005-L acceptance

- [x] Saved es-MX updates Today chrome/actions/barriers and, since LOC-001, approved bilingual wording; reminder times stay unchanged ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)).
- [x] The retained October 14 byte-identical synthetic copy displays skipped extraction in Rajeev's patient Records and Elena's clinician Documents/Review Queue; patient detail opens the original preview and download control, without a false empty-facts review.
- [x] Record these observations in the [deployed acceptance report](../docs/deployed-recheck-2026-10-11.md#task-verdicts), then close this slice.

#140 is deployed. No new migration/reset/publication needed. V4 is now active,
approved in both languages under LOC-001; V3 history is preserved.

### PV-001-B acceptance

- [x] Implementation and author-reported staging/local-branch acceptance in #136.
- [x] Resolve conflicts and integrate with current human/Nora separation and language controls (merged October 12).
- [x] Review and required CI; main CI and deployment succeeded for the merge.
- [x] Authorized rollout: migration 047 applied.
- [x] Patient answers → clinician evidence/score through the deployed portals (Hannah's synthetic en-US answer, October 18; [evidence](../docs/deployed-recheck-2026-10-11.md#task-verdicts)).
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

## Done — accepted slices

| Issue | Owner | Delivered scope | Evidence / limit |
| --- | --- | --- | --- |
| AI-005 — Agent quality: documents, explanations, triage, OCR | Rajeev + Ganesh | Row-preserving extraction of results, vitals, immunizations, procedures, appointments and medication actions grounded on their printed row; stop/changed-dose care-plan blockers; explanations for every type with a number check in both languages; critical-result clinician alert (059–061); production triage eval (36 cases, 92% accuracy, 100% safety); phone-photo OCR; patient Records results; one Spanish register (tú); results card on Nora's document answers (062) ([spec](specs/ai-005-agent-quality.md)) | #161–#164, then #166–#168 and #170 from the October 13 production check: heading-named results kept, medication evidence from its own lines, no doubled dose in titles, no boilerplate instructions, one approval line on Today, bedtime/morning reminders. Verified on production October 13 ([deployed recheck](../docs/deployed-recheck-2026-10-11.md#ai-005-production-check-october-13)). Follow-ups are AI-006. |
| EMAIL-001 — Account and selective notification emails | Rajeev | Clinician invitations, patient verification, password reset in both portals and both languages, unread-message and appointment notices, opt-out ([contract](specs/email-001-email-flows.md)) | #152, #156, #157 (migrations 057/058); verified on production October 12 ([evidence](../docs/deployed-recheck-2026-10-11.md#email-001-on-production-october-12)) after the Vercel anon-key fix; Resend shows every recent send Delivered (October 13). Limits: the first invitation landed in Spam; MFA after a reset not exercised. |
| LOC-001 — One language setting, bilingual approved wording | Rajeev | Care-plan wording drafted and approved in en-US and es-MX together; Today/Reminders follow the saved language; bilingual record titles ([spec](specs/loc-001-bilingual-approved-wording.md)) | #145; Profile language switch verified October 11 and a new bilingual draft approved on the deployed clinician portal October 13. Follow-ups are LOC-002. |
| UX-003 — Invitation, roles and copy fixes | Rajeev | One primary action on invitation sign-up, Team & Roles invitations for clinic admins only, Copy buttons with a clipboard fallback | [#156](https://github.com/sjsu-masters-projects/medi-agent/pull/156); verified on production October 12 as provider Elena and clinic admin Carmen. Not blocking: non-admins still see a per-member menu the server rejects. |
| UX-004 — Clinician date format and fact labels | Rajeev | en-US clinician dates everywhere and extracted facts labelled by type | Merged with AI-005 (#161); verified in the clinician portal October 13. |
| PAT-PROFILE-001 — Optional profile gender | Patient lane | Optional gender with a Not specified choice that clears a saved value; not required signup data | [#141](https://github.com/sjsu-masters-projects/medi-agent/pull/141), [#153](https://github.com/sjsu-masters-projects/medi-agent/pull/153); production save-and-reload of a value and of Not specified verified October 11 ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). |
| OPS-003 — Scheduled job correctness and run logs | Rajeev | Weekly refresh due after six days with documented conditions seeded; reminders for `confirmed` visits, reschedule-aware keys, contiguous windows, conflict fallback, skipped counts; nightly ADR scan retired; `scheduled_job.started`/`finished` run logs ([runbook](CLOUD_INFRASTRUCTURE_GUIDE.md#5-scheduled-jobs-cloud-scheduler-and-run-logs)) | [#151](https://github.com/sjsu-masters-projects/medi-agent/pull/151); requester resumed reminder dispatch and deleted the ADR trigger October 11; first logged runs succeeded: reminders (first-run window, 3 inactive schedules skipped), ingestion, and a manual refresh that seeded 13 conditions and updated 10 subjects ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). The refresh then found no topic for 13 of 29 condition lookups: Spanish was searched with English names, only the first search hit was considered, and qualifiers such as "mild persistent" or "of the knee" defeated the search; some first hits were narrower topics. Fixed in [#153](https://github.com/sjsu-masters-projects/medi-agent/pull/153): best match among several hits, a qualifier fallback, and the Spanish page resolved from the English topic. |
| SEC-002 — GitHub security and code-quality findings | Rajeev | Next.js 16.3.8 in both portals, `google-cloud-aiplatform>=1.133.0` on every lock marker, four CodeQL quality fixes, 8 of 14 AI findings fixed (4 already resolved, 2 not applicable) | [#151](https://github.com/sjsu-masters-projects/medi-agent/pull/151); after merge, 0 open Dependabot alerts, 0 open code-scanning alerts and 0 open CodeQL quality findings. Open requester decision: malware scanning, Dependabot security updates and secret-scanning push protection are disabled. Not a security certification. |
| NOT-001 — Notifications and clinician alerts | Rajeev | Recipient-scoped centre, shared authorized work and private-message notifications ([contract](specs/not-001-notification-centre.md)) | #148 and #196 merged. DV-013 passed live October 19 evening: fresh Rajeev→Elena message raised unread 37→38; opening its exact thread returned it to 37, persisted after reload, and left unrelated unread/action counts intact. [Evidence](../docs/deployed-recheck-2026-10-11.md#pr-196-deployed-recheck--october-19-evening). |
| NOT-002 — Notification follow-ups | Rajeev | Compact lists, one unread count, real times for existing work, partial "Mark all read", account deletion through conversations/offers, page-proportional reads, Earlier messages, appointment response rule, one item per answered offer, consistent refreshes (migrations 052–056, applied October 11) | [#149](https://github.com/sjsu-masters-projects/medi-agent/pull/149); local end-to-end check plus deployed acknowledgement, bulk read, matching counts and Spanish copy ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). Follow-ups are NOT-003. |
| UX-001 — Both portal UI/UX polish | Rajeev; lane review | Inventory, simplified content, saved patient language, responsive layouts and accessible dialogs | [#141](https://github.com/sjsu-masters-projects/medi-agent/pull/141); screens since replaced by UX-002, rechecked together on the deployed portals ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). |
| UX-002 — Reference-led portal redesign | Rajeev | Reference-led patient and clinician redesign with responsive and wording follow-up ([requirements](specs/ux-002-reference-redesign.md)) | #142–#145 ([overhaul checks](../docs/ux-002-overhaul-verification.md)); deployed screens at 390 and 1280 px without errors or horizontal scrolling, both patient locales ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). |
| NORA-001 — Nora answers every message | Rajeev | Relative model deadline under uvloop, a triage decision on every follow-up, document handoff from Records, message language labels | [#146](https://github.com/sjsu-masters-projects/medi-agent/pull/146); deployed chat answered every message in English and Spanish ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). |
| NORA-002 — Grounded, plain-language Nora | Rajeev | Shared MedlinePlus/DailyMed/RxNorm cache, record and document tools with server-written sources, daily conversations, replies in the language the patient uses, female Spanish voice, AI-004 safety changes ([spec](specs/nora-002-grounded-answers.md)); supersedes RAG-001 | [#147](https://github.com/sjsu-masters-projects/medi-agent/pull/147); deployed answers grounded in the record with dated MedlinePlus and DailyMed sources, Spanish and English regardless of the app setting ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). Voice on a phone is VOI-001; refresh cadence fixed in OPS-003. |
| DOC-001 — Board and documentation cleanup | Rajeev | #141 routing/evidence cleanup merged. October 11: hand-written migration list replaced by the ledger script in CONTRIBUTING; ARCHITECTURE, docs map and READMEs updated for NORA-002 and NOT-001; retired drug-RAG docs removed; false allergy/duplicate-therapy rule claim corrected; HANDOFF traps recorded. October 12: EMAIL-001 spec condensed from rollout handoff to contract, operations and production status; Supabase guide, architecture and scheduler runbook updated for the deployed email rollout. October 13: tracker refreshed line by line, completed rows moved to Done, stale evidence notes corrected, October 13 production evidence recorded and superseded untracked notes removed. Repeat per PR, not as a separate task. | Kept current per PR from now on. |
| PAT-005 — Controlled care-plan → Today loop | Rajeev; portal support | Fresh synthetic uploads, grounded draft, protected source/review/blockers, approval, Today, completion/barriers and clinician follow-up | [Acceptance report](../docs/pat-005-final-acceptance-2026-10-10.md). |
| PAT-005-A/B/D/E/G/I/K — Draft and publication safeguards | Rajeev | Diagnostics, draft visibility, active/proposed/source review, locale/medication attestation, incomplete evidence, overlaps and exact preview | Merged #114–#116, #118–#122, #124, #125; durable [PAT-005 specification](specs/pat-005-clinician-approved-today-feed-plan.md). |
| PAT-005-C/F/J — Fresh scenario and continuity | Rajeev | V1 stays active until V2 approval; unchanged identities/reminders/history retained; changed activity gets fresh identity; six barriers and audit | Access-isolation closure requester-confirmed, with recorded denial/regression support; not blanket qualification. |
| PAT-005-H — Reminder usability | Rajeev; patient lane | Patient-selected valid days/times, cancel, saved timezone, safe PRN/unknown/event handling | #124 plus cadence fixes; recorded live reminder acceptance. [#170](https://github.com/sjsu-masters-projects/medi-agent/pull/170) (October 13) treats "at bedtime", "nightly" and "every morning" in both languages as once daily, so those approved activities offer a reminder. |
| PAT-005-S — Spanish, cadence and batching | Rajeev | Reviewed Spanish V3, no duplicate medication, Saturday weekday activity absent; 5/5 ingestion and quiet-window consolidation | Core accepted; full interface parity remains PAT-003/UX-001. |
| PAT-005-R — Patient-upload review gate | Rajeev | Pending/rejected source exclusion, approval queues generation, exact-document deep link, V4 blocked on overlap | #138; approved V3/history preserved. |
| COM-001-A — Human message foundation | Jeevan | Clinician compose/inbox and human/AI distinction | Merged #128/#129; integrated into later addressed threads. |
| COM-001-B — Private two-way threads | Rajeev; Jeevan/Tushar review | Explicit linked clinician, real sender/clinic, replies, paging/unread, audit/idempotent retry | #139; bilingual live persistence; not a shared clinic inbox. |
| PV-001-A — Audited ADR review | Ganesh | Deterministic Naranjo inputs, separate model/reviewer state, review/dismiss/information request and assignment/audit guards | Merged #123/#134; full confirmation/reassessment loop remains partial. |
| SCH-001 slices 1–6 — Implementation | Tushar + Jeevan | Offers, accept/decline/alternative/cancel, locales/timezones, booking/expiry guards and one-time calendar export | Merged #97/#98/#133; canonical final recheck remains SCH-001-V. |
| OPS-001 / OPS-002 — Demo ingestion operation | Rajeev | Scheduled private-source worker, PDF/image/TIFF/preview lifecycle and ten completed observations | [Worker guide](../docs/document-ingestion-worker.md); demo proof, not capacity certification. |
| INT-001 — Clinical facts/provenance | Rajeev | Candidates, citations, lineage, review and append-only audit | [Provenance contract](../docs/clinical-facts-provenance.md). |
| INT-003 — EHR-initiated SMART sandbox | Rajeev | Authorized PKCE launch/callback and provenance-backed candidate import/review handoff | Recorded live public-sandbox success; standalone issue remains INT-003-V. |
| SEC-001 — No WebSocket tokens in URLs | Runtime/platform lanes | Chat/voice subprotocol transport, rejected query fallback and regressions | Not a complete security certification. |
| REV-002 / REV-003 / REV-004 / REV-005 / REV-006 — Revival foundations | Rajeev + team | Reconciled old work, truthful architecture/docs, empty-shell cleanup, deterministic fixtures | [Demo guide](../docs/demo-environment.md), [catalog](../docs/synthetic-data-catalog.md); ongoing doc upkeep is DOC-001. |
| REV-001 baseline slice | Integration lane | Reproducible installs, bounded/sharded CI and green baseline | Main CI succeeds; selective enforcement remains CI-001. |
| SOAP-001 — Accurate SOAP adherence | Rajeev | SOAP drafts counted only `completed` logs, so medications (logged `taken`) always read 0% and the model described non-adherence; fixed, with honest "no logs recorded" wording | [#145](https://github.com/sjsu-masters-projects/medi-agent/pull/145); live synthetic generation through the clinician portal matched Risk Radar (83% medication, 57% overall). Clinician edit/sign-off/export remain PV-002/CON-001; prompt framing is AI-004. |
| AI-001 interfaces / AI-003 shipped slices | Rajeev + Ganesh | Provider/voice boundaries, ADK runtime, pre-model safety, workload routing and bounded 429 retry/pacing | Merged #96/#110/#127/#130; [runtime decision](../docs/decisions/ai-runtime-2026-09.md), not medical adjudication. |

### PAT-005 core acceptance

- [x] Fresh evidence-backed scenario, previews, blockers and explicit medication/locale review.
- [x] Multiple documents consolidate; approved plan stays active during new drafting.
- [x] Atomic approval and deterministic approved/effective Today projection.
- [x] V2 continuity; changed activities do not inherit incorrect history/reminders.
- [x] Completion and all six barriers visible to clinicians; header/detail denominator aligned.
- [x] Audit reconstructs generation, reviewer/publication, projections and responses.
- [x] Access isolation requester-confirmed; do not reopen solely because this run did not repeat it.
- [x] Five-document batch, reviewed es-MX publication and non-scheduled-day absence.
- [x] Pending/rejected evidence excluded; approval → request → overlap-blocked V4.
- [x] Independent presentation follow-up PAT-005-L (deployed October 18; see its acceptance section and report).

Intermediate edit wording snapshots are not individually reconstructable.
Earlier transport failures were mitigated, not root-cause proven. These limitations
do not turn an accepted core journey into an unimplemented feature.

## Backlog and partial epics

For each ID below, read its section in the
[detailed acceptance requirements](specs/project-backlog-acceptance.md), or the
dedicated specification linked here, before implementing. Owners are lane leads,
not a claim that every task is personally claimed.

| Issue | Priority | Status | Owner / lane | Remaining work |
| --- | --- | --- | --- | --- |
| PAT-001 | P2 | Verify deployed | Ganesh + Tushar | Durable terminal turn/retry/focus recovery merged in #188; implementation and pending live/accessibility/bilingual acceptance are tracked in PAT-001-A, not a second implementation task. |
| PAT-002 | P1 | In progress | Tushar + Ganesh/Jeevan | Adherence/barriers accepted; confirmed structured symptom-report workflow remains. |
| PAT-003 | P1 | In progress | Tushar; Jeevan review | #141 global locale rollout and LOC-001 bilingual approved wording are merged. Requester decision October 11: the language setting controls screens only; Nora answers in the language the patient writes or speaks. Remaining: bilingual voice/errors/consent and high-risk wording review. |
| LOC-002 | P2 | Verify deployed | Patient + runtime lanes | #200 merged/deployed. DV-011 observed transition passed October 19 evening: Rajeev en-US→es-MX→en-US showed matching loading states before approved wording, retained 0/4 completion, persisted Spanish after reload and retained the October 20 10:00 Pacific visit. English restored. This is sampled UI evidence, not a measured every-frame network-throttled proof. Guest/onboarding continuity, first-paint timing and remaining phone/bilingual review stay open. [Evidence](../docs/deployed-recheck-2026-10-11.md#post-merge-200201-verification--october-19). |
| REC-001 | P2 | In progress | Rajeev + Jeevan | Remaining correction/deletion/projection paths, display-title reuse in citations and care-plan review (titles shipped in LOC-001), and recovery matrix; extraction/viewers already exist. |
| REC-002 | P2 | In progress | Rajeev + Jeevan | Explicit add/update/keep/defer/reject reconciliation and live proof; no automatic truth overwrite. |
| NOT-003 | P2 | Backlog | Rajeev | NOT-002 follow-ups: a dedicated signing key for notification read tokens; clinician account deletion is blocked by document upload/review provenance and SOAP annotations (needs a decision). The same open decision (PV-001-C D1) covers the ADR/MedWatch clinician references, all `ON DELETE RESTRICT`: `adr_information_requests.requested_by`, `adr_assessment_audit_events.actor_id`, `medwatch_drafts.created_by`/`approved_by`/`discarded_by` (064), `medwatch_draft_audit_events.actor_id` and `medwatch_external_submissions.recorded_by` (064, recorder and amender). |
| OPS-004 | P3 | Done | Rajeev | [#156](https://github.com/sjsu-masters-projects/medi-agent/pull/156) deployed. The October 18 scheduler run succeeded, added 2 missing locales, and had zero failures; a read-only cache check found no active condition missing either locale. The third historical one-language cache key is no longer active. [Deployed evidence](../docs/deployed-recheck-2026-10-11.md#task-verdicts). |
| OPS-005 | P1 | In review — outage RCA | Rajeev | Prior 502s remain historical. October 20 real outage isolated a browser recovery defect despite one completed server turn (DV-017, fix in #205). Current bounded 20-read sample: all HTTP 200, 0.002–0.569s; this does not explain every earlier DV-006 failure. Quiet renewal check is running; no completed result yet. [RCA/evidence](../docs/deployed-recheck-2026-10-11.md#october-20--pr-205-outage-accessibility-and-rca). |
| OPS-006 | P1 | In progress | Rajeev | Phase 1 traceability, completion fix and bounded/shared pollers merged in [#194](https://github.com/sjsu-masters-projects/medi-agent/pull/194); phase 2 worker service, Cloud Tasks queue and turn events behind default-off flags merged in [#195](https://github.com/sjsu-masters-projects/medi-agent/pull/195). Migrations 077/078 are in main, but hosted application, deployment and worker infrastructure/configuration have **not** been verified in this campaign. Do not turn on `CHAT_TURNS_VIA_WORKER`/`WORKER_MODE` without the authorized [rollout setup](../docs/chat-worker-setup.md). Remaining: deployed phase-1 check, staged phase-2 rollout, phase 3 one SSE stream per tab, phase 4 notification writes, phase 5 staging load test and API CPU review. [Decision](../docs/decisions/realtime-and-workers-2026-10.md) · [Spec](specs/ops-006-workers-and-event-stream.md). #198 adds the portal `queued` status and socket close-reason logging needed to verify phase 2 in production. API `--timeout` raised 300 to 3600 on the `fix/chat-progress-after-reload` branch (not yet deployed). |
| MED-001 | P2 | Backlog | Ganesh + Rajeev | Full multi-source medication identity/conflict/allergy matching, freshness, uncertainty and approved history. Includes medicines a patient reports in chat that are not on their list (OTC, supplements, another prescriber): today the ADR suspect must be a listed medication, so these are dropped. NORA-002's cached RxNorm ingredient resolution can be reused. There is no deterministic interaction, allergy-conflict or duplicate-therapy checker yet; the docstrings that claimed one are corrected. Also: RxNorm normalization in live ingestion, and a later migration to drop the unused `drug_knowledge_chunks` table (the old drug RAG was removed in #147). |
| MED-002 | P2 | Backlog | Jeevan | Full-source comparison/defer/request-confirmation and approved updates/export; depends MED-001/REC-002. |
| CLN-001 | P2 | In progress | Jeevan | Unified review queue and priority/age/source/update/decision paths; separate screens exist. |
| CLN-002 | P2 | Backlog | Jeevan + Ganesh | Versioned risk explanations/freshness and chronological cross-domain events. |
| PV-001 | P1 | In progress | Ganesh | #136 information loop (merged), confirmed-report B/C and evidence-driven reassessment; score is not a clinician verdict. The MedWatch draft is PV-002. Post-merge gap fixes are PV-001-C. |
| PV-002 | P2 | Done | Ganesh (#150); Rajeev for Form 3500 (requester override) | Synthetic create → edit/save/reload → preview → approval → export → discard/retained history passes; source score unchanged. Exact ordered audit events verified. Filled export inspected in Chrome, macOS Preview and sampled Poppler renders; no Acrobat/physical-phone claim. DV-005 inline in-app viewer remains a separate compatibility issue, not failed export. 285 focused checks pass. FDA transmission and external-submission recording are excluded. [Closure evidence](../docs/deployed-recheck-2026-10-11.md#acceptance-closure-evidence--october-19). |
| UX-005 | P2 | Verify deployed | Rajeev | [#179](https://github.com/sjsu-masters-projects/medi-agent/pull/179) and mobile-stepper fix [#180](https://github.com/sjsu-masters-projects/medi-agent/pull/180) are deployed. October 18: the patient-record ADR tab, old `/medwatch?assessment=` redirect, and 390 px Preview/Approve/Download step navigation passed; the preview link returned a valid renderable PDF. The embedded PDF appeared blank only in the in-app browser, so compare Chrome/mobile before closing (DV-005). [Evidence](../docs/deployed-recheck-2026-10-11.md#task-verdicts). **Follow-ups:** queue filters are client-side with a 200-case cap; notification links still use the redirect. [UI notes](specs/ux-005-adr-medwatch-workspace.md#ui-review-fixes-october-17). The MedWatch PDF preview writes a separate `preview_viewed` audit row, not an export (migration 070). |
| UX-006 | P2 | Verify deployed | Rajeev | #187 deployed. Week agenda, clinic filters, needs-action and patient history checked; evening follow-up measured 390/1280 CSS px with no horizontal overflow. New offer derives patient clinic/Pacific timezone. Booked-day guidance passed for Rajeev and across clinics: the Willow Terrace offer for Evelyn also shows the October 20 Cedar Grove booking, 10:00–10:30 AM. Native date events were required to trigger the lookup in automation; no offer submitted. Remaining: cross-clinic conflict refusal, visit actions, distinct-patient count and bilingual wording. [Contract](specs/ux-006-clinician-schedule.md) · [evidence](../docs/deployed-recheck-2026-10-11.md#october-19-evening-follow-up-verification-and-fixes). |
| SCH-001 | P2 | In progress | Tushar + Jeevan | SCH-001-V remains the canonical deployed acceptance. Clinician edit/cancel/complete/no-show merged in #187 (UX-006); migration `071_clinician_visit_management.sql` applied per requester report. [Contract, audit, notification and wording requirements](specs/sch-001-appointment-scheduling.md). Do not equate migration application with the live visit-management check. |
| COM-001 | P2 | In progress | Jeevan + Tushar | Beyond private threads: opt-in administrative delivery/retry/operations and care-gap tasks; shared clinic inbox separately scoped. |
| VOI-001 | P2 | In progress | Tushar + Ganesh | #147: speech is transcribed in multilingual mode and labelled with the language spoken (Spanish under an English app setting no longer returns an empty transcript); Spanish voice is female (Aura-2 Estrella); spoken replies skip the source line; transcripts are no longer logged. Remaining: transcript/state, interruption/reconnect/cancel, bilingual text-fallback acceptance and hands-free on a phone. |
| CON-001 | P2 | Backlog | Jeevan + Rajeev | Longitudinal timeline, reviewed handoff/export and explicit care-team visibility restrictions. |
| INT-002 | P2 | In progress | Rajeev | Import of 12 resource types with validation, deduplication and review-only candidates exists. Remaining: keep and normalize source identifiers (currently dropped), export of local facts as a validated R4 Bundle, round-trip fixtures, and page/size caps when following sandbox bundle links. [Spec](specs/int-002-003-interoperability-plan.md). |
| INT-003-V | P2 | Verify deployed | Rajeev | Diagnosed October 11: "Invalid launch options" is the sandbox's response to an authorize request with neither a launch parameter nor a simulator segment, and the configured standalone simulator code was not a valid launcher encoding (the sandbox ran a provider-EHR flow). [#153](https://github.com/sjsu-masters-projects/medi-agent/pull/153) uses a valid patient-standalone code and keeps the provider's error description; on production the standalone launch now reaches the sandbox patient login instead of the provider picker ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). Remaining: one recorded run past login and consent to the review hand-off (needs requester OK); the passed EHR launch is not reopened. |
| SAFE-001 | P2 | In progress | Rajeev; safety/clinical review | Future executor tiers and fixture actions/proxies with no supported route; feature guards/audit exist. |
| SAFE-002 | P1 | In progress | Ganesh; peer safety review | Synthetic rule/wording tests and durable per-turn rule/outcome audit; no professional recruitment required and no clinical-validation claim. NORA-002's prompt and safety changes had a separate reviewer-agent review, with findings fixed in #147 ([spec](specs/nora-002-grounded-answers.md#safety-review-and-live-evidence-2026-10-11)). [Runtime contract](../docs/decisions/ai-runtime-2026-09.md). |
| AI-003 | P2 | In progress | Rajeev + Ganesh | Durable recovery/context/evidence gaps and bounded availability metrics. [Runtime contract](../docs/decisions/ai-runtime-2026-09.md). |
| AI-004 — Prompt review follow-ups | P1 | Verify deployed | Rajeev; safety review (SAFE-002) | Text-only fixes shipped in [#145](https://github.com/sjsu-masters-projects/medi-agent/pull/145). The held behaviour changes shipped with NORA-002 in [#147](https://github.com/sjsu-masters-projects/medi-agent/pull/147): 911 guidance and a care-team alert for symptom severity 9–10 (the deterministic floor still answers explicit emergencies first); SOAP assessment/plan framed as considerations for clinician review; extraction document text fenced as data; the unused legacy chat-response prompt retired; no gendered titles in Spanish. Decided October 11 by the requester: Nora answers in the language the patient writes or speaks, whatever the app is set to; the setting controls the screens. Reviewer-agent findings resolved. Remaining: evaluation runs (EVA-001). |
| EVA-001 | P2 | Verify deployed | Ganesh + team | Repeatable 34-case synthetic demo selection (17 locale pairs), extraction/intake/triage/explanation criteria and strict raw-final-response replay implemented. [Operator guide](../docs/demo-ai-evaluation.md). Dry runs and mocked report tests pass; real-provider reports and final-answer review remain, with no clinical-performance claim. Professional adjudication/120-case research expansion optional, not an expo gate. |
| AI-006 | P2 | Verify deployed | Rajeev + Ganesh | Bounded wellness and mild/stable-symptom/low-mood prompt refinements; deterministic bilingual crisis, medication-error and severe-symptom floors. October 19 one deployed English sleep-habits prompt returned bounded general guidance and displayed no symptom-report confirmation. This is a narrow live pass: mild/stable symptoms, low mood, Spanish, safety-floor calibration and deployed SOAP retry/failure remain. SOAP uses the registry with one retry only for transient/truncated generation and writes no note on final failure. [Combined verification](specs/demo-care-loop-followups.md) · [evaluation guide](../docs/demo-ai-evaluation.md) · [live evidence](../docs/deployed-recheck-2026-10-11.md#task-verdicts). |
| COM-002 | P2 | Verify deployed | Integration + portal lanes | DV-010 passed live October 19 evening after #196: Rajeev's attached glucose activity opens the exact editor, scrolls and receives keyboard focus in one unpublished V2 draft. V1 remains live; no review edits/publication. Remaining: independent reminder comparison, audit/retry/authorization and bilingual review. [Contract](specs/demo-care-loop-followups.md) · [evidence](../docs/deployed-recheck-2026-10-11.md#pr-196-deployed-recheck--october-19-evening). Migration 076 recorded applied. |
| CI-001 | P3 | Backlog | Unassigned | Ten safe selective observations before enforcement; archived evidence records one; retain full-suite safety. |
| QUA-001 | P3 | Backlog | Team | Broader browser/accessibility/security/load qualification if scheduled; not current production-certification exercise. |
| REL-001 | P2 | Backlog | Rajeev + team | Selected demo-flow checks, rehearsal, known limitations and tagged expo snapshot; no production qualification. |
| REL-002 | P2 | In progress | Rajeev | Final reproducible demo/reset rehearsal and outage recording; deployments/accounts already exist. |
| REL-003 | P2 | Backlog | Team | University-expo demo script, academic architecture/limitations brief and recovery materials; no startup/VC pitch. |

## Workflow and documentation maintenance

1. Claim an issue and record owner/branch/PR before coding.
2. Read its linked specification or acceptance-requirements section, adjacent code/tests and routed operating docs.
3. Update the row/card when state changes. Put commands/screenshots/checksums and dated observations in the evidence document, not a second tracker.
4. Require peer and safety review where applicable, preserving in-app clinician-role approvals; distinguish tested, merged, deployed and live-verified. Recruiting a healthcare professional is not an expo acceptance gate.
5. Do not weaken requirements because logs are retired. Historical work remains recoverable in Git; specifications are active workflow inputs.

[Documentation map](../docs/README.md) routes durable specs, runbooks and acceptance
evidence. [Contributor workflow](../docs/contributor-agent-workflow.md) enforces
that path. Do not add a forgotten archive as a parallel source of truth.
