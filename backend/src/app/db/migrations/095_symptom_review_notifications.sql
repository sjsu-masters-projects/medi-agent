-- PAT-002-C follow-ups: the patient hears when a care team reviews their confirmed report, and
-- the generic hand-off message to the clinician carries the report it is about.
--
--   1. clinician_messages.symptom_report_id (nullable, ON DELETE SET NULL). The 091 hand-off
--      writes it, so the clinician's message can open the existing report panel
--      (/patients/{patient}?tab=symptoms#symptom-{id}). Hand-off rows that already exist are
--      linked only when exactly one report matches: the 071/091 'review_handoff' audit row
--      names the report, the message is for the same patient, carries the same fixed
--      subject and the exact body that report produces, and was written in the same
--      transaction. Anything else keeps no link. Who may read a message is unchanged
--      (the addressed clinician, by the existing policies and API filters).
--   2. A new patient notification, event type symptom_report_reviewed (category follow_up,
--      source symptom_reports). An AFTER INSERT trigger on symptom_report_reviews captures it
--      in the review's own transaction: a rolled-back review leaves nothing, a committed one
--      always has it. The event key is symptom_report_reviews:<report>:<care team>, the same
--      identity as the review's primary key, so a replay or a concurrent repeat converges on
--      one event, one pending delivery and one receipt (notification_capture is ON CONFLICT
--      DO NOTHING). Each care team that reviews gets its own item. Reviews recorded before
--      this migration are not replayed: nobody is told late about an old review.
--      The event stores the reviewer's name, the team's specialty and the report title the
--      patient already wrote (capped); nothing else from the report. It is History only
--      (never actionable) and maps to no email category (private.email_preference is NULL
--      for it), so no preference can turn it into email. Only "reviewed" exists; nothing
--      here records viewed or replied.
--
-- Lock order (OPS-006 rule 7): the trigger runs inside the review insert that already holds
-- the report-review primary-key slot; it takes no lock beyond notification_capture's own
-- unique-key insert, and reads reports, care teams and clinicians without locks.

-- ── 1. The hand-off message names its report ────────────────────────────────────────────

ALTER TABLE public.clinician_messages
  ADD COLUMN IF NOT EXISTS symptom_report_id uuid REFERENCES public.symptom_reports(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS clinician_messages_symptom_report
  ON public.clinician_messages (symptom_report_id) WHERE symptom_report_id IS NOT NULL;

-- The 091 hand-off, unchanged except that each message now carries the report id.
CREATE OR REPLACE FUNCTION private.enqueue_confirmed_symptom_review() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE report public.symptom_reports; recipient record; reached integer := 0;
BEGIN
  IF NEW.status='confirmed' AND OLD.status IS DISTINCT FROM 'confirmed' THEN
    SELECT * INTO STRICT report FROM public.symptom_reports WHERE id=NEW.confirmed_report_id
      AND patient_id=NEW.patient_id AND confirmation_state='patient_confirmed';
    INSERT INTO public.a2a_tasks(patient_id,symptom_event_id,idempotency_key,conversation_session_id,
      source_agent,target_agent,task_type,status,input_payload,worker_payload,next_retry_at)
      VALUES(NEW.patient_id,report.id,'confirmed_symptom:'||report.id::text,NEW.session_id,
        'symptom','pharmacovigilance','symptom_adr_screen','retrying',
        jsonb_build_object('session_id',NEW.session_id,'symptom_report',jsonb_build_object('id',report.id)),
        '{}',clock_timestamp()) ON CONFLICT(patient_id,idempotency_key) DO NOTHING;
    FOR recipient IN SELECT DISTINCT t.clinician_id FROM public.care_teams t
      JOIN public.clinic_memberships m ON m.clinician_id=t.clinician_id AND m.clinic_id=t.clinic_id
      JOIN public.clinics c ON c.id=t.clinic_id
      WHERE t.patient_id=NEW.patient_id AND t.status='active' AND m.status='active' AND c.status='active'
    LOOP
      INSERT INTO public.clinician_messages(clinician_id,patient_id,channel,subject,body,symptom_report_id)
        VALUES(recipient.clinician_id,NEW.patient_id,'in_app',
          CASE WHEN report.severity>=8 THEN 'High-severity patient-confirmed symptom' ELSE 'Patient-confirmed symptom for review' END,
          'Patient confirmed: '||report.symptom||'. Severity: '||coalesce(report.severity::text||'/10','unknown')||
          '. Review the confirmed summary and patient-reported products. A cause has not been established.',report.id);
      reached := reached + 1;
    END LOOP;
    INSERT INTO public.symptom_intake_audit(intake_id,patient_id,actor_id,action,revision,evidence)
      VALUES(NEW.id,NEW.patient_id,NEW.patient_id,'review_handoff',NEW.revision,
        jsonb_build_object('report_id',report.id,'task_key','confirmed_symptom:'||report.id::text,
          'recipients',reached));
  END IF;
  RETURN NEW;
END; $$;

-- Link existing hand-off messages where the audit row identifies the report unambiguously.
UPDATE public.clinician_messages m
   SET symptom_report_id = x.report_id
  FROM (
    SELECT cm.id AS message_id, min(r.id::text)::uuid AS report_id
      FROM public.clinician_messages cm
      JOIN public.symptom_intake_audit a
        ON a.patient_id = cm.patient_id AND a.action = 'review_handoff'
       AND cm.created_at BETWEEN a.created_at - interval '1 minute' AND a.created_at + interval '1 second'
      JOIN public.symptom_reports r
        ON r.id = nullif(a.evidence ->> 'report_id', '')::uuid AND r.patient_id = cm.patient_id
       AND r.confirmation_state = 'patient_confirmed'
       AND cm.subject = CASE WHEN r.severity >= 8 THEN 'High-severity patient-confirmed symptom'
                             ELSE 'Patient-confirmed symptom for review' END
       AND cm.body = 'Patient confirmed: ' || r.symptom || '. Severity: '
         || coalesce(r.severity::text || '/10', 'unknown')
         || '. Review the confirmed summary and patient-reported products. A cause has not been established.'
     WHERE cm.symptom_report_id IS NULL
     GROUP BY cm.id
    HAVING count(DISTINCT r.id) = 1
  ) x
 WHERE m.id = x.message_id AND m.symptom_report_id IS NULL;

-- ── 2. A care team's review reaches the patient ─────────────────────────────────────────

ALTER TABLE public.notification_events
  DROP CONSTRAINT IF EXISTS notification_events_event_type_check,
  ADD CONSTRAINT notification_events_event_type_check CHECK (event_type IN (
    'message_received','appointment_offered','appointment_changed','appointment_response',
    'appointment_reminder','care_plan_published','care_plan_draft','document_review',
    'document_processed','document_failed','document_reviewed','barrier_reported',
    'adr_review','adr_information_requested','safety_flag','med_reminder','obligation_reminder',
    'legacy_update','critical_result','adr_information_answered','care_plan_review',
    'symptom_report_reviewed'));

-- As 087, plus symptom_report_reviewed (History only).
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
 -- Open exactly while the care-team work item is open; replying, adopting or retiring ends it.
 WHEN 'care_plan_review' THEN RETURN p_role='clinician' AND s->>'status'='open';
 -- News for the patient (095): a care team recorded that it reviewed their report. History only.
 WHEN 'symptom_report_reviewed' THEN RETURN false;
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

CREATE OR REPLACE FUNCTION private.capture_symptom_report_review() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_title text; v_name text; v_specialty text;
BEGIN
  SELECT left(btrim(r.symptom), 120) INTO v_title FROM public.symptom_reports r
   WHERE r.id = NEW.report_id AND r.patient_id = NEW.patient_id
     AND r.confirmation_state = 'patient_confirmed';
  IF NOT FOUND THEN RETURN NEW; END IF;
  SELECT btrim(cl.first_name || ' ' || cl.last_name),
         coalesce(nullif(btrim(t.specialty_context), ''), nullif(btrim(cl.specialty), ''))
    INTO v_name, v_specialty
    FROM public.care_teams t JOIN public.clinicians cl ON cl.id = NEW.reviewed_by
   WHERE t.id = NEW.care_team_id;
  PERFORM private.notification_capture('symptom_reports', NEW.report_id, NEW.patient_id,
    'symptom_report_reviewed', 'follow_up', 'patient', NULL,
    jsonb_build_object('care_team_id', NEW.care_team_id, 'clinician_name', left(v_name, 160),
      'specialty', left(v_specialty, 100), 'report_title', v_title),
    'symptom_report_reviews:' || NEW.report_id::text || ':' || NEW.care_team_id::text,
    NEW.reviewed_at);
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS symptom_report_review_notification ON public.symptom_report_reviews;
CREATE TRIGGER symptom_report_review_notification
  AFTER INSERT ON public.symptom_report_reviews
  FOR EACH ROW EXECUTE FUNCTION private.capture_symptom_report_review();

-- ── 3. Grants and verification ──────────────────────────────────────────────────────────

REVOKE ALL ON FUNCTION private.capture_symptom_report_review(), private.enqueue_confirmed_symptom_review(),
  private.notification_actionable(public.notification_events, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.capture_symptom_report_review(), private.enqueue_confirmed_symptom_review(),
  private.notification_actionable(public.notification_events, text) TO service_role;

DO $verify$
DECLARE v_function text;
BEGIN
  FOREACH v_function IN ARRAY ARRAY[
    'private.capture_symptom_report_review()',
    'private.enqueue_confirmed_symptom_review()',
    'private.notification_actionable(public.notification_events,text)'] LOOP
    IF has_function_privilege('anon', v_function, 'EXECUTE')
       OR has_function_privilege('authenticated', v_function, 'EXECUTE')
       OR NOT has_function_privilege('service_role', v_function, 'EXECUTE') THEN
      RAISE EXCEPTION '095: wrong execute grants on %', v_function;
    END IF;
  END LOOP;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
      AND table_name = 'clinician_messages' AND column_name = 'symptom_report_id') THEN
    RAISE EXCEPTION '095: clinician_messages.symptom_report_id is missing';
  END IF;
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.clinician_messages'::regclass)
     OR NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.symptom_report_reviews'::regclass) THEN
    RAISE EXCEPTION '095: row level security must stay enabled';
  END IF;
  IF has_table_privilege('anon', 'public.symptom_report_reviews', 'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('authenticated', 'public.symptom_report_reviews', 'SELECT,INSERT,UPDATE,DELETE') THEN
    RAISE EXCEPTION '095: browser roles must have no access to symptom_report_reviews';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'symptom_report_review_notification'
      AND tgrelid = 'public.symptom_report_reviews'::regclass AND NOT tgisinternal) THEN
    RAISE EXCEPTION '095: the review notification trigger is missing';
  END IF;
  IF private.email_preference('symptom_report_reviewed') IS NOT NULL THEN
    RAISE EXCEPTION '095: a review notice must not map to an email category';
  END IF;
  IF (SELECT prosrc FROM pg_proc WHERE oid = 'private.enqueue_confirmed_symptom_review()'::regprocedure)
     NOT LIKE '%symptom_report_id%' THEN
    RAISE EXCEPTION '095: the hand-off no longer records its report';
  END IF;
END
$verify$;
