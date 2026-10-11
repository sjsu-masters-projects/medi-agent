# MediAgent — Project task board

> **Active plan:** live-check follow-ups in #153 (PAT-PROFILE-001, PAT-004 dismiss, INT-003-V); remaining deployed checks LOC-001 and PAT-005-L · [accepted PAT-005 contract](specs/pat-005-clinician-approved-today-feed-plan.md)
>
> **Updated:** October 11, 2026 · **Feature freeze:** December 4, 2026
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
| Main deployment | `8b44610` ([#151](https://github.com/sjsu-masters-projects/medi-agent/pull/151)), after [#149](https://github.com/sjsu-masters-projects/medi-agent/pull/149) (`8b93b48`), [#148](https://github.com/sjsu-masters-projects/medi-agent/pull/148) (`e1ad3f4`) and [#147](https://github.com/sjsu-masters-projects/medi-agent/pull/147) (`4c9de30`), all October 11: main CI, frontend CI, CodeQL, backend Cloud Run deployment and both Vercel production deployments succeeded for each. | Deployment signals do not prove every screen was retested; see the [deployed recheck](../docs/deployed-recheck-2026-10-11.md). |
| PAT-005 core | Synthetic Morgan/Elena loop verified live, including V2 continuity, six barriers, audit, Spanish V3 and non-scheduled-day absence | V4 approved October 10 in English and Spanish under LOC-001 after removing a duplicate-upload overlap ([evidence](specs/loc-001-bilingual-approved-wording.md#verification--2026-10-10-synthetic-environment)). Presentation follow-up is separate. |
| Patient-upload review | [#138](https://github.com/sjsu-masters-projects/medi-agent/pull/138) deployed; pending/rejected exclusion, approval eligibility/queue handoff and exact-document link verified | Negative preview/publication guards have API/PostgreSQL evidence, not a newly repeated live blocked publication. |
| Human messaging | [#139](https://github.com/sjsu-masters-projects/medi-agent/pull/139) deployed; migration checked; bilingual replies, actual sender/clinic, unread and reload persistence verified | Concurrency/reassignment/multiple-recipient isolation tested in isolated PostgreSQL, not repeated by the four-message live run. |
| Portal polish | [#141](https://github.com/sjsu-masters-projects/medi-agent/pull/141) merged at `657602d`; original local checks: 372 patient + 260 clinician tests and both app checks pass | Authenticated deployed UI checks remain separate from merge; UX-002 replaces the visual direction. |
| Reference redesign | [#144](https://github.com/sjsu-masters-projects/medi-agent/pull/144) merged at `a36fc37`; responsive and wording follow-up [#145](https://github.com/sjsu-masters-projects/medi-agent/pull/145) merged and deployed at `0cf4c93` | Authenticated deployed screen recheck not yet recorded. |
| Synthetic database schema | Applied with requester authorization: 049 (LOC-001), 050 (record titles), `051_health_knowledge_and_chat_sessions.sql` (NORA-002) and `051_notification_centre.sql` (NOT-001), the last on October 11 ([LOC-001 evidence](specs/loc-001-bilingual-approved-wording.md#verification--2026-10-10-synthetic-environment)); for [#149](https://github.com/sjsu-masters-projects/medi-agent/pull/149), 052 (existing work keeps its real time), 053 (account deletion through conversations and offer history) and 054 (page-proportional notification reads), also October 11. 055 (one notification per answered appointment offer) and 056 (parallel requests agree on new arrivals) were applied after them, also October 11 | None pending on main. The ledger's extra `047_adr_patient_information_loop.sql` comes from #136 (applied in staging); [#150](https://github.com/sjsu-masters-projects/medi-agent/pull/150) adds an unapplied `048_medwatch_draft_lifecycle.sql`. Both reuse numbers main already has (047, 048), so their order in a fresh environment needs review before merge. |
| Scheduled jobs | Three Cloud Scheduler triggers, all enabled: document ingestion (every 5 minutes), weekly reference refresh (Sundays 03:00 America/Los_Angeles) and reminder dispatch (every 15 minutes UTC, resumed October 11). The nightly ADR scan trigger was deleted October 11. After [#151](https://github.com/sjsu-masters-projects/medi-agent/pull/151) deployed, each job logged a successful `scheduled_job.finished` line ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). | Watch the first Sunday refresh and the first reminder that is actually due. |
| Patient symptoms | #141 removes hard-coded examples and routes Today directly to Nora | No connected patient timeline of confirmed reports; raw chat capture is not a complete confirmation workflow. |
| ADR patient information loop | Ganesh's [#136](https://github.com/sjsu-masters-projects/medi-agent/pull/136) open, conflicting since October 9; author reports staging migration and authenticated local-branch acceptance. [#150](https://github.com/sjsu-masters-projects/medi-agent/pull/150) (MedWatch-compatible draft lifecycle, PV-002) is stacked on it. | Neither is merged or deployed on canonical apps. |

Evidence: [deployed recheck](../docs/deployed-recheck-2026-10-11.md),
[PAT-005 acceptance](../docs/pat-005-final-acceptance-2026-10-10.md),
[portal review](../docs/portal-ui-ux-review-2026-10-10.md),
[scheduling contract](specs/sch-001-appointment-scheduling.md),
[conversation contract](specs/com-001-two-way-conversations.md).
This is prototype acceptance, not clinical/compliance/production certification.

## Current sprint

| Issue | Priority | Status | Owner | Next observable result |
| --- | --- | --- | --- | --- |
| LOC-001 — One language setting, bilingual approved wording | P1 | Verify deployed | Rajeev | [Spec](specs/loc-001-bilingual-approved-wording.md) · [#145](https://github.com/sjsu-masters-projects/medi-agent/pull/145) merged and deployed: care-plan wording drafted and approved in en-US and es-MX together; Today/Reminders follow `preferred_language`; bilingual record titles. Deployed Profile switch to Spanish changed Today to the approved Spanish wording with unchanged reminder times ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). Remaining: approve a new bilingual draft on the deployed clinician portal when one exists. Follow-ups are LOC-002. |
| PAT-005-L — Presentation recheck | P1 | Verify deployed | Rajeev | Saved-locale Today controls verified on the deployed app ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). Remaining: duplicate-skipped explanation in both document surfaces, which needs a new byte-identical synthetic upload (the earlier duplicate no longer exists). |
| PV-001-B — ADR patient answers | P1 | Blocked | Ganesh | Resolve #136 conflicts, integrate current chat/language UI, reverify and request review; canonical rollout acceptance then follows. |
| PAT-002-B — Confirmed symptom intake | P1 | Ready | Unassigned; Tushar + Ganesh lanes | Inventory existing capture, then a reviewed question library, attributable draft, correct/confirm/cancel, bounded retrieval and ownership, with bilingual tests. |
| PAT-002-C — Real symptom timeline | P2 | Blocked | Unassigned; Tushar + Jeevan lanes | Confirmed-report contract from B, then actual saved reports and authorized clinician detail; no invented history. |
| SCH-001-V — Canonical scheduling acceptance | P2 | Verify deployed | Tushar + Jeevan | Record deployed offer → patient response → persisted visit/calendar flow; distinguish earlier branch/staging proof. |
| PAT-001-A — Terminal chat-turn recovery | P2 | Ready | Unassigned; Ganesh + patient lane | Persist bounded processing/completed/failed/interrupted outcomes; retry/reconnect without duplicate messages/actions. |
| PAT-004 — Focused-document chat | P2 | In progress | Rajeev + Ganesh/Tushar | "Ask about this document" opens Nora on that document in its own conversation ([#146](https://github.com/sjsu-masters-projects/medi-agent/pull/146), [#147](https://github.com/sjsu-masters-projects/medi-agent/pull/147)). Live October 11: the focus card, a grounded answer and restore after reopening the conversation work; Dismiss did not stick because the server restored the saved document, fixed in [#153](https://github.com/sjsu-masters-projects/medi-agent/pull/153) along with an explicit message when the document is no longer available. Remaining: a visible source on each answer with a per-message document link, replacing the focused document from an open chat, and refresh landing on the same focused conversation. |
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
- [ ] Resolve conflicts and integrate with current human/Nora separation and language controls.
- [ ] Focused/full relevant checks, real PostgreSQL transaction tests, review and required CI.
- [ ] Authorized rollout; patient answers → clinician evidence/score through canonical portals.
- [ ] Preserve patient attribution, unknown answers, prior clinician judgment and audit.

Three safe retrospective questions only: no medication experiments, new treatment
or MedWatch submission. Author records score 3 → 6 with three patient responses;
this is not independent canonical-app proof or full PV-001 completion.

## Done — accepted slices

| Issue | Owner | Delivered scope | Evidence / limit |
| --- | --- | --- | --- |
| OPS-003 — Scheduled job correctness and run logs | Rajeev | Weekly refresh due after six days with documented conditions seeded; reminders for `confirmed` visits, reschedule-aware keys, contiguous windows, conflict fallback, skipped counts; nightly ADR scan retired; `scheduled_job.started`/`finished` run logs ([runbook](CLOUD_INFRASTRUCTURE_GUIDE.md#5-scheduled-jobs-cloud-scheduler-and-run-logs)) | [#151](https://github.com/sjsu-masters-projects/medi-agent/pull/151); requester resumed reminder dispatch and deleted the ADR trigger October 11; first logged runs succeeded: reminders (first-run window, 3 inactive schedules skipped), ingestion, and a manual refresh that seeded 13 conditions and updated 10 subjects ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). The refresh then found no topic for 13 of 29 condition lookups: Spanish was searched with English names, only the first search hit was considered, and qualifiers such as "mild persistent" or "of the knee" defeated the search; some first hits were narrower topics. Fixed in [#153](https://github.com/sjsu-masters-projects/medi-agent/pull/153): best match among several hits, a qualifier fallback, and the Spanish page resolved from the English topic. |
| SEC-002 — GitHub security and code-quality findings | Rajeev | Next.js 16.3.8 in both portals, `google-cloud-aiplatform>=1.133.0` on every lock marker, four CodeQL quality fixes, 8 of 14 AI findings fixed (4 already resolved, 2 not applicable) | [#151](https://github.com/sjsu-masters-projects/medi-agent/pull/151); after merge, 0 open Dependabot alerts, 0 open code-scanning alerts and 0 open CodeQL quality findings. Open requester decision: malware scanning, Dependabot security updates and secret-scanning push protection are disabled. Not a security certification. |
| NOT-001 — Notifications and clinician alerts | Rajeev | Recipient-scoped in-app centre for patients and clinicians: shared authorized work, private message notifications, atomic capture, read snapshots, bilingual copy ([contract](specs/not-001-notification-centre.md)) | [#148](https://github.com/sjsu-masters-projects/medi-agent/pull/148); verified in disposable PostgreSQL 16 and on the deployed portals October 11 ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). |
| NOT-002 — Notification follow-ups | Rajeev | Compact lists, one unread count, real times for existing work, partial "Mark all read", account deletion through conversations/offers, page-proportional reads, Earlier messages, appointment response rule, one item per answered offer, consistent refreshes (migrations 052–056, applied October 11) | [#149](https://github.com/sjsu-masters-projects/medi-agent/pull/149); local end-to-end check plus deployed acknowledgement, bulk read, matching counts and Spanish copy ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). Follow-ups are NOT-003. |
| UX-001 — Both portal UI/UX polish | Rajeev; lane review | Inventory, simplified content, saved patient language, responsive layouts and accessible dialogs | [#141](https://github.com/sjsu-masters-projects/medi-agent/pull/141); screens since replaced by UX-002, rechecked together on the deployed portals ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). |
| UX-002 — Reference-led portal redesign | Rajeev | Reference-led patient and clinician redesign with responsive and wording follow-up ([requirements](specs/ux-002-reference-redesign.md)) | #142–#145 ([overhaul checks](../docs/ux-002-overhaul-verification.md)); deployed screens at 390 and 1280 px without errors or horizontal scrolling, both patient locales ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). |
| NORA-001 — Nora answers every message | Rajeev | Relative model deadline under uvloop, a triage decision on every follow-up, document handoff from Records, message language labels | [#146](https://github.com/sjsu-masters-projects/medi-agent/pull/146); deployed chat answered every message in English and Spanish ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). |
| NORA-002 — Grounded, plain-language Nora | Rajeev | Shared MedlinePlus/DailyMed/RxNorm cache, record and document tools with server-written sources, daily conversations, replies in the language the patient uses, female Spanish voice, AI-004 safety changes ([spec](specs/nora-002-grounded-answers.md)); supersedes RAG-001 | [#147](https://github.com/sjsu-masters-projects/medi-agent/pull/147); deployed answers grounded in the record with dated MedlinePlus and DailyMed sources, Spanish and English regardless of the app setting ([deployed recheck](../docs/deployed-recheck-2026-10-11.md)). Voice on a phone is VOI-001; refresh cadence fixed in OPS-003. |
| DOC-001 — Board and documentation cleanup | Rajeev | #141 routing/evidence cleanup merged. October 11: hand-written migration list replaced by the ledger script in CONTRIBUTING; ARCHITECTURE, docs map and READMEs updated for NORA-002 and NOT-001; retired drug-RAG docs removed; false allergy/duplicate-therapy rule claim corrected; HANDOFF traps recorded. Repeat per PR, not as a separate task. | Kept current per PR from now on. |
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
| PAT-PROFILE-001 | P2 | In review | Patient lane | Live October 11: a gender value saves and survives reload, but "Not specified" reported success and kept the old value (both portal and API dropped the empty value). Fix in [#153](https://github.com/sjsu-masters-projects/medi-agent/pull/153); then record a deployed clear-and-reload check. Not required signup data. |
| REC-001 | P2 | In progress | Rajeev + Jeevan | Remaining correction/deletion/projection paths, display-title reuse in citations and care-plan review (titles shipped in LOC-001), and recovery matrix; extraction/viewers already exist. |
| REC-002 | P2 | In progress | Rajeev + Jeevan | Explicit add/update/keep/defer/reject reconciliation and live proof; no automatic truth overwrite. |
| NOT-003 | P2 | Backlog | Rajeev | NOT-002 follow-ups: a dedicated signing key for notification read tokens; clinician account deletion is blocked by document upload/review provenance and SOAP annotations (needs a decision). |
| MED-001 | P2 | Backlog | Ganesh + Rajeev | Full multi-source medication identity/conflict/allergy matching, freshness, uncertainty and approved history. NORA-002's cached RxNorm ingredient resolution can be reused. There is no deterministic interaction, allergy-conflict or duplicate-therapy checker yet; the docstrings that claimed one are corrected. Also: RxNorm normalization in live ingestion, and a later migration to drop the unused `drug_knowledge_chunks` table (the old drug RAG was removed in #147). |
| MED-002 | P2 | Backlog | Jeevan | Full-source comparison/defer/request-confirmation and approved updates/export; depends MED-001/REC-002. |
| CLN-001 | P2 | In progress | Jeevan | Unified review queue and priority/age/source/update/decision paths; separate screens exist. |
| CLN-002 | P2 | Backlog | Jeevan + Ganesh | Versioned risk explanations/freshness and chronological cross-domain events. |
| PV-001 | P1 | In progress | Ganesh | #136 information loop, confirmed-report B/C and evidence-driven reassessment; score is not a clinician verdict. #150 adds the MedWatch draft (PV-002). |
| PV-002 | P2 | Blocked | Ganesh (#150); Jeevan review | [#150](https://github.com/sjsu-masters-projects/medi-agent/pull/150): assigned-clinician draft from reviewed ADR evidence, field attribution, edit revisions, approval attestation, audit and JSON export; never FDA submission. Blocked on #136 (stacked); then review, migration 048 rollout and authorized live acceptance. |
| SCH-001 | P2 | In progress | Tushar + Jeevan | SCH-001-V; later clinician cancellation/completion and approved-workflow booking. [Spec](specs/sch-001-appointment-scheduling.md). |
| COM-001 | P2 | In progress | Jeevan + Tushar | Beyond private threads: opt-in administrative delivery/retry/operations and care-gap tasks; shared clinic inbox separately scoped. |
| VOI-001 | P2 | In progress | Tushar + Ganesh | #147: speech is transcribed in multilingual mode and labelled with the language spoken (Spanish under an English app setting no longer returns an empty transcript); Spanish voice is female (Aura-2 Estrella); spoken replies skip the source line; transcripts are no longer logged. Remaining: transcript/state, interruption/reconnect/cancel, bilingual text-fallback acceptance and hands-free on a phone. |
| CON-001 | P2 | Backlog | Jeevan + Rajeev | Longitudinal timeline, reviewed handoff/export and explicit care-team visibility restrictions. |
| INT-002 | P2 | In progress | Rajeev | Import of 12 resource types with validation, deduplication and review-only candidates exists. Remaining: keep and normalize source identifiers (currently dropped), export of local facts as a validated R4 Bundle, round-trip fixtures, and page/size caps when following sandbox bundle links. [Spec](specs/int-002-003-interoperability-plan.md). |
| INT-003-V | P2 | In review | Rajeev | Diagnosed October 11: "Invalid launch options" is the sandbox's response to an authorize request with neither a launch parameter nor a simulator segment, and the configured standalone simulator code was not a valid launcher encoding (the sandbox ran a provider-EHR flow). [#153](https://github.com/sjsu-masters-projects/medi-agent/pull/153) uses a valid patient-standalone code and keeps the provider's error description. Remaining: one recorded live standalone run to the review hand-off; the passed EHR launch is not reopened. |
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
