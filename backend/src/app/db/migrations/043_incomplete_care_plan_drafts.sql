-- Missing evidence is a review blocker, not a reason to fabricate instructions.
ALTER TABLE public.care_plan_items DROP CONSTRAINT care_plan_items_instructions_check;
ALTER TABLE public.care_plan_items DROP CONSTRAINT care_plan_items_frequency_check;
ALTER TABLE public.care_plan_items ADD CONSTRAINT care_plan_items_instructions_check
  CHECK (char_length(instructions) <= 2000);
ALTER TABLE public.care_plan_items ADD CONSTRAINT care_plan_items_frequency_check
  CHECK (char_length(frequency) <= 200);

-- This trigger runs inside the existing atomic publication transaction, including
-- service-role callers. A stale UI or bypassed API cannot publish a partial draft.
CREATE FUNCTION public.guard_care_plan_publication() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_request public.care_plan_generation_requests%ROWTYPE;
BEGIN
  IF NEW.status = 'approved' AND OLD.status IS DISTINCT FROM 'approved' THEN
    SELECT * INTO v_request FROM public.care_plan_generation_requests
    WHERE patient_id = NEW.patient_id ORDER BY created_at DESC LIMIT 1 FOR UPDATE;
    IF FOUND AND (v_request.status <> 'completed'
      OR v_request.source_watermark > NEW.source_watermark
      OR (v_request.source_watermark >= NEW.source_watermark
        AND v_request.plan_version_id IS DISTINCT FROM NEW.id)) THEN
      RAISE EXCEPTION 'automatic generation must complete before publication';
    END IF;
    IF EXISTS (SELECT 1 FROM public.care_plan_items
      WHERE plan_version_id = NEW.id AND NOT is_removed AND (
        btrim(title) = '' OR btrim(instructions) = '' OR btrim(frequency) = ''
        OR lower(btrim(frequency)) = 'as directed'
        OR (category = 'medication' AND (
          NULLIF(btrim(medication->>'name'), '') IS NULL
          OR NULLIF(btrim(medication->>'dosage'), '') IS NULL
          OR NULLIF(btrim(medication->>'route'), '') IS NULL
          OR NULLIF(btrim(medication->>'frequency'), '') IS NULL)))) THEN
      RAISE EXCEPTION 'active care-plan items require complete reviewed instructions';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER care_plan_publication_guard BEFORE UPDATE ON public.care_plan_versions
  FOR EACH ROW EXECUTE FUNCTION public.guard_care_plan_publication();
REVOKE ALL ON FUNCTION public.guard_care_plan_publication() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.guard_care_plan_publication() TO service_role;

-- Serialize item edits with publication and freeze historical wording. Projection
-- links are written by approval while the parent is still a draft.
CREATE FUNCTION public.guard_care_plan_item_edit() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_status text;
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.plan_version_id IS DISTINCT FROM OLD.plan_version_id THEN
    RAISE EXCEPTION 'care-plan items cannot move between versions';
  END IF;
  SELECT status INTO v_status FROM public.care_plan_versions
    WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.plan_version_id ELSE NEW.plan_version_id END
    FOR UPDATE;
  IF v_status IS DISTINCT FROM 'draft' THEN
    RAISE EXCEPTION 'only draft care-plan items can be changed';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER care_plan_item_edit_guard BEFORE INSERT OR UPDATE OR DELETE
  ON public.care_plan_items FOR EACH ROW EXECUTE FUNCTION public.guard_care_plan_item_edit();
REVOKE ALL ON FUNCTION public.guard_care_plan_item_edit() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.guard_care_plan_item_edit() TO service_role;

CREATE FUNCTION public.complete_care_plan_generation(
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
  INSERT INTO public.care_plan_items(plan_version_id, source_fact_id, category, title,
    instructions, frequency, schedule, medication, confidence_score, uncertainty,
    conflict, blocker_reason)
  SELECT v_plan.id, i.source_fact_id, i.category, i.title, i.instructions,
    i.frequency, i.schedule, i.medication, i.confidence_score, i.uncertainty,
    i.conflict, i.blocker_reason
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
REVOKE ALL ON FUNCTION public.complete_care_plan_generation(uuid, uuid, timestamptz, jsonb)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.complete_care_plan_generation(uuid, uuid, timestamptz, jsonb)
  TO service_role;
