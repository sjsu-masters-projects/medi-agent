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

-- Preserve the saved model intent rather than describing every model alert as a symptom.
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
    IF v_alert.safety_rule IN ('model_classification','adverse_effect_signal') THEN
      SELECT coalesce(intent,'general') INTO v_intent FROM public.chat_messages
        WHERE id=v_alert.assistant_message_id;
    END IF;
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
