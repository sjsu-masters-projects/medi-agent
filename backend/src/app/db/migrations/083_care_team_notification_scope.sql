-- PLAN-002 / CLN-003 slice G: the notification centre follows record ownership.
--
-- 051-079 fan a "shared" notification out to every active care-team link of the patient and
-- authorize a clinician by assignment alone. Since 080-082 a document, a plan, and reviewed
-- ADR work belong to ONE care team, so a second team's clinician would be told about, and be
-- able to open an item for, a record that is not theirs. This migration scopes who receives
-- and who may open each clinician item. Nothing is rewritten and no history is removed.
--
-- Recipients by source (clinician side):
--   documents (document_review, document_failed)  the owning team; every active team while
--       routing_state = 'unrouted' (one claims it, 081); nobody when a routed document lost
--       its owner link.
--   care_plan_versions (care_plan_draft)           the team that owns the plan; nobody for an
--       unowned or unassigned plan (those are review items for a clinic's admins, 080).
--   adr_assessments (adr_review), adr_information_requests (adr_information_answered)
--       every team while the assessment is pending (reviewed_by IS NULL), then the
--       reviewing team, as the 081 policy reads it.
--   critical_result                                every active team: it is safety
--       information. A team that does not hold the document sees a neutral item whose link
--       stops at the patient (metadata.source_accessible = false), never the document.
--   safety_flag, barrier_reported, message_received, appointment_response   unchanged:
--       patient-level safety/adherence news, or addressed to one clinician or one link.
--
-- Opening, reading, reading through and acknowledging all pass notification_authorized or
-- notification_row, so the same rule re-checks ownership at read time; an old receipt of a
-- team that no longer owns the record is hidden, not deleted (history stays append only).
--
-- Every function below starts from its latest definition (notification_capture 051,
-- notification_prepare 056, notification_authorized 066, notification_row 069) and changes
-- only what is named above. Same signatures, so the existing grants still apply.

-- ── 1. Ownership helpers ──────────────────────────────────────────────────────────────────

-- The clinician's links to the patient that the notification centre honours: active link,
-- active clinic, active membership at that clinic (the same conditions as 066).
CREATE OR REPLACE FUNCTION private.notification_links(p_actor uuid, p_patient uuid)
RETURNS uuid[] LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
  SELECT coalesce(array_agg(ct.id ORDER BY ct.id), ARRAY[]::uuid[])
    FROM public.care_teams ct
    JOIN public.clinics cl ON cl.id = ct.clinic_id
    JOIN public.clinic_memberships m ON m.clinician_id = ct.clinician_id AND m.clinic_id = ct.clinic_id
   WHERE ct.patient_id = p_patient AND ct.clinician_id = p_actor
     AND ct.status = 'active' AND cl.status = 'active' AND m.status = 'active';
$$;

-- The team that owns a notification source, for labelling; NULL when it has none.
CREATE OR REPLACE FUNCTION private.notification_owner_team(p_type text, p_id uuid)
RETURNS uuid LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
  SELECT CASE p_type
    WHEN 'documents' THEN
      (SELECT d.care_team_id FROM public.documents d WHERE d.id = p_id)
    WHEN 'care_plan_versions' THEN
      (SELECT cp.care_team_id FROM public.care_plan_versions v
         JOIN public.care_plans cp ON cp.id = v.care_plan_id WHERE v.id = p_id)
    WHEN 'adr_assessments' THEN
      (SELECT a.reviewed_by_care_team_id FROM public.adr_assessments a WHERE a.id = p_id)
    WHEN 'adr_information_requests' THEN
      (SELECT a.reviewed_by_care_team_id FROM public.adr_information_requests r
         JOIN public.adr_assessments a ON a.id = r.adr_assessment_id WHERE r.id = p_id)
  END;
$$;

-- May this clinician see a notification about this source? p_kind = 'critical_result' is the
-- shared safety alert and always passes; any other value applies the ownership rule, so a
-- caller can ask the strict question with p_kind = 'strict'. Sources that are not owned
-- records (messages, appointments, adherence, safety flags) are decided elsewhere.
CREATE OR REPLACE FUNCTION private.notification_owner_sees(
  p_type text, p_id uuid, p_kind text, p_actor uuid, p_patient uuid
) RETURNS boolean LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_links uuid[];
BEGIN
  IF p_kind = 'critical_result'
     OR p_type NOT IN ('documents', 'care_plan_versions', 'adr_assessments', 'adr_information_requests')
  THEN RETURN true; END IF;
  v_links := private.notification_links(p_actor, p_patient);
  IF cardinality(v_links) = 0 THEN RETURN false; END IF;
  IF p_type = 'documents' THEN
    RETURN EXISTS (SELECT 1 FROM public.documents d WHERE d.id = p_id AND d.patient_id = p_patient
      AND (d.routing_state = 'unrouted' OR d.care_team_id = ANY (v_links)));
  ELSIF p_type = 'care_plan_versions' THEN
    RETURN EXISTS (SELECT 1 FROM public.care_plan_versions v
      JOIN public.care_plans cp ON cp.id = v.care_plan_id
      WHERE v.id = p_id AND v.patient_id = p_patient AND cp.care_team_id = ANY (v_links));
  ELSIF p_type = 'adr_assessments' THEN
    RETURN EXISTS (SELECT 1 FROM public.adr_assessments a WHERE a.id = p_id AND a.patient_id = p_patient
      AND (a.reviewed_by IS NULL OR a.reviewed_by_care_team_id = ANY (v_links)
        OR (a.reviewed_by_care_team_id IS NULL AND a.reviewed_by = p_actor)));
  END IF;
  RETURN EXISTS (SELECT 1 FROM public.adr_information_requests r
    JOIN public.adr_assessments a ON a.id = r.adr_assessment_id
    WHERE r.id = p_id AND r.patient_id = p_patient AND a.patient_id = p_patient
      AND (a.reviewed_by IS NULL OR a.reviewed_by_care_team_id = ANY (v_links)
        OR (a.reviewed_by_care_team_id IS NULL AND a.reviewed_by = p_actor)));
END;
$$;

-- ── 2. Opening an item re-checks ownership, not only assignment ───────────────────────────
-- Same as 066 with one added condition on the clinician branch.
CREATE OR REPLACE FUNCTION private.notification_authorized(e public.notification_events,p_actor uuid,p_role text)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE s jsonb; t public.care_conversations;
BEGIN
 s:=private.notification_source(e.source_type,e.source_id);
 IF s IS NULL THEN RETURN false; END IF;
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

-- ── 3. Capture delivers a shared item to the teams that may see it ─────────────────────────
-- Same as 051; the shared fan-out is limited to clinicians the ownership rule admits.
CREATE OR REPLACE FUNCTION private.notification_capture(p_type text,p_id uuid,p_patient uuid,p_kind text,
  p_category text,p_audience text,p_recipient uuid,p_metadata jsonb,p_key text,p_created timestamptz)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE v_id uuid;
BEGIN
 INSERT INTO public.notification_events(event_key,event_type,category,source_type,source_id,patient_id,
   audience,recipient_id,metadata,created_at)
 VALUES(p_key,p_kind,p_category,p_type,p_id,p_patient,p_audience,p_recipient,p_metadata,p_created)
 ON CONFLICT(event_key) DO NOTHING RETURNING id INTO v_id;
 IF v_id IS NULL THEN SELECT id INTO v_id FROM public.notification_events WHERE event_key=p_key; END IF;
 IF p_audience='patient' THEN
   INSERT INTO public.notification_pending_deliveries(event_id,recipient_id,recipient_role)
     VALUES(v_id,p_patient,'patient') ON CONFLICT DO NOTHING;
 ELSIF p_audience='private' THEN
   INSERT INTO public.notification_pending_deliveries(event_id,recipient_id,recipient_role)
     VALUES(v_id,p_recipient,CASE WHEN p_recipient=p_patient THEN 'patient' ELSE 'clinician' END) ON CONFLICT DO NOTHING;
 ELSIF p_audience='clinician' THEN
   INSERT INTO public.notification_pending_deliveries(event_id,recipient_id,recipient_role)
     VALUES(v_id,p_recipient,'clinician') ON CONFLICT DO NOTHING;
 ELSE
   INSERT INTO public.notification_pending_deliveries(event_id,recipient_id,recipient_role)
     SELECT DISTINCT v_id,ct.clinician_id,'clinician' FROM public.care_teams ct
       JOIN public.clinicians c ON c.id=ct.clinician_id JOIN public.clinics cl ON cl.id=c.clinic_id
     WHERE ct.patient_id=p_patient AND ct.status='active' AND cl.status='active'
       AND private.notification_owner_sees(p_type,p_id,p_kind,ct.clinician_id,p_patient)
     ON CONFLICT DO NOTHING;
 END IF;
 RETURN v_id;
END;
$$;

-- ── 4. A newly assigned or newly owning clinician is caught up on their own work only ──────
-- Same as 056; the catch-up skips work another team owns, so no undeliverable pending
-- delivery is left behind for a clinician who can never see the item.
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

-- ── 5. The item names its owner's clinic and a critical result never links a hidden file ───
-- Same as 069. A reminder or appointment item still names the appointment's clinic; an item
-- from an owned record names the owner's link before any other link of the same person; and
-- a critical-result item a team cannot open carries metadata.source_accessible = false.
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
     CASE WHEN a.source_type='appointments' THEN private.notification_uuid(a.s->>'clinic_id')
       WHEN a.event_type='appointment_reminder' THEN (SELECT ap.clinic_id FROM public.appointments ap
         WHERE ap.id=private.notification_uuid(a.metadata->>'appointment_id') AND ap.patient_id=a.patient_id)
     END ref_clinic,
     private.notification_owner_team(a.source_type,a.source_id) owner_team,
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
     'source_id',a.source_id,'patient_id',a.patient_id,
     'metadata',CASE WHEN a.source_hidden THEN a.metadata||'{"source_accessible":false}'::jsonb ELSE a.metadata END,
     'created_at',a.created_at,
     'is_read',a.seen,'actionable',a.needs,'can_acknowledge',
       p_role='clinician' AND a.event_type IN ('barrier_reported','safety_flag','appointment_response','critical_result') AND a.needs,
     'patient_name',concat_ws(' ',p.first_name,p.last_name),
     'clinic_id',coalesce(a.ref_clinic,ct.clinic_id),
     'clinic_name',CASE WHEN a.ref_clinic IS NOT NULL THEN rc.display_name ELSE coalesce(cl.display_name,ct.clinic_name) END,
     'actor_name',coalesce(a.metadata->>'actor_name',concat_ws(' ',c.first_name,c.last_name)))
 FROM states a JOIN public.patients p ON p.id=a.patient_id
 LEFT JOIN LATERAL (SELECT t.* FROM public.care_teams t WHERE t.patient_id=a.patient_id AND t.status='active'
   AND (CASE WHEN p_role='clinician' THEN t.clinician_id=p_actor
     WHEN a.metadata->>'clinician_id' IS NOT NULL THEN t.clinician_id=(a.metadata->>'clinician_id')::uuid ELSE true END)
   ORDER BY coalesce(t.id=a.owner_team,false) DESC,t.id LIMIT 1) ct ON true
 LEFT JOIN public.clinicians c ON c.id=ct.clinician_id LEFT JOIN public.clinics cl ON cl.id=ct.clinic_id
 LEFT JOIN public.clinics rc ON rc.id=a.ref_clinic;
$$;

-- ── 6. Undelivered copies for clinicians who can never see the item are dropped ────────────
-- Only never-delivered pending rows: they cannot become receipts (notification_prepare
-- re-checks), and a team that later owns the record is caught up again by the catch-up.
-- Receipts and events, the history, are untouched.
DELETE FROM public.notification_pending_deliveries d
 USING public.notification_events e
 WHERE e.id = d.event_id AND d.delivered_at IS NULL AND d.recipient_role = 'clinician'
   AND e.audience = 'shared'
   AND e.source_type IN ('documents', 'care_plan_versions', 'adr_assessments', 'adr_information_requests')
   AND NOT private.notification_owner_sees(e.source_type, e.source_id, e.event_type, d.recipient_id, e.patient_id);

-- ── 7. Grants: service role only, like every other notification function ─────────────────
REVOKE ALL ON FUNCTION
  private.notification_links(uuid, uuid),
  private.notification_owner_team(text, uuid),
  private.notification_owner_sees(text, uuid, text, uuid, uuid),
  private.notification_authorized(public.notification_events, uuid, text),
  private.notification_capture(text, uuid, uuid, text, text, text, uuid, jsonb, text, timestamptz),
  private.notification_prepare(uuid, text),
  private.notification_row(public.notification_receipts, uuid, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION
  private.notification_links(uuid, uuid),
  private.notification_owner_team(text, uuid),
  private.notification_owner_sees(text, uuid, text, uuid, uuid),
  private.notification_authorized(public.notification_events, uuid, text),
  private.notification_capture(text, uuid, uuid, text, text, text, uuid, jsonb, text, timestamptz),
  private.notification_prepare(uuid, text),
  private.notification_row(public.notification_receipts, uuid, text)
  TO service_role;

-- ── 8. Verification: fail the migration if a grant or definition is wrong ──────────────────
DO $verify$
DECLARE v_function text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_class WHERE oid IN
    ('public.notification_events'::regclass, 'public.notification_receipts'::regclass,
     'public.notification_pending_deliveries'::regclass, 'public.notification_read_audit'::regclass)
    AND NOT relrowsecurity) THEN
    RAISE EXCEPTION '083: the notification ledger must have RLS enabled';
  END IF;
  FOREACH v_function IN ARRAY ARRAY[
    'private.notification_links(uuid,uuid)',
    'private.notification_owner_team(text,uuid)',
    'private.notification_owner_sees(text,uuid,text,uuid,uuid)',
    'private.notification_authorized(public.notification_events,uuid,text)',
    'private.notification_capture(text,uuid,uuid,text,text,text,uuid,jsonb,text,timestamptz)',
    'private.notification_prepare(uuid,text)',
    'private.notification_row(public.notification_receipts,uuid,text)'] LOOP
    IF has_function_privilege('anon', v_function, 'EXECUTE')
       OR has_function_privilege('authenticated', v_function, 'EXECUTE')
       OR NOT has_function_privilege('service_role', v_function, 'EXECUTE') THEN
      RAISE EXCEPTION '083: wrong execute grants on %', v_function;
    END IF;
  END LOOP;
  IF (SELECT prosrc FROM pg_proc WHERE oid = 'private.notification_authorized(public.notification_events,uuid,text)'::regprocedure)
     NOT LIKE '%notification_owner_sees%'
     OR (SELECT prosrc FROM pg_proc WHERE oid = 'private.notification_capture(text,uuid,uuid,text,text,text,uuid,jsonb,text,timestamptz)'::regprocedure)
     NOT LIKE '%notification_owner_sees%'
     OR (SELECT prosrc FROM pg_proc WHERE oid = 'private.notification_prepare(uuid,text)'::regprocedure)
     NOT LIKE '%notification_owner_sees%' THEN
    RAISE EXCEPTION '083: a notification function lost its ownership check';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_proc
              WHERE proname IN ('notification_row', 'notification_centre_operation')
                AND prosrc ~ 'cl\.id\s*=\s*c\.clinic_id') THEN
    RAISE EXCEPTION '083: notification clinic labels must come from the care-team link''s clinic';
  END IF;
END
$verify$;
