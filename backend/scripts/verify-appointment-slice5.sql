-- Read-only structural verification after 042/043, before backend activation.
-- Run with psql -v ON_ERROR_STOP=1. This neither expires nor changes appointments.
BEGIN READ ONLY;
DO $$
DECLARE
  v_signature text;
  v_function oid;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
      JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'appointment_status_enum' AND e.enumlabel = 'expired'
  ) THEN RAISE EXCEPTION 'Slice 5 expired status is missing'; END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_attribute
    WHERE attrelid = 'public.appointments'::regclass AND attname = 'proposal_expires_at'
      AND NOT attisdropped AND atttypid = 'timestamptz'::regtype
  ) THEN RAISE EXCEPTION 'Slice 5 proposal deadline column is missing'; END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_index i ON i.indexrelid = c.conindid
    WHERE c.conrelid = 'public.appointments'::regclass
      AND c.conname = 'appointments_patient_no_overlap' AND c.contype = 'x'
      AND c.convalidated AND NOT c.condeferrable AND i.indisvalid AND i.indisready
  ) THEN RAISE EXCEPTION 'Slice 5 patient overlap constraint is missing or invalid'; END IF;

  IF (SELECT count(*) FROM pg_trigger
    WHERE tgrelid = 'public.appointments'::regclass AND NOT tgisinternal
      AND tgenabled IN ('O', 'A') AND
      ((tgname = 'appointments_booking_guard' AND tgfoid = to_regprocedure('public.guard_appointment_booking()'))
       OR (tgname = 'appointments_expiration_audit' AND tgfoid = to_regprocedure('public.audit_appointment_expiration()')))
  ) <> 2 THEN RAISE EXCEPTION 'Slice 5 booking or expiration trigger is missing or disabled'; END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgrelid = 'public.appointment_offer_events'::regclass
      AND tgname = 'appointment_offer_events_immutable' AND NOT tgisinternal AND tgenabled IN ('O', 'A')
      AND tgfoid = to_regprocedure('public.protect_appointment_offer_events()')
  ) THEN RAISE EXCEPTION 'Appointment audit immutability trigger is missing or disabled'; END IF;

  IF (SELECT count(*) FROM pg_class WHERE oid IN
    ('public.appointments'::regclass, 'public.appointment_offer_events'::regclass)
    AND relrowsecurity) <> 2 THEN RAISE EXCEPTION 'Appointment or audit RLS is disabled'; END IF;

  FOREACH v_signature IN ARRAY ARRAY[
    'public.propose_appointment_slots(uuid,uuid,timestamp with time zone[],integer,text,text,text)',
    'public.respond_to_appointment_offer(uuid,uuid,text,text)',
    'public.expire_appointment_proposals(uuid,text)'
  ] LOOP
    v_function := to_regprocedure(v_signature);
    IF v_function IS NULL THEN RAISE EXCEPTION 'Required appointment function is missing: %', v_signature; END IF;
    IF NOT has_function_privilege('service_role', v_function, 'EXECUTE')
       OR has_function_privilege('anon', v_function, 'EXECUTE')
       OR has_function_privilege('authenticated', v_function, 'EXECUTE') THEN
      RAISE EXCEPTION 'Appointment function grants are incorrect: %', v_signature;
    END IF;
    IF (SELECT prosecdef FROM pg_proc WHERE oid = v_function) THEN
      RAISE EXCEPTION 'Appointment function must use invoker security: %', v_signature;
    END IF;
  END LOOP;

  IF EXISTS (SELECT 1 FROM public.appointments WHERE status = 'proposed'
    AND (proposal_expires_at IS NULL
      OR proposal_expires_at > least(created_at + interval '168 hours', scheduled_at))) THEN
    RAISE EXCEPTION 'Proposed appointment deadlines require review';
  END IF;
END;
$$;
SELECT 'Slice 5 schema and function permissions verified' AS result;
COMMIT;
