-- NOT-001 follow-up: reads cost what the page shows, and "mark all read" skips.
--
-- Fan-out stays on write: capture triggers insert pending deliveries. 051 then made every
-- summary, list and action-item request scan current work and every safety flag system
-- wide, and build, authorize and read the source of every receipt the person ever had
-- before applying LIMIT. Now:
--   * prepare converts only this person's undelivered deliveries and, for a clinician,
--     backfills current work and safety flags for the patients they are assigned to now;
--   * lists walk the person's receipts newest first from the cursor in bounded windows
--     and authorize only what they walk; unread groups come from the unread index;
--   * unread counts use the unread index; action items start from work that is still
--     open for the clinician's patients, not from their whole history;
--   * read markers and legacy is_read now also set receipt.read_at, so the unread index
--     holds what is actually unread. Read-time checks of both are kept.
-- Result shapes, ordering, grouping and cursors are unchanged. read_through now marks the
-- authorized receipts of the signed snapshot and reports the rest as skipped.

CREATE INDEX notification_events_safety ON public.notification_events(patient_id)
  WHERE event_type = 'safety_flag';

-- Requester rule for clinician "Needs attention": appointment responses are classified by
-- what the patient answered (see notification_actionable below).
CREATE OR REPLACE FUNCTION private.notification_actionable(e public.notification_events,p_role text) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE s jsonb:=private.notification_source(e.source_type,e.source_id);
BEGIN
 IF s IS NULL THEN RETURN false; END IF;
 CASE e.event_type
 WHEN 'message_received' THEN RETURN true;
 WHEN 'legacy_update' THEN RETURN false;
 WHEN 'care_plan_draft' THEN RETURN p_role='clinician' AND private.notification_draft_ready(e.source_id);
 WHEN 'care_plan_published' THEN RETURN s->>'status'='approved';
 WHEN 'document_review' THEN RETURN p_role='clinician' AND s->>'uploaded_by_role'='patient' AND s->>'review_status'='pending';
 WHEN 'document_processed' THEN RETURN s->>'parse_status'='completed' AND s->>'review_status' IS DISTINCT FROM 'rejected';
 WHEN 'document_failed' THEN RETURN s->>'parse_status' IN ('failed','needs_ocr','needs_evidence_review');
 WHEN 'document_reviewed' THEN RETURN s->>'review_status' IN ('approved','rejected');
 WHEN 'adr_review' THEN RETURN p_role='clinician' AND s->>'status'='draft';
 WHEN 'adr_information_requested' THEN RETURN s->>'status'='draft' AND s->>'last_review_action'='request_information';
 WHEN 'barrier_reported' THEN RETURN p_role='clinician' AND s->>'status'='skipped' AND s->>'barrier_code' IS NOT NULL;
 WHEN 'safety_flag' THEN RETURN p_role='clinician';
 WHEN 'med_reminder','obligation_reminder' THEN RETURN private.notification_reminder_active(s);
 WHEN 'appointment_offered' THEN
   -- Answered offers (accepted, declined, withdrawn, expired) no longer ask for action.
   RETURN coalesce(s->>'status'='proposed'
     AND private.notification_ts(s->>'scheduled_at')>clock_timestamp()
     AND (nullif(s->>'proposal_expires_at','') IS NULL
       OR private.notification_ts(s->>'proposal_expires_at')>clock_timestamp()),false);
 WHEN 'appointment_response' THEN
   -- A confirmation is news, not work. A decline, request for another time or
   -- cancellation needs the responsible clinician until they acknowledge it (receipt
   -- state, checked by the caller) or a later offer or booking for the same patient and
   -- care team answers it. The visit time no longer matters. Declining a multi-slot
   -- offer changes every slot, so one slot of the offer carries the item.
   RETURN coalesce(p_role='clinician' AND s->>'status' IN ('declined','alternative_requested','cancelled')
     AND NOT EXISTS(SELECT 1 FROM public.appointments a WHERE a.patient_id=e.patient_id
       AND a.care_team_id=private.notification_uuid(s->>'care_team_id') AND a.id<>e.source_id
       AND a.created_at>e.created_at)
     AND NOT EXISTS(SELECT 1 FROM public.appointments a
       WHERE a.proposal_group_id=private.notification_uuid(s->>'proposal_group_id')
         AND a.status::text=s->>'status' AND a.id<e.source_id),false);
 WHEN 'appointment_reminder' THEN
   SELECT to_jsonb(a) INTO s FROM public.appointments a
     WHERE a.id=private.notification_uuid(e.metadata->>'appointment_id') AND a.patient_id=e.patient_id;
   RETURN coalesce(s->>'status' IN ('confirmed','scheduled')
     AND private.notification_ts(s->>'scheduled_at')>clock_timestamp(),false);
 ELSE RETURN coalesce(s->>'status' IN ('proposed','confirmed','scheduled')
   AND private.notification_ts(s->>'scheduled_at')>clock_timestamp()
   AND (s->>'status'<>'proposed' OR nullif(s->>'proposal_expires_at','') IS NULL
     OR private.notification_ts(s->>'proposal_expires_at')>clock_timestamp()),false);
 END CASE;
END;
$$;

-- One receipt as the centre shows it, or no row when the person may not see it. Same
-- semantics as 051's notification_rows, which is redefined on top of it below.
CREATE FUNCTION private.notification_row(p_receipt public.notification_receipts,p_actor uuid,p_role text)
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
   (p_role='clinician' AND a.event_type IN ('barrier_reported','safety_flag','appointment_response') AND a.needs),
   CASE WHEN a.event_type='message_received' THEN 'message:'||(a.metadata->>'conversation_id')
     WHEN a.category='reminders' THEN 'reminder:'||coalesce(a.metadata->>'target_id',a.source_id::text)||':'||
       coalesce((private.notification_ts(a.metadata->>'scheduled_at')
         AT TIME ZONE private.notification_zone(p.timezone))::date::text,a.created_at::date::text)
     ELSE 'receipt:'||a.id END,
   jsonb_build_object('id',a.id,'event_type',a.event_type,'category',a.category,'source_type',a.source_type,
     'source_id',a.source_id,'patient_id',a.patient_id,'metadata',a.metadata,'created_at',a.created_at,
     'is_read',a.seen,'actionable',a.needs,'can_acknowledge',
       p_role='clinician' AND a.event_type IN ('barrier_reported','safety_flag','appointment_response') AND a.needs,
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

CREATE OR REPLACE FUNCTION private.notification_rows(p_actor uuid,p_role text)
RETURNS TABLE(id uuid,event_id uuid,created_at timestamptz,is_read boolean,actionable boolean,
  can_acknowledge boolean,group_key text,item jsonb)
LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT x.* FROM public.notification_receipts r
   CROSS JOIN LATERAL private.notification_row(r,p_actor,p_role) x
 WHERE r.recipient_id=p_actor AND r.recipient_role=p_role;
$$;

-- A clinician's possible action items, driven by work that is still open for the patients
-- in scope rather than by every receipt they ever had. Never a decision: it admits
-- every receipt notification_actionable could call open for a clinician (the only
-- clinician-audience kinds are below), and notification_row decides. Patients have none.
CREATE FUNCTION private.notification_open_work(p_actor uuid,p_role text,p_patients uuid[])
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
 )
 SELECT r.* FROM open_events o CROSS JOIN LATERAL (SELECT n.* FROM public.notification_receipts n
   WHERE n.event_id=o.id AND n.recipient_id=p_actor AND n.recipient_role=p_role
     AND n.acknowledged_at IS NULL OFFSET 0) r
 WHERE p_role='clinician'
$$;

-- Open barriers are found per patient by prepare and by open work; without this a
-- patient's whole adherence history is read for each request.
CREATE INDEX adherence_logs_open_barriers ON public.adherence_logs(patient_id)
  WHERE status='skipped' AND barrier_code IS NOT NULL;

-- The patients whose notifications this person could be authorized for. Every rule in
-- notification_authorized implies this, so it narrows what is walked; it never grants.
CREATE FUNCTION private.notification_scope(p_actor uuid,p_role text) RETURNS uuid[]
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT CASE WHEN p_role='patient' THEN ARRAY[p_actor] ELSE
   (SELECT coalesce(array_agg(DISTINCT t.patient_id),'{}') FROM public.care_teams t
     JOIN public.clinicians c ON c.id=t.clinician_id JOIN public.clinics cl ON cl.id=c.clinic_id
     WHERE t.clinician_id=p_actor AND t.status='active' AND cl.status='active') END
$$;

-- Same contract as 052, scoped to this person.
CREATE OR REPLACE FUNCTION private.notification_prepare(p_actor uuid,p_role text) RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE x record; v_id uuid; v_patients uuid[];
BEGIN
 -- A concurrent request for this person is doing the same work, and what it writes is
 -- visible to later requests once it commits. Skipping avoids queueing on its locks.
 IF NOT pg_try_advisory_xact_lock(hashtextextended('notification_prepare:'||p_actor::text,0)) THEN
   RETURN;
 END IF;
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

-- Keep receipt.read_at in step with the two other ways a notification becomes read, so
-- the unread index holds what is unread. Read time still checks both, so a write that
-- cannot sync (a browser role without receipt access) changes nothing that is shown.
CREATE FUNCTION private.notification_sync_conversation_read() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v_from_at timestamptz; v_from_id uuid;
BEGIN
 -- An advanced marker only needs the messages between the old and new position.
 IF TG_OP='UPDATE' THEN v_from_at:=OLD.last_message_at; v_from_id:=OLD.last_message_id; END IF;
 UPDATE public.notification_receipts r SET read_at=clock_timestamp()
   FROM public.care_conversation_messages m JOIN public.notification_events e
     ON e.source_type='care_conversation_messages' AND e.source_id=m.id AND e.event_type='message_received'
   WHERE m.conversation_id=NEW.conversation_id
     AND (m.created_at,m.id)<=(NEW.last_message_at,NEW.last_message_id)
     AND (v_from_at IS NULL OR (m.created_at,m.id)>(v_from_at,v_from_id))
     AND r.event_id=e.id AND r.recipient_id=NEW.actor_id AND r.read_at IS NULL;
 RETURN NULL;
EXCEPTION WHEN insufficient_privilege THEN RETURN NULL;
END;
$$;
CREATE TRIGGER notification_read_marker AFTER INSERT OR UPDATE ON public.care_conversation_reads
  FOR EACH ROW EXECUTE FUNCTION private.notification_sync_conversation_read();

CREATE FUNCTION private.notification_sync_legacy_read() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 UPDATE public.notification_receipts r SET read_at=clock_timestamp()
   FROM public.notification_events e
   WHERE e.source_type='notifications' AND e.source_id=NEW.id AND r.event_id=e.id
     AND r.recipient_id=NEW.patient_id AND r.read_at IS NULL;
 RETURN NULL;
EXCEPTION WHEN insufficient_privilege THEN RETURN NULL;
END;
$$;
CREATE TRIGGER notification_legacy_read AFTER UPDATE OF is_read ON public.notifications
  FOR EACH ROW WHEN (NEW.is_read IS TRUE AND OLD.is_read IS NOT TRUE)
  EXECUTE FUNCTION private.notification_sync_legacy_read();

-- One-time catch-up for receipts that are already read by either route.
UPDATE public.notification_receipts r SET read_at=clock_timestamp()
  FROM public.notification_events e
  WHERE e.id=r.event_id AND r.read_at IS NULL AND (
    (e.source_type='notifications' AND EXISTS(SELECT 1 FROM public.notifications n
      WHERE n.id=e.source_id AND n.is_read))
    OR (e.event_type='message_received' AND EXISTS(SELECT 1 FROM public.care_conversation_messages m
      JOIN public.care_conversation_reads cr ON cr.conversation_id=m.conversation_id AND cr.actor_id=r.recipient_id
      WHERE m.id=e.source_id AND (m.created_at,m.id)<=(cr.last_message_at,cr.last_message_id))));

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
         AND e.event_type IN ('barrier_reported','safety_flag','appointment_response')) THEN
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

-- New private functions follow 051: server role may execute, browser roles may not;
-- trigger functions are executable by no one directly.
DO $$ DECLARE f record; BEGIN
 FOR f IN SELECT p.oid::regprocedure signature,p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname='private' AND p.proname IN ('notification_actionable','notification_row','notification_rows','notification_open_work',
     'notification_scope','notification_prepare','notification_sync_conversation_read','notification_sync_legacy_read') LOOP
   EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,anon,authenticated,service_role',f.signature);
   IF f.proname NOT LIKE 'notification_sync_%' THEN
     EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role',f.signature);
   END IF;
 END LOOP;
END $$;
