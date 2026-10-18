# Demo care-loop follow-ups — LOC-002, EVA-001, AI-006, COM-002

Status: In review in [#191](https://github.com/sjsu-masters-projects/medi-agent/pull/191).
One PR; separate behavior and test lanes. This increment
includes the pending task-board/documentation reconciliation after #188.

## Acceptance plan

1. **LOC-002:** carry en-US/es-MX from guest entry through onboarding and saved
   Profile preference; render the document language consistently on first load;
   localize Today/notification errors from stable codes, not backend prose. Reuse
   shared locale labels. Language changes must not alter clinical wording approval,
   schedules, timezone or completion. Existing onboarding preference persistence
   must be retained, not duplicated. Clinician LOC-003 work remains separate.
2. **AI-006:** allow bounded general wellness education instead of blanket refusal;
   distinguish mild/stable symptoms and low mood from urgent deterioration while
   retaining deterministic emergency/crisis floors, overdose/unsafe-dose and
   suspected medication-reaction escalation. Remove only the unused legacy
   ingestion graph/test after verifying callers. Route SOAP through the registry;
   failure produces no invented/stored note. Operational budgets are explicitly
   configured limits, never claimed measured clinical performance.
3. **EVA-001:** reuse the existing synthetic evaluation framework with a bounded,
   paired-locale demo suite for grounding, explanation, symptom classification,
   unavailable responses and safety/approval boundaries. Keep raw final responses
   and structured outcomes, never reasoning. Deterministic tests and dry runs are
   not a live model evaluation or clinical validation; report them separately.
4. **COM-002:** a patient explicitly attaches an existing approved care-plan activity
   to a private addressed conversation. The server checks ownership and current
   source state. The clinician sees source context and may open it in a draft via
   an explicit action; authorization is rechecked. Preserve original-message
   identity, draft provenance and idempotency. Stale/replaced/foreign sources fail
   clearly. Opening a thread, sending a message or replying never changes the
   approved plan, projections, reminders or completion history. Reuse existing
   clinician review, bilingual verification and publication gates.

## Verification

- Focused backend/API/service tests for authorization, stale/foreign context,
  retries and approval boundaries; PostgreSQL permission/concurrency tests for any
  new database contract, including re-runs and backend-only grants.
- Both portals: focused tests, lint, typecheck and production builds. Patient
  narrow layouts, long Spanish, loading/failure/retry states and keyboard controls.
- Evaluation fixtures validate offline; raw-response scoring and paired-locale
  coverage are tested. Record real-provider runs only if actually performed.
- Update TASKS with commands/outcomes and remaining live checks. Remote migration,
  deployment, merge and clinical publication need separate authorization.

Professional adjudication and a 120-case study are not expo completion gates.
No new cross-clinic sharing or implicit broadcast recipient behavior is introduced.

## COM-002 implementation and rollout contract

- Composer action **Ask about a plan activity** expands an optional picker from
  the existing approved-plan endpoint; recipient selection remains explicit.
  Attaching/changing an activity does not send. An uncertain retry locks body,
  source identity and client message UUID together. Confirmed sends clear them.
- Migration `074_care_conversation_activity_review.sql` extends existing message
  and plan-item tables. It stores an item reference, not a second clinical summary.
  The saved message presents the source's approved wording; a superseded source
  is labelled historical. Database authorization still owns thread isolation.
- `care_conversation_activity_operation` wraps the existing atomic send operation
  and adds an explicit clinician-only review action. Replays compare attachment
  identity; a stale source rejects a new send but does not erase a prior saved send.
  Invalid source validation rolls back the message, notification and audit together.
- Review creates a full draft from the approved version or reuses the existing
  draft. Carried items keep provenance; projected medication items target the
  existing medication rather than proposing a duplicate. Verification defaults
  remain unapproved. Removed/ambiguous draft matches are rejected, not appended.
  The review audit records the message, conversation, source item and draft item.
  Repeat clicks do not duplicate the draft, items or actor's review audit.
- The clinician opens the exact draft item by a local patient-route anchor, with
  keyboard focus. Saving, bilingual attestation and publication remain separate
  existing actions. The source plan stays approved until an authorized publication.
- This uses today's patient-level approved-plan model. Per-team plan ownership is
  PLAN-002, not implicitly implemented by attaching an item to a private thread.
- Apply 074 only with separate authorization, before deploying this backend.
  Rerunning it is tested; existing conversation reads/legacy deployments remain
  compatible. No remote migration, publication or live acceptance is claimed.

## Pending es-MX interface drafts

New nonclinical activity-message copy remains **draft, awaiting bilingual review**:
`Preguntar sobre una actividad del plan`, `Actividad sobre la que preguntas (opcional)`,
`Cargando actividades…`, `Sin actividad adjunta`, `Actividad adjunta anteriormente`,
`No se pudieron cargar las actividades.`, `Reintentar actividades`,
`Actividad del plan adjunta`, `Esta actividad ya no pertenece al plan actual.`, and
`Tu mensaje no cambia el plan ni los recordatorios. Tu equipo debe revisar y aprobar cualquier cambio.`
Stale attachment recovery: `La actividad adjunta ya no está disponible. Conservamos tu texto. Quita la actividad o vuelve a cargar las actividades antes de enviar.`
Clinical titles/frequencies displayed beside these strings are existing approved
wording, not new UI translations. Reviewed emergency/crisis copy is unchanged.

## Local verification and remaining acceptance

All checks use synthetic fixtures and isolated data, not live patient accounts.

| Check | Result |
| --- | --- |
| Backend `PYTHONPATH=src .venv/bin/pytest tests --ignore=tests/integration/test_appointment_offer_transactions.py --no-cov -q --tb=short --disable-warnings` | 3,622 passed / 344 opt-in skips after merging current main; excluded native database fixture run separately |
| Native appointment transaction suite, same pytest flags | 31 passed outside sandbox; its disposable PostgreSQL startup was denied in the initial sandbox run |
| Conversation PostgreSQL suite with `CARE_CONVERSATION_TEST_POSTGRES_DOCKER=1` | 43 passed after merging current main and renumbering the activity migration to 074, including publication lock order, rerun permissions, concurrent draft review and preservation of main's clinic guard functions |
| Final conversation service/API suites | 60 passed, including neutral errors for concurrent draft changes |
| AI/SOAP/evaluation/ingestion focused checks | 563 passed; exact commands in the [operator guide](../../docs/demo-ai-evaluation.md) |
| Patient `npm run test -- --silent` | 737 passed after merging current main (includes localized stale-attachment feedback and current chat recovery tests) |
| Clinician `npm run test -- --silent` | 576 passed, including one-time focus without stealing focus during edits |
| Both portals `npm run lint`, `npm run typecheck`, `SENTRY_AUTH_TOKEN='' npm run build -- --webpack` | Passed; existing font fetch required network access for clinician build |
| Changed Python Ruff / targeted mypy | Passed; nine source files in final targeted mypy pass |
| Migration validator / diff whitespace / documentation links | 87 migration files validated; checks passed |
| Demo evaluation `--suite demo --dry-run` | 34 selected; paired locale runs 17 / 17; no model called |

Browser check: the locally built Spanish login and signup render Spanish labels,
retain `lang=es-MX` navigation and `html lang=es-MX`; no horizontal overflow in the
observed browser viewport. This is not authenticated mobile workflow acceptance.
No current authenticated accounts were available in the browser for the two-portal
handoff. Mobile 360/390/430 and clinician desktop screenshots, keyboard/reduced-motion
journeys, approved-plan publication after handoff, actual provider responses and
human bilingual review remain unrecorded. PR/CI/merge and separately authorized
migration/deployment are still required; no task is marked Done from local checks.
