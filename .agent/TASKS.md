# MediAgent — Project task board

> **Active plan:** [NOT-001](specs/not-001-notification-centre.md) · [accepted PAT-005 contract](specs/pat-005-clinician-approved-today-feed-plan.md)
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
| Main deployment | `4c9de30`, [#147](https://github.com/sjsu-masters-projects/medi-agent/pull/147) merged after [#146](https://github.com/sjsu-masters-projects/medi-agent/pull/146); October 11 main CI, frontend CI and backend Cloud Run deployment succeeded, including the new `mediagent-health-knowledge-refresh` Job | Deployment signals do not prove every screen was retested. |
| PAT-005 core | Synthetic Morgan/Elena loop verified live, including V2 continuity, six barriers, audit, Spanish V3 and non-scheduled-day absence | V4 approved October 10 in English and Spanish under LOC-001 after removing a duplicate-upload overlap ([evidence](specs/loc-001-bilingual-approved-wording.md#verification--2026-10-10-synthetic-environment)). Presentation follow-up is separate. |
| Patient-upload review | [#138](https://github.com/sjsu-masters-projects/medi-agent/pull/138) deployed; pending/rejected exclusion, approval eligibility/queue handoff and exact-document link verified | Negative preview/publication guards have API/PostgreSQL evidence, not a newly repeated live blocked publication. |
| Human messaging | [#139](https://github.com/sjsu-masters-projects/medi-agent/pull/139) deployed; migration checked; bilingual replies, actual sender/clinic, unread and reload persistence verified | Concurrency/reassignment/multiple-recipient isolation tested in isolated PostgreSQL, not repeated by the four-message live run. |
| Portal polish | [#141](https://github.com/sjsu-masters-projects/medi-agent/pull/141) merged at `657602d`; original local checks: 372 patient + 260 clinician tests and both app checks pass | Authenticated deployed UI checks remain separate from merge; UX-002 replaces the visual direction. |
| Reference redesign | [#144](https://github.com/sjsu-masters-projects/medi-agent/pull/144) merged at `a36fc37`; responsive and wording follow-up in [#145](https://github.com/sjsu-masters-projects/medi-agent/pull/145) | Authenticated deployed screen recheck not yet recorded. |
| Synthetic database schema | Migrations 049 (LOC-001), 050 (record titles) and 051 `051_health_knowledge_and_chat_sessions.sql` (NORA-002) applied with requester authorization ([LOC-001 evidence](specs/loc-001-bilingual-approved-wording.md#verification--2026-10-10-synthetic-environment)). `051_notification_centre.sql` (NOT-001) applied by the requester October 11. `052_notification_source_times.sql` is pending | Apply 052 before its branch deploys; it only redefines one function. The ledger's extra `047_adr_patient_information_loop.sql` comes from #136. |
| Patient symptoms | #141 removes hard-coded examples and routes Today directly to Nora | No connected patient timeline of confirmed reports; raw chat capture is not a complete confirmation workflow. |
| ADR patient information loop | Ganesh's [#136](https://github.com/sjsu-masters-projects/medi-agent/pull/136) open, conflicting; author reports staging migration and authenticated local-branch acceptance | Not merged or deployed on canonical apps. |

Evidence: [PAT-005 acceptance](../docs/pat-005-final-acceptance-2026-10-10.md),
[portal review](../docs/portal-ui-ux-review-2026-10-10.md),
[scheduling contract](specs/sch-001-appointment-scheduling.md),
[conversation contract](specs/com-001-two-way-conversations.md).
This is prototype acceptance, not clinical/compliance/production certification.

## Current sprint

| Issue | Priority | Status | Owner | Next observable result |
| --- | --- | --- | --- | --- |
| NOT-001 — Notifications and clinician alerts | P1 | Verify deployed | Rajeev | [Contract](specs/not-001-notification-centre.md) · [#148](https://github.com/sjsu-masters-projects/medi-agent/pull/148): recipient-scoped in-app centre for patients (bell, sheet, Notifications page) and clinicians (bell panel, Alerts with Needs attention/History), shared authorized work, private message notifications, atomic capture, read snapshots and bilingual copy. Review fixes: every RPC failed on PostgreSQL (ambiguous variable); account deletion and the demo reset were blocked; malformed rows broke a person's centre; appointment events are now routed by transition and actor; history keeps exact-source links; opening an item marks it read; Spanish uses tú; polling is once a minute; dialogs cover the whole screen. Verified in disposable PostgreSQL 16 and in both portals at phone, tablet and desktop widths with synthetic fixtures. Merged in #148; `051_notification_centre.sql` applied. Compact list redesign and migration `052_notification_source_times.sql` (existing work keeps its real time) follow in `feature/notification-ui-compact`. Next: apply 052, then recheck with real synthetic accounts. Follow-ups: database work per poll still grows with a user's full history (NOT-002); the batch "Mark all read" fails if one item became inaccessible. |
| UX-001 — Both portal UI/UX polish | P1 | Verify deployed | Rajeev; patient/clinician lane review | #141 merged; recheck authenticated screens at narrow widths and both patient locales after deployment. |
| UX-002 — Reference-led portal redesign | P1 | Verify deployed | Rajeev | [Requirements](specs/ux-002-reference-redesign.md): #142–#145 merged ([overhaul checks](../docs/ux-002-overhaul-verification.md)). Next: authenticated deployed recheck at phone and desktop widths, including responsive/wording follow-up. |
| LOC-001 — One language setting, bilingual approved wording | P1 | Verify deployed | Rajeev | [Spec](specs/loc-001-bilingual-approved-wording.md) · [#145](https://github.com/sjsu-masters-projects/medi-agent/pull/145) merged and deployed: care-plan wording drafted and approved in en-US and es-MX together; Today/Reminders follow `preferred_language`; bilingual record titles. Next: authenticated deployed recheck in both locales. Follow-ups are LOC-002. |
| NORA-001 — Nora answers every message | P1 | Verify deployed | Rajeev | [#146](https://github.com/sjsu-masters-projects/medi-agent/pull/146) merged and deployed: relative model deadline under uvloop, a triage decision on every follow-up message, document handoff from Records, and message language labels; verified live on the branch in English and Spanish. Next: recheck deployed chat. |
| NORA-002 — Grounded, plain-language Nora | P1 | Verify deployed | Rajeev | [Spec](specs/nora-002-grounded-answers.md) · merged in [#147](https://github.com/sjsu-masters-projects/medi-agent/pull/147) and deployed: shared MedlinePlus/DailyMed/RxNorm reference cache, medication/condition/document tools with server-written sources, daily conversations with New chat and past conversations, replies and speech in the language the patient uses, female Spanish voice, plain-language document explanations, AI-004 safety changes. Weekly refresh trigger `mediagent-health-knowledge-refresh-weekly` (Sundays 03:00 America/Los_Angeles, invoker-only service account `mediagent-knowledge-sched`) created with requester authorization October 11; a manual run succeeded and checked 17 subjects. Next: recheck deployed chat and voice. |
| PAT-005-L — Presentation recheck | P1 | Verify deployed | Rajeev | Confirm #140 saved-locale Today controls and duplicate-skipped explanations in both document surfaces; sources/history unchanged. |
| PV-001-B — ADR patient answers | P1 | Blocked | Ganesh | Resolve #136 conflicts, integrate current chat/language UI, reverify and request review; canonical rollout acceptance then follows. |
| PAT-002-B — Confirmed symptom intake | P1 | Ready | Unassigned; Tushar + Ganesh lanes | Inventory existing capture, implement missing draft → correct/review → patient confirmation boundary with bilingual tests. |
| PAT-002-C — Real symptom timeline | P2 | Blocked | Unassigned; Tushar + Jeevan lanes | Confirmed-report contract from B, then actual saved reports and authorized clinician detail. |
| SCH-001-V — Canonical scheduling acceptance | P2 | Verify deployed | Tushar + Jeevan | Record deployed offer → patient response → persisted visit/calendar flow; distinguish earlier branch/staging proof. |
| PAT-001-A — Terminal chat-turn recovery | P2 | Ready | Unassigned; Ganesh + patient lane | Persist bounded processing/completed/failed/interrupted outcomes; retry/reconnect without duplicate messages/actions. |
| PAT-004 — Focused-document chat | P2 | In progress | Rajeev + Ganesh/Tushar | Verify focus identity, route reuse, dismiss/replace, refresh/reconnect and unavailable-source behavior. |
| DOC-001 — Board and documentation cleanup | P2 | In review | Rajeev | Board/spec routing, consolidated evidence and obsolete auth checklist retirement prepared in #141; review before merging. |
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
- [ ] Authenticated post-deployment mobile/bilingual screen checks.

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
- [ ] #145 CI, review and merge; deployment.
- [ ] Deployed: approve a bilingual draft from the clinician portal and switch the patient's saved language in Profile, observing Today change. (Spanish was verified read-only server-side, not through the Profile switch.)
- [ ] Clinician review of the second synthetic patient's bilingual V3 draft (left for a clinician decision).

### PAT-005-L acceptance

- [ ] Saved es-MX updates Today chrome/actions/barriers and, since LOC-001, approved bilingual wording; reminder times stay unchanged.
- [ ] Duplicate fixture displays skipped extraction in patient Records and clinician Documents/Review Queue, with source accessible and no false empty-facts review.
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
| PAT-005 — Controlled care-plan → Today loop | Rajeev; portal support | Fresh synthetic uploads, grounded draft, protected source/review/blockers, approval, Today, completion/barriers and clinician follow-up | [Acceptance report](../docs/pat-005-final-acceptance-2026-10-10.md). |
| PAT-005-A/B/D/E/G/I/K — Draft and publication safeguards | Rajeev | Diagnostics, draft visibility, active/proposed/source review, locale/medication attestation, incomplete evidence, overlaps and exact preview | Merged #114–#125; durable [PAT-005 specification](specs/pat-005-clinician-approved-today-feed-plan.md). |
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
| PAT-002-B | P1 | Ready | Unassigned | Reviewed question library, attributable draft, correct/confirm/cancel, bounded retrieval and ownership. |
| PAT-002-C | P2 | Blocked | Unassigned | B's report contract, real patient timeline and authorized clinician detail; no invented history. |
| PAT-003 | P1 | In progress | Tushar; Jeevan review | #141 global locale rollout; bilingual voice/errors/consent and high-risk wording review. |
| LOC-002 | P2 | Backlog | Unassigned; patient + runtime lanes | LOC-001 follow-ups ([spec](specs/loc-001-bilingual-approved-wording.md)): notifications and Today errors from codes; sign-up saves the guest language and the server renders `lang` without an English flash; one label set for the two locales; clinician patient-language chip and per-message language; chat locale from the profile including mid-session switches; cached per-locale document explanations; one Spanish register. |
| PAT-004 | P2 | In progress | Rajeev + runtime/patient lanes | Per-turn visible focus/provenance and route/reconnect/unavailable-source acceptance. |
| PAT-PROFILE-001 | P2 | In review | Patient lane | #141 optional gender/unset presentation, then save/reload verification; not required signup data. |
| REC-001 | P2 | In progress | Rajeev + Jeevan | Remaining correction/deletion/projection paths, sourced display titles and recovery matrix; extraction/viewers already exist. |
| REC-002 | P2 | In progress | Rajeev + Jeevan | Explicit add/update/keep/defer/reject reconciliation and live proof; no automatic truth overwrite. |
| MED-001 | P2 | Backlog | Ganesh + Rajeev | Full multi-source medication identity/conflict/allergy matching, freshness, uncertainty and approved history. |
| MED-002 | P2 | Backlog | Jeevan | Full-source comparison/defer/request-confirmation and approved updates/export; depends MED-001/REC-002. |
| CLN-001 | P2 | In progress | Jeevan | Unified review queue and priority/age/source/update/decision paths; separate screens exist. |
| CLN-002 | P2 | Backlog | Jeevan + Ganesh | Versioned risk explanations/freshness and chronological cross-domain events. |
| PV-001 | P1 | In progress | Ganesh | #136 information loop, confirmed-report B/C and evidence-driven reassessment; score is not a clinician verdict. |
| PV-002 | P2 | Blocked | Jeevan | Confirmed facts/ADR review → editable cited draft → sign-off/export; never FDA submission. |
| SCH-001 | P2 | In progress | Tushar + Jeevan | SCH-001-V; later clinician cancellation/completion and approved-workflow booking. [Spec](specs/sch-001-appointment-scheduling.md). |
| COM-001 | P2 | In progress | Jeevan + Tushar | Beyond private threads: opt-in administrative delivery/retry/operations and care-gap tasks; shared clinic inbox separately scoped. |
| VOI-001 | P2 | In progress | Tushar + Ganesh | Transcript/state, interruption/reconnect/cancel and actual bilingual text-fallback acceptance. |
| NOT-002 | P2 | Backlog | Rajeev | NOT-001 follow-ups: bound the per-poll database work (prepare and authorization currently scan all of a user's receipts and every system-wide safety event, with dynamic source reads per row) with cursor-limited scans and indexed counts; let "Mark all read" skip items that became inaccessible instead of failing the batch; consider a key derived for notification tokens rather than the Supabase JWT secret. Outside NOT-001 but found by its PostgreSQL suite: deleting a patient account is still blocked by `care_conversation_messages.sender_id`/`actor_id` (048) and `appointment_offer_events.patient_id` (041), which have no delete rule; deciding their retention needs a team decision and a new migration. |
| CON-001 | P2 | Backlog | Jeevan + Rajeev | Longitudinal timeline, reviewed handoff/export and explicit care-team visibility restrictions. |
| INT-002 | P2 | In progress | Rajeev | Identifier quality, approved export/round-trip fixtures; supported import exists. [Spec](specs/int-002-003-interoperability-plan.md). |
| INT-003-V | P2 | Ready | Rajeev | Standalone sandbox Invalid launch options diagnosis; passed EHR launch not reopened. |
| SAFE-001 | P2 | In progress | Rajeev; safety/clinical review | Future executor tiers and fixture actions/proxies with no supported route; feature guards/audit exist. |
| SAFE-002 | P1 | In progress | Ganesh; peer safety review | Synthetic rule/wording tests and durable per-turn rule/outcome audit; no professional recruitment required and no clinical-validation claim. [Runtime contract](../docs/decisions/ai-runtime-2026-09.md). |
| AI-003 | P2 | In progress | Rajeev + Ganesh | Durable recovery/context/evidence gaps and bounded availability metrics. [Runtime contract](../docs/decisions/ai-runtime-2026-09.md). |
| AI-004 — Prompt review follow-ups | P1 | In progress | Rajeev; safety review (SAFE-002) | Text-only fixes shipped in [#145](https://github.com/sjsu-masters-projects/medi-agent/pull/145). The held behaviour changes shipped with NORA-002 in [#147](https://github.com/sjsu-masters-projects/medi-agent/pull/147): 911 guidance and a care-team alert for symptom severity 9–10 (the deterministic floor still answers explicit emergencies first); SOAP assessment/plan framed as considerations for clinician review; extraction document text fenced as data; the unused legacy chat-response prompt retired; no gendered titles in Spanish. Decided October 11 by the requester: Nora answers in the language the patient writes or speaks, whatever the app is set to; the setting controls the screens. Remaining: reviewer-agent findings and evaluation runs. |
| RAG-001 — Grounded drug and document retrieval | P1 | Verify deployed | Rajeev + Ganesh | Superseded by NORA-002, merged in [#147](https://github.com/sjsu-masters-projects/medi-agent/pull/147): the per-turn pgvector retrieval whose result never reached the model, its one-time ingest script and `drug_knowledge_service` are removed; reference text is fetched by RxNorm ingredient with versioned DailyMed labels (interactions and contraindications included) and refreshed weekly; Nora searches the patient's own documents and reads extracted items with page excerpts. Still missing: a deterministic interaction or allergy-conflict checker (claims corrected in `app/safety`; belongs to MED-001), and RxNorm normalization in live ingestion (MED-001). `drug_knowledge_chunks` is left in place until a later migration drops it. |
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
