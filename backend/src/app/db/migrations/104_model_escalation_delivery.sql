-- SAFE-003: model/override escalations share the durable safety delivery queue.
-- Existing message content is never rewritten. Browser roles cannot register alerts.
ALTER TABLE public.chat_safety_alerts DROP CONSTRAINT chat_safety_alerts_rule_urgency_check;
ALTER TABLE public.chat_safety_alerts ADD CONSTRAINT chat_safety_alerts_rule_urgency_check CHECK (
  (safety_rule IN ('emergency_symptom_keyword','emergency_mental_health_keyword') AND urgency='emergency')
  OR (safety_rule='urgent_medication_error' AND urgency='urgent')
  OR (safety_rule IN ('adverse_effect_signal','model_classification') AND urgency IN ('urgent','emergency')));
ALTER TABLE public.chat_safety_alerts DROP CONSTRAINT chat_safety_alerts_result_check;
ALTER TABLE public.chat_safety_alerts ADD CONSTRAINT chat_safety_alerts_result_check
  CHECK (result IN ('interrupted_safety','escalation_recommended'));

CREATE OR REPLACE FUNCTION public.record_model_chat_safety_alert(
  p_patient_id uuid,p_turn_id uuid,p_payload jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE
  source public.chat_messages;
  reply public.chat_messages;
  alert public.chat_safety_alerts;
BEGIN
  IF p_patient_id IS NULL OR p_turn_id IS NULL OR p_payload IS NULL
    OR jsonb_typeof(p_payload)<>'object'
    OR p_payload->>'safety_rule' IS NULL
    OR p_payload->>'safety_rule' NOT IN ('model_classification','adverse_effect_signal')
    OR p_payload->>'urgency' IS NULL OR p_payload->>'urgency' NOT IN ('urgent','emergency')
    OR p_payload->>'rule_version' IS DISTINCT FROM 'triage-floor/1' THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid escalation';
  END IF;
  -- Lock the source to serialize repeated/concurrent registrations of the same turn.
  SELECT * INTO source FROM public.chat_messages WHERE id=p_turn_id FOR UPDATE;
  IF NOT FOUND OR source.patient_id<>p_patient_id OR source.role::text<>'user' THEN
    RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Escalation unavailable';
  END IF;
  SELECT * INTO reply FROM public.chat_messages
    WHERE id=(p_payload->>'assistant_message_id')::uuid FOR SHARE;
  IF NOT FOUND OR reply.patient_id<>p_patient_id OR reply.role::text<>'assistant'
    OR reply.session_id IS DISTINCT FROM source.session_id THEN
    RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Escalation unavailable';
  END IF;
  INSERT INTO public.chat_safety_alerts(id,patient_id,source_message_id,assistant_message_id,
    safety_rule,urgency,rule_version,result)
    VALUES(p_turn_id,p_patient_id,p_turn_id,reply.id,p_payload->>'safety_rule',
      p_payload->>'urgency','triage-floor/1','escalation_recommended')
    ON CONFLICT(id) DO NOTHING;
  SELECT * INTO STRICT alert FROM public.chat_safety_alerts WHERE id=p_turn_id;
  IF alert.assistant_message_id<>reply.id OR alert.safety_rule<>p_payload->>'safety_rule'
    OR alert.urgency<>p_payload->>'urgency' OR alert.result<>'escalation_recommended' THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Escalation identity conflict';
  END IF;
  RETURN jsonb_build_object('alert_id',alert.id,'safety_rule',alert.safety_rule,
    'urgency',alert.urgency,'delivery_state',alert.delivery_state);
END; $$;
REVOKE ALL ON FUNCTION public.record_model_chat_safety_alert(uuid,uuid,jsonb)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.record_model_chat_safety_alert(uuid,uuid,jsonb) TO service_role;
