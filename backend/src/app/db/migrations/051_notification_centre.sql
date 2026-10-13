-- NOT-001: capture is part of the source transaction; delivery is retryable.
-- This ledger uses complete filenames/checksums, not CLI timestamp filenames.
CREATE TABLE public.notification_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_key text NOT NULL UNIQUE,
  event_type text NOT NULL CHECK (event_type IN (
    'message_received','appointment_offered','appointment_changed','appointment_response',
    'appointment_reminder','care_plan_published','care_plan_draft','document_review',
    'document_processed','document_failed','document_reviewed','barrier_reported',
    'adr_review','adr_information_requested','safety_flag','med_reminder','obligation_reminder','legacy_update')),
  category text NOT NULL CHECK (category IN ('messages','documents','care_plans',
    'appointments','reminders','follow_up','safety')),
  source_type text NOT NULL CHECK (source_type IN ('care_conversation_messages',
    'appointments','notifications','care_plan_versions','documents','adherence_logs',
    'adr_assessments','clinician_messages')),
  source_id uuid NOT NULL,
  patient_id uuid NOT NULL REFERENCES public.patients(id) ON DELETE CASCADE,
  audience text NOT NULL CHECK (audience IN ('patient','clinician','shared','private')),
  recipient_id uuid,
  metadata jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata)='object'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX notification_events_source ON public.notification_events(source_type,source_id,created_at DESC,id DESC);
CREATE INDEX notification_events_patient ON public.notification_events(patient_id,created_at DESC,id DESC);

CREATE TABLE public.notification_pending_deliveries (
  event_id uuid NOT NULL REFERENCES public.notification_events(id) ON DELETE CASCADE,
  recipient_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  recipient_role text NOT NULL CHECK (recipient_role IN ('patient','clinician')),
  delivered_at timestamptz,
  PRIMARY KEY(event_id,recipient_id)
);
CREATE INDEX notification_pending_actor ON public.notification_pending_deliveries(recipient_id,event_id)
  WHERE delivered_at IS NULL;
CREATE TABLE public.notification_receipts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id uuid NOT NULL REFERENCES public.notification_events(id) ON DELETE CASCADE,
  recipient_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  recipient_role text NOT NULL CHECK (recipient_role IN ('patient','clinician')),
  created_at timestamptz NOT NULL,
  read_at timestamptz,
  acknowledged_at timestamptz,
  UNIQUE(event_id,recipient_id)
);
CREATE INDEX notification_receipts_page ON public.notification_receipts(recipient_id,created_at DESC,id DESC);
CREATE INDEX notification_receipts_unread ON public.notification_receipts(recipient_id,created_at DESC,id DESC)
  WHERE read_at IS NULL;
CREATE INDEX notification_receipts_event ON public.notification_receipts(event_id);
CREATE TABLE public.notification_read_audit (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  receipt_id uuid NOT NULL REFERENCES public.notification_receipts(id) ON DELETE CASCADE,
  actor_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  action text NOT NULL CHECK (action IN ('read','acknowledge')),
  note text CHECK (char_length(note)<=1000),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE(receipt_id,action)
);
CREATE INDEX notification_read_audit_actor ON public.notification_read_audit(actor_id,created_at);
ALTER TABLE public.notification_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_pending_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_read_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.notification_events,public.notification_pending_deliveries,
  public.notification_receipts,public.notification_read_audit FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT ON public.notification_events,public.notification_read_audit TO service_role;
GRANT SELECT,INSERT,UPDATE ON public.notification_pending_deliveries,public.notification_receipts TO service_role;
-- Existing source grants vary between historical ledgers. Only server reads are added.
GRANT SELECT ON public.adherence_logs,public.clinician_messages,public.obligations,
  public.reminder_schedules,public.adr_assessments TO service_role;

CREATE FUNCTION private.notification_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path='' AS $$
BEGIN RAISE EXCEPTION 'Notification history is append only' USING ERRCODE='42501'; END;
$$;
-- History is never edited. Rows are removed only with the account or patient they belong
-- to (cascade), which keeps account deletion and the synthetic demo reset working; no
-- role is granted DELETE, so nothing else can remove them.
CREATE TRIGGER notification_events_immutable BEFORE UPDATE ON public.notification_events
  FOR EACH ROW EXECUTE FUNCTION private.notification_immutable();
CREATE TRIGGER notification_audit_immutable BEFORE UPDATE ON public.notification_read_audit
  FOR EACH ROW EXECUTE FUNCTION private.notification_immutable();

-- One malformed source value must not break a person's whole notification centre.
CREATE FUNCTION private.notification_ts(p_value text) RETURNS timestamptz
LANGUAGE plpgsql STABLE SET search_path='' AS $$
BEGIN RETURN nullif(p_value,'')::timestamptz;
EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR datetime_field_overflow
  OR invalid_parameter_value THEN RETURN NULL;
END;
$$;
CREATE FUNCTION private.notification_uuid(p_value text) RETURNS uuid
LANGUAGE plpgsql IMMUTABLE SET search_path='' AS $$
BEGIN RETURN nullif(p_value,'')::uuid;
EXCEPTION WHEN invalid_text_representation THEN RETURN NULL;
END;
$$;
CREATE FUNCTION private.notification_zone(p_zone text) RETURNS text
LANGUAGE sql STABLE SET search_path='' AS $$
  SELECT CASE WHEN EXISTS(SELECT 1 FROM pg_catalog.pg_timezone_names WHERE name=p_zone)
    THEN p_zone ELSE 'UTC' END
$$;

-- Internal only: never return arbitrary source JSON to the API (ADR reasoning,
-- storage URLs, and unrelated clinical content must not enter notification data).
CREATE FUNCTION private.notification_source(p_type text,p_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v jsonb;
BEGIN
  IF p_type NOT IN ('care_conversation_messages','appointments','notifications',
    'care_plan_versions','documents','adherence_logs','adr_assessments','clinician_messages') THEN RETURN NULL; END IF;
  EXECUTE format('SELECT to_jsonb(s) FROM public.%I s WHERE id=$1',p_type) INTO v USING p_id;
  RETURN v;
END;
$$;

CREATE FUNCTION private.notification_draft_ready(p_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT EXISTS(SELECT 1 FROM public.care_plan_versions v WHERE v.id=p_id AND v.status='draft'
   AND v.generated_at IS NOT NULL
   AND EXISTS(SELECT 1 FROM public.care_plan_items i WHERE i.plan_version_id=v.id AND NOT i.is_removed)
   AND NOT EXISTS(SELECT 1 FROM public.care_plan_generation_requests g WHERE g.patient_id=v.patient_id
     AND g.source_watermark>=v.source_watermark AND
       (g.status<>'completed' OR g.plan_version_id IS DISTINCT FROM v.id)));
$$;

CREATE FUNCTION private.notification_authorized(e public.notification_events,p_actor uuid,p_role text)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE s jsonb; t public.care_conversations;
BEGIN
 s:=private.notification_source(e.source_type,e.source_id);
 IF s IS NULL THEN RETURN false; END IF;
 IF e.source_type='care_conversation_messages' THEN
   SELECT * INTO t FROM public.care_conversations WHERE id=(s->>'conversation_id')::uuid;
   RETURN e.recipient_id=p_actor AND EXISTS(SELECT 1 FROM public.care_teams ct
     JOIN public.clinicians c ON c.id=ct.clinician_id JOIN public.clinics cl ON cl.id=c.clinic_id
     WHERE ct.id=t.care_team_id AND ct.patient_id=t.patient_id AND ct.clinician_id=t.clinician_id
       AND c.clinic_id=t.clinic_id AND cl.status='active' AND ct.status='active'
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
   AND EXISTS(SELECT 1 FROM public.care_teams ct JOIN public.clinicians c ON c.id=ct.clinician_id
     JOIN public.clinics cl ON cl.id=c.clinic_id WHERE ct.patient_id=e.patient_id
       AND ct.clinician_id=p_actor AND ct.status='active' AND cl.status='active');
END;
$$;

CREATE FUNCTION private.notification_reminder_active(s jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE m jsonb:=s->'metadata'; v_target uuid; v_when timestamptz; v_schedule public.reminder_schedules;
  v_frequency text; v_timezone text; v_day text;
BEGIN
 IF nullif(m->>'target_id','') IS NULL OR nullif(m->>'scheduled_at','') IS NULL THEN RETURN false; END IF;
 v_target:=(m->>'target_id')::uuid; v_when:=(m->>'scheduled_at')::timestamptz;
 SELECT * INTO v_schedule FROM public.reminder_schedules WHERE patient_id=(s->>'patient_id')::uuid
   AND target_id=v_target AND target_type::text=m->>'target_type' AND is_enabled;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT private.notification_zone(timezone) INTO v_timezone FROM public.patients
   WHERE id=(s->>'patient_id')::uuid;
 IF (v_when AT TIME ZONE v_timezone)::date<>(clock_timestamp() AT TIME ZONE v_timezone)::date THEN RETURN false; END IF;
 v_day:=lower(trim(to_char(v_when AT TIME ZONE v_schedule.timezone,'Day')));
 IF NOT v_schedule.days_of_week ? v_day OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements_text(v_schedule.times_of_day) x
   WHERE x::time=(v_when AT TIME ZONE v_schedule.timezone)::time) THEN RETURN false; END IF;
 IF m->>'target_type'='medication' THEN
   SELECT frequency INTO v_frequency FROM public.medications WHERE id=v_target AND patient_id=(s->>'patient_id')::uuid
     AND is_active AND (start_date IS NULL OR start_date<=(v_when AT TIME ZONE v_timezone)::date)
     AND (end_date IS NULL OR end_date>=(v_when AT TIME ZONE v_timezone)::date);
 ELSE
   SELECT frequency INTO v_frequency FROM public.obligations WHERE id=v_target AND patient_id=(s->>'patient_id')::uuid AND is_active;
 END IF;
 IF v_frequency IS NULL OR lower(v_frequency) ~ '(as needed|as directed|prn|unknown|activity)' THEN RETURN false; END IF;
 RETURN NOT EXISTS(SELECT 1 FROM public.adherence_logs a WHERE a.patient_id=(s->>'patient_id')::uuid
   AND a.target_id=v_target AND a.target_type::text=m->>'target_type' AND a.status IN ('taken','completed','skipped')
   AND (a.scheduled_time=v_when OR (a.scheduled_time IS NULL AND
     (a.logged_at AT TIME ZONE v_timezone)::date=(v_when AT TIME ZONE v_timezone)::date)));
EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR datetime_field_overflow
  OR invalid_parameter_value THEN RETURN false;
END;
$$;

CREATE FUNCTION private.notification_actionable(e public.notification_events,p_role text) RETURNS boolean
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

CREATE FUNCTION private.notification_capture(p_type text,p_id uuid,p_patient uuid,p_kind text,
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
     SELECT v_id,ct.clinician_id,'clinician' FROM public.care_teams ct
       JOIN public.clinicians c ON c.id=ct.clinician_id JOIN public.clinics cl ON cl.id=c.clinic_id
     WHERE ct.patient_id=p_patient AND ct.status='active' AND cl.status='active' ON CONFLICT DO NOTHING;
 END IF;
 RETURN v_id;
END;
$$;

CREATE FUNCTION private.capture_notification_source() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE s jsonb:=to_jsonb(NEW); o jsonb:='{}'; v_patient uuid; v_id uuid:=NEW.id;
  v_kind text; v_category text; v_audience text:='shared'; v_recipient uuid;
  v_meta jsonb:='{}'; v_key text; v_created timestamptz:=clock_timestamp(); t public.care_conversations;
BEGIN
 IF TG_OP='UPDATE' THEN o:=to_jsonb(OLD); END IF;
 IF TG_TABLE_NAME='care_plan_items' THEN
   v_id:=(s->>'plan_version_id')::uuid;
   SELECT to_jsonb(v) INTO s FROM public.care_plan_versions v WHERE id=v_id;
 ELSIF TG_TABLE_NAME='care_plan_generation_requests' THEN
   v_id:=(s->>'plan_version_id')::uuid;
   IF s->>'status' IS DISTINCT FROM 'completed' OR v_id IS NULL THEN RETURN NEW; END IF;
   SELECT to_jsonb(v) INTO s FROM public.care_plan_versions v WHERE id=v_id;
 END IF;
 v_patient:=(s->>'patient_id')::uuid;
 CASE TG_TABLE_NAME
 WHEN 'care_conversation_messages' THEN
   IF TG_OP<>'INSERT' THEN RETURN NEW; END IF;
   SELECT * INTO t FROM public.care_conversations WHERE id=NEW.conversation_id;
   v_patient:=t.patient_id; v_recipient:=CASE WHEN NEW.sender_role='patient' THEN t.clinician_id ELSE t.patient_id END;
   v_kind:='message_received'; v_category:='messages'; v_audience:='private';
   v_meta:=jsonb_build_object('conversation_id',t.id,'clinician_id',t.clinician_id,'actor_name',NEW.sender_name);
   v_created:=NEW.created_at;
 WHEN 'appointments' THEN
   IF TG_OP='UPDATE' AND (s->>'status',s->>'scheduled_at',s->>'patient_note',s->>'location')
     IS NOT DISTINCT FROM (o->>'status',o->>'scheduled_at',o->>'patient_note',o->>'location') THEN RETURN NEW; END IF;
   -- Classified by transition, because the same status means different things: a
   -- patient's cancel or "another time" goes to the clinician, a clinician's offer or
   -- time change goes to the patient, and siblings withdrawn when one slot of an offer
   -- is accepted are bookkeeping, not news. Patients can only accept, decline, ask for
   -- another time or cancel (039, 043); everything else here is the clinician's.
   v_kind:=CASE
     WHEN s->>'status'='proposed' AND (TG_OP='INSERT' OR o->>'status' IS DISTINCT FROM 'proposed')
       THEN 'appointment_offered'
     WHEN TG_OP='UPDATE' AND o->>'status'='proposed'
       AND s->>'status' IN ('confirmed','declined','alternative_requested','cancelled')
       THEN 'appointment_response'
     WHEN TG_OP='UPDATE' AND o->>'status' IN ('confirmed','scheduled') AND s->>'status'='cancelled'
       THEN 'appointment_response'
     WHEN TG_OP='UPDATE' AND s->>'status' IS NOT DISTINCT FROM o->>'status'
       AND (s->>'patient_note') IS DISTINCT FROM (o->>'patient_note')
       AND (s->>'scheduled_at',s->>'location') IS NOT DISTINCT FROM (o->>'scheduled_at',o->>'location')
       THEN 'appointment_response'
     WHEN s->>'status' IN ('withdrawn','completed','no_show','proposed') THEN NULL
     ELSE 'appointment_changed' END;
   IF v_kind IS NULL THEN RETURN NEW; END IF;
   v_category:='appointments';
   v_meta:=jsonb_build_object('appointment_id',v_id,'status',s->>'status','scheduled_at',s->>'scheduled_at');
   SELECT clinician_id INTO v_recipient FROM public.care_teams WHERE id=private.notification_uuid(s->>'care_team_id');
   v_meta:=v_meta||jsonb_build_object('clinician_id',v_recipient);
   IF v_kind='appointment_response' THEN v_audience:='clinician'; ELSE v_audience:='patient'; END IF;
   IF v_kind='appointment_offered' THEN
     -- One notification per offer, however many time slots it proposes.
     v_key:='appointments:offer:'||coalesce(s->>'proposal_group_id',v_id::text);
   END IF;
 WHEN 'care_plan_versions','care_plan_items','care_plan_generation_requests' THEN
   IF s->>'status'='draft' AND private.notification_draft_ready(v_id) THEN
     v_kind:='care_plan_draft';
   ELSIF TG_TABLE_NAME='care_plan_versions' AND s->>'status'='approved' AND o->>'status' IS DISTINCT FROM 'approved' THEN
     v_kind:='care_plan_published'; v_audience:='patient';
   ELSE RETURN NEW; END IF;
   v_category:='care_plans'; v_meta:=jsonb_build_object('version_number',s->'version_number');
 WHEN 'documents' THEN
   IF TG_OP='UPDATE' AND (s->>'review_status',s->>'parse_status',s->>'summary_status')
     IS NOT DISTINCT FROM (o->>'review_status',o->>'parse_status',o->>'summary_status') THEN RETURN NEW; END IF;
   v_category:='documents';
   IF s->>'uploaded_by_role'='patient' AND s->>'review_status'='pending'
     AND (TG_OP='INSERT' OR o->>'review_status' IS DISTINCT FROM 'pending') THEN
     PERFORM private.notification_capture('documents',v_id,v_patient,'document_review',v_category,'shared',NULL,
       jsonb_build_object('review_status','pending'),'documents:'||v_id||':review:'||txid_current(),v_created);
   END IF;
   IF s->>'review_status' IN ('approved','rejected') AND o->>'review_status' IS DISTINCT FROM s->>'review_status' THEN
     v_kind:='document_reviewed'; v_audience:='patient';
   ELSIF s->>'parse_status'='completed' AND o->>'parse_status' IS DISTINCT FROM 'completed' THEN
     v_kind:='document_processed'; v_audience:='patient';
   ELSIF s->>'parse_status' IN ('failed','needs_ocr','needs_evidence_review') AND o->>'parse_status' IS DISTINCT FROM s->>'parse_status' THEN
     v_kind:='document_failed';
     PERFORM private.notification_capture('documents',v_id,v_patient,v_kind,v_category,'patient',NULL,
       jsonb_build_object('parse_status',s->>'parse_status'),'documents:'||v_id||':failed:'||txid_current()||':patient',v_created);
   ELSE RETURN NEW; END IF;
   v_meta:=jsonb_build_object('review_status',s->>'review_status','parse_status',s->>'parse_status');
 WHEN 'adherence_logs' THEN
   IF s->>'barrier_code' IS NULL OR s->>'status' IS DISTINCT FROM 'skipped'
     OR (TG_OP='UPDATE' AND (s->>'barrier_code',s->>'status') IS NOT DISTINCT FROM (o->>'barrier_code',o->>'status')) THEN RETURN NEW; END IF;
   v_kind:='barrier_reported'; v_category:='follow_up';
   v_meta:=jsonb_build_object('target_id',s->>'target_id','target_type',s->>'target_type','barrier_code',s->>'barrier_code');
 WHEN 'adr_assessments' THEN
   IF s->>'status' IS DISTINCT FROM 'draft' THEN RETURN NEW; END IF;
   IF s->>'last_review_action'='request_information' AND (TG_OP='INSERT' OR
     (s->>'last_review_action',s->'requested_information',s->>'updated_at') IS DISTINCT FROM
       (o->>'last_review_action',o->'requested_information',o->>'updated_at')) THEN
     v_kind:='adr_information_requested'; v_audience:='patient';
     v_meta:=jsonb_build_object('requested_information',s->'requested_information','clinician_id',s->>'reviewed_by');
   ELSIF TG_OP='INSERT' OR o->>'status' IS DISTINCT FROM 'draft' THEN v_kind:='adr_review';
   ELSE RETURN NEW; END IF;
   v_category:='safety';
 WHEN 'clinician_messages' THEN
   IF TG_OP<>'INSERT' OR s->>'subject' IS DISTINCT FROM 'Urgent patient chat escalation'
     OR left(s->>'body',25) IS DISTINCT FROM 'Chat escalation flagged (' THEN RETURN NEW; END IF;
   v_kind:='safety_flag'; v_category:='safety';
   -- Fanout inserts share transaction timestamp/body; keep one event for the patient.
   v_key:='safety:'||v_patient||':'||md5((s->>'body')||':'||(s->>'created_at'));
 WHEN 'notifications' THEN
   IF TG_OP='UPDATE' THEN RETURN NEW; END IF;
   v_kind:=CASE WHEN s->>'notification_type'='appointment' THEN 'appointment_reminder'
     WHEN s->>'notification_type' IN ('med_reminder','obligation_reminder') THEN s->>'notification_type' ELSE 'legacy_update' END;
   v_category:=CASE WHEN v_kind='appointment_reminder' THEN 'appointments'
     WHEN v_kind='legacy_update' THEN 'follow_up' ELSE 'reminders' END;
   v_audience:='patient'; v_created:=NEW.created_at;
   v_meta:=jsonb_build_object('target_id',s->'metadata'->>'target_id','target_type',s->'metadata'->>'target_type',
     'scheduled_at',s->'metadata'->>'scheduled_at','appointment_id',s->'metadata'->>'appointment_id',
     'legacy_notification_type',s->>'notification_type');
   v_key:='notification:'||v_id;
 END CASE;
 IF v_kind IS NOT NULL THEN
   PERFORM private.notification_capture(CASE WHEN TG_TABLE_NAME IN ('care_plan_items','care_plan_generation_requests')
       THEN 'care_plan_versions' ELSE TG_TABLE_NAME END,v_id,v_patient,v_kind,v_category,v_audience,v_recipient,v_meta,
     coalesce(v_key,CASE WHEN v_kind='care_plan_draft' THEN 'draft:'||v_id ELSE
       TG_TABLE_NAME||':'||v_id||':'||v_kind||':'||txid_current()||':'||md5(v_meta::text) END),v_created);
 END IF;
 RETURN NEW;
END;
$$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['care_conversation_messages','appointments','care_plan_versions','care_plan_items',
   'care_plan_generation_requests','documents','adherence_logs','adr_assessments','clinician_messages','notifications'] LOOP
   EXECUTE format('CREATE TRIGGER notification_capture AFTER INSERT OR UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION private.capture_notification_source()',t);
 END LOOP;
END $$;

-- Import existing reminders exactly once, preserving their original ID/time/read
-- state. No legacy safety/message history is captured and no reminders generated.
SELECT private.notification_capture('notifications',n.id,n.patient_id,
  CASE WHEN n.notification_type='appointment' THEN 'appointment_reminder'
    WHEN n.notification_type IN ('med_reminder','obligation_reminder') THEN n.notification_type::text ELSE 'legacy_update' END,
  CASE WHEN n.notification_type='appointment' THEN 'appointments'
    WHEN n.notification_type IN ('med_reminder','obligation_reminder') THEN 'reminders' ELSE 'follow_up' END,'patient',NULL,
  jsonb_build_object('target_id',n.metadata->>'target_id','target_type',n.metadata->>'target_type',
    'scheduled_at',n.metadata->>'scheduled_at','appointment_id',n.metadata->>'appointment_id',
    'legacy_notification_type',n.notification_type),
  'notification:'||n.id,n.created_at)
FROM public.notifications n;

-- Newly assigned reviewers receive only current shared work, never private
-- thread history or old resolved tasks. Existing event identities are reused.
CREATE FUNCTION private.notification_prepare(p_actor uuid,p_role text) RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE x record; v_ev public.notification_events; v_id uuid;
BEGIN
 IF p_role='clinician' THEN
   FOR x IN
     SELECT 'documents'::text typ,d.id,d.patient_id,'document_review'::text kind,'documents'::text category
       FROM public.documents d WHERE d.uploaded_by_role='patient' AND d.review_status='pending'
         AND EXISTS(SELECT 1 FROM public.care_teams t WHERE t.patient_id=d.patient_id AND t.clinician_id=p_actor AND t.status='active')
     UNION ALL SELECT 'care_plan_versions',v.id,v.patient_id,'care_plan_draft','care_plans'
       FROM public.care_plan_versions v WHERE EXISTS(SELECT 1 FROM public.care_teams t
         WHERE t.patient_id=v.patient_id AND t.clinician_id=p_actor AND t.status='active') AND private.notification_draft_ready(v.id)
     UNION ALL SELECT 'adr_assessments',a.id,a.patient_id,'adr_review','safety'
       FROM public.adr_assessments a WHERE a.status='draft' AND EXISTS(SELECT 1 FROM public.care_teams t
         WHERE t.patient_id=a.patient_id AND t.clinician_id=p_actor AND t.status='active')
     UNION ALL SELECT 'adherence_logs',a.id,a.patient_id,'barrier_reported','follow_up'
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
         '{}'::jsonb,'current:'||x.typ||':'||x.id||':'||x.kind,clock_timestamp());
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

CREATE FUNCTION private.notification_rows(p_actor uuid,p_role text)
RETURNS TABLE(id uuid,event_id uuid,created_at timestamptz,is_read boolean,actionable boolean,
  can_acknowledge boolean,group_key text,item jsonb)
LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 WITH authorized AS (
   SELECT r.*,e.event_type,e.category,e.source_type,e.source_id,e.patient_id,e.metadata,
     private.notification_source(e.source_type,e.source_id) s,
     private.notification_actionable(e,p_role) active,
     row_number() OVER (PARTITION BY e.source_type,e.source_id,e.event_type ORDER BY e.created_at DESC,e.id DESC) latest
   FROM public.notification_receipts r JOIN public.notification_events e ON e.id=r.event_id
   WHERE r.recipient_id=p_actor AND r.recipient_role=p_role AND private.notification_authorized(e,p_actor,p_role)
 ), states AS (
   SELECT a.*,(a.read_at IS NOT NULL OR (a.source_type='notifications' AND coalesce((s->>'is_read')::boolean,false))
     OR (a.event_type='message_received' AND EXISTS(SELECT 1 FROM public.care_conversation_reads cr
       WHERE cr.conversation_id=private.notification_uuid(a.metadata->>'conversation_id') AND cr.actor_id=p_actor
         AND (private.notification_ts(a.s->>'created_at'),a.source_id)<=(cr.last_message_at,cr.last_message_id)))) seen,
     (a.active AND a.latest=1 AND a.acknowledged_at IS NULL) needs
   FROM authorized a
 )
 SELECT a.id,a.event_id,a.created_at,a.seen,a.needs,
   (p_role='clinician' AND a.event_type IN ('barrier_reported','safety_flag') AND a.needs),
   CASE WHEN a.event_type='message_received' THEN 'message:'||(a.metadata->>'conversation_id')
     WHEN a.category='reminders' THEN 'reminder:'||coalesce(a.metadata->>'target_id',a.source_id::text)||':'||
       coalesce((private.notification_ts(a.metadata->>'scheduled_at')
         AT TIME ZONE private.notification_zone(p.timezone))::date::text,a.created_at::date::text)
     ELSE 'receipt:'||a.id END,
   jsonb_build_object('id',a.id,'event_type',a.event_type,'category',a.category,'source_type',a.source_type,
     'source_id',a.source_id,'patient_id',a.patient_id,'metadata',a.metadata,'created_at',a.created_at,
     'is_read',a.seen,'actionable',a.needs,'can_acknowledge',
       p_role='clinician' AND a.event_type IN ('barrier_reported','safety_flag') AND a.needs,
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

CREATE FUNCTION public.notification_centre_operation(
 p_actor_id uuid,p_actor_role text,p_action text,p_payload jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v_limit int; v_items jsonb; v_next jsonb; v_ids uuid[]; v_read_ids jsonb; v_count int:=0;
  x record; v_target record; v_group text; v_note text; v_ack boolean; v_receipt uuid;
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
 IF p_action='summary' THEN
   SELECT jsonb_build_object('unread_count',count(DISTINCT group_key) FILTER(WHERE NOT is_read),
     'action_item_count',count(*) FILTER(WHERE actionable AND item->>'category'<>'messages'
       AND p_actor_role='clinician')) INTO v_items FROM private.notification_rows(p_actor_id,p_actor_role);
   RETURN v_items;
 ELSIF p_action IN ('list','action_items') THEN
   v_limit:=coalesce((p_payload->>'limit')::int,50);
   IF v_limit NOT BETWEEN 1 AND 100 OR (p_payload ? 'category' AND p_payload->>'category' NOT IN
     ('documents','care_plans','appointments','follow_up','safety'))
     OR (p_payload ? 'before' AND (jsonb_typeof(p_payload->'before')<>'object'
       OR p_payload->'before'->>'id' IS NULL OR p_payload->'before'->>'created_at' IS NULL)) THEN
     RAISE EXCEPTION 'Invalid notification request' USING ERRCODE='22023'; END IF;
   WITH raw AS MATERIALIZED (SELECT * FROM private.notification_rows(p_actor_id,p_actor_role)),
   eligible AS (SELECT *,CASE WHEN NOT is_read AND p_action='list' THEN group_key ELSE 'receipt:'||id END bucket
     FROM raw WHERE (NOT coalesce((p_payload->>'unread')::boolean,false) OR NOT is_read)
       AND (p_action='list' OR (actionable AND item->>'category'<>'messages'))
       AND (p_payload->>'category' IS NULL OR item->>'category'=p_payload->>'category')),
   ranked AS (SELECT *,row_number() OVER(PARTITION BY bucket ORDER BY created_at DESC,id DESC) n FROM eligible),
   page AS (SELECT * FROM ranked WHERE n=1 AND (p_payload->>'before' IS NULL OR
     (created_at,id)<((p_payload->'before'->>'created_at')::timestamptz,(p_payload->'before'->>'id')::uuid))
     ORDER BY created_at DESC,id DESC LIMIT v_limit+1),
   shown AS (SELECT * FROM page ORDER BY created_at DESC,id DESC LIMIT v_limit)
   SELECT coalesce(jsonb_agg(s.item||jsonb_build_object('receipt_ids',
     (SELECT jsonb_agg(q.id ORDER BY q.created_at DESC,q.id DESC) FROM
       (SELECT r.id,r.created_at FROM eligible r WHERE r.bucket=s.bucket ORDER BY r.created_at DESC,r.id DESC LIMIT 1000) q))
     ORDER BY s.created_at DESC,s.id DESC),'[]'),
     CASE WHEN (SELECT count(*) FROM page)>v_limit THEN
       (SELECT jsonb_build_object('created_at',created_at,'id',id) FROM shown ORDER BY created_at,id LIMIT 1) END,
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
 ELSE
   v_receipt:=(p_payload->>'id')::uuid;
   SELECT * INTO v_target FROM private.notification_rows(p_actor_id,p_actor_role) WHERE id=v_receipt;
   IF NOT FOUND THEN RAISE EXCEPTION 'Notification unavailable' USING ERRCODE='42501'; END IF;
   IF v_ack THEN
     IF NOT v_target.can_acknowledge AND NOT EXISTS(SELECT 1 FROM public.notification_receipts r
       JOIN public.notification_events e ON e.id=r.event_id WHERE r.id=v_receipt AND r.acknowledged_at IS NOT NULL
         AND e.event_type IN ('barrier_reported','safety_flag')) THEN
       RAISE EXCEPTION 'Notification cannot be acknowledged' USING ERRCODE='22023'; END IF;
     v_ids:=ARRAY[v_receipt];
   ELSE
     -- Bound a grouped read by the captured representative, never newer arrivals.
     SELECT array_agg(id ORDER BY id) INTO v_ids FROM private.notification_rows(p_actor_id,p_actor_role)
       WHERE group_key=v_target.group_key AND (created_at,id)<=(v_target.created_at,v_target.id);
   END IF;
 END IF;
 IF EXISTS(SELECT 1 FROM unnest(v_ids) i WHERE NOT EXISTS(
   SELECT 1 FROM private.notification_rows(p_actor_id,p_actor_role) r WHERE r.id=i)) THEN
   RAISE EXCEPTION 'Notification unavailable' USING ERRCODE='42501'; END IF;
 PERFORM r.id FROM public.notification_receipts r WHERE r.id=ANY(v_ids) ORDER BY r.id FOR UPDATE;
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
 RETURN jsonb_build_object('updated_count',v_count);
END;
$$;

REVOKE ALL ON FUNCTION public.notification_centre_operation(uuid,text,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.notification_centre_operation(uuid,text,text,jsonb) TO service_role;
DO $$ DECLARE f record; BEGIN
 FOR f IN SELECT p.oid::regprocedure signature,p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname='private' AND (p.proname LIKE 'notification_%' OR p.proname='capture_notification_source') LOOP
   EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,anon,authenticated,service_role',f.signature);
   IF f.proname NOT IN ('capture_notification_source','notification_immutable') THEN
     EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role',f.signature);
   END IF;
 END LOOP;
END $$;
GRANT USAGE ON SCHEMA private TO service_role;
