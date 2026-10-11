-- NOT-001 follow-up: parallel requests agree on what has arrived.
--
-- A portal refresh sends the summary and both lists at once. 054 let a request skip
-- prepare while another request for the same person was running it, so the list could
-- miss an item that the summary had just delivered and counted ("2 unread", one shown)
-- until the next refresh. Prepare now waits for the other request to commit. It is the
-- same function otherwise.
CREATE OR REPLACE FUNCTION private.notification_prepare(p_actor uuid,p_role text) RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE x record; v_id uuid; v_patients uuid[];
BEGIN
 -- A concurrent request for this person is doing the same work. Wait for it to commit
 -- rather than skip, so this request sees what it delivered; the work left is then an
 -- index probe.
 PERFORM pg_advisory_xact_lock(hashtextextended('notification_prepare:'||p_actor::text,0));
 IF p_role='clinician' THEN
   v_patients:=private.notification_scope(p_actor,p_role);
   -- Newly assigned reviewers receive current shared work for the patients they are
   -- assigned to now, never private thread history or resolved tasks. Work already
   -- delivered to this clinician costs an index probe, not a loop iteration.
   FOR x IN
     WITH work AS (
       SELECT 'documents'::text typ,d.id,d.patient_id,'document_review'::text kind,'documents'::text category,d.created_at happened
         FROM public.documents d WHERE d.patient_id=ANY(v_patients) AND d.uploaded_by_role='patient' AND d.review_status='pending'
       UNION ALL SELECT 'care_plan_versions',v.id,v.patient_id,'care_plan_draft','care_plans',v.created_at
         FROM public.care_plan_versions v WHERE v.patient_id=ANY(v_patients) AND v.status='draft'
           AND private.notification_draft_ready(v.id)
       UNION ALL SELECT 'adr_assessments',a.id,a.patient_id,'adr_review','safety',a.created_at
         FROM public.adr_assessments a WHERE a.patient_id=ANY(v_patients) AND a.status='draft'
       UNION ALL SELECT 'adherence_logs',a.id,a.patient_id,'barrier_reported','follow_up',a.logged_at
         FROM public.adherence_logs a WHERE a.patient_id=ANY(v_patients) AND a.status='skipped' AND a.barrier_code IS NOT NULL
     ), known AS (
       SELECT w.*,(SELECT e.id FROM public.notification_events e WHERE e.source_type=w.typ AND e.source_id=w.id
         AND e.event_type=w.kind ORDER BY e.created_at DESC,e.id DESC LIMIT 1) event_id FROM work w
     )
     SELECT * FROM known k WHERE k.event_id IS NULL OR NOT EXISTS(SELECT 1 FROM public.notification_pending_deliveries d
       WHERE d.event_id=k.event_id AND d.recipient_id=p_actor)
   LOOP
     IF x.event_id IS NULL THEN
       v_id:=private.notification_capture(x.typ,x.id,x.patient_id,x.kind,x.category,'shared',NULL,
         '{}'::jsonb,'current:'||x.typ||':'||x.id||':'||x.kind,coalesce(x.happened,clock_timestamp()));
     ELSE v_id:=x.event_id; END IF;
     INSERT INTO public.notification_pending_deliveries(event_id,recipient_id,recipient_role)
       VALUES(v_id,p_actor,p_role) ON CONFLICT DO NOTHING;
   END LOOP;
   -- Capture already delivers safety flags to the active care team. This backfills a
   -- newly assigned reviewer, for their own patients only.
   INSERT INTO public.notification_pending_deliveries(event_id,recipient_id,recipient_role)
     SELECT e.id,p_actor,p_role FROM public.notification_events e WHERE e.event_type='safety_flag'
       AND e.patient_id=ANY(v_patients)
       AND NOT EXISTS(SELECT 1 FROM public.notification_pending_deliveries d WHERE d.event_id=e.id AND d.recipient_id=p_actor)
       AND private.notification_authorized(e,p_actor,p_role) ON CONFLICT DO NOTHING;
 END IF;
 INSERT INTO public.notification_receipts(event_id,recipient_id,recipient_role,created_at,read_at)
   SELECT e.id,p_actor,p_role,e.created_at,
     CASE WHEN (e.source_type='notifications'
         AND coalesce((private.notification_source(e.source_type,e.source_id)->>'is_read')::boolean,false))
       OR (e.event_type='message_received' AND EXISTS(SELECT 1 FROM public.care_conversation_messages m
         JOIN public.care_conversation_reads cr ON cr.conversation_id=m.conversation_id AND cr.actor_id=p_actor
         WHERE m.id=e.source_id AND (m.created_at,m.id)<=(cr.last_message_at,cr.last_message_id)))
     THEN clock_timestamp() ELSE NULL END
   FROM public.notification_pending_deliveries d JOIN public.notification_events e ON e.id=d.event_id
   WHERE d.recipient_id=p_actor AND d.recipient_role=p_role AND d.delivered_at IS NULL
     AND private.notification_authorized(e,p_actor,p_role)
     AND (e.event_type<>'care_plan_draft' OR private.notification_draft_ready(e.source_id))
   ON CONFLICT(event_id,recipient_id) DO NOTHING;
 UPDATE public.notification_pending_deliveries d SET delivered_at=clock_timestamp()
   WHERE recipient_id=p_actor AND delivered_at IS NULL AND EXISTS(SELECT 1 FROM public.notification_receipts r
     WHERE r.event_id=d.event_id AND r.recipient_id=p_actor);
END;
$$;
