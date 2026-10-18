-- UX-006: clinician visit management (cancel, complete, no-show). Requires 043, 063 and 069.
--
-- This migration:
--   * adds appointments.cancelled_by ('patient' | 'clinician'), cancel_reason_code, cancel_reason
--     and cancelled_at. A patient's own cancel (043) leaves cancelled_by empty, as before;
--   * lets appointment_offer_events record 'clinician_cancel', 'complete' and 'no_show' with the
--     actor and a note (the reason), still append-only;
--   * adds public.manage_appointment (backend only): one transaction that checks the actor is the
--     appointment's own clinician or holds an active link to the patient at the appointment's
--     clinic, applies the transition, and writes the audit row. cancel: confirmed or scheduled
--     only; complete and no_show: confirmed or scheduled, and only once the visit has ended;
--   * replaces private.capture_notification_source (063's body) so that a clinician's cancel of a
--     booked visit is an 'appointment_changed' notice to the PATIENT (in-app and, through the
--     existing outbox, email) instead of being read as a patient's response to the clinician.
--
-- The exclusion constraints (043 patient, 069 clinician) apply only to confirmed/scheduled, so a
-- cancelled, completed or no-show visit frees its slot; the verification block checks this.
-- Written, not applied: applied to a hosted project only on explicit authorization, before the
-- backend that calls it deploys (apply first, merge after). Synthetic data.

ALTER TABLE public.appointments
  ADD COLUMN IF NOT EXISTS cancelled_by text,
  ADD COLUMN IF NOT EXISTS cancel_reason_code text,
  ADD COLUMN IF NOT EXISTS cancel_reason text,
  ADD COLUMN IF NOT EXISTS cancelled_at timestamptz;
ALTER TABLE public.appointments DROP CONSTRAINT IF EXISTS appointments_cancelled_by_check;
ALTER TABLE public.appointments ADD CONSTRAINT appointments_cancelled_by_check
  CHECK (cancelled_by IS NULL OR cancelled_by IN ('patient', 'clinician'));
ALTER TABLE public.appointments DROP CONSTRAINT IF EXISTS appointments_cancel_reason_check;
ALTER TABLE public.appointments ADD CONSTRAINT appointments_cancel_reason_check
  CHECK ((cancel_reason_code IS NULL OR cancel_reason_code IN
      ('clinician_unavailable', 'clinic_closed', 'patient_request', 'scheduling_error', 'other'))
    AND (cancel_reason IS NULL OR char_length(cancel_reason) <= 500));

ALTER TABLE public.appointment_offer_events ADD COLUMN IF NOT EXISTS note text;
ALTER TABLE public.appointment_offer_events DROP CONSTRAINT IF EXISTS appointment_offer_events_note_check;
ALTER TABLE public.appointment_offer_events ADD CONSTRAINT appointment_offer_events_note_check
  CHECK (note IS NULL OR char_length(note) <= 600);
ALTER TABLE public.appointment_offer_events DROP CONSTRAINT IF EXISTS appointment_offer_events_action_check;
ALTER TABLE public.appointment_offer_events ADD CONSTRAINT appointment_offer_events_action_check
  CHECK (action IN ('propose', 'accept', 'decline', 'request_alternative', 'cancel', 'expire',
    'clinician_cancel', 'complete', 'no_show'));

CREATE OR REPLACE FUNCTION public.manage_appointment(
  p_actor_id uuid, p_appointment_id uuid, p_action text, p_reason_code text, p_reason text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE
  v_row public.appointments%ROWTYPE;
  v_new appointment_status_enum;
  v_prev appointment_status_enum;
  v_reason text := nullif(btrim(coalesce(p_reason, '')), '');
BEGIN
  IF p_actor_id IS NULL OR p_action IS NULL OR p_action NOT IN ('cancel', 'complete', 'no_show') THEN
    RETURN jsonb_build_object('error', 'invalid');
  END IF;
  SELECT * INTO v_row FROM public.appointments WHERE id = p_appointment_id FOR UPDATE;
  IF NOT FOUND THEN RETURN jsonb_build_object('error', 'not_found'); END IF;
  IF v_row.clinician_id IS DISTINCT FROM p_actor_id AND NOT EXISTS (
    SELECT 1 FROM public.care_teams
    WHERE clinician_id = p_actor_id AND patient_id = v_row.patient_id
      AND clinic_id = v_row.clinic_id AND status = 'active'
  ) THEN RETURN jsonb_build_object('error', 'forbidden'); END IF;
  IF v_row.status NOT IN ('confirmed', 'scheduled') THEN
    RETURN jsonb_build_object('error', 'stale');
  END IF;
  IF p_action = 'cancel' THEN
    IF p_reason_code IS NULL OR p_reason_code NOT IN
        ('clinician_unavailable', 'clinic_closed', 'patient_request', 'scheduling_error', 'other')
       OR (p_reason_code = 'other' AND v_reason IS NULL)
       OR char_length(coalesce(v_reason, '')) > 500 THEN
      RETURN jsonb_build_object('error', 'invalid');
    END IF;
    v_new := 'cancelled';
  ELSE
    IF v_row.scheduled_at + make_interval(mins => v_row.duration_minutes) > clock_timestamp() THEN
      RETURN jsonb_build_object('error', 'too_early');
    END IF;
    v_new := CASE p_action WHEN 'complete' THEN 'completed' ELSE 'no_show' END;
  END IF;
  v_prev := v_row.status;
  UPDATE public.appointments SET
    status = v_new,
    cancelled_by = CASE WHEN p_action = 'cancel' THEN 'clinician' ELSE cancelled_by END,
    cancel_reason_code = CASE WHEN p_action = 'cancel' THEN p_reason_code ELSE cancel_reason_code END,
    cancel_reason = CASE WHEN p_action = 'cancel' THEN v_reason ELSE cancel_reason END,
    cancelled_at = CASE WHEN p_action = 'cancel' THEN clock_timestamp() ELSE cancelled_at END
  WHERE id = p_appointment_id RETURNING * INTO v_row;
  INSERT INTO public.appointment_offer_events(appointment_id, patient_id, proposal_group_id,
      actor_id, action, previous_status, new_status, note)
    VALUES (v_row.id, v_row.patient_id, v_row.proposal_group_id, p_actor_id,
      CASE p_action WHEN 'cancel' THEN 'clinician_cancel' ELSE p_action END,
      v_prev, v_new,
      CASE WHEN p_action = 'cancel' THEN left(p_reason_code || coalesce(': ' || v_reason, ''), 600) END);
  RETURN jsonb_build_object('appointment', to_jsonb(v_row));
END;
$$;
REVOKE ALL ON FUNCTION public.manage_appointment(uuid, uuid, text, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.manage_appointment(uuid, uuid, text, text, text) TO service_role;

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
     -- A clinician's cancel of a booked visit tells the patient (071); the patient's own
     -- cancel, which leaves cancelled_by empty, still goes to the clinician.
     WHEN TG_OP='UPDATE' AND o->>'status' IN ('confirmed','scheduled') AND s->>'status'='cancelled'
       AND s->>'cancelled_by'='clinician'
       THEN 'appointment_changed'
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

-- Verification: fail the whole migration if anything above did not land as intended.
DO $$
DECLARE v_def text;
BEGIN
  IF (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public'
        AND table_name = 'appointments'
        AND column_name IN ('cancelled_by', 'cancel_reason_code', 'cancel_reason', 'cancelled_at')) <> 4 THEN
    RAISE EXCEPTION '071: appointments cancellation columns are missing';
  END IF;
  FOR v_def IN SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c
      WHERE c.conrelid = 'public.appointments'::regclass AND c.contype = 'x'
        AND c.conname IN ('appointments_patient_no_overlap', 'appointments_clinician_no_overlap') LOOP
    IF v_def NOT LIKE '%confirmed%' OR v_def NOT LIKE '%scheduled%' OR v_def LIKE '%cancelled%'
       OR v_def LIKE '%completed%' OR v_def LIKE '%no_show%' THEN
      RAISE EXCEPTION '071: an overlap constraint covers more than confirmed/scheduled: %', v_def;
    END IF;
  END LOOP;
  IF (SELECT count(*) FROM pg_constraint WHERE conrelid = 'public.appointments'::regclass
        AND conname IN ('appointments_patient_no_overlap', 'appointments_clinician_no_overlap')) <> 2 THEN
    RAISE EXCEPTION '071: an overlap constraint is missing';
  END IF;
  IF to_regprocedure('public.manage_appointment(uuid,uuid,text,text,text)') IS NULL THEN
    RAISE EXCEPTION '071: manage_appointment is missing';
  END IF;
  IF has_function_privilege('anon', 'public.manage_appointment(uuid,uuid,text,text,text)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.manage_appointment(uuid,uuid,text,text,text)', 'EXECUTE') THEN
    RAISE EXCEPTION '071: manage_appointment is executable by a browser role';
  END IF;
  IF position('cancelled_by' IN pg_get_functiondef('private.capture_notification_source()'::regprocedure)) = 0 THEN
    RAISE EXCEPTION '071: the notification capture does not classify a clinician cancel';
  END IF;
END $$;
