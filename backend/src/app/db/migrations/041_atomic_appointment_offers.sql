-- Group mutations and their audit records commit together. Only the backend may call
-- these functions; actor ownership is rechecked inside the transaction.
CREATE TABLE public.appointment_offer_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  appointment_id uuid NOT NULL REFERENCES public.appointments(id),
  patient_id uuid NOT NULL REFERENCES public.patients(id),
  proposal_group_id uuid NOT NULL,
  actor_id uuid NOT NULL,
  action text NOT NULL CHECK (action IN ('propose', 'accept', 'decline', 'request_alternative', 'cancel')),
  previous_status appointment_status_enum,
  new_status appointment_status_enum NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.appointment_offer_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY appointment_offer_events_patient_read ON public.appointment_offer_events
  FOR SELECT TO authenticated USING (patient_id = (SELECT auth.uid()));
CREATE POLICY appointment_offer_events_clinician_read ON public.appointment_offer_events
  FOR SELECT TO authenticated USING (private.is_clinician() AND private.is_assigned_clinician(patient_id));
REVOKE ALL ON TABLE public.appointment_offer_events FROM anon, authenticated;
GRANT SELECT ON TABLE public.appointment_offer_events TO authenticated;
GRANT SELECT, INSERT ON TABLE public.appointment_offer_events TO service_role;

CREATE FUNCTION public.protect_appointment_offer_events() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
BEGIN
  RAISE EXCEPTION 'appointment offer events are append-only';
END;
$$;
CREATE TRIGGER appointment_offer_events_immutable
  BEFORE UPDATE OR DELETE ON public.appointment_offer_events
  FOR EACH ROW EXECUTE FUNCTION public.protect_appointment_offer_events();
REVOKE ALL ON FUNCTION public.protect_appointment_offer_events() FROM PUBLIC, anon, authenticated;

CREATE FUNCTION public.propose_appointment_slots(
  p_actor_id uuid, p_care_team_id uuid, p_slots timestamptz[],
  p_duration_minutes integer, p_appointment_type text, p_location text, p_reason text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE
  v_team public.care_teams%ROWTYPE;
  v_group uuid := gen_random_uuid();
  v_name text;
  v_rows jsonb;
BEGIN
  SELECT * INTO v_team FROM public.care_teams WHERE id = p_care_team_id FOR SHARE;
  IF NOT FOUND OR v_team.status <> 'active' OR v_team.clinician_id <> p_actor_id THEN
    RETURN jsonb_build_object('error', 'forbidden');
  END IF;
  IF cardinality(p_slots) IS NULL OR cardinality(p_slots) NOT BETWEEN 2 AND 4
     OR (SELECT count(DISTINCT value) FROM unnest(p_slots) AS value) <> cardinality(p_slots)
     OR EXISTS (SELECT 1 FROM unnest(p_slots) AS value WHERE value <= now() OR value IS NULL)
     OR p_duration_minutes IS NULL OR p_duration_minutes NOT BETWEEN 5 AND 480
     OR p_appointment_type IS NULL
     OR p_appointment_type NOT IN ('follow_up', 'initial', 'routine', 'urgent', 'pre_op') THEN
    RETURN jsonb_build_object('error', 'invalid');
  END IF;
  SELECT concat_ws(' ', first_name, last_name) INTO v_name
    FROM public.clinicians WHERE id = p_actor_id;
  WITH inserted AS (
    INSERT INTO public.appointments(patient_id, care_team_id, clinician_name,
      scheduled_at, duration_minutes, appointment_type, location, reason, status, proposal_group_id)
    SELECT v_team.patient_id, v_team.id, v_name, value, p_duration_minutes,
      p_appointment_type::appointment_type_enum, p_location, p_reason, 'proposed', v_group
    FROM unnest(p_slots) AS value ORDER BY value
    RETURNING *
  ) SELECT jsonb_agg(to_jsonb(inserted) ORDER BY scheduled_at) INTO v_rows FROM inserted;
  INSERT INTO public.appointment_offer_events(appointment_id, patient_id, proposal_group_id,
    actor_id, action, new_status)
  SELECT id, patient_id, proposal_group_id, p_actor_id, 'propose', status
    FROM public.appointments WHERE proposal_group_id = v_group;
  RETURN jsonb_build_object('appointments', v_rows);
END;
$$;

CREATE FUNCTION public.respond_to_appointment_offer(
  p_actor_id uuid, p_appointment_id uuid, p_action text, p_note text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE
  v_row public.appointments%ROWTYPE;
  v_group uuid;
  v_new_status appointment_status_enum;
BEGIN
  SELECT proposal_group_id INTO v_group FROM public.appointments WHERE id = p_appointment_id;
  IF NOT FOUND THEN RETURN jsonb_build_object('error', 'not_found'); END IF;
  IF v_group IS NULL THEN RETURN jsonb_build_object('error', 'invalid'); END IF;
  -- Every response locks the same group before locking individual rows. A second
  -- response waits, then sees the committed state rather than confirming another slot.
  PERFORM pg_advisory_xact_lock(hashtextextended(v_group::text, 0));
  PERFORM id FROM public.appointments WHERE proposal_group_id = v_group ORDER BY id FOR UPDATE;
  SELECT * INTO v_row FROM public.appointments WHERE id = p_appointment_id;
  IF NOT FOUND THEN RETURN jsonb_build_object('error', 'not_found'); END IF;
  IF p_actor_id IS NULL OR v_row.patient_id <> p_actor_id OR EXISTS (
    SELECT 1 FROM public.appointments WHERE proposal_group_id = v_group
      AND (patient_id <> p_actor_id OR care_team_id <> v_row.care_team_id)
  ) THEN RETURN jsonb_build_object('error', 'forbidden'); END IF;
  IF p_action IS NULL OR p_action NOT IN ('accept', 'decline', 'request_alternative', 'cancel')
     OR char_length(p_note) > 1000 THEN RETURN jsonb_build_object('error', 'invalid'); END IF;
  IF (p_action = 'cancel' AND v_row.status NOT IN ('confirmed', 'scheduled'))
     OR (p_action <> 'cancel' AND v_row.status <> 'proposed') THEN
    RETURN jsonb_build_object('error', 'stale');
  END IF;
  IF p_action = 'accept' AND v_row.scheduled_at <= now() THEN
    RETURN jsonb_build_object('error', 'stale');
  END IF;
  v_new_status := CASE p_action WHEN 'accept' THEN 'confirmed'
    WHEN 'decline' THEN 'declined' WHEN 'request_alternative' THEN 'alternative_requested'
    WHEN 'cancel' THEN 'cancelled' END;
  WITH previous AS MATERIALIZED (
    SELECT id, status FROM public.appointments
    WHERE (p_action = 'cancel' AND id = p_appointment_id)
       OR (p_action <> 'cancel' AND proposal_group_id = v_group AND status = 'proposed')
  ), changed AS (
    UPDATE public.appointments AS a SET
      status = CASE WHEN p_action = 'accept' AND a.id <> p_appointment_id
                    THEN 'withdrawn'::appointment_status_enum ELSE v_new_status END,
      patient_note = CASE WHEN p_note IS NOT NULL THEN nullif(btrim(p_note), '') ELSE a.patient_note END
    FROM previous WHERE a.id = previous.id
    RETURNING a.*
  ) INSERT INTO public.appointment_offer_events(appointment_id, patient_id, proposal_group_id,
      actor_id, action, previous_status, new_status)
    SELECT changed.id, changed.patient_id, changed.proposal_group_id, p_actor_id,
      p_action, previous.status, changed.status FROM changed JOIN previous ON changed.id = previous.id;
  SELECT * INTO v_row FROM public.appointments WHERE id = p_appointment_id;
  RETURN jsonb_build_object('appointment', to_jsonb(v_row));
END;
$$;

REVOKE ALL ON FUNCTION public.propose_appointment_slots(uuid, uuid, timestamptz[], integer, text, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.propose_appointment_slots(uuid, uuid, timestamptz[], integer, text, text, text)
  TO service_role;
REVOKE ALL ON FUNCTION public.respond_to_appointment_offer(uuid, uuid, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.respond_to_appointment_offer(uuid, uuid, text, text)
  TO service_role;
