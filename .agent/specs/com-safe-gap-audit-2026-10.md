# COM-001 / SAFE-001 / SAFE-002 code-level gap audit (October 22, 2026)

> **Status:** Audit only. No feature code, schema, statuses or acceptance claims
> changed. Basis: `origin/main` at `de2a7782` (after #216), read
> statically. **Nothing here was executed or checked against a deployed
> environment**; anything needing a running service is marked *unverified*.
> Feature freeze: December 4, 2026.

Sizes: **S** under a day, **M** one to three days, **L** more than three days
including tests and both-portal UI. "Expo" means needed for the university-expo
demo with fictional data, not for any production claim.

## Summary of the real gaps

| Row | Real gaps (largest first) | Contradicted claims |
| --- | --- | --- |
| COM-001 | Care-gap tasks for missed follow-up do not exist (L if a task surface, M if reusing the notification centre); no operations view of email delivery (M); administrative reminders are in-app only and unrelated to email (M, optional) | Backlog text says clinician-to-patient email existed as a backend endpoint; the code rejects the `email` channel |
| SAFE-001 | `ClinicalActionService` has no production caller, so tier enforcement guards nothing live (M); four of eight fixture denial cases cannot be exercised and the script is not in CI (S to M); no `clinician` proposer proof for the top tier (S) | "`propose` enforces it" is true only inside an unwired service |
| SAFE-002 | `urgent_medication_error` turns are rejected by the safety RPC on the live WebSocket path and the patient gets an unsaved turn with no alert (S, bug); no per-turn audit for non-emergency, escalated or cleared turns (M); safety plugin audits by log line only (S to M) | Row implies durable per-turn audit is partly there; only emergency floor halts on one path are durable |

---

## COM-001 — administrative delivery/retry/operations and care-gap tasks

Row (TASKS.md:253): "Beyond private threads: opt-in administrative delivery/retry/operations
and care-gap tasks; shared clinic inbox separately scoped." Linked specs:
[`com-001-two-way-conversations.md`](com-001-two-way-conversations.md) (covers COM-001-B only),
`project-backlog-acceptance.md` § COM-001, [`email-001-email-flows.md`](email-001-email-flows.md),
[`not-001-notification-centre.md`](not-001-notification-centre.md).

| Requirement (backlog § COM-001) | Shipped? and evidence | Gap | Size | Owner / lane | Expo? |
| --- | --- | --- | --- | --- | --- |
| Patient-to-care-team and clinician-to-patient message paths | Yes. Private threads: `backend/src/app/routers/care_conversations.py`, `services/care_conversation_service.py`; legacy one-way `ClinicianService.send_patient_message` (`services/clinician_service.py:189`). Tests: `tests/integration/test_care_conversation_postgres.py` | None for the two-way path. Shared clinic inbox is explicitly separate scope | - | Done (COM-001-B) | Already in demo |
| Require approval for clinical outbound messages | Partly by design. The spec treats a clinician's explicit send as approval and no AI message is sent automatically. `routine_message` is registered in `core/action_tiers.py:38` | No message path calls `ClinicalActionService`, so the tier is declarative only (see SAFE-001). Nothing AI-authored is sent, so there is no live exposure | S (decide and document that explicit send is the approval; no code) | Rajeev + Jeevan decision | Document only |
| Opted-in administrative reminders | Partly. Email opt-in with verified mailbox and consent: `email_contacts` and `private.email_eligible` (`migrations/057_email_delivery.sql`), preference types messages/appointments/care_plans/records/reviews (`private.email_preference`, same file), routers `routers/email_preferences.py`, UI `apps/*/src/components/features/email-preferences.tsx`. Patient reminders are opt-in schedules (`services/reminder_schedule_service.py`, `cron_service.py:326,384`) delivered **in-app only** | `appointment_reminder`, `med_reminder`, `obligation_reminder` events (`migrations/051_notification_centre.sql:6-10`) have no email preference mapping, so reminders never email. No reminder consent beyond per-activity schedules | M, optional | Rajeev (backend) + Jeevan (patient UI) | No. In-app reminders already demo |
| Retry | Yes for email. `email_delivery_operation` claim/freeze/finish with lease, 2-minute lease, 5 attempts, 23-hour cap, same idempotency key (`migrations/057:178-224`, `services/email_service.py:485-540`). Worker route `routers/cron.py:35`. Tests: `tests/unit/services/test_email_service.py` (34 tests), `tests/integration/test_email_postgres.py` | Rows reaching `failed` (attempts or age) or `bounced` are terminal and have no requeue or operator action; payload is nulled at failure. Retry for other channels (reminders) is the next cron window only (`OPS-003`) | S to M | Rajeev | No |
| Deduplication | Yes. `email_outbox.dedupe_key UNIQUE` (`057:40`), notification `dedupe_key` for reminders (`cron_service.py:754-810`) | None found | - | - | - |
| Delivery state | Partly. States queued/sending/accepted/delivered/bounced/failed/suppressed with Resend reconciliation (`057:41`, `email_service.py:541-557`). Spec warns accepted is not inbox receipt | State is not shown to any user. Patients see no per-message delivery status (the spec forbids fake delivered/read claims), clinicians see none either | S (copy and a read-only count) | Rajeev | No |
| Operations queue | **No.** `routers/ops.py` exposes only model availability counters (`ops.py:21`). `EmailDeliveryService.pending` (`email_service.py:507`) is used only by the cron dry run. Grep of `apps/*/src` finds no outbox or delivery UI. Scheduled-job runs are logged (`OPS-003`) but not surfaced | Admin-facing read of outbox counts by state, oldest queued age, failed/bounced list without addresses or bodies, plus a bounded requeue for `failed`. Needs RLS or service-role-only read, no PHI | M (backend read plus clinic-admin page) | Rajeev (backend), Jeevan (clinician admin UI) | Optional. A single "delivery health" card is enough |
| Care-gap tasks for missed follow-up | **No.** Grep of backend and migrations finds no care-gap, missed-follow-up or overdue entity. `POST /appointments/{id}/no-show` only sets status (`routers/appointments.py:170`). Adherence `missed` exists as an enum and counter (`models/enums.py:143`, `models/feed.py:87`). Notification centre has a `follow_up` category and `barrier_reported` event (`051:6-12`) but no event for a no-show, unreturned offer, or lapsed plan activity | Define the gap source (no-show, offer unanswered N days, unaddressed barrier, overdue review), a task state (open, contacted, resolved, dismissed) with owner and audit, and a clinician worklist. Reusing `notification_events` + open-work (`060_critical_result_open_work`-style actionable items) avoids a new table | M if reusing notification centre actionable items; L if a new task entity and page | Tushar (scheduling source) + Jeevan (clinician UI); Rajeev review for RLS/audit | **Yes, if the demo narrative includes "missed follow-up".** Otherwise defer. Smallest demo slice: no-show creates one actionable item for the assigned clinician (M) |
| Shared clinic inbox | No, intentionally separate | - | L | Unscheduled | No |

### Claims the code contradicts or that are stale (COM-001)

- `project-backlog-acceptance.md` § COM-001 says clinician-to-patient "(in-app and email)" send existed
  as backend endpoints. `ClinicianService.send_patient_message` now **raises** for `channel == "email"`
  (`services/clinician_service.py:202-206`); email goes only through opted-in notice capture. The
  backlog sentence is historical and should be reworded when COM-001 is next edited.
- The tracker row's "opt-in administrative delivery/retry" reads as unbuilt. Opt-in, dedupe, retry and
  delivery state are shipped under EMAIL-001 (#152/#156/#157); what is missing is operations
  visibility and requeue, not delivery itself.

Unverified: current production email state; whether reminder email was ever intended
(spec `email-001-email-flows.md` excludes per-dose medication email and says optional
notices are the listed kinds only).

---

## SAFE-001 — executor tiers, fixture actions/proxies, feature guards and audit

Row (TASKS.md:259): "Future executor tiers and fixture actions/proxies with no supported
route; feature guards/audit exist." Spec: `project-backlog-acceptance.md` § SAFE-001
(line 47), `core/action_tiers.py` docstring.

| Requirement | Shipped? and evidence | Gap | Size | Owner / lane | Expo? |
| --- | --- | --- | --- | --- | --- |
| Define `ClinicalRecommendation`, `ApprovalDecision`, `ActionEnvelope`, `AuditRecord` | Yes. Models `models/clinical_action.py`; tables `migrations/019_clinical_action_approvals.sql` (RLS select-only for assigned clinicians) | None | - | - | - |
| Tiered authority enforced server-side; unclassified action fails closed | Yes in code: `core/action_tiers.py:36-52`, enforced in `ClinicalActionService.propose` (`services/clinical_action_service.py:32-43`), tier written to audit (`:56-61`). Tests `tests/unit/core/test_action_tiers.py`, `tests/unit/services/test_clinical_action_service.py:169-205` use an in-memory fake | **`ClinicalActionService` has no caller** (grep of `backend/src`: only its own file). The only live writers of these tables are SQL publication functions, which insert the recommendation directly as `executed` with `proposer_type='document_evidence_agent'` and no tier in the audit (`migrations/085_cross_plan_publication.sql:521-535`, earlier `040`, `042`). So tiers guard no live action. Only two types are classified (`publish_care_plan`, `routine_message`); both map to the lower tier | M: route care-plan publication audit through a shared tier-recording helper or SQL function, or explicitly record in the ADR that publication is the sole executor and tiering is a registry for future actions | Rajeev; safety/clinical review | No. Demo does not need it; correct the row text |
| Idempotency keys for envelopes | Yes in service and table: `UNIQUE (recommendation_id, idempotency_key)`, 16-255 chars (`019`), lookup `:130-139`. Unit-tested | `get_or_create_envelope` check-then-insert is not atomic; the unique index would surface a race as `ValidationError`, not the existing row (service `:130-148`). Service unwired, so unreachable today | S | Rajeev | No |
| Record proposer, evidence, reviewer, edits, decision, executor, outcome | Yes in schema (`019`) and service (`:91-116`, `:171-190`) | `record_outcome` allows any assigned clinician to record an outcome, not necessarily the approver; `decide` reads state then writes (race limited by the one-decision unique index `idx_approval_decisions_one_final_decision`) | S | Rajeev | No |
| Block approval by unauthorized, unassigned or proposing clinician | Yes (`:73`, `:76-84`; reason codes `core/authorization_reasons.py`) | `propose` with an `actor_id` only checks assignment; it does not verify the actor is a clinician proposing as a clinician (`proposer_type` is caller text). The top-tier "must be clinician-originated" check therefore trusts the caller | S | Rajeev | No |
| Replay and duplicate-action tests | Unit tests only (`test_clinical_action_service.py:112`). No PostgreSQL test of the action tables outside care-plan publication | PostgreSQL concurrency test for double approve/execute | S | Rajeev | No |
| Record every authorization denial with a reason code from the 403 handler | Yes. `core/exception_handlers.py:40,104`, `services/authorization_audit_service.py:86`, table `authorization_denial_events` (`migrations/033`). Tests `tests/integration/test_authorization_denial_audit.py` | None found. Denial audit is best-effort with a 5-second bound by design | - | - | - |
| Verify fixture's declared denial expectations in a live environment | **Half.** `backend/scripts/verify_authorization_denials.py` maps only `open_patient_chart` and `open_patient_chart_by_direct_id` (`:49-52`). Fixture `negative_access_cases` has 8 cases: SYN-NEG-001, 003, 006, 008 testable; SYN-NEG-002 (`list_patient_documents`), -004 (`view_medication_timeline`), -005 (`view_document_metadata`) have no route (`:58-75`); SYN-NEG-007 uses `actor_proxy_id` and proxies are not persisted (`:80-82`, `docs/synthetic-data-catalog.md:15,49`) | (a) No recorded live run: no doc or evidence file mentions the script's result (grep of `docs`, `.agent`). (b) Script is not in CI (`.github/workflows/ci.yml` runs unit/integration only; unit test dir `tests/unit/scripts` has no test for it). (c) Four cases need a product decision per the script's own rule: which existing route owns a per-patient document list, medication timeline and document metadata, and whether to persist proxies at all | (a) S (run against staging with a requester-authorized synthetic session, record in an evidence file); (b) S; (c) S to M decision, plus M only if a proxy model is built, L if proxy sessions are implemented | Rajeev (script and run); Tushar/Jeevan for route ownership; requester for proxy scope | Run (a): yes if the demo claims access isolation. Proxy implementation: no. Prefer re-labelling the proxy case "declared, not supported" in the fixture catalog |
| Feature guards | Partly. Per-workload kill switches `*_ai_enabled` (`config.py:75-83`) enforced in the registry (`adk/registry.py:159-169`); `symptom_intake_enabled` default false (`config.py:210`, checked `services/symptom_intake_service.py:43`); worker/availability flags (`config.py:194,219`) | Guards are operational switches, not authority checks. No flag gates a future executor and no test asserts a classified action cannot execute while its feature flag is off | S, only when an executor is added | Owner of the future executor | No |

### Claims the code contradicts (SAFE-001)

- The backlog says "`propose` enforces it" and "the applied tier is recorded on the audit trail".
  True for `ClinicalActionService.propose`, but that method is never called by a router, worker
  or SQL function. The tier is **not** recorded for care-plan publication, the only live executor.
- "Fixture actions/proxies with no supported route" is accurate (3 actions plus the proxy actor),
  but the row does not say the script is manual-only and has no recorded result.

---

## SAFE-002 — durable per-turn safety rule/outcome audit; synthetic rule/wording tests

Row (TASKS.md:260): "Synthetic rule/wording tests and durable per-turn rule/outcome audit;
no professional recruitment required and no clinical-validation claim." There is no dedicated
SAFE-002 spec; references are `project-backlog-acceptance.md:191`,
[`nora-002-grounded-answers.md`](nora-002-grounded-answers.md#safety-review-and-live-evidence-2026-10-11)
and [`../docs/decisions/ai-runtime-2026-09.md`](../../docs/decisions/ai-runtime-2026-09.md) (control 1, line 43).

| Requirement | Shipped? and evidence | Gap | Size | Owner / lane | Expo? |
| --- | --- | --- | --- | --- | --- |
| Deterministic floor before any model | Yes. `safety/triage_floor.py:396` (emergency, mental health, medication error; EN and ES, negation handling), `adk/plugins/safety_floor.py:72-101` halts the run, `safety/escalation.py` monotonic escalation, `safety/intake_gate.py`, `chat_turn_service.floor_guidance` (`:318`) | None for rule coverage in scope. No allergy or interaction checker (`safety/__init__.py` docstring, MED-001) | - | - | - |
| Durable record of rule, version and outcome per emergency turn | Yes for two rules on the WebSocket/intake paths. `chat_safety_alerts` stores safety_rule, `rule_version='triage-floor/1'`, result, evaluated time, delivery state and clinicians notified; immutable by trigger; atomic RPC `record_chat_safety_turn` (`migrations/059_chat_safety_alerts.sql:1-125`). Writers: `routers/chat.py:145-150,1518`, `services/symptom_intake_service.py:135`, retry via `services/a2a_retry_worker.py`. Tests: `tests/integration/test_chat_safety_postgres.py` (PostgreSQL), `tests/unit/services/test_chat_safety_service.py` | See rows below | - | - | - |
| **`urgent_medication_error` durability** | **Broken by construction.** `evaluate_intake_safety` returns that rule (`safety/intake_gate.py:17,41`; `triage_floor.py:424-429`), the chat router sends it through `record_safely` (`routers/chat.py:1518-1535`), but the RPC and table CHECK allow only `emergency_symptom_keyword` and `emergency_mental_health_keyword` (`059:8-9,77-79`) and raise 22023. `record_safely` swallows that and returns an `uncertain`, unsaved turn (`services/chat_safety_service.py:33-40`), so the patient sees the same-day copy but no message row, no safety record, no clinician alert. The completion event also hard-codes `urgency: "emergency"` for a verdict whose urgency is `urgent` (`routers/chat.py:127`). No test covers this rule through the RPC (grep of tests for `urgent_medication_error` shows only floor/copy/plugin tests) | Widen the CHECK and RPC, persist true urgency, choose whether a same-day (not 911) alert goes to clinicians, add PostgreSQL and router tests. **Needs a new migration, not authorized here** | S for code and test; migration application is a requester step | Rajeev; peer safety review (Ganesh) | **Yes.** The demo can trigger a "took my pill twice" message. Unverified whether the durable-turn worker path differs for this rule; static read shows `chat_turn_service.floor_guidance` only builds display guidance |
| Per-turn audit when no rule fires, when the model's urgency is raised by `apply_safety_override`, or when a model escalation notifies clinicians | **No.** `chat_runtime._apply_floor_rules` (`adk/chat_runtime.py:466-480`) returns a raised urgency with no persisted trace. Model-classified escalation uses `ChatService.notify_assigned_clinicians` (`services/chat_service.py:545-577`), a best-effort insert into `clinician_messages` with no rule name or version, no delivery state, no retry; the floor path is atomic and retried. `chat_messages` keeps intent but not the rule version | A single immutable `chat_turn_safety_evaluations` (turn id, patient id, rule or `none`, rule_version, floor urgency, final urgency, escalation delivered, evaluated_at, no message text) written by the turn pipeline. Needs retention and "no PHI" decision | M (migration, pipeline hook in `chat_turn_pipeline.py`, tests); L if every path (voice, intake, document chat) is retrofitted | Rajeev (backend); Ganesh safety review | Optional. A thin version limited to turns where a rule fired or urgency was raised (S to M) covers the demo claim |
| Audit from the ADK plugin | Log line only. `SafetyFloorPlugin` logs a warning with rule and urgency (`safety_floor.py:96-100`), returns copy; no persistence and no tie to a turn id | Either persist from the plugin or document that the durable record is created by the router; today a plugin halt on a path that does not go through `routers/chat.py` is not durably recorded (unverified which production paths bypass it; `adk/chat_runtime.py` and the worker pipeline are the candidates) | S to M | Rajeev | Same as above |
| Synthetic rule tests | Yes. `tests/unit/safety/test_triage_floor.py` (26 tests, 20 parametrized, EN/ES, negation, precedence, educational questions), `tests/unit/adk/test_safety_floor_plugin.py` (14), `tests/unit/safety/test_intake_gate.py` (3), `tests/unit/services/test_ai_evaluation.py` floor cases. Safety suite runs in CI (`ci.yml:250`) | No fixture corpus with expected outcome per message and per locale; cases are inline. No test that every rule the floor can emit is accepted by the persistence RPC (this would have caught the gap above) | S | Ganesh | Yes (cheap, supports the "rule tests" claim) |
| Synthetic wording tests | Partly. `tests/unit/safety/test_safety_copy.py` (14): presence in en-US, es-MX and default, Spanish differs from English, 911 and 988 present, same-day wording | Tests prove presence and structure, not language quality. `loc-001` says Spanish clinical safety copy is not a separately approved bilingual artifact beyond what existing review covered; no recorded bilingual approval of `triage_copy.py` was found. Do not describe this as clinically validated wording | S to M (recorded bilingual wording review through the LOC-001 flow) | Rajeev + bilingual reviewer | Optional; keep the "no validation claim" line |
| Peer safety review recorded | NORA-002 review recorded in its spec; AI-004 closed prompt-review slice. Row requires peer review for SAFE-002 itself | No review record for any SAFE-002 change after the above fixes | S per change | Ganesh | Per change |

### Claims the code contradicts (SAFE-002)

- "Durable per-turn rule/outcome audit" implies every turn. Code persists only emergency floor
  halts (two of three floor rules), not clearances, raised urgencies or model-driven escalations.
- Anywhere the docs say all floor rules reach the patient safely: the patient does receive the
  same-day copy for a medication error, but the durable save and clinician alert fail silently
  on the WebSocket path (static finding, not reproduced).

---

## Suggested order for the expo (feature freeze December 4)

1. SAFE-002: persist `urgent_medication_error` correctly plus a test that every floor rule is
   accepted by the RPC (S, needs a migration the requester must authorize).
2. SAFE-001: run `verify_authorization_denials.py` on staging and record the result; relabel
   the four skipped cases honestly in the catalog (S).
3. COM-001: only if the demo story includes it, a no-show actionable item for the assigned
   clinician (M). A delivery-health card (M) is lower priority.
4. Everything else is post-expo or documentation-only.

## Method and limits

Static read of `backend/src/app` (services, routers, `safety/`, `adk/`, `db/migrations`), the
canonical fixture, `scripts/verify_authorization_denials.py`, both portals' `src` trees by grep,
and the listed tests by name and count. No test, script, migration or service was run, and no
environment was contacted. Portal UI was searched by keyword only, not read in full.
