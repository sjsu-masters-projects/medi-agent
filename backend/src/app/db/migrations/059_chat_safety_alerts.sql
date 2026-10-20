-- Safety alerts are independent of symptom reports and ordinary ADR work.
-- Trusted RPCs atomically retain an ordinary chat turn and its pending alert.
CREATE TABLE public.chat_safety_alerts (
  id uuid PRIMARY KEY,
  patient_id uuid NOT NULL REFERENCES public.patients(id),
  source_message_id uuid NOT NULL UNIQUE REFERENCES public.chat_messages(id),
  assistant_message_id uuid NOT NULL UNIQUE REFERENCES public.chat_messages(id),
  safety_rule text NOT NULL CHECK (safety_rule IN
    ('emergency_symptom_keyword', 'emergency_mental_health_keyword')),
  rule_version text NOT NULL CHECK (rule_version = 'triage-floor/1'),
  result text NOT NULL DEFAULT 'interrupted_safety' CHECK (result = 'interrupted_safety'),
  evaluated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  delivery_state text NOT NULL DEFAULT 'pending' CHECK
    (delivery_state IN ('pending', 'delivered', 'no_recipients')),
  clinicians_notified integer NOT NULL DEFAULT 0 CHECK (clinicians_notified >= 0),
  delivered_at timestamptz,
  CHECK ((delivery_state = 'pending' AND delivered_at IS NULL AND clinicians_notified = 0)
    OR (delivery_state = 'delivered' AND delivered_at IS NOT NULL AND clinicians_notified > 0)
    OR (delivery_state = 'no_recipients' AND delivered_at IS NOT NULL AND clinicians_notified = 0))
);
CREATE INDEX chat_safety_alerts_pending ON public.chat_safety_alerts(evaluated_at, id)
  WHERE delivery_state = 'pending';
ALTER TABLE public.chat_safety_alerts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.chat_safety_alerts FROM PUBLIC, anon, authenticated, service_role;

CREATE FUNCTION private.guard_chat_safety_alert() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Safety evidence is immutable';
  END IF;
  IF (NEW.id, NEW.patient_id, NEW.source_message_id, NEW.assistant_message_id,
      NEW.safety_rule, NEW.rule_version, NEW.result, NEW.evaluated_at)
    IS DISTINCT FROM
     (OLD.id, OLD.patient_id, OLD.source_message_id, OLD.assistant_message_id,
      OLD.safety_rule, OLD.rule_version, OLD.result, OLD.evaluated_at)
    OR OLD.delivery_state <> 'pending' THEN
    RAISE EXCEPTION 'Safety evidence is immutable';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER chat_safety_alert_immutable BEFORE UPDATE OR DELETE
  ON public.chat_safety_alerts FOR EACH ROW EXECUTE FUNCTION private.guard_chat_safety_alert();

CREATE FUNCTION private.guard_chat_safety_message() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM public.chat_safety_alerts
    WHERE source_message_id=OLD.id OR assistant_message_id=OLD.id) THEN
    RAISE EXCEPTION 'Safety source messages are immutable';
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER chat_safety_message_immutable BEFORE UPDATE OR DELETE
  ON public.chat_messages FOR EACH ROW EXECUTE FUNCTION private.guard_chat_safety_message();

CREATE FUNCTION public.record_chat_safety_turn(p_patient_id uuid, p_turn_id uuid, p_payload jsonb)
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
  v_session text := coalesce(p_payload->>'session_id','default');
BEGIN
  IF p_patient_id IS NULL OR p_turn_id IS NULL OR v_content IS NULL OR btrim(v_content) = ''
    OR v_response IS NULL OR btrim(v_response) = '' OR v_locale IS NULL
    OR v_rule IS NULL OR v_rule NOT IN ('emergency_symptom_keyword', 'emergency_mental_health_keyword')
    OR p_payload->>'rule_version' IS DISTINCT FROM 'triage-floor/1'
    OR v_locale::text NOT IN ('en-US', 'es-MX')
    OR char_length(v_session) NOT BETWEEN 1 AND 64 THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid safety turn';
  END IF;
  v_intent := CASE WHEN v_rule='emergency_mental_health_keyword' THEN 'mental_health' ELSE 'symptom' END;
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
      assistant_message_id, safety_rule, rule_version)
      VALUES (p_turn_id, p_patient_id, p_turn_id, v_assistant.id, v_rule, 'triage-floor/1')
      RETURNING * INTO v_alert;
  END IF;
  RETURN jsonb_build_object('alert_id', v_alert.id, 'user_message', to_jsonb(v_source),
    'assistant_message', to_jsonb(v_assistant), 'delivery_state', v_alert.delivery_state);
END;
$$;

CREATE FUNCTION public.deliver_chat_safety_alerts(p_limit integer DEFAULT 25, p_alert_id uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_alert public.chat_safety_alerts;
  v_source public.chat_messages;
  v_team public.care_teams;
  v_recipients uuid[];
  v_intent text;
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
    v_intent := CASE WHEN v_alert.safety_rule='emergency_mental_health_keyword'
      THEN 'mental_health' ELSE 'symptom' END;
    INSERT INTO public.clinician_messages(clinician_id, patient_id, channel, subject, body)
      SELECT recipient, v_alert.patient_id, 'in_app', 'Urgent patient chat escalation',
        'Chat escalation flagged (emergency/' || v_intent || '). Latest message: ' || left(v_source.content, 280)
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
REVOKE ALL ON FUNCTION private.guard_chat_safety_alert() FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION private.guard_chat_safety_message() FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.record_chat_safety_turn(uuid, uuid, jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.deliver_chat_safety_alerts(integer, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_chat_safety_turn(uuid, uuid, jsonb),
  public.deliver_chat_safety_alerts(integer, uuid) TO service_role;
