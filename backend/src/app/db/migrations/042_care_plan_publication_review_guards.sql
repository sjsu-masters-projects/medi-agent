-- PAT-005: require a reviewed patient locale and an explicit medication projection
-- decision before the atomic publication operation can change canonical truth.
ALTER TABLE public.care_plan_items ADD COLUMN reviewed_locale text;
ALTER TABLE public.care_plan_items ADD CONSTRAINT care_plan_items_reviewed_locale_check
  CHECK (reviewed_locale IS NULL OR reviewed_locale IN ('en-US', 'es-MX'));

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
  v_locale text;
  v_target_id uuid;
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
  SELECT COALESCE(NULLIF(preferred_language::text, ''), 'en-US') INTO v_locale
  FROM public.patients WHERE id = v_plan.patient_id FOR UPDATE;
  IF v_locale IS NULL OR EXISTS (
    SELECT 1 FROM public.care_plan_items
    WHERE plan_version_id = p_plan_version_id AND NOT is_removed
      AND reviewed_locale IS DISTINCT FROM v_locale
  ) THEN
    RAISE EXCEPTION 'all patient-facing items need current-locale review';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.care_plan_items
    WHERE plan_version_id = p_plan_version_id AND NOT is_removed
      AND blocker_reason IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'all care-plan blockers must be resolved before approval';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.care_plan_items
    WHERE plan_version_id = p_plan_version_id AND category = 'medication' AND NOT is_removed
      AND medication->>'decision' = 'update'
    GROUP BY medication->>'target_id' HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'two plan items cannot update one medication';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.care_plan_items
    WHERE plan_version_id = p_plan_version_id AND category = 'medication' AND NOT is_removed
      AND medication->>'decision' = 'create'
    GROUP BY lower(trim(medication->>'name')) HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'two plan items cannot create the same medication';
  END IF;
  -- Validate against current canonical state while the plan is still a draft.
  -- Any failure occurs before recommendation, supersession, or projection writes.
  FOR v_item IN SELECT * FROM public.care_plan_items
    WHERE plan_version_id = p_plan_version_id AND category = 'medication' AND NOT is_removed
  LOOP
    IF trim(v_item.frequency) IS DISTINCT FROM trim(v_item.medication->>'frequency') THEN
      RAISE EXCEPTION 'medication frequency must match the patient-facing item';
    END IF;
    IF v_item.medication->>'decision' = 'create'
       AND NULLIF(v_item.medication->>'target_id', '') IS NULL THEN
      IF EXISTS (
        SELECT 1 FROM public.medications
        WHERE patient_id = v_plan.patient_id AND is_active
          AND lower(trim(name)) = lower(trim(v_item.medication->>'name'))
      ) THEN
        RAISE EXCEPTION 'active medication already exists; choose an update decision';
      END IF;
    ELSIF v_item.medication->>'decision' = 'update'
      AND NULLIF(v_item.medication->>'target_id', '') IS NOT NULL THEN
      v_target_id := (v_item.medication->>'target_id')::uuid;
      PERFORM 1 FROM public.medications
      WHERE id = v_target_id AND patient_id = v_plan.patient_id AND is_active
        AND lower(trim(name)) = lower(trim(v_item.medication->>'name')) FOR UPDATE;
      IF NOT FOUND THEN
        RAISE EXCEPTION 'medication update target is not an active matching patient record';
      END IF;
    ELSE
      RAISE EXCEPTION 'medication projection needs an explicit create or update decision';
    END IF;
  END LOOP;
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
      IF v_item.medication->>'decision' = 'update' THEN
        UPDATE public.medications SET
          name = v_item.medication->>'name', dosage = v_item.medication->>'dosage',
          frequency = v_item.medication->>'frequency', route = v_route,
          instructions = v_item.instructions, is_active = true, care_plan_item_id = v_item.id
        WHERE id = (v_item.medication->>'target_id')::uuid AND patient_id = v_plan.patient_id
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
    jsonb_build_object('recommendation_id', v_recommendation_id, 'reviewed_locale', v_locale));
  RETURN jsonb_build_object('plan_version_id', v_plan.id, 'recommendation_id', v_recommendation_id,
    'status', 'approved');
END;
$$;

REVOKE ALL ON FUNCTION public.approve_care_plan_version(uuid, uuid, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.approve_care_plan_version(uuid, uuid, text) TO service_role;
