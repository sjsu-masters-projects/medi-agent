# MediAgent — Project task board

> **Active plan:** [PAT-005](specs/pat-005-clinician-approved-today-feed-plan.md)
>
> **Updated:** October 10, 2026 · **Feature freeze:** December 4, 2026
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
| Main deployment | `ce3799a`, [#140](https://github.com/sjsu-masters-projects/medi-agent/pull/140) merged; October 10 main CI/backend deployment and both portal commit statuses succeeded | Deployment signals do not prove every screen was retested. |
| PAT-005 core | Synthetic Morgan/Elena loop verified live, including V2 continuity, six barriers, audit, Spanish V3 and non-scheduled-day absence | V3 active; V4 is an unpublished overlap-blocked draft. Presentation follow-up is separate. |
| Patient-upload review | [#138](https://github.com/sjsu-masters-projects/medi-agent/pull/138) deployed; pending/rejected exclusion, approval eligibility/queue handoff and exact-document link verified | Negative preview/publication guards have API/PostgreSQL evidence, not a newly repeated live blocked publication. |
| Human messaging | [#139](https://github.com/sjsu-masters-projects/medi-agent/pull/139) deployed; migration checked; bilingual replies, actual sender/clinic, unread and reload persistence verified | Concurrency/reassignment/multiple-recipient isolation tested in isolated PostgreSQL, not repeated by the four-message live run. |
| Portal polish | [#141](https://github.com/sjsu-masters-projects/medi-agent/pull/141) merged at `657602d`; original local checks: 372 patient + 260 clinician tests and both app checks pass | Authenticated deployed UI checks remain separate from merge; UX-002 replaces the visual direction. |
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
| UX-001 — Both portal UI/UX polish | P1 | Verify deployed | Rajeev; patient/clinician lane review | #141 merged; recheck authenticated screens at narrow widths and both patient locales after deployment. |
| UX-002 — Reference-led portal redesign | P1 | In review | Rajeev | [Requirements](specs/ux-002-reference-redesign.md): Foundation #142 merged → Patient screens prepared for review (420 tests, build and entry mobile checks pass; authenticated visual acceptance pending) → Clinician screens next. [Foundation checks](../docs/ux-002-foundation-verification.md); [patient acceptance checklist](../docs/ux-002-patient-verification.md). Unchanged routes/API/clinical gates; prior uncommitted theme draft is excluded. |
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
- [x] Approved clinical wording/history unchanged; language switching does not translate/publish a plan.
- [x] Responsive layouts, tap/keyboard help, refresh/recovery and accessible dialogs.
- [x] Four workstream reviews/cross-review fixes integrated; 632 tests and both app checks pass.
- [x] Remove fabricated timeline; Today opens Nora directly, old Symptoms URL is an honest compact handoff.
- [x] Merge #141 (`657602d`); post-deployment observations remain separate.
- [ ] Authenticated post-deployment mobile/bilingual screen checks.

Local 320/768/1280 component/layout checks are not every deployed route.
Patient symptom history, existing MFA lookup-failure handling and dashboard
unknown-versus-zero API ambiguity are documented limits.
[Scope and evidence](../docs/portal-ui-ux-review-2026-10-10.md).

### PAT-005-L acceptance

- [ ] Saved es-MX updates Today chrome/actions/barriers; reviewed wording and reminder times stay unchanged.
- [ ] Duplicate fixture displays skipped extraction in patient Records and clinician Documents/Review Queue, with source accessible and no false empty-facts review.
- [ ] Record these observations in the acceptance report, then close this slice.

#140 is deployed. No new migration/reset/publication needed. Keep V3 active;
V4 publication is not a QA requirement.

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
| CON-001 | P2 | Backlog | Jeevan + Rajeev | Longitudinal timeline, reviewed handoff/export and explicit care-team visibility restrictions. |
| INT-002 | P2 | In progress | Rajeev | Identifier quality, approved export/round-trip fixtures; supported import exists. [Spec](specs/int-002-003-interoperability-plan.md). |
| INT-003-V | P2 | Ready | Rajeev | Standalone sandbox Invalid launch options diagnosis; passed EHR launch not reopened. |
| SAFE-001 | P2 | In progress | Rajeev; safety/clinical review | Future executor tiers and fixture actions/proxies with no supported route; feature guards/audit exist. |
| SAFE-002 | P1 | In progress | Ganesh; peer safety review | Synthetic rule/wording tests and durable per-turn rule/outcome audit; no professional recruitment required and no clinical-validation claim. [Runtime contract](../docs/decisions/ai-runtime-2026-09.md). |
| AI-003 | P2 | In progress | Rajeev + Ganesh | Durable recovery/context/evidence gaps and bounded availability metrics. [Runtime contract](../docs/decisions/ai-runtime-2026-09.md). |
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
