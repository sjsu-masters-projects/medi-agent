-- Apply after 042 has committed. No automatic repair of existing overlapping bookings.
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA extensions;

-- UTC timestamp arithmetic is immutable and counts elapsed minutes across DST.
CREATE FUNCTION public.appointment_booking_window(p_start timestamptz, p_minutes integer)
RETURNS tsrange LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
SET search_path = pg_catalog AS $$
  SELECT tsrange(p_start AT TIME ZONE 'UTC',
    (p_start AT TIME ZONE 'UTC') + p_minutes * interval '1 minute', '[)');
$$;
REVOKE ALL ON FUNCTION public.appointment_booking_window(timestamptz, integer) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.appointment_booking_window(timestamptz, integer)
  TO authenticated, service_role;

-- This constraint also arbitrates concurrent transactions and legacy/direct writes.
-- [start, end) permits back-to-back visits. Proposed options do not reserve time.
ALTER TABLE public.appointments ADD CONSTRAINT appointments_patient_no_overlap
  EXCLUDE USING gist (patient_id WITH =,
    public.appointment_booking_window(scheduled_at, duration_minutes) WITH &&)
  WHERE (status IN ('confirmed', 'scheduled'));

ALTER TABLE public.appointments ADD COLUMN proposal_expires_at timestamptz;
UPDATE public.appointments SET proposal_expires_at =
  least(created_at + interval '168 hours', scheduled_at)
  WHERE status = 'proposed';
CREATE INDEX idx_appointment_proposal_expiry ON public.appointments(proposal_expires_at)
  WHERE status = 'proposed';

-- Legacy responses and automatic expiration share the existing append-only audit.
ALTER TABLE public.appointment_offer_events ALTER COLUMN proposal_group_id DROP NOT NULL;
ALTER TABLE public.appointment_offer_events ALTER COLUMN actor_id DROP NOT NULL;
ALTER TABLE public.appointment_offer_events DROP CONSTRAINT appointment_offer_events_action_check;
ALTER TABLE public.appointment_offer_events ADD CONSTRAINT appointment_offer_events_action_check
  CHECK (action IN ('propose', 'accept', 'decline', 'request_alternative', 'cancel', 'expire'));
ALTER TABLE public.appointment_offer_events ADD CONSTRAINT appointment_offer_events_actor_check
  CHECK ((action = 'expire' AND actor_id IS NULL) OR (action <> 'expire' AND actor_id IS NOT NULL));

CREATE FUNCTION public.guard_appointment_booking() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE v_now timestamptz := clock_timestamp();
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF OLD.status = 'expired' AND NEW.status <> OLD.status THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'appointment_expired';
    END IF;
    IF OLD.status = 'proposed' AND NEW.status <> OLD.status AND NEW.status <> 'expired'
       AND (OLD.proposal_expires_at <= v_now OR OLD.scheduled_at <= v_now) THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'appointment_expired';
    END IF;
    IF NEW.status = 'expired' AND OLD.status <> 'expired'
       AND (OLD.status <> 'proposed' OR
         (OLD.proposal_expires_at > v_now AND OLD.scheduled_at > v_now)) THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'appointment_stale';
    END IF;
  END IF;
  IF NEW.status IN ('proposed', 'confirmed', 'scheduled') AND
     (TG_OP = 'INSERT' OR NEW.status IS DISTINCT FROM OLD.status
       OR NEW.scheduled_at IS DISTINCT FROM OLD.scheduled_at
       OR NEW.duration_minutes IS DISTINCT FROM OLD.duration_minutes) AND NEW.scheduled_at <= v_now THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'appointment_past';
  END IF;
  IF NEW.status = 'proposed' THEN
    -- Neither editing nor re-saving a proposal extends its original deadline.
    NEW.proposal_expires_at := least(NEW.created_at + interval '168 hours', NEW.scheduled_at);
    IF TG_OP = 'UPDATE' AND OLD.proposal_expires_at IS NOT NULL THEN
      NEW.proposal_expires_at := least(NEW.proposal_expires_at, OLD.proposal_expires_at);
    END IF;
  ELSIF TG_OP = 'UPDATE' THEN
    NEW.proposal_expires_at := OLD.proposal_expires_at;
  ELSE
    NEW.proposal_expires_at := NULL;
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER appointments_booking_guard BEFORE INSERT OR UPDATE ON public.appointments
  FOR EACH ROW EXECUTE FUNCTION public.guard_appointment_booking();
REVOKE ALL ON FUNCTION public.guard_appointment_booking() FROM PUBLIC, anon, authenticated;

CREATE FUNCTION public.audit_appointment_expiration() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
BEGIN
  INSERT INTO public.appointment_offer_events(appointment_id, patient_id, proposal_group_id,
    actor_id, action, previous_status, new_status)
  VALUES (NEW.id, NEW.patient_id, NEW.proposal_group_id, NULL, 'expire', OLD.status, NEW.status);
  RETURN NEW;
END;
$$;
CREATE TRIGGER appointments_expiration_audit AFTER UPDATE ON public.appointments
  FOR EACH ROW WHEN (OLD.status = 'proposed' AND NEW.status = 'expired')
  EXECUTE FUNCTION public.audit_appointment_expiration();
REVOKE ALL ON FUNCTION public.audit_appointment_expiration() FROM PUBLIC, anon, authenticated;

CREATE FUNCTION public.expire_appointment_proposals(p_actor_id uuid, p_actor_role text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE v_count integer;
BEGIN
  IF p_actor_id IS NULL OR p_actor_role IS NULL OR p_actor_role NOT IN ('patient', 'clinician') THEN
    RETURN jsonb_build_object('error', 'forbidden');
  END IF;
  WITH due AS MATERIALIZED (
    SELECT a.id FROM public.appointments a
    WHERE a.status = 'proposed' AND a.proposal_expires_at <= clock_timestamp()
      AND ((p_actor_role = 'patient' AND a.patient_id = p_actor_id) OR
        (p_actor_role = 'clinician' AND EXISTS (SELECT 1 FROM public.care_teams c
          WHERE c.patient_id = a.patient_id AND c.clinician_id = p_actor_id AND c.status = 'active')))
    ORDER BY a.id FOR UPDATE OF a
  ) UPDATE public.appointments a SET status = 'expired' FROM due
    WHERE a.id = due.id AND a.status = 'proposed';
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN jsonb_build_object('expired_count', v_count);
END;
$$;
REVOKE ALL ON FUNCTION public.expire_appointment_proposals(uuid, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.expire_appointment_proposals(uuid, text) TO service_role;

-- Replace the transaction in 041 without changing its public signature. Standalone
-- responses now use the same transaction, status rechecks, and audit as grouped ones.
CREATE OR REPLACE FUNCTION public.respond_to_appointment_offer(
  p_actor_id uuid, p_appointment_id uuid, p_action text, p_note text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE
  v_row public.appointments%ROWTYPE;
  v_group uuid;
  v_new_status appointment_status_enum;
BEGIN
  SELECT * INTO v_row FROM public.appointments WHERE id = p_appointment_id;
  IF NOT FOUND THEN RETURN jsonb_build_object('error', 'not_found'); END IF;
  IF p_actor_id IS NULL OR v_row.patient_id <> p_actor_id THEN
    RETURN jsonb_build_object('error', 'forbidden');
  END IF;
  v_group := v_row.proposal_group_id;
  -- Serialize competing offer responses before any row locks. The exclusion
  -- constraint remains authoritative for direct writers that do not take this lock.
  PERFORM pg_advisory_xact_lock(hashtextextended('appointment-patient:' || v_row.patient_id::text, 0));
  PERFORM pg_advisory_xact_lock(hashtextextended(coalesce(v_group, p_appointment_id)::text, 0));
  PERFORM id FROM public.appointments
    WHERE id = p_appointment_id OR (v_group IS NOT NULL AND proposal_group_id = v_group)
    ORDER BY id FOR UPDATE;
  SELECT * INTO v_row FROM public.appointments WHERE id = p_appointment_id;
  IF NOT FOUND THEN RETURN jsonb_build_object('error', 'not_found'); END IF;
  IF v_row.proposal_group_id IS DISTINCT FROM v_group THEN
    RETURN jsonb_build_object('error', 'stale');
  END IF;
  IF v_row.patient_id <> p_actor_id OR EXISTS (
    SELECT 1 FROM public.appointments WHERE proposal_group_id = v_group
      AND (patient_id <> p_actor_id OR care_team_id <> v_row.care_team_id)
  ) THEN RETURN jsonb_build_object('error', 'forbidden'); END IF;
  IF p_action IS NULL OR p_action NOT IN ('accept', 'decline', 'request_alternative', 'cancel')
     OR char_length(p_note) > 1000 THEN RETURN jsonb_build_object('error', 'invalid'); END IF;

  -- Expiration and its audit commit even when the response is refused as expired.
  UPDATE public.appointments SET status = 'expired'
    WHERE (id = p_appointment_id OR (v_group IS NOT NULL AND proposal_group_id = v_group))
      AND status = 'proposed' AND proposal_expires_at <= clock_timestamp();
  SELECT * INTO v_row FROM public.appointments WHERE id = p_appointment_id;
  IF v_row.status = 'expired' THEN RETURN jsonb_build_object('error', 'expired'); END IF;
  IF (p_action = 'cancel' AND v_row.status NOT IN ('proposed', 'confirmed', 'scheduled'))
     OR (p_action <> 'cancel' AND v_row.status <> 'proposed') THEN
    RETURN jsonb_build_object('error', 'stale');
  END IF;
  IF v_group IS NOT NULL AND p_action = 'cancel' AND v_row.status = 'proposed' THEN
    RETURN jsonb_build_object('error', 'stale');
  END IF;
  v_new_status := CASE p_action WHEN 'accept' THEN 'confirmed'
    WHEN 'decline' THEN 'declined' WHEN 'request_alternative' THEN 'alternative_requested'
    WHEN 'cancel' THEN 'cancelled' END;
  BEGIN
    WITH previous AS MATERIALIZED (
      SELECT id, status FROM public.appointments
      WHERE id = p_appointment_id OR (p_action <> 'cancel' AND v_group IS NOT NULL
        AND proposal_group_id = v_group AND status = 'proposed')
    ), changed AS (
      UPDATE public.appointments AS a SET
        status = CASE WHEN p_action = 'accept' AND a.id <> p_appointment_id
                      THEN 'withdrawn'::appointment_status_enum ELSE v_new_status END,
        patient_note = CASE WHEN p_note IS NOT NULL THEN nullif(btrim(p_note), '') ELSE a.patient_note END
      FROM previous WHERE a.id = previous.id RETURNING a.*
    ) INSERT INTO public.appointment_offer_events(appointment_id, patient_id, proposal_group_id,
        actor_id, action, previous_status, new_status)
      SELECT changed.id, changed.patient_id, changed.proposal_group_id, p_actor_id,
        p_action, previous.status, changed.status FROM changed JOIN previous ON changed.id = previous.id;
  EXCEPTION
    WHEN exclusion_violation OR deadlock_detected THEN
      RETURN jsonb_build_object('error', 'conflict');
    WHEN raise_exception THEN
      IF SQLERRM NOT IN ('appointment_expired', 'appointment_past') THEN RAISE; END IF;
      UPDATE public.appointments SET status = 'expired'
        WHERE (id = p_appointment_id OR (v_group IS NOT NULL AND proposal_group_id = v_group))
          AND status = 'proposed' AND proposal_expires_at <= clock_timestamp();
      RETURN jsonb_build_object('error', 'expired');
  END;
  SELECT * INTO v_row FROM public.appointments WHERE id = p_appointment_id;
  RETURN jsonb_build_object('appointment', to_jsonb(v_row));
END;
$$;
