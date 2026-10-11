-- LOC-001: patient-facing care-plan wording is reviewed and approved in en-US and es-MX
-- together. Approved and superseded versions are not rewritten; only new drafts carry
-- bilingual wording, and approval projects it for the patient's current language.

-- Complete means both languages are present and the source language matches the
-- item's own columns, which medication reconciliation and continuity still compare.
CREATE FUNCTION private.care_plan_wording_is_complete(
  p_wording jsonb, p_source_locale text, p_title text, p_instructions text, p_frequency text
) RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
  SELECT p_source_locale IN ('en-US', 'es-MX')
    AND NOT EXISTS (
      SELECT 1 FROM unnest(ARRAY['en-US', 'es-MX']) AS locale(code)
      WHERE NULLIF(btrim(p_wording #>> ARRAY[locale.code, 'title']), '') IS NULL
        OR NULLIF(btrim(p_wording #>> ARRAY[locale.code, 'instructions']), '') IS NULL
        OR NULLIF(btrim(p_wording #>> ARRAY[locale.code, 'frequency']), '') IS NULL)
    AND btrim(p_wording #>> ARRAY[p_source_locale, 'title']) = btrim(p_title)
    AND btrim(p_wording #>> ARRAY[p_source_locale, 'instructions']) = btrim(p_instructions)
    AND btrim(p_wording #>> ARRAY[p_source_locale, 'frequency']) = btrim(p_frequency);
$$;

ALTER TABLE public.care_plan_items
  ADD COLUMN source_locale text
    CHECK (source_locale IS NULL OR source_locale IN ('en-US', 'es-MX')),
  -- {"en-US": {title, instructions, frequency}, "es-MX": {...}}; plain expressions so
  -- any role allowed to write these tables can satisfy the check.
  ADD COLUMN wording jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(wording) = 'object'
      AND (wording - 'en-US' - 'es-MX') = '{}'::jsonb
      AND COALESCE(jsonb_typeof(wording->'en-US'), 'object') = 'object'
      AND (COALESCE(wording->'en-US', '{}'::jsonb) - 'title' - 'instructions' - 'frequency') = '{}'::jsonb
      AND char_length(COALESCE(wording #>> '{en-US,title}', '')) <= 300
      AND char_length(COALESCE(wording #>> '{en-US,instructions}', '')) <= 2000
      AND char_length(COALESCE(wording #>> '{en-US,frequency}', '')) <= 200
      AND COALESCE(jsonb_typeof(wording->'es-MX'), 'object') = 'object'
      AND (COALESCE(wording->'es-MX', '{}'::jsonb) - 'title' - 'instructions' - 'frequency') = '{}'::jsonb
      AND char_length(COALESCE(wording #>> '{es-MX,title}', '')) <= 300
      AND char_length(COALESCE(wording #>> '{es-MX,instructions}', '')) <= 2000
      AND char_length(COALESCE(wording #>> '{es-MX,frequency}', '')) <= 200),
  ADD COLUMN wording_origin jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(wording_origin) = 'object'
      AND (wording_origin - 'en-US' - 'es-MX') = '{}'::jsonb),
  ADD COLUMN wording_verified boolean NOT NULL DEFAULT false;

-- Projection copies written only by approval. Empty means legacy single-language text.
ALTER TABLE public.medications ADD COLUMN patient_wording jsonb NOT NULL DEFAULT '{}'::jsonb
  CHECK (jsonb_typeof(patient_wording) = 'object'
      AND (patient_wording - 'en-US' - 'es-MX') = '{}'::jsonb
      AND COALESCE(jsonb_typeof(patient_wording->'en-US'), 'object') = 'object'
      AND (COALESCE(patient_wording->'en-US', '{}'::jsonb) - 'title' - 'instructions' - 'frequency') = '{}'::jsonb
      AND char_length(COALESCE(patient_wording #>> '{en-US,title}', '')) <= 300
      AND char_length(COALESCE(patient_wording #>> '{en-US,instructions}', '')) <= 2000
      AND char_length(COALESCE(patient_wording #>> '{en-US,frequency}', '')) <= 200
      AND COALESCE(jsonb_typeof(patient_wording->'es-MX'), 'object') = 'object'
      AND (COALESCE(patient_wording->'es-MX', '{}'::jsonb) - 'title' - 'instructions' - 'frequency') = '{}'::jsonb
      AND char_length(COALESCE(patient_wording #>> '{es-MX,title}', '')) <= 300
      AND char_length(COALESCE(patient_wording #>> '{es-MX,instructions}', '')) <= 2000
      AND char_length(COALESCE(patient_wording #>> '{es-MX,frequency}', '')) <= 200);
ALTER TABLE public.obligations ADD COLUMN patient_wording jsonb NOT NULL DEFAULT '{}'::jsonb
  CHECK (jsonb_typeof(patient_wording) = 'object'
      AND (patient_wording - 'en-US' - 'es-MX') = '{}'::jsonb
      AND COALESCE(jsonb_typeof(patient_wording->'en-US'), 'object') = 'object'
      AND (COALESCE(patient_wording->'en-US', '{}'::jsonb) - 'title' - 'instructions' - 'frequency') = '{}'::jsonb
      AND char_length(COALESCE(patient_wording #>> '{en-US,title}', '')) <= 300
      AND char_length(COALESCE(patient_wording #>> '{en-US,instructions}', '')) <= 2000
      AND char_length(COALESCE(patient_wording #>> '{en-US,frequency}', '')) <= 200
      AND COALESCE(jsonb_typeof(patient_wording->'es-MX'), 'object') = 'object'
      AND (COALESCE(patient_wording->'es-MX', '{}'::jsonb) - 'title' - 'instructions' - 'frequency') = '{}'::jsonb
      AND char_length(COALESCE(patient_wording #>> '{es-MX,title}', '')) <= 300
      AND char_length(COALESCE(patient_wording #>> '{es-MX,instructions}', '')) <= 2000
      AND char_length(COALESCE(patient_wording #>> '{es-MX,frequency}', '')) <= 200);

CREATE OR REPLACE FUNCTION private.approve_care_plan_version(
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
  v_continuity jsonb := '{}'::jsonb;
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
  -- Both languages are reviewed together, so a later language switch needs no new review.
  IF EXISTS (
    SELECT 1 FROM public.care_plan_items
    WHERE plan_version_id = p_plan_version_id AND NOT is_removed
      AND NOT (wording_verified AND private.care_plan_wording_is_complete(
        wording, source_locale, title, instructions, frequency))
  ) THEN
    RAISE EXCEPTION 'every patient-facing item needs verified English and Spanish wording';
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
    -- Lock prior canonical activities before comparing them. Retain identity only
    -- for one exact source-backed, unchanged item; never merge distinct evidence.
    PERFORM 1 FROM public.obligations
    WHERE care_plan_item_id IN (
      SELECT id FROM public.care_plan_items WHERE plan_version_id = v_old_plan.id
    ) ORDER BY id FOR UPDATE;
    SELECT COALESCE(jsonb_object_agg(new_item.id::text, matching.id::text), '{}'::jsonb)
    INTO v_continuity
    FROM public.care_plan_items new_item
    CROSS JOIN LATERAL (
      SELECT (array_agg(o.id ORDER BY o.id))[1] AS id
      FROM public.care_plan_items old_item
      JOIN public.obligations o ON o.id = old_item.projection_id
      WHERE old_item.plan_version_id = v_old_plan.id AND NOT old_item.is_removed
        AND old_item.projection_type = 'obligation'
        AND old_item.source_fact_id = new_item.source_fact_id
        AND old_item.category = new_item.category
        AND old_item.title = new_item.title
        AND old_item.instructions = new_item.instructions
        AND old_item.frequency = new_item.frequency
        AND old_item.schedule = new_item.schedule
        AND o.patient_id = v_plan.patient_id AND o.is_active
        AND o.care_plan_item_id = old_item.id
        AND o.description = old_item.title AND o.notes = old_item.instructions
        AND o.frequency = old_item.frequency
        AND o.obligation_type = CASE old_item.category
          WHEN 'nutrition' THEN 'diet'::public.obligation_type_enum
          WHEN 'movement' THEN 'exercise'::public.obligation_type_enum
          ELSE 'custom'::public.obligation_type_enum END
      HAVING count(*) = 1
    ) matching
    WHERE new_item.plan_version_id = v_plan.id AND NOT new_item.is_removed
      AND new_item.category <> 'medication' AND new_item.source_fact_id IS NOT NULL;
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
          instructions = v_item.instructions, is_active = true, care_plan_item_id = v_item.id,
          patient_wording = v_item.wording
        WHERE id = (v_item.medication->>'target_id')::uuid AND patient_id = v_plan.patient_id
        RETURNING id INTO v_projection_id;
      ELSE
        INSERT INTO public.medications(
          patient_id, name, dosage, frequency, route, instructions,
          prescribed_by_care_team_id, start_date, end_date, is_active, care_plan_item_id,
          patient_wording
        ) VALUES (
          v_plan.patient_id, v_item.medication->>'name', v_item.medication->>'dosage',
          v_item.medication->>'frequency', v_route, v_item.instructions, v_care_team_id,
          NULLIF(v_item.schedule->>'start_date', '')::date,
          NULLIF(v_item.schedule->>'end_date', '')::date, true, v_item.id, v_item.wording
        ) RETURNING id INTO v_projection_id;
      END IF;
      UPDATE public.care_plan_items SET projection_type = 'medication', projection_id = v_projection_id
      WHERE id = v_item.id;
    ELSE
      v_projection_id := NULLIF(v_continuity->>v_item.id::text, '')::uuid;
      IF v_projection_id IS NOT NULL THEN
        -- Reminder settings and adherence logs reference this stable identity.
        -- Historical item projection references remain immutable.
        UPDATE public.obligations SET is_active = true, care_plan_item_id = v_item.id,
          patient_wording = v_item.wording
        WHERE id = v_projection_id AND patient_id = v_plan.patient_id;
      ELSE
      INSERT INTO public.obligations(
        patient_id, obligation_type, description, frequency, notes, set_by_care_team_id,
        is_active, care_plan_item_id, patient_wording
      ) VALUES (
        v_plan.patient_id,
        CASE v_item.category WHEN 'nutrition' THEN 'diet'::public.obligation_type_enum
          WHEN 'movement' THEN 'exercise'::public.obligation_type_enum
          ELSE 'custom'::public.obligation_type_enum END,
        v_item.title, v_item.frequency, v_item.instructions, v_care_team_id, true, v_item.id,
        v_item.wording
      ) RETURNING id INTO v_projection_id;
      END IF;
      UPDATE public.care_plan_items SET projection_type = 'obligation', projection_id = v_projection_id
      WHERE id = v_item.id;
    END IF;
  END LOOP;

  UPDATE public.care_plan_versions SET status = 'approved', approved_by = p_reviewer_id,
    approved_at = now(), recommendation_id = v_recommendation_id WHERE id = v_plan.id;
  INSERT INTO public.care_plan_audit_events(plan_version_id, actor_id, event_type, event_data)
  VALUES (v_plan.id, p_reviewer_id, 'approved_and_published',
    jsonb_build_object('recommendation_id', v_recommendation_id, 'patient_locale', v_locale,
      'wording', (SELECT COALESCE(jsonb_object_agg(id::text, jsonb_build_object(
        'source_locale', source_locale, 'origin', wording_origin)), '{}'::jsonb)
        FROM public.care_plan_items WHERE plan_version_id = v_plan.id AND NOT is_removed)));
  RETURN jsonb_build_object('plan_version_id', v_plan.id, 'recommendation_id', v_recommendation_id,
    'status', 'approved');
END;
$$;

CREATE OR REPLACE FUNCTION private.complete_care_plan_generation(
  p_plan_version_id uuid, p_request_id uuid, p_source_watermark timestamptz, p_items jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_plan public.care_plan_versions%ROWTYPE;
  v_request public.care_plan_generation_requests%ROWTYPE;
  v_item jsonb;
BEGIN
  -- Match publication's lock order; no provider call is held inside this transaction.
  SELECT * INTO v_plan FROM public.care_plan_versions WHERE id = p_plan_version_id FOR UPDATE;
  IF NOT FOUND OR v_plan.status <> 'draft' THEN
    RAISE EXCEPTION 'care plan is not an open draft';
  END IF;
  SELECT * INTO v_request FROM public.care_plan_generation_requests
    WHERE id = p_request_id FOR UPDATE;
  IF NOT FOUND OR v_request.patient_id <> v_plan.patient_id
    OR v_request.status <> 'processing'
    OR v_request.source_watermark IS DISTINCT FROM p_source_watermark THEN
    RAISE EXCEPTION 'generation claim is no longer current';
  END IF;
  IF jsonb_typeof(p_items) IS DISTINCT FROM 'array'
    OR jsonb_array_length(p_items) NOT BETWEEN 1 AND 100 THEN
    RAISE EXCEPTION 'invalid care plan item batch';
  END IF;
  -- Repair a historical partial baseline copy on retry, preserving all clinician
  -- edits already made in the open draft and the immutable approved snapshot.
  -- Approved wording is carried forward in both languages; it is verified again.
  INSERT INTO public.care_plan_items(plan_version_id, source_fact_id, category, title,
    instructions, frequency, schedule, medication, confidence_score, uncertainty,
    conflict, blocker_reason, source_locale, wording, wording_origin)
  SELECT v_plan.id, i.source_fact_id, i.category, i.title, i.instructions,
    i.frequency, i.schedule, i.medication, i.confidence_score, i.uncertainty,
    i.conflict, i.blocker_reason, i.source_locale, i.wording, i.wording_origin
  FROM public.care_plan_items i JOIN public.care_plan_versions v ON v.id = i.plan_version_id
  WHERE v.patient_id = v_plan.patient_id AND v.status = 'approved' AND NOT i.is_removed
    AND NOT EXISTS (SELECT 1 FROM public.care_plan_items d
      WHERE d.plan_version_id = v_plan.id AND d.source_fact_id IS NOT DISTINCT FROM i.source_fact_id);
  FOR v_item IN SELECT value FROM jsonb_array_elements(p_items) LOOP
    IF NOT EXISTS (SELECT 1 FROM public.clinical_facts
      WHERE id = (v_item->>'source_fact_id')::uuid AND patient_id = v_plan.patient_id
        AND review_state IN ('pending_review', 'approved')) THEN
      RAISE EXCEPTION 'source fact is not eligible patient evidence';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.care_plan_items
      WHERE plan_version_id = v_plan.id
        AND source_fact_id = (v_item->>'source_fact_id')::uuid) THEN
      INSERT INTO public.care_plan_items(plan_version_id, source_fact_id, category,
        title, instructions, frequency, medication, confidence_score, uncertainty,
        conflict, blocker_reason)
      VALUES (v_plan.id, (v_item->>'source_fact_id')::uuid, v_item->>'category',
        v_item->>'title', v_item->>'instructions', v_item->>'frequency',
        COALESCE(v_item->'medication', '{}'::jsonb),
        (v_item->>'confidence_score')::numeric,
        COALESCE(v_item->'uncertainty', '[]'::jsonb),
        COALESCE(v_item->'conflict', '{}'::jsonb), v_item->>'blocker_reason');
    END IF;
  END LOOP;
  UPDATE public.care_plan_versions SET source_watermark = p_source_watermark,
    generated_at = now(), generation_error_code = NULL WHERE id = v_plan.id;
  INSERT INTO public.care_plan_audit_events(plan_version_id, event_type, event_data)
    VALUES (v_plan.id, 'generated', jsonb_build_object('fact_count', jsonb_array_length(p_items),
      'request_id', p_request_id));
  UPDATE public.care_plan_generation_requests SET status = 'completed',
    plan_version_id = v_plan.id, completed_at = now(), failure_code = NULL,
    claimed_at = NULL WHERE id = v_request.id;
  RETURN jsonb_build_object('plan_version_id', v_plan.id, 'status', 'completed');
END;
$$;

REVOKE ALL ON FUNCTION private.care_plan_wording_is_complete(jsonb, text, text, text, text),
  private.approve_care_plan_version(uuid, uuid, text),
  private.complete_care_plan_generation(uuid, uuid, timestamptz, jsonb)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.care_plan_wording_is_complete(jsonb, text, text, text, text),
  private.approve_care_plan_version(uuid, uuid, text),
  private.complete_care_plan_generation(uuid, uuid, timestamptz, jsonb)
  TO service_role;
