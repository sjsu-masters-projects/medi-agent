-- Durable claim-and-worker boundary for document ingestion.
--
-- Upload requests only insert documents with parse_status = 'pending'.  A Cloud
-- Run Job claims rows with SKIP LOCKED so two job executions never process the
-- same source.  The service-role backend is the only caller allowed to change
-- this lifecycle; clinician retries are separately authorized and only requeue
-- a failed document.

CREATE OR REPLACE FUNCTION public.claim_pending_document_ingestion(p_limit integer DEFAULT 10)
RETURNS SETOF jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
  v_document public.documents%ROWTYPE;
  v_attempt integer;
  v_run_id uuid;
BEGIN
  FOR v_document IN
    SELECT *
    FROM public.documents
    WHERE parse_status = 'pending'
    ORDER BY created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT LEAST(GREATEST(p_limit, 1), 100)
  LOOP
    v_attempt := v_document.parse_attempts + 1;
    IF v_attempt > 3 THEN
      UPDATE public.documents
      SET parse_status = 'failed',
          parse_failure_code = 'attempt_limit_reached',
          parse_error = NULL
      WHERE id = v_document.id;
      CONTINUE;
    END IF;

    UPDATE public.documents
    SET parse_status = 'processing',
        parse_error = NULL,
        parse_failure_code = NULL,
        parse_attempts = v_attempt,
        parsed = false
    WHERE id = v_document.id;

    INSERT INTO public.document_ingestion_runs (
      document_id, patient_id, source_hash, status, attempt, extractor_version
    ) VALUES (
      v_document.id, v_document.patient_id, v_document.content_hash, 'processing', v_attempt,
      'document-intelligence/1'
    ) RETURNING id INTO v_run_id;

    RETURN NEXT jsonb_build_object(
      'document_id', v_document.id,
      'patient_id', v_document.patient_id,
      'run_id', v_run_id,
      'attempt', v_attempt,
      'file_path', v_document.file_path,
      'document_type', v_document.document_type,
      'mime_type', v_document.mime_type,
      'content_hash', v_document.content_hash
    );
  END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION public.enqueue_document_ingestion_retry(
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
  v_document public.documents%ROWTYPE;
BEGIN
  SELECT * INTO v_document
  FROM public.documents
  WHERE id = p_document_id AND patient_id = p_patient_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'document not found for patient';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.care_teams
    WHERE clinician_id = p_actor_id
      AND patient_id = p_patient_id
      AND status = 'active'
  ) THEN
    RAISE EXCEPTION 'clinician is not assigned to patient';
  END IF;

  IF v_document.parse_status <> 'failed' THEN
    RAISE EXCEPTION 'document is not eligible for retry';
  END IF;
  IF v_document.parse_attempts >= 3 THEN
    RAISE EXCEPTION 'document ingestion attempt limit reached';
  END IF;

  UPDATE public.documents
  SET parse_status = 'pending',
      parse_error = NULL,
      parse_failure_code = NULL,
      parsed = false
  WHERE id = p_document_id;

  RETURN jsonb_build_object('document_id', p_document_id, 'status', 'pending');
END;
$$;

REVOKE ALL ON FUNCTION public.claim_pending_document_ingestion(integer)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.enqueue_document_ingestion_retry(uuid, uuid, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_pending_document_ingestion(integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.enqueue_document_ingestion_retry(uuid, uuid, uuid) TO service_role;
