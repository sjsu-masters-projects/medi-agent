# Safety floor and clinical action controls

The code that decides patient safety and clinical authority without a model: the
deterministic emergency floor in chat, intake and voice, the alerts and audit it writes, and
the approval gate for clinical actions. Patients see fixed reviewed direction; clinicians
see operational alerts and approve every clinical action.

## What it does

- **Patient.** Every chat message, symptom-intake answer and spoken utterance is checked
  before any model, retrieval or tool. Self-harm or emergency wording gets fixed localized
  direction (911 or 988); a possible medication dose or hold error gets same-day guidance;
  other messages continue to bounded general guidance.
- **Clinician.** The active care team gets one in-app operational alert per safety turn,
  with a short message excerpt: an "urgent chat escalation" for emergencies and a "not an
  emergency alert" notice for a medication error. A turn only the model escalates gets a
  plainer in-app message.
- **Clinical actions.** A recommendation, approval by an assigned clinician other than the
  proposer, then an envelope recording execution. Care-plan publication is the only live
  executor, through its own SQL functions.

## Rules it must keep

1. Emergency rules are code in `app/safety`, not prompts. On a match the model is not
   consulted to confirm or phrase the answer. Precedence is self-harm, emergency symptom,
   then medication error. Matching handles negation and educational questions in en-US and
   es-MX.
2. Escalation only moves up. A model or override may raise urgency, never lower it; the
   floor wins on emergencies; an adverse-effect signal raises routine to urgent.
3. Safety wording comes only from the reviewed `TRIAGE_COPY` in both locales and is never
   replaced or downgraded by a generic notice, "try later" or model rewrite. A rule with no
   copy falls back to the emergency copy and logs an error.
4. Every rule the floor can emit is listed in `FLOOR_RULE_URGENCY` and accepted by the
   persistence RPC and database constraint; guard tests enumerate it, so a new rule cannot
   ship unsaved.
5. Direction is sent first and never waits for storage, retrieval or a model. The turn's
   messages and a pending alert are saved by one atomic RPC; a storage failure keeps the
   direction and reports the save as uncertain. Worker retry sends pending alerts, so
   `A2A_RETRY_WORKER_ENABLED` must stay on.
6. Alert state is honest: `delivered` means an in-app message was persisted, not read;
   `no_recipients` is never sent later to a newly assigned clinician; recipients are active
   care-team members, deduplicated. Source messages and terminal safety records are
   immutable.
7. A safety turn never creates a symptom report or ADR task, and an emergency alert depends
   on no confirmation. Urgent (medication error) and emergency stay distinct end to end,
   including clinician wording.
8. Audit rows hold rule id, rule version, model and final urgency, outcome and turn id,
   never message text, prompts or reasoning. They are written when the floor halts a turn
   (chat, document chat, intake start and interrupt, voice) and when an override raised
   urgency or the model escalated. Writes are idempotent per turn, best effort with one
   retry, and never delay or alter the patient's answer. Rows are immutable except that
   rows older than 365 days are purged, at most 500 per call, by one service-only function.
   `test_floor_audit_paths.py` fails until each floor or override call site has one.
9. Tool access is deny by default, by per-agent allowlist, checked before the tool runs.
    Denials log agent and tool name, never arguments. The coordinator's tools are read-only.
10. Each model workload has a kill switch and a deterministic fallback. Model output is a
    reviewable candidate and cannot approve a medication change, diagnosis, ADR
    classification or external clinical action. No chain-of-thought is stored or shown.
11. Action tiers only tighten. An unclassified action type gets the strictest tier,
    `clinician_originated`, which a model proposer (no actor) can never put before a
    reviewer. The applied tier is written to the proposal audit event.
12. Proposing, deciding and executing need an active care-team assignment and a persisted
    clinician profile. A clinician cannot approve their own recommendation. A unique index
    allows one final decision per recommendation. An envelope needs an approved
    recommendation.
13. Envelope creation is a conflict-ignore insert on (recommendation, idempotency key). A
    retry reads the saved winner, never overwrites its outcome, and adds no second
    execution-request audit. Browser roles can only read these tables, scoped to assigned
    clinicians.
14. Every authorization denial is recorded with a reason code by the central 403 handler
    (best effort, bounded to 5 seconds); the response does not reveal the reason.
15. The product never diagnoses, prescribes, autonomously changes medication or submits a
    regulatory report; MedWatch is draft only. No safety test or wording check is clinical
    validation, and there is no allergy or interaction checker yet.

## Why it was built this way

- A deterministic floor ahead of the model, because an under-called emergency is the worst
  failure and prompts cannot guarantee a halt. The plugin halts by returning
  `types.Content`; returning an event does not stop the run.
- Alerts and audit are separate from any report, and the audit stores no text, so it is
  not a second copy of patient messages.
- Action tiers default strict so an unclassified action cannot loosen the gate.
  Conflict-ignore insert replaced check-then-insert, which lost races.

## Excluded on purpose

- Staging runs of `verify_authorization_denials.py` as a completion gate. It stays an
  optional diagnostic; automated denial tests and authorization controls stay.
- Action-tier enforcement on live actions, new executors and proxy actor sessions.
- Any claim of clinical validation of rules or wording.

## Where it lives

- Backend (`backend/src/app/`): `safety/` (`triage_floor.py`, `escalation.py`,
  `intake_gate.py`, `triage_copy.py`), `adk/plugins/safety_floor.py`, `tool_policy.py`,
  `adk/chat_runtime.py`, `routers/chat.py`, `routers/voice.py`,
  `services/chat_safety_service.py`, `a2a_retry_worker.py`,
  `authorization_audit_service.py`, `clinical_action_service.py`,
  `core/exception_handlers.py`, `core/action_tiers.py`.
- Migrations: `019_clinical_action_approvals`, `033` (denial events),
  `059_chat_safety_alerts`, `097_medication_error_safety_persistence`,
  `098_safety_audit_retention`.
- Tests (`backend/tests/`): `unit/safety/`, `unit/adk/test_safety_floor_plugin.py`,
  `unit/core/test_action_tiers.py`, `unit/services/test_clinical_action_service.py`,
  `integration/routers/test_chat_emergency_copy.py`,
  `integration/test_chat_safety_postgres.py`, `integration/test_clinical_action_postgres.py`.

## How to check it

[QA handoff section 3.9](../qa-handoff-2026-10.md): in both locales send a double-dose
statement, a severe-symptom phrase, a low-mood message, a mild stable symptom and a wellness
question: the first two give urgent wording and a care-team alert, low mood gives crisis
wording, the rest general guidance with no report.

```sh
cd backend
PYTHONPATH=src .venv/bin/pytest tests/unit/safety tests/unit/core/test_action_tiers.py \
  tests/unit/services/test_clinical_action_service.py \
  tests/integration/routers/test_chat_emergency_copy.py --no-cov -q
```

PostgreSQL modules need a disposable local database; see each module's header.

## Still open

- No live caller uses `ClinicalActionService`, so tiers guard no live action; care-plan
  publication records its recommendation as executed with no tier. See the
  [gap audit](../evidence/com-safe-gap-audit-2026-10.md).
- Four fixture denial cases (document list, medication timeline, document metadata, proxy
  actor) have no route to exercise, and the diagnostic script is not in CI.
- `record_outcome` accepts any assigned clinician; envelope creation and its audit row are
  separate writes.
- A turn only the model escalates gets a best-effort message with no rule id, delivery
  state or retry. A turn with no rule and no raised urgency leaves no record.
- The floor's `escalation_recommended` event says `emergency` even for a medication error.
