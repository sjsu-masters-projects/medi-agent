-- The optional patient explanation gets its own lifecycle, separate from ingestion.
--
-- Extraction, evidence grounding, and the immutable source are clinical work. The
-- patient-facing summary is an optional convenience generated from candidates that
-- already exist. Before this migration a provider outage during the summary step
-- left only `ai_summary = NULL`: indistinguishable from a document nobody had
-- summarized yet, with no reason, no attempt history, and no retry that avoided
-- re-running OCR and re-proposing the same clinical candidates.
--
-- These columns make that failure observable and retryable on its own. Nothing
-- here may change `parse_status`, the stored source, or the candidate lifecycle.

ALTER TABLE public.documents
  ADD COLUMN IF NOT EXISTS summary_status text NOT NULL DEFAULT 'not_required',
  ADD COLUMN IF NOT EXISTS summary_failure_code text,
  ADD COLUMN IF NOT EXISTS summary_prompt_version text,
  ADD COLUMN IF NOT EXISTS summary_attempts integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS summary_last_attempt_at timestamptz;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'documents_summary_status_check'
      AND conrelid = 'public.documents'::regclass
  ) THEN
    ALTER TABLE public.documents
      ADD CONSTRAINT documents_summary_status_check
      CHECK (summary_status IN ('not_required', 'pending', 'processing', 'ready', 'failed'));
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'documents_summary_failure_code_check'
      AND conrelid = 'public.documents'::regclass
  ) THEN
    ALTER TABLE public.documents
      ADD CONSTRAINT documents_summary_failure_code_check
      CHECK (summary_failure_code IS NULL OR summary_failure_code IN (
        'provider_unavailable', 'summary_empty', 'source_unavailable',
        'attempt_limit_reached'
      ));
  END IF;
END
$$;

-- A `ready` summary must actually have text. Without this a UI could report an
-- explanation as available and then render nothing.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'documents_summary_shape_check'
      AND conrelid = 'public.documents'::regclass
  ) THEN
    ALTER TABLE public.documents
      ADD CONSTRAINT documents_summary_shape_check
      CHECK (
        (summary_status = 'ready' AND ai_summary IS NOT NULL AND length(btrim(ai_summary)) > 0)
        OR summary_status <> 'ready'
      );
  END IF;
END
$$;

ALTER TABLE public.documents
  DROP CONSTRAINT IF EXISTS documents_summary_attempts_check;
ALTER TABLE public.documents
  ADD CONSTRAINT documents_summary_attempts_check CHECK (summary_attempts >= 0);

-- Backfill: an existing summary is already `ready`; a completed extraction with no
-- summary is exactly the state this work makes retryable, so it starts `pending`.
UPDATE public.documents
SET summary_status = 'ready'
WHERE summary_status = 'not_required'
  AND ai_summary IS NOT NULL
  AND length(btrim(ai_summary)) > 0;

UPDATE public.documents
SET summary_status = 'pending'
WHERE summary_status = 'not_required'
  AND parse_status = 'completed'
  AND (ai_summary IS NULL OR length(btrim(ai_summary)) = 0);

CREATE INDEX IF NOT EXISTS documents_summary_status_pending_idx
  ON public.documents (created_at)
  WHERE summary_status = 'pending';

-- Claim summaries only. This never touches parse_status, the source artifact, or any
-- clinical candidate, so a retry cannot duplicate facts or re-run OCR.
CREATE OR REPLACE FUNCTION public.claim_pending_document_summary(p_limit integer DEFAULT 10)
RETURNS SETOF jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
  v_document public.documents%ROWTYPE;
  v_attempt integer;
BEGIN
  FOR v_document IN
    SELECT *
    FROM public.documents
    WHERE summary_status = 'pending'
      AND parse_status = 'completed'
    ORDER BY created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT LEAST(GREATEST(p_limit, 1), 100)
  LOOP
    v_attempt := v_document.summary_attempts + 1;
    IF v_attempt > 3 THEN
      UPDATE public.documents
      SET summary_status = 'failed',
          summary_failure_code = 'attempt_limit_reached'
      WHERE id = v_document.id;
      CONTINUE;
    END IF;

    UPDATE public.documents
    SET summary_status = 'processing',
        summary_failure_code = NULL,
        summary_attempts = v_attempt,
        summary_last_attempt_at = now()
    WHERE id = v_document.id;

    RETURN NEXT jsonb_build_object(
      'document_id', v_document.id,
      'patient_id', v_document.patient_id,
      'attempt', v_attempt
    );
  END LOOP;
END;
$$;

-- A clinician retry resets the attempt counter, which the ingestion retry deliberately
-- does not. Re-running ingestion spends OCR and re-proposes clinical candidates, so its
-- attempts are capped for safety. A summary retry only re-reads candidates that already
-- exist, so an outage that burns three automatic attempts must not permanently strand the
-- explanation. Each human action still buys one bounded cycle, not unlimited retries.
CREATE OR REPLACE FUNCTION public.enqueue_document_summary_retry(
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

  IF v_document.parse_status <> 'completed' THEN
    RAISE EXCEPTION 'document has no completed extraction to summarize';
  END IF;
  IF v_document.summary_status <> 'failed' THEN
    RAISE EXCEPTION 'document summary is not eligible for retry';
  END IF;

  UPDATE public.documents
  SET summary_status = 'pending',
      summary_failure_code = NULL,
      summary_attempts = 0
  WHERE id = p_document_id;

  RETURN jsonb_build_object('document_id', p_document_id, 'summary_status', 'pending');
END;
$$;

REVOKE ALL ON FUNCTION public.claim_pending_document_summary(integer)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.enqueue_document_summary_retry(uuid, uuid, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_pending_document_summary(integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.enqueue_document_summary_retry(uuid, uuid, uuid) TO service_role;
