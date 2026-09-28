-- Queue the one-time PAT-005 handoff for facts extracted before migration 040
-- introduced the care-plan request lifecycle. These requests remain subject to the
-- same five-minute quiet window, generation safeguards, clinician review, and
-- whole-plan approval as newly ingested documents.

WITH eligible_patients AS (
  SELECT
    facts.patient_id,
    MAX(GREATEST(facts.updated_at, documents.created_at)) AS source_watermark
  FROM public.clinical_facts AS facts
  JOIN public.evidence_citations AS citations ON citations.fact_id = facts.id
  JOIN public.source_provenances AS provenance ON provenance.id = citations.provenance_id
  JOIN public.documents AS documents ON documents.id = provenance.document_id
  WHERE facts.fact_type IN ('medication', 'obligation')
    AND facts.review_state IN ('pending_review', 'approved')
    AND provenance.artifact_type = 'document'
    AND documents.parse_status = 'completed'
  GROUP BY facts.patient_id
)
INSERT INTO public.care_plan_generation_requests (patient_id, source_watermark)
SELECT eligible.patient_id, eligible.source_watermark
FROM eligible_patients AS eligible
WHERE NOT EXISTS (
  SELECT 1
  FROM public.care_plan_versions AS plans
  WHERE plans.patient_id = eligible.patient_id
)
  AND NOT EXISTS (
    SELECT 1
    FROM public.care_plan_generation_requests AS requests
    WHERE requests.patient_id = eligible.patient_id
      AND requests.status IN ('pending', 'processing', 'retry')
  )
ON CONFLICT DO NOTHING;
