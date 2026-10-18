-- COM-002: context is an explicit patient choice, never an instruction to publish.
ALTER TABLE public.care_conversation_messages
  ADD COLUMN IF NOT EXISTS care_plan_item_id uuid REFERENCES public.care_plan_items(id) ON DELETE SET NULL;
ALTER TABLE public.care_plan_items
  ADD COLUMN IF NOT EXISTS review_source_item_id uuid REFERENCES public.care_plan_items(id) ON DELETE SET NULL;
CREATE UNIQUE INDEX IF NOT EXISTS care_plan_items_review_source
  ON public.care_plan_items(plan_version_id, review_source_item_id)
  WHERE review_source_item_id IS NOT NULL;

CREATE OR REPLACE FUNCTION private.care_conversation_message(p_id uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path = '' AS $$
  SELECT jsonb_build_object('id', m.id, 'conversation_id', m.conversation_id,
    'sender_id', m.sender_id, 'sender_role', m.sender_role, 'sender_name', m.sender_name,
    'body', m.body, 'created_at', m.created_at,
    'activity_context', CASE WHEN i.id IS NULL THEN NULL ELSE jsonb_build_object(
      'item_id', i.id, 'plan_id', v.id, 'title', i.title, 'frequency', i.frequency,
      'wording', i.wording, 'current', v.status='approved' AND NOT i.is_removed) END)
  FROM public.care_conversation_messages m
  LEFT JOIN public.care_plan_items i ON i.id=m.care_plan_item_id
  LEFT JOIN public.care_plan_versions v ON v.id=i.plan_version_id
  WHERE m.id=p_id;
$$;

CREATE OR REPLACE FUNCTION public.care_conversation_activity_operation(
  p_actor_id uuid, p_actor_role text, p_action text, p_payload jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_result jsonb;
  v_message public.care_conversation_messages;
  v_item public.care_plan_items;
  v_plan public.care_plan_versions;
  v_draft public.care_plan_versions;
  v_thread public.care_conversations;
  v_key uuid;
  v_item_id uuid;
  v_target uuid;
  v_existing boolean;
  v_count integer;
  v_patient uuid;
BEGIN
  IF p_action='send' THEN
    v_key := (p_payload->>'client_message_id')::uuid;
    v_item_id := (p_payload->>'care_plan_item_id')::uuid;
    -- Match the original sender-key -> assignment -> thread lock order.
    PERFORM pg_advisory_xact_lock(hashtextextended(p_actor_id::text || ':' || v_key::text,0));
    SELECT * INTO v_message FROM public.care_conversation_messages
      WHERE sender_id=p_actor_id AND client_message_id=v_key;
    v_existing := FOUND;
    v_result := public.care_conversation_operation(p_actor_id,p_actor_role,'send',p_payload);
    IF v_existing THEN
      IF v_message.care_plan_item_id IS DISTINCT FROM v_item_id THEN
        RAISE EXCEPTION USING ERRCODE='23505', MESSAGE='Message idempotency mismatch';
      END IF;
      RETURN v_result;
    END IF;
    IF v_item_id IS NOT NULL THEN
      IF p_actor_role<>'patient' THEN
        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Activity unavailable';
      END IF;
      SELECT i.* INTO v_item FROM public.care_plan_items i
        JOIN public.care_plan_versions v ON v.id=i.plan_version_id
        WHERE i.id=v_item_id AND v.patient_id=p_actor_id AND v.status='approved'
          AND NOT i.is_removed FOR SHARE OF i,v;
      IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Activity is no longer approved';
      END IF;
      UPDATE public.care_conversation_messages SET care_plan_item_id=v_item_id
        WHERE id=(v_result->>'id')::uuid;
    END IF;
    RETURN private.care_conversation_message((v_result->>'id')::uuid);
  ELSIF p_action='review' THEN
    IF p_actor_role IS DISTINCT FROM 'clinician' THEN
      RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Conversation unavailable';
    END IF;
    -- Match publication/generation: evidence fence BEFORE plan/patient locks.
    -- Resolve identity without row locks, then recheck the exact thread below.
    SELECT patient_id INTO v_patient FROM public.care_conversations
      WHERE id=(p_payload->>'conversation_id')::uuid;
    PERFORM private.lock_care_plan_evidence(v_patient,true);
    -- Existing RPC rechecks and locks current assignment and exact private thread.
    PERFORM public.care_conversation_operation(p_actor_id,p_actor_role,'messages',
      jsonb_build_object('conversation_id',p_payload->>'conversation_id','limit',1));
    SELECT * INTO v_thread FROM public.care_conversations
      WHERE id=(p_payload->>'conversation_id')::uuid;
    IF v_thread.patient_id IS DISTINCT FROM v_patient THEN
      RAISE EXCEPTION USING ERRCODE='40001', MESSAGE='Conversation changed; retry review';
    END IF;
    SELECT * INTO v_message FROM public.care_conversation_messages
      WHERE id=(p_payload->>'message_id')::uuid AND conversation_id=v_thread.id
        AND sender_role='patient';
    IF NOT FOUND OR v_message.care_plan_item_id IS NULL THEN
      RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Activity context unavailable';
    END IF;
    SELECT i.* INTO v_item FROM public.care_plan_items i
      JOIN public.care_plan_versions v ON v.id=i.plan_version_id
      WHERE i.id=v_message.care_plan_item_id AND v.patient_id=v_thread.patient_id
        AND v.status='approved' AND NOT i.is_removed FOR SHARE OF i,v;
    IF NOT FOUND THEN
      RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Activity is no longer approved';
    END IF;
    SELECT * INTO v_plan FROM public.care_plan_versions WHERE id=v_item.plan_version_id;
    SELECT * INTO v_draft FROM public.care_plan_versions
      WHERE patient_id=v_thread.patient_id AND status='draft' FOR UPDATE;
    IF NOT FOUND THEN
      INSERT INTO public.care_plan_versions(patient_id,version_number,status,source_watermark,generated_at)
        SELECT v_thread.patient_id,coalesce(max(version_number),0)+1,'draft',v_plan.source_watermark,clock_timestamp()
        FROM public.care_plan_versions WHERE patient_id=v_thread.patient_id RETURNING * INTO v_draft;
      INSERT INTO public.care_plan_items(plan_version_id,review_source_item_id,source_fact_id,
        category,title,instructions,frequency,schedule,medication,confidence_score,
        uncertainty,conflict,blocker_reason,is_removed,source_locale,wording,wording_origin)
        SELECT v_draft.id,i.id,i.source_fact_id,i.category,i.title,i.instructions,i.frequency,
          i.schedule,CASE WHEN i.projection_type='medication' AND i.projection_id IS NOT NULL
            AND NOT i.is_removed THEN i.medication || jsonb_build_object('decision','update','target_id',i.projection_id)
            ELSE i.medication END,i.confidence_score,i.uncertainty,i.conflict,i.blocker_reason,
          i.is_removed,i.source_locale,i.wording,i.wording_origin
        FROM public.care_plan_items i WHERE i.plan_version_id=v_plan.id;
    END IF;
    SELECT count(*),(array_agg(id))[1] INTO v_count,v_target FROM public.care_plan_items
      WHERE plan_version_id=v_draft.id AND NOT is_removed AND
        (review_source_item_id=v_item.id OR
          (v_item.source_fact_id IS NOT NULL AND source_fact_id=v_item.source_fact_id));
    IF v_count<>1 THEN
      RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Review the existing draft before opening this activity';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.care_plan_audit_events
      WHERE plan_version_id=v_draft.id AND event_type='message_review_opened'
        AND event_data->>'message_id'=v_message.id::text AND actor_id=p_actor_id) THEN
      INSERT INTO public.care_plan_audit_events(plan_version_id,actor_id,event_type,event_data)
        VALUES(v_draft.id,p_actor_id,'message_review_opened',jsonb_build_object(
          'message_id',v_message.id,'conversation_id',v_thread.id,
          'source_item_id',v_item.id,'draft_item_id',v_target));
    END IF;
    RETURN jsonb_build_object('patient_id',v_thread.patient_id,'plan_id',v_draft.id,'item_id',v_target);
  END IF;
  RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid activity operation';
END;
$$;

ALTER TABLE public.care_conversation_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.care_plan_items ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON FUNCTION public.care_conversation_activity_operation(uuid,text,text,jsonb)
  FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION private.care_conversation_message(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.care_conversation_activity_operation(uuid,text,text,jsonb),
  private.care_conversation_message(uuid) TO service_role;
GRANT UPDATE(care_plan_item_id) ON public.care_conversation_messages TO service_role;

DO $$
BEGIN
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid='public.care_conversation_messages'::regclass)
    OR NOT (SELECT relrowsecurity FROM pg_class WHERE oid='public.care_plan_items'::regclass)
    OR has_function_privilege('anon','public.care_conversation_activity_operation(uuid,text,text,jsonb)','EXECUTE')
    OR has_function_privilege('authenticated','public.care_conversation_activity_operation(uuid,text,text,jsonb)','EXECUTE')
    OR NOT has_function_privilege('service_role','public.care_conversation_activity_operation(uuid,text,text,jsonb)','EXECUTE')
    OR NOT has_column_privilege('service_role','public.care_conversation_messages','care_plan_item_id','UPDATE')
    OR has_table_privilege('anon','public.care_conversation_messages','SELECT,INSERT,UPDATE,DELETE')
    OR has_table_privilege('authenticated','public.care_conversation_messages','SELECT,INSERT,UPDATE,DELETE') THEN
    RAISE EXCEPTION 'COM-002 permission verification failed';
  END IF;
END;
$$;
