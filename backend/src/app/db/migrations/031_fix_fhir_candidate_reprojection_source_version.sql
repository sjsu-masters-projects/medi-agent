-- Keep legacy resources without meta.versionId eligible for audited re-projection.
-- Import-time candidate versioning uses versionId when present and content_hash otherwise.

CREATE OR REPLACE FUNCTION public.apply_pending_fhir_candidate_reprojection(
  p_fact_id uuid,
  p_actor_id uuid,
  p_mapper_version text,
  p_source_version text,
  p_projected_value jsonb,
  p_idempotency_key uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
  v_fact public.clinical_facts%ROWTYPE;
  v_revision public.clinical_fact_mapping_revisions%ROWTYPE;
BEGIN
  SELECT * INTO v_revision
  FROM public.clinical_fact_mapping_revisions
  WHERE idempotency_key = p_idempotency_key;
  IF FOUND THEN
    IF v_revision.fact_id <> p_fact_id
       OR v_revision.actor_id <> p_actor_id
       OR v_revision.mapper_version <> p_mapper_version THEN
      RAISE EXCEPTION 'idempotency key belongs to another mapping revision';
    END IF;
    RETURN jsonb_build_object(
      'fact_id', v_revision.fact_id,
      'revision_id', v_revision.id,
      'replayed', true
    );
  END IF;

  IF p_projected_value IS NULL OR jsonb_typeof(p_projected_value) <> 'object' THEN
    RAISE EXCEPTION 'projected candidate value must be a JSON object';
  END IF;

  SELECT * INTO v_fact
  FROM public.clinical_facts
  WHERE id = p_fact_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'clinical fact not found';
  END IF;
  IF v_fact.review_state <> 'pending_review'
     OR coalesce(v_fact.reconciliation_state, 'not_started') <> 'not_started' THEN
    RAISE EXCEPTION 'only untouched pending candidates can be reprojected';
  END IF;
  IF v_fact.external_source_version IS DISTINCT FROM p_source_version THEN
    RAISE EXCEPTION 'candidate source version changed since the dry run';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.clinical_fact_audit_events
    WHERE fact_id = p_fact_id
      AND event_type <> 'created'
  ) THEN
    RAISE EXCEPTION 'clinician-touched candidates cannot be reprojected';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM public.care_teams
    WHERE patient_id = v_fact.patient_id
      AND clinician_id = p_actor_id
      AND status = 'active'
  ) THEN
    RAISE EXCEPTION 'clinician is not assigned to this patient';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM public.evidence_citations citation
    JOIN public.source_provenances provenance ON provenance.id = citation.provenance_id
    JOIN public.fhir_import_resources resource
      ON provenance.source_reference = 'fhir_import_resources/' || resource.id::text
    WHERE citation.fact_id = p_fact_id
      AND coalesce(resource.version_id, resource.content_hash) IS NOT DISTINCT FROM p_source_version
  ) THEN
    RAISE EXCEPTION 'candidate does not have the expected stored FHIR source';
  END IF;
  IF v_fact.value = p_projected_value THEN
    RETURN jsonb_build_object('fact_id', p_fact_id, 'unchanged', true);
  END IF;

  INSERT INTO public.clinical_fact_mapping_revisions(
    fact_id, actor_id, mapper_version, source_version, prior_value,
    projected_value, idempotency_key
  ) VALUES (
    p_fact_id, p_actor_id, p_mapper_version, p_source_version, v_fact.value,
    p_projected_value, p_idempotency_key
  ) RETURNING * INTO v_revision;

  UPDATE public.clinical_facts
  SET value = p_projected_value
  WHERE id = p_fact_id;

  INSERT INTO public.clinical_fact_audit_events(fact_id, actor_id, event_type, event_data)
  VALUES (
    p_fact_id, p_actor_id, 'reprojected',
    jsonb_build_object(
      'revision_id', v_revision.id,
      'mapper_version', p_mapper_version,
      'source_version', p_source_version,
      'prior_value', v_fact.value,
      'projected_value', p_projected_value
    )
  );

  RETURN jsonb_build_object(
    'fact_id', p_fact_id,
    'revision_id', v_revision.id,
    'replayed', false
  );
END;
$$;

REVOKE ALL ON FUNCTION public.apply_pending_fhir_candidate_reprojection(uuid, uuid, text, text, jsonb, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.apply_pending_fhir_candidate_reprojection(uuid, uuid, text, text, jsonb, uuid)
  TO service_role;
