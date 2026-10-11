-- NOT-001 follow-up: existing open work keeps the time it actually happened.
--
-- When a clinician first loads their centre, documents awaiting review, draft care
-- plans, ADR drafts and reported barriers that predate a notification are captured
-- then. 051 stamped them with the capture time, so a week-old barrier read
-- "1m ago". This keeps the same function and uses the source row's own time.
-- Events already captured keep their recorded time: history is append only.
CREATE OR REPLACE FUNCTION private.notification_prepare(p_actor uuid,p_role text) RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE x record; v_ev public.notification_events; v_id uuid;
BEGIN
 IF p_role='clinician' THEN
   FOR x IN
     SELECT 'documents'::text typ,d.id,d.patient_id,'document_review'::text kind,'documents'::text category,d.created_at happened
       FROM public.documents d WHERE d.uploaded_by_role='patient' AND d.review_status='pending'
         AND EXISTS(SELECT 1 FROM public.care_teams t WHERE t.patient_id=d.patient_id AND t.clinician_id=p_actor AND t.status='active')
     UNION ALL SELECT 'care_plan_versions',v.id,v.patient_id,'care_plan_draft','care_plans',v.created_at
       FROM public.care_plan_versions v WHERE EXISTS(SELECT 1 FROM public.care_teams t
         WHERE t.patient_id=v.patient_id AND t.clinician_id=p_actor AND t.status='active') AND private.notification_draft_ready(v.id)
     UNION ALL SELECT 'adr_assessments',a.id,a.patient_id,'adr_review','safety',a.created_at
       FROM public.adr_assessments a WHERE a.status='draft' AND EXISTS(SELECT 1 FROM public.care_teams t
         WHERE t.patient_id=a.patient_id AND t.clinician_id=p_actor AND t.status='active')
     UNION ALL SELECT 'adherence_logs',a.id,a.patient_id,'barrier_reported','follow_up',a.logged_at
       FROM public.adherence_logs a WHERE a.status='skipped' AND a.barrier_code IS NOT NULL AND EXISTS(
         SELECT 1 FROM public.care_teams t WHERE t.patient_id=a.patient_id AND t.clinician_id=p_actor AND t.status='active')
   LOOP
     IF NOT EXISTS(SELECT 1 FROM public.care_teams ct JOIN public.clinicians c ON c.id=ct.clinician_id
       JOIN public.clinics cl ON cl.id=c.clinic_id WHERE ct.patient_id=x.patient_id AND ct.clinician_id=p_actor
       AND ct.status='active' AND cl.status='active') THEN CONTINUE; END IF;
     SELECT * INTO v_ev FROM public.notification_events WHERE source_type=x.typ AND source_id=x.id
       AND event_type=x.kind ORDER BY created_at DESC,id DESC LIMIT 1;
     IF NOT FOUND THEN
       v_id:=private.notification_capture(x.typ,x.id,x.patient_id,x.kind,x.category,'shared',NULL,
         '{}'::jsonb,'current:'||x.typ||':'||x.id||':'||x.kind,coalesce(x.happened,clock_timestamp()));
     ELSE v_id:=v_ev.id; END IF;
     INSERT INTO public.notification_pending_deliveries(event_id,recipient_id,recipient_role)
       VALUES(v_id,p_actor,p_role) ON CONFLICT DO NOTHING;
   END LOOP;
   -- Safety is current shared work only if it was captured after this migration.
   INSERT INTO public.notification_pending_deliveries(event_id,recipient_id,recipient_role)
     SELECT e.id,p_actor,p_role FROM public.notification_events e WHERE e.event_type='safety_flag'
       AND private.notification_authorized(e,p_actor,p_role) ON CONFLICT DO NOTHING;
 END IF;
 INSERT INTO public.notification_receipts(event_id,recipient_id,recipient_role,created_at,read_at)
   SELECT e.id,p_actor,p_role,e.created_at,
     CASE WHEN e.source_type='notifications' AND (private.notification_source(e.source_type,e.source_id)->>'is_read')::boolean
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

