-- SAFE-002: retention for the per-turn safety audit (chat_turn_safety_audits, 097).
-- Re-runnable. Apply after 097.
--
-- Rows hold a rule id and version, urgencies, an outcome and a patient id; no message text.
-- They are kept 365 days from evaluated_at and then deleted, at most 500 per call. The table
-- stays immutable to every caller: the 097 guard still rejects UPDATE, and it rejects DELETE
-- unless the row is older than 365 days AND the delete runs inside purge_chat_turn_safety_audits
-- (a transaction-local flag that only that SECURITY DEFINER function sets; service_role has no
-- table privilege and cannot set it usefully).
--
-- The purge runs from the existing audit write (record_chat_turn_safety_audit), as migration 090
-- does for its counters, so no new scheduler is needed; it is also callable by service_role for a
-- scheduled job. A purge failure never fails or delays an audit write beyond its own 5s bound.
-- Rollback: restore the 097 guard and record function; drop purge_chat_turn_safety_audits.
-- chat_safety_alerts (059) keeps its separate evidence rules and is not touched here.

CREATE INDEX IF NOT EXISTS chat_turn_safety_audits_evaluated
  ON public.chat_turn_safety_audits(evaluated_at);

CREATE OR REPLACE FUNCTION private.guard_chat_turn_safety_audit() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
  IF TG_OP = 'DELETE'
     AND coalesce(current_setting('app.safety_audit_purge', true), '') = 'on'
     AND OLD.evaluated_at < clock_timestamp() - interval '365 days' THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'Safety audit evidence is immutable';
END;
$$;

CREATE OR REPLACE FUNCTION public.purge_chat_turn_safety_audits(p_limit integer DEFAULT 500)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
  SET lock_timeout = '2s' SET statement_timeout = '5s' AS $$
DECLARE
  v_deleted integer;
BEGIN
  IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 500 THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid purge batch';
  END IF;
  PERFORM set_config('app.safety_audit_purge', 'on', true);
  WITH doomed AS (
    SELECT turn_id FROM public.chat_turn_safety_audits
     WHERE evaluated_at < clock_timestamp() - interval '365 days'
     ORDER BY evaluated_at LIMIT p_limit FOR UPDATE SKIP LOCKED)
  DELETE FROM public.chat_turn_safety_audits a USING doomed d WHERE a.turn_id = d.turn_id;
  GET DIAGNOSTICS v_deleted = ROW_COUNT;
  PERFORM set_config('app.safety_audit_purge', 'off', true);
  RETURN v_deleted;
END;
$$;

-- Same contract as 097, plus a bounded retention pass after the write.
CREATE OR REPLACE FUNCTION public.record_chat_turn_safety_audit(p_patient_id uuid, p_turn_id uuid, p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_row public.chat_turn_safety_audits;
BEGIN
  IF p_patient_id IS NULL OR p_turn_id IS NULL
    OR p_payload->>'rule_version' IS DISTINCT FROM 'triage-floor/1'
    OR jsonb_typeof(p_payload->'escalation_required') IS DISTINCT FROM 'boolean' THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid safety audit';
  END IF;
  BEGIN
    INSERT INTO public.chat_turn_safety_audits(turn_id, patient_id, safety_rule, rule_version,
      model_urgency, final_urgency, outcome, escalation_required)
      VALUES (p_turn_id, p_patient_id, p_payload->>'safety_rule', p_payload->>'rule_version',
        p_payload->>'model_urgency', p_payload->>'final_urgency', p_payload->>'outcome',
        (p_payload->>'escalation_required')::boolean)
      ON CONFLICT (turn_id) DO NOTHING;
  EXCEPTION WHEN check_violation OR not_null_violation THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid safety audit';
  END;
  SELECT * INTO STRICT v_row FROM public.chat_turn_safety_audits WHERE turn_id=p_turn_id;
  IF v_row.patient_id <> p_patient_id THEN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Safety audit unavailable';
  END IF;
  BEGIN
    PERFORM public.purge_chat_turn_safety_audits(500);
  EXCEPTION WHEN OTHERS THEN
    NULL; -- retention is best effort and never fails the audit
  END;
  RETURN jsonb_build_object('turn_id', v_row.turn_id, 'safety_rule', v_row.safety_rule,
    'outcome', v_row.outcome);
END;
$$;

REVOKE ALL ON FUNCTION private.guard_chat_turn_safety_audit() FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.purge_chat_turn_safety_audits(integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.record_chat_turn_safety_audit(uuid, uuid, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.purge_chat_turn_safety_audits(integer),
  public.record_chat_turn_safety_audit(uuid, uuid, jsonb) TO service_role;

DO $verify$
DECLARE v_function text;
BEGIN
  FOREACH v_function IN ARRAY ARRAY[
    'public.purge_chat_turn_safety_audits(integer)',
    'public.record_chat_turn_safety_audit(uuid,uuid,jsonb)'] LOOP
    IF has_function_privilege('anon', v_function, 'EXECUTE')
       OR has_function_privilege('authenticated', v_function, 'EXECUTE')
       OR NOT has_function_privilege('service_role', v_function, 'EXECUTE') THEN
      RAISE EXCEPTION '098: wrong execute grants on %', v_function;
    END IF;
    IF (SELECT proconfig IS NULL OR NOT proconfig::text LIKE '%search_path%'
          FROM pg_proc WHERE oid = v_function::regprocedure) THEN
      RAISE EXCEPTION '098: % must pin search_path', v_function;
    END IF;
  END LOOP;
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.chat_turn_safety_audits'::regclass)
     OR has_table_privilege('anon', 'public.chat_turn_safety_audits', 'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('authenticated', 'public.chat_turn_safety_audits', 'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('service_role', 'public.chat_turn_safety_audits', 'SELECT,INSERT,UPDATE,DELETE') THEN
    RAISE EXCEPTION '098: chat_turn_safety_audits must stay RPC-only with row level security';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger
      WHERE tgrelid = 'public.chat_turn_safety_audits'::regclass
        AND tgname = 'chat_turn_safety_audit_immutable') THEN
    RAISE EXCEPTION '098: the audit immutability trigger is missing';
  END IF;
  IF (SELECT proconfig IS NULL OR NOT proconfig::text LIKE '%search_path%'
        FROM pg_proc WHERE oid = 'private.guard_chat_turn_safety_audit()'::regprocedure) THEN
    RAISE EXCEPTION '098: the audit guard must pin search_path';
  END IF;
END
$verify$;
