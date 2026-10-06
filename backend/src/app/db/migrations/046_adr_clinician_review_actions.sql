-- Add an auditable clinician decision lifecycle to ADR assessments.
-- Requesting information intentionally leaves an assessment in draft status.

ALTER TABLE public.adr_assessments
  ADD COLUMN IF NOT EXISTS last_review_action text,
  ADD COLUMN IF NOT EXISTS review_note text,
  ADD COLUMN IF NOT EXISTS requested_information jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

ALTER TABLE public.adr_assessments
  DROP CONSTRAINT IF EXISTS adr_assessments_last_review_action_check,
  DROP CONSTRAINT IF EXISTS adr_assessments_requested_information_array;

ALTER TABLE public.adr_assessments
  ADD CONSTRAINT adr_assessments_last_review_action_check
    CHECK (
      last_review_action IS NULL
      OR last_review_action IN ('mark_reviewed', 'dismiss', 'request_information')
    ),
  ADD CONSTRAINT adr_assessments_requested_information_array
    CHECK (jsonb_typeof(requested_information) = 'array');

CREATE TABLE IF NOT EXISTS public.adr_assessment_audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  adr_assessment_id uuid NOT NULL REFERENCES public.adr_assessments(id) ON DELETE CASCADE,
  actor_id uuid NOT NULL REFERENCES public.clinicians(id) ON DELETE RESTRICT,
  event_type text NOT NULL CHECK (
    event_type IN ('marked_reviewed', 'dismissed', 'information_requested')
  ),
  event_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_adr_assessment_audit_events_assessment
  ON public.adr_assessment_audit_events(adr_assessment_id, created_at ASC);

ALTER TABLE public.adr_assessment_audit_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS adr_assessment_audit_events_clinician_select
  ON public.adr_assessment_audit_events;
CREATE POLICY adr_assessment_audit_events_clinician_select
  ON public.adr_assessment_audit_events FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1
      FROM public.adr_assessments assessment
      JOIN public.care_teams team ON team.patient_id = assessment.patient_id
      WHERE assessment.id = adr_assessment_audit_events.adr_assessment_id
        AND team.clinician_id = auth.uid()
        AND team.status = 'active'
    )
  );

CREATE OR REPLACE FUNCTION public.review_adr_assessment(
  p_assessment_id uuid,
  p_actor_id uuid,
  p_action text,
  p_note text DEFAULT NULL,
  p_requested_information jsonb DEFAULT '[]'::jsonb
) RETURNS SETOF public.adr_assessments
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_assessment public.adr_assessments%ROWTYPE;
  v_note text := NULLIF(btrim(COALESCE(p_note, '')), '');
  v_status public.adr_status_enum;
  v_event_type text;
  v_requested_information jsonb := COALESCE(p_requested_information, '[]'::jsonb);
  v_now timestamptz := now();
BEGIN
  SELECT * INTO v_assessment
  FROM public.adr_assessments
  WHERE id = p_assessment_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'ADR assessment not found' USING ERRCODE = 'P0002';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.care_teams
    WHERE clinician_id = p_actor_id
      AND patient_id = v_assessment.patient_id
      AND status = 'active'
  ) THEN
    RAISE EXCEPTION 'Clinician is not assigned to this patient' USING ERRCODE = '42501';
  END IF;

  IF v_assessment.status <> 'draft' THEN
    RAISE EXCEPTION 'ADR assessment review has already been completed'
      USING ERRCODE = '23514';
  END IF;

  IF p_action NOT IN ('mark_reviewed', 'dismiss', 'request_information') THEN
    RAISE EXCEPTION 'Unsupported ADR review action' USING ERRCODE = '22023';
  END IF;

  IF p_action IN ('dismiss', 'request_information') AND v_note IS NULL THEN
    RAISE EXCEPTION 'A review note is required for this action' USING ERRCODE = '22023';
  END IF;

  IF jsonb_typeof(v_requested_information) <> 'array' THEN
    RAISE EXCEPTION 'Requested information must be an array' USING ERRCODE = '22023';
  END IF;

  v_status := CASE
    WHEN p_action = 'mark_reviewed' THEN 'reviewed'::public.adr_status_enum
    WHEN p_action = 'dismiss' THEN 'dismissed'::public.adr_status_enum
    ELSE 'draft'::public.adr_status_enum
  END;
  v_event_type := CASE
    WHEN p_action = 'mark_reviewed' THEN 'marked_reviewed'
    WHEN p_action = 'dismiss' THEN 'dismissed'
    ELSE 'information_requested'
  END;

  UPDATE public.adr_assessments
  SET status = v_status,
      reviewed_by = p_actor_id,
      reviewed_at = v_now,
      dismiss_reason = CASE WHEN p_action = 'dismiss' THEN v_note ELSE NULL END,
      last_review_action = p_action,
      review_note = v_note,
      requested_information = CASE
        WHEN p_action = 'request_information' THEN v_requested_information
        ELSE '[]'::jsonb
      END,
      updated_at = v_now
  WHERE id = p_assessment_id;

  INSERT INTO public.adr_assessment_audit_events(
    adr_assessment_id,
    actor_id,
    event_type,
    event_data
  ) VALUES (
    p_assessment_id,
    p_actor_id,
    v_event_type,
    jsonb_build_object(
      'previous_status', v_assessment.status,
      'status', v_status,
      'note', v_note,
      'requested_information', CASE
        WHEN p_action = 'request_information' THEN v_requested_information
        ELSE '[]'::jsonb
      END
    )
  );

  RETURN QUERY
  SELECT * FROM public.adr_assessments WHERE id = p_assessment_id;
END;
$$;

REVOKE ALL ON FUNCTION public.review_adr_assessment(uuid, uuid, text, text, jsonb)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.review_adr_assessment(uuid, uuid, text, text, jsonb)
  TO service_role;
GRANT SELECT ON TABLE public.adr_assessment_audit_events TO service_role;

COMMENT ON TABLE public.adr_assessment_audit_events IS
  'Immutable clinician actions for ADR review; never model reasoning.';
COMMENT ON COLUMN public.adr_assessments.requested_information IS
  'Naranjo or free-form information requested by the assigned clinician.';
