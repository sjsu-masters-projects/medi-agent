-- AI-005: alert assigned clinicians when a document reports a critical test result.
--
-- Document extraction (AI-005) records each printed test result as a review-only
-- candidate. When the report itself flags a result as critical ("HH", "LL", "CRITICAL",
-- "Pánico"; read deterministically into value->>'flag_meaning'), the patient's active care
-- team gets one Safety notification per document. Patients never receive it: their
-- explanation already tells them to contact the care team today.
--
-- Capture runs when the result's document citation is written, because the citation is
-- what ties the fact to its document. It is idempotent per document and part of the same
-- transaction, like every NOT-001 capture. Additive: the event-type list is widened, and
-- two functions are replaced with the same signatures, so existing grants still apply.

ALTER TABLE public.notification_events
  DROP CONSTRAINT notification_events_event_type_check,
  ADD CONSTRAINT notification_events_event_type_check CHECK (event_type IN (
    'message_received','appointment_offered','appointment_changed','appointment_response',
    'appointment_reminder','care_plan_published','care_plan_draft','document_review',
    'document_processed','document_failed','document_reviewed','barrier_reported',
    'adr_review','adr_information_requested','safety_flag','med_reminder','obligation_reminder',
    'legacy_update','critical_result'));

CREATE FUNCTION private.capture_critical_result() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE v_document uuid; v_patient uuid;
BEGIN
 SELECT p.document_id, f.patient_id INTO v_document, v_patient
   FROM public.clinical_facts f JOIN public.source_provenances p ON p.id=NEW.provenance_id
  WHERE f.id=NEW.fact_id AND f.fact_type='lab_result' AND f.value->>'flag_meaning'='critical'
    AND f.review_state IN ('pending_review','approved') AND p.document_id IS NOT NULL;
 IF v_document IS NULL OR NOT EXISTS(
   SELECT 1 FROM public.documents d WHERE d.id=v_document AND d.patient_id=v_patient) THEN
   RETURN NEW;
 END IF;
 -- No test name or value in metadata: the clinician opens the document to see the result.
 PERFORM private.notification_capture('documents',v_document,v_patient,'critical_result',
   'safety','shared',NULL,'{}'::jsonb,'critical_result:'||v_document,clock_timestamp());
 RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION private.capture_critical_result() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION private.capture_critical_result() TO service_role;

CREATE TRIGGER critical_result_capture AFTER INSERT ON public.evidence_citations
  FOR EACH ROW EXECUTE FUNCTION private.capture_critical_result();

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

CREATE OR REPLACE FUNCTION private.email_preference(p_type text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path='' AS $$
SELECT CASE WHEN p_type='message_received' THEN 'messages'
 WHEN p_type IN ('appointment_offered','appointment_changed','appointment_response') THEN 'appointments'
 WHEN p_type='care_plan_published' THEN 'care_plans'
 WHEN p_type IN ('document_failed','adr_information_requested') THEN 'records'
 WHEN p_type IN ('document_review','care_plan_draft','critical_result') THEN 'reviews' END;
$$;
