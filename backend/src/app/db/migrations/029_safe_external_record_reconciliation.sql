-- R2 reconciliation foundation. Imported records remain clinical-fact candidates
-- until an assigned clinician explicitly applies a permitted field-level change.

ALTER TYPE allergy_severity_enum ADD VALUE IF NOT EXISTS 'unknown';

ALTER TABLE clinical_facts
  ADD COLUMN IF NOT EXISTS reconciliation_state text NOT NULL DEFAULT 'not_started'
    CHECK (reconciliation_state IN (
      'not_started', 'applied', 'kept_existing', 'deferred', 'rejected',
      'reviewed_evidence', 'source_withdrawn', 'legacy_applied'
    )),
  ADD COLUMN IF NOT EXISTS reconciliation_target_type text,
  ADD COLUMN IF NOT EXISTS reconciliation_target_id uuid,
  ADD COLUMN IF NOT EXISTS external_source_key text,
  ADD COLUMN IF NOT EXISTS external_source_version text,
  ADD COLUMN IF NOT EXISTS source_withdrawn_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_clinical_facts_patient_reconciliation
  ON clinical_facts(patient_id, reconciliation_state, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_clinical_facts_external_source
  ON clinical_facts(patient_id, external_source_key, external_source_version)
  WHERE external_source_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS external_patient_bindings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  issuer text NOT NULL,
  external_patient_id text NOT NULL,
  patient_id uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  confirmed_by uuid NOT NULL REFERENCES clinicians(id) ON DELETE RESTRICT,
  confirmation_note text,
  external_identity jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (issuer, external_patient_id),
  UNIQUE (issuer, patient_id)
);

CREATE TRIGGER external_patient_bindings_updated_at
  BEFORE UPDATE ON external_patient_bindings
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE INDEX IF NOT EXISTS idx_external_patient_bindings_patient
  ON external_patient_bindings(patient_id, issuer);

ALTER TABLE fhir_imports
  ADD COLUMN IF NOT EXISTS external_identity jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS external_patient_binding_id uuid
    REFERENCES external_patient_bindings(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS identity_confirmed_at timestamptz,
  ADD COLUMN IF NOT EXISTS identity_confirmation_note text;

CREATE INDEX IF NOT EXISTS idx_fhir_imports_patient_binding
  ON fhir_imports(patient_id, external_patient_binding_id);

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS content_hash text
    CHECK (content_hash IS NULL OR content_hash ~ '^[A-Fa-f0-9]{64}$');

ALTER TABLE source_provenances
  ADD COLUMN IF NOT EXISTS withdrawn_at timestamptz,
  ADD COLUMN IF NOT EXISTS withdrawal_reason text;

CREATE INDEX IF NOT EXISTS idx_documents_patient_content_hash
  ON documents(patient_id, content_hash)
  WHERE content_hash IS NOT NULL;

CREATE TABLE IF NOT EXISTS document_ingestion_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  patient_id uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  source_hash text,
  status text NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'duplicate')),
  attempt integer NOT NULL DEFAULT 1 CHECK (attempt > 0),
  extractor_version text,
  error_message text,
  candidate_fact_count integer NOT NULL DEFAULT 0 CHECK (candidate_fact_count >= 0),
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_document_ingestion_runs_document
  ON document_ingestion_runs(document_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_document_ingestion_runs_patient_status
  ON document_ingestion_runs(patient_id, status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_document_ingestion_runs_hash_patient
  ON document_ingestion_runs(patient_id, source_hash)
  WHERE source_hash IS NOT NULL AND status = 'completed';

CREATE TABLE IF NOT EXISTS clinical_fact_reconciliation_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fact_id uuid NOT NULL REFERENCES clinical_facts(id) ON DELETE RESTRICT,
  patient_id uuid NOT NULL REFERENCES patients(id) ON DELETE RESTRICT,
  actor_id uuid NOT NULL REFERENCES clinicians(id) ON DELETE RESTRICT,
  decision text NOT NULL CHECK (decision IN (
    'add', 'update', 'keep_existing', 'defer', 'reject', 'mark_reviewed'
  )),
  target_type text,
  target_id uuid,
  selected_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
  candidate_snapshot jsonb NOT NULL,
  target_before jsonb,
  target_after jsonb,
  source_version text,
  note text,
  idempotency_key uuid NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_clinical_fact_reconciliation_events_fact
  ON clinical_fact_reconciliation_events(fact_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_clinical_fact_reconciliation_events_target
  ON clinical_fact_reconciliation_events(patient_id, target_type, target_id)
  WHERE target_id IS NOT NULL;

CREATE OR REPLACE FUNCTION public.reject_clinical_fact_reconciliation_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
  RAISE EXCEPTION 'clinical_fact_reconciliation_events are append-only';
END;
$$;

DROP TRIGGER IF EXISTS clinical_fact_reconciliation_events_append_only
  ON clinical_fact_reconciliation_events;
CREATE TRIGGER clinical_fact_reconciliation_events_append_only
  BEFORE UPDATE OR DELETE ON clinical_fact_reconciliation_events
  FOR EACH ROW EXECUTE FUNCTION public.reject_clinical_fact_reconciliation_event_mutation();

-- The backend calls this function with service_role only after its own request
-- authorization. The function repeats the active care-team check and performs
-- the target mutation, decision audit, and fact lifecycle change in one transaction.
CREATE OR REPLACE FUNCTION public.apply_clinical_fact_reconciliation(
  p_fact_id uuid,
  p_actor_id uuid,
  p_decision text,
  p_target_id uuid,
  p_patch jsonb,
  p_selected_fields jsonb,
  p_note text,
  p_idempotency_key uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
  v_fact public.clinical_facts%ROWTYPE;
  v_event public.clinical_fact_reconciliation_events%ROWTYPE;
  v_before jsonb;
  v_after jsonb;
  v_target_id uuid;
  v_target_type text;
  v_state text;
  v_now timestamptz := now();
BEGIN
  SELECT * INTO v_event
  FROM public.clinical_fact_reconciliation_events
  WHERE idempotency_key = p_idempotency_key;
  IF FOUND THEN
    IF v_event.fact_id <> p_fact_id OR v_event.actor_id <> p_actor_id THEN
      RAISE EXCEPTION 'idempotency key belongs to another reconciliation decision';
    END IF;
    RETURN jsonb_build_object(
      'fact_id', v_event.fact_id,
      'event_id', v_event.id,
      'decision', v_event.decision,
      'target_id', v_event.target_id,
      'replayed', true
    );
  END IF;

  SELECT * INTO v_fact
  FROM public.clinical_facts
  WHERE id = p_fact_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'clinical fact not found';
  END IF;
  IF v_fact.review_state <> 'pending_review' THEN
    RAISE EXCEPTION 'only pending clinical facts can be reconciled';
  END IF;
  IF coalesce(v_fact.reconciliation_state, 'not_started') NOT IN ('not_started', 'deferred') THEN
    RAISE EXCEPTION 'reconciled clinical facts are immutable evidence';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.care_teams
    WHERE patient_id = v_fact.patient_id
      AND clinician_id = p_actor_id
      AND status = 'active'
  ) THEN
    RAISE EXCEPTION 'clinician is not assigned to this patient';
  END IF;
  IF p_decision NOT IN ('add', 'update', 'keep_existing', 'defer', 'reject', 'mark_reviewed') THEN
    RAISE EXCEPTION 'unsupported reconciliation decision';
  END IF;
  IF p_decision IN ('reject', 'defer') AND coalesce(btrim(p_note), '') = '' THEN
    RAISE EXCEPTION 'a note is required for reject and defer decisions';
  END IF;

  v_target_type := NULL;
  v_target_id := NULL;
  v_before := NULL;
  v_after := NULL;

  IF p_decision IN ('add', 'update') THEN
    IF v_fact.fact_type NOT IN ('medication', 'condition', 'allergy') THEN
      RAISE EXCEPTION 'this evidence type cannot modify local clinical records';
    END IF;
    IF p_patch IS NULL OR jsonb_typeof(p_patch) <> 'object' THEN
      RAISE EXCEPTION 'reconciliation patch is required';
    END IF;
    IF jsonb_typeof(coalesce(p_selected_fields, '[]'::jsonb)) <> 'array'
       OR EXISTS (
         SELECT 1
         FROM jsonb_object_keys(p_patch) AS field_name
         WHERE NOT (coalesce(p_selected_fields, '[]'::jsonb) ? field_name)
       ) THEN
      RAISE EXCEPTION 'patch fields must be explicitly selected';
    END IF;
    IF p_decision = 'add' AND p_target_id IS NOT NULL THEN
      RAISE EXCEPTION 'add must not specify an existing target';
    END IF;
    IF p_decision = 'update' AND p_target_id IS NULL THEN
      RAISE EXCEPTION 'update requires a target';
    END IF;

    IF v_fact.fact_type = 'medication' THEN
      v_target_type := 'medication';
      IF p_decision = 'update' THEN
        SELECT to_jsonb(m.*) INTO v_before
        FROM public.medications m
        WHERE m.id = p_target_id AND m.patient_id = v_fact.patient_id
        FOR UPDATE;
        IF v_before IS NULL THEN RAISE EXCEPTION 'medication target not found'; END IF;
        UPDATE public.medications m SET
          name = CASE WHEN p_patch ? 'name' THEN coalesce(nullif(btrim(p_patch->>'name'), ''), m.name) ELSE m.name END,
          generic_name = CASE WHEN p_patch ? 'generic_name' THEN coalesce(nullif(btrim(p_patch->>'generic_name'), ''), m.generic_name) ELSE m.generic_name END,
          rxcui = CASE WHEN p_patch ? 'rxcui' THEN coalesce(nullif(btrim(p_patch->>'rxcui'), ''), m.rxcui) ELSE m.rxcui END,
          dosage = CASE WHEN p_patch ? 'dosage' THEN coalesce(nullif(btrim(p_patch->>'dosage'), ''), m.dosage) ELSE m.dosage END,
          frequency = CASE WHEN p_patch ? 'frequency' THEN coalesce(nullif(btrim(p_patch->>'frequency'), ''), m.frequency) ELSE m.frequency END,
          route = CASE WHEN p_patch ? 'route' AND nullif(btrim(p_patch->>'route'), '') IS NOT NULL THEN (p_patch->>'route')::public.medication_route_enum ELSE m.route END,
          start_date = CASE WHEN p_patch ? 'start_date' AND nullif(p_patch->>'start_date', '') IS NOT NULL THEN (p_patch->>'start_date')::date ELSE m.start_date END,
          end_date = CASE WHEN p_patch ? 'end_date' AND nullif(p_patch->>'end_date', '') IS NOT NULL THEN (p_patch->>'end_date')::date ELSE m.end_date END,
          instructions = CASE WHEN p_patch ? 'instructions' THEN coalesce(nullif(btrim(p_patch->>'instructions'), ''), m.instructions) ELSE m.instructions END,
          is_active = CASE WHEN p_patch ? 'is_active' THEN (p_patch->>'is_active')::boolean ELSE m.is_active END
        WHERE m.id = p_target_id AND m.patient_id = v_fact.patient_id
        RETURNING to_jsonb(m.*) INTO v_after;
      ELSE
        IF coalesce(nullif(btrim(p_patch->>'name'), ''), '') = ''
           OR coalesce(nullif(btrim(p_patch->>'dosage'), ''), '') = ''
           OR coalesce(nullif(btrim(p_patch->>'frequency'), ''), '') = '' THEN
          RAISE EXCEPTION 'new medications require name, dosage, and frequency';
        END IF;
        INSERT INTO public.medications AS m(
          patient_id, name, generic_name, rxcui, dosage, frequency, route,
          start_date, end_date, instructions, is_active
        ) VALUES (
          v_fact.patient_id, p_patch->>'name', nullif(btrim(p_patch->>'generic_name'), ''),
          nullif(btrim(p_patch->>'rxcui'), ''), p_patch->>'dosage', p_patch->>'frequency',
          coalesce((p_patch->>'route')::public.medication_route_enum, 'oral'::public.medication_route_enum),
          nullif(p_patch->>'start_date', '')::date, nullif(p_patch->>'end_date', '')::date,
          nullif(btrim(p_patch->>'instructions'), ''), coalesce((p_patch->>'is_active')::boolean, true)
        ) RETURNING id, to_jsonb(m) INTO v_target_id, v_after;
      END IF;
    ELSIF v_fact.fact_type = 'condition' THEN
      v_target_type := 'condition';
      IF p_decision = 'update' THEN
        SELECT to_jsonb(c.*) INTO v_before FROM public.conditions c
        WHERE c.id = p_target_id AND c.patient_id = v_fact.patient_id FOR UPDATE;
        IF v_before IS NULL THEN RAISE EXCEPTION 'condition target not found'; END IF;
        UPDATE public.conditions c SET
          name = CASE WHEN p_patch ? 'name' THEN coalesce(nullif(btrim(p_patch->>'name'), ''), c.name) ELSE c.name END,
          icd10_code = CASE WHEN p_patch ? 'icd10_code' THEN coalesce(nullif(btrim(p_patch->>'icd10_code'), ''), c.icd10_code) ELSE c.icd10_code END,
          status = CASE WHEN p_patch ? 'status' THEN coalesce(nullif(btrim(p_patch->>'status'), ''), c.status) ELSE c.status END,
          notes = CASE WHEN p_patch ? 'notes' THEN coalesce(nullif(btrim(p_patch->>'notes'), ''), c.notes) ELSE c.notes END
        WHERE c.id = p_target_id AND c.patient_id = v_fact.patient_id
        RETURNING to_jsonb(c.*) INTO v_after;
      ELSE
        IF coalesce(nullif(btrim(p_patch->>'name'), ''), '') = '' THEN
          RAISE EXCEPTION 'new conditions require a name';
        END IF;
        INSERT INTO public.conditions AS c(patient_id, name, icd10_code, status, notes)
        VALUES (v_fact.patient_id, p_patch->>'name', nullif(btrim(p_patch->>'icd10_code'), ''),
          coalesce(nullif(btrim(p_patch->>'status'), ''), 'active'), nullif(btrim(p_patch->>'notes'), ''))
        RETURNING id, to_jsonb(c) INTO v_target_id, v_after;
      END IF;
    ELSE
      v_target_type := 'allergy';
      IF p_decision = 'update' THEN
        SELECT to_jsonb(a.*) INTO v_before FROM public.allergies a
        WHERE a.id = p_target_id AND a.patient_id = v_fact.patient_id FOR UPDATE;
        IF v_before IS NULL THEN RAISE EXCEPTION 'allergy target not found'; END IF;
        UPDATE public.allergies a SET
          allergen = CASE WHEN p_patch ? 'allergen' THEN coalesce(nullif(btrim(p_patch->>'allergen'), ''), a.allergen) ELSE a.allergen END,
          reaction = CASE WHEN p_patch ? 'reaction' THEN coalesce(nullif(btrim(p_patch->>'reaction'), ''), a.reaction) ELSE a.reaction END,
          severity = CASE WHEN p_patch ? 'severity' AND nullif(btrim(p_patch->>'severity'), '') IS NOT NULL THEN (p_patch->>'severity')::public.allergy_severity_enum ELSE a.severity END
        WHERE a.id = p_target_id AND a.patient_id = v_fact.patient_id
        RETURNING to_jsonb(a.*) INTO v_after;
      ELSE
        IF coalesce(nullif(btrim(p_patch->>'allergen'), ''), '') = '' THEN
          RAISE EXCEPTION 'new allergies require an allergen';
        END IF;
        INSERT INTO public.allergies AS a(patient_id, allergen, reaction, severity)
        VALUES (v_fact.patient_id, p_patch->>'allergen', nullif(btrim(p_patch->>'reaction'), ''),
          coalesce((p_patch->>'severity')::public.allergy_severity_enum, 'unknown'::public.allergy_severity_enum))
        RETURNING id, to_jsonb(a) INTO v_target_id, v_after;
      END IF;
    END IF;
  END IF;

  v_state := CASE p_decision
    WHEN 'add' THEN 'applied'
    WHEN 'update' THEN 'applied'
    WHEN 'keep_existing' THEN 'kept_existing'
    WHEN 'defer' THEN 'deferred'
    WHEN 'reject' THEN 'rejected'
    ELSE 'reviewed_evidence'
  END;

  UPDATE public.clinical_facts SET
    review_state = CASE WHEN p_decision IN ('add', 'update', 'keep_existing', 'mark_reviewed') THEN 'approved'
                        WHEN p_decision = 'reject' THEN 'rejected'
                        ELSE review_state END,
    reviewed_by = CASE WHEN p_decision IN ('add', 'update', 'keep_existing', 'mark_reviewed', 'reject') THEN p_actor_id ELSE reviewed_by END,
    reviewed_at = CASE WHEN p_decision IN ('add', 'update', 'keep_existing', 'mark_reviewed', 'reject') THEN v_now ELSE reviewed_at END,
    review_note = CASE WHEN p_note IS NULL OR btrim(p_note) = '' THEN review_note ELSE btrim(p_note) END,
    reconciliation_state = v_state,
    reconciliation_target_type = v_target_type,
    reconciliation_target_id = coalesce(v_target_id, p_target_id)
  WHERE id = p_fact_id;

  INSERT INTO public.clinical_fact_reconciliation_events(
    fact_id, patient_id, actor_id, decision, target_type, target_id, selected_fields,
    candidate_snapshot, target_before, target_after, source_version, note, idempotency_key
  ) VALUES (
    p_fact_id, v_fact.patient_id, p_actor_id, p_decision, v_target_type,
    coalesce(v_target_id, p_target_id), coalesce(p_selected_fields, '[]'::jsonb),
    v_fact.value, v_before, v_after, v_fact.external_source_version,
    nullif(btrim(p_note), ''), p_idempotency_key
  ) RETURNING id INTO v_event.id;

  INSERT INTO public.clinical_fact_audit_events(fact_id, actor_id, event_type, event_data)
  VALUES (
    p_fact_id, p_actor_id, 'reconciled',
    jsonb_build_object('decision', p_decision, 'target_type', v_target_type,
      'target_id', coalesce(v_target_id, p_target_id), 'event_id', v_event.id)
  );

  RETURN jsonb_build_object(
    'fact_id', p_fact_id, 'event_id', v_event.id, 'decision', p_decision,
    'target_type', v_target_type, 'target_id', coalesce(v_target_id, p_target_id),
    'target_before', v_before, 'target_after', v_after, 'replayed', false
  );
END;
$$;

-- A source may be removed only before it has changed local clinical truth.
-- This function owns the delete ordering so service_role never receives broad
-- DELETE privileges on clinical facts or their append-only reconciliation audit.
CREATE OR REPLACE FUNCTION public.withdraw_unapplied_document_source(
  p_document_id uuid,
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
  SELECT array_agg(id) INTO v_provenance_ids
  FROM public.source_provenances
  WHERE document_id = p_document_id;
  IF coalesce(array_length(v_provenance_ids, 1), 0) = 0 THEN
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

  -- A prior clinician decision is append-only evidence. Keep the source rather
  -- than deleting its audit trail, even when the decision did not apply a patch.
  SELECT array_agg(id) INTO v_retained_ids
  FROM public.clinical_facts
  WHERE id = ANY(coalesce(v_fact_ids, ARRAY[]::uuid[]))
    AND reconciliation_state IN (
      'applied', 'source_withdrawn', 'kept_existing', 'deferred',
      'rejected', 'reviewed_evidence', 'legacy_applied'
    );
  IF coalesce(array_length(v_retained_ids, 1), 0) > 0 THEN
    UPDATE public.source_provenances
    SET withdrawn_at = now(),
        withdrawal_reason = 'source document removal requested after reconciliation'
    WHERE id = ANY(v_provenance_ids);
    UPDATE public.clinical_facts
    SET reconciliation_state = 'source_withdrawn',
        source_withdrawn_at = now()
    WHERE id = ANY(coalesce(v_fact_ids, ARRAY[]::uuid[]));
    INSERT INTO public.clinical_fact_audit_events(fact_id, actor_id, event_type, event_data)
    SELECT id, p_actor_id, 'source_withdrawn',
      jsonb_build_object('document_id', p_document_id)
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

  RETURN jsonb_build_object(
    'can_delete', true,
    'candidate_count', coalesce(array_length(v_fact_ids, 1), 0),
    'removed_candidate_count', coalesce(array_length(v_orphan_fact_ids, 1), 0)
  );
END;
$$;

-- SMART imports follow the same rule: an unapplied import can be withdrawn;
-- an import that affected local truth stays as immutable evidence and is
-- surfaced for clinician review instead of being erased.
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

  -- Keep source and immutable audit history for every prior clinician decision.
  SELECT array_agg(id) INTO v_retained_ids
  FROM public.clinical_facts
  WHERE id = ANY(coalesce(v_fact_ids, ARRAY[]::uuid[]))
    AND reconciliation_state IN (
      'applied', 'source_withdrawn', 'kept_existing', 'deferred',
      'rejected', 'reviewed_evidence', 'legacy_applied'
    );
  IF coalesce(array_length(v_retained_ids, 1), 0) > 0 THEN
    UPDATE public.source_provenances
    SET withdrawn_at = now(),
        withdrawal_reason = 'SMART import removal requested after reconciliation'
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

ALTER TABLE clinical_fact_audit_events
  DROP CONSTRAINT IF EXISTS clinical_fact_audit_events_event_type_check;
ALTER TABLE clinical_fact_audit_events
  ADD CONSTRAINT clinical_fact_audit_events_event_type_check
  CHECK (event_type IN (
    'created', 'corrected', 'approved', 'rejected', 'deleted', 'reconciled',
    'source_withdrawn'
  ));

ALTER TABLE external_patient_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_ingestion_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE clinical_fact_reconciliation_events ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.external_patient_bindings,
  public.document_ingestion_runs, public.clinical_fact_reconciliation_events
  FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.external_patient_bindings,
  public.document_ingestion_runs, public.clinical_fact_reconciliation_events
  TO service_role;

REVOKE ALL ON FUNCTION public.apply_clinical_fact_reconciliation(uuid, uuid, text, uuid, jsonb, jsonb, text, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.apply_clinical_fact_reconciliation(uuid, uuid, text, uuid, jsonb, jsonb, text, uuid)
  TO service_role;

REVOKE ALL ON FUNCTION public.withdraw_unapplied_document_source(uuid, uuid, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.withdraw_unapplied_document_source(uuid, uuid, uuid)
  TO service_role;

REVOKE ALL ON FUNCTION public.withdraw_unapplied_fhir_import(uuid, uuid, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.withdraw_unapplied_fhir_import(uuid, uuid, uuid)
  TO service_role;
