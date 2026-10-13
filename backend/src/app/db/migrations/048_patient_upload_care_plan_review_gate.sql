-- Patient-scoped fencing covers evidence row changes and new citation phantoms.
-- Approved snapshots, canonical projections and response history are unchanged.
GRANT USAGE ON SCHEMA private TO service_role;

CREATE FUNCTION private.lock_care_plan_evidence(p_patient_id uuid, p_wait boolean)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  IF p_patient_id IS NULL THEN RETURN; END IF;
  IF p_wait THEN
    PERFORM pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended('care-plan-evidence:' || p_patient_id::text, 0));
  ELSIF NOT pg_catalog.pg_try_advisory_xact_lock(
    pg_catalog.hashtextextended('care-plan-evidence:' || p_patient_id::text, 0)) THEN
    -- Row-trigger callers may already own row locks: never wait in reverse order.
    RAISE EXCEPTION 'Care-plan evidence changed concurrently; retry the transaction'
      USING ERRCODE = '40001';
  END IF;
END;
$$;

CREATE FUNCTION private.care_plan_fact_is_eligible(p_patient_id uuid, p_fact_id uuid)
RETURNS boolean LANGUAGE sql VOLATILE SECURITY INVOKER SET search_path = '' AS $$
  SELECT EXISTS (SELECT 1 FROM public.clinical_facts f
    WHERE f.id = p_fact_id AND f.patient_id = p_patient_id
      AND f.review_state IN ('pending_review', 'approved'))
  AND EXISTS (SELECT 1 FROM public.evidence_citations c
    JOIN public.source_provenances p ON p.id = c.provenance_id
    LEFT JOIN public.documents d ON d.id = p.document_id
    WHERE c.fact_id = p_fact_id AND p.withdrawn_at IS NULL
      AND (p.artifact_type = 'clinician_entry' OR
        (p.artifact_type = 'document' AND d.patient_id = p_patient_id AND
          (d.uploaded_by_role = 'clinician' OR
            (d.uploaded_by_role = 'patient' AND d.review_status = 'approved')))))
  AND NOT EXISTS (SELECT 1 FROM public.evidence_citations c
    JOIN public.source_provenances p ON p.id = c.provenance_id
    LEFT JOIN public.documents d ON d.id = p.document_id
    WHERE c.fact_id = p_fact_id AND p.artifact_type = 'document'
      AND (p.withdrawn_at IS NOT NULL OR d.id IS NULL
        OR d.patient_id IS DISTINCT FROM p_patient_id
        OR d.uploaded_by_role IS NULL OR d.uploaded_by_role NOT IN ('patient', 'clinician')
        OR (d.uploaded_by_role = 'patient' AND d.review_status IS DISTINCT FROM 'approved')));
$$;

-- Fence both old and new patients before changing a lineage relationship.
CREATE FUNCTION private.fence_care_plan_evidence_mutation() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_old jsonb := CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) ELSE '{}'::jsonb END;
  v_new jsonb := CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) ELSE '{}'::jsonb END;
  v_patients uuid[];
  v_patient uuid;
  v_locked uuid[] := ARRAY[]::uuid[];
BEGIN
  LOOP
  IF TG_TABLE_NAME IN ('documents', 'clinical_facts', 'care_plan_versions') THEN
    v_patients := ARRAY[(v_old->>'patient_id')::uuid, (v_new->>'patient_id')::uuid];
  ELSIF TG_TABLE_NAME = 'evidence_citations' THEN
    SELECT array_agg(f.patient_id) INTO v_patients FROM public.clinical_facts f
      WHERE f.id IN ((v_old->>'fact_id')::uuid, (v_new->>'fact_id')::uuid);
  ELSIF TG_TABLE_NAME = 'care_plan_items' THEN
    SELECT array_agg(v.patient_id) INTO v_patients FROM public.care_plan_versions v
      WHERE v.id IN ((v_old->>'plan_version_id')::uuid, (v_new->>'plan_version_id')::uuid);
  ELSE
    SELECT array_agg(patient_id) INTO v_patients FROM (
      SELECT d.patient_id FROM public.documents d
        WHERE d.id IN ((v_old->>'document_id')::uuid, (v_new->>'document_id')::uuid)
      UNION
      SELECT f.patient_id FROM public.evidence_citations c
        JOIN public.clinical_facts f ON f.id = c.fact_id
        WHERE c.provenance_id IN ((v_old->>'id')::uuid, (v_new->>'id')::uuid)
    ) affected;
  END IF;
  -- INSERT/DELETE discovery includes an absent OLD/NEW patient. NULL is not
  -- contained by any uuid array, so normalize before testing loop termination.
  SELECT coalesce(array_agg(DISTINCT id ORDER BY id), ARRAY[]::uuid[])
    INTO v_patients FROM unnest(v_patients) id WHERE id IS NOT NULL;
  IF v_patients <@ v_locked THEN EXIT; END IF;
  FOR v_patient IN SELECT DISTINCT id FROM unnest(v_patients) id
    WHERE id IS NOT NULL ORDER BY id LOOP
    -- RPCs do not lock documents; single-document reviews can wait safely.
    -- Other mutations may have already locked facts in a reconciliation RPC.
    PERFORM private.lock_care_plan_evidence(v_patient,
      TG_TABLE_NAME = 'documents' AND (TG_OP = 'INSERT' OR
        (TG_OP = 'UPDATE' AND v_old->>'id' = v_new->>'id'
          AND v_old->>'patient_id' = v_new->>'patient_id')));
    v_locked := array_append(v_locked, v_patient);
  END LOOP;
  IF TG_TABLE_NAME = 'evidence_citations' THEN
    -- Stabilize endpoints, including a provenance gaining its first citation.
    -- FK KEY SHARE alone permits withdrawn_at/patient_id changes. NOWAIT avoids
    -- reversing an endpoint mutator's row -> patient-fence order.
    PERFORM f.id FROM public.clinical_facts f
      WHERE f.id IN ((v_old->>'fact_id')::uuid, (v_new->>'fact_id')::uuid)
      ORDER BY f.id FOR SHARE NOWAIT;
    PERFORM p.id FROM public.source_provenances p
      WHERE p.id IN ((v_old->>'provenance_id')::uuid, (v_new->>'provenance_id')::uuid)
      ORDER BY p.id FOR SHARE NOWAIT;
  END IF;
  -- Relationships can commit between discovery and acquiring the fence. Repeat
  -- discovery under the acquired locks before allowing the mutation to proceed.
  END LOOP;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
EXCEPTION WHEN lock_not_available THEN
  RAISE EXCEPTION 'Care-plan evidence changed concurrently; retry the transaction'
    USING ERRCODE = '40001';
END;
$$;
CREATE TRIGGER care_plan_evidence_fence BEFORE INSERT OR UPDATE OR DELETE ON public.documents
  FOR EACH ROW EXECUTE FUNCTION private.fence_care_plan_evidence_mutation();
CREATE TRIGGER care_plan_evidence_fence BEFORE INSERT OR UPDATE OR DELETE ON public.clinical_facts
  FOR EACH ROW EXECUTE FUNCTION private.fence_care_plan_evidence_mutation();
CREATE TRIGGER care_plan_evidence_fence BEFORE INSERT OR UPDATE OR DELETE ON public.source_provenances
  FOR EACH ROW EXECUTE FUNCTION private.fence_care_plan_evidence_mutation();
CREATE TRIGGER care_plan_evidence_fence BEFORE INSERT OR UPDATE OR DELETE ON public.evidence_citations
  FOR EACH ROW EXECUTE FUNCTION private.fence_care_plan_evidence_mutation();
CREATE TRIGGER care_plan_evidence_fence BEFORE INSERT OR UPDATE OR DELETE ON public.care_plan_versions
  FOR EACH ROW EXECUTE FUNCTION private.fence_care_plan_evidence_mutation();
-- Fence draft edits before 043's parent-row lock to avoid item -> plan inversion.
CREATE TRIGGER care_plan_aaa_evidence_fence BEFORE INSERT OR UPDATE OR DELETE ON public.care_plan_items
  FOR EACH ROW EXECUTE FUNCTION private.fence_care_plan_evidence_mutation();

CREATE FUNCTION public.guard_care_plan_document_review() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  IF NEW.status = 'approved' AND OLD.status IS DISTINCT FROM 'approved' THEN
    -- Public RPC owns the fence before plan/patient/projection locks. Direct
    -- UPDATE callers already own a plan row and must not wait in reverse order.
    PERFORM private.lock_care_plan_evidence(NEW.patient_id, false);
    IF current_setting('transaction_isolation') <> 'read committed' THEN
      RAISE EXCEPTION 'Care-plan eligibility requires a fresh read-committed snapshot';
    END IF;
    IF EXISTS (
      SELECT 1 FROM public.care_plan_items i
      WHERE i.plan_version_id = NEW.id AND NOT i.is_removed AND (
        NOT EXISTS (
          SELECT 1 FROM public.clinical_facts f
          WHERE f.id = i.source_fact_id AND f.patient_id = NEW.patient_id
            AND f.review_state IN ('pending_review', 'approved')) OR
        NOT EXISTS (
          SELECT 1 FROM public.evidence_citations c
          JOIN public.source_provenances p ON p.id = c.provenance_id
          LEFT JOIN public.documents d ON d.id = p.document_id
          WHERE c.fact_id = i.source_fact_id AND p.withdrawn_at IS NULL
            AND (p.artifact_type = 'clinician_entry' OR
              (p.artifact_type = 'document' AND d.patient_id = NEW.patient_id AND
                (d.uploaded_by_role = 'clinician' OR
                  (d.uploaded_by_role = 'patient' AND d.review_status = 'approved')))))
        OR EXISTS (
          SELECT 1 FROM public.evidence_citations c
          JOIN public.source_provenances p ON p.id = c.provenance_id
          LEFT JOIN public.documents d ON d.id = p.document_id
          WHERE c.fact_id = i.source_fact_id AND p.artifact_type = 'document'
            AND (p.withdrawn_at IS NOT NULL OR d.id IS NULL
              OR d.patient_id IS DISTINCT FROM NEW.patient_id
              OR d.uploaded_by_role IS NULL OR d.uploaded_by_role NOT IN ('patient', 'clinician')
              OR (d.uploaded_by_role = 'patient' AND d.review_status IS DISTINCT FROM 'approved')))))
    THEN
      RAISE EXCEPTION 'Review and approve patient-uploaded source documents before publication; remove rejected, missing or withdrawn sources';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER care_plan_aaa_document_review_guard BEFORE UPDATE ON public.care_plan_versions
  FOR EACH ROW EXECUTE FUNCTION public.guard_care_plan_document_review();
REVOKE ALL ON FUNCTION public.guard_care_plan_document_review() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.guard_care_plan_document_review() TO service_role;

-- Approving an already-parsed upload must wake drafting without re-ingestion.
-- Trigger and review decision commit together: no successful review can lose this handoff.
CREATE FUNCTION public.queue_accepted_document_care_plan() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  IF NEW.uploaded_by_role = 'patient' AND NEW.review_status = 'approved'
    AND OLD.review_status IS DISTINCT FROM 'approved' AND NEW.parse_status = 'completed'
    AND EXISTS (
      SELECT 1 FROM public.source_provenances p
      JOIN public.evidence_citations c ON c.provenance_id = p.id
      JOIN public.clinical_facts f ON f.id = c.fact_id
      WHERE p.document_id = NEW.id AND p.withdrawn_at IS NULL
        AND f.patient_id = NEW.patient_id AND f.fact_type IN ('medication', 'obligation')
        AND private.care_plan_fact_is_eligible(NEW.patient_id, f.id)) THEN
    PERFORM public.request_care_plan_generation(NEW.patient_id, clock_timestamp());
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER accepted_document_care_plan_queue AFTER UPDATE OF review_status ON public.documents
  FOR EACH ROW EXECUTE FUNCTION public.queue_accepted_document_care_plan();
REVOKE ALL ON FUNCTION public.queue_accepted_document_care_plan() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.queue_accepted_document_care_plan() TO service_role;

-- Preserve the existing publication/continuity and generation bodies outside
-- the Data API schema. Their public entries take the fence before any row lock.
ALTER FUNCTION public.approve_care_plan_version(uuid, uuid, text) SET SCHEMA private;
CREATE FUNCTION public.approve_care_plan_version(
  p_plan_version_id uuid, p_reviewer_id uuid, p_note text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_patient uuid;
BEGIN
  SELECT patient_id INTO v_patient FROM public.care_plan_versions WHERE id = p_plan_version_id;
  PERFORM private.lock_care_plan_evidence(v_patient, true);
  IF EXISTS (SELECT 1 FROM public.care_plan_versions
    WHERE id = p_plan_version_id AND patient_id IS DISTINCT FROM v_patient) THEN
    RAISE EXCEPTION 'Care-plan patient changed; reload before publication';
  END IF;
  RETURN private.approve_care_plan_version(p_plan_version_id, p_reviewer_id, p_note);
END;
$$;

ALTER FUNCTION public.complete_care_plan_generation(uuid, uuid, timestamptz, jsonb) SET SCHEMA private;
CREATE FUNCTION public.complete_care_plan_generation(
  p_plan_version_id uuid, p_request_id uuid, p_source_watermark timestamptz, p_items jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_patient uuid;
BEGIN
  SELECT patient_id INTO v_patient FROM public.care_plan_versions WHERE id = p_plan_version_id;
  PERFORM private.lock_care_plan_evidence(v_patient, true);
  IF EXISTS (SELECT 1 FROM public.care_plan_versions
    WHERE id = p_plan_version_id AND patient_id IS DISTINCT FROM v_patient) THEN
    RAISE EXCEPTION 'Care-plan patient changed; reload before generation';
  END IF;
  IF current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION 'Care-plan eligibility requires a fresh read-committed snapshot';
  END IF;
  IF jsonb_typeof(p_items) IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'invalid care plan item batch';
  END IF;
  IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_items) proposed
    WHERE NOT EXISTS (SELECT 1 FROM public.care_plan_items i
      WHERE i.plan_version_id = p_plan_version_id
        AND i.source_fact_id = (proposed->>'source_fact_id')::uuid AND i.is_removed)
      AND NOT private.care_plan_fact_is_eligible(v_patient, (proposed->>'source_fact_id')::uuid)) THEN
    RAISE EXCEPTION 'Review and approve patient-uploaded source documents before generation; remove rejected, missing or withdrawn sources';
  END IF;
  RETURN private.complete_care_plan_generation(
    p_plan_version_id, p_request_id, p_source_watermark, p_items);
END;
$$;

-- Serialize even when no open request exists: SELECT-then-INSERT alone races.
CREATE OR REPLACE FUNCTION public.request_care_plan_generation(
  p_patient_id uuid, p_source_watermark timestamptz
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_request public.care_plan_generation_requests%ROWTYPE;
BEGIN
  PERFORM private.lock_care_plan_evidence(p_patient_id, true);
  SELECT * INTO v_request FROM public.care_plan_generation_requests
    WHERE patient_id = p_patient_id AND status IN ('pending', 'processing', 'retry') FOR UPDATE;
  IF FOUND THEN
    UPDATE public.care_plan_generation_requests
    SET source_watermark = GREATEST(source_watermark, p_source_watermark),
      status = 'pending', requested_at = now(), next_attempt_at = NULL,
      claimed_at = NULL, failure_code = NULL
    WHERE id = v_request.id RETURNING * INTO v_request;
  ELSE
    INSERT INTO public.care_plan_generation_requests(patient_id, source_watermark)
      VALUES (p_patient_id, p_source_watermark) RETURNING * INTO v_request;
  END IF;
  RETURN jsonb_build_object('request_id', v_request.id, 'status', v_request.status);
END;
$$;

REVOKE ALL ON FUNCTION private.lock_care_plan_evidence(uuid, boolean),
  private.care_plan_fact_is_eligible(uuid, uuid), private.fence_care_plan_evidence_mutation(),
  private.approve_care_plan_version(uuid, uuid, text),
  private.complete_care_plan_generation(uuid, uuid, timestamptz, jsonb),
  public.approve_care_plan_version(uuid, uuid, text),
  public.complete_care_plan_generation(uuid, uuid, timestamptz, jsonb),
  public.request_care_plan_generation(uuid, timestamptz)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.lock_care_plan_evidence(uuid, boolean),
  private.care_plan_fact_is_eligible(uuid, uuid), private.fence_care_plan_evidence_mutation(),
  private.approve_care_plan_version(uuid, uuid, text),
  private.complete_care_plan_generation(uuid, uuid, timestamptz, jsonb),
  public.approve_care_plan_version(uuid, uuid, text),
  public.complete_care_plan_generation(uuid, uuid, timestamptz, jsonb),
  public.request_care_plan_generation(uuid, timestamptz)
  TO service_role;
