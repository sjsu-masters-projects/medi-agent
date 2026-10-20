# Demo care-loop follow-ups — LOC-002, EVA-001, AI-006, COM-002

Status: [#191](https://github.com/sjsu-masters-projects/medi-agent/pull/191) merged
after #192; migration `076_care_conversation_activity_review.sql` is recorded in
the hosted ledger. Deployed behavior still requires the acceptance checks below.

## Acceptance plan

DV-011 follow-up in PR #200: Today must not render a previous-locale feed while
current saved-locale wording loads. Only the latest request may replace the feed
or its error state. Regression coverage delays an older English response behind
a Spanish response and verifies task identity, scheduled time and completion are
retained. A failed locale change displays retry feedback without stale wording.
This implementation still requires a deployed language-switch recheck.

1. **LOC-002:** carry en-US/es-MX from guest entry through onboarding and saved
   Profile preference; render the document language consistently on first load;
   localize Today/notification errors from stable codes, not backend prose. Reuse
   shared locale labels. Language changes must not alter clinical wording approval,
   schedules, timezone or completion. Existing onboarding preference persistence
   must be retained, not duplicated. Clinician LOC-003 work remains separate.
2. **AI-006:** allow bounded general wellness education instead of blanket refusal;
   distinguish mild/stable symptoms and low mood from urgent deterioration while
   retaining deterministic emergency/crisis floors, bilingual medication-error
   and suspected medication-reaction escalation. The unused legacy ingestion
   graph/test is removed after verifying callers and migrating its golden coverage.
   Route SOAP through the registry; transient provider and truncation failures get
   one bounded retry, while any final failure produces no invented/stored note.
   Operational budgets are configured limits, never claimed measured clinical
   performance.
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

## Review follow-up decisions

- **Locale first paint (LOC-002):** the proxy always sets a locale hint: query on entry
  pages, then the cookie, then `Accept-Language` (`es*` maps to es-MX, anything else to
  en-US). The root layout therefore renders dynamically on purpose. While a locale or
  profile is unresolved the portal shows a locale-neutral skeleton, never an empty page.
  The profile preference seeds the cookie when it loads; a user sign-out, a cross-tab
  sign-out and an inactivity or absolute-limit sign-out clear the cookie and the guest
  preference so the next person on a shared device does not inherit it. The cookie is a
  presentation hint, never identity or authorization.
- **Medication-error safety floor (AI-006):** deterministic and bilingual, not model-only.
  Affirmed reports of a double, extra or repeat dose, taking too many or too much,
  overdose, a self-directed dose change, stopping on one's own, or taking a medicine after
  hold/stop advice answer "contact your care team or pharmacist today" (`urgent`,
  rule `urgent_medication_error`). Severe symptoms in the same message take the existing
  emergency rule first. Denials ("I didn't take it twice"), schedule wording ("twice a
  day") and definitions ("what is an overdose?") do not trip it. A question about
  changing a dose ("can I double my dose?") does, by design. Hopelessness phrases
  ("I can't go on", "no puedo más") reach the crisis floor only when they end the
  sentence, so "no puedo más café" does not. Low mood that persists or worsens is told to
  contact the care team in the responder prompt (model-guided; the keyword crisis floor is
  unchanged).
- **SOAP:** one retry on a rate-limit, unavailable or truncated generation; invalid
  content is never retried. A final failure writes no note.
- **Activity errors:** distinct stable codes `ACTIVITY_CONTEXT_UNAVAILABLE` (missing,
  foreign or unauthorized, deliberately neutral), `ACTIVITY_CONTEXT_STALE` (the source is
  superseded or removed; the clinician is told to open the current plan),
  `CARE_PLAN_DRAFT_EXISTS` and `INVALID_CONVERSATION_REQUEST`. Reviewing a question about
  an item in a superseded plan fails with the stale code by design.
- **Review path locking:** the clinician review checks the exact thread, its active
  care-team link, clinic and membership without locks before taking the per-patient
  evidence lock, so an outsider cannot queue behind a patient's evidence writers
  (covered by a Docker test that holds the lock).
- **Document import errors** use stable codes localized through the Today copy.

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
- Migration `076_care_conversation_activity_review.sql` extends existing message
  and plan-item tables. It stores an item reference, not a second clinical summary.
  The saved message presents the source's approved wording; a superseded source
  is labelled historical. Database authorization still owns thread isolation.
- `care_conversation_activity_operation` wraps the existing atomic send operation
  and adds an explicit clinician-only review action. Replays compare attachment
  identity; a stale source rejects a new send but does not erase a prior saved send.
  Invalid source validation rolls back the message, notification and audit together.
  Review authorization is checked before waiting on the patient evidence fence and
  is rechecked after it. Invalid message input, unavailable context, superseded
  context and an existing ambiguous draft have distinct stable failures.
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
- Migration 076 is recorded as applied in the hosted ledger. Rerunning it is
  tested; existing conversation reads/legacy deployments remain compatible.
  The October 19 live message-to-draft check did not publish a plan. Its
  exact-item focus defect and remaining acceptance are in the deployed recheck.

## Pending es-MX interface drafts

New nonclinical activity-message copy remains **draft, awaiting bilingual review**:
`Preguntar sobre una actividad del plan`, `Actividad sobre la que preguntas (opcional)`,
`Cargando actividades…`, `Sin actividad adjunta`, `Actividad adjunta anteriormente`,
`No se pudieron cargar las actividades.`, `Reintentar actividades`,
`Actividad del plan adjunta`, `Esta actividad ya no pertenece al plan actual.`, and
`Tu mensaje no cambia el plan ni los recordatorios. Tu equipo debe revisar y aprobar cualquier cambio.`
Also draft: `Actividad adjunta: {título}` and `La actividad no se puede cambiar mientras se confirma o reintenta este mensaje.`
Stale attachment recovery: `La actividad adjunta ya no está disponible. Conservamos tu texto. Quita la actividad o vuelve a cargar las actividades antes de enviar.`
Document-import errors remain draft: `Vuelve a iniciar sesión antes de importar un documento clínico.`,
`Tu sesión expiró. Vuelve a iniciar sesión antes de importar un documento clínico.` and
`No se pudo importar el documento. Revisa tu conexión e intenta de nuevo.`
Medication-error safety reply (`medication_error_response`, es-MX) is a new clinical-safety
draft pending LOC-001 and safety review: `Un posible error de dosis o al tomar un medicamento que debía pausarse o suspenderse requiere orientación hoy mismo. Contacta hoy a tu equipo de atención o a tu farmacéutico. Si tienes síntomas graves o repentinos, dificultad para respirar, dolor de pecho, desmayo o no te sientes a salvo, llama al 911 o acude al servicio de urgencias más cercano ahora.`
Today recovery copy also remains draft: `Actualiza tus actividades e intenta de nuevo.`,
`Vuelve a iniciar sesión. Tu respuesta no se ha guardado.`, and
`No pudimos confirmar que se guardó tu respuesta. Actualiza antes de volver a intentarlo; la actividad no se ha marcado como completada.`
Clinical titles/frequencies displayed beside these strings are existing approved
wording, not new UI translations. Reviewed emergency/crisis copy is unchanged.

## Local verification and remaining acceptance

All checks use synthetic fixtures and isolated data, not live patient accounts.

| Check | Result |
| --- | --- |
| Backend `PYTHONPATH=src .venv/bin/pytest tests --ignore=tests/integration/test_appointment_offer_transactions.py --no-cov -q --tb=short --disable-warnings` | 3,622 passed / 344 opt-in skips after merging current main; excluded native database fixture run separately |
| Native appointment transaction suite, same pytest flags | 31 passed outside sandbox; its disposable PostgreSQL startup was denied in the initial sandbox run |
| Conversation PostgreSQL suite with `CARE_CONVERSATION_TEST_POSTGRES_DOCKER=1` | 43 passed after merging current main and renumbering the activity migration to 076, including publication lock order, rerun permissions, concurrent draft review and preservation of main's clinic guard functions |
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
At the time of this local check, authenticated accounts were not available for
the two-portal handoff. Subsequently, #191 merged, migration 076 was recorded
applied, and the October 19 Rajeev/Elena deployed message-to-draft path was
exercised with an exact-item focus defect. The patient locale switch was also
exercised and restored, with a transient mixed-language render after navigation.
See the [deployed recheck](../../docs/deployed-recheck-2026-10-11.md#task-verdicts).
Mobile 360/390/430 and clinician desktop screenshots, keyboard/reduced-motion
journeys, approved-plan publication after handoff, actual provider responses and
human bilingual review remain unrecorded; no task is marked Done from these
partial checks.
