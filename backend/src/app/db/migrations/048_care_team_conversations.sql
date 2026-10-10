-- Human threads are separate from AI chat and operational notifications.
-- Backend-only RPCs authorize against fresh assignments, not service-role RLS bypass.
CREATE TABLE public.care_conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  care_team_id uuid NOT NULL REFERENCES public.care_teams(id),
  patient_id uuid NOT NULL REFERENCES public.patients(id),
  clinician_id uuid NOT NULL REFERENCES public.clinicians(id),
  clinic_id uuid NOT NULL REFERENCES public.clinics(id),
  clinic_name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  last_message_at timestamptz,
  UNIQUE (care_team_id, patient_id, clinician_id, clinic_id)
);
CREATE INDEX care_conversations_patient ON public.care_conversations(patient_id);
CREATE INDEX care_conversations_clinician ON public.care_conversations(clinician_id);

CREATE TABLE public.care_conversation_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL REFERENCES public.care_conversations(id),
  sender_id uuid NOT NULL REFERENCES auth.users(id),
  sender_role text NOT NULL CHECK (sender_role IN ('patient', 'clinician')),
  sender_name text NOT NULL,
  body text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 4000
    AND body = regexp_replace(body, '^[[:space:]]+|[[:space:]]+$', '', 'g')),
  client_message_id uuid NOT NULL,
  created_at timestamptz NOT NULL,
  UNIQUE (sender_id, client_message_id)
);
CREATE INDEX care_conversation_messages_page
  ON public.care_conversation_messages(conversation_id, created_at DESC, id DESC);

CREATE TABLE public.care_conversation_reads (
  conversation_id uuid NOT NULL REFERENCES public.care_conversations(id),
  actor_id uuid NOT NULL REFERENCES auth.users(id),
  last_message_id uuid NOT NULL REFERENCES public.care_conversation_messages(id),
  last_message_at timestamptz NOT NULL,
  read_at timestamptz NOT NULL,
  PRIMARY KEY (conversation_id, actor_id)
);
CREATE INDEX care_conversation_reads_message ON public.care_conversation_reads(last_message_id);
CREATE INDEX care_conversation_reads_actor ON public.care_conversation_reads(actor_id);

CREATE TABLE public.care_conversation_audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL REFERENCES public.care_conversations(id),
  actor_id uuid NOT NULL REFERENCES auth.users(id),
  action text NOT NULL CHECK (action IN ('opened', 'sent', 'read')),
  message_id uuid REFERENCES public.care_conversation_messages(id),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX care_conversation_audit_thread ON public.care_conversation_audit_events(conversation_id, created_at);
CREATE INDEX care_conversation_audit_actor ON public.care_conversation_audit_events(actor_id);
CREATE INDEX care_conversation_audit_message ON public.care_conversation_audit_events(message_id);

ALTER TABLE public.care_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.care_conversation_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.care_conversation_reads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.care_conversation_audit_events ENABLE ROW LEVEL SECURITY;
-- There is intentionally no browser policy/grant: both portals use the API.
REVOKE ALL ON public.care_conversations, public.care_conversation_messages,
  public.care_conversation_reads, public.care_conversation_audit_events FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE ON public.care_conversations, public.care_conversation_reads TO service_role;
GRANT SELECT, INSERT ON public.care_conversation_messages, public.care_conversation_audit_events TO service_role;

CREATE FUNCTION private.care_conversation_summary(p_id uuid, p_actor uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path = '' AS $$
  SELECT jsonb_build_object(
    'id', t.id, 'patient_id', t.patient_id, 'clinician_id', t.clinician_id,
    'patient_name', concat_ws(' ', p.first_name, p.last_name),
    'clinician_name', concat_ws(' ', c.first_name, c.last_name),
    'clinic_name', t.clinic_name, 'last_message_at', t.last_message_at,
    'last_message_preview', (SELECT left(m.body, 160) FROM public.care_conversation_messages m
      WHERE m.conversation_id=t.id ORDER BY m.created_at DESC, m.id DESC LIMIT 1),
    'unread_count', (SELECT count(*) FROM public.care_conversation_messages m
      WHERE m.conversation_id=t.id AND m.sender_id<>p_actor AND
        (r.last_message_id IS NULL OR (m.created_at,m.id)>(r.last_message_at,r.last_message_id))),
    'writable', true)
  FROM public.care_conversations t JOIN public.patients p ON p.id=t.patient_id
    JOIN public.clinicians c ON c.id=t.clinician_id
    LEFT JOIN public.care_conversation_reads r ON r.conversation_id=t.id AND r.actor_id=p_actor
  WHERE t.id=p_id;
$$;

CREATE FUNCTION private.care_conversation_message(p_id uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path = '' AS $$
  SELECT jsonb_build_object('id', id, 'conversation_id', conversation_id,
    'sender_id', sender_id, 'sender_role', sender_role, 'sender_name', sender_name,
    'body', body, 'created_at', created_at)
  FROM public.care_conversation_messages WHERE id=p_id;
$$;

-- Locks the assignment itself so ordinary status UPDATE/DELETE serializes with
-- every read/write. Profile/clinic locks also protect reassignment during a send.
CREATE FUNCTION private.lock_care_conversation_pair(p_team uuid, p_actor uuid, p_role text)
RETURNS public.care_teams LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_team public.care_teams;
BEGIN
  SELECT t.* INTO v_team FROM public.care_teams t
    JOIN public.patients p ON p.id=t.patient_id
    JOIN public.clinicians c ON c.id=t.clinician_id
    JOIN public.clinics cl ON cl.id=c.clinic_id
    WHERE t.id=p_team AND t.status='active' AND cl.status='active'
      AND ((p_role='patient' AND t.patient_id=p_actor) OR
           (p_role='clinician' AND t.clinician_id=p_actor))
    FOR SHARE OF t, p, c, cl;
  IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Conversation unavailable'; END IF;
  RETURN v_team;
END;
$$;

CREATE FUNCTION public.care_conversation_operation(
  p_actor_id uuid, p_actor_role text, p_action text, p_payload jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_team public.care_teams;
  v_thread public.care_conversations;
  v_message public.care_conversation_messages;
  v_marker public.care_conversation_reads;
  v_id uuid; v_team_id uuid; v_cursor public.care_conversation_messages;
  v_key uuid; v_body text; v_name text; v_clinic uuid; v_clinic_name text;
  v_limit int; v_items jsonb; v_next uuid; v_result jsonb := '[]'::jsonb;
  v_created boolean := false;
BEGIN
  IF current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION USING ERRCODE='40001', MESSAGE='Conversation operation requires read committed';
  END IF;
  IF p_actor_id IS NULL OR p_actor_role NOT IN ('patient','clinician') OR p_actor_role IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Conversation unavailable';
  END IF;
  IF p_action IN ('recipients','list') THEN
    -- Consistent assignment order for multi-team reads; each pair is checked anew.
    FOR v_team_id IN SELECT t.id FROM public.care_teams t WHERE t.status='active'
      AND ((p_actor_role='patient' AND t.patient_id=p_actor_id) OR
           (p_actor_role='clinician' AND t.clinician_id=p_actor_id)) ORDER BY t.id LOOP
      BEGIN
        v_team := private.lock_care_conversation_pair(v_team_id,p_actor_id,p_actor_role);
      EXCEPTION WHEN insufficient_privilege THEN CONTINUE;
      END;
      IF p_action='recipients' THEN
        SELECT jsonb_build_object('id', CASE WHEN p_actor_role='patient' THEN c.id ELSE p.id END,
          'name', CASE WHEN p_actor_role='patient' THEN concat_ws(' ',c.first_name,c.last_name)
                      ELSE concat_ws(' ',p.first_name,p.last_name) END,
          'role', CASE WHEN p_actor_role='patient' THEN c.role::text ELSE 'patient' END,
          'clinic_name', cl.display_name) INTO v_items
          FROM public.patients p JOIN public.clinicians c ON c.id=v_team.clinician_id
            JOIN public.clinics cl ON cl.id=c.clinic_id WHERE p.id=v_team.patient_id;
        v_result := v_result || jsonb_build_array(v_items);
      ELSE
        SELECT t.* INTO v_thread FROM public.care_conversations t JOIN public.clinicians c
          ON c.id=t.clinician_id WHERE t.care_team_id=v_team.id
          AND t.patient_id=v_team.patient_id AND t.clinician_id=v_team.clinician_id
          AND t.clinic_id=c.clinic_id;
        IF FOUND THEN
          v_result := v_result || jsonb_build_array(private.care_conversation_summary(v_thread.id,p_actor_id));
        END IF;
      END IF;
    END LOOP;
    IF p_action='list' THEN
      -- Presentation order is independent of the consistent assignment lock order.
      SELECT coalesce(jsonb_agg(value ORDER BY (value->>'last_message_at')::timestamptz DESC NULLS LAST,
        (value->>'id')::uuid), '[]'::jsonb) INTO v_result FROM jsonb_array_elements(v_result);
    END IF;
    RETURN v_result;
  END IF;
  -- Sender-scoped key locks precede assignment/thread locks, including cross-thread retries.
  IF p_action='send' THEN
    v_key := (p_payload->>'client_message_id')::uuid;
    v_body := regexp_replace(p_payload->>'body', '^[[:space:]]+|[[:space:]]+$', '', 'g');
    IF v_key IS NULL OR v_body IS NULL OR char_length(v_body) NOT BETWEEN 1 AND 4000 THEN
      RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid conversation request';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(p_actor_id::text || ':' || v_key::text,0));
  END IF;
  IF p_action='open' THEN
    SELECT t.id INTO v_team_id FROM public.care_teams t WHERE t.status='active' AND
      ((p_actor_role='patient' AND t.patient_id=p_actor_id AND t.clinician_id=(p_payload->>'recipient_id')::uuid)
       OR (p_actor_role='clinician' AND t.clinician_id=p_actor_id AND t.patient_id=(p_payload->>'recipient_id')::uuid));
  ELSE
    SELECT t.care_team_id INTO v_team_id FROM public.care_conversations t
      WHERE t.id=(p_payload->>'conversation_id')::uuid;
  END IF;
  v_team := private.lock_care_conversation_pair(v_team_id,p_actor_id,p_actor_role);
  SELECT c.clinic_id, cl.display_name INTO v_clinic,v_clinic_name FROM public.clinicians c
    JOIN public.clinics cl ON cl.id=c.clinic_id WHERE c.id=v_team.clinician_id;
  IF p_action='open' THEN
    INSERT INTO public.care_conversations(care_team_id,patient_id,clinician_id,clinic_id,clinic_name)
      VALUES(v_team.id,v_team.patient_id,v_team.clinician_id,v_clinic,v_clinic_name)
      ON CONFLICT(care_team_id,patient_id,clinician_id,clinic_id) DO NOTHING RETURNING id INTO v_id;
    v_created := FOUND;
    SELECT * INTO v_thread FROM public.care_conversations WHERE care_team_id=v_team.id
      AND patient_id=v_team.patient_id AND clinician_id=v_team.clinician_id
      AND clinic_id=v_clinic FOR UPDATE;
  ELSE
    SELECT * INTO v_thread FROM public.care_conversations
      WHERE id=(p_payload->>'conversation_id')::uuid FOR UPDATE;
  END IF;
  IF NOT FOUND OR v_thread.patient_id<>v_team.patient_id OR v_thread.clinician_id<>v_team.clinician_id
    OR v_thread.clinic_id<>v_clinic THEN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Conversation unavailable';
  END IF;
  IF p_action='open' THEN
    IF v_created THEN
      INSERT INTO public.care_conversation_audit_events(conversation_id,actor_id,action)
        VALUES(v_thread.id,p_actor_id,'opened');
    END IF;
    RETURN private.care_conversation_summary(v_thread.id,p_actor_id);
  ELSIF p_action='messages' THEN
    v_limit := coalesce((p_payload->>'limit')::int,50);
    IF v_limit NOT BETWEEN 1 AND 100 THEN
      RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid conversation request';
    END IF;
    IF p_payload->>'before' IS NOT NULL THEN
      SELECT * INTO v_cursor FROM public.care_conversation_messages
        WHERE id=(p_payload->>'before')::uuid AND conversation_id=v_thread.id;
      IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid conversation request'; END IF;
    END IF;
    SELECT coalesce(jsonb_agg(private.care_conversation_message(m.id) ORDER BY m.created_at,m.id),'[]'::jsonb)
      INTO v_items FROM (SELECT * FROM public.care_conversation_messages
        WHERE conversation_id=v_thread.id AND (v_cursor.id IS NULL OR (created_at,id)<(v_cursor.created_at,v_cursor.id))
        ORDER BY created_at DESC,id DESC LIMIT v_limit) m;
    IF jsonb_array_length(v_items)>0 THEN
      SELECT * INTO v_cursor FROM public.care_conversation_messages WHERE id=(v_items->0->>'id')::uuid;
      IF EXISTS(SELECT 1 FROM public.care_conversation_messages WHERE conversation_id=v_thread.id
        AND (created_at,id)<(v_cursor.created_at,v_cursor.id)) THEN v_next := v_cursor.id; END IF;
    END IF;
    RETURN jsonb_build_object('items',v_items,'next_cursor',v_next);
  ELSIF p_action='send' THEN
    SELECT * INTO v_message FROM public.care_conversation_messages
      WHERE sender_id=p_actor_id AND client_message_id=v_key;
    IF FOUND THEN
      IF v_message.conversation_id<>v_thread.id OR v_message.body<>v_body THEN
        RAISE EXCEPTION USING ERRCODE='23505', MESSAGE='Message idempotency mismatch';
      END IF;
      RETURN private.care_conversation_message(v_message.id);
    END IF;
    IF p_actor_role='patient' THEN
      SELECT concat_ws(' ',first_name,last_name) INTO v_name FROM public.patients WHERE id=p_actor_id;
    ELSE
      SELECT concat_ws(' ',first_name,last_name) INTO v_name FROM public.clinicians WHERE id=p_actor_id;
    END IF;
    -- Transaction start timestamps can backdate waiting sends below a read marker.
    INSERT INTO public.care_conversation_messages(conversation_id,sender_id,sender_role,sender_name,body,client_message_id,created_at)
      VALUES(v_thread.id,p_actor_id,p_actor_role,v_name,v_body,v_key,
        greatest(clock_timestamp(),v_thread.last_message_at + interval '1 microsecond')) RETURNING * INTO v_message;
    UPDATE public.care_conversations SET last_message_at=v_message.created_at WHERE id=v_thread.id;
    INSERT INTO public.care_conversation_audit_events(conversation_id,actor_id,action,message_id)
      VALUES(v_thread.id,p_actor_id,'sent',v_message.id);
    RETURN private.care_conversation_message(v_message.id);
  ELSIF p_action='read' THEN
    SELECT * INTO v_message FROM public.care_conversation_messages
      WHERE id=(p_payload->>'last_message_id')::uuid AND conversation_id=v_thread.id;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid conversation request'; END IF;
    SELECT * INTO v_marker FROM public.care_conversation_reads WHERE conversation_id=v_thread.id AND actor_id=p_actor_id;
    IF NOT FOUND OR (v_message.created_at,v_message.id)>(v_marker.last_message_at,v_marker.last_message_id) THEN
      INSERT INTO public.care_conversation_reads(conversation_id,actor_id,last_message_id,last_message_at,read_at)
        VALUES(v_thread.id,p_actor_id,v_message.id,v_message.created_at,clock_timestamp())
        ON CONFLICT(conversation_id,actor_id) DO UPDATE SET last_message_id=EXCLUDED.last_message_id,
          last_message_at=EXCLUDED.last_message_at,read_at=EXCLUDED.read_at RETURNING * INTO v_marker;
      INSERT INTO public.care_conversation_audit_events(conversation_id,actor_id,action,message_id)
        VALUES(v_thread.id,p_actor_id,'read',v_message.id);
    END IF;
    RETURN jsonb_build_object('read_at',v_marker.read_at);
  END IF;
  RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid conversation request';
END;
$$;

REVOKE ALL ON FUNCTION public.care_conversation_operation(uuid,text,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.care_conversation_operation(uuid,text,text,jsonb) TO service_role;
REVOKE ALL ON FUNCTION private.care_conversation_summary(uuid,uuid), private.care_conversation_message(uuid),
  private.lock_care_conversation_pair(uuid,uuid,text) FROM PUBLIC,anon,authenticated;
GRANT USAGE ON SCHEMA private TO service_role;
GRANT EXECUTE ON FUNCTION private.care_conversation_summary(uuid,uuid), private.care_conversation_message(uuid),
  private.lock_care_conversation_pair(uuid,uuid,text) TO service_role;
