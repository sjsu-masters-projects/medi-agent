-- PAT-005: clinician-approved care plans are immutable versions.  The model may
-- create a draft, but only this explicitly authorized publication transaction
-- can project plan items into medications or obligations visible to a patient.

CREATE TABLE public.care_plan_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL REFERENCES public.patients(id) ON DELETE CASCADE,
  version_number integer NOT NULL CHECK (version_number > 0),
  status text NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'approved', 'superseded', 'rejected', 'generation_failed')),
  source_watermark timestamptz NOT NULL DEFAULT now(),
  generated_at timestamptz,
  generation_error_code text,
  recommendation_id uuid UNIQUE REFERENCES public.clinical_recommendations(id) ON DELETE RESTRICT,
  approved_by uuid REFERENCES public.clinicians(id) ON DELETE RESTRICT,
  approved_at timestamptz,
  superseded_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (patient_id, version_number),
  CHECK ((status = 'approved' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)
    OR status <> 'approved')
);

CREATE TRIGGER care_plan_versions_updated_at
  BEFORE UPDATE ON public.care_plan_versions
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

CREATE UNIQUE INDEX care_plan_versions_one_open_draft
  ON public.care_plan_versions(patient_id)
  WHERE status = 'draft';
CREATE INDEX care_plan_versions_patient_status
  ON public.care_plan_versions(patient_id, status, version_number DESC);

CREATE TABLE public.care_plan_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_version_id uuid NOT NULL REFERENCES public.care_plan_versions(id) ON DELETE CASCADE,
  source_fact_id uuid REFERENCES public.clinical_facts(id) ON DELETE RESTRICT,
  category text NOT NULL CHECK (category IN (
    'medication', 'movement', 'nutrition', 'hydration', 'monitoring', 'follow_up', 'other'
  )),
  title text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 300),
  instructions text NOT NULL CHECK (char_length(instructions) BETWEEN 1 AND 2000),
  frequency text NOT NULL CHECK (char_length(frequency) BETWEEN 1 AND 200),
  schedule jsonb NOT NULL DEFAULT '{}'::jsonb,
  medication jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence_score numeric(4,3) CHECK (confidence_score >= 0 AND confidence_score <= 1),
  uncertainty jsonb NOT NULL DEFAULT '[]'::jsonb,
  conflict jsonb NOT NULL DEFAULT '{}'::jsonb,
  blocker_reason text,
  is_removed boolean NOT NULL DEFAULT false,
  projection_type adherence_target_type_enum,
  projection_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(schedule) = 'object' AND jsonb_typeof(medication) = 'object')
);

CREATE TRIGGER care_plan_items_updated_at
  BEFORE UPDATE ON public.care_plan_items
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

CREATE INDEX care_plan_items_plan_active
  ON public.care_plan_items(plan_version_id, is_removed);
CREATE INDEX care_plan_items_source_fact ON public.care_plan_items(source_fact_id)
  WHERE source_fact_id IS NOT NULL;

CREATE TABLE public.care_plan_generation_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL REFERENCES public.patients(id) ON DELETE CASCADE,
  source_watermark timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'processing', 'retry', 'completed', 'failed')),
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0 AND attempts <= 3),
  requested_at timestamptz NOT NULL DEFAULT now(),
  next_attempt_at timestamptz,
  claimed_at timestamptz,
  completed_at timestamptz,
  plan_version_id uuid REFERENCES public.care_plan_versions(id) ON DELETE SET NULL,
  failure_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER care_plan_generation_requests_updated_at
  BEFORE UPDATE ON public.care_plan_generation_requests
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

CREATE UNIQUE INDEX care_plan_generation_requests_one_open
  ON public.care_plan_generation_requests(patient_id)
  WHERE status IN ('pending', 'processing', 'retry');
CREATE INDEX care_plan_generation_requests_claimable
  ON public.care_plan_generation_requests(status, next_attempt_at, requested_at)
  WHERE status IN ('pending', 'retry');

CREATE TABLE public.care_plan_audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_version_id uuid NOT NULL REFERENCES public.care_plan_versions(id) ON DELETE RESTRICT,
  actor_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  event_type text NOT NULL CHECK (char_length(event_type) BETWEEN 1 AND 100),
  event_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX care_plan_audit_events_version ON public.care_plan_audit_events(plan_version_id, created_at);

ALTER TABLE public.medications
  ADD COLUMN IF NOT EXISTS care_plan_item_id uuid REFERENCES public.care_plan_items(id) ON DELETE SET NULL;
ALTER TABLE public.obligations
  ADD COLUMN IF NOT EXISTS care_plan_item_id uuid REFERENCES public.care_plan_items(id) ON DELETE SET NULL;
CREATE UNIQUE INDEX medications_care_plan_item ON public.medications(care_plan_item_id)
  WHERE care_plan_item_id IS NOT NULL;
CREATE UNIQUE INDEX obligations_care_plan_item ON public.obligations(care_plan_item_id)
  WHERE care_plan_item_id IS NOT NULL;

ALTER TABLE public.adherence_logs
  ADD COLUMN IF NOT EXISTS barrier_code text;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'adherence_logs_barrier_code_check') THEN
    ALTER TABLE public.adherence_logs ADD CONSTRAINT adherence_logs_barrier_code_check
      CHECK (barrier_code IS NULL OR barrier_code IN (
        'side_effects', 'cost', 'access', 'schedule', 'confusion', 'other'
      ));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'adherence_logs_barrier_note_check') THEN
    ALTER TABLE public.adherence_logs ADD CONSTRAINT adherence_logs_barrier_note_check
      CHECK (barrier_code <> 'other' OR char_length(trim(COALESCE(notes, ''))) > 0);
  END IF;
END;
$$;

ALTER TABLE public.care_plan_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.care_plan_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.care_plan_generation_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.care_plan_audit_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY care_plan_versions_patient_select ON public.care_plan_versions
  FOR SELECT USING (patient_id = auth.uid() AND status IN ('approved', 'superseded'));
CREATE POLICY care_plan_versions_clinician_select ON public.care_plan_versions
  FOR SELECT USING (public.is_clinician() AND public.is_assigned_clinician(patient_id));
CREATE POLICY care_plan_items_patient_select ON public.care_plan_items
  FOR SELECT USING (EXISTS (
    SELECT 1 FROM public.care_plan_versions v
    WHERE v.id = care_plan_items.plan_version_id
      AND v.patient_id = auth.uid() AND v.status IN ('approved', 'superseded')
  ));
CREATE POLICY care_plan_items_clinician_select ON public.care_plan_items
  FOR SELECT USING (EXISTS (
    SELECT 1 FROM public.care_plan_versions v
    WHERE v.id = care_plan_items.plan_version_id
      AND public.is_clinician() AND public.is_assigned_clinician(v.patient_id)
  ));
CREATE POLICY care_plan_generation_requests_clinician_select ON public.care_plan_generation_requests
  FOR SELECT USING (public.is_clinician() AND public.is_assigned_clinician(patient_id));
CREATE POLICY care_plan_audit_events_clinician_select ON public.care_plan_audit_events
  FOR SELECT USING (EXISTS (
    SELECT 1 FROM public.care_plan_versions v
    WHERE v.id = care_plan_audit_events.plan_version_id
      AND public.is_clinician() AND public.is_assigned_clinician(v.patient_id)
  ));

CREATE OR REPLACE FUNCTION public.request_care_plan_generation(
  p_patient_id uuid,
  p_source_watermark timestamptz
) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE v_request public.care_plan_generation_requests%ROWTYPE;
BEGIN
  SELECT * INTO v_request FROM public.care_plan_generation_requests
  WHERE patient_id = p_patient_id AND status IN ('pending', 'processing', 'retry')
  FOR UPDATE;
  IF FOUND THEN
    UPDATE public.care_plan_generation_requests
    SET source_watermark = GREATEST(source_watermark, p_source_watermark),
        status = 'pending', requested_at = now(), next_attempt_at = NULL,
        claimed_at = NULL, failure_code = NULL
    WHERE id = v_request.id
    RETURNING * INTO v_request;
  ELSE
    INSERT INTO public.care_plan_generation_requests(patient_id, source_watermark)
    VALUES (p_patient_id, p_source_watermark) RETURNING * INTO v_request;
  END IF;
  RETURN jsonb_build_object('request_id', v_request.id, 'status', v_request.status);
END;
$$;

CREATE OR REPLACE FUNCTION public.claim_pending_care_plan_generation(p_limit integer DEFAULT 10)
RETURNS SETOF jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE v_request public.care_plan_generation_requests%ROWTYPE;
BEGIN
  UPDATE public.care_plan_generation_requests
  SET status = 'retry', next_attempt_at = now(), claimed_at = NULL,
      failure_code = 'worker_lease_expired'
  WHERE status = 'processing' AND claimed_at < now() - interval '15 minutes';

  FOR v_request IN
    SELECT * FROM public.care_plan_generation_requests
    WHERE status IN ('pending', 'retry')
      AND requested_at <= now() - interval '5 minutes'
      AND (next_attempt_at IS NULL OR next_attempt_at <= now())
    ORDER BY requested_at ASC
    FOR UPDATE SKIP LOCKED LIMIT LEAST(GREATEST(p_limit, 1), 100)
  LOOP
    IF v_request.attempts >= 3 THEN
      UPDATE public.care_plan_generation_requests
      SET status = 'failed', failure_code = 'attempt_limit_reached', completed_at = now()
      WHERE id = v_request.id;
      CONTINUE;
    END IF;
    UPDATE public.care_plan_generation_requests
    SET status = 'processing', attempts = attempts + 1, claimed_at = now(),
        next_attempt_at = NULL, failure_code = NULL
    WHERE id = v_request.id;
    RETURN NEXT jsonb_build_object(
      'request_id', v_request.id, 'patient_id', v_request.patient_id,
      'source_watermark', v_request.source_watermark, 'attempt', v_request.attempts + 1
    );
  END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION public.approve_care_plan_version(
  p_plan_version_id uuid,
  p_reviewer_id uuid,
  p_note text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE
  v_plan public.care_plan_versions%ROWTYPE;
  v_old_plan public.care_plan_versions%ROWTYPE;
  v_item public.care_plan_items%ROWTYPE;
  v_recommendation_id uuid;
  v_care_team_id uuid;
  v_projection_id uuid;
  v_evidence jsonb;
  v_route public.medication_route_enum;
BEGIN
  SELECT * INTO v_plan FROM public.care_plan_versions WHERE id = p_plan_version_id FOR UPDATE;
  IF NOT FOUND OR v_plan.status <> 'draft' THEN
    RAISE EXCEPTION 'care plan draft is not eligible for approval';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.care_teams
    WHERE clinician_id = p_reviewer_id AND patient_id = v_plan.patient_id AND status = 'active'
  ) THEN
    RAISE EXCEPTION 'clinician is not assigned to patient';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.care_plan_items
    WHERE plan_version_id = p_plan_version_id AND NOT is_removed
      AND blocker_reason IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'all care-plan blockers must be resolved before approval';
  END IF;
  SELECT jsonb_agg(jsonb_build_object('fact_id', source_fact_id)) INTO v_evidence
  FROM public.care_plan_items
  WHERE plan_version_id = p_plan_version_id AND NOT is_removed AND source_fact_id IS NOT NULL;
  IF v_evidence IS NULL OR jsonb_array_length(v_evidence) = 0 THEN
    RAISE EXCEPTION 'care plan needs evidence-backed items before approval';
  END IF;
  SELECT id INTO v_care_team_id FROM public.care_teams
  WHERE clinician_id = p_reviewer_id AND patient_id = v_plan.patient_id AND status = 'active'
  ORDER BY created_at ASC LIMIT 1;

  INSERT INTO public.clinical_recommendations(
    patient_id, action_type, proposed_payload, evidence, rationale, proposer_type, proposer_reference, state
  ) VALUES (
    v_plan.patient_id, 'publish_care_plan', jsonb_build_object('plan_version_id', v_plan.id),
    v_evidence, 'Evidence-backed care plan draft awaiting assigned clinician approval.',
    'document_evidence_agent', v_plan.id::text, 'executed'
  ) RETURNING id INTO v_recommendation_id;
  INSERT INTO public.approval_decisions(recommendation_id, reviewer_id, decision, note, edited_payload)
  VALUES (v_recommendation_id, p_reviewer_id, 'approve', p_note,
    jsonb_build_object('plan_version_id', v_plan.id, 'version_number', v_plan.version_number));
  INSERT INTO public.clinical_action_audit_records(recommendation_id, actor_id, event_type, event_data)
  VALUES
    (v_recommendation_id, NULL, 'proposed', jsonb_build_object('proposer_type', 'document_evidence_agent')),
    (v_recommendation_id, p_reviewer_id, 'approved', jsonb_build_object('plan_version_id', v_plan.id)),
    (v_recommendation_id, p_reviewer_id, 'executed', jsonb_build_object('plan_version_id', v_plan.id));

  SELECT * INTO v_old_plan FROM public.care_plan_versions
  WHERE patient_id = v_plan.patient_id AND status = 'approved' FOR UPDATE;
  IF FOUND THEN
    UPDATE public.medications SET is_active = false
    WHERE care_plan_item_id IN (SELECT id FROM public.care_plan_items WHERE plan_version_id = v_old_plan.id);
    UPDATE public.obligations SET is_active = false
    WHERE care_plan_item_id IN (SELECT id FROM public.care_plan_items WHERE plan_version_id = v_old_plan.id);
    UPDATE public.care_plan_versions SET status = 'superseded', superseded_at = now()
    WHERE id = v_old_plan.id;
  END IF;

  FOR v_item IN SELECT * FROM public.care_plan_items
    WHERE plan_version_id = v_plan.id AND NOT is_removed ORDER BY created_at
  LOOP
    IF v_item.category = 'medication' THEN
      IF lower(COALESCE(v_item.medication->>'route', '')) NOT IN (
        'oral', 'topical', 'inhaled', 'iv', 'im', 'subcutaneous'
      ) THEN
        RAISE EXCEPTION 'medication route is required and must be supported before approval';
      END IF;
      v_route := CASE lower(v_item.medication->>'route')
        WHEN 'oral' THEN 'oral'::public.medication_route_enum
        WHEN 'topical' THEN 'topical'::public.medication_route_enum
        WHEN 'inhaled' THEN 'inhaled'::public.medication_route_enum
        WHEN 'iv' THEN 'iv'::public.medication_route_enum
        WHEN 'im' THEN 'im'::public.medication_route_enum
        WHEN 'subcutaneous' THEN 'subcutaneous'::public.medication_route_enum
        ELSE NULL
      END;
      IF NULLIF(v_item.medication->>'target_id', '') IS NOT NULL AND EXISTS (
        SELECT 1 FROM public.medications WHERE id = (v_item.medication->>'target_id')::uuid
          AND patient_id = v_plan.patient_id
      ) THEN
        UPDATE public.medications SET
          name = COALESCE(NULLIF(v_item.medication->>'name', ''), name),
          dosage = COALESCE(NULLIF(v_item.medication->>'dosage', ''), dosage),
          frequency = COALESCE(NULLIF(v_item.medication->>'frequency', ''), frequency),
          route = v_route, instructions = v_item.instructions,
          is_active = true, care_plan_item_id = v_item.id
        WHERE id = (v_item.medication->>'target_id')::uuid
        RETURNING id INTO v_projection_id;
      ELSE
        INSERT INTO public.medications(
          patient_id, name, dosage, frequency, route, instructions,
          prescribed_by_care_team_id, start_date, end_date, is_active, care_plan_item_id
        ) VALUES (
          v_plan.patient_id, v_item.medication->>'name', v_item.medication->>'dosage',
          v_item.medication->>'frequency', v_route, v_item.instructions, v_care_team_id,
          NULLIF(v_item.schedule->>'start_date', '')::date,
          NULLIF(v_item.schedule->>'end_date', '')::date, true, v_item.id
        ) RETURNING id INTO v_projection_id;
      END IF;
      UPDATE public.care_plan_items SET projection_type = 'medication', projection_id = v_projection_id
      WHERE id = v_item.id;
    ELSE
      INSERT INTO public.obligations(
        patient_id, obligation_type, description, frequency, notes, set_by_care_team_id,
        is_active, care_plan_item_id
      ) VALUES (
        v_plan.patient_id,
        CASE v_item.category WHEN 'nutrition' THEN 'diet'::public.obligation_type_enum
          WHEN 'movement' THEN 'exercise'::public.obligation_type_enum
          ELSE 'custom'::public.obligation_type_enum END,
        v_item.title, v_item.frequency, v_item.instructions, v_care_team_id, true, v_item.id
      ) RETURNING id INTO v_projection_id;
      UPDATE public.care_plan_items SET projection_type = 'obligation', projection_id = v_projection_id
      WHERE id = v_item.id;
    END IF;
  END LOOP;

  UPDATE public.care_plan_versions SET status = 'approved', approved_by = p_reviewer_id,
    approved_at = now(), recommendation_id = v_recommendation_id WHERE id = v_plan.id;
  INSERT INTO public.care_plan_audit_events(plan_version_id, actor_id, event_type, event_data)
  VALUES (v_plan.id, p_reviewer_id, 'approved_and_published',
    jsonb_build_object('recommendation_id', v_recommendation_id));
  RETURN jsonb_build_object('plan_version_id', v_plan.id, 'recommendation_id', v_recommendation_id,
    'status', 'approved');
END;
$$;

REVOKE ALL ON FUNCTION public.request_care_plan_generation(uuid, timestamptz)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_pending_care_plan_generation(integer)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.approve_care_plan_version(uuid, uuid, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.request_care_plan_generation(uuid, timestamptz) TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_pending_care_plan_generation(integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.approve_care_plan_version(uuid, uuid, text) TO service_role;
GRANT SELECT ON public.care_plan_versions, public.care_plan_items,
  public.care_plan_generation_requests, public.care_plan_audit_events TO authenticated, service_role;
GRANT INSERT, UPDATE, DELETE ON public.care_plan_versions, public.care_plan_items,
  public.care_plan_generation_requests, public.care_plan_audit_events TO service_role;
