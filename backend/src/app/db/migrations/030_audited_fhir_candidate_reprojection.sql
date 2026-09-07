-- Re-project pending FHIR candidates only when a newer mapper can expose fields
-- already present in the immutable raw source. This never changes local truth.

CREATE TABLE IF NOT EXISTS clinical_fact_mapping_revisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fact_id uuid NOT NULL REFERENCES clinical_facts(id) ON DELETE RESTRICT,
  actor_id uuid NOT NULL REFERENCES clinicians(id) ON DELETE RESTRICT,
  mapper_version text NOT NULL CHECK (char_length(mapper_version) BETWEEN 1 AND 100),
  source_version text,
  prior_value jsonb NOT NULL,
  projected_value jsonb NOT NULL,
  idempotency_key uuid NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_clinical_fact_mapping_revisions_fact
  ON clinical_fact_mapping_revisions(fact_id, created_at ASC);

-- A reprojected candidate has an additional immutable mapping-revision record.
-- Treat that record as retained evidence when a SMART source is withdrawn, so
-- the withdrawal flow never attempts to erase the audit trail.
CREATE OR REPLACE FUNCTION public.withdraw_unapplied_fhir_import(
  p_import_id uuid,
  p_patient_id uuid,
  p_actor_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
  v_provenance_ids uuid[];
  v_fact_ids uuid[];
  v_retained_ids uuid[];
  v_orphan_fact_ids uuid[];
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM public.fhir_imports
    WHERE id = p_import_id AND patient_id = p_patient_id
  ) THEN
    RAISE EXCEPTION 'FHIR import not found for patient';
  END IF;

  SELECT array_agg(p.id) INTO v_provenance_ids
  FROM public.source_provenances p
  JOIN public.fhir_import_resources r
    ON p.source_reference = 'fhir_import_resources/' || r.id::text
  WHERE r.import_id = p_import_id;
  IF coalesce(array_length(v_provenance_ids, 1), 0) = 0 THEN
    DELETE FROM public.fhir_imports WHERE id = p_import_id AND patient_id = p_patient_id;
    RETURN jsonb_build_object('can_delete', true, 'candidate_count', 0);
  END IF;

  PERFORM 1
  FROM public.clinical_facts f
  WHERE f.patient_id = p_patient_id
    AND EXISTS (
      SELECT 1 FROM public.evidence_citations e
      WHERE e.fact_id = f.id AND e.provenance_id = ANY(v_provenance_ids)
    )
  FOR UPDATE;

  SELECT array_agg(DISTINCT e.fact_id) INTO v_fact_ids
  FROM public.evidence_citations e
  JOIN public.clinical_facts f ON f.id = e.fact_id
  WHERE e.provenance_id = ANY(v_provenance_ids)
    AND f.patient_id = p_patient_id;

  -- A mapping revision is audit history, even though it never changed local
  -- truth. Retain its raw source and mark it withdrawn rather than deleting it.
  SELECT array_agg(f.id) INTO v_retained_ids
  FROM public.clinical_facts f
  WHERE f.id = ANY(coalesce(v_fact_ids, ARRAY[]::uuid[]))
    AND (
      f.reconciliation_state IN (
        'applied', 'source_withdrawn', 'kept_existing', 'deferred',
        'rejected', 'reviewed_evidence', 'legacy_applied'
      )
      OR EXISTS (
        SELECT 1
        FROM public.clinical_fact_mapping_revisions revision
        WHERE revision.fact_id = f.id
      )
    );
  IF coalesce(array_length(v_retained_ids, 1), 0) > 0 THEN
    UPDATE public.source_provenances
    SET withdrawn_at = now(),
        withdrawal_reason = 'SMART import removal requested after reconciliation or mapping revision'
    WHERE id = ANY(v_provenance_ids);
    UPDATE public.clinical_facts
    SET reconciliation_state = 'source_withdrawn',
        source_withdrawn_at = now()
    WHERE id = ANY(coalesce(v_fact_ids, ARRAY[]::uuid[]));
    INSERT INTO public.clinical_fact_audit_events(fact_id, actor_id, event_type, event_data)
    SELECT id, p_actor_id, 'source_withdrawn',
      jsonb_build_object('fhir_import_id', p_import_id)
    FROM public.clinical_facts
    WHERE id = ANY(v_retained_ids);
    RETURN jsonb_build_object(
      'can_delete', false,
      'source_withdrawn_fact_ids', coalesce(to_jsonb(v_fact_ids), '[]'::jsonb)
    );
  END IF;

  DELETE FROM public.evidence_citations
  WHERE provenance_id = ANY(v_provenance_ids);
  SELECT array_agg(f.id) INTO v_orphan_fact_ids
  FROM public.clinical_facts f
  WHERE f.id = ANY(coalesce(v_fact_ids, ARRAY[]::uuid[]))
    AND NOT EXISTS (
      SELECT 1 FROM public.evidence_citations e WHERE e.fact_id = f.id
    );
  DELETE FROM public.clinical_fact_audit_events
  WHERE fact_id = ANY(coalesce(v_orphan_fact_ids, ARRAY[]::uuid[]));
  DELETE FROM public.clinical_facts
  WHERE id = ANY(coalesce(v_orphan_fact_ids, ARRAY[]::uuid[]));
  DELETE FROM public.source_provenances
  WHERE id = ANY(v_provenance_ids);
  DELETE FROM public.fhir_imports WHERE id = p_import_id AND patient_id = p_patient_id;

  RETURN jsonb_build_object(
    'can_delete', true,
    'candidate_count', coalesce(array_length(v_fact_ids, 1), 0),
    'removed_candidate_count', coalesce(array_length(v_orphan_fact_ids, 1), 0)
  );
END;
$$;

CREATE OR REPLACE FUNCTION public.reject_clinical_fact_mapping_revision_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
  RAISE EXCEPTION 'clinical_fact_mapping_revisions are append-only';
END;
$$;

DROP TRIGGER IF EXISTS clinical_fact_mapping_revisions_append_only
  ON clinical_fact_mapping_revisions;
CREATE TRIGGER clinical_fact_mapping_revisions_append_only
  BEFORE UPDATE OR DELETE ON clinical_fact_mapping_revisions
  FOR EACH ROW EXECUTE FUNCTION public.reject_clinical_fact_mapping_revision_mutation();

-- This function is intentionally service-role-only. The repair script computes a
-- proposal from stored source JSON, while this transaction locks and re-checks
-- every eligibility condition before replacing the pending display projection.
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
      AND resource.version_id IS NOT DISTINCT FROM p_source_version
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

ALTER TABLE clinical_fact_audit_events
  DROP CONSTRAINT IF EXISTS clinical_fact_audit_events_event_type_check;
ALTER TABLE clinical_fact_audit_events
  ADD CONSTRAINT clinical_fact_audit_events_event_type_check
  CHECK (event_type IN (
    'created', 'corrected', 'approved', 'rejected', 'deleted', 'reconciled',
    'source_withdrawn', 'reprojected'
  ));

ALTER TABLE clinical_fact_mapping_revisions ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.clinical_fact_mapping_revisions
  FROM anon, authenticated;
GRANT SELECT, INSERT ON TABLE public.clinical_fact_mapping_revisions TO service_role;

REVOKE ALL ON FUNCTION public.apply_pending_fhir_candidate_reprojection(uuid, uuid, text, text, jsonb, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.apply_pending_fhir_candidate_reprojection(uuid, uuid, text, text, jsonb, uuid)
  TO service_role;
