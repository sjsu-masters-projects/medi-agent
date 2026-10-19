-- OPS-006 phase 2: queued Nora turns, ordered turn events and the worker's queue-side operations.
-- Re-runnable; 072-077 stay untouched. Apply after 077. Nothing changes until the backend runs
-- with CHAT_TURNS_VIA_WORKER=true: the status 'queued' and the new columns are unused before that,
-- and the in-process path behaves exactly as under 077.
--
-- 1. chat_turn_events(turn_id, seq, type, payload, created_at): an append-only, per-turn ordered log
--    (started, draft checkpoints, notices, completed, failed, interrupted). Backend only.
-- 2. chat_turns.status gains 'queued'; new columns via_worker, run_count and dispatched_at.
--    * via_worker  the turn is executed by the worker service, not an API instance.
--    * run_count   times a worker claimed the turn (a Cloud Tasks retry is another claim). It is
--                  separate from `attempt`, the user-visible retry count capped at 3, because the
--                  queue task is named from the turn id and `attempt` (de-duplication, rule 4).
--    * dispatched_at  when the queue accepted the task. A queued turn with dispatched_at NULL is
--                  the transactional outbox row (rule 6): the sweep re-enqueues it.
-- 3. chat_turn_operation: keeps everything 072-077 added; a queued turn counts as the
--    conversation's active turn (one per conversation), reconciles at its deadline, and a turn
--    started by the worker writes its terminal event in the SAME transaction as its state change.
-- 4. chat_turn_worker_operation(turn, action, payload): claim, append_event, requeue, prune_events
--    and the queue-side dispatched/undispatched. Lock order (rule 7): lock-free pre-check (rule 9)
--    -> the conversation advisory lock (same key as chat_turn_operation) -> the chat_turns row ->
--    the documents row (KEY SHARE) -> chat_turn_events inserts. append_event takes only the turn
--    row. No lock is held across a network call; lock_timeout 5 s and statement_timeout 8 s.
--
-- Rollback: stop setting CHAT_TURNS_VIA_WORKER. Queued/processing worker turns finish or reconcile
-- by their deadline. The objects here are inert without the flag.

CREATE TABLE IF NOT EXISTS public.chat_turn_events (
 turn_id uuid NOT NULL REFERENCES public.chat_turns(id) ON DELETE CASCADE,
 seq bigint NOT NULL CHECK(seq>=1),
 type text NOT NULL CHECK(type IN ('started','draft','notice','completed','failed','interrupted')),
 payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(payload)='object' AND octet_length(payload::text)<=65536),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(turn_id,seq)
);
ALTER TABLE public.chat_turn_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.chat_turn_events FROM PUBLIC,anon,authenticated,service_role;
-- Append-only for the backend: no UPDATE. DELETE exists for pruning drafts.
GRANT SELECT,INSERT,DELETE ON public.chat_turn_events TO service_role;

ALTER TABLE public.chat_turns ADD COLUMN IF NOT EXISTS via_worker boolean NOT NULL DEFAULT false;
ALTER TABLE public.chat_turns ADD COLUMN IF NOT EXISTS run_count integer NOT NULL DEFAULT 0 CHECK(run_count>=0);
ALTER TABLE public.chat_turns ADD COLUMN IF NOT EXISTS dispatched_at timestamptz;

DO $$
BEGIN
 IF EXISTS(SELECT 1 FROM pg_catalog.pg_constraint WHERE conrelid='public.chat_turns'::regclass AND conname='chat_turns_status_check') THEN
  ALTER TABLE public.chat_turns DROP CONSTRAINT chat_turns_status_check;
 END IF;
 ALTER TABLE public.chat_turns ADD CONSTRAINT chat_turns_status_check
  CHECK(status IN ('queued','processing','completed','failed','interrupted'));
END $$;

-- One active (queued or running) turn per conversation; replaces chat_turns_one_processing.
DROP INDEX IF EXISTS public.chat_turns_one_processing;
CREATE UNIQUE INDEX IF NOT EXISTS chat_turns_one_active ON public.chat_turns(patient_id,session_id)
 WHERE status IN ('processing','queued');
CREATE INDEX IF NOT EXISTS chat_turns_undispatched ON public.chat_turns(updated_at)
 WHERE status='queued' AND dispatched_at IS NULL;

-- Internal helpers. Callers hold the turn row lock (or the row update that implies it), so seq
-- assignment is serialised per turn; the primary key is the backstop.
CREATE OR REPLACE FUNCTION public.chat_turn_append_event(p_turn uuid,p_type text,p_payload jsonb,p_seq bigint DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE nxt bigint;
BEGIN
 SELECT coalesce(max(seq),0)+1 INTO nxt FROM public.chat_turn_events WHERE turn_id=p_turn;
 IF p_seq IS NOT NULL AND p_seq<>nxt THEN
  -- A repeated append (a timed-out call that did commit) is a no-op; anything else is a gap.
  IF p_seq<nxt AND EXISTS(SELECT 1 FROM public.chat_turn_events WHERE turn_id=p_turn AND seq=p_seq AND type=p_type) THEN
   RETURN jsonb_build_object('accepted',true,'duplicate',true,'seq',p_seq,'next_seq',nxt);
  END IF;
  RETURN jsonb_build_object('accepted',false,'reason',CASE WHEN p_seq<nxt THEN 'seq_conflict' ELSE 'seq_gap' END,'next_seq',nxt);
 END IF;
 INSERT INTO public.chat_turn_events(turn_id,seq,type,payload) VALUES(p_turn,nxt,p_type,coalesce(p_payload,'{}'::jsonb));
 RETURN jsonb_build_object('accepted',true,'seq',nxt,'next_seq',nxt+1);
END;
$$;

-- A terminal event replaces the draft checkpoints: only the final events are kept.
CREATE OR REPLACE FUNCTION public.chat_turn_terminal_event(p_turn uuid,p_type text,p_payload jsonb)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 DELETE FROM public.chat_turn_events WHERE turn_id=p_turn AND type='draft';
 PERFORM public.chat_turn_append_event(p_turn,p_type,p_payload);
END;
$$;

CREATE OR REPLACE FUNCTION public.chat_turn_operation(p_patient uuid,p_session text,p_action text,p_payload jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=''
 SET lock_timeout='5s' SET statement_timeout='8s' AS $$
DECLARE t public.chat_turns; u public.chat_messages; a public.chat_messages; r record;
 d public.documents; snapshot jsonb; result jsonb; seconds integer; queued boolean; fc text; moved jsonb;
BEGIN
 IF p_session !~ '^[A-Za-z0-9_-]{1,64}$' OR NOT EXISTS(SELECT 1 FROM public.patients WHERE id=p_patient) THEN
  RAISE EXCEPTION 'CHAT_TURN_UNAVAILABLE' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('chat_turn:'||p_patient::text||':'||p_session,0));
 -- Reconcile: a running turn past its deadline, and a queued turn nobody claimed by its deadline.
 WITH m AS (
   UPDATE public.chat_turns SET status='interrupted',updated_at=clock_timestamp(),
    failure_code=CASE WHEN actions_started THEN 'action_uncertain' ELSE 'deadline' END
    WHERE patient_id=p_patient AND session_id=p_session AND status IN ('processing','queued') AND deadline_at<=clock_timestamp()
    RETURNING id,via_worker,failure_code)
  SELECT coalesce(jsonb_agg(jsonb_build_object('id',m.id,'fc',m.failure_code)) FILTER (WHERE m.via_worker),'[]') INTO moved FROM m;
 FOR r IN SELECT (e->>'id')::uuid AS id,e->>'fc' AS fc FROM jsonb_array_elements(moved) e LOOP
  PERFORM public.chat_turn_terminal_event(r.id,'interrupted',jsonb_build_object('failure_code',r.fc));
 END LOOP;
 IF p_action='recover' THEN
  SELECT coalesce(jsonb_agg(to_jsonb(s)-'lease'-'request_hash'),'[]') INTO result
   FROM (SELECT t0.*,to_jsonb(m) user_message FROM public.chat_turns t0 JOIN public.chat_messages m ON m.id=t0.user_message_id
     AND m.patient_id=t0.patient_id AND m.session_id=t0.session_id AND m.role::text='user'
    WHERE t0.patient_id=p_patient AND t0.session_id=p_session AND t0.dismissed_at IS NULL
    ORDER BY (t0.status IN ('processing','queued')) DESC,(t0.status<>'completed') DESC,t0.created_at DESC LIMIT 20) s;
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
  -- queued=true: the worker service executes the turn; the row doubles as the outbox entry.
  queued:=coalesce((p_payload->>'queued')::boolean,false);
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
   IF t.status IN ('processing','queued') OR t.actions_started OR t.attempt>=3 OR t.dismissed_at IS NOT NULL THEN
    RETURN jsonb_build_object('execute',false,'turn',to_jsonb(t)-'lease'-'request_hash','user_message',to_jsonb(u)); END IF;
  END IF;
  IF EXISTS(SELECT 1 FROM public.chat_turns WHERE patient_id=p_patient AND session_id=p_session AND status IN ('processing','queued')) THEN
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
   INSERT INTO public.chat_turns(patient_id,session_id,client_message_id,request_hash,user_message_id,document_context,deadline_at,status,via_worker)
    VALUES(p_patient,p_session,(p_payload->>'client_message_id')::uuid,p_payload->>'request_hash',u.id,snapshot-'summary',
     clock_timestamp()+make_interval(secs=>seconds),CASE WHEN queued THEN 'queued' ELSE 'processing' END,queued) RETURNING * INTO t;
  ELSE
   UPDATE public.chat_turns SET status=CASE WHEN queued THEN 'queued' ELSE 'processing' END,via_worker=queued,
    dispatched_at=NULL,failure_code=NULL,lease=gen_random_uuid(),attempt=attempt+1,
    deadline_at=clock_timestamp()+make_interval(secs=>seconds),updated_at=clock_timestamp()
    WHERE id=t.id RETURNING * INTO t;
  END IF;
  RETURN jsonb_build_object('execute',true,'turn',(to_jsonb(t)-'request_hash')||jsonb_build_object('document_context',snapshot),'user_message',to_jsonb(u));
 END IF;
 SELECT * INTO t FROM public.chat_turns WHERE patient_id=p_patient AND session_id=p_session
  AND id=(p_payload->>'id')::uuid AND lease=(p_payload->>'lease')::uuid
  AND (status='processing' OR (p_action='complete' AND status='interrupted'
    AND assistant_message_id IS NULL AND dismissed_at IS NULL)) FOR UPDATE;
 IF NOT FOUND THEN
  -- Explain the refusal. A second, non-locking lookup by id and patient only: it changes
  -- nothing and never reveals another patient's turn.
  SELECT * INTO t FROM public.chat_turns WHERE id=(p_payload->>'id')::uuid AND patient_id=p_patient;
  RETURN jsonb_build_object('accepted',false,'reason',CASE
   WHEN NOT FOUND THEN 'not_found'
   WHEN t.session_id<>p_session THEN 'session_mismatch'
   WHEN t.lease<>(p_payload->>'lease')::uuid THEN 'lease_mismatch'
   WHEN t.status IN ('processing','interrupted') AND t.deadline_at<=t.updated_at THEN 'deadline_passed'
   ELSE 'status:'||t.status END);
 END IF;
 IF p_action='actions' THEN
  UPDATE public.chat_turns SET actions_started=true,updated_at=clock_timestamp() WHERE id=t.id;
 ELSIF p_action='complete' THEN
  INSERT INTO public.chat_messages(id,patient_id,session_id,role,content,language,intent,attachments)
   VALUES((p_payload->>'message_id')::uuid,p_patient,p_session,'assistant',p_payload->>'content',(p_payload->>'language')::public.language_enum,
    p_payload->>'intent',coalesce(p_payload->'attachments','[]'::jsonb)) RETURNING * INTO a;
  UPDATE public.chat_turns SET status='completed',failure_code=NULL,assistant_message_id=a.id,updated_at=clock_timestamp() WHERE id=t.id;
  IF t.via_worker THEN
   PERFORM public.chat_turn_terminal_event(t.id,'completed',jsonb_build_object('message_id',a.id));
  END IF;
  RETURN jsonb_build_object('accepted',true,'late',t.status<>'processing','message',to_jsonb(a));
 ELSIF p_action IN ('failed','interrupted') THEN
  UPDATE public.chat_turns SET status=p_action,updated_at=clock_timestamp(),
   failure_code=CASE WHEN actions_started THEN 'action_uncertain' WHEN p_action='interrupted' THEN 'interrupted' ELSE 'processing_failed' END
   WHERE id=t.id RETURNING failure_code INTO fc;
  IF t.via_worker THEN
   PERFORM public.chat_turn_terminal_event(t.id,p_action,jsonb_build_object('failure_code',fc));
  END IF;
 ELSE RAISE EXCEPTION 'CHAT_TURN_INVALID' USING ERRCODE='22023'; END IF;
 RETURN jsonb_build_object('accepted',true);
END;
$$;

CREATE OR REPLACE FUNCTION public.chat_turn_worker_operation(p_turn uuid,p_action text,p_payload jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=''
 SET lock_timeout='5s' SET statement_timeout='8s' AS $$
DECLARE t public.chat_turns; u public.chat_messages; d public.documents; snapshot jsonb; items jsonb;
 seconds integer; lim integer; age integer; n integer; ev jsonb; ev_type text; wanted uuid;
BEGIN
 IF p_action='undispatched' THEN
  -- The outbox: queued worker turns whose task was never accepted by the queue. SKIP LOCKED so
  -- concurrent sweeps take different rows and never wait (rule 10). Only ids leave the database.
  lim:=greatest(1,least(100,coalesce((p_payload->>'limit')::integer,25)));
  age:=greatest(0,least(3600,coalesce((p_payload->>'min_age_seconds')::integer,15)));
  SELECT coalesce(jsonb_agg(jsonb_build_object('id',s.id,'attempt',s.attempt)),'[]') INTO items
   FROM (SELECT c.id,c.attempt FROM public.chat_turns c
     WHERE c.status='queued' AND c.via_worker AND c.dispatched_at IS NULL AND c.deadline_at>clock_timestamp()
      AND c.updated_at<=clock_timestamp()-make_interval(secs=>age)
     ORDER BY c.updated_at,c.id LIMIT lim FOR UPDATE SKIP LOCKED) s;
  RETURN jsonb_build_object('items',items);
 END IF;
 IF p_action='dispatched' THEN
  UPDATE public.chat_turns SET dispatched_at=clock_timestamp()
   WHERE id=p_turn AND status='queued' AND via_worker AND dispatched_at IS NULL
    AND attempt=coalesce((p_payload->>'attempt')::integer,attempt);
  RETURN jsonb_build_object('accepted',FOUND);
 END IF;
 -- Lock-free existence check (rule 9): an unknown id never queues behind anyone.
 SELECT * INTO t FROM public.chat_turns WHERE id=p_turn;
 IF NOT FOUND THEN RETURN jsonb_build_object('accepted',false,'reason','not_found'); END IF;
 wanted:=(p_payload->>'lease')::uuid;

 IF p_action='append_event' THEN
  -- Turn row only (no conversation lock): appenders of one turn serialise on its row.
  ev_type:=p_payload->>'type';
  IF ev_type IS NULL OR ev_type NOT IN ('draft','notice') OR jsonb_typeof(p_payload->'payload') IS DISTINCT FROM 'object'
    OR octet_length((p_payload->'payload')::text)>65536 THEN
   RAISE EXCEPTION 'CHAT_TURN_INVALID' USING ERRCODE='22023'; END IF;
  SELECT * INTO t FROM public.chat_turns WHERE id=p_turn AND status='processing'
   AND wanted IS NOT NULL AND lease=wanted FOR UPDATE;
  IF NOT FOUND THEN
   SELECT * INTO t FROM public.chat_turns WHERE id=p_turn;
   RETURN jsonb_build_object('accepted',false,'reason',CASE
    WHEN t.lease IS DISTINCT FROM wanted THEN 'lease_mismatch' ELSE 'status:'||t.status END);
  END IF;
  IF t.deadline_at<=clock_timestamp() THEN
   RETURN jsonb_build_object('accepted',false,'reason','deadline_passed'); END IF;
  RETURN public.chat_turn_append_event(t.id,ev_type,p_payload->'payload',(p_payload->>'seq')::bigint);
 END IF;

 IF p_action NOT IN ('claim','requeue','prune_events') THEN
  RAISE EXCEPTION 'CHAT_TURN_INVALID' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('chat_turn:'||t.patient_id::text||':'||t.session_id,0));
 SELECT * INTO t FROM public.chat_turns WHERE id=p_turn FOR UPDATE;

 IF p_action='prune_events' THEN
  IF t.status NOT IN ('completed','failed','interrupted') THEN
   RETURN jsonb_build_object('accepted',false,'reason','status:'||t.status); END IF;
  DELETE FROM public.chat_turn_events WHERE turn_id=t.id AND type='draft';
  GET DIAGNOSTICS n=ROW_COUNT;
  RETURN jsonb_build_object('accepted',true,'deleted',n);
 END IF;

 IF p_action='requeue' THEN
  -- The lease holder hands the turn back after a transient infrastructure failure, before any
  -- clinical action: the queue's own retry then claims it again. Never after actions started.
  IF t.status<>'processing' OR wanted IS NULL OR t.lease<>wanted THEN
   RETURN jsonb_build_object('accepted',false,'reason',CASE WHEN t.lease IS DISTINCT FROM wanted THEN 'lease_mismatch' ELSE 'status:'||t.status END); END IF;
  IF t.actions_started THEN RETURN jsonb_build_object('accepted',false,'reason','actions_started'); END IF;
  seconds:=greatest(10,least(120,coalesce((p_payload->>'timeout_seconds')::integer,60)));
  UPDATE public.chat_turns SET status='queued',lease=gen_random_uuid(),dispatched_at=clock_timestamp(),
   deadline_at=clock_timestamp()+make_interval(secs=>seconds),updated_at=clock_timestamp() WHERE id=t.id;
  RETURN jsonb_build_object('accepted',true);
 END IF;

 -- claim: queued -> processing (or a processing turn whose lease expired, when no clinical
 -- action started). Every refusal says why; 'lease_active' is the only retryable one.
 IF NOT t.via_worker THEN RETURN jsonb_build_object('accepted',false,'reason','not_worker_turn'); END IF;
 IF p_payload ? 'attempt' AND (p_payload->>'attempt')::integer<>t.attempt THEN
  RETURN jsonb_build_object('accepted',false,'reason','stale_attempt'); END IF;
 IF t.status NOT IN ('queued','processing') THEN
  RETURN jsonb_build_object('accepted',false,'reason','status:'||t.status); END IF;
 IF t.status='processing' AND t.deadline_at>clock_timestamp() THEN
  RETURN jsonb_build_object('accepted',false,'reason','lease_active'); END IF;
 IF t.status='queued' AND t.deadline_at<=clock_timestamp() THEN
  UPDATE public.chat_turns SET status='interrupted',failure_code='deadline',updated_at=clock_timestamp() WHERE id=t.id;
  PERFORM public.chat_turn_terminal_event(t.id,'interrupted',jsonb_build_object('failure_code','deadline'));
  RETURN jsonb_build_object('accepted',false,'reason','queue_expired');
 END IF;
 IF t.status='processing' AND (t.actions_started OR t.run_count>=3) THEN
  -- A crashed worker may have recorded a clinical action: never run the turn again.
  UPDATE public.chat_turns SET status='interrupted',updated_at=clock_timestamp(),
   failure_code=CASE WHEN t.actions_started THEN 'action_uncertain' ELSE 'deadline' END WHERE id=t.id;
  PERFORM public.chat_turn_terminal_event(t.id,'interrupted',
   jsonb_build_object('failure_code',CASE WHEN t.actions_started THEN 'action_uncertain' ELSE 'deadline' END));
  RETURN jsonb_build_object('accepted',false,'reason',CASE WHEN t.actions_started THEN 'action_uncertain' ELSE 'attempts_exhausted' END);
 END IF;
 SELECT * INTO u FROM public.chat_messages WHERE id=t.user_message_id AND patient_id=t.patient_id
  AND session_id=t.session_id AND role::text='user';
 IF NOT FOUND THEN RETURN jsonb_build_object('accepted',false,'reason','not_found'); END IF;
 IF nullif(t.document_context->>'id','') IS NOT NULL THEN
  -- Re-authorise the selected document against its stored version, as a retry does.
  SELECT * INTO d FROM public.documents WHERE id=(t.document_context->>'id')::uuid AND patient_id=t.patient_id FOR KEY SHARE;
  IF NOT FOUND OR d.parse_status::text<>'completed' OR nullif(btrim(d.ai_summary),'') IS NULL
    OR md5(d.ai_summary) IS DISTINCT FROM t.document_context->>'context_version' THEN
   UPDATE public.chat_turns SET status='failed',failure_code='processing_failed',updated_at=clock_timestamp() WHERE id=t.id;
   PERFORM public.chat_turn_terminal_event(t.id,'failed',jsonb_build_object('failure_code','processing_failed'));
   RETURN jsonb_build_object('accepted',false,'reason','document_unavailable');
  END IF;
  snapshot:=jsonb_build_object('id',d.id,'file_name',d.file_name,'display_title',d.display_title,
   'document_type',d.document_type,'summary',left(d.ai_summary,6000),'parse_status',d.parse_status,
   'context_version',md5(d.ai_summary));
 END IF;
 seconds:=greatest(10,least(120,coalesce((p_payload->>'timeout_seconds')::integer,45)));
 UPDATE public.chat_turns SET status='processing',failure_code=NULL,lease=gen_random_uuid(),run_count=run_count+1,
  deadline_at=clock_timestamp()+make_interval(secs=>seconds),updated_at=clock_timestamp()
  WHERE id=t.id RETURNING * INTO t;
 ev:=public.chat_turn_append_event(t.id,'started',jsonb_build_object('attempt',t.attempt,'run',t.run_count));
 RETURN jsonb_build_object('accepted',true,'patient_id',t.patient_id,'session_id',t.session_id,
  'next_seq',(ev->>'next_seq')::bigint,
  'turn',(to_jsonb(t)-'request_hash')||jsonb_build_object('document_context',snapshot),'user_message',to_jsonb(u));
END;
$$;

REVOKE ALL ON FUNCTION public.chat_turn_operation(uuid,text,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.chat_turn_operation(uuid,text,text,jsonb) TO service_role;
REVOKE ALL ON FUNCTION public.chat_turn_worker_operation(uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.chat_turn_worker_operation(uuid,text,jsonb) TO service_role;
REVOKE ALL ON FUNCTION public.chat_turn_append_event(uuid,text,jsonb,bigint) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.chat_turn_append_event(uuid,text,jsonb,bigint) TO service_role;
REVOKE ALL ON FUNCTION public.chat_turn_terminal_event(uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.chat_turn_terminal_event(uuid,text,jsonb) TO service_role;

DO $$
DECLARE def text; fn text;
BEGIN
 def:=pg_catalog.pg_get_functiondef('public.chat_turn_operation(uuid,text,text,jsonb)'::regprocedure);
 IF def NOT LIKE '%reply_unavailable%' OR def NOT LIKE '%IS NULL OR p_payload->>''language'' IS NULL%'
   OR def NOT LIKE '%''late'',t.status<>''processing''%' OR def NOT LIKE '%status=''interrupted''%'
   OR def NOT LIKE '%''session_mismatch''%' OR def NOT LIKE '%''lease_mismatch''%'
   OR def NOT LIKE '%''deadline_passed''%' OR def NOT LIKE '%''not_found''%'
   OR def NOT LIKE '%''queued''%' OR def NOT LIKE '%chat_turn_terminal_event%' THEN
  RAISE EXCEPTION 'chat_turn_operation does not carry the 073 validation, the 074 late completion, the 077 rejection reasons and the 078 queued turns';
 END IF;
 FOREACH fn IN ARRAY ARRAY['public.chat_turn_operation(uuid,text,text,jsonb)','public.chat_turn_worker_operation(uuid,text,jsonb)'] LOOP
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p WHERE p.oid=fn::regprocedure
    AND p.proconfig @> ARRAY['lock_timeout=5s'] AND p.proconfig @> ARRAY['statement_timeout=8s']) THEN
   RAISE EXCEPTION '% must set lock_timeout and statement_timeout',fn;
  END IF;
 END LOOP;
 FOREACH fn IN ARRAY ARRAY['public.chat_turn_operation(uuid,text,text,jsonb)','public.chat_turn_worker_operation(uuid,text,jsonb)',
   'public.chat_turn_append_event(uuid,text,jsonb,bigint)','public.chat_turn_terminal_event(uuid,text,jsonb)'] LOOP
  IF pg_catalog.has_function_privilege('anon',fn::regprocedure,'EXECUTE')
    OR pg_catalog.has_function_privilege('authenticated',fn::regprocedure,'EXECUTE')
    OR NOT pg_catalog.has_function_privilege('service_role',fn::regprocedure,'EXECUTE') THEN
   RAISE EXCEPTION '% must be executable by the service role only',fn;
  END IF;
 END LOOP;
 IF pg_catalog.has_table_privilege('anon','public.chat_turn_events','SELECT')
   OR pg_catalog.has_table_privilege('anon','public.chat_turn_events','INSERT')
   OR pg_catalog.has_table_privilege('authenticated','public.chat_turn_events','SELECT')
   OR pg_catalog.has_table_privilege('authenticated','public.chat_turn_events','INSERT')
   OR pg_catalog.has_table_privilege('authenticated','public.chat_turn_events','UPDATE')
   OR pg_catalog.has_table_privilege('authenticated','public.chat_turn_events','DELETE')
   OR pg_catalog.has_table_privilege('service_role','public.chat_turn_events','UPDATE')
   OR NOT pg_catalog.has_table_privilege('service_role','public.chat_turn_events','SELECT')
   OR NOT pg_catalog.has_table_privilege('service_role','public.chat_turn_events','INSERT')
   OR NOT pg_catalog.has_table_privilege('service_role','public.chat_turn_events','DELETE') THEN
  RAISE EXCEPTION 'chat_turn_events must be backend-only and append-only';
 END IF;
 IF NOT (SELECT relrowsecurity FROM pg_catalog.pg_class WHERE oid='public.chat_turn_events'::regclass) THEN
  RAISE EXCEPTION 'chat_turn_events must have row level security enabled';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint WHERE conrelid='public.chat_turns'::regclass
   AND conname='chat_turns_status_check' AND pg_catalog.pg_get_constraintdef(oid) LIKE '%queued%') THEN
  RAISE EXCEPTION 'chat_turns status must allow queued';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_indexes WHERE schemaname='public' AND indexname='chat_turns_one_active') THEN
  RAISE EXCEPTION 'chat_turns_one_active is missing';
 END IF;
END $$;
