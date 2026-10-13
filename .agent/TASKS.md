# MediAgent — Project task board

> **Active plan:** AI-005 agent quality (documents, explanations, triage, OCR); EMAIL-001 provider status and the OPS-004 Sunday check; then PAT-002-B; remaining deployed checks LOC-001, PAT-005-L, PV-001-B/PV-002 and the INT-003-V standalone run · [accepted PAT-005 contract](specs/pat-005-clinician-approved-today-feed-plan.md)
>
> **Updated:** October 12, 2026 · **Feature freeze:** December 4, 2026
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

## Current release and live status

| Area | Current state | Remaining boundary |
| --- | --- | --- |
| Main deployment | `87a466d` ([#157](https://github.com/sjsu-masters-projects/medi-agent/pull/157), October 12), after [#156](https://github.com/sjsu-masters-projects/medi-agent/pull/156) (`62a1945`), [#150](https://github.com/sjsu-masters-projects/medi-agent/pull/150) (`6a43049`) and [#136](https://github.com/sjsu-masters-projects/medi-agent/pull/136) (`0c586be`) on October 12, and [#152](https://github.com/sjsu-masters-projects/medi-agent/pull/152) (`4782088`), [#154](https://github.com/sjsu-masters-projects/medi-agent/pull/154) (`38b51e6`), [#153](https://github.com/sjsu-masters-projects/medi-agent/pull/153) (`a7cef68`) and [#151](https://github.com/sjsu-masters-projects/medi-agent/pull/151) (`8b44610`) on October 11: main CI, CodeQL and the backend Cloud Run deployment succeeded for each; both portals serve #157's reset page. | Deployment signals do not prove every screen was retested; see the [deployed recheck](../docs/deployed-recheck-2026-10-11.md). |
| PAT-005 core | Synthetic Morgan/Elena loop verified live, including V2 continuity, six barriers, audit, Spanish V3 and non-scheduled-day absence | V4 approved October 10 in English and Spanish under LOC-001 after removing a duplicate-upload overlap ([evidence](specs/loc-001-bilingual-approved-wording.md#verification--2026-10-10-synthetic-environment)). Presentation follow-up is separate. |
| Patient-upload review | [#138](https://github.com/sjsu-masters-projects/medi-agent/pull/138) deployed; pending/rejected exclusion, approval eligibility/queue handoff and exact-document link verified | Negative preview/publication guards have API/PostgreSQL evidence, not a newly repeated live blocked publication. |
| Human messaging | [#139](https://github.com/sjsu-masters-projects/medi-agent/pull/139) deployed; migration checked; bilingual replies, actual sender/clinic, unread and reload persistence verified | Concurrency/reassignment/multiple-recipient isolation tested in isolated PostgreSQL, not repeated by the four-message live run. |
| Portal polish | [#141](https://github.com/sjsu-masters-projects/medi-agent/pull/141) merged at `657602d`; original local checks: 372 patient + 260 clinician tests and both app checks pass | Authenticated deployed UI checks remain separate from merge; UX-002 replaces the visual direction. |
| Reference redesign | [#144](https://github.com/sjsu-masters-projects/medi-agent/pull/144) merged at `a36fc37`; responsive and wording follow-up [#145](https://github.com/sjsu-masters-projects/medi-agent/pull/145) merged and deployed at `0cf4c93` | Authenticated deployed screen recheck not yet recorded. |
| Synthetic database schema | Every migration on main is in the ledger (70 files, none pending, none ledger-only; checked October 12). `059_critical_result_alerts.sql` (AI-005 second slice) applied by the requester October 13. `060_critical_result_open_work.sql` (critical alerts listed under Alerts → Needs attention; found in the production check: they showed only under History) applied by the requester October 13. `061_critical_result_acknowledge.sql` (lets clinicians acknowledge the alert; without it the alert could never leave Needs attention) is pending; the requester applies it from their terminal. The ledger also holds `059_chat_safety_alerts.sql` and `060_confirmed_symptom_intake.sql` from the unmerged `feature/confirmed-symptom-intake` branch (applied October 13); they touch no notification-centre objects, so the shared 059 prefix is harmless, but do not rename either applied file. Applied with requester authorization: 049–056 on October 11 (LOC-001 bilingual wording, record titles, NORA-002 knowledge/conversations, NOT-001/NOT-002 notifications; [LOC-001 evidence](specs/loc-001-bilingual-approved-wording.md#verification--2026-10-10-synthetic-environment)); `057_email_delivery.sql` October 11 and `058_email_delivery_fixes.sql` October 12 before #152 merged; `047_adr_patient_information_loop.sql` (#136) and `048_medwatch_draft_lifecycle.sql` (#150, October 12). | 047 and 048 each have two files with the same number prefix. The ledger keys on the full filename, so both apply, but the order in a fresh environment has not been tested separately. PV-001-C (this branch) adds no migration: it extends the notification-centre and email PostgreSQL fixtures to apply 042 through 061 in ledger order (Docker: 50 and 31 passed on 042–058) and pins `pypdf`. The PV-001-C follow-up migrations are not written; they take the next free numbers after 061 (the spec's working names 059 and 060 are taken and must be renumbered). |
| Scheduled jobs | Three Cloud Scheduler triggers, all enabled: document ingestion (every 5 minutes), weekly reference refresh (Sundays 03:00 America/Los_Angeles) and reminder dispatch (every 15 minutes UTC, resumed October 11). EMAIL-001's `email_dispatch` runs after each reminder run with its own run record; all 90 recorded email runs and the latest 110 reminder runs succeeded (checked October 12). The nightly ADR scan trigger was deleted October 11. After [#151](https://github.com/sjsu-masters-projects/medi-agent/pull/151) deployed, each job logged a successful `scheduled_job.finished` line ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). | Watch the first Sunday refresh (October 18, also the OPS-004 check) and the first reminder that is actually due. |
| Patient symptoms | #141 removes hard-coded examples and routes Today directly to Nora | No connected patient timeline of confirmed reports; raw chat capture is not a complete confirmation workflow. |
| ADR patient information loop | Ganesh's [#136](https://github.com/sjsu-masters-projects/medi-agent/pull/136) and [#150](https://github.com/sjsu-masters-projects/medi-agent/pull/150) (MedWatch-compatible draft lifecycle, PV-002) merged and deployed October 12; their migrations 047 and 048 are applied. | Patient answers → clinician evidence and the MedWatch draft have not been rechecked through the deployed portals. Ten gaps in the loop (bilingual form, notification path, lifecycle, provenance, deletion) are scoped in PV-001-C. |

Evidence: [deployed recheck](../docs/deployed-recheck-2026-10-11.md),
[PAT-005 acceptance](../docs/pat-005-final-acceptance-2026-10-10.md),
[portal review](../docs/portal-ui-ux-review-2026-10-10.md),
[scheduling contract](specs/sch-001-appointment-scheduling.md),
[conversation contract](specs/com-001-two-way-conversations.md).
This is prototype acceptance, not clinical/compliance/production certification.

## Current sprint

| Issue | Priority | Status | Owner | Next observable result |
| --- | --- | --- | --- | --- |
| EMAIL-001 — Account and selective notification emails | P1 | Verify deployed | Rajeev | [Contract](specs/email-001-email-flows.md). Delivered by [#152](https://github.com/sjsu-masters-projects/medi-agent/pull/152), [#156](https://github.com/sjsu-masters-projects/medi-agent/pull/156) and [#157](https://github.com/sjsu-masters-projects/medi-agent/pull/157); migrations 057/058 applied. Verified on production October 12 ([evidence](../docs/deployed-recheck-2026-10-11.md#email-001-on-production-october-12)): clinician invitation (delivered, signed, sign-up and acceptance work, non-admins refused), patient verification code, unread-message notice, Spanish appointment notice, opt-out (in-app item only, no email), neutral reset request, the clinician reset email (MediAgent Pro blue, "within 1 hour, works once") and the clinician password reset. Scanner-safe Reset password template installed and confirmed after reload. Clinician password reset passed end to end after the requester corrected `NEXT_PUBLIC_SUPABASE_ANON_KEY` in both Vercel projects and redeployed (both portals had been built with the key missing its first character, so the save returned 401 "Invalid API key"); the test account has no MFA factor, so MFA after reset was not exercised. Patient password reset also passed (requested from the patient portal 05:47 UTC, sign-in 05:47 UTC; English and Spanish patient emails checked in the inbox). A patient upload after the key fix stored and registered a synthetic follow-up lab report for Morgan (storage 200, document 201; dashboard realtime is off in production because `NEXT_PUBLIC_ENABLE_DASHBOARD_REALTIME` is unset). **Open:** patient en-US/es-MX reset not yet run; delivery status stays "accepted" until a full-access Resend key replaces the sending-only one (requester action); the first invitation landed in Spam. Email preferences card redesign [#158](https://github.com/sjsu-masters-projects/medi-agent/pull/158) verified on production October 12 (Morgan at desktop and 375 px, Elena in Settings). |
| LOC-001 — One language setting, bilingual approved wording | P1 | Verify deployed | Rajeev | [Spec](specs/loc-001-bilingual-approved-wording.md) · [#145](https://github.com/sjsu-masters-projects/medi-agent/pull/145) merged and deployed: care-plan wording drafted and approved in en-US and es-MX together; Today/Reminders follow `preferred_language`; bilingual record titles. Deployed Profile switch to Spanish changed Today to the approved Spanish wording with unchanged reminder times ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). Remaining: approve a new bilingual draft on the deployed clinician portal when one exists. Follow-ups are LOC-002. |
| PAT-005-L — Presentation recheck | P1 | Verify deployed | Rajeev | Saved-locale Today controls verified on the deployed app ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). Remaining: duplicate-skipped explanation in both document surfaces, which needs a new byte-identical synthetic upload (the earlier duplicate no longer exists). |
| PV-001-B — ADR patient answers | P1 | Verify deployed | Ganesh | #136 merged and deployed October 12 with current chat/language UI; migration 047 applied. Record patient answers → clinician evidence/score through the deployed portals. Gaps found after merge are scoped in PV-001-C. |
| PV-001-C — ADR loop gap fixes | P1 | In progress | Rajeev | [Requirements](specs/pv-001-c-adr-loop-gap-fixes/requirements.md) · [design](specs/pv-001-c-adr-loop-gap-fixes/design.md) · [tasks](specs/pv-001-c-adr-loop-gap-fixes/tasks.md) · branch `fix/adr-information-loop-gaps`. **PR 1 is delivered in this PR (no migration; G1 to G5):** bilingual token-built follow-up form, direct notification/chat/Today path, deterministic bilingual request wording, request lifecycle states, per-entry evidence provenance and MedWatch draft defects ([evidence](#pv-001-c-acceptance-pr-1)). **PR 2 is a planned follow-up (G6 to G10):** answering resolves the patient item, one item per request, clinician answered alert, patient deletion through ADR/MedWatch data, cancelled/superseded end states, through a new migration. **PR 3 is a planned follow-up:** MedWatch Form 3500 structured draft, preview, official-PDF download, recorded external submission and discard/reopen, through a second new migration. Neither migration is written or applied; the spec's working numbers 059 and 060 must be re-checked against `origin/main`, which has since added `059_critical_result_alerts.sql`. Groundwork already in this PR: the `pypdf==6.20.1` pin with regenerated locks, an empty `medwatch_3500` package marker, and the notification-centre and email PostgreSQL fixtures extended to apply 042 through 058 in ledger order. **Ownership:** the requester decided on 2026-10-12 that Rajeev takes PR 3, overriding TEAM.md's assignment of PV-002 to Jeevan. Clinician-deletion policy stays NOT-003 (D1). |
| AI-005 — Agent quality: documents, explanations, triage, OCR | P1 | In review | Rajeev + Ganesh | [Spec](specs/ai-005-agent-quality.md). First slice on `feature/document-results-extraction`: row-preserving model input; lab results, vital signs, immunizations, procedures, appointments, document type and medication actions extracted and grounded on their printed row; stop/hold and changed-dose blockers in care-plan drafts; results-only documents no longer open drafts; explanations cover every type with a number check in English and Spanish; Nora sees results and medication actions; clinician facts dialog per type. Verified against the production model on synthetic lab, discharge and Spanish documents. Second slice on `feature/agent-quality-followups`: critical-result clinician alert (migration 059, requester applies), triage eval on the production Care Coordinator prompt (36 cases, 92% accuracy, 100% safety), phone-photo OCR fixtures with OCR quality passed to the model, patient Records results view, one Spanish register (tú). Chat results card on `feature/chat-results-card` (migration 062): Nora's replies that cite a document show its results as a server-built card. Remaining: over-triage calibration, legacy ingestion graph removal, SOAP via the model registry. |
| UX-004 — Clinician date format and fact labels | P2 | In review | Rajeev | Fixed with AI-005: clinician dates are formatted en-US explicitly (review queue, documents, SOAP, MFA, settings, care plan, MedWatch), and the extracted-facts dialog labels each fact by its type instead of calling every name "Medication". |
| PAT-002-B — Confirmed symptom intake | P1 | Ready | Unassigned; Tushar + Ganesh lanes | Inventory existing capture, then a reviewed question library, attributable draft, correct/confirm/cancel, bounded retrieval and ownership, with bilingual tests. |
| PAT-002-C — Real symptom timeline | P2 | Blocked | Unassigned; Tushar + Jeevan lanes | Confirmed-report contract from B, then actual saved reports and authorized clinician detail; no invented history. |
| SCH-001-V — Canonical scheduling acceptance | P2 | Verify deployed | Tushar + Jeevan | Record deployed offer → patient response → persisted visit/calendar flow; distinguish earlier branch/staging proof. |
| PAT-001-A — Terminal chat-turn recovery | P2 | Ready | Unassigned; Ganesh + patient lane | Persist bounded processing/completed/failed/interrupted outcomes; retry/reconnect without duplicate messages/actions. |
| PAT-004 — Focused-document chat | P2 | In progress | Rajeev + Ganesh/Tushar | "Ask about this document" opens Nora on that document in its own conversation ([#146](https://github.com/sjsu-masters-projects/medi-agent/pull/146), [#147](https://github.com/sjsu-masters-projects/medi-agent/pull/147)). Live October 11: the focus card, a grounded answer and restore after reopening the conversation work; Dismiss did not stick because the server restored the saved document, fixed in [#153](https://github.com/sjsu-masters-projects/medi-agent/pull/153) with an explicit message when the document is no longer available, and verified on production (dismissed card stays gone after reload and reopening; [deployed recheck](../docs/deployed-recheck-2026-10-11.md)). Visible source on each answer: [#154](https://github.com/sjsu-masters-projects/medi-agent/pull/154), merged and verified on production October 11 in English and Spanish. Document-grounded answers end with a server-written line naming the record title or file name and the cited pages, in English or Spanish, combined with reference sources ([NORA-002 document citations](specs/nora-002-grounded-answers.md#documents)). It is plain text in the saved message: no message-sources field exists, so a clickable per-message link would need a schema decision. Remaining: replacing the focused document from an open chat, and refresh landing on the same focused conversation. |
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

### UX-001 acceptance

- [x] Inventory core live screens and source/test-review remaining entry/import routes.
- [x] Simplify duplicate/technical content while retaining clinical instructions and evidence identity.
- [x] One saved patient en-US/es-MX interface language; clinician controls English.
- [x] Approved clinical wording/history unchanged; language switching does not translate/publish a plan. (Superseded for care-plan wording by LOC-001: both languages are approved together.)
- [x] Responsive layouts, tap/keyboard help, refresh/recovery and accessible dialogs.
- [x] Four workstream reviews/cross-review fixes integrated; 632 tests and both app checks pass.
- [x] Remove fabricated timeline; Today opens Nora directly, old Symptoms URL is an honest compact handoff.
- [x] Merge #141 (`657602d`); post-deployment observations remain separate.
- [x] Authenticated post-deployment mobile/bilingual screen checks, run with the UX-002 recheck ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)).

Local 320/768/1280 component/layout checks are not every deployed route.
Patient symptom history, existing MFA lookup-failure handling and dashboard
unknown-versus-zero API ambiguity are documented limits.
[Scope and evidence](../docs/portal-ui-ux-review-2026-10-10.md).

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
- [ ] Deployed: approve a new bilingual draft from the clinician portal (no draft pending on October 11).
- [ ] Clinician review of the second synthetic patient's bilingual V3 draft (left for a clinician decision).

### PAT-005-L acceptance

- [x] Saved es-MX updates Today chrome/actions/barriers and, since LOC-001, approved bilingual wording; reminder times stay unchanged ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)).
- [ ] Duplicate fixture (needs a new byte-identical synthetic upload) displays skipped extraction in patient Records and clinician Documents/Review Queue, with source accessible and no false empty-facts review.
- [ ] Record these observations in the acceptance report, then close this slice.

#140 is deployed. No new migration/reset/publication needed. V4 is now active,
approved in both languages under LOC-001; V3 history is preserved.

### PV-001-B acceptance

- [x] Implementation and author-reported staging/local-branch acceptance in #136.
- [x] Resolve conflicts and integrate with current human/Nora separation and language controls (merged October 12).
- [x] Review and required CI; main CI and deployment succeeded for the merge.
- [x] Authorized rollout: migration 047 applied.
- [ ] Patient answers → clinician evidence/score through the deployed portals.
- [ ] Preserve patient attribution, unknown answers, prior clinician judgment and audit.

Three safe retrospective questions only: no medication experiments, new treatment
or MedWatch submission. Author records score 3 → 6 with three patient responses;
this is not independent canonical-app proof or full PV-001 completion.
### PV-001-C acceptance (PR 1)
Run on 2026-10-13 from the working tree on branch `fix/adr-information-loop-gaps` (base `87a466d`, nothing committed), Python 3.12.11, Node 24.3.0 (CI uses Node 20), `uv` 0.9.24.
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
- [ ] Requester: authenticated deployed and visual checks (patient 320, 360 and 430 px, clinician 1024, 1280 and 1536 px, screenshots, keyboard-only, 200% zoom, reduced motion) and the Spanish-fluent review of the es-MX wording (D9). Neither was done.
- [ ] Before merge: the branch base is 4 commits behind `origin/main` (`5294bd9`); 8 files changed on both sides (this tracker, `apps/patient-portal/README.md`, the chat page and its test, `medwatch-draft-card.tsx`, the notification presentation module and its test, and the notification-centre PostgreSQL test) need a rebase and a rerun of the checks above.

## Done — accepted slices

| Issue | Owner | Delivered scope | Evidence / limit |
| --- | --- | --- | --- |
| PAT-PROFILE-001 — Optional profile gender | Patient lane | Optional gender with a Not specified choice that clears a saved value; not required signup data | [#141](https://github.com/sjsu-masters-projects/medi-agent/pull/141), [#153](https://github.com/sjsu-masters-projects/medi-agent/pull/153); production save-and-reload of a value and of Not specified verified October 11 ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). |
| OPS-003 — Scheduled job correctness and run logs | Rajeev | Weekly refresh due after six days with documented conditions seeded; reminders for `confirmed` visits, reschedule-aware keys, contiguous windows, conflict fallback, skipped counts; nightly ADR scan retired; `scheduled_job.started`/`finished` run logs ([runbook](CLOUD_INFRASTRUCTURE_GUIDE.md#5-scheduled-jobs-cloud-scheduler-and-run-logs)) | [#151](https://github.com/sjsu-masters-projects/medi-agent/pull/151); requester resumed reminder dispatch and deleted the ADR trigger October 11; first logged runs succeeded: reminders (first-run window, 3 inactive schedules skipped), ingestion, and a manual refresh that seeded 13 conditions and updated 10 subjects ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). The refresh then found no topic for 13 of 29 condition lookups: Spanish was searched with English names, only the first search hit was considered, and qualifiers such as "mild persistent" or "of the knee" defeated the search; some first hits were narrower topics. Fixed in [#153](https://github.com/sjsu-masters-projects/medi-agent/pull/153): best match among several hits, a qualifier fallback, and the Spanish page resolved from the English topic. |
| SEC-002 — GitHub security and code-quality findings | Rajeev | Next.js 16.3.8 in both portals, `google-cloud-aiplatform>=1.133.0` on every lock marker, four CodeQL quality fixes, 8 of 14 AI findings fixed (4 already resolved, 2 not applicable) | [#151](https://github.com/sjsu-masters-projects/medi-agent/pull/151); after merge, 0 open Dependabot alerts, 0 open code-scanning alerts and 0 open CodeQL quality findings. Open requester decision: malware scanning, Dependabot security updates and secret-scanning push protection are disabled. Not a security certification. |
| NOT-001 — Notifications and clinician alerts | Rajeev | Recipient-scoped in-app centre for patients and clinicians: shared authorized work, private message notifications, atomic capture, read snapshots, bilingual copy ([contract](specs/not-001-notification-centre.md)) | [#148](https://github.com/sjsu-masters-projects/medi-agent/pull/148); verified in disposable PostgreSQL 16 and on the deployed portals October 11 ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). |
| NOT-002 — Notification follow-ups | Rajeev | Compact lists, one unread count, real times for existing work, partial "Mark all read", account deletion through conversations/offers, page-proportional reads, Earlier messages, appointment response rule, one item per answered offer, consistent refreshes (migrations 052–056, applied October 11) | [#149](https://github.com/sjsu-masters-projects/medi-agent/pull/149); local end-to-end check plus deployed acknowledgement, bulk read, matching counts and Spanish copy ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). Follow-ups are NOT-003. |
| UX-001 — Both portal UI/UX polish | Rajeev; lane review | Inventory, simplified content, saved patient language, responsive layouts and accessible dialogs | [#141](https://github.com/sjsu-masters-projects/medi-agent/pull/141); screens since replaced by UX-002, rechecked together on the deployed portals ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). |
| UX-002 — Reference-led portal redesign | Rajeev | Reference-led patient and clinician redesign with responsive and wording follow-up ([requirements](specs/ux-002-reference-redesign.md)) | #142–#145 ([overhaul checks](../docs/ux-002-overhaul-verification.md)); deployed screens at 390 and 1280 px without errors or horizontal scrolling, both patient locales ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). |
| NORA-001 — Nora answers every message | Rajeev | Relative model deadline under uvloop, a triage decision on every follow-up, document handoff from Records, message language labels | [#146](https://github.com/sjsu-masters-projects/medi-agent/pull/146); deployed chat answered every message in English and Spanish ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). |
| NORA-002 — Grounded, plain-language Nora | Rajeev | Shared MedlinePlus/DailyMed/RxNorm cache, record and document tools with server-written sources, daily conversations, replies in the language the patient uses, female Spanish voice, AI-004 safety changes ([spec](specs/nora-002-grounded-answers.md)); supersedes RAG-001 | [#147](https://github.com/sjsu-masters-projects/medi-agent/pull/147); deployed answers grounded in the record with dated MedlinePlus and DailyMed sources, Spanish and English regardless of the app setting ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). Voice on a phone is VOI-001; refresh cadence fixed in OPS-003. |
| DOC-001 — Board and documentation cleanup | Rajeev | #141 routing/evidence cleanup merged. October 11: hand-written migration list replaced by the ledger script in CONTRIBUTING; ARCHITECTURE, docs map and READMEs updated for NORA-002 and NOT-001; retired drug-RAG docs removed; false allergy/duplicate-therapy rule claim corrected; HANDOFF traps recorded. October 12: EMAIL-001 spec condensed from rollout handoff to contract, operations and production status; Supabase guide, architecture and scheduler runbook updated for the deployed email rollout. Repeat per PR, not as a separate task. | Kept current per PR from now on. |
| PAT-005 — Controlled care-plan → Today loop | Rajeev; portal support | Fresh synthetic uploads, grounded draft, protected source/review/blockers, approval, Today, completion/barriers and clinician follow-up | [Acceptance report](../docs/pat-005-final-acceptance-2026-10-10.md). |
| PAT-005-A/B/D/E/G/I/K — Draft and publication safeguards | Rajeev | Diagnostics, draft visibility, active/proposed/source review, locale/medication attestation, incomplete evidence, overlaps and exact preview | Merged #114–#116, #118–#122, #124, #125; durable [PAT-005 specification](specs/pat-005-clinician-approved-today-feed-plan.md). |
| PAT-005-C/F/J — Fresh scenario and continuity | Rajeev | V1 stays active until V2 approval; unchanged identities/reminders/history retained; changed activity gets fresh identity; six barriers and audit | Access-isolation closure requester-confirmed, with recorded denial/regression support; not blanket qualification. |
| PAT-005-H — Reminder usability | Rajeev; patient lane | Patient-selected valid days/times, cancel, saved timezone, safe PRN/unknown/event handling | #124 plus cadence fixes; recorded live reminder acceptance. |
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
- [ ] Independent presentation follow-up PAT-005-L.

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
| PAT-001 | P2 | In progress | Ganesh + Tushar | Durable terminal turn/retry/focus recovery; history and localized fallback exist. |
| PAT-002 | P1 | In progress | Tushar + Ganesh/Jeevan | Adherence/barriers accepted; confirmed structured symptom-report workflow remains. |
| PAT-003 | P1 | In progress | Tushar; Jeevan review | #141 global locale rollout and LOC-001 bilingual approved wording are merged. Requester decision October 11: the language setting controls screens only; Nora answers in the language the patient writes or speaks. Remaining: bilingual voice/errors/consent and high-risk wording review. |
| LOC-002 | P2 | Backlog | Unassigned; patient + runtime lanes | LOC-001 follow-ups ([spec](specs/loc-001-bilingual-approved-wording.md)): notifications and Today errors from codes; sign-up saves the guest language and the server renders `lang` without an English flash; one label set for the two locales; clinician patient-language chip and per-message language; cached per-locale document explanations; one Spanish register. |
| REC-001 | P2 | In progress | Rajeev + Jeevan | Remaining correction/deletion/projection paths, display-title reuse in citations and care-plan review (titles shipped in LOC-001), and recovery matrix; extraction/viewers already exist. |
| REC-002 | P2 | In progress | Rajeev + Jeevan | Explicit add/update/keep/defer/reject reconciliation and live proof; no automatic truth overwrite. |
| NOT-003 | P2 | Backlog | Rajeev | NOT-002 follow-ups: a dedicated signing key for notification read tokens; clinician account deletion is blocked by document upload/review provenance and SOAP annotations (needs a decision). The same open decision (PV-001-C D1) covers the ADR/MedWatch clinician references, all `ON DELETE RESTRICT`: `adr_information_requests.requested_by`, `adr_assessment_audit_events.actor_id`, `medwatch_drafts.created_by`/`approved_by` and `medwatch_draft_audit_events.actor_id`. |
| OPS-004 | P3 | Verify deployed | Rajeev | [#156](https://github.com/sjsu-masters-projects/medi-agent/pull/156), merged and deployed October 12: the weekly refresh seeds per condition and language, so an active documented condition cached in only en-US or es-MX gets the missing one through the twin-page lookup, within the run's limit, reported as `subjects_new_locales`. Remaining: confirm the Sunday October 18 run (or an authorized manual run) fills the 3 one-language synthetic conditions. |
| UX-003 | P2 | Done | Rajeev | October 12 production findings, fixed in [#156](https://github.com/sjsu-masters-projects/medi-agent/pull/156) (merged and deployed October 12): invitation signup has one primary action (Create account) with an opt-in "Sign in to accept" path; Team & Roles shows staff invitations only to clinic admins, a read-only note to others; clinic-code and invite-code Copy buttons fall back when the Clipboard API is missing or refused and report Copied or a manual-copy error. Production October 12, as provider Elena: Team & Roles shows "Only clinic admins can invite team members." and no invite form; clinic-code Copy shows Copied with no error. The requester then confirmed Copy as clinic admin Carmen and a fresh invitation link signed out: one primary "Create clinician account" button with "Already have a MediAgent clinician account? Sign in to accept" as a link. Follow-up (not blocking): non-admins still see the per-member ⋯ menu the server rejects. |
| MED-001 | P2 | Backlog | Ganesh + Rajeev | Full multi-source medication identity/conflict/allergy matching, freshness, uncertainty and approved history. NORA-002's cached RxNorm ingredient resolution can be reused. There is no deterministic interaction, allergy-conflict or duplicate-therapy checker yet; the docstrings that claimed one are corrected. Also: RxNorm normalization in live ingestion, and a later migration to drop the unused `drug_knowledge_chunks` table (the old drug RAG was removed in #147). |
| MED-002 | P2 | Backlog | Jeevan | Full-source comparison/defer/request-confirmation and approved updates/export; depends MED-001/REC-002. |
| CLN-001 | P2 | In progress | Jeevan | Unified review queue and priority/age/source/update/decision paths; separate screens exist. |
| CLN-002 | P2 | Backlog | Jeevan + Ganesh | Versioned risk explanations/freshness and chronological cross-domain events. |
| PV-001 | P1 | In progress | Ganesh | #136 information loop (merged), confirmed-report B/C and evidence-driven reassessment; score is not a clinician verdict. The MedWatch draft is PV-002. Post-merge gap fixes are PV-001-C. |
| PV-002 | P2 | Verify deployed | Ganesh; Jeevan review | [#150](https://github.com/sjsu-masters-projects/medi-agent/pull/150), merged and deployed October 12 with migration 048 applied: assigned-clinician draft from reviewed ADR evidence, field attribution, edit revisions, approval attestation, audit and JSON export; never FDA submission. Remaining: a recorded draft → edit → approve → export run through the deployed clinician portal. Draft defects found after the merge are scoped in PV-001-C (PR 1 here; Form 3500 fidelity is the planned PR 3). |
| SCH-001 | P2 | In progress | Tushar + Jeevan | SCH-001-V; later clinician cancellation/completion and approved-workflow booking. [Spec](specs/sch-001-appointment-scheduling.md). |
| COM-001 | P2 | In progress | Jeevan + Tushar | Beyond private threads: opt-in administrative delivery/retry/operations and care-gap tasks; shared clinic inbox separately scoped. |
| VOI-001 | P2 | In progress | Tushar + Ganesh | #147: speech is transcribed in multilingual mode and labelled with the language spoken (Spanish under an English app setting no longer returns an empty transcript); Spanish voice is female (Aura-2 Estrella); spoken replies skip the source line; transcripts are no longer logged. Remaining: transcript/state, interruption/reconnect/cancel, bilingual text-fallback acceptance and hands-free on a phone. |
| CON-001 | P2 | Backlog | Jeevan + Rajeev | Longitudinal timeline, reviewed handoff/export and explicit care-team visibility restrictions. |
| INT-002 | P2 | In progress | Rajeev | Import of 12 resource types with validation, deduplication and review-only candidates exists. Remaining: keep and normalize source identifiers (currently dropped), export of local facts as a validated R4 Bundle, round-trip fixtures, and page/size caps when following sandbox bundle links. [Spec](specs/int-002-003-interoperability-plan.md). |
| INT-003-V | P2 | Verify deployed | Rajeev | Diagnosed October 11: "Invalid launch options" is the sandbox's response to an authorize request with neither a launch parameter nor a simulator segment, and the configured standalone simulator code was not a valid launcher encoding (the sandbox ran a provider-EHR flow). [#153](https://github.com/sjsu-masters-projects/medi-agent/pull/153) uses a valid patient-standalone code and keeps the provider's error description; on production the standalone launch now reaches the sandbox patient login instead of the provider picker ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). Remaining: one recorded run past login and consent to the review hand-off (needs requester OK); the passed EHR launch is not reopened. |
| SAFE-001 | P2 | In progress | Rajeev; safety/clinical review | Future executor tiers and fixture actions/proxies with no supported route; feature guards/audit exist. |
| SAFE-002 | P1 | In progress | Ganesh; peer safety review | Synthetic rule/wording tests and durable per-turn rule/outcome audit; no professional recruitment required and no clinical-validation claim. NORA-002's prompt and safety changes had a separate reviewer-agent review, with findings fixed in #147 ([spec](specs/nora-002-grounded-answers.md#safety-review-and-live-evidence-2026-10-11)). [Runtime contract](../docs/decisions/ai-runtime-2026-09.md). |
| AI-003 | P2 | In progress | Rajeev + Ganesh | Durable recovery/context/evidence gaps and bounded availability metrics. [Runtime contract](../docs/decisions/ai-runtime-2026-09.md). |
| AI-004 — Prompt review follow-ups | P1 | Verify deployed | Rajeev; safety review (SAFE-002) | Text-only fixes shipped in [#145](https://github.com/sjsu-masters-projects/medi-agent/pull/145). The held behaviour changes shipped with NORA-002 in [#147](https://github.com/sjsu-masters-projects/medi-agent/pull/147): 911 guidance and a care-team alert for symptom severity 9–10 (the deterministic floor still answers explicit emergencies first); SOAP assessment/plan framed as considerations for clinician review; extraction document text fenced as data; the unused legacy chat-response prompt retired; no gendered titles in Spanish. Decided October 11 by the requester: Nora answers in the language the patient writes or speaks, whatever the app is set to; the setting controls the screens. Reviewer-agent findings resolved. Remaining: evaluation runs (EVA-001). |
| EVA-001 | P2 | In progress | Ganesh + team | Repeatable synthetic checks for selected demo tasks, paired locales and raw responses. Professional adjudication/120-case research expansion optional, not an expo gate. |
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
