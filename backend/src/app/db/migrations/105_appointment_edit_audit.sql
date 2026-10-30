-- SAFE-003: visit edits and their append-only audit commit together.
ALTER TABLE public.appointment_offer_events ADD COLUMN changes jsonb NOT NULL DEFAULT '{}';
ALTER TABLE public.appointment_offer_events ADD CONSTRAINT appointment_offer_events_changes_check
  CHECK (jsonb_typeof(changes)='object');
ALTER TABLE public.appointment_offer_events DROP CONSTRAINT appointment_offer_events_action_check;
ALTER TABLE public.appointment_offer_events ADD CONSTRAINT appointment_offer_events_action_check
  CHECK (action IN ('propose','accept','decline','request_alternative','cancel','expire',
    'clinician_cancel','complete','no_show','details_updated'));

CREATE OR REPLACE FUNCTION public.edit_appointment_details(
  p_actor_id uuid,p_appointment_id uuid,p_changes jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE
  target public.appointments;
  prior public.appointments;
  edited public.appointments;
  response public.appointments;
  delta jsonb;
BEGIN
  IF p_actor_id IS NULL OR p_changes IS NULL OR jsonb_typeof(p_changes)<>'object'
    OR p_changes='{}'::jsonb
    OR EXISTS (SELECT 1 FROM jsonb_each(p_changes) AS f(key,value)
      WHERE key NOT IN ('location','reason','notes','appointment_type','scheduled_at','duration_minutes')
        OR jsonb_typeof(value) NOT IN ('string','number')) THEN
    RETURN jsonb_build_object('error','invalid');
  END IF;
  SELECT * INTO target FROM public.appointments WHERE id=p_appointment_id;
  IF NOT FOUND THEN RETURN jsonb_build_object('error','not_found'); END IF;
  -- Lock every proposed sibling in a stable order before rechecking the target.
  -- The normal response workflow also locks these rows; no stale status bypass.
  PERFORM 1 FROM public.appointments
    WHERE id=p_appointment_id OR (target.proposal_group_id IS NOT NULL
      AND proposal_group_id=target.proposal_group_id AND status='proposed')
    ORDER BY id FOR UPDATE;
  SELECT * INTO STRICT target FROM public.appointments WHERE id=p_appointment_id;
  IF NOT EXISTS (SELECT 1 FROM public.clinicians WHERE id=p_actor_id) THEN
    RETURN jsonb_build_object('error','forbidden');
  END IF;
  IF target.clinician_id IS DISTINCT FROM p_actor_id THEN
    PERFORM 1 FROM public.care_teams WHERE clinician_id=p_actor_id
      AND patient_id=target.patient_id AND clinic_id=target.clinic_id AND status='active'
      FOR SHARE;
    IF NOT FOUND THEN RETURN jsonb_build_object('error','forbidden'); END IF;
  END IF;
  IF target.status NOT IN ('proposed','confirmed','scheduled') THEN
    RETURN jsonb_build_object('error','stale');
  END IF;
  IF (target.proposal_group_id IS NOT NULL OR target.status IN ('confirmed','scheduled'))
    AND p_changes ?| ARRAY['scheduled_at','duration_minutes'] THEN
    RETURN jsonb_build_object('error','stale');
  END IF;
  IF p_changes ? 'duration_minutes' AND ((p_changes->>'duration_minutes')::integer NOT BETWEEN 5 AND 480) THEN
    RETURN jsonb_build_object('error','invalid');
  END IF;
  FOR prior IN SELECT * FROM public.appointments WHERE id=p_appointment_id
    OR (target.proposal_group_id IS NOT NULL AND target.status='proposed'
      AND proposal_group_id=target.proposal_group_id AND status='proposed')
    ORDER BY id LOOP
    UPDATE public.appointments SET
      location=CASE WHEN p_changes ? 'location' THEN p_changes->>'location' ELSE location END,
      reason=CASE WHEN p_changes ? 'reason' THEN p_changes->>'reason' ELSE reason END,
      notes=CASE WHEN p_changes ? 'notes' THEN p_changes->>'notes' ELSE notes END,
      appointment_type=CASE WHEN p_changes ? 'appointment_type'
        THEN (p_changes->>'appointment_type')::public.appointment_type_enum ELSE appointment_type END,
      scheduled_at=CASE WHEN p_changes ? 'scheduled_at'
        THEN (p_changes->>'scheduled_at')::timestamptz ELSE scheduled_at END,
      duration_minutes=CASE WHEN p_changes ? 'duration_minutes'
        THEN (p_changes->>'duration_minutes')::integer ELSE duration_minutes END
      WHERE id=prior.id RETURNING * INTO edited;
    SELECT coalesce(jsonb_object_agg(f.key,jsonb_build_object('before',to_jsonb(prior)->f.key,
      'after',to_jsonb(edited)->f.key)), '{}'::jsonb) INTO delta
      FROM jsonb_object_keys(p_changes) AS f(key)
      WHERE to_jsonb(prior)->f.key IS DISTINCT FROM to_jsonb(edited)->f.key;
    IF delta<>'{}'::jsonb THEN
      INSERT INTO public.appointment_offer_events(appointment_id,patient_id,proposal_group_id,
        actor_id,action,previous_status,new_status,changes)
        VALUES(edited.id,edited.patient_id,edited.proposal_group_id,p_actor_id,
          'details_updated',prior.status,edited.status,delta);
    END IF;
    IF edited.id=p_appointment_id THEN response:=edited; END IF;
  END LOOP;
  RETURN jsonb_build_object('appointment',to_jsonb(response));
END; $$;
REVOKE ALL ON FUNCTION public.edit_appointment_details(uuid,uuid,jsonb)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.edit_appointment_details(uuid,uuid,jsonb) TO service_role;
