-- Persist deterministic Naranjo decision support and its patient-grounded evidence.
-- The score is advisory: clinicians and pharmacists retain final review authority.

ALTER TABLE public.adr_assessments
  DROP CONSTRAINT IF EXISTS adr_assessments_naranjo_score_check;

ALTER TABLE public.adr_assessments
  ADD CONSTRAINT adr_assessments_naranjo_score_check
    CHECK (naranjo_score BETWEEN -4 AND 13),
  ADD COLUMN IF NOT EXISTS naranjo_answers jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS naranjo_assessment jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS evidence jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE public.adr_assessments
  ADD CONSTRAINT adr_assessments_naranjo_answers_object
    CHECK (jsonb_typeof(naranjo_answers) = 'object'),
  ADD CONSTRAINT adr_assessments_naranjo_assessment_object
    CHECK (jsonb_typeof(naranjo_assessment) = 'object'),
  ADD CONSTRAINT adr_assessments_evidence_array
    CHECK (jsonb_typeof(evidence) = 'array');

CREATE UNIQUE INDEX IF NOT EXISTS adr_assessments_one_per_symptom
  ON public.adr_assessments(symptom_report_id);

GRANT INSERT, UPDATE ON TABLE public.adr_assessments TO service_role;

COMMENT ON COLUMN public.adr_assessments.naranjo_assessment IS
  'Deterministic Naranjo score snapshot; decision support, not a clinical conclusion.';
COMMENT ON COLUMN public.adr_assessments.evidence IS
  'Patient-grounded excerpts supporting explicitly answered Naranjo questions.';
