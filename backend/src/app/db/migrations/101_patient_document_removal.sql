-- Patient removal is confined to the patient's own pending, unused upload.
-- A refused request must not withdraw evidence or change clinical truth.
CREATE TABLE public.document_removal_events (
  document_id uuid PRIMARY KEY,
  patient_id uuid NOT NULL REFERENCES public.patients(id) ON DELETE CASCADE,
  actor_id uuid NOT NULL,
  removed_at timestamptz NOT NULL DEFAULT now(),
  CHECK (actor_id = patient_id)
);
ALTER TABLE public.document_removal_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.document_removal_events FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.document_removal_events TO service_role;

CREATE FUNCTION private.patient_document_removal_blocker(p_document_id uuid, p_patient_id uuid)
RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
  SELECT CASE
    WHEN d.uploaded_by_role IS DISTINCT FROM 'patient' OR d.uploaded_by <> p_patient_id
      THEN 'care_team_upload'
    WHEN d.review_status IS DISTINCT FROM 'pending' OR d.reviewed_by IS NOT NULL
      OR d.reviewed_at IS NOT NULL OR nullif(btrim(d.clinician_annotation), '') IS NOT NULL
      OR nullif(btrim(d.review_note), '') IS NOT NULL
      THEN 'reviewed'
    WHEN d.parse_status = 'processing' OR d.summary_status = 'processing'
      OR EXISTS (SELECT 1 FROM public.document_ingestion_runs r
        WHERE r.document_id = d.id AND r.status = 'processing')
      THEN 'processing'
    WHEN EXISTS (SELECT 1 FROM public.medications m WHERE m.source_document_id = d.id)
      OR EXISTS (SELECT 1 FROM public.obligations o WHERE o.source_document_id = d.id)
      OR EXISTS (SELECT 1 FROM public.appointments a WHERE a.source_document_id = d.id)
      OR EXISTS (SELECT 1 FROM public.documents other WHERE other.id <> d.id AND (
        nullif(ltrim(btrim(d.file_path), '/'), '') IN (
          nullif(ltrim(btrim(other.file_path), '/'), ''), nullif(ltrim(btrim(other.preview_path), '/'), ''))
        OR nullif(ltrim(btrim(d.preview_path), '/'), '') IN (
          nullif(ltrim(btrim(other.file_path), '/'), ''), nullif(ltrim(btrim(other.preview_path), '/'), ''))))
      OR EXISTS (SELECT 1 FROM public.source_provenances p
        WHERE p.document_id = d.id AND p.withdrawn_at IS NOT NULL)
      OR EXISTS (
        SELECT 1 FROM public.source_provenances p
        JOIN public.evidence_citations c ON c.provenance_id = p.id
        JOIN public.clinical_facts f ON f.id = c.fact_id
        WHERE p.document_id = d.id AND (
          f.patient_id <> p_patient_id OR f.review_state <> 'pending_review'
          OR f.reconciliation_state <> 'not_started' OR f.reviewed_by IS NOT NULL
          OR f.reviewed_at IS NOT NULL
          OR EXISTS (SELECT 1 FROM public.clinical_fact_reconciliation_events e WHERE e.fact_id = f.id)
          OR EXISTS (SELECT 1 FROM public.clinical_fact_audit_events e
            WHERE e.fact_id = f.id AND e.event_type <> 'created')
          OR EXISTS (SELECT 1 FROM public.care_plan_items i WHERE i.source_fact_id = f.id)))
      THEN 'used_in_record'
    ELSE NULL
  END
  FROM public.documents d WHERE d.id = p_document_id AND d.patient_id = p_patient_id;
$$;
REVOKE ALL ON FUNCTION private.patient_document_removal_blocker(uuid, uuid)
  FROM PUBLIC, anon, authenticated, service_role;

CREATE FUNCTION public.patient_document_removal_status(
  p_document_id uuid, p_patient_id uuid, p_actor_id uuid
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_reason text;
BEGIN
  IF p_actor_id IS DISTINCT FROM p_patient_id THEN
    RAISE EXCEPTION 'Patient actor required' USING ERRCODE = '42501';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.documents WHERE id = p_document_id AND patient_id = p_patient_id) THEN
    RAISE EXCEPTION 'Document unavailable' USING ERRCODE = 'P0002';
  END IF;
  v_reason := private.patient_document_removal_blocker(p_document_id, p_patient_id);
  RETURN jsonb_build_object('can_remove', v_reason IS NULL, 'reason', v_reason);
END;
$$;

CREATE FUNCTION public.remove_patient_document_upload(
  p_document_id uuid, p_patient_id uuid, p_actor_id uuid
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_document public.documents%ROWTYPE; v_reason text; v_cleanup jsonb;
BEGIN
  IF p_actor_id IS DISTINCT FROM p_patient_id THEN
    RAISE EXCEPTION 'Patient actor required' USING ERRCODE = '42501';
  END IF;
  IF current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION 'Removal requires a fresh read-committed snapshot' USING ERRCODE = '40001';
  END IF;
  SELECT * INTO v_document FROM public.documents
    WHERE id = p_document_id AND patient_id = p_patient_id FOR UPDATE;
  IF NOT FOUND THEN
    IF EXISTS (SELECT 1 FROM public.document_removal_events
      WHERE document_id = p_document_id AND patient_id = p_patient_id AND actor_id = p_actor_id) THEN
      RETURN jsonb_build_object('removed', true, 'replayed', true);
    END IF;
    RAISE EXCEPTION 'Document unavailable' USING ERRCODE = 'P0002';
  END IF;
  -- Reviews and ingestion UPDATE the document before their row trigger fences
  -- evidence. Match that row-first order and never wait for a reverse lock.
  PERFORM private.lock_care_plan_evidence(p_patient_id, false);
  v_reason := private.patient_document_removal_blocker(p_document_id, p_patient_id);
  IF v_reason IS NOT NULL THEN
    RAISE EXCEPTION 'Document requires care-team review' USING ERRCODE = '42501';
  END IF;
  v_cleanup := public.withdraw_unapplied_document_source(p_document_id, p_patient_id, p_actor_id);
  IF (v_cleanup->>'can_delete')::boolean IS DISTINCT FROM true THEN
    -- Roll back even a legacy helper's withdrawal writes if a new blocker appears.
    RAISE EXCEPTION 'Document requires care-team review' USING ERRCODE = '42501';
  END IF;
  INSERT INTO public.document_removal_events(document_id, patient_id, actor_id)
    VALUES(p_document_id, p_patient_id, p_actor_id);
  DELETE FROM public.documents WHERE id = p_document_id AND patient_id = p_patient_id;
  RETURN jsonb_build_object('removed', true, 'replayed', false,
    'file_path', v_document.file_path, 'preview_path', v_document.preview_path);
END;
$$;

REVOKE ALL ON FUNCTION public.patient_document_removal_status(uuid, uuid, uuid)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.remove_patient_document_upload(uuid, uuid, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.patient_document_removal_status(uuid, uuid, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.remove_patient_document_upload(uuid, uuid, uuid) TO service_role;
