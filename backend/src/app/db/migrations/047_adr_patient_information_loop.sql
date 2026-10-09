-- Close the clinician-to-patient ADR information loop without asking patients to
-- perform a rechallenge, placebo exposure, dose change, or test. Patient responses
-- describe only events that already happened; the backend deterministically rescores.

CREATE TABLE IF NOT EXISTS public.adr_information_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  adr_assessment_id uuid NOT NULL
    REFERENCES public.adr_assessments(id) ON DELETE CASCADE,
  patient_id uuid NOT NULL REFERENCES public.patients(id) ON DELETE CASCADE,
  requested_by uuid NOT NULL REFERENCES public.clinicians(id) ON DELETE RESTRICT,
  requested_information jsonb NOT NULL,
  patient_message text NOT NULL CHECK (char_length(patient_message) BETWEEN 1 AND 2000),
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'answered', 'cancelled')),
  responses jsonb NOT NULL DEFAULT '[]'::jsonb,
  baseline_naranjo_score smallint NOT NULL CHECK (baseline_naranjo_score BETWEEN -4 AND 13),
  baseline_causality public.naranjo_causality_enum NOT NULL,
  resolved_naranjo_score smallint CHECK (resolved_naranjo_score BETWEEN -4 AND 13),
  resolved_causality public.naranjo_causality_enum,
  created_at timestamptz NOT NULL DEFAULT now(),
  responded_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT adr_information_requests_questions_array
    CHECK (jsonb_typeof(requested_information) = 'array'),
  CONSTRAINT adr_information_requests_responses_array
    CHECK (jsonb_typeof(responses) = 'array'),
  CONSTRAINT adr_information_requests_patient_safe_questions
    CHECK (
      requested_information <@ '["reappeared_on_rechallenge", "dose_response", "similar_previous_reaction"]'::jsonb
      AND jsonb_array_length(requested_information) > 0
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_adr_information_requests_one_pending
  ON public.adr_information_requests(adr_assessment_id)
  WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_adr_information_requests_patient_status
  ON public.adr_information_requests(patient_id, status, created_at DESC);

ALTER TABLE public.adr_information_requests ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS adr_information_requests_patient_select
  ON public.adr_information_requests;
CREATE POLICY adr_information_requests_patient_select
  ON public.adr_information_requests FOR SELECT TO authenticated
  USING (patient_id = auth.uid());

DROP POLICY IF EXISTS adr_information_requests_clinician_select
  ON public.adr_information_requests;
CREATE POLICY adr_information_requests_clinician_select
  ON public.adr_information_requests FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1
      FROM public.care_teams team
      WHERE team.patient_id = adr_information_requests.patient_id
        AND team.clinician_id = auth.uid()
        AND team.status = 'active'
    )
  );

REVOKE ALL ON TABLE public.adr_information_requests FROM anon, authenticated;
GRANT SELECT ON TABLE public.adr_information_requests TO authenticated;
GRANT ALL ON TABLE public.adr_information_requests TO service_role;

-- Audit events originally supported clinician actors only. Patient answers retain a
-- separate FK so the actor type stays explicit and reconstructable.
ALTER TABLE public.adr_assessment_audit_events
  ALTER COLUMN actor_id DROP NOT NULL,
  ADD COLUMN IF NOT EXISTS patient_actor_id uuid
    REFERENCES public.patients(id) ON DELETE RESTRICT;

ALTER TABLE public.adr_assessment_audit_events
  DROP CONSTRAINT IF EXISTS adr_assessment_audit_events_event_type_check,
  DROP CONSTRAINT IF EXISTS adr_assessment_audit_events_exactly_one_actor;

ALTER TABLE public.adr_assessment_audit_events
  ADD CONSTRAINT adr_assessment_audit_events_event_type_check
    CHECK (
      event_type IN (
        'marked_reviewed',
        'dismissed',
        'information_requested',
        'patient_information_provided'
      )
    ),
  ADD CONSTRAINT adr_assessment_audit_events_exactly_one_actor
    CHECK (num_nonnulls(actor_id, patient_actor_id) = 1);

-- Preserve an already-open request created by migration 046-era code, but expose only
-- the retrospective questions that a patient can safely answer.
WITH legacy_requests AS (
  SELECT
    assessment.id AS adr_assessment_id,
    assessment.patient_id,
    assessment.reviewed_by AS requested_by,
    assessment.review_note AS patient_message,
    assessment.naranjo_score AS baseline_naranjo_score,
    assessment.causality AS baseline_causality,
    assessment.reviewed_at AS created_at,
    (
      SELECT jsonb_agg(question.value ORDER BY question.ordinality)
      FROM jsonb_array_elements_text(assessment.requested_information)
        WITH ORDINALITY AS question(value, ordinality)
      WHERE question.value IN (
        'reappeared_on_rechallenge',
        'dose_response',
        'similar_previous_reaction'
      )
    ) AS patient_safe_questions
  FROM public.adr_assessments assessment
  WHERE assessment.status = 'draft'
    AND assessment.last_review_action = 'request_information'
    AND assessment.reviewed_by IS NOT NULL
    AND assessment.review_note IS NOT NULL
)
INSERT INTO public.adr_information_requests(
  adr_assessment_id,
  patient_id,
  requested_by,
  requested_information,
  patient_message,
  baseline_naranjo_score,
  baseline_causality,
  created_at
)
SELECT
  adr_assessment_id,
  patient_id,
  requested_by,
  patient_safe_questions,
  patient_message,
  baseline_naranjo_score,
  baseline_causality,
  COALESCE(created_at, now())
FROM legacy_requests
WHERE patient_safe_questions IS NOT NULL
  AND jsonb_array_length(patient_safe_questions) > 0
ON CONFLICT DO NOTHING;

INSERT INTO public.notifications(
  patient_id,
  notification_type,
  title,
  body,
  action_url,
  dedupe_key,
  metadata
)
SELECT
  request.patient_id,
  'adr_alert'::public.notification_type_enum,
  'Your care team has follow-up questions',
  'Please answer a few questions about a symptom you already reported.',
  '/chat',
  'adr-information-request:' || request.id::text,
  jsonb_build_object('adr_information_request_id', request.id)
FROM public.adr_information_requests request
WHERE request.status = 'pending'
ON CONFLICT (dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING;

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
  v_request_id uuid;
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

  IF p_action = 'request_information' AND (
    jsonb_array_length(v_requested_information) = 0
    OR NOT (
      v_requested_information <@ '["reappeared_on_rechallenge", "dose_response", "similar_previous_reaction"]'::jsonb
    )
  ) THEN
    RAISE EXCEPTION 'Only patient-answerable retrospective questions may be requested'
      USING ERRCODE = '22023';
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

  UPDATE public.adr_information_requests
  SET status = 'cancelled', updated_at = v_now
  WHERE adr_assessment_id = p_assessment_id
    AND status = 'pending';

  IF p_action = 'request_information' THEN
    INSERT INTO public.adr_information_requests(
      adr_assessment_id,
      patient_id,
      requested_by,
      requested_information,
      patient_message,
      baseline_naranjo_score,
      baseline_causality,
      created_at,
      updated_at
    ) VALUES (
      p_assessment_id,
      v_assessment.patient_id,
      p_actor_id,
      v_requested_information,
      v_note,
      v_assessment.naranjo_score,
      v_assessment.causality,
      v_now,
      v_now
    ) RETURNING id INTO v_request_id;

    INSERT INTO public.notifications(
      patient_id,
      notification_type,
      title,
      body,
      action_url,
      dedupe_key,
      metadata
    ) VALUES (
      v_assessment.patient_id,
      'adr_alert'::public.notification_type_enum,
      'Your care team has follow-up questions',
      'Please answer a few questions about a symptom you already reported.',
      '/chat',
      'adr-information-request:' || v_request_id::text,
      jsonb_build_object('adr_information_request_id', v_request_id)
    );
  END IF;

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
      'information_request_id', v_request_id,
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

CREATE OR REPLACE FUNCTION public.respond_to_adr_information_request(
  p_request_id uuid,
  p_patient_id uuid,
  p_responses jsonb,
  p_naranjo_answers jsonb,
  p_naranjo_assessment jsonb,
  p_evidence jsonb,
  p_score smallint,
  p_causality text
) RETURNS SETOF public.adr_information_requests
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_request public.adr_information_requests%ROWTYPE;
  v_assessment public.adr_assessments%ROWTYPE;
  v_now timestamptz := now();
BEGIN
  SELECT * INTO v_request
  FROM public.adr_information_requests
  WHERE id = p_request_id
  FOR UPDATE;

  IF NOT FOUND OR v_request.patient_id <> p_patient_id THEN
    RAISE EXCEPTION 'ADR information request not found' USING ERRCODE = 'P0002';
  END IF;
  IF v_request.status <> 'pending' THEN
    RAISE EXCEPTION 'ADR information request has already been completed'
      USING ERRCODE = '23514';
  END IF;

  SELECT * INTO v_assessment
  FROM public.adr_assessments
  WHERE id = v_request.adr_assessment_id
  FOR UPDATE;
  IF NOT FOUND OR v_assessment.status <> 'draft' THEN
    RAISE EXCEPTION 'ADR assessment is no longer awaiting information'
      USING ERRCODE = '23514';
  END IF;

  IF jsonb_typeof(p_responses) <> 'array'
    OR jsonb_array_length(p_responses) <> jsonb_array_length(v_request.requested_information)
    OR jsonb_typeof(p_naranjo_answers) <> 'object'
    OR jsonb_typeof(p_naranjo_assessment) <> 'object'
    OR jsonb_typeof(p_evidence) <> 'array'
    OR p_score NOT BETWEEN -4 AND 13
  THEN
    RAISE EXCEPTION 'Invalid ADR information response payload' USING ERRCODE = '22023';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM jsonb_array_elements(p_responses) response
    WHERE response->>'question' NOT IN (
      SELECT jsonb_array_elements_text(v_request.requested_information)
    )
      OR response->>'answer' NOT IN ('yes', 'no', 'do_not_know')
      OR (
        response->>'answer' <> 'do_not_know'
        AND NULLIF(btrim(response->>'evidence'), '') IS NULL
      )
  ) OR (
    SELECT count(*) <> count(DISTINCT response->>'question')
    FROM jsonb_array_elements(p_responses) response
  ) THEN
    RAISE EXCEPTION 'Responses must answer each requested question exactly once'
      USING ERRCODE = '22023';
  END IF;

  UPDATE public.adr_information_requests
  SET status = 'answered',
      responses = p_responses,
      resolved_naranjo_score = p_score,
      resolved_causality = p_causality::public.naranjo_causality_enum,
      responded_at = v_now,
      updated_at = v_now
  WHERE id = p_request_id;

  UPDATE public.adr_assessments
  SET naranjo_answers = p_naranjo_answers,
      naranjo_assessment = p_naranjo_assessment,
      evidence = p_evidence,
      naranjo_score = p_score,
      causality = p_causality::public.naranjo_causality_enum,
      updated_at = v_now
  WHERE id = v_request.adr_assessment_id;

  UPDATE public.notifications
  SET is_read = true
  WHERE patient_id = p_patient_id
    AND dedupe_key = 'adr-information-request:' || p_request_id::text;

  INSERT INTO public.adr_assessment_audit_events(
    adr_assessment_id,
    actor_id,
    patient_actor_id,
    event_type,
    event_data
  ) VALUES (
    v_request.adr_assessment_id,
    NULL,
    p_patient_id,
    'patient_information_provided',
    jsonb_build_object(
      'information_request_id', p_request_id,
      'answered_questions', v_request.requested_information,
      'previous_naranjo_score', v_assessment.naranjo_score,
      'naranjo_score', p_score,
      'causality', p_causality
    )
  );

  RETURN QUERY
  SELECT * FROM public.adr_information_requests WHERE id = p_request_id;
END;
$$;

REVOKE ALL ON FUNCTION public.review_adr_assessment(uuid, uuid, text, text, jsonb)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.review_adr_assessment(uuid, uuid, text, text, jsonb)
  TO service_role;

REVOKE ALL ON FUNCTION public.respond_to_adr_information_request(
  uuid, uuid, jsonb, jsonb, jsonb, jsonb, smallint, text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.respond_to_adr_information_request(
  uuid, uuid, jsonb, jsonb, jsonb, jsonb, smallint, text
) TO service_role;

COMMENT ON TABLE public.adr_information_requests IS
  'Auditable clinician-to-patient ADR follow-up requests and confirmed responses.';
COMMENT ON FUNCTION public.respond_to_adr_information_request(
  uuid, uuid, jsonb, jsonb, jsonb, jsonb, smallint, text
) IS 'Atomically records confirmed patient evidence and a deterministic Naranjo rescore.';
