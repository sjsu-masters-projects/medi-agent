-- Fair, delayed retry scheduling for optional patient explanations.
--
-- The ingestion result, source document, and pending clinical candidates remain
-- immutable here. This only determines when the separate explanation worker may
-- retry an operational failure.

ALTER TABLE public.documents
  ADD COLUMN IF NOT EXISTS summary_next_attempt_at timestamptz;

-- Preserve previously pending provider failures as immediately eligible after this
-- migration. New failures receive a deliberate delay from the worker instead.
UPDATE public.documents
SET summary_next_attempt_at = COALESCE(summary_last_attempt_at, created_at)
WHERE summary_status = 'pending'
  AND summary_next_attempt_at IS NULL
  AND summary_attempts > 0;

CREATE INDEX IF NOT EXISTS documents_summary_claim_schedule_idx
  ON public.documents (summary_attempts, summary_next_attempt_at, created_at)
  WHERE summary_status = 'pending' AND parse_status = 'completed';

CREATE INDEX IF NOT EXISTS documents_summary_processing_lease_idx
  ON public.documents (summary_last_attempt_at)
  WHERE summary_status = 'processing';

-- Fresh explanations are normally chosen ahead of retries, while retries only
-- become claimable after their recorded delay. A retry that has been due for 15
-- minutes takes the anti-starvation lane ahead of fresh work, so a sustained
-- stream of uploads cannot leave it pending forever. This keeps an unavailable
-- provider from repeatedly consuming a small validation batch while still
-- bounding how long an eligible retry can wait. `SKIP LOCKED` preserves safe
-- concurrent Job execution.
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
  -- A stopped Job must not strand a claim forever. The explanation is optional
  -- and built only from persisted candidates, so returning an expired lease to
  -- pending is safe and does not re-run OCR or mutate clinical candidates.
  UPDATE public.documents
  SET summary_status = 'pending',
      summary_failure_code = 'worker_lease_expired',
      summary_next_attempt_at = now()
  WHERE summary_status = 'processing'
    AND summary_last_attempt_at < now() - interval '10 minutes';

  FOR v_document IN
    SELECT *
    FROM public.documents
    WHERE summary_status = 'pending'
      AND parse_status = 'completed'
      AND (summary_next_attempt_at IS NULL OR summary_next_attempt_at <= now())
    ORDER BY
      CASE
        WHEN summary_attempts > 0
          AND summary_next_attempt_at <= now() - interval '15 minutes' THEN 0
        WHEN summary_attempts = 0 THEN 1
        ELSE 2
      END,
      summary_next_attempt_at ASC NULLS FIRST,
      created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT LEAST(GREATEST(p_limit, 1), 100)
  LOOP
    v_attempt := v_document.summary_attempts + 1;
    IF v_attempt > 3 THEN
      UPDATE public.documents
      SET summary_status = 'failed',
          summary_failure_code = 'attempt_limit_reached',
          summary_next_attempt_at = NULL
      WHERE id = v_document.id;
      CONTINUE;
    END IF;

    UPDATE public.documents
    SET summary_status = 'processing',
        summary_failure_code = NULL,
        summary_attempts = v_attempt,
        summary_last_attempt_at = now(),
        summary_next_attempt_at = NULL
    WHERE id = v_document.id;

    RETURN NEXT jsonb_build_object(
      'document_id', v_document.id,
      'patient_id', v_document.patient_id,
      'attempt', v_attempt
    );
  END LOOP;
END;
$$;

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
      summary_attempts = 0,
      summary_next_attempt_at = now()
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
