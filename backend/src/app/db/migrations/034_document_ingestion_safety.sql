-- Safe document-ingestion lifecycle. Extraction remains candidate-only.

ALTER TABLE public.documents
  DROP CONSTRAINT IF EXISTS documents_parse_status_check;
ALTER TABLE public.documents
  ADD CONSTRAINT documents_parse_status_check
  CHECK (parse_status IN (
    'none', 'pending', 'processing', 'completed', 'failed',
    'needs_ocr', 'needs_evidence_review'
  ));
ALTER TABLE public.documents
  ADD COLUMN IF NOT EXISTS parse_failure_code text,
  ADD CONSTRAINT documents_parse_failure_code_check
  CHECK (parse_failure_code IS NULL OR parse_failure_code IN (
    'provider_unavailable', 'invalid_model_response', 'source_unreadable',
    'needs_ocr', 'evidence_not_grounded', 'attempt_limit_reached'
  ));

ALTER TABLE public.document_ingestion_runs
  DROP CONSTRAINT IF EXISTS document_ingestion_runs_status_check;
ALTER TABLE public.document_ingestion_runs
  ADD CONSTRAINT document_ingestion_runs_status_check
  CHECK (status IN (
    'pending', 'processing', 'completed', 'failed', 'duplicate',
    'needs_ocr', 'needs_evidence_review'
  ));
ALTER TABLE public.document_ingestion_runs
  ADD COLUMN IF NOT EXISTS failure_code text,
  ADD COLUMN IF NOT EXISTS warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS input_kind text,
  ADD COLUMN IF NOT EXISTS page_count integer NOT NULL DEFAULT 0 CHECK (page_count >= 0),
  ADD COLUMN IF NOT EXISTS extracted_text_char_count integer NOT NULL DEFAULT 0
    CHECK (extracted_text_char_count >= 0),
  ADD COLUMN IF NOT EXISTS extraction_method text;

CREATE OR REPLACE FUNCTION public.claim_document_ingestion(
  p_document_id uuid,
  p_patient_id uuid,
  p_actor_id uuid DEFAULT NULL,
  p_is_retry boolean DEFAULT false
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
  v_document public.documents%ROWTYPE;
  v_attempt integer;
  v_run_id uuid;
BEGIN
  SELECT * INTO v_document
  FROM public.documents
  WHERE id = p_document_id AND patient_id = p_patient_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'document not found for patient';
  END IF;

  IF p_actor_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM public.care_teams
    WHERE clinician_id = p_actor_id
      AND patient_id = p_patient_id
      AND status = 'active'
  ) THEN
    RAISE EXCEPTION 'clinician is not assigned to patient';
  END IF;

  IF v_document.parse_status = 'processing' THEN
    RAISE EXCEPTION 'document ingestion is already processing';
  END IF;
  IF p_is_retry AND v_document.parse_status <> 'failed' THEN
    RAISE EXCEPTION 'document is not eligible for retry';
  END IF;
  IF NOT p_is_retry AND v_document.parse_status NOT IN ('pending', 'none') THEN
    RAISE EXCEPTION 'document is not eligible for initial ingestion';
  END IF;

  v_attempt := v_document.parse_attempts + 1;
  IF v_attempt > 3 THEN
    UPDATE public.documents
    SET parse_status = 'failed',
        parse_failure_code = 'attempt_limit_reached',
        parse_error = NULL
    WHERE id = p_document_id;
    RAISE EXCEPTION 'document ingestion attempt limit reached';
  END IF;

  UPDATE public.documents
  SET parse_status = 'processing',
      parse_error = NULL,
      parse_failure_code = NULL,
      parse_attempts = v_attempt,
      parsed = false
  WHERE id = p_document_id;

  INSERT INTO public.document_ingestion_runs (
    document_id, patient_id, source_hash, status, attempt, extractor_version
  ) VALUES (
    p_document_id, p_patient_id, v_document.content_hash, 'processing', v_attempt,
    'document-intelligence/1'
  ) RETURNING id INTO v_run_id;

  RETURN jsonb_build_object(
    'run_id', v_run_id,
    'attempt', v_attempt,
    'file_path', v_document.file_path,
    'document_type', v_document.document_type,
    'mime_type', v_document.mime_type,
    'content_hash', v_document.content_hash
  );
END;
$$;

REVOKE ALL ON FUNCTION public.claim_document_ingestion(uuid, uuid, uuid, boolean)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_document_ingestion(uuid, uuid, uuid, boolean)
  TO service_role;
