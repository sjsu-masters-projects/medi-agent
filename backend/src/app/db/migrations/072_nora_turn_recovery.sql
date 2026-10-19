-- PAT-001-A / PAT-004: server-owned turn identity, bounded execution and source snapshot.
CREATE TABLE IF NOT EXISTS public.chat_turns (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 patient_id uuid NOT NULL REFERENCES public.patients(id) ON DELETE CASCADE,
 session_id text NOT NULL CHECK(session_id ~ '^[A-Za-z0-9_-]{1,64}$'),
 client_message_id uuid NOT NULL,
 request_hash text NOT NULL CHECK(request_hash ~ '^[a-f0-9]{64}$'),
 user_message_id uuid NOT NULL UNIQUE REFERENCES public.chat_messages(id) ON DELETE CASCADE,
 assistant_message_id uuid UNIQUE REFERENCES public.chat_messages(id) ON DELETE SET NULL,
 document_context jsonb CHECK(document_context IS NULL OR jsonb_typeof(document_context)='object'),
 status text NOT NULL DEFAULT 'processing' CHECK(status IN ('processing','completed','failed','interrupted')),
 lease uuid NOT NULL DEFAULT gen_random_uuid(),
 deadline_at timestamptz NOT NULL,
 actions_started boolean NOT NULL DEFAULT false,
 attempt integer NOT NULL DEFAULT 1 CHECK(attempt BETWEEN 1 AND 3),
 failure_code text CHECK(failure_code IN ('deadline','interrupted','processing_failed','action_uncertain')),
 dismissed_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(patient_id,client_message_id)
);
CREATE INDEX IF NOT EXISTS chat_turns_patient_session ON public.chat_turns(patient_id,session_id,created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS chat_turns_one_processing ON public.chat_turns(patient_id,session_id) WHERE status='processing';
ALTER TABLE public.chat_turns ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.chat_turns FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT,UPDATE ON public.chat_turns TO service_role;

-- Document text is execution-only. Retain identity/version, never a duplicate summary.
UPDATE public.chat_turns SET document_context=document_context-'summary'
 WHERE document_context ? 'summary';

CREATE OR REPLACE FUNCTION public.chat_turn_operation(p_patient uuid,p_session text,p_action text,p_payload jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE t public.chat_turns; u public.chat_messages; a public.chat_messages;
 d public.documents; snapshot jsonb; result jsonb; seconds integer;
BEGIN
 IF p_session !~ '^[A-Za-z0-9_-]{1,64}$' OR NOT EXISTS(SELECT 1 FROM public.patients WHERE id=p_patient) THEN
  RAISE EXCEPTION 'CHAT_TURN_UNAVAILABLE' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('chat_turn:'||p_patient::text||':'||p_session,0));
 UPDATE public.chat_turns SET status='interrupted',updated_at=clock_timestamp(),
  failure_code=CASE WHEN actions_started THEN 'action_uncertain' ELSE 'deadline' END
  WHERE patient_id=p_patient AND session_id=p_session AND status='processing' AND deadline_at<=clock_timestamp();
 IF p_action='recover' THEN
  SELECT coalesce(jsonb_agg(to_jsonb(s)-'lease'-'request_hash'),'[]') INTO result
   FROM (SELECT t0.*,to_jsonb(m) user_message FROM public.chat_turns t0 JOIN public.chat_messages m ON m.id=t0.user_message_id
     AND m.patient_id=t0.patient_id AND m.session_id=t0.session_id AND m.role::text='user'
    WHERE t0.patient_id=p_patient AND t0.session_id=p_session AND t0.dismissed_at IS NULL
    ORDER BY (t0.status='processing') DESC,(t0.status<>'completed') DESC,t0.created_at DESC LIMIT 20) s;
  RETURN jsonb_build_object('items',result);
 END IF;
 IF p_action='dismiss' THEN
  UPDATE public.chat_turns SET dismissed_at=clock_timestamp()
   WHERE patient_id=p_patient AND session_id=p_session
    AND client_message_id=(p_payload->>'client_message_id')::uuid AND status IN ('failed','interrupted');
  RETURN jsonb_build_object('accepted',FOUND);
 END IF;
 IF p_action='begin' THEN
  seconds:=greatest(10,least(120,coalesce((p_payload->>'timeout_seconds')::integer,45)));
  SELECT * INTO t FROM public.chat_turns WHERE patient_id=p_patient AND client_message_id=(p_payload->>'client_message_id')::uuid FOR UPDATE;
  IF FOUND THEN
   IF t.session_id<>p_session OR t.request_hash<>p_payload->>'request_hash' THEN
    RAISE EXCEPTION 'CHAT_TURN_CONFLICT' USING ERRCODE='22023'; END IF;
   SELECT * INTO u FROM public.chat_messages WHERE id=t.user_message_id
     AND patient_id=p_patient AND session_id=p_session AND role::text='user';
   IF NOT FOUND THEN RAISE EXCEPTION 'CHAT_TURN_UNAVAILABLE' USING ERRCODE='42501'; END IF;
   IF t.status='completed' THEN
    SELECT * INTO a FROM public.chat_messages WHERE id=t.assistant_message_id
      AND patient_id=p_patient AND session_id=p_session AND role::text='assistant';
    IF NOT FOUND THEN RAISE EXCEPTION 'CHAT_TURN_UNAVAILABLE' USING ERRCODE='42501'; END IF;
    RETURN jsonb_build_object('execute',false,'turn',to_jsonb(t)-'lease'-'request_hash','user_message',to_jsonb(u),'assistant_message',to_jsonb(a));
   END IF;
   IF t.status='processing' OR t.actions_started OR t.attempt>=3 OR t.dismissed_at IS NOT NULL THEN
    RETURN jsonb_build_object('execute',false,'turn',to_jsonb(t)-'lease'-'request_hash','user_message',to_jsonb(u)); END IF;
  END IF;
  IF EXISTS(SELECT 1 FROM public.chat_turns WHERE patient_id=p_patient AND session_id=p_session AND status='processing') THEN
   RAISE EXCEPTION 'CHAT_TURN_BUSY' USING ERRCODE='22023'; END IF;
  IF nullif(p_payload->>'document_id','') IS NOT NULL THEN
   SELECT * INTO d FROM public.documents WHERE id=(p_payload->>'document_id')::uuid AND patient_id=p_patient FOR KEY SHARE;
   IF NOT FOUND OR d.parse_status::text<>'completed' OR nullif(btrim(d.ai_summary),'') IS NULL THEN
    RAISE EXCEPTION 'CHAT_DOCUMENT_UNAVAILABLE' USING ERRCODE='22023'; END IF;
   snapshot:=jsonb_build_object('id',d.id,'file_name',d.file_name,'display_title',d.display_title,
    'document_type',d.document_type,'summary',left(d.ai_summary,6000),'parse_status',d.parse_status,
    'context_version',md5(d.ai_summary));
   IF t.id IS NOT NULL AND t.document_context->>'context_version' IS DISTINCT FROM snapshot->>'context_version' THEN
    RAISE EXCEPTION 'CHAT_DOCUMENT_CHANGED' USING ERRCODE='22023'; END IF;
  END IF;
  IF t.id IS NULL THEN
   IF length(btrim(p_payload->>'content')) NOT BETWEEN 1 AND 8000 OR p_payload->>'language' NOT IN ('en-US','es-MX') THEN
    RAISE EXCEPTION 'CHAT_TURN_INVALID' USING ERRCODE='22023'; END IF;
   INSERT INTO public.chat_messages(patient_id,session_id,content,role,language,audio_url)
    VALUES(p_patient,p_session,p_payload->>'content','user',(p_payload->>'language')::public.language_enum,p_payload->>'audio_url') RETURNING * INTO u;
   INSERT INTO public.chat_turns(patient_id,session_id,client_message_id,request_hash,user_message_id,document_context,deadline_at)
    VALUES(p_patient,p_session,(p_payload->>'client_message_id')::uuid,p_payload->>'request_hash',u.id,snapshot-'summary',
     clock_timestamp()+make_interval(secs=>seconds)) RETURNING * INTO t;
  ELSE
   UPDATE public.chat_turns SET status='processing',failure_code=NULL,lease=gen_random_uuid(),attempt=attempt+1,
    deadline_at=clock_timestamp()+make_interval(secs=>seconds),updated_at=clock_timestamp()
    WHERE id=t.id RETURNING * INTO t;
  END IF;
  RETURN jsonb_build_object('execute',true,'turn',(to_jsonb(t)-'request_hash')||jsonb_build_object('document_context',snapshot),'user_message',to_jsonb(u));
 END IF;
 SELECT * INTO t FROM public.chat_turns WHERE patient_id=p_patient AND session_id=p_session
  AND id=(p_payload->>'id')::uuid AND lease=(p_payload->>'lease')::uuid AND status='processing' FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('accepted',false); END IF;
 IF p_action='actions' THEN
  UPDATE public.chat_turns SET actions_started=true,updated_at=clock_timestamp() WHERE id=t.id;
 ELSIF p_action='complete' THEN
  INSERT INTO public.chat_messages(id,patient_id,session_id,role,content,language,intent,attachments)
   VALUES((p_payload->>'message_id')::uuid,p_patient,p_session,'assistant',p_payload->>'content',(p_payload->>'language')::public.language_enum,
    p_payload->>'intent',coalesce(p_payload->'attachments','[]'::jsonb)) RETURNING * INTO a;
  UPDATE public.chat_turns SET status='completed',assistant_message_id=a.id,updated_at=clock_timestamp() WHERE id=t.id;
  RETURN jsonb_build_object('accepted',true,'message',to_jsonb(a));
 ELSIF p_action IN ('failed','interrupted') THEN
  UPDATE public.chat_turns SET status=p_action,updated_at=clock_timestamp(),
   failure_code=CASE WHEN actions_started THEN 'action_uncertain' WHEN p_action='interrupted' THEN 'interrupted' ELSE 'processing_failed' END WHERE id=t.id;
 ELSE RAISE EXCEPTION 'CHAT_TURN_INVALID' USING ERRCODE='22023'; END IF;
 RETURN jsonb_build_object('accepted',true);
END;
$$;
REVOKE ALL ON FUNCTION public.chat_turn_operation(uuid,text,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.chat_turn_operation(uuid,text,text,jsonb) TO service_role;

-- Fail closed if hosted default grants, inheritance or schema drift leave browser access.
DO $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_class
   WHERE oid='public.chat_turns'::regclass AND relrowsecurity) THEN
  RAISE EXCEPTION 'chat_turns must have row level security enabled';
 END IF;
 IF EXISTS (SELECT 1 FROM unnest(ARRAY['anon','authenticated']) r(role)
   CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) p(privilege)
   WHERE pg_catalog.has_table_privilege(r.role,'public.chat_turns',p.privilege)) THEN
  RAISE EXCEPTION 'chat_turns must not be open to a browser role';
 END IF;
 IF pg_catalog.has_function_privilege('anon','public.chat_turn_operation(uuid,text,text,jsonb)','EXECUTE')
   OR pg_catalog.has_function_privilege('authenticated','public.chat_turn_operation(uuid,text,text,jsonb)','EXECUTE')
   OR NOT pg_catalog.has_function_privilege('service_role','public.chat_turn_operation(uuid,text,text,jsonb)','EXECUTE') THEN
  RAISE EXCEPTION 'chat_turn_operation must be executable by the service role only';
 END IF;
END $$;
