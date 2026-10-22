# candidate-1 — paired-locale review worksheet

**Status: requester reports Ganesh approved candidate-1 on October 12, 2026. The approval record is below; intake activation is tracked separately.**

- Version: `candidate-1`
- Canonical bundle SHA-256: `a7ee7f3c7bfd91fdbf3fccba56fb42af86176801895ca0d70ad3c99ffd0917ab`
- Source: [candidate-1.json](candidate-1.json)
- Review location: [draft PR #159](https://github.com/sjsu-masters-projects/medi-agent/pull/159). A formal PR review is not asserted by this record.
- Designated safety/backend reviewer: Ganesh, per the task tracker. Include a reviewer able to assess Mexican Spanish wording.

## Proposed questions

All questions require an explicit resolution; **I don’t know** and **Prefer not to answer** remain valid. A rating is never preselected or inferred. The budget is twelve; the concomitant-products question is applicable only when the patient explicitly reports a product concern.

| ID / answer | English (en-US) | Mexican Spanish (es-MX) | Applicability |
| --- | --- | --- | --- |
| `description` / text | Describe the symptom or event in your own words. | Describe el síntoma o evento con tus propias palabras. | General candidate |
| `location` / text | Where do you feel it? | ¿En qué parte del cuerpo lo sientes? | General candidate |
| `onset` / text | When did it start? Use your own words; an exact date is optional. | ¿Cuándo empezó? Usa tus propias palabras; una fecha exacta es opcional. | General candidate |
| `duration` / text | How long does it last, or is it ongoing? | ¿Cuánto dura o sigue presente? | General candidate |
| `course` / text | How has it changed since it started? | ¿Cómo ha cambiado desde que empezó? | General candidate |
| `severity` / rating | Choose your own severity rating from 1 to 10, or choose unknown or prefer not to answer. | Elige tu propia intensidad del 1 al 10, o elige no sé o prefiero no responder. | General candidate |
| `associated` / text | What other symptoms have you noticed? | ¿Qué otros síntomas has notado? | General candidate |
| `red_flags` / text | Describe any symptom that concerns you right now. | Describe cualquier síntoma que te preocupe en este momento. | General candidate |
| `product` / product | Are you concerned about a medicine or other product? If so, enter its name and the details you know. | ¿Te preocupa algún medicamento u otro producto? Si es así, escribe su nombre y los detalles que sabes. | General candidate |
| `concomitant` / text | What other medicines or products were you using at the time? | ¿Qué otros medicamentos o productos usabas en ese momento? | Explicit product concern |
| `history` / text | What relevant history or test results would you like to report? | ¿Qué antecedentes o resultados de pruebas relevantes quieres reportar? | General candidate |
| `outcome` / text | What happened afterward, or how are you feeling now? | ¿Qué pasó después o cómo te sientes ahora? | General candidate |

## Decisions the reviewer must make

- [ ] Review every question in both languages for clarity, equivalent meaning and suitability for the synthetic-demo collection scope.
- [ ] Review order, required resolution, applicability and the twelve-question ceiling.
- [ ] Verify unknown/declined answers, nullable severity and patient-supplied product details; record context must not supply or infer an answer.
- [ ] Decide whether the generic candidate covers the intended symptom scenarios. It currently has no symptom-specific branches.
- [ ] Review red-flag handling. Every `positive_safety_rule` is currently null; the general concern question is not a structured positive red-flag mapping. Record whether changes are required and their reviewed criteria.
- [ ] Check safety interruption, review/correction/cancel and explicit consent using synthetic test evidence. Tests are functional evidence, not clinical validation or reviewer approval.
- [ ] Record findings and an actual approval, rejection or changes-requested decision. Do not mark these boxes based only on automated checks.

## Record the actual decision

The reviewer can place the decision on PR #159, with these fields:

| Field | Required actual evidence |
| --- | --- |
| Reviewed version / hash | The version and canonical hash above, or the final revised version/hash |
| Reviewer identity / role | Actual name and role of the person who performed the review |
| Date | Actual review date |
| Decision | Approved, rejected or changes requested |
| Findings / scope | Both locales, applicability and explicit branch/red-flag decisions |
| Reference | Stable link to the actual decision/comment |

## Requester-reported approval

On October 12, 2026, while this worksheet and `candidate-1.json` were open, the
requester stated “Yes he reviewed it and approved it,” then clarified “Today just
now he reviewed and approved it.” This records their report that Ganesh Thampi,
the designated safety/backend reviewer, approved `candidate-1` on **October 12,
2026**. The reviewed resource is the unchanged canonical bundle hash shown above;
its package contains the paired English and Mexican Spanish wording, applicability,
and safety-rule fields displayed here. The requester did not provide itemized
findings or an independently observable reviewer signature. The unchecked review
prompts above remain prompts, not independently verified findings. This record is
the approval reference and provenance for the synthetic-demo library gate; it is
not a GitHub PR approval or professional clinical validation.

This synthetic-demo team review does not claim professional clinical validation.
Approved content is immutable; later changes require a new version and review.

## Activation after a real approval

1. Record the actual decision in `manifest.json`, with the approved version, canonical hash and reviewer/reference/date metadata. Select that approved version as `active_version`.
2. Through an explicitly authorized rollout, publish matching `set_symptom_question_eligibility` metadata to the same synthetic database. Never substitute test-fixture approval metadata.
3. Start the local backend with `SYMPTOM_INTAKE_ENABLED=true` only after file and database eligibility agree. Configuration files containing credentials must not be edited or copied into this review record.
4. Follow [the authenticated acceptance journey](../../../../../docs/evidence/pat-002-b-acceptance-2026-10-12.md#activation-and-authenticated-manual-journey): draft, recovery, unknown severity, review/correction, consent/confirm once, assigned clinician summary, cancellation and both locales.

Migration application alone does not approve this library or activate intake.
