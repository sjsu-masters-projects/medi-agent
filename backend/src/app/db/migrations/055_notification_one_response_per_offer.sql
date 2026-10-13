-- NOT-001 follow-up: one notification per answered offer.
--
-- A patient declining or asking for other times answers the whole offer, and 043 changes
-- every proposed slot at once. 051 captured an "appointment response" for each slot, so a
-- two-slot offer showed the clinician two items and two unread. Needs attention already
-- counted only the lowest-ID slot. Capture now records only that slot. Accepting one slot
-- still records one response, because the other slots become withdrawn, which is not news.
-- Events already captured are kept: history is append only.
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
