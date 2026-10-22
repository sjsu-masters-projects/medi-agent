-- SAFE-002: persist every rule the deterministic safety floor can emit, and keep a thin
-- per-turn audit of turns whose urgency was raised or escalated.
--
--   1. chat_safety_alerts accepted only the two emergency rules (059), so an
--      urgent_medication_error verdict was rejected by record_chat_safety_turn (22023): the
--      patient saw the same-day copy, but no safety turn was saved and no clinician alert
--      was raised. The accepted rule set now matches app/safety/triage_floor.py, and the
--      urgency is typed: the emergency rules are 'emergency', the medication-error rule is
--      'urgent'. The RPC derives urgency from the rule, so a caller cannot mislabel it.
--   2. deliver_chat_safety_alerts words the clinician message by rule and urgency (en-US,
--      clinician-facing) for the patient's active care teams, as before. Delivery stays
--      idempotent per turn: one alert per turn id, delivered once from 'pending'.
--   3. chat_turn_safety_audits records, per turn, the rule id and version, the model's
--      urgency, the final urgency and the outcome for turns where apply_safety_override
--      raised the urgency or the model's own classification triggered an escalation. No
--      message text is stored. Clean turns are not recorded. The write is idempotent per turn.
--
-- Rule ids: emergency_symptom_keyword, emergency_mental_health_keyword and
-- urgent_medication_error come from the floor; adverse_effect_signal is the second
-- override rule in safety/escalation.py; model_classification marks an escalation the model
-- chose without any override.

-- ── 1. Alerts: full rule set, typed urgency ──────────────────────────────────────────────

ALTER TABLE public.chat_safety_alerts
  ADD COLUMN IF NOT EXISTS urgency text NOT NULL DEFAULT 'emergency';

DO $migration$
BEGIN
  ALTER TABLE public.chat_safety_alerts DROP CONSTRAINT IF EXISTS chat_safety_alerts_safety_rule_check;
  ALTER TABLE public.chat_safety_alerts DROP CONSTRAINT IF EXISTS chat_safety_alerts_rule_urgency_check;
  ALTER TABLE public.chat_safety_alerts ADD CONSTRAINT chat_safety_alerts_rule_urgency_check CHECK (
    (safety_rule IN ('emergency_symptom_keyword', 'emergency_mental_health_keyword')
       AND urgency = 'emergency')
    OR (safety_rule = 'urgent_medication_error' AND urgency = 'urgent'));
END
$migration$;

CREATE OR REPLACE FUNCTION private.guard_chat_safety_alert() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Safety evidence is immutable';
  END IF;
  IF (NEW.id, NEW.patient_id, NEW.source_message_id, NEW.assistant_message_id,
      NEW.safety_rule, NEW.urgency, NEW.rule_version, NEW.result, NEW.evaluated_at)
    IS DISTINCT FROM
     (OLD.id, OLD.patient_id, OLD.source_message_id, OLD.assistant_message_id,
      OLD.safety_rule, OLD.urgency, OLD.rule_version, OLD.result, OLD.evaluated_at)
    OR OLD.delivery_state <> 'pending' THEN
    RAISE EXCEPTION 'Safety evidence is immutable';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.record_chat_safety_turn(p_patient_id uuid, p_turn_id uuid, p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_source public.chat_messages;
  v_assistant public.chat_messages;
  v_alert public.chat_safety_alerts;
  v_rule text := p_payload->>'safety_rule';
  v_content text := p_payload->>'content';
  v_response text := p_payload->>'response_text';
  v_locale public.language_enum := (p_payload->>'language')::public.language_enum;
  v_intent text;
  v_urgency text;
  v_session text := coalesce(p_payload->>'session_id','default');
BEGIN
  v_urgency := CASE v_rule
    WHEN 'emergency_symptom_keyword' THEN 'emergency'
    WHEN 'emergency_mental_health_keyword' THEN 'emergency'
    WHEN 'urgent_medication_error' THEN 'urgent'
  END;
  IF p_patient_id IS NULL OR p_turn_id IS NULL OR v_content IS NULL OR btrim(v_content) = ''
    OR v_response IS NULL OR btrim(v_response) = '' OR v_locale IS NULL
    OR v_urgency IS NULL
    OR (p_payload->>'urgency' IS NOT NULL AND p_payload->>'urgency' <> v_urgency)
    OR p_payload->>'rule_version' IS DISTINCT FROM 'triage-floor/1'
    OR v_locale::text NOT IN ('en-US', 'es-MX')
    OR char_length(v_session) NOT BETWEEN 1 AND 64 THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid safety turn';
  END IF;
  v_intent := CASE v_rule
    WHEN 'emergency_mental_health_keyword' THEN 'mental_health'
    WHEN 'urgent_medication_error' THEN 'medication_question'
    ELSE 'symptom' END;
  -- The source row serializes repeated keys, including concurrent requests.
  INSERT INTO public.chat_messages(id, patient_id, content, role, language, audio_url, session_id)
    VALUES (p_turn_id, p_patient_id, v_content, 'user', v_locale, p_payload->>'audio_url', v_session)
    ON CONFLICT (id) DO NOTHING;
  SELECT * INTO STRICT v_source FROM public.chat_messages WHERE id=p_turn_id FOR UPDATE;
  IF v_source.patient_id <> p_patient_id OR v_source.role::text <> 'user'
    OR v_source.content <> v_content OR v_source.language <> v_locale
    OR v_source.audio_url IS DISTINCT FROM p_payload->>'audio_url'
    OR v_source.session_id IS DISTINCT FROM v_session THEN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Safety turn unavailable';
  END IF;
  SELECT * INTO v_alert FROM public.chat_safety_alerts WHERE id=p_turn_id;
  IF FOUND THEN
    SELECT * INTO STRICT v_assistant FROM public.chat_messages WHERE id=v_alert.assistant_message_id;
    IF v_alert.safety_rule <> v_rule OR v_assistant.content <> v_response THEN
      RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Safety turn identity conflict';
    END IF;
  ELSE
    INSERT INTO public.chat_messages(patient_id, content, role, language, intent, session_id)
      VALUES (p_patient_id, v_response, 'assistant', v_locale, v_intent, v_session) RETURNING * INTO v_assistant;
    INSERT INTO public.chat_safety_alerts(id, patient_id, source_message_id,
      assistant_message_id, safety_rule, urgency, rule_version)
      VALUES (p_turn_id, p_patient_id, p_turn_id, v_assistant.id, v_rule, v_urgency, 'triage-floor/1')
      RETURNING * INTO v_alert;
  END IF;
  RETURN jsonb_build_object('alert_id', v_alert.id, 'user_message', to_jsonb(v_source),
    'assistant_message', to_jsonb(v_assistant), 'delivery_state', v_alert.delivery_state,
    'urgency', v_alert.urgency);
END;
$$;

-- ── 2. Delivery: clinician wording by rule, same care-team ownership as before ──────────

CREATE OR REPLACE FUNCTION public.deliver_chat_safety_alerts(p_limit integer DEFAULT 25, p_alert_id uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_alert public.chat_safety_alerts;
  v_source public.chat_messages;
  v_team public.care_teams;
  v_recipients uuid[];
  v_intent text;
  v_subject text;
  v_body text;
  v_results jsonb := '[]'::jsonb;
BEGIN
  IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200 THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid safety batch';
  END IF;
  FOR v_alert IN SELECT * FROM public.chat_safety_alerts
    WHERE delivery_state='pending' AND (p_alert_id IS NULL OR id=p_alert_id)
    ORDER BY evaluated_at, id LIMIT p_limit FOR UPDATE SKIP LOCKED LOOP
    SELECT * INTO STRICT v_source FROM public.chat_messages
      WHERE id=v_alert.source_message_id AND patient_id=v_alert.patient_id AND role::text='user'
      FOR SHARE;
    v_recipients := ARRAY[]::uuid[];
    -- Assignment updates serialize with dispatch; multiple roles do not duplicate recipients.
    FOR v_team IN SELECT * FROM public.care_teams
      WHERE patient_id=v_alert.patient_id AND status='active' ORDER BY id FOR SHARE LOOP
      IF NOT v_team.clinician_id=ANY(v_recipients) THEN
        v_recipients := array_append(v_recipients, v_team.clinician_id);
      END IF;
    END LOOP;
    v_intent := CASE v_alert.safety_rule
      WHEN 'emergency_mental_health_keyword' THEN 'mental_health'
      WHEN 'urgent_medication_error' THEN 'medication_question'
      ELSE 'symptom' END;
    IF v_alert.safety_rule = 'urgent_medication_error' THEN
      v_subject := 'Same-day review: possible patient medication error';
      v_body := 'Possible medication error reported in chat (urgent/' || v_intent
        || '). Same-day review is recommended; this is not an emergency alert. Latest message: '
        || left(v_source.content, 280);
    ELSE
      v_subject := 'Urgent patient chat escalation';
      v_body := 'Chat escalation flagged (' || v_alert.urgency || '/' || v_intent
        || '). Latest message: ' || left(v_source.content, 280);
    END IF;
    INSERT INTO public.clinician_messages(clinician_id, patient_id, channel, subject, body)
      SELECT recipient, v_alert.patient_id, 'in_app', v_subject, v_body
      FROM unnest(v_recipients) recipient;
    UPDATE public.chat_safety_alerts SET
      delivery_state=CASE WHEN cardinality(v_recipients)>0 THEN 'delivered' ELSE 'no_recipients' END,
      clinicians_notified=cardinality(v_recipients), delivered_at=clock_timestamp()
      WHERE id=v_alert.id RETURNING * INTO v_alert;
    v_results := v_results || jsonb_build_array(jsonb_build_object('alert_id', v_alert.id,
      'delivery_state', v_alert.delivery_state, 'clinicians_notified', v_alert.clinicians_notified));
  END LOOP;
  RETURN v_results;
END;
$$;

-- ── 3. Thin per-turn audit: raised or escalated turns only, no message text ─────────────

CREATE TABLE IF NOT EXISTS public.chat_turn_safety_audits (
  turn_id uuid PRIMARY KEY,
  patient_id uuid NOT NULL REFERENCES public.patients(id),
  safety_rule text NOT NULL CHECK (safety_rule IN ('emergency_symptom_keyword',
    'emergency_mental_health_keyword', 'urgent_medication_error', 'adverse_effect_signal',
    'model_classification')),
  rule_version text NOT NULL CHECK (rule_version = 'triage-floor/1'),
  model_urgency text NOT NULL CHECK (model_urgency IN ('routine', 'urgent', 'emergency')),
  final_urgency text NOT NULL CHECK (final_urgency IN ('urgent', 'emergency')),
  outcome text NOT NULL CHECK (outcome IN ('urgency_raised', 'model_escalated')),
  escalation_required boolean NOT NULL,
  evaluated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK ((outcome = 'urgency_raised' AND model_urgency <> final_urgency
            AND safety_rule <> 'model_classification')
      OR (outcome = 'model_escalated' AND model_urgency = final_urgency
            AND safety_rule = 'model_classification'))
);
CREATE INDEX IF NOT EXISTS chat_turn_safety_audits_patient
  ON public.chat_turn_safety_audits(patient_id, evaluated_at DESC);
ALTER TABLE public.chat_turn_safety_audits ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.chat_turn_safety_audits FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION private.guard_chat_turn_safety_audit() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
  RAISE EXCEPTION 'Safety audit evidence is immutable';
END;
$$;
DROP TRIGGER IF EXISTS chat_turn_safety_audit_immutable ON public.chat_turn_safety_audits;
CREATE TRIGGER chat_turn_safety_audit_immutable BEFORE UPDATE OR DELETE
  ON public.chat_turn_safety_audits FOR EACH ROW EXECUTE FUNCTION private.guard_chat_turn_safety_audit();

-- Retry-safe: the turn id is the key, a repeat returns the stored row and changes nothing.
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
  RETURN jsonb_build_object('turn_id', v_row.turn_id, 'safety_rule', v_row.safety_rule,
    'outcome', v_row.outcome);
END;
$$;

REVOKE ALL ON FUNCTION private.guard_chat_safety_alert() FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION private.guard_chat_turn_safety_audit() FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.record_chat_safety_turn(uuid, uuid, jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.deliver_chat_safety_alerts(integer, uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.record_chat_turn_safety_audit(uuid, uuid, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_chat_safety_turn(uuid, uuid, jsonb),
  public.deliver_chat_safety_alerts(integer, uuid),
  public.record_chat_turn_safety_audit(uuid, uuid, jsonb) TO service_role;

DO $verify$
DECLARE v_function text;
BEGIN
  FOREACH v_function IN ARRAY ARRAY[
    'public.record_chat_safety_turn(uuid,uuid,jsonb)',
    'public.deliver_chat_safety_alerts(integer,uuid)',
    'public.record_chat_turn_safety_audit(uuid,uuid,jsonb)'] LOOP
    IF has_function_privilege('anon', v_function, 'EXECUTE')
       OR has_function_privilege('authenticated', v_function, 'EXECUTE')
       OR NOT has_function_privilege('service_role', v_function, 'EXECUTE') THEN
      RAISE EXCEPTION '097: wrong execute grants on %', v_function;
    END IF;
    IF (SELECT proconfig IS NULL OR NOT proconfig::text LIKE '%search_path%'
          FROM pg_proc WHERE oid = v_function::regprocedure) THEN
      RAISE EXCEPTION '097: % must pin search_path', v_function;
    END IF;
  END LOOP;
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.chat_turn_safety_audits'::regclass)
     OR has_table_privilege('anon', 'public.chat_turn_safety_audits', 'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('authenticated', 'public.chat_turn_safety_audits', 'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('service_role', 'public.chat_turn_safety_audits', 'SELECT,INSERT,UPDATE,DELETE') THEN
    RAISE EXCEPTION '097: chat_turn_safety_audits must be RPC-only';
  END IF;
  IF has_table_privilege('anon', 'public.chat_safety_alerts', 'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('authenticated', 'public.chat_safety_alerts', 'SELECT,INSERT,UPDATE,DELETE') THEN
    RAISE EXCEPTION '097: chat_safety_alerts must stay backend-only';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
      WHERE conrelid = 'public.chat_safety_alerts'::regclass
        AND conname = 'chat_safety_alerts_rule_urgency_check'
        AND pg_get_constraintdef(oid) LIKE '%urgent_medication_error%') THEN
    RAISE EXCEPTION '097: the alert rule/urgency constraint is missing';
  END IF;
END
$verify$;
