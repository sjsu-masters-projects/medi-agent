-- PAT-001-A production fix: a finished Nora reply is saved even when the turn lease lapsed.
-- Re-runnable; 072 and 073 stay untouched.
-- 1. "complete" for the CURRENT lease is accepted while the turn is processing, or interrupted
--    (deadline or socket loss) with no reply and no dismissal. A finished reply used to be thrown
--    away (CHAT_TURN_EXPIRED) when the deadline had just passed. A lease replaced by a retry, a
--    dismissed turn and a failed turn are still refused, so one turn never gets two replies.
--    The result says late=true so the service can audit it. "actions" stays strict: no new
--    clinical action starts on a lapsed lease.
-- 2. A completed turn whose reply row is gone replays as reply_unavailable, not silently.
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
  IF nullif(p_payload->>'client_message_id','') IS NULL OR nullif(p_payload->>'request_hash','') IS NULL THEN
   RAISE EXCEPTION 'CHAT_TURN_INVALID' USING ERRCODE='22023'; END IF;
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
    IF NOT FOUND THEN
     -- The reply row was removed after completion: say so instead of replaying nothing.
     RETURN jsonb_build_object('execute',false,'reply_unavailable',true,'turn',to_jsonb(t)-'lease'-'request_hash','user_message',to_jsonb(u));
    END IF;
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
   IF p_payload->>'content' IS NULL OR p_payload->>'language' IS NULL
     OR length(btrim(p_payload->>'content')) NOT BETWEEN 1 AND 8000 OR p_payload->>'language' NOT IN ('en-US','es-MX') THEN
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
  AND id=(p_payload->>'id')::uuid AND lease=(p_payload->>'lease')::uuid
  AND (status='processing' OR (p_action='complete' AND status='interrupted'
    AND assistant_message_id IS NULL AND dismissed_at IS NULL)) FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('accepted',false); END IF;
 IF p_action='actions' THEN
  UPDATE public.chat_turns SET actions_started=true,updated_at=clock_timestamp() WHERE id=t.id;
 ELSIF p_action='complete' THEN
  INSERT INTO public.chat_messages(id,patient_id,session_id,role,content,language,intent,attachments)
   VALUES((p_payload->>'message_id')::uuid,p_patient,p_session,'assistant',p_payload->>'content',(p_payload->>'language')::public.language_enum,
    p_payload->>'intent',coalesce(p_payload->'attachments','[]'::jsonb)) RETURNING * INTO a;
  UPDATE public.chat_turns SET status='completed',failure_code=NULL,assistant_message_id=a.id,updated_at=clock_timestamp() WHERE id=t.id;
  RETURN jsonb_build_object('accepted',true,'late',t.status<>'processing','message',to_jsonb(a));
 ELSIF p_action IN ('failed','interrupted') THEN
  UPDATE public.chat_turns SET status=p_action,updated_at=clock_timestamp(),
   failure_code=CASE WHEN actions_started THEN 'action_uncertain' WHEN p_action='interrupted' THEN 'interrupted' ELSE 'processing_failed' END WHERE id=t.id;
 ELSE RAISE EXCEPTION 'CHAT_TURN_INVALID' USING ERRCODE='22023'; END IF;
 RETURN jsonb_build_object('accepted',true);
END;
$$;
REVOKE ALL ON FUNCTION public.chat_turn_operation(uuid,text,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.chat_turn_operation(uuid,text,text,jsonb) TO service_role;

DO $$
DECLARE def text;
BEGIN
 def:=pg_catalog.pg_get_functiondef('public.chat_turn_operation(uuid,text,text,jsonb)'::regprocedure);
 IF def NOT LIKE '%reply_unavailable%' OR def NOT LIKE '%IS NULL OR p_payload->>''language'' IS NULL%'
   OR def NOT LIKE '%''late'',t.status<>''processing''%' OR def NOT LIKE '%status=''interrupted''%' THEN
  RAISE EXCEPTION 'chat_turn_operation does not carry the 073 validation and the 075 late completion';
 END IF;
 IF pg_catalog.has_function_privilege('anon','public.chat_turn_operation(uuid,text,text,jsonb)','EXECUTE')
   OR pg_catalog.has_function_privilege('authenticated','public.chat_turn_operation(uuid,text,text,jsonb)','EXECUTE')
   OR NOT pg_catalog.has_function_privilege('service_role','public.chat_turn_operation(uuid,text,text,jsonb)','EXECUTE') THEN
  RAISE EXCEPTION 'chat_turn_operation must be executable by the service role only';
 END IF;
END $$;
