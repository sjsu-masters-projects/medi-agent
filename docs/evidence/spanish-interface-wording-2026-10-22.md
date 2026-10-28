# English / Mexican Spanish interface wording review

## Verdict and boundary

Accepted after corrections for synthetic-project interface use on October 22,
2026. The requester explicitly accepted a model-assisted meaning-and-safety review
and did not require a separate fluent professional reviewer. This is the review
method, not a claim of native-speaker, professional translation or clinical
validation. No external translation service or patient data was used.

All 553 paired inventory entries were compared, including dynamic branches.
There are 460 distinct source locations; declaration/accessor aliases account for
the repeated rows. The [paired review pack](../spanish-draft-review-pack.md) and
[machine-checkable receipt](spanish-interface-wording-2026-10-22.json) identify
the exact accepted sources and pair fingerprints. This verdict is not a claim
about every Spanish string elsewhere in the application.

Nine English-only clinician title/description tuples were incorrectly treated as
English/Spanish pairs in the initial 562-row inventory. They are now excluded,
not translated: clinician controls intentionally remain English. Extraction is
limited to the explicitly bilingual tables and covered by a regression test.

## Review criteria

Compared meaning and actor identity rather than literal word order. Checked
uncertainty and negation; past events versus instructions; patient testimony
versus clinician decisions; approval and privacy boundaries; saved versus sent
versus reviewed state; dates, counts, names and placeholders; emergency wording;
retry/deduplication guidance; voice controls and text fallback.

Both alternatives were reviewed for nullable names/dates, singular/plural counts,
privacy settings and timer formatting. Clinical original text, historical human
messages and stored care-plan wording were not rewritten or approved here.

## Results by source

Paths below are relative to the repository root. Each result covers only the
paired entries included in the inventory, not unrelated runtime behavior.

| Source | Entries | Result |
| --- | --- | --- |
| `apps/patient-portal/src/content/chat-copy.ts` | 105 | Accepted after clarifying unavailable-message scope, no automatic reprocessing and the hands-free off action. Existing emergency/contact guidance and text fallbacks retained. |
| `apps/patient-portal/src/content/care-team-copy.ts` | 41 | Accepted unchanged: private conditions, shared medicines/allergies, ownership, upload routing, reminder continuity and nullable owner/version branches preserve meaning. |
| `apps/patient-portal/src/content/symptom-history-copy.ts` | 62 | Accepted after removing an unsupported implication that the care team itself marked a report urgent. Reviewed status remains separate. |
| `apps/patient-portal/src/content/visits-copy.ts` | 75 | Accepted after preserving clinician identity in offer/empty-state labels. Cancellation reasons, timezone fallback, saved-response/refresh errors and date placeholders retained. |
| `apps/patient-portal/src/app/(app)/profile/profile-copy.ts` | 118 | Accepted after making language switching explicitly a display change. No plan, reminder or completion change is implied. Saved/uncertain errors and non-continuous-monitoring notice retained. |
| `apps/patient-portal/src/components/features/nora-conversations.tsx` | 8 | Accepted unchanged: incomplete and in-progress replies remain distinct from saved history. |
| `packages/shared/src/utils/care-conversations.ts` | 58 | Accepted unchanged: recipient identity, uncertain sends, duplicate warning, read-only originals, automatic-translation caveat and clinical-approval boundary retained. |
| `backend/src/app/services/notification_centre_presentation.py` | 47 | Accepted after restoring omitted task/history, actor, exact-source and original-conversation context. Patient testimony and candidate findings remain explicitly not clinical decisions or confirmed ADRs. |
| `backend/src/app/services/symptom_report_presenter.py` | 25 | Accepted unchanged: labels, unknown/declined answers, yes/no, dose and concentration remain distinct. Original patient answers are not translated. |
| `backend/src/app/services/appointment_calendar.py` | 3 | Accepted after explicitly describing the calendar export as a one-time copy; no automatic update or cancellation sync is implied. |
| `backend/src/app/services/email_service.py` | 11 | Accepted unchanged: subjects describe generic saved events, not diagnoses, delivery guarantees or direct clinician email. |

## Corrections recorded

| Source/key | Problem addressed | Accepted Spanish meaning |
| --- | --- | --- |
| Chat `replyUnavailable`, `noRetry` | Conversation-wide scope and technical “execute” wording | The reply to this message is unavailable; the message is not processed again automatically. |
| Chat `handsFreeOn` | Omitted off action | Hands-free is on; tap to turn it off. |
| Symptom history `events.flagged_urgent` | Added a care-team actor not established by the source | Marked so the care team can review urgently; no assertion that a clinician already did so. |
| Visits `offerTitle`, `emptyDetail` | Broadened the responsible clinician to an unspecified team | The clinician offers the visit, without changing the named recipient or available actions. |
| Profile `languageHelp` | “The plan changes” could imply a clinical change | Approved plan/activity text is displayed in the selected language. |
| Notification `legacy_update` | Omitted “not a new task” | Historical inbox entry, not new work. |
| Notification `appointment_response`, `document_review`, `barrier_reported` | Lost patient attribution or exact source direction | Preserve the patient/source and the action to review it. |
| Notification `adr_review`, `adr_information_answered` | Generic “security” omitted medicine-safety context | Medication-safety review/follow-up, not confirmed diagnosis or causality. |
| Notification `critical_result` | Lost patient/laboratory context | The patient's source document contains a result the laboratory marked critical. |
| Notification `care_plan_review` | Literal “open the patient” and unclear task | Open the patient's record for the care-plan item requiring attention. |
| Notification `safety_flag` | Omitted original conversation direction | Review the original conversation; the automated flag is not a clinical decision. |
| Calendar `_COPY.1` | Omitted explicit one-time nature | One-time calendar copy; changes and cancellations do not synchronize. |

## Addendum: completion batch 2 (October 22)

Completion batch 2 (PAT-002-C review notifications, CON-001 handoff sharing) added four
paired notification strings. They received the same model-assisted meaning-and-safety
review, on the requester's authority (no human bilingual reviewer is required for this
synthetic project). All other differences at this snapshot are moved line numbers.

| Source/key | Review | Accepted Spanish |
| --- | --- | --- |
| Notification `symptom_report_reviewed.0` | Accurate; uses the app's "equipo de atención" and "reporte de síntomas" | Tu equipo de atención revisó tu reporte de síntomas |
| Notification `symptom_report_reviewed.1` | Accurate, tú register, no clinical claim | Consulta tu reporte de síntomas. |
| Notification `handoff_shared.0` | **Corrected.** "Resumen de traspaso" reads as an administrative transfer; Mexican clinical usage for a care handoff is "entrega" | Un colega compartió un resumen de entrega |
| Notification `handoff_shared.1` | Accurate; keeps both boundaries (read-only, no record access); "expediente" is the Mexican term for the clinical record | Abre el resumen aprobado. Es de solo lectura; compartirlo no da acceso al expediente. |

The receipt below was regenerated after this review, not to silence the gate.

## Addendum: code closure (October 22)

Three patient copy files were marked draft but were not in the inventory, so their pairs
were never reviewed: `symptom-intake-copy.ts` (the #221 conversational offer and private
intake), `medication-confirmation-copy.ts` (MED-002) and `reply-sources-copy.ts` (Nora's
Sources line). The extractor also missed files whose Spanish table is named `esMX`, or
that declare a local `es` inside a function, which shadowed the file-level table; it now
reads only file-level declarations (output for the previously covered files is byte-identical).

All 91 new pairs (62 intake, 21 MED-002, 6 Sources, 2 new notification) received the same
model-assisted meaning-and-safety review on the requester's authority. Inventory: 553 at
the first pass, 557 after the batch-2 addendum, 648 now.

| Source/key | Review | Accepted Spanish |
| --- | --- | --- |
| Intake `saved` | **Corrected.** "Informe" → "Reporte", matching "reporte de síntomas" used elsewhere | Reporte guardado para revisión del equipo clínico |
| Intake `pendingAnswer` | **Corrected.** Awkward passive | Tu respuesta — aún no confirmamos que se guardó |
| Intake `unavailable`, `reload`, and the two in-function stale/terminal errors | **Corrected.** "Carga…" made consistent with `error` ("Vuelve a cargar…") | Vuelve a cargar el estado guardado… / Volver a cargar el estado guardado |
| Intake `confirm`, `consent`, `summary` | Kept "equipo clínico": the term is used across the patient portal (messages, sign-in, care conversations) and was accepted with "equipo de atención" in the first pass | unchanged |
| Intake offer (`offerPrompt`, `offerYes`, `offerNo`, `privateTag`) | Accurate; tú register; consent stays explicit | unchanged |
| MED-002 question card and errors | Accurate; "No, lo dejé" / "Cambió" / "No lo sé"; "venció" is the Mexican usage for expiry; the privacy line keeps "does not change your medicines or reminders" | unchanged |
| Sources (`summary`, `record`, `page`) | Accurate; "expediente" for the record | unchanged |
| Notification `medication_confirmation_asked` | Accurate; names no medicine | unchanged |

## Proposed addendum: PV-001-D Naranjo answer coverage (October 28)

**Status: awaiting requester acceptance. Not accepted; the receipt is unchanged.** PV-001-D
(branch `feature/adr-naranjo-answer-coverage`) adds two retrospective ADR follow-up questions.
The two notification strings below are in the receipt-gated inventory (650 rows at this
snapshot), so `--require-reviewed` fails until they are accepted and a new receipt is recorded.
The six follow-up strings live in `adr-follow-up-copy.ts`, outside the inventory, under the
PV-001-C wording decision; they need the same acceptance. The review notes below are proposed
for that decision.

| Source/key | Proposed review | Proposed Spanish |
| --- | --- | --- |
| Notification `_QUESTION_WORDING.event_after_drug.0` | Accurate; "comenzaste" keeps the tú register; names no medicine | Si el síntoma empezó después de que comenzaste este medicamento |
| Notification `_QUESTION_WORDING.improved_on_dechallenge.0` | Accurate; impersonal "se suspendió o pausó" does not imply the patient stopped it alone | Si el síntoma mejoró después de que se suspendió o pausó este medicamento |
| Follow-up `event_after_drug.label` | Accurate | Cuándo empezó el síntoma |
| Follow-up `event_after_drug.prompt` | Accurate; "por primera vez" keeps "first start" | ¿Este síntoma empezó por primera vez después de que comenzaste a tomar este medicamento? |
| Follow-up `event_after_drug.evidencePrompt` | Accurate | Describe cuándo empezaste el medicamento y cuándo empezó el síntoma. |
| Follow-up `improved_on_dechallenge.label` | Accurate; follows the accepted "Qué pasó al reiniciarlo antes" pattern | Qué pasó al suspenderlo o pausarlo antes |
| Follow-up `improved_on_dechallenge.prompt` | Accurate; keeps "Antes de esta solicitud" and the explicit do-not-stop caution, as the accepted rechallenge and dose prompts do | Antes de esta solicitud, ¿el síntoma mejoró después de que se suspendió o pausó este medicamento? No lo suspendas ni lo omitas para responder. |
| Follow-up `improved_on_dechallenge.evidencePrompt` | Accurate | Describe cuándo se suspendió o pausó y qué pasó. |

## Durable acceptance

The receipt stores every source SHA-256, the full paired-entry fingerprint and row
count. CI runs:

```sh
python3 backend/scripts/build_spanish_review_pack.py --check --require-reviewed
```

Missing/malformed receipts, altered source, added/edited pairs and stale generated
Markdown fail the gate. Regenerating the Markdown alone cannot renew acceptance.
After a future edit, review the affected pairs and record a new receipt through
normal review. Do not copy a new hash merely to silence CI.

## Verification and remaining work

Focused source/regression checks are recorded in the
[review specification](../../.agent/specs/loc-001-interface-review.md).
The full patient suite passes 989 tests in 91 files; focused backend checks pass
280 tests. Lint, both portal type-checks, backend mypy, receipt freshness and
documentation checks pass. These verify code/copy contracts, not live rendering.
No database migration, remote configuration, clinical approval flag, medication,
schedule, reminder, patient history or stored message was changed.

This closes the language meaning-and-safety review for the exact paired interface
snapshot. It does not establish deployed rendering, narrow-screen wrapping,
physical voice/device behavior, bilingual generated clinical content, an expo
rehearsal or clinical safety qualification. Those remain their own tasks.
