-- PLAN-002 / CLN-003 follow-up: reviewed ADR work and MedWatch drafts always have an owner,
-- and care-team work items reach the notification centre.
--
--   1. The ADR review and MedWatch draft functions take the acting care team and write the
--      owner in the SAME transaction as the review (they wrap the existing bodies, which are
--      moved to the private schema unchanged). A clinician with several links to the patient
--      must name one; a review by a clinician with no link is refused. A deferred constraint
--      trigger makes it impossible to commit a new review or draft without an owner, whatever
--      path wrote it. The Python second write is gone.
--   2. Rows that already have a reviewer but no owner (written before ownership, or in the
--      window between the old two statements) are assigned only when unambiguous. Otherwise
--      they stay unassigned: visible to no clinician, with a review item for the patient's
--      active care teams. `assign_clinical_record_owner` lets exactly one of them take it.
--   3. Care-plan review items addressed to a care team become notification-centre items for
--      that team's clinician (write-time capture, the same pipeline as every other source).
--      An item addressed to a clinic's admins carries no patient and stays on the review-item
--      endpoint: a centre item always names its patient.
--
-- New objects revoke the browser roles explicitly; the final block fails the migration if a
-- grant, policy or function lost its check.

-- ── 1. Review-item kind for records with no owner ────────────────────────────────────────

ALTER TABLE public.care_plan_review_items DROP CONSTRAINT care_plan_review_items_kind_check;
ALTER TABLE public.care_plan_review_items ADD CONSTRAINT care_plan_review_items_kind_check
  CHECK (kind IN (
    'unassigned_legacy_plan', 'unowned_plan', 'cross_plan_conflict', 'conflict_acknowledged',
    'conflict_published_without', 'conflict_reply', 'unowned_clinical_record'));

-- ── 2. The acting care team: named, or the only one, or refused ──────────────────────────

CREATE FUNCTION private.resolve_acting_team(
  p_actor_id uuid, p_patient_id uuid, p_requested uuid
) RETURNS uuid LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE v_links uuid[] := private.clinician_patient_links(p_actor_id, p_patient_id);
BEGIN
  IF cardinality(v_links) = 0 THEN
    RAISE EXCEPTION 'Clinician is not assigned to this patient' USING ERRCODE = '42501';
  END IF;
  IF p_requested IS NOT NULL THEN
    IF NOT (p_requested = ANY (v_links)) THEN
      RAISE EXCEPTION 'Clinician is not assigned to this patient' USING ERRCODE = '42501';
    END IF;
    RETURN p_requested;
  END IF;
  IF cardinality(v_links) = 1 THEN RETURN v_links[1]; END IF;
  RAISE EXCEPTION 'CARE_TEAM_REQUIRED: choose the care team for this record'
    USING ERRCODE = '22023', HINT = 'CARE_TEAM_REQUIRED';
END;
$$;

-- ── 3. ADR review: the existing body, then the owner, in one transaction ─────────────────

ALTER FUNCTION public.review_adr_assessment(uuid, uuid, text, text, jsonb) SET SCHEMA private;

CREATE FUNCTION public.review_adr_assessment(
  p_assessment_id uuid, p_actor_id uuid, p_action text, p_note text DEFAULT NULL,
  p_requested_information jsonb DEFAULT '[]'::jsonb, p_care_team_id uuid DEFAULT NULL
) RETURNS SETOF public.adr_assessments
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_assessment public.adr_assessments%ROWTYPE;
  v_team uuid;
BEGIN
  SELECT * INTO v_assessment FROM public.adr_assessments WHERE id = p_assessment_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'ADR assessment not found' USING ERRCODE = 'P0002';
  END IF;
  v_team := private.resolve_acting_team(p_actor_id, v_assessment.patient_id, p_care_team_id);
  -- Once a team has taken the assessment up, only that team continues it.
  IF v_assessment.reviewed_by IS NOT NULL
     AND v_assessment.reviewed_by_care_team_id IS DISTINCT FROM v_team THEN
    RAISE EXCEPTION 'ADR assessment unavailable' USING ERRCODE = '42501';
  END IF;
  PERFORM 1 FROM private.review_adr_assessment(p_assessment_id, p_actor_id, p_action, p_note,
    p_requested_information);
  UPDATE public.adr_assessments SET reviewed_by_care_team_id = v_team
    WHERE id = p_assessment_id AND reviewed_by = p_actor_id;
  RETURN QUERY SELECT * FROM public.adr_assessments WHERE id = p_assessment_id;
END;
$$;

-- ── 4. MedWatch draft creation: the same ─────────────────────────────────────────────────

ALTER FUNCTION public.create_medwatch_draft(uuid, uuid, jsonb, jsonb, text, uuid) SET SCHEMA private;

CREATE FUNCTION public.create_medwatch_draft(
  p_assessment_id uuid, p_actor_id uuid, p_form_data jsonb, p_source_evidence jsonb,
  p_reportability_rationale text, p_draft_id uuid, p_care_team_id uuid DEFAULT NULL
) RETURNS SETOF public.medwatch_drafts
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_assessment public.adr_assessments%ROWTYPE;
  v_team uuid;
BEGIN
  SELECT * INTO v_assessment FROM public.adr_assessments WHERE id = p_assessment_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'ADR assessment not found' USING ERRCODE = 'P0002';
  END IF;
  v_team := private.resolve_acting_team(p_actor_id, v_assessment.patient_id, p_care_team_id);
  IF v_assessment.reviewed_by IS NOT NULL
     AND v_assessment.reviewed_by_care_team_id IS DISTINCT FROM v_team THEN
    RAISE EXCEPTION 'ADR assessment unavailable' USING ERRCODE = '42501';
  END IF;
  PERFORM 1 FROM private.create_medwatch_draft(p_assessment_id, p_actor_id, p_form_data,
    p_source_evidence, p_reportability_rationale, p_draft_id);
  UPDATE public.medwatch_drafts SET care_team_id = v_team WHERE id = p_draft_id;
  UPDATE public.adr_assessments SET reviewed_by_care_team_id = v_team
    WHERE id = p_assessment_id AND reviewed_by = p_actor_id;
  RETURN QUERY SELECT * FROM public.medwatch_drafts WHERE id = p_draft_id;
END;
$$;

-- ── 5. No new review or draft commits without an owner, whatever path wrote it ───────────
-- Deferred to the end of the transaction so the wrappers above can write the owner after the
-- unchanged inner body. Rows that were already reviewed are not rechecked unless their
-- review changes.

CREATE FUNCTION private.require_clinical_record_owner() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_reviewed uuid;
  v_team uuid;
BEGIN
  IF COALESCE(current_setting('mediagent.record_owner_backfill', true), '') = '1' THEN
    RETURN NULL;
  END IF;
  -- A deferred trigger sees the row as it was when the event was queued; the owner is
  -- written later in the same transaction, so judge the row as it stands at commit.
  IF TG_TABLE_NAME = 'adr_assessments' THEN
    IF NOT (TG_OP = 'INSERT' OR OLD.reviewed_by IS DISTINCT FROM NEW.reviewed_by
        OR OLD.reviewed_at IS DISTINCT FROM NEW.reviewed_at
        OR OLD.last_review_action IS DISTINCT FROM NEW.last_review_action) THEN
      RETURN NULL;
    END IF;
    SELECT reviewed_by, reviewed_by_care_team_id INTO v_reviewed, v_team
      FROM public.adr_assessments WHERE id = NEW.id;
    IF v_reviewed IS NOT NULL AND v_team IS NULL THEN
      RAISE EXCEPTION 'a reviewed ADR assessment needs its care team' USING ERRCODE = '23514';
    END IF;
  ELSE
    SELECT care_team_id INTO v_team FROM public.medwatch_drafts WHERE id = NEW.id;
    IF FOUND AND v_team IS NULL THEN
      RAISE EXCEPTION 'a MedWatch draft needs its care team' USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER adr_assessments_require_owner
  AFTER INSERT OR UPDATE OF reviewed_by, reviewed_at, last_review_action, reviewed_by_care_team_id
  ON public.adr_assessments DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION private.require_clinical_record_owner();
CREATE CONSTRAINT TRIGGER medwatch_drafts_require_owner
  AFTER INSERT ON public.medwatch_drafts DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION private.require_clinical_record_owner();

-- ── 6. Backfill: assign only what is unambiguous; surface the rest, never guess ──────────

DO $backfill$
DECLARE
  v_row record;
  v_team uuid;
  v_count integer;
  v_target uuid;
BEGIN
  PERFORM set_config('mediagent.record_owner_backfill', '1', true);
  -- ADR assessments reviewed by a clinician with exactly one link to the patient.
  UPDATE public.adr_assessments a SET reviewed_by_care_team_id = (
    SELECT t.id FROM public.care_teams t
     WHERE t.patient_id = a.patient_id AND t.clinician_id = a.reviewed_by)
   WHERE a.reviewed_by IS NOT NULL AND a.reviewed_by_care_team_id IS NULL
     AND (SELECT count(*) FROM public.care_teams t
       WHERE t.patient_id = a.patient_id AND t.clinician_id = a.reviewed_by) = 1;
  -- MedWatch drafts follow their assessment, else their creator's only link.
  UPDATE public.medwatch_drafts m SET care_team_id = a.reviewed_by_care_team_id
    FROM public.adr_assessments a
   WHERE a.id = m.adr_assessment_id AND m.care_team_id IS NULL
     AND a.reviewed_by_care_team_id IS NOT NULL;
  UPDATE public.medwatch_drafts m SET care_team_id = (
    SELECT t.id FROM public.care_teams t
     WHERE t.patient_id = m.patient_id AND t.clinician_id = m.created_by)
   WHERE m.care_team_id IS NULL AND m.created_by IS NOT NULL
     AND (SELECT count(*) FROM public.care_teams t
       WHERE t.patient_id = m.patient_id AND t.clinician_id = m.created_by) = 1;
  -- What is still unowned: visible to no clinician, and every active team is asked.
  FOR v_row IN
    SELECT 'adr_assessment'::text AS record, a.id, a.patient_id FROM public.adr_assessments a
     WHERE a.reviewed_by IS NOT NULL AND a.reviewed_by_care_team_id IS NULL
    UNION ALL
    SELECT 'medwatch_draft', m.id, m.patient_id FROM public.medwatch_drafts m
     WHERE m.care_team_id IS NULL
  LOOP
    FOR v_target IN SELECT t.id FROM public.care_teams t
      WHERE t.patient_id = v_row.patient_id AND t.status = 'active' ORDER BY t.id
    LOOP
      INSERT INTO public.care_plan_review_items(patient_id, kind, target_care_team_id, summary)
      VALUES (v_row.patient_id, 'unowned_clinical_record', v_target,
        jsonb_build_object('record', v_row.record, 'record_id', v_row.id))
      ON CONFLICT DO NOTHING;
    END LOOP;
  END LOOP;
END;
$backfill$;

-- One team takes an unowned record; exactly one caller can.
CREATE FUNCTION public.assign_clinical_record_owner(
  p_record text, p_record_id uuid, p_actor_id uuid, p_care_team_id uuid
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_patient uuid;
  v_assessment public.adr_assessments%ROWTYPE;
  v_draft public.medwatch_drafts%ROWTYPE;
BEGIN
  IF p_record NOT IN ('adr_assessment', 'medwatch_draft') THEN
    RAISE EXCEPTION 'unsupported record' USING ERRCODE = '22023';
  END IF;
  IF p_record = 'adr_assessment' THEN
    SELECT patient_id INTO v_patient FROM public.adr_assessments WHERE id = p_record_id;
  ELSE
    SELECT patient_id INTO v_patient FROM public.medwatch_drafts WHERE id = p_record_id;
  END IF;
  IF v_patient IS NULL OR NOT private.clinician_holds_link(p_actor_id, p_care_team_id)
     OR NOT EXISTS (SELECT 1 FROM public.care_teams WHERE id = p_care_team_id
       AND patient_id = v_patient) THEN
    RAISE EXCEPTION 'record unavailable' USING ERRCODE = '42501';
  END IF;
  PERFORM private.lock_care_plan_evidence(v_patient, true);
  IF p_record = 'adr_assessment' THEN
    SELECT * INTO v_assessment FROM public.adr_assessments WHERE id = p_record_id FOR UPDATE;
    IF v_assessment.reviewed_by_care_team_id IS NOT NULL THEN
      IF v_assessment.reviewed_by_care_team_id = p_care_team_id THEN
        RETURN jsonb_build_object('record', p_record, 'care_team_id', p_care_team_id,
          'replayed', true);
      END IF;
      RAISE EXCEPTION 'record was taken by someone else' USING ERRCODE = '40001';
    END IF;
    UPDATE public.adr_assessments SET reviewed_by_care_team_id = p_care_team_id
      WHERE id = p_record_id;
  ELSE
    SELECT * INTO v_draft FROM public.medwatch_drafts WHERE id = p_record_id FOR UPDATE;
    IF v_draft.care_team_id IS NOT NULL THEN
      IF v_draft.care_team_id = p_care_team_id THEN
        RETURN jsonb_build_object('record', p_record, 'care_team_id', p_care_team_id,
          'replayed', true);
      END IF;
      RAISE EXCEPTION 'record was taken by someone else' USING ERRCODE = '40001';
    END IF;
    UPDATE public.medwatch_drafts SET care_team_id = p_care_team_id WHERE id = p_record_id;
  END IF;
  UPDATE public.care_plan_review_items
     SET status = 'resolved', resolved_by = p_actor_id, resolved_at = clock_timestamp()
   WHERE kind = 'unowned_clinical_record' AND status = 'open'
     AND summary->>'record_id' = p_record_id::text;
  PERFORM private.log_plan_ownership(v_patient, NULL, p_care_team_id, p_actor_id,
    'clinical_record_assigned', jsonb_build_object('record', p_record, 'record_id', p_record_id));
  RETURN jsonb_build_object('record', p_record, 'care_team_id', p_care_team_id, 'replayed', false);
END;
$$;

-- ── 7. Direct sessions: an unowned reviewed record is visible to nobody ──────────────────

ALTER POLICY adr_clinician_select ON public.adr_assessments USING (
  private.is_clinician() AND private.is_assigned_clinician(patient_id)
  AND (reviewed_by IS NULL OR reviewed_by_care_team_id = ANY (private.rls_links(patient_id))));
ALTER POLICY adr_clinician_update ON public.adr_assessments USING (
  private.is_clinician() AND private.is_assigned_clinician(patient_id)
  AND (reviewed_by IS NULL OR reviewed_by_care_team_id = ANY (private.rls_links(patient_id))));
ALTER POLICY medwatch_clinician_select ON public.medwatch_drafts USING (
  private.is_clinician() AND private.is_assigned_clinician(patient_id)
  AND care_team_id = ANY (private.rls_links(patient_id)));
ALTER POLICY medwatch_audit_clinician_select ON public.medwatch_draft_audit_events USING (EXISTS (
  SELECT 1 FROM public.medwatch_drafts draft
  WHERE draft.id = medwatch_draft_audit_events.medwatch_draft_id AND private.is_clinician()
    AND private.is_assigned_clinician(draft.patient_id)
    AND draft.care_team_id = ANY (private.rls_links(draft.patient_id))));
ALTER POLICY medwatch_submissions_clinician_select ON public.medwatch_external_submissions USING (
  private.is_clinician() AND private.is_assigned_clinician(patient_id)
  AND EXISTS (SELECT 1 FROM public.medwatch_drafts draft
    WHERE draft.id = medwatch_external_submissions.medwatch_draft_id
      AND draft.care_team_id = ANY (private.rls_links(draft.patient_id))));

-- ── 8. Care-team work items reach the notification centre ────────────────────────────────

ALTER TABLE public.notification_events
  DROP CONSTRAINT notification_events_event_type_check,
  ADD CONSTRAINT notification_events_event_type_check CHECK (event_type IN (
    'message_received','appointment_offered','appointment_changed','appointment_response',
    'appointment_reminder','care_plan_published','care_plan_draft','document_review',
    'document_processed','document_failed','document_reviewed','barrier_reported',
    'adr_review','adr_information_requested','safety_flag','med_reminder','obligation_reminder',
    'legacy_update','critical_result','adr_information_answered','care_plan_review')),
  DROP CONSTRAINT notification_events_source_type_check,
  ADD CONSTRAINT notification_events_source_type_check CHECK (source_type IN (
    'care_conversation_messages','appointments','notifications','care_plan_versions','documents',
    'adherence_logs','adr_assessments','clinician_messages','adr_information_requests',
    'symptom_reports','care_plan_review_items'));

CREATE OR REPLACE FUNCTION private.notification_source(p_type text,p_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v jsonb;
BEGIN
  IF p_type NOT IN ('care_conversation_messages','appointments','notifications',
    'care_plan_versions','documents','adherence_logs','adr_assessments','clinician_messages',
    'adr_information_requests','symptom_reports','care_plan_review_items') THEN RETURN NULL; END IF;
  EXECUTE format('SELECT to_jsonb(s) FROM public.%I s WHERE id=$1',p_type) INTO v USING p_id;
  RETURN v;
END;
$$;

-- Open care-team work items are actionable until resolved.
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

-- Ownership of a notification source. As 086, without the reviewer fallback (an unowned
-- reviewed record is visible to nobody) and with care-team work items.
CREATE OR REPLACE FUNCTION private.notification_owner_sees(
  p_type text, p_id uuid, p_kind text, p_actor uuid, p_patient uuid
) RETURNS boolean LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_links uuid[];
BEGIN
  IF p_kind = 'critical_result'
     OR p_type NOT IN ('documents', 'care_plan_versions', 'adr_assessments', 'adr_information_requests',
       'care_plan_review_items')
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
      AND (a.reviewed_by IS NULL OR a.reviewed_by_care_team_id = ANY (v_links)));
  ELSIF p_type = 'care_plan_review_items' THEN
    RETURN EXISTS (SELECT 1 FROM public.care_plan_review_items i WHERE i.id = p_id
      AND i.patient_id = p_patient AND i.target_care_team_id = ANY (v_links));
  END IF;
  RETURN EXISTS (SELECT 1 FROM public.adr_information_requests r
    JOIN public.adr_assessments a ON a.id = r.adr_assessment_id
    WHERE r.id = p_id AND r.patient_id = p_patient AND a.patient_id = p_patient
      AND (a.reviewed_by IS NULL OR a.reviewed_by_care_team_id = ANY (v_links)));
END;
$$;

-- Capture a new care-team work item for the clinician of the team it is addressed to. The
-- event names the review kind and plan, never conflict wording, notes or activities.
CREATE FUNCTION private.capture_care_plan_review_item() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_recipient uuid;
BEGIN
  IF NEW.target_care_team_id IS NULL OR NEW.status <> 'open' THEN RETURN NEW; END IF;
  SELECT clinician_id INTO v_recipient FROM public.care_teams
    WHERE id = NEW.target_care_team_id AND status = 'active' AND patient_id = NEW.patient_id;
  IF v_recipient IS NULL THEN RETURN NEW; END IF;
  PERFORM private.notification_capture('care_plan_review_items', NEW.id, NEW.patient_id,
    'care_plan_review', 'care_plans', 'clinician', v_recipient,
    jsonb_build_object('review_kind', NEW.kind, 'care_plan_id', NEW.care_plan_id),
    'care_plan_review_items:' || NEW.id::text, NEW.created_at);
  RETURN NEW;
END;
$$;
CREATE TRIGGER care_plan_review_item_notification
  AFTER INSERT ON public.care_plan_review_items
  FOR EACH ROW EXECUTE FUNCTION private.capture_care_plan_review_item();

-- Items that were already open when this migration ran (from the ownership backfill).
INSERT INTO public.notification_events(event_key, event_type, category, source_type, source_id,
  patient_id, audience, recipient_id, metadata, created_at)
SELECT 'care_plan_review_items:' || i.id::text, 'care_plan_review', 'care_plans',
  'care_plan_review_items', i.id, i.patient_id, 'clinician', t.clinician_id,
  jsonb_build_object('review_kind', i.kind, 'care_plan_id', i.care_plan_id), i.created_at
FROM public.care_plan_review_items i
JOIN public.care_teams t ON t.id = i.target_care_team_id AND t.status = 'active'
  AND t.patient_id = i.patient_id
WHERE i.status = 'open'
ON CONFLICT (event_key) DO NOTHING;
INSERT INTO public.notification_pending_deliveries(event_id, recipient_id, recipient_role)
SELECT e.id, e.recipient_id, 'clinician' FROM public.notification_events e
WHERE e.source_type = 'care_plan_review_items' AND e.recipient_id IS NOT NULL
ON CONFLICT DO NOTHING;

-- ── 9. Grants and verification ───────────────────────────────────────────────────────────

REVOKE ALL ON FUNCTION
  private.resolve_acting_team(uuid, uuid, uuid),
  private.review_adr_assessment(uuid, uuid, text, text, jsonb),
  private.create_medwatch_draft(uuid, uuid, jsonb, jsonb, text, uuid),
  private.require_clinical_record_owner(), private.capture_care_plan_review_item(),
  private.notification_source(text, uuid), private.notification_actionable(public.notification_events, text),
  private.notification_owner_sees(text, uuid, text, uuid, uuid),
  public.review_adr_assessment(uuid, uuid, text, text, jsonb, uuid),
  public.create_medwatch_draft(uuid, uuid, jsonb, jsonb, text, uuid, uuid),
  public.assign_clinical_record_owner(text, uuid, uuid, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION
  private.resolve_acting_team(uuid, uuid, uuid),
  private.review_adr_assessment(uuid, uuid, text, text, jsonb),
  private.create_medwatch_draft(uuid, uuid, jsonb, jsonb, text, uuid),
  private.require_clinical_record_owner(), private.capture_care_plan_review_item(),
  private.notification_source(text, uuid), private.notification_actionable(public.notification_events, text),
  private.notification_owner_sees(text, uuid, text, uuid, uuid),
  public.review_adr_assessment(uuid, uuid, text, text, jsonb, uuid),
  public.create_medwatch_draft(uuid, uuid, jsonb, jsonb, text, uuid, uuid),
  public.assign_clinical_record_owner(text, uuid, uuid, uuid)
  TO service_role;

DO $verify$
DECLARE v_function text;
BEGIN
  FOREACH v_function IN ARRAY ARRAY[
    'public.review_adr_assessment(uuid,uuid,text,text,jsonb,uuid)',
    'public.create_medwatch_draft(uuid,uuid,jsonb,jsonb,text,uuid,uuid)',
    'public.assign_clinical_record_owner(text,uuid,uuid,uuid)',
    'private.review_adr_assessment(uuid,uuid,text,text,jsonb)',
    'private.create_medwatch_draft(uuid,uuid,jsonb,jsonb,text,uuid)'] LOOP
    IF has_function_privilege('anon', v_function, 'EXECUTE')
       OR has_function_privilege('authenticated', v_function, 'EXECUTE')
       OR NOT has_function_privilege('service_role', v_function, 'EXECUTE') THEN
      RAISE EXCEPTION '087: wrong execute grants on %', v_function;
    END IF;
  END LOOP;
  -- The old unwrapped signatures must be gone from the Data API schema.
  IF to_regprocedure('public.review_adr_assessment(uuid,uuid,text,text,jsonb)') IS NOT NULL
     OR to_regprocedure('public.create_medwatch_draft(uuid,uuid,jsonb,jsonb,text,uuid)') IS NOT NULL THEN
    RAISE EXCEPTION '087: an ownerless review function is still callable';
  END IF;
  IF (SELECT count(*) FROM pg_trigger WHERE tgname IN
      ('adr_assessments_require_owner', 'medwatch_drafts_require_owner')
      AND tgdeferrable AND tginitdeferred) <> 2 THEN
    RAISE EXCEPTION '087: the owner constraint triggers are missing';
  END IF;
  IF EXISTS (SELECT 1 FROM public.adr_assessments WHERE reviewed_by IS NOT NULL
      AND reviewed_by_care_team_id IS NULL
      AND NOT EXISTS (SELECT 1 FROM public.care_plan_review_items i
        WHERE i.kind = 'unowned_clinical_record' AND i.summary->>'record_id' = adr_assessments.id::text)
      AND EXISTS (SELECT 1 FROM public.care_teams t WHERE t.patient_id = adr_assessments.patient_id
        AND t.status = 'active')) THEN
    RAISE EXCEPTION '087: an unowned reviewed assessment has no review item';
  END IF;
END;
$verify$;
