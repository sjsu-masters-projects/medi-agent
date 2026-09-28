"""Prompts for clinician-visible, evidence-constrained care-plan drafts."""

CARE_PLAN_DRAFT_SYSTEM = """You classify already-grounded clinical source facts into a
clinician-visible care-plan draft. You are not writing clinical advice.

Return every supplied source_fact_id exactly once. You may choose only one supplied
category per fact. Medication facts must use category medication. Obligation facts may
use movement, nutrition, hydration, monitoring, follow_up, or other when that category
is explicitly supported by the fact wording.

Do not create, omit, combine, edit, normalize, translate, or infer any clinical
instruction, dose, frequency, route, duration, hydration target, appointment detail, or
source_fact_id. The application copies patient-visible wording directly from the source
fact after your response is validated.

Output only valid JSON matching this shape:
{"items":[{"source_fact_id":"UUID from input","category":"allowed category"}]}"""

CARE_PLAN_DRAFT_USER = """Classify every grounded source fact below. Their values are
evidence-backed candidates, not approved clinical truth:

{facts_json}"""
