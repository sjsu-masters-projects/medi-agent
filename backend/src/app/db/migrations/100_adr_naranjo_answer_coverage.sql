-- PV-001-D: every Naranjo question that someone can answer has a place to be answered.
--
-- Before this file a case built from a guided symptom report could never score above 4:
-- the patient follow-up asked only three questions and a clinician could record none.
--   * Patients may now also be asked two retrospective questions: whether the symptom
--     started after the medicine was begun (event_after_drug) and whether it improved after
--     the medicine was stopped or paused (improved_on_dechallenge). Both ask only about what
--     already happened; the portal tells the patient not to stop or change a medicine.
--   * An assigned clinician on the owning care team may record answers to the five
--     clinical questions (previous reports, alternative causes, placebo, toxic drug level,
--     objective evidence) on an open assessment. Each answer is evidence with its source,
--     the score is recalculated by the same deterministic rules, and one audit event is
--     written. The weights and thresholds do not change.
--   * The patient answer RPC now refuses a payload built on stale answers or evidence
--     (SQLSTATE 40001), so a clinician answer and a patient answer saved at the same time
--     cannot overwrite each other. The backend reloads and retries once.
--
-- Every redefined function starts from its latest definition (review_adr_assessment 063,
-- moved to private by 087; respond_to_adr_information_request 063) and keeps its
-- signature, so existing callers are unchanged. Both allowlists are supersets, so every
-- existing row still validates.
-- Rollback: restore the 063 bodies of both functions and the 047/064 constraints, then
-- drop public.record_adr_clinician_answers. Recorded answers stay valid Naranjo answers.
-- Written for review; it is applied to a hosted project only on explicit authorization.

-- 1. Allowlists.
ALTER TABLE public.adr_information_requests
  DROP CONSTRAINT adr_information_requests_patient_safe_questions,
  ADD CONSTRAINT adr_information_requests_patient_safe_questions
    CHECK (
      requested_information <@ '[
        "event_after_drug", "improved_on_dechallenge", "reappeared_on_rechallenge",
        "dose_response", "similar_previous_reaction"
      ]'::jsonb
      AND jsonb_array_length(requested_information) > 0
    );

ALTER TABLE public.adr_assessment_audit_events
  DROP CONSTRAINT adr_assessment_audit_events_event_type_check,
  ADD CONSTRAINT adr_assessment_audit_events_event_type_check CHECK (event_type IN (
    'marked_reviewed', 'dismissed', 'information_requested',
    'patient_information_provided', 'medwatch_draft_discarded',
    'clinician_naranjo_answers_recorded'));

-- 2. Review: the 063 body (in private since 087) with the five patient questions.
CREATE OR REPLACE FUNCTION private.review_adr_assessment(
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
      v_requested_information <@ '[
        "event_after_drug", "improved_on_dechallenge", "reappeared_on_rechallenge",
        "dose_response", "similar_previous_reaction"
      ]'::jsonb
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

  -- The request insert captures the patient's bilingual notification item.
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

-- 3. Patient answers: the 063 body plus the stale-payload guard.
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
  v_answered text[];
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

  -- PV-001-D: a clinician can now record answers on the same assessment. The backend
  -- builds this payload from the answers and evidence it read before the call, so it must
  -- still describe the stored assessment: every answer outside this response unchanged,
  -- each answered question set to its response, and every stored evidence entry kept.
  -- Otherwise a concurrent write landed in between; the backend reloads and retries.
  SELECT array_agg(response->>'question') INTO v_answered
  FROM jsonb_array_elements(p_responses) response;
  IF (p_naranjo_answers - v_answered) IS DISTINCT FROM (v_assessment.naranjo_answers - v_answered)
    OR EXISTS (
      SELECT 1
      FROM jsonb_array_elements(p_responses) response
      WHERE p_naranjo_answers->>(response->>'question') IS DISTINCT FROM response->>'answer'
    )
    OR NOT (p_evidence @> v_assessment.evidence)
  THEN
    RAISE EXCEPTION 'ADR assessment changed; reload before answering'
      USING ERRCODE = '40001';
  END IF;

  -- Captures the clinicians' "patient answered" item (063).
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

  -- Requests made before 063 may still have a legacy row; none is created after it.
  UPDATE public.notifications
  SET is_read = true
  WHERE patient_id = p_patient_id
    AND dedupe_key = 'adr-information-request:' || p_request_id::text;

  -- Deliver anything still pending to the patient, then mark this request's item read:
  -- the item captured from the request, or one captured from the assessment for it
  -- before 063. Earlier requests' items keep their unread state.
  PERFORM private.notification_prepare(p_patient_id, 'patient');
  WITH marked AS (
    UPDATE public.notification_receipts r
    SET read_at = clock_timestamp()
    FROM public.notification_events e
    WHERE e.id = r.event_id
      AND r.recipient_id = p_patient_id
      AND r.recipient_role = 'patient'
      AND r.read_at IS NULL
      AND e.patient_id = p_patient_id
      AND e.event_type = 'adr_information_requested'
      AND (
        (e.source_type = 'adr_information_requests' AND e.source_id = p_request_id)
        OR (
          e.source_type = 'adr_assessments'
          AND e.source_id = v_request.adr_assessment_id
          AND e.created_at >= v_request.created_at
        )
      )
    RETURNING r.id
  )
  INSERT INTO public.notification_read_audit(receipt_id, actor_id, action)
  SELECT id, p_patient_id, 'read' FROM marked
  ON CONFLICT DO NOTHING;

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

-- 4. Clinician answers. The backend scores the merged answers with the shared Naranjo
-- rules and sends the result; this function checks that the answers are exactly the
-- stored ones with the recorded questions replaced, builds the evidence entries itself
-- and writes the audit event, all under the assessment row lock. The acting team and
-- owner rule are those of the 087 review wrapper.
CREATE FUNCTION public.record_adr_clinician_answers(
  p_assessment_id uuid,
  p_actor_id uuid,
  p_answers jsonb,
  p_naranjo_answers jsonb,
  p_naranjo_assessment jsonb,
  p_score smallint,
  p_causality text,
  p_care_team_id uuid DEFAULT NULL
) RETURNS SETOF public.adr_assessments
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_assessment public.adr_assessments%ROWTYPE;
  v_team uuid;
  v_questions text[];
  v_entries jsonb;
  v_now timestamptz := now();
BEGIN
  SELECT * INTO v_assessment
  FROM public.adr_assessments
  WHERE id = p_assessment_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'ADR assessment not found' USING ERRCODE = 'P0002';
  END IF;

  v_team := private.resolve_acting_team(p_actor_id, v_assessment.patient_id, p_care_team_id);
  -- Once a team has taken the assessment up, only that team continues it (087).
  IF v_assessment.reviewed_by IS NOT NULL
     AND v_assessment.reviewed_by_care_team_id IS DISTINCT FROM v_team THEN
    RAISE EXCEPTION 'ADR assessment unavailable' USING ERRCODE = '42501';
  END IF;
  IF v_assessment.status <> 'draft' THEN
    RAISE EXCEPTION 'ADR assessment review has already been completed'
      USING ERRCODE = '23514';
  END IF;

  IF jsonb_typeof(p_answers) IS DISTINCT FROM 'array'
    OR jsonb_array_length(p_answers) NOT BETWEEN 1 AND 5
    OR jsonb_typeof(p_naranjo_answers) IS DISTINCT FROM 'object'
    OR jsonb_typeof(p_naranjo_assessment) IS DISTINCT FROM 'object'
    OR p_score IS NULL
    OR p_score NOT BETWEEN -4 AND 13
    OR p_causality IS NULL
  THEN
    RAISE EXCEPTION 'Invalid clinician Naranjo answer payload' USING ERRCODE = '22023';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM jsonb_array_elements(p_answers) answer
    WHERE jsonb_typeof(answer) <> 'object'
      OR COALESCE(answer->>'question', '') NOT IN (
        'previous_reports', 'alternative_causes', 'reappeared_with_placebo',
        'toxic_drug_concentration', 'objective_evidence'
      )
      OR COALESCE(answer->>'answer', '') NOT IN ('yes', 'no', 'do_not_know')
      OR (
        answer->>'answer' <> 'do_not_know'
        AND NULLIF(btrim(COALESCE(answer->>'basis', '')), '') IS NULL
      )
      OR char_length(COALESCE(answer->>'basis', '')) > 500
  ) OR (
    SELECT count(*) <> count(DISTINCT answer->>'question')
    FROM jsonb_array_elements(p_answers) answer
  ) THEN
    RAISE EXCEPTION 'Only clinician-answerable Naranjo questions, each once, may be recorded'
      USING ERRCODE = '22023';
  END IF;

  SELECT array_agg(answer->>'question') INTO v_questions
  FROM jsonb_array_elements(p_answers) answer;
  IF (p_naranjo_answers - v_questions) IS DISTINCT FROM (v_assessment.naranjo_answers - v_questions)
    OR EXISTS (
      SELECT 1
      FROM jsonb_array_elements(p_answers) answer
      WHERE p_naranjo_answers->>(answer->>'question') IS DISTINCT FROM answer->>'answer'
    )
  THEN
    RAISE EXCEPTION 'ADR assessment changed; reload before recording answers'
      USING ERRCODE = '40001';
  END IF;

  SELECT jsonb_agg(
    jsonb_strip_nulls(jsonb_build_object(
      'question', answer->>'question',
      'answer', answer->>'answer',
      'evidence', NULLIF(btrim(COALESCE(answer->>'basis', '')), ''),
      'source', 'clinician_entry',
      'recorded_by', p_actor_id,
      'care_team_id', v_team,
      'recorded_at', v_now
    ))
    ORDER BY ordinality
  ) INTO v_entries
  FROM jsonb_array_elements(p_answers) WITH ORDINALITY AS item(answer, ordinality);

  UPDATE public.adr_assessments
  SET naranjo_answers = p_naranjo_answers,
      naranjo_assessment = p_naranjo_assessment,
      evidence = v_assessment.evidence || v_entries,
      naranjo_score = p_score,
      causality = p_causality::public.naranjo_causality_enum,
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
    'clinician_naranjo_answers_recorded',
    jsonb_build_object(
      'care_team_id', v_team,
      'questions', to_jsonb(v_questions),
      'previous_answers', (
        SELECT COALESCE(jsonb_object_agg(question, v_assessment.naranjo_answers->question), '{}'::jsonb)
        FROM unnest(v_questions) AS question
        WHERE v_assessment.naranjo_answers ? question
      ),
      'answers', (
        SELECT jsonb_object_agg(question, p_naranjo_answers->question)
        FROM unnest(v_questions) AS question
      ),
      'previous_naranjo_score', v_assessment.naranjo_score,
      'naranjo_score', p_score,
      'causality', p_causality
    )
  );

  RETURN QUERY
  SELECT * FROM public.adr_assessments WHERE id = p_assessment_id;
END;
$$;

-- 5. Grants. The two redefined functions keep their privileges; restated for the new one.
REVOKE ALL ON FUNCTION public.record_adr_clinician_answers(
  uuid, uuid, jsonb, jsonb, jsonb, smallint, text, uuid
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_adr_clinician_answers(
  uuid, uuid, jsonb, jsonb, jsonb, smallint, text, uuid
) TO service_role;

-- 6. Fail the migration rather than leave a browser role able to record answers.
DO $$
BEGIN
  IF has_function_privilege('anon',
       'public.record_adr_clinician_answers(uuid, uuid, jsonb, jsonb, jsonb, smallint, text, uuid)',
       'EXECUTE')
     OR has_function_privilege('authenticated',
       'public.record_adr_clinician_answers(uuid, uuid, jsonb, jsonb, jsonb, smallint, text, uuid)',
       'EXECUTE') THEN
    RAISE EXCEPTION 'record_adr_clinician_answers must not be executable by browser roles';
  END IF;
END;
$$;
