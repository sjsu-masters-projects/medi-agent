-- PV-001-C: the patient's ADR follow-up notification follows its information request.
--
-- 047 and 055 captured the patient's "your care team requested information" item from
-- adr_assessments. Answering touched the assessment, so a second, unread and actionable
-- request item appeared after the patient had already answered (G6), and 047 also
-- inserted an English-only public.notifications row that the centre captured as a second
-- "Earlier notification" item (G7). The clinician was never told about the answer (G8),
-- and deleting a patient who had answered failed on the RESTRICT reference from the ADR
-- audit to patients (G9; reproduced by the disposable PostgreSQL contract test).
--
-- Now each information request is its own notification source:
--   * the patient item is captured once, when the request is inserted, and is actionable
--     only while that request is pending; answering marks its receipt read;
--   * answering records one History-only "patient answered" item for the currently
--     assigned clinicians (shared, like adr_review), which maps to no email category;
--   * review_adr_assessment no longer inserts the legacy public.notifications row.
-- History is append only: earlier events and legacy rows are kept. Assessment-sourced
-- request items captured before this migration stay actionable only while a request that
-- existed when they were captured is still pending (rule L in notification_actionable).
--
-- Every redefined function starts from its latest definition (notification_source 051,
-- notification_actionable 059, capture_notification_source 055, both ADR RPCs 047) and
-- keeps its signature, so existing callers and the critical_result branches are unchanged.
-- Written for review; it is applied to a hosted project only on explicit authorization.

-- 1. Allowlists. Both are supersets, so existing rows still validate.
ALTER TABLE public.notification_events
  DROP CONSTRAINT notification_events_event_type_check,
  ADD CONSTRAINT notification_events_event_type_check CHECK (event_type IN (
    'message_received','appointment_offered','appointment_changed','appointment_response',
    'appointment_reminder','care_plan_published','care_plan_draft','document_review',
    'document_processed','document_failed','document_reviewed','barrier_reported',
    'adr_review','adr_information_requested','safety_flag','med_reminder','obligation_reminder',
    'legacy_update','critical_result','adr_information_answered')),
  DROP CONSTRAINT notification_events_source_type_check,
  ADD CONSTRAINT notification_events_source_type_check CHECK (source_type IN ('care_conversation_messages',
    'appointments','notifications','care_plan_versions','documents','adherence_logs',
    'adr_assessments','clinician_messages','adr_information_requests'));

-- 2. Internal only: never return arbitrary source JSON to the API (ADR reasoning,
-- storage URLs, and unrelated clinical content must not enter notification data).
CREATE OR REPLACE FUNCTION private.notification_source(p_type text,p_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v jsonb;
BEGIN
  IF p_type NOT IN ('care_conversation_messages','appointments','notifications',
    'care_plan_versions','documents','adherence_logs','adr_assessments','clinician_messages',
    'adr_information_requests') THEN RETURN NULL; END IF;
  EXECUTE format('SELECT to_jsonb(s) FROM public.%I s WHERE id=$1',p_type) INTO v USING p_id;
  RETURN v;
END;
$$;

-- 3. Only the two ADR follow-up branches change.
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
 WHEN 'adr_information_requested' THEN
   -- Open exactly while its own request is pending. Answering, a later request, marking
   -- the assessment reviewed or dismissed, and preparing a MedWatch draft all end it.
   IF e.source_type='adr_information_requests' THEN RETURN s->>'status'='pending'; END IF;
   -- Rule L, for items captured from the assessment before 063: open only while a
   -- request that already existed when the item was captured is still pending.
   RETURN s->>'status'='draft' AND s->>'last_review_action'='request_information'
     AND EXISTS(SELECT 1 FROM public.adr_information_requests r WHERE r.adr_assessment_id=e.source_id
       AND r.patient_id=e.patient_id AND r.status='pending' AND r.created_at<=e.created_at);
 -- News for the assigned clinicians; the assessment's own adr_review item is the work.
 WHEN 'adr_information_answered' THEN RETURN false;
 WHEN 'barrier_reported' THEN RETURN p_role='clinician' AND s->>'status'='skipped' AND s->>'barrier_code' IS NOT NULL;
 WHEN 'safety_flag' THEN RETURN p_role='clinician';
 -- Stays actionable for assigned clinicians until they read it, unless the source document
 -- was rejected as not this patient's.
 WHEN 'critical_result' THEN RETURN p_role='clinician' AND s->>'review_status' IS DISTINCT FROM 'rejected';
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

-- 4. Capture: the adr_assessments branch keeps adr_review only; requests capture the
-- patient item on insert and the clinician alert on the answer, each under one key.
CREATE OR REPLACE FUNCTION private.capture_notification_source() RETURNS trigger
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
   -- A patient's decline or request for other times changes every slot of the offer in
   -- one statement, and row triggers run after it, so all slots are visible here. Only the
   -- lowest-ID slot (the one notification_actionable treats as the item) records the news.
   IF v_kind='appointment_response' AND o->>'status'='proposed' AND s->>'proposal_group_id' IS NOT NULL
     AND EXISTS(SELECT 1 FROM public.appointments a WHERE a.proposal_group_id=(s->>'proposal_group_id')::uuid
       AND a.status::text=s->>'status' AND a.id<v_id) THEN RETURN NEW; END IF;
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
   -- Clinician review work only. Patient requests are captured from their own rows
   -- below, so a rescore, evidence change or updated_at touch notifies nobody.
   IF s->>'status' IS DISTINCT FROM 'draft' OR (TG_OP='UPDATE' AND o->>'status'='draft') THEN RETURN NEW; END IF;
   v_kind:='adr_review'; v_category:='safety';
 WHEN 'adr_information_requests' THEN
   -- No symptom, medication, message or answer text: the request ID resolves the view.
   IF TG_OP='INSERT' AND s->>'status'='pending' THEN
     v_kind:='adr_information_requested'; v_audience:='patient';
     v_meta:=jsonb_build_object('requested_information',s->'requested_information',
       'clinician_id',s->>'requested_by','adr_assessment_id',s->>'adr_assessment_id','information_request_id',v_id);
     v_key:='adr_information_requests:'||v_id||':requested';
   ELSIF TG_OP='UPDATE' AND o->>'status'='pending' AND s->>'status'='answered' THEN
     -- Shared with the clinicians assigned now, like adr_review; one per request.
     v_kind:='adr_information_answered';
     v_meta:=jsonb_build_object('adr_assessment_id',s->>'adr_assessment_id','information_request_id',v_id);
     v_key:='adr_information_requests:'||v_id||':answered';
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

-- 5. Capture is part of the request's own transaction, as for every NOT-001 source.
CREATE TRIGGER notification_capture AFTER INSERT OR UPDATE ON public.adr_information_requests
  FOR EACH ROW EXECUTE FUNCTION private.capture_notification_source();

-- 6. 047 without the English-only public.notifications insert. Existing legacy rows and
-- their "Earlier notification" events stay as History.
CREATE OR REPLACE FUNCTION public.review_adr_assessment(
  p_assessment_id uuid,
  p_actor_id uuid,
  p_action text,
  p_note text DEFAULT NULL,
  p_requested_information jsonb DEFAULT '[]'::jsonb
) RETURNS SETOF public.adr_assessments
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_assessment public.adr_assessments%ROWTYPE;
  v_note text := NULLIF(btrim(COALESCE(p_note, '')), '');
  v_status public.adr_status_enum;
  v_event_type text;
  v_requested_information jsonb := COALESCE(p_requested_information, '[]'::jsonb);
  v_now timestamptz := now();
  v_request_id uuid;
BEGIN
  SELECT * INTO v_assessment
  FROM public.adr_assessments
  WHERE id = p_assessment_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'ADR assessment not found' USING ERRCODE = 'P0002';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.care_teams
    WHERE clinician_id = p_actor_id
      AND patient_id = v_assessment.patient_id
      AND status = 'active'
  ) THEN
    RAISE EXCEPTION 'Clinician is not assigned to this patient' USING ERRCODE = '42501';
  END IF;

  IF v_assessment.status <> 'draft' THEN
    RAISE EXCEPTION 'ADR assessment review has already been completed'
      USING ERRCODE = '23514';
  END IF;

  IF p_action NOT IN ('mark_reviewed', 'dismiss', 'request_information') THEN
    RAISE EXCEPTION 'Unsupported ADR review action' USING ERRCODE = '22023';
  END IF;

  IF p_action IN ('dismiss', 'request_information') AND v_note IS NULL THEN
    RAISE EXCEPTION 'A review note is required for this action' USING ERRCODE = '22023';
  END IF;

  IF jsonb_typeof(v_requested_information) <> 'array' THEN
    RAISE EXCEPTION 'Requested information must be an array' USING ERRCODE = '22023';
  END IF;

  IF p_action = 'request_information' AND (
    jsonb_array_length(v_requested_information) = 0
    OR NOT (
      v_requested_information <@ '["reappeared_on_rechallenge", "dose_response", "similar_previous_reaction"]'::jsonb
    )
  ) THEN
    RAISE EXCEPTION 'Only patient-answerable retrospective questions may be requested'
      USING ERRCODE = '22023';
  END IF;

  v_status := CASE
    WHEN p_action = 'mark_reviewed' THEN 'reviewed'::public.adr_status_enum
    WHEN p_action = 'dismiss' THEN 'dismissed'::public.adr_status_enum
    ELSE 'draft'::public.adr_status_enum
  END;
  v_event_type := CASE
    WHEN p_action = 'mark_reviewed' THEN 'marked_reviewed'
    WHEN p_action = 'dismiss' THEN 'dismissed'
    ELSE 'information_requested'
  END;

  UPDATE public.adr_assessments
  SET status = v_status,
      reviewed_by = p_actor_id,
      reviewed_at = v_now,
      dismiss_reason = CASE WHEN p_action = 'dismiss' THEN v_note ELSE NULL END,
      last_review_action = p_action,
      review_note = v_note,
      requested_information = CASE
        WHEN p_action = 'request_information' THEN v_requested_information
        ELSE '[]'::jsonb
      END,
      updated_at = v_now
  WHERE id = p_assessment_id;

  UPDATE public.adr_information_requests
  SET status = 'cancelled', updated_at = v_now
  WHERE adr_assessment_id = p_assessment_id
    AND status = 'pending';

  -- The request insert captures the patient's bilingual notification item.
  IF p_action = 'request_information' THEN
    INSERT INTO public.adr_information_requests(
      adr_assessment_id,
      patient_id,
      requested_by,
      requested_information,
      patient_message,
      baseline_naranjo_score,
      baseline_causality,
      created_at,
      updated_at
    ) VALUES (
      p_assessment_id,
      v_assessment.patient_id,
      p_actor_id,
      v_requested_information,
      v_note,
      v_assessment.naranjo_score,
      v_assessment.causality,
      v_now,
      v_now
    ) RETURNING id INTO v_request_id;
  END IF;

  INSERT INTO public.adr_assessment_audit_events(
    adr_assessment_id,
    actor_id,
    event_type,
    event_data
  ) VALUES (
    p_assessment_id,
    p_actor_id,
    v_event_type,
    jsonb_build_object(
      'previous_status', v_assessment.status,
      'status', v_status,
      'note', v_note,
      'information_request_id', v_request_id,
      'requested_information', CASE
        WHEN p_action = 'request_information' THEN v_requested_information
        ELSE '[]'::jsonb
      END
    )
  );

  RETURN QUERY
  SELECT * FROM public.adr_assessments WHERE id = p_assessment_id;
END;
$$;

-- 7. 047 plus marking the patient's request receipt read, in the same transaction as the
-- answer, so a capture or read-audit failure rolls the answer back.
CREATE OR REPLACE FUNCTION public.respond_to_adr_information_request(
  p_request_id uuid,
  p_patient_id uuid,
  p_responses jsonb,
  p_naranjo_answers jsonb,
  p_naranjo_assessment jsonb,
  p_evidence jsonb,
  p_score smallint,
  p_causality text
) RETURNS SETOF public.adr_information_requests
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_request public.adr_information_requests%ROWTYPE;
  v_assessment public.adr_assessments%ROWTYPE;
  v_now timestamptz := now();
BEGIN
  SELECT * INTO v_request
  FROM public.adr_information_requests
  WHERE id = p_request_id
  FOR UPDATE;

  IF NOT FOUND OR v_request.patient_id <> p_patient_id THEN
    RAISE EXCEPTION 'ADR information request not found' USING ERRCODE = 'P0002';
  END IF;
  IF v_request.status <> 'pending' THEN
    RAISE EXCEPTION 'ADR information request has already been completed'
      USING ERRCODE = '23514';
  END IF;

  SELECT * INTO v_assessment
  FROM public.adr_assessments
  WHERE id = v_request.adr_assessment_id
  FOR UPDATE;
  IF NOT FOUND OR v_assessment.status <> 'draft' THEN
    RAISE EXCEPTION 'ADR assessment is no longer awaiting information'
      USING ERRCODE = '23514';
  END IF;

  IF jsonb_typeof(p_responses) <> 'array'
    OR jsonb_array_length(p_responses) <> jsonb_array_length(v_request.requested_information)
    OR jsonb_typeof(p_naranjo_answers) <> 'object'
    OR jsonb_typeof(p_naranjo_assessment) <> 'object'
    OR jsonb_typeof(p_evidence) <> 'array'
    OR p_score NOT BETWEEN -4 AND 13
  THEN
    RAISE EXCEPTION 'Invalid ADR information response payload' USING ERRCODE = '22023';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM jsonb_array_elements(p_responses) response
    WHERE response->>'question' NOT IN (
      SELECT jsonb_array_elements_text(v_request.requested_information)
    )
      OR response->>'answer' NOT IN ('yes', 'no', 'do_not_know')
      OR (
        response->>'answer' <> 'do_not_know'
        AND NULLIF(btrim(response->>'evidence'), '') IS NULL
      )
  ) OR (
    SELECT count(*) <> count(DISTINCT response->>'question')
    FROM jsonb_array_elements(p_responses) response
  ) THEN
    RAISE EXCEPTION 'Responses must answer each requested question exactly once'
      USING ERRCODE = '22023';
  END IF;

  -- Captures the clinicians' "patient answered" item (063).
  UPDATE public.adr_information_requests
  SET status = 'answered',
      responses = p_responses,
      resolved_naranjo_score = p_score,
      resolved_causality = p_causality::public.naranjo_causality_enum,
      responded_at = v_now,
      updated_at = v_now
  WHERE id = p_request_id;

  UPDATE public.adr_assessments
  SET naranjo_answers = p_naranjo_answers,
      naranjo_assessment = p_naranjo_assessment,
      evidence = p_evidence,
      naranjo_score = p_score,
      causality = p_causality::public.naranjo_causality_enum,
      updated_at = v_now
  WHERE id = v_request.adr_assessment_id;

  -- Requests made before 063 may still have a legacy row; none is created after it.
  UPDATE public.notifications
  SET is_read = true
  WHERE patient_id = p_patient_id
    AND dedupe_key = 'adr-information-request:' || p_request_id::text;

  -- Deliver anything still pending to the patient, then mark this request's item read:
  -- the item captured from the request, or one captured from the assessment for it
  -- before 063. Earlier requests' items keep their unread state.
  PERFORM private.notification_prepare(p_patient_id, 'patient');
  WITH marked AS (
    UPDATE public.notification_receipts r
    SET read_at = clock_timestamp()
    FROM public.notification_events e
    WHERE e.id = r.event_id
      AND r.recipient_id = p_patient_id
      AND r.recipient_role = 'patient'
      AND r.read_at IS NULL
      AND e.patient_id = p_patient_id
      AND e.event_type = 'adr_information_requested'
      AND (
        (e.source_type = 'adr_information_requests' AND e.source_id = p_request_id)
        OR (
          e.source_type = 'adr_assessments'
          AND e.source_id = v_request.adr_assessment_id
          AND e.created_at >= v_request.created_at
        )
      )
    RETURNING r.id
  )
  INSERT INTO public.notification_read_audit(receipt_id, actor_id, action)
  SELECT id, p_patient_id, 'read' FROM marked
  ON CONFLICT DO NOTHING;

  INSERT INTO public.adr_assessment_audit_events(
    adr_assessment_id,
    actor_id,
    patient_actor_id,
    event_type,
    event_data
  ) VALUES (
    v_request.adr_assessment_id,
    NULL,
    p_patient_id,
    'patient_information_provided',
    jsonb_build_object(
      'information_request_id', p_request_id,
      'answered_questions', v_request.requested_information,
      'previous_naranjo_score', v_assessment.naranjo_score,
      'naranjo_score', p_score,
      'causality', p_causality
    )
  );

  RETURN QUERY
  SELECT * FROM public.adr_information_requests WHERE id = p_request_id;
END;
$$;

-- 8. A patient's ADR audit goes with the patient. The contract test reproduced the
-- RESTRICT failure: the patient row was still referenced although the cascade through
-- adr_assessments removes the same audit rows. SET NULL would break exactly_one_actor.
-- Clinician references stay RESTRICT until the clinician-deletion decision (D1).
ALTER TABLE public.adr_assessment_audit_events
  DROP CONSTRAINT adr_assessment_audit_events_patient_actor_id_fkey,
  ADD CONSTRAINT adr_assessment_audit_events_patient_actor_id_fkey FOREIGN KEY (patient_actor_id)
    REFERENCES public.patients(id) ON DELETE CASCADE;

-- 9. The cascade is the only way audit rows leave. 048 granted service_role ALL on the
-- MedWatch audit, and hosted default privileges can grant it on new tables; revoke
-- explicitly, as 053 did for conversation history.
REVOKE DELETE, TRUNCATE ON public.adr_assessment_audit_events, public.medwatch_draft_audit_events
  FROM PUBLIC, anon, authenticated, service_role;

-- 10. Grants. Signatures are unchanged; restated so this file stands on its own.
REVOKE ALL ON FUNCTION public.review_adr_assessment(uuid, uuid, text, text, jsonb)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.review_adr_assessment(uuid, uuid, text, text, jsonb)
  TO service_role;
REVOKE ALL ON FUNCTION public.respond_to_adr_information_request(
  uuid, uuid, jsonb, jsonb, jsonb, jsonb, smallint, text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.respond_to_adr_information_request(
  uuid, uuid, jsonb, jsonb, jsonb, jsonb, smallint, text
) TO service_role;
REVOKE ALL ON FUNCTION private.notification_source(text, uuid),
  private.notification_actionable(public.notification_events, text),
  private.capture_notification_source() FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.notification_source(text, uuid),
  private.notification_actionable(public.notification_events, text) TO service_role;

-- 11. Fail the migration rather than leave a patient reference that blocks deletion, a
-- role that can delete ADR or MedWatch audit, a request without capture, the legacy
-- insert, or a browser role that can call either RPC.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint c
    WHERE c.contype = 'f' AND c.confdeltype NOT IN ('c', 'n')
      AND c.conrelid IN ('public.adr_information_requests'::regclass,
        'public.adr_assessment_audit_events'::regclass, 'public.medwatch_drafts'::regclass,
        'public.medwatch_draft_audit_events'::regclass)
      AND c.confrelid IN ('public.patients'::regclass, 'public.adr_assessments'::regclass,
        'public.medwatch_drafts'::regclass)
  ) THEN
    RAISE EXCEPTION 'A patient ADR or MedWatch reference still blocks patient deletion';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(ARRAY['public.adr_assessment_audit_events',
      'public.medwatch_draft_audit_events']) t(name)
    CROSS JOIN unnest(ARRAY['anon', 'authenticated', 'service_role']) r(role)
    WHERE pg_catalog.has_table_privilege(r.role, t.name, 'DELETE')
      OR pg_catalog.has_table_privilege(r.role, t.name, 'TRUNCATE')
  ) THEN
    RAISE EXCEPTION 'No role may delete ADR or MedWatch audit directly';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_trigger
    WHERE tgrelid = 'public.adr_information_requests'::regclass
      AND tgname = 'notification_capture' AND NOT tgisinternal
  ) THEN
    RAISE EXCEPTION 'ADR information requests are not captured as notification sources';
  END IF;
  IF position('INSERT INTO public.notifications' IN pg_catalog.pg_get_functiondef(
    'public.review_adr_assessment(uuid,uuid,text,text,jsonb)'::regprocedure)) > 0 THEN
    RAISE EXCEPTION 'review_adr_assessment still writes the legacy notification';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(ARRAY['public.review_adr_assessment(uuid,uuid,text,text,jsonb)',
      'public.respond_to_adr_information_request(uuid,uuid,jsonb,jsonb,jsonb,jsonb,smallint,text)']) f(name)
    CROSS JOIN unnest(ARRAY['anon', 'authenticated']) r(role)
    WHERE pg_catalog.has_function_privilege(r.role, f.name, 'EXECUTE')
  ) THEN
    RAISE EXCEPTION 'Browser roles may not call the ADR information RPCs';
  END IF;
END $$;
