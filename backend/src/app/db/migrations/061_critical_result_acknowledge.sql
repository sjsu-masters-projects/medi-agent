-- AI-005 follow-up: a clinician can acknowledge a critical-result alert.
--
-- 060 lists the alert under Alerts -> Needs attention until it is acknowledged, but the
-- acknowledge rule names its event types explicitly (054), so acknowledging it was refused
-- ("Notification cannot be acknowledged") and the alert could never leave the list. Both
-- places that rule lives, the row a clinician sees and the acknowledge operation, now
-- include critical_result. Same signatures as 054, so their grants still apply.

CREATE OR REPLACE FUNCTION private.notification_row(p_receipt public.notification_receipts,p_actor uuid,p_role text)
RETURNS TABLE(id uuid,event_id uuid,created_at timestamptz,is_read boolean,actionable boolean,
  can_acknowledge boolean,group_key text,item jsonb)
LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 WITH authorized AS (
   SELECT p_receipt.id,p_receipt.event_id,p_receipt.created_at,p_receipt.read_at,p_receipt.acknowledged_at,
     e.event_type,e.category,e.source_type,e.source_id,e.patient_id,e.metadata,
     private.notification_source(e.source_type,e.source_id) s,
     private.notification_actionable(e,p_role) active,
     -- Only the newest receipt this person can see for a source and kind asks for action.
     NOT EXISTS(SELECT 1 FROM public.notification_events n JOIN public.notification_receipts o ON o.event_id=n.id
       WHERE n.source_type=e.source_type AND n.source_id=e.source_id AND n.event_type=e.event_type
         AND (n.created_at,n.id)>(e.created_at,e.id) AND o.recipient_id=p_actor AND o.recipient_role=p_role
         AND private.notification_authorized(n,p_actor,p_role)) latest
   FROM public.notification_events e
   WHERE e.id=p_receipt.event_id AND p_receipt.recipient_id=p_actor AND p_receipt.recipient_role=p_role
     AND private.notification_authorized(e,p_actor,p_role)
 ), states AS (
   SELECT a.*,(a.read_at IS NOT NULL OR (a.source_type='notifications' AND coalesce((s->>'is_read')::boolean,false))
     OR (a.event_type='message_received' AND EXISTS(SELECT 1 FROM public.care_conversation_reads cr
       WHERE cr.conversation_id=private.notification_uuid(a.metadata->>'conversation_id') AND cr.actor_id=p_actor
         AND (private.notification_ts(a.s->>'created_at'),a.source_id)<=(cr.last_message_at,cr.last_message_id)))) seen,
     (a.active AND a.latest AND a.acknowledged_at IS NULL) needs
   FROM authorized a
 )
 SELECT a.id,a.event_id,a.created_at,a.seen,a.needs,
   (p_role='clinician' AND a.event_type IN ('barrier_reported','safety_flag','appointment_response','critical_result') AND a.needs),
   CASE WHEN a.event_type='message_received' THEN 'message:'||(a.metadata->>'conversation_id')
     WHEN a.category='reminders' THEN 'reminder:'||coalesce(a.metadata->>'target_id',a.source_id::text)||':'||
       coalesce((private.notification_ts(a.metadata->>'scheduled_at')
         AT TIME ZONE private.notification_zone(p.timezone))::date::text,a.created_at::date::text)
     ELSE 'receipt:'||a.id END,
   jsonb_build_object('id',a.id,'event_type',a.event_type,'category',a.category,'source_type',a.source_type,
     'source_id',a.source_id,'patient_id',a.patient_id,'metadata',a.metadata,'created_at',a.created_at,
     'is_read',a.seen,'actionable',a.needs,'can_acknowledge',
       p_role='clinician' AND a.event_type IN ('barrier_reported','safety_flag','appointment_response','critical_result') AND a.needs,
     'patient_name',concat_ws(' ',p.first_name,p.last_name),
     'clinic_name',coalesce(cl.display_name,ct.clinic_name),
     'actor_name',coalesce(a.metadata->>'actor_name',concat_ws(' ',c.first_name,c.last_name)))
 FROM states a JOIN public.patients p ON p.id=a.patient_id
 LEFT JOIN LATERAL (SELECT t.* FROM public.care_teams t WHERE t.patient_id=a.patient_id AND t.status='active'
   AND (CASE WHEN p_role='clinician' THEN t.clinician_id=p_actor
     WHEN a.metadata->>'clinician_id' IS NOT NULL THEN t.clinician_id=(a.metadata->>'clinician_id')::uuid ELSE true END)
   ORDER BY t.id LIMIT 1) ct ON true
 LEFT JOIN public.clinicians c ON c.id=ct.clinician_id LEFT JOIN public.clinics cl ON cl.id=c.clinic_id;
$$;

CREATE OR REPLACE FUNCTION public.notification_centre_operation(
 p_actor_id uuid,p_actor_role text,p_action text,p_payload jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v_limit int; v_items jsonb; v_next jsonb; v_ids uuid[]; v_read_ids jsonb; v_count int:=0;
  x record; v_target record; v_note text; v_ack boolean; v_receipt uuid; v_skipped int:=0; v_actions int:=0;
  v_patients uuid[]; v_list boolean; v_unread boolean; v_category text;
  v_before_at timestamptz; v_before_id uuid; v_pos_at timestamptz; v_pos_id uuid;
  v_window int; v_fetched int; v_walked int:=0; v_capped boolean:=false; v_walk text;
  v_r public.notification_receipts; v_row record;
  v_found_ids uuid[]:='{}'; v_found_at timestamptz[]:='{}'; v_found_items jsonb[]:='{}'; v_found_read boolean[]:='{}';
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN
   RAISE EXCEPTION 'Notification operation requires read committed' USING ERRCODE='40001'; END IF;
 IF p_actor_id IS NULL OR p_actor_role IS NULL OR p_actor_role NOT IN ('patient','clinician')
   OR (p_actor_role='patient' AND NOT EXISTS(SELECT 1 FROM public.patients WHERE id=p_actor_id))
   OR (p_actor_role='clinician' AND NOT EXISTS(SELECT 1 FROM public.clinicians WHERE id=p_actor_id)) THEN
   RAISE EXCEPTION 'Notification unavailable' USING ERRCODE='42501'; END IF;
 IF p_action IS NULL OR p_action NOT IN ('list','summary','action_items','read','read_through','acknowledge')
   OR jsonb_typeof(p_payload) IS DISTINCT FROM 'object' THEN
   RAISE EXCEPTION 'Invalid notification request' USING ERRCODE='22023'; END IF;
 IF p_action IN ('action_items','acknowledge') AND p_actor_role<>'clinician' THEN
   RAISE EXCEPTION 'Notification unavailable' USING ERRCODE='42501'; END IF;
 -- Assignment locks precede receipt locks, serializing revocation with access.
 PERFORM t.id FROM public.care_teams t JOIN public.patients p ON p.id=t.patient_id
   JOIN public.clinicians c ON c.id=t.clinician_id JOIN public.clinics cl ON cl.id=c.clinic_id
   WHERE t.status='active' AND ((p_actor_role='patient' AND t.patient_id=p_actor_id)
     OR (p_actor_role='clinician' AND t.clinician_id=p_actor_id)) ORDER BY t.id FOR SHARE OF t,p,c,cl;
 PERFORM private.notification_prepare(p_actor_id,p_actor_role);
 v_patients:=private.notification_scope(p_actor_id,p_actor_role);

 IF p_action='summary' THEN
   -- Unread: only receipts in the unread index are evaluated.
   SELECT count(DISTINCT nr.group_key) INTO v_count FROM public.notification_receipts r
     JOIN public.notification_events e ON e.id=r.event_id
     CROSS JOIN LATERAL private.notification_row(r,p_actor_id,p_actor_role) nr
     WHERE r.recipient_id=p_actor_id AND r.recipient_role=p_actor_role AND r.read_at IS NULL
       AND e.patient_id=ANY(v_patients) AND NOT nr.is_read;
   -- Action items: only work whose source is still open is evaluated.
   IF p_actor_role='clinician' THEN
     SELECT count(*) INTO v_actions FROM private.notification_open_work(p_actor_id,p_actor_role,v_patients) r
       CROSS JOIN LATERAL private.notification_row(r,p_actor_id,p_actor_role) nr
       WHERE nr.actionable AND nr.item->>'category'<>'messages';
   END IF;
   RETURN jsonb_build_object('unread_count',v_count,'action_item_count',v_actions);
 ELSIF p_action IN ('list','action_items') THEN
   v_limit:=coalesce((p_payload->>'limit')::int,50);
   IF v_limit NOT BETWEEN 1 AND 100 OR (p_payload ? 'category' AND p_payload->>'category' NOT IN
     ('documents','care_plans','appointments','follow_up','safety'))
     OR (p_payload ? 'before' AND (jsonb_typeof(p_payload->'before')<>'object'
       OR p_payload->'before'->>'id' IS NULL OR p_payload->'before'->>'created_at' IS NULL)) THEN
     RAISE EXCEPTION 'Invalid notification request' USING ERRCODE='22023'; END IF;
   v_list:=p_action='list'; v_unread:=coalesce((p_payload->>'unread')::boolean,false);
   v_category:=p_payload->>'category';
   IF p_payload ? 'before' THEN
     v_before_at:=(p_payload->'before'->>'created_at')::timestamptz; v_before_id:=(p_payload->'before'->>'id')::uuid;
   END IF;
   -- Walk this person's receipts newest first from the cursor in bounded windows and
   -- evaluate only what is walked, until the page plus one is found. Unread grouped rows
   -- (messages, same-day reminders) are excluded here and taken from the unread index below.
   v_walk:='SELECT r.* FROM '
     ||CASE WHEN v_list THEN 'public.notification_receipts' ELSE 'private.notification_open_work($1,$2,$3)' END
     ||' r JOIN public.notification_events e ON e.id=r.event_id
     WHERE r.recipient_id=$1 AND r.recipient_role=$2 AND e.patient_id=ANY($3)
       AND ($4::timestamptz IS NULL OR (r.created_at,r.id)<($4,$5)) AND ($7::text IS NULL OR e.category=$7)'
     ||CASE WHEN NOT v_list THEN ' AND e.category<>''messages'''
       WHEN v_unread THEN ' AND r.read_at IS NULL AND e.event_type<>''message_received'' AND e.category<>''reminders'''
       ELSE ' AND NOT (r.read_at IS NULL AND (e.event_type=''message_received'' OR e.category=''reminders''))' END
     ||' ORDER BY r.created_at DESC,r.id DESC LIMIT $6';
   v_window:=greatest(2*(v_limit+1),50); v_pos_at:=v_before_at; v_pos_id:=v_before_id;
   <<walk>> LOOP
     v_fetched:=0;
     FOR v_r IN EXECUTE v_walk USING p_actor_id,p_actor_role,v_patients,v_pos_at,v_pos_id,v_window,v_category LOOP
       v_fetched:=v_fetched+1; v_walked:=v_walked+1; v_pos_at:=v_r.created_at; v_pos_id:=v_r.id;
       SELECT * INTO v_row FROM private.notification_row(v_r,p_actor_id,p_actor_role);
       CONTINUE WHEN NOT FOUND;
       CONTINUE WHEN CASE WHEN v_list THEN v_unread AND v_row.is_read
         ELSE NOT v_row.actionable OR v_row.item->>'category'='messages' END;
       v_found_ids:=array_append(v_found_ids,v_row.id); v_found_at:=array_append(v_found_at,v_row.created_at);
       v_found_items:=array_append(v_found_items,v_row.item); v_found_read:=array_append(v_found_read,v_row.is_read);
       EXIT walk WHEN cardinality(v_found_ids)>v_limit;
     END LOOP;
     EXIT walk WHEN v_fetched<v_window;
     -- Bounded: a long run of rows that are not shown ends this page early with a cursor
     -- at the walk position, and the next page continues from there.
     IF v_walked>=1000 THEN v_capped:=true; EXIT walk; END IF;
   END LOOP;
   WITH grouped AS MATERIALIZED (
     SELECT nr.id,nr.created_at,nr.is_read,nr.group_key,nr.item FROM public.notification_receipts r
       JOIN public.notification_events e ON e.id=r.event_id
       CROSS JOIN LATERAL private.notification_row(r,p_actor_id,p_actor_role) nr
     WHERE v_list AND r.recipient_id=p_actor_id AND r.recipient_role=p_actor_role AND r.read_at IS NULL
       AND (e.event_type='message_received' OR e.category='reminders') AND e.patient_id=ANY(v_patients)
       AND (v_category IS NULL OR e.category=v_category) AND (NOT v_unread OR NOT nr.is_read)
   ), eligible AS (
     SELECT f.id,f.created_at,f.is_read,'receipt:'||f.id bucket,f.item
       FROM unnest(v_found_ids,v_found_at,v_found_read,v_found_items) f(id,created_at,is_read,item)
     UNION ALL SELECT g.id,g.created_at,g.is_read,CASE WHEN g.is_read THEN 'receipt:'||g.id ELSE g.group_key END,g.item
       FROM grouped g
   ), ranked AS (SELECT *,row_number() OVER(PARTITION BY bucket ORDER BY created_at DESC,id DESC) n FROM eligible),
   page AS (SELECT * FROM ranked WHERE n=1
     AND (v_before_at IS NULL OR (created_at,id)<(v_before_at,v_before_id))
     AND (NOT v_capped OR (created_at,id)>=(v_pos_at,v_pos_id))
     ORDER BY created_at DESC,id DESC LIMIT v_limit+1),
   shown AS (SELECT * FROM page ORDER BY created_at DESC,id DESC LIMIT v_limit)
   SELECT coalesce(jsonb_agg(s.item||jsonb_build_object('receipt_ids',
     (SELECT jsonb_agg(q.id ORDER BY q.created_at DESC,q.id DESC) FROM
       (SELECT r.id,r.created_at FROM eligible r WHERE r.bucket=s.bucket ORDER BY r.created_at DESC,r.id DESC LIMIT 1000) q))
     ORDER BY s.created_at DESC,s.id DESC),'[]'),
     CASE WHEN (SELECT count(*) FROM page)>v_limit THEN
       (SELECT jsonb_build_object('created_at',created_at,'id',id) FROM shown ORDER BY created_at,id LIMIT 1)
     WHEN v_capped THEN jsonb_build_object('created_at',v_pos_at,'id',v_pos_id) END,
     (SELECT coalesce(jsonb_agg(q.id),'[]') FROM (SELECT DISTINCT r.id FROM eligible r JOIN shown s ON s.bucket=r.bucket
       WHERE NOT r.is_read ORDER BY r.id LIMIT 1000) q)
   INTO v_items,v_next,v_read_ids FROM shown s;
   RETURN jsonb_build_object('items',v_items,'next_cursor',v_next,'read_ids',v_read_ids);
 END IF;
 v_ack:=p_action='acknowledge'; v_note:=nullif(btrim(p_payload->>'note'),'');
 IF char_length(v_note)>1000 THEN RAISE EXCEPTION 'Invalid notification request' USING ERRCODE='22023'; END IF;
 IF p_action='read_through' THEN
   IF jsonb_typeof(p_payload->'ids') IS DISTINCT FROM 'array' OR jsonb_array_length(p_payload->'ids')>1000 THEN
     RAISE EXCEPTION 'Invalid notification request' USING ERRCODE='22023'; END IF;
   SELECT coalesce(array_agg(DISTINCT value::uuid),'{}') INTO v_ids FROM jsonb_array_elements_text(p_payload->'ids');
   v_skipped:=cardinality(v_ids);
   -- Only this person's receipts are locked or touched. A receipt in the snapshot that is
   -- no longer authorized (or was never theirs) is skipped, not an error for the batch.
   PERFORM r.id FROM public.notification_receipts r WHERE r.id=ANY(v_ids) AND r.recipient_id=p_actor_id
     ORDER BY r.id FOR UPDATE;
   SELECT coalesce(array_agg(r.id ORDER BY r.id),'{}') INTO v_ids FROM public.notification_receipts r
     JOIN public.notification_events e ON e.id=r.event_id
     WHERE r.id=ANY(v_ids) AND r.recipient_id=p_actor_id AND r.recipient_role=p_actor_role
       AND private.notification_authorized(e,p_actor_id,p_actor_role);
   v_skipped:=v_skipped-cardinality(v_ids);
 ELSE
   v_receipt:=(p_payload->>'id')::uuid;
   SELECT nr.* INTO v_target FROM public.notification_receipts r
     CROSS JOIN LATERAL private.notification_row(r,p_actor_id,p_actor_role) nr
     WHERE r.id=v_receipt AND r.recipient_id=p_actor_id;
   IF NOT FOUND THEN RAISE EXCEPTION 'Notification unavailable' USING ERRCODE='42501'; END IF;
   IF v_ack THEN
     IF NOT v_target.can_acknowledge AND NOT EXISTS(SELECT 1 FROM public.notification_receipts r
       JOIN public.notification_events e ON e.id=r.event_id WHERE r.id=v_receipt AND r.acknowledged_at IS NOT NULL
         AND e.event_type IN ('barrier_reported','safety_flag','appointment_response','critical_result')) THEN
       RAISE EXCEPTION 'Notification cannot be acknowledged' USING ERRCODE='22023'; END IF;
     v_ids:=ARRAY[v_receipt];
   ELSIF v_target.group_key LIKE 'receipt:%' THEN
     v_ids:=ARRAY[v_receipt];
   ELSE
     -- Bound a grouped read by the captured representative, never newer arrivals. Members
     -- already read need nothing, so only the unread index is searched.
     SELECT array_agg(DISTINCT u.id ORDER BY u.id) INTO v_ids FROM (
       SELECT v_receipt id
       UNION ALL SELECT nr.id FROM public.notification_receipts r JOIN public.notification_events e ON e.id=r.event_id
         CROSS JOIN LATERAL private.notification_row(r,p_actor_id,p_actor_role) nr
         WHERE r.recipient_id=p_actor_id AND r.recipient_role=p_actor_role AND r.read_at IS NULL
           AND (e.event_type='message_received' OR e.category='reminders') AND e.patient_id=ANY(v_patients)
           AND nr.group_key=v_target.group_key AND (nr.created_at,nr.id)<=(v_target.created_at,v_target.id)) u;
   END IF;
   PERFORM r.id FROM public.notification_receipts r WHERE r.id=ANY(v_ids) ORDER BY r.id FOR UPDATE;
 END IF;
 FOR x IN SELECT r.*,e.source_type,e.source_id FROM public.notification_receipts r
   JOIN public.notification_events e ON e.id=r.event_id WHERE r.id=ANY(v_ids) ORDER BY r.id LOOP
   IF v_ack AND x.acknowledged_at IS NULL THEN
     UPDATE public.notification_receipts SET acknowledged_at=clock_timestamp() WHERE id=x.id;
     INSERT INTO public.notification_read_audit(receipt_id,actor_id,action,note)
       VALUES(x.id,p_actor_id,'acknowledge',v_note) ON CONFLICT DO NOTHING;
   END IF;
   IF x.read_at IS NULL THEN
     UPDATE public.notification_receipts SET read_at=clock_timestamp() WHERE id=x.id;
     INSERT INTO public.notification_read_audit(receipt_id,actor_id,action) VALUES(x.id,p_actor_id,'read') ON CONFLICT DO NOTHING;
     v_count:=v_count+1;
   END IF;
   IF x.source_type='notifications' THEN UPDATE public.notifications SET is_read=true WHERE id=x.source_id; END IF;
 END LOOP;
 IF p_action='read_through' THEN
   RETURN jsonb_build_object('updated_count',v_count,'skipped_count',v_skipped);
 END IF;
 RETURN jsonb_build_object('updated_count',v_count);
END;
$$;
