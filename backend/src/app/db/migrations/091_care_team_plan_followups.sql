-- PLAN-002 / CLN-003 follow-ups.
--
--   1. SMART launch for a clinician with several links to one patient: the launch session
--      records which care team it is for (smart_launch_sessions.care_team_id). The API fails
--      closed when the named team is not the caller's; the callback re-checks the link and
--      stamps the import with it. Sessions created before this migration have no team and
--      keep the old rule (the only link, or a choice is required).
--   2. Clinic-level review items (addressed to a clinic's admins, no patient detail) reach
--      the notification centre of each ACTIVE ADMIN of that clinic and nobody else. The
--      event carries metadata.scope = 'clinic' and the clinic id; the item JSON returned to
--      the portal carries no patient id or name, and the deep link is a clinic page. They
--      are actionable while the item is open and stop when it is resolved. Care-team items
--      (087) were never part of the action-item list; they are now, too.
--   3. A conflict reply the asking clinician has read can be resolved:
--      public.resolve_conflict_reply accepts the other team's answer (and re-checks whether
--      the conflict still blocks the draft) or keeps both instructions with a written reason
--      (the existing keep-both record), and closes the item. Idempotent; audited.
--
-- Every function below starts from its latest definition (notification_authorized 086,
-- notification_prepare 086, notification_row 086, notification_open_work 060,
-- notification_centre_operation 067, capture_care_plan_review_item 087) and changes only
-- what is named above. Same signatures, so the existing grants still apply.
-- Lock order (OPS-006 rule 7) for resolve_conflict_reply: lock-free authorization read,
-- then the patient evidence advisory lock, then care_plans, care_plan_versions and the
-- review item by primary key; it follows record_cross_plan_resolution, which it calls.

-- ── 1. SMART launch sessions record their care team ──────────────────────────────────────

ALTER TABLE public.smart_launch_sessions
  ADD COLUMN IF NOT EXISTS care_team_id uuid REFERENCES public.care_teams(id) ON DELETE CASCADE;

ALTER TABLE public.smart_launch_sessions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.smart_launch_sessions FROM PUBLIC, anon, authenticated;

-- ── 2. Clinic-level work items reach the clinic's admins ─────────────────────────────────

-- Authorization of a notification (opening, reading, acknowledging).
CREATE OR REPLACE FUNCTION private.notification_authorized(e public.notification_events,p_actor uuid,p_role text)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE s jsonb; t public.care_conversations;
BEGIN
 s:=private.notification_source(e.source_type,e.source_id);
 IF s IS NULL THEN RETURN false; END IF;
 -- A clinic-level work item (no patient detail) belongs to the admins of that clinic only:
 -- the event's own recipient, who must still be an active admin of the addressed clinic.
 IF e.event_type='care_plan_review' AND e.metadata->>'scope'='clinic' THEN
   RETURN p_role='clinician' AND e.audience='clinician' AND e.recipient_id=p_actor
     AND e.source_type='care_plan_review_items'
     AND (s->>'target_clinic_id') IS NOT NULL
     AND s->>'target_clinic_id'=e.metadata->>'clinic_id'
     AND EXISTS(SELECT 1 FROM public.clinic_memberships m JOIN public.clinics cl ON cl.id=m.clinic_id
       WHERE m.clinician_id=p_actor AND m.clinic_id=private.notification_uuid(e.metadata->>'clinic_id')
         AND m.role='admin' AND m.status='active' AND cl.status='active');
 END IF;
 IF e.source_type='care_conversation_messages' THEN
   SELECT * INTO t FROM public.care_conversations WHERE id=(s->>'conversation_id')::uuid;
   RETURN e.recipient_id=p_actor AND EXISTS(SELECT 1 FROM public.care_teams ct
     JOIN public.clinics cl ON cl.id=ct.clinic_id
     JOIN public.clinic_memberships m ON m.clinician_id=ct.clinician_id AND m.clinic_id=ct.clinic_id
     WHERE ct.id=t.care_team_id AND ct.patient_id=t.patient_id AND ct.clinician_id=t.clinician_id
       AND ct.clinic_id=t.clinic_id AND cl.status='active' AND ct.status='active' AND m.status='active'
       AND ((p_role='patient' AND t.patient_id=p_actor) OR (p_role='clinician' AND t.clinician_id=p_actor)));
 END IF;
 IF (s->>'patient_id')::uuid IS DISTINCT FROM e.patient_id THEN RETURN false; END IF;
 IF p_role='patient' THEN
   IF p_actor<>e.patient_id OR e.audience<>'patient' THEN RETURN false; END IF;
   IF e.source_type='care_plan_versions' AND s->>'status' NOT IN ('approved','superseded') THEN RETURN false; END IF;
   IF e.source_type='adr_assessments' AND e.event_type<>'adr_information_requested' THEN RETURN false; END IF;
   RETURN true;
 END IF;
 RETURN p_role='clinician' AND e.audience IN ('clinician','shared')
   AND (e.audience<>'clinician' OR e.recipient_id=p_actor)
   AND EXISTS(SELECT 1 FROM public.care_teams ct JOIN public.clinics cl ON cl.id=ct.clinic_id
     JOIN public.clinic_memberships m ON m.clinician_id=ct.clinician_id AND m.clinic_id=ct.clinic_id
     WHERE ct.patient_id=e.patient_id AND ct.clinician_id=p_actor AND ct.status='active'
       AND cl.status='active' AND m.status='active')
   AND private.notification_owner_sees(e.source_type,e.source_id,e.event_type,p_actor,e.patient_id);
END;
$$;

-- Catch-up: an admin (also one made admin later) is told of the open clinic items once.
CREATE OR REPLACE FUNCTION private.notification_prepare(p_actor uuid,p_role text) RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE x record; v_id uuid; v_patients uuid[];
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('notification_prepare:'||p_actor::text,0));
 IF p_role='clinician' THEN
   v_patients:=private.notification_scope(p_actor,p_role);
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
     ), mine AS (
       SELECT w.* FROM work w WHERE private.notification_owner_sees(w.typ,w.id,w.kind,p_actor,w.patient_id)
     ), known AS (
       SELECT w.*,(SELECT e.id FROM public.notification_events e WHERE e.source_type=w.typ AND e.source_id=w.id
         AND e.event_type=w.kind ORDER BY e.created_at DESC,e.id DESC LIMIT 1) event_id FROM mine w
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
   INSERT INTO public.notification_pending_deliveries(event_id,recipient_id,recipient_role)
     SELECT e.id,p_actor,p_role FROM public.notification_events e WHERE e.event_type='safety_flag'
       AND e.patient_id=ANY(v_patients)
       AND NOT EXISTS(SELECT 1 FROM public.notification_pending_deliveries d WHERE d.event_id=e.id AND d.recipient_id=p_actor)
       AND private.notification_authorized(e,p_actor,p_role) ON CONFLICT DO NOTHING;
   -- A clinic admin (including one made admin after an item was raised) is told of every
   -- open clinic-level work item of a clinic they administer, once.
   FOR x IN SELECT i.id,i.patient_id,i.kind,i.care_plan_id,i.target_clinic_id,i.created_at
       FROM public.care_plan_review_items i
       JOIN public.clinic_memberships m ON m.clinic_id=i.target_clinic_id AND m.clinician_id=p_actor
         AND m.role='admin' AND m.status='active'
       JOIN public.clinics cl ON cl.id=i.target_clinic_id AND cl.status='active'
       WHERE i.status='open' AND i.target_clinic_id IS NOT NULL
         AND NOT EXISTS(SELECT 1 FROM public.notification_events e
           WHERE e.event_key='care_plan_review_items:'||i.id::text||':'||p_actor::text)
       ORDER BY i.id LIMIT 200
   LOOP
     PERFORM private.notification_capture('care_plan_review_items',x.id,x.patient_id,'care_plan_review',
       'care_plans','clinician',p_actor,
       jsonb_build_object('review_kind',x.kind,'care_plan_id',x.care_plan_id,'scope','clinic',
         'clinic_id',x.target_clinic_id),
       'care_plan_review_items:'||x.id::text||':'||p_actor::text,x.created_at);
   END LOOP;
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

-- The item JSON: a clinic-level item names no patient and links no patient.
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
     (a.active AND a.latest AND a.acknowledged_at IS NULL) needs,
     -- The appointment's clinic: from the appointment itself, or from the one a reminder names.
     CASE WHEN a.event_type='care_plan_review' AND a.metadata->>'scope'='clinic'
         THEN private.notification_uuid(a.metadata->>'clinic_id')
       WHEN a.source_type='appointments' THEN private.notification_uuid(a.s->>'clinic_id')
       WHEN a.event_type='appointment_reminder' THEN (SELECT ap.clinic_id FROM public.appointments ap
         WHERE ap.id=private.notification_uuid(a.metadata->>'appointment_id') AND ap.patient_id=a.patient_id)
     END ref_clinic,
     private.notification_owner_team(a.source_type,a.source_id) owner_team,
     (a.event_type='care_plan_review' AND a.metadata->>'scope'='clinic') clinic_scope,
     (p_role='clinician' AND a.event_type='critical_result'
       AND NOT private.notification_owner_sees(a.source_type,a.source_id,'strict',p_actor,a.patient_id)) source_hidden
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
     'source_id',a.source_id,'patient_id',CASE WHEN a.clinic_scope THEN NULL ELSE a.patient_id END,
     'metadata',CASE WHEN a.source_hidden THEN a.metadata||'{"source_accessible":false}'::jsonb ELSE a.metadata END,
     'created_at',a.created_at,
     'is_read',a.seen,'actionable',a.needs,'can_acknowledge',
       p_role='clinician' AND a.event_type IN ('barrier_reported','safety_flag','appointment_response','critical_result') AND a.needs,
     'patient_name',CASE WHEN a.clinic_scope THEN NULL ELSE concat_ws(' ',p.first_name,p.last_name) END,
     'clinic_id',coalesce(a.ref_clinic,ct.clinic_id),
     'clinic_name',CASE WHEN a.ref_clinic IS NOT NULL THEN rc.display_name ELSE coalesce(cl.display_name,ct.clinic_name) END,
     'actor_name',CASE WHEN a.clinic_scope THEN NULL
       ELSE coalesce(a.metadata->>'actor_name',concat_ws(' ',c.first_name,c.last_name)) END)
 FROM states a JOIN public.patients p ON p.id=a.patient_id
 LEFT JOIN LATERAL (SELECT t.* FROM public.care_teams t WHERE t.patient_id=a.patient_id AND t.status='active' AND NOT a.clinic_scope
   AND (CASE WHEN p_role='clinician' THEN t.clinician_id=p_actor
     WHEN a.metadata->>'clinician_id' IS NOT NULL THEN t.clinician_id=(a.metadata->>'clinician_id')::uuid ELSE true END)
   ORDER BY coalesce(t.id=a.owner_team,false) DESC,t.id LIMIT 1) ct ON true
 LEFT JOIN public.clinicians c ON c.id=ct.clinician_id LEFT JOIN public.clinics cl ON cl.id=ct.clinic_id
 LEFT JOIN public.clinics rc ON rc.id=a.ref_clinic;
$$;

-- Open work: care-team items and the clinic items of clinics I administer.
CREATE OR REPLACE FUNCTION private.notification_open_work(p_actor uuid,p_role text,p_patients uuid[])
RETURNS SETOF public.notification_receipts
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 -- OFFSET 0 keeps each lookup a per-row index probe from the open source, so the plan
 -- cannot turn around and scan all of this person's receipts or all events.
 WITH open_events AS MATERIALIZED (
   SELECT x.id FROM public.documents d CROSS JOIN LATERAL (SELECT e.id FROM public.notification_events e
       WHERE e.source_type='documents' AND e.source_id=d.id
         AND ((e.event_type='document_review' AND d.review_status='pending') OR (e.event_type='document_failed'
           AND d.parse_status IN ('failed','needs_ocr','needs_evidence_review'))) OFFSET 0) x
     WHERE d.patient_id=ANY(p_patients)
       AND (d.review_status='pending' OR d.parse_status IN ('failed','needs_ocr','needs_evidence_review'))
   UNION ALL SELECT x.id FROM public.care_plan_versions v CROSS JOIN LATERAL (SELECT e.id
       FROM public.notification_events e WHERE e.source_type='care_plan_versions' AND e.source_id=v.id
         AND e.event_type='care_plan_draft' OFFSET 0) x
     WHERE v.patient_id=ANY(p_patients) AND v.status='draft'
   UNION ALL SELECT x.id FROM public.adr_assessments a CROSS JOIN LATERAL (SELECT e.id
       FROM public.notification_events e WHERE e.source_type='adr_assessments' AND e.source_id=a.id
         AND e.event_type='adr_review' OFFSET 0) x
     WHERE a.patient_id=ANY(p_patients) AND a.status='draft'
   UNION ALL SELECT x.id FROM public.adherence_logs a CROSS JOIN LATERAL (SELECT e.id
       FROM public.notification_events e WHERE e.source_type='adherence_logs' AND e.source_id=a.id
         AND e.event_type='barrier_reported' OFFSET 0) x
     WHERE a.patient_id=ANY(p_patients) AND a.status='skipped' AND a.barrier_code IS NOT NULL
   UNION ALL SELECT x.id FROM public.appointments a CROSS JOIN LATERAL (SELECT e.id
       FROM public.notification_events e WHERE e.source_type='appointments' AND e.source_id=a.id
         AND e.event_type='appointment_response' OFFSET 0) x
     WHERE a.patient_id=ANY(p_patients) AND a.status IN ('declined','alternative_requested','cancelled')
   UNION ALL SELECT e.id FROM public.notification_events e
     WHERE e.event_type='safety_flag' AND e.patient_id=ANY(p_patients)
   -- Care-team work items (patient in scope) and clinic-level items (clinics I administer).
   UNION ALL SELECT x.id FROM public.care_plan_review_items i CROSS JOIN LATERAL (SELECT e.id
       FROM public.notification_events e WHERE e.source_type='care_plan_review_items' AND e.source_id=i.id
         AND e.event_type='care_plan_review' OFFSET 0) x
     WHERE i.status='open' AND (i.patient_id=ANY(p_patients) OR i.target_clinic_id IN (
       SELECT m.clinic_id FROM public.clinic_memberships m
         WHERE m.clinician_id=p_actor AND m.role='admin' AND m.status='active'))
   UNION ALL SELECT e.id FROM public.notification_events e
     WHERE e.event_type='critical_result' AND e.patient_id=ANY(p_patients)
       AND NOT EXISTS(SELECT 1 FROM public.documents d
         WHERE d.id=e.source_id AND d.review_status='rejected')
 )
 SELECT r.* FROM open_events o CROSS JOIN LATERAL (SELECT n.* FROM public.notification_receipts n
   WHERE n.event_id=o.id AND n.recipient_id=p_actor AND n.recipient_role=p_role
     AND n.acknowledged_at IS NULL OFFSET 0) r
 WHERE p_role='clinician'
$$;

-- Operation: a clinic-level item is not tied to the patients in the caller's scope.
CREATE OR REPLACE FUNCTION public.notification_centre_operation(
 p_actor_id uuid,p_actor_role text,p_action text,p_payload jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v_limit int; v_items jsonb; v_next jsonb; v_ids uuid[]; v_read_ids jsonb; v_count int:=0;
  x record; v_target record; v_note text; v_ack boolean; v_receipt uuid; v_skipped int:=0; v_actions int:=0;
  v_patients uuid[]; v_clinic uuid; v_list boolean; v_unread boolean; v_category text;
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
   JOIN public.clinicians c ON c.id=t.clinician_id JOIN public.clinics cl ON cl.id=t.clinic_id
   WHERE t.status='active' AND ((p_actor_role='patient' AND t.patient_id=p_actor_id)
     OR (p_actor_role='clinician' AND t.clinician_id=p_actor_id)) ORDER BY t.id FOR SHARE OF t,p,c,cl;
 PERFORM private.notification_prepare(p_actor_id,p_actor_role);
 v_patients:=private.notification_scope(p_actor_id,p_actor_role);
 -- A clinician's clinic filter: only patients linked at that clinic, and only where the caller
 -- holds an active membership. Any other clinic is an empty list, never an error.
 IF p_actor_role='clinician' AND p_action IN ('list','action_items') AND p_payload ? 'clinic_id' THEN
   v_clinic:=(p_payload->>'clinic_id')::uuid;
   v_patients:=coalesce((SELECT array_agg(DISTINCT t.patient_id) FROM public.care_teams t
     JOIN public.clinic_memberships cm ON cm.clinician_id=t.clinician_id AND cm.clinic_id=t.clinic_id
     JOIN public.clinics cc ON cc.id=t.clinic_id
     WHERE t.clinician_id=p_actor_id AND t.status='active' AND t.patient_id=ANY(v_patients)
       AND cm.status='active' AND cc.status='active'
       AND t.clinic_id=(p_payload->>'clinic_id')::uuid),'{}');
 END IF;

 IF p_action='summary' THEN
   -- Unread: only receipts in the unread index are evaluated.
   SELECT count(DISTINCT nr.group_key) INTO v_count FROM public.notification_receipts r
     JOIN public.notification_events e ON e.id=r.event_id
     CROSS JOIN LATERAL private.notification_row(r,p_actor_id,p_actor_role) nr
     WHERE r.recipient_id=p_actor_id AND r.recipient_role=p_actor_role AND r.read_at IS NULL
       AND (e.patient_id=ANY(v_patients) OR (e.event_type='care_plan_review' AND e.metadata->>'scope'='clinic'))
       AND NOT nr.is_read;
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
     WHERE r.recipient_id=$1 AND r.recipient_role=$2 AND (e.patient_id=ANY($3)
       OR (e.event_type=''care_plan_review'' AND e.metadata->>''scope''=''clinic''
         AND ($8::uuid IS NULL OR e.metadata->>''clinic_id''=$8::text)))
       AND ($4::timestamptz IS NULL OR (r.created_at,r.id)<($4,$5)) AND ($7::text IS NULL OR e.category=$7)'
     ||CASE WHEN NOT v_list THEN ' AND e.category<>''messages'''
       WHEN v_unread THEN ' AND r.read_at IS NULL AND e.event_type<>''message_received'' AND e.category<>''reminders'''
       ELSE ' AND NOT (r.read_at IS NULL AND (e.event_type=''message_received'' OR e.category=''reminders''))' END
     ||' ORDER BY r.created_at DESC,r.id DESC LIMIT $6';
   v_window:=greatest(2*(v_limit+1),50); v_pos_at:=v_before_at; v_pos_id:=v_before_id;
   <<walk>> LOOP
     v_fetched:=0;
     FOR v_r IN EXECUTE v_walk USING p_actor_id,p_actor_role,v_patients,v_pos_at,v_pos_id,v_window,v_category,v_clinic LOOP
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

-- Capture: a team item goes to the team's clinician (087); a clinic item to each active admin.
CREATE OR REPLACE FUNCTION private.capture_care_plan_review_item() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_recipient uuid;
BEGIN
  IF NEW.status <> 'open' THEN RETURN NEW; END IF;
  IF NEW.target_care_team_id IS NOT NULL THEN
    SELECT clinician_id INTO v_recipient FROM public.care_teams
      WHERE id = NEW.target_care_team_id AND status = 'active' AND patient_id = NEW.patient_id;
    IF v_recipient IS NULL THEN RETURN NEW; END IF;
    PERFORM private.notification_capture('care_plan_review_items', NEW.id, NEW.patient_id,
      'care_plan_review', 'care_plans', 'clinician', v_recipient,
      jsonb_build_object('review_kind', NEW.kind, 'care_plan_id', NEW.care_plan_id),
      'care_plan_review_items:' || NEW.id::text, NEW.created_at);
  ELSIF NEW.target_clinic_id IS NOT NULL THEN
    -- The event names the kind and plan, never the patient's name or any conflict wording.
    FOR v_recipient IN
      SELECT m.clinician_id FROM public.clinic_memberships m
        JOIN public.clinics cl ON cl.id = m.clinic_id AND cl.status = 'active'
        WHERE m.clinic_id = NEW.target_clinic_id AND m.role = 'admin' AND m.status = 'active'
        ORDER BY m.clinician_id
    LOOP
      PERFORM private.notification_capture('care_plan_review_items', NEW.id, NEW.patient_id,
        'care_plan_review', 'care_plans', 'clinician', v_recipient,
        jsonb_build_object('review_kind', NEW.kind, 'care_plan_id', NEW.care_plan_id,
          'scope', 'clinic', 'clinic_id', NEW.target_clinic_id),
        'care_plan_review_items:' || NEW.id::text || ':' || v_recipient::text, NEW.created_at);
    END LOOP;
  END IF;
  RETURN NEW;
END;
$$;

-- Clinic items that were already open: one event per active admin, delivered once.
INSERT INTO public.notification_events(event_key, event_type, category, source_type, source_id,
  patient_id, audience, recipient_id, metadata, created_at)
SELECT 'care_plan_review_items:' || i.id::text || ':' || m.clinician_id::text, 'care_plan_review',
  'care_plans', 'care_plan_review_items', i.id, i.patient_id, 'clinician', m.clinician_id,
  jsonb_build_object('review_kind', i.kind, 'care_plan_id', i.care_plan_id, 'scope', 'clinic',
    'clinic_id', i.target_clinic_id), i.created_at
FROM public.care_plan_review_items i
JOIN public.clinics cl ON cl.id = i.target_clinic_id AND cl.status = 'active'
JOIN public.clinic_memberships m ON m.clinic_id = i.target_clinic_id AND m.role = 'admin'
  AND m.status = 'active'
WHERE i.status = 'open' AND i.target_clinic_id IS NOT NULL
ON CONFLICT (event_key) DO NOTHING;
INSERT INTO public.notification_pending_deliveries(event_id, recipient_id, recipient_role)
SELECT e.id, e.recipient_id, 'clinician' FROM public.notification_events e
WHERE e.source_type = 'care_plan_review_items' AND e.metadata->>'scope' = 'clinic'
  AND e.recipient_id IS NOT NULL
ON CONFLICT DO NOTHING;

-- ── 3. Resolving a conflict reply ────────────────────────────────────────────────────────

-- p_action 'accept':    the other team's answer is accepted; the item closes. The result says
--                       whether the conflict still blocks the current draft (it is re-checked
--                       against the live plans; nothing is assumed cleared).
-- p_action 'keep_both': the existing keep-both record (needs a written reason and a draft
--                       that still has the conflict), then the item closes.
CREATE OR REPLACE FUNCTION public.resolve_conflict_reply(
  p_item_id uuid, p_actor_id uuid, p_action text, p_reason text DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_item public.care_plan_review_items%ROWTYPE;
  v_plan public.care_plans%ROWTYPE;
  v_draft public.care_plan_versions%ROWTYPE;
  v_audit_version uuid;
  v_blocking boolean := false;
BEGIN
  IF p_action IS NULL OR p_action NOT IN ('accept', 'keep_both') THEN
    RAISE EXCEPTION 'unsupported action' USING ERRCODE = '22023';
  END IF;
  IF p_action = 'keep_both'
     AND (p_reason IS NULL OR char_length(btrim(p_reason)) NOT BETWEEN 1 AND 2000) THEN
    RAISE EXCEPTION 'a written reason is required' USING ERRCODE = '22023';
  END IF;
  IF p_action = 'accept' AND p_reason IS NOT NULL AND char_length(btrim(p_reason)) > 2000 THEN
    RAISE EXCEPTION 'a written reason is required' USING ERRCODE = '22023';
  END IF;
  -- Authorize before taking any lock: only the asking team's clinician, and only a reply.
  SELECT * INTO v_item FROM public.care_plan_review_items WHERE id = p_item_id;
  IF NOT FOUND OR v_item.kind <> 'conflict_reply' OR v_item.target_care_team_id IS NULL
     OR NOT private.clinician_holds_link(p_actor_id, v_item.target_care_team_id) THEN
    RAISE EXCEPTION 'review item unavailable' USING ERRCODE = '42501';
  END IF;
  PERFORM private.lock_care_plan_evidence(v_item.patient_id, true);
  SELECT * INTO v_plan FROM public.care_plans WHERE id = v_item.care_plan_id FOR UPDATE;
  SELECT * INTO v_draft FROM public.care_plan_versions
    WHERE care_plan_id = v_item.care_plan_id AND status = 'draft'
    ORDER BY version_number DESC LIMIT 1 FOR UPDATE;
  SELECT * INTO v_item FROM public.care_plan_review_items WHERE id = p_item_id FOR UPDATE;
  -- Guarded transition: authority and state are re-read under the locks.
  IF NOT private.clinician_holds_link(p_actor_id, v_item.target_care_team_id) THEN
    RAISE EXCEPTION 'review item unavailable' USING ERRCODE = '42501';
  END IF;
  IF v_item.status <> 'open' THEN
    RETURN jsonb_build_object('id', p_item_id, 'status', v_item.status, 'replayed', true);
  END IF;
  IF p_action = 'keep_both' THEN
    IF v_draft.id IS NULL OR v_item.conflict_fingerprint IS NULL THEN
      RAISE EXCEPTION 'this conflict has changed; review it again' USING ERRCODE = '40001';
    END IF;
    PERFORM public.record_cross_plan_resolution(v_draft.id, p_actor_id,
      v_item.conflict_fingerprint, 'keep_both', p_reason);
  END IF;
  -- Re-run the blocker check against the live plans: blocking means the same conflict is
  -- still present on the draft and has no current keep-both reason.
  IF v_draft.id IS NOT NULL AND v_item.conflict_fingerprint IS NOT NULL THEN
    v_blocking := EXISTS (
      SELECT 1 FROM private.care_plan_cross_conflicts(v_draft.id) c
       WHERE c.fingerprint = v_item.conflict_fingerprint AND c.severity = 'blocker'
         AND NOT EXISTS (SELECT 1 FROM public.care_plan_conflict_resolutions r
           WHERE r.plan_version_id = v_draft.id AND r.fingerprint = c.fingerprint
             AND r.resolution = 'keep_both' AND btrim(r.reason) <> ''));
  END IF;
  UPDATE public.care_plan_review_items
     SET status = 'resolved', resolved_by = p_actor_id, resolved_at = clock_timestamp()
   WHERE id = p_item_id AND status = 'open';
  SELECT id INTO v_audit_version FROM public.care_plan_versions
    WHERE care_plan_id = v_item.care_plan_id ORDER BY version_number DESC LIMIT 1;
  IF v_audit_version IS NOT NULL THEN
    INSERT INTO public.care_plan_audit_events(plan_version_id, actor_id, event_type, event_data)
    VALUES (v_audit_version, p_actor_id, 'conflict_reply_resolved',
      jsonb_build_object('review_item_id', p_item_id, 'action', p_action,
        'fingerprint', v_item.conflict_fingerprint, 'still_blocking', v_blocking));
  END IF;
  RETURN jsonb_build_object('id', p_item_id, 'status', 'resolved', 'action', p_action,
    'still_blocking', v_blocking, 'draft_version_id', v_draft.id, 'replayed', false);
END;
$$;

-- ── 4. Grants and verification ───────────────────────────────────────────────────────────

REVOKE ALL ON FUNCTION
  private.notification_authorized(public.notification_events, uuid, text),
  private.notification_prepare(uuid, text),
  private.notification_row(public.notification_receipts, uuid, text),
  private.notification_open_work(uuid, text, uuid[]),
  private.capture_care_plan_review_item(),
  public.notification_centre_operation(uuid, text, text, jsonb),
  public.resolve_conflict_reply(uuid, uuid, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION
  private.notification_authorized(public.notification_events, uuid, text),
  private.notification_prepare(uuid, text),
  private.notification_row(public.notification_receipts, uuid, text),
  private.notification_open_work(uuid, text, uuid[]),
  private.capture_care_plan_review_item(),
  public.notification_centre_operation(uuid, text, text, jsonb),
  public.resolve_conflict_reply(uuid, uuid, text, text)
  TO service_role;

DO $verify$
DECLARE v_function text;
BEGIN
  FOREACH v_function IN ARRAY ARRAY[
    'private.notification_authorized(public.notification_events,uuid,text)',
    'private.notification_prepare(uuid,text)',
    'private.notification_row(public.notification_receipts,uuid,text)',
    'private.notification_open_work(uuid,text,uuid[])',
    'private.capture_care_plan_review_item()',
    'public.notification_centre_operation(uuid,text,text,jsonb)',
    'public.resolve_conflict_reply(uuid,uuid,text,text)'] LOOP
    IF has_function_privilege('anon', v_function, 'EXECUTE')
       OR has_function_privilege('authenticated', v_function, 'EXECUTE')
       OR NOT has_function_privilege('service_role', v_function, 'EXECUTE') THEN
      RAISE EXCEPTION '091: wrong execute grants on %', v_function;
    END IF;
  END LOOP;
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.smart_launch_sessions'::regclass)
     OR has_table_privilege('anon', 'public.smart_launch_sessions', 'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('authenticated', 'public.smart_launch_sessions', 'SELECT,INSERT,UPDATE,DELETE') THEN
    RAISE EXCEPTION '091: smart_launch_sessions must stay backend-only';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'smart_launch_sessions'
        AND column_name = 'care_team_id') THEN
    RAISE EXCEPTION '091: smart_launch_sessions.care_team_id is missing';
  END IF;
  IF (SELECT prosrc FROM pg_proc WHERE oid = 'private.notification_authorized(public.notification_events,uuid,text)'::regprocedure)
     NOT LIKE '%clinic_memberships%'
     OR (SELECT prosrc FROM pg_proc WHERE oid = 'private.notification_authorized(public.notification_events,uuid,text)'::regprocedure)
     NOT LIKE '%notification_owner_sees%' THEN
    RAISE EXCEPTION '091: notification_authorized lost a check';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_proc
              WHERE proname IN ('notification_row', 'notification_centre_operation')
                AND prosrc ~ 'cl\.id\s*=\s*c\.clinic_id') THEN
    RAISE EXCEPTION '091: notification clinic labels must come from the care-team link''s clinic';
  END IF;
  -- No clinic-level event may exist for a recipient who is not an admin of its clinic.
  IF EXISTS (SELECT 1 FROM public.notification_events e
      WHERE e.event_type = 'care_plan_review' AND e.metadata->>'scope' = 'clinic'
        AND e.audience <> 'clinician') THEN
    RAISE EXCEPTION '091: a clinic-level notification must address a single clinician';
  END IF;
END
$verify$;
