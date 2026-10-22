-- PAT-002-C: the patient's own confirmed-symptom history and the clinician's structured
-- report detail with an audited, idempotent "mark reviewed".
--
-- Nothing here creates a second event store. Every event shown is read from a row the product
-- already writes: the confirmation (symptom_reports), the care-team hand-off audit row (071),
-- an urgent-answer alert (060/071) and, new in this migration, one review row. The browser
-- roles get no direct access; the backend calls one function that checks the actor itself.
--
--   1. symptom_report_reviews: one review per (report, care team). Each care-team link owns its
--      own follow-up (PLAN-002), so teams review independently; a repeat by the same team
--      returns that team's review. The patient sees every team's review.
--   2. The 071 hand-off now records how many active care-team links it reached, in the same
--      transaction. "Sent to your care team" is shown only when that number is above zero; a
--      confirmation with no active link is shown as not sent, and a report confirmed before
--      this migration (no count recorded) is shown as unrecorded rather than guessed.
--   3. private.symptom_report_card: the one shaped read used by the list, the detail and the
--      review result. Unconfirmed drafts are not reports and cannot be reached through it.
--   4. public.symptom_report_history(actor, role, action, payload): list / detail / review.
--      A patient reaches only their own reports; a clinician needs an active care-team link
--      (active clinic membership, active clinic) to the report's patient and reviews for a
--      link of their own, named when they hold several. Denial and "no such report" are the
--      same error so ids reveal nothing.

CREATE TABLE IF NOT EXISTS public.symptom_report_reviews (
  report_id    uuid NOT NULL REFERENCES public.symptom_reports(id),
  care_team_id uuid NOT NULL REFERENCES public.care_teams(id),
  patient_id   uuid NOT NULL REFERENCES public.patients(id),
  reviewed_by  uuid NOT NULL REFERENCES public.clinicians(id),
  reviewed_at  timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (report_id, care_team_id)
);
ALTER TABLE public.symptom_report_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.symptom_report_reviews FROM PUBLIC, anon, authenticated, service_role;

CREATE INDEX IF NOT EXISTS symptom_reports_confirmed_history
  ON public.symptom_reports (patient_id, confirmed_at DESC, id DESC)
  WHERE confirmation_state = 'patient_confirmed';
CREATE INDEX IF NOT EXISTS symptom_intake_audit_intake_action
  ON public.symptom_intake_audit (intake_id, action);

-- The clinician's active links (care team rows) to a patient, in a stable order.
CREATE OR REPLACE FUNCTION private.symptom_report_links(p_clinician_id uuid, p_patient_id uuid)
RETURNS uuid[] LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
  SELECT coalesce(array_agg(t.id ORDER BY t.id), ARRAY[]::uuid[]) FROM public.care_teams t
    JOIN public.clinic_memberships m ON m.clinician_id = t.clinician_id AND m.clinic_id = t.clinic_id
    JOIN public.clinics c ON c.id = t.clinic_id
   WHERE t.patient_id = p_patient_id AND t.clinician_id = p_clinician_id
     AND t.status = 'active' AND m.status = 'active' AND c.status = 'active';
$$;

-- The 071 hand-off, unchanged except that its audit row now says how many clinicians it reached.
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
      INSERT INTO public.clinician_messages(clinician_id,patient_id,channel,subject,body)
        VALUES(recipient.clinician_id,NEW.patient_id,'in_app',
          CASE WHEN report.severity>=8 THEN 'High-severity patient-confirmed symptom' ELSE 'Patient-confirmed symptom for review' END,
          'Patient confirmed: '||report.symptom||'. Severity: '||coalesce(report.severity::text||'/10','unknown')||
          '. Review the confirmed summary and patient-reported products. A cause has not been established.');
      reached := reached + 1;
    END LOOP;
    INSERT INTO public.symptom_intake_audit(intake_id,patient_id,actor_id,action,revision,evidence)
      VALUES(NEW.id,NEW.patient_id,NEW.patient_id,'review_handoff',NEW.revision,
        jsonb_build_object('report_id',report.id,'task_key','confirmed_symptom:'||report.id::text,
          'recipients',reached));
  END IF;
  RETURN NEW;
END; $$;

-- One report as the caller may see it. Staff get provenance and the safety outcome; the
-- patient gets their own answers and what happened next. Retrieval context is never included.
CREATE OR REPLACE FUNCTION private.symptom_report_card(
  r public.symptom_reports, p_staff boolean, p_detail boolean, p_viewer uuid DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  audit public.symptom_intake_audit;
  handoff_state text := 'unrecorded';
  reviews jsonb;
  alert public.symptom_intake_safety_alerts;
  viewer_links uuid[] := CASE WHEN p_viewer IS NULL THEN ARRAY[]::uuid[]
    ELSE private.symptom_report_links(p_viewer, r.patient_id) END;
  card jsonb;
BEGIN
  SELECT coalesce(jsonb_agg(jsonb_build_object(
      'care_team_id', v.care_team_id, 'team_label', v.label, 'reviewed_by_name', v.name,
      'reviewed_at', v.reviewed_at, 'mine', v.care_team_id = ANY (viewer_links))
      ORDER BY v.reviewed_at, v.care_team_id), '[]'::jsonb) INTO reviews
    FROM (SELECT rv.care_team_id, rv.reviewed_at,
                 concat_ws(' · ', nullif(btrim(coalesce(t.specialty_context, t.role)), ''), c.display_name) AS label,
                 btrim(cl.first_name || ' ' || cl.last_name) AS name
            FROM public.symptom_report_reviews rv
            JOIN public.care_teams t ON t.id = rv.care_team_id
            LEFT JOIN public.clinics c ON c.id = t.clinic_id
            LEFT JOIN public.clinicians cl ON cl.id = rv.reviewed_by
           WHERE rv.report_id = r.id) v;
  SELECT * INTO audit FROM public.symptom_intake_audit a
   WHERE a.intake_id = r.intake_id AND a.action = 'review_handoff' ORDER BY a.created_at LIMIT 1;
  IF FOUND AND audit.evidence ? 'recipients' THEN
    handoff_state := CASE WHEN (audit.evidence ->> 'recipients')::integer > 0 THEN 'sent' ELSE 'not_sent' END;
  END IF;
  SELECT * INTO alert FROM public.symptom_intake_safety_alerts s WHERE s.intake_id = r.intake_id
   ORDER BY (s.urgency = 'emergency') DESC, s.created_at LIMIT 1;

  card := jsonb_build_object(
    'id', r.id, 'symptom', r.symptom, 'severity', r.severity, 'onset', r.onset,
    'duration', r.duration, 'body_area', r.body_area, 'confirmed_at', r.confirmed_at,
    'locale', r.confirmed_content ->> 'locale', 'timezone', r.confirmed_content ->> 'timezone',
    'handoff_state', handoff_state,
    'handed_off_at', CASE WHEN handoff_state = 'sent' THEN audit.created_at END,
    'escalation', CASE WHEN alert.intake_id IS NULL THEN NULL ELSE jsonb_build_object(
      'urgency', alert.urgency, 'at', alert.created_at, 'delivery_state', alert.delivery_state) END,
    'reviews', reviews);
  IF p_detail THEN
    card := card || jsonb_build_object(
      'answers', COALESCE(r.confirmed_content -> 'answers', '{}'::jsonb),
      'summary', r.confirmed_content ->> 'summary');
  END IF;
  IF p_staff THEN
    card := card || jsonb_build_object(
      'patient_id', r.patient_id, 'flagged_for_adr', r.flagged_for_adr,
      'related_medication_name', r.related_medication_name,
      'viewer_care_team_ids', to_jsonb(viewer_links));
    IF p_detail THEN
      card := card || jsonb_build_object('provenance', jsonb_build_object(
        'report_id', r.id, 'intake_id', r.intake_id,
        'source_message_id', r.confirmed_content ->> 'source_message_id',
        'session_id', r.confirmed_content ->> 'session_id',
        'schema_version', r.report_schema_version,
        'library_version', r.confirmed_content ->> 'library_version',
        'submitted_status', r.submitted_status, 'confirmed_by', r.confirmed_by,
        'consent_recorded', EXISTS (SELECT 1 FROM public.symptom_intake_mutations m
          WHERE m.intake_id = r.intake_id AND m.action = 'confirm' AND m.request ->> 'consent' = 'true')),
        'safety', r.confirmed_content -> 'safety',
        'selection', r.confirmed_content -> 'selection');
    END IF;
  END IF;
  RETURN card;
END;
$$;

CREATE OR REPLACE FUNCTION public.symptom_report_history(
  p_actor_id uuid, p_actor_role text, p_action text, p_payload jsonb DEFAULT '{}'
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  r public.symptom_reports;
  links uuid[];
  team uuid;
  lim integer;
  items jsonb;
  total integer;
  inserted boolean := false;
  revision integer;
BEGIN
  IF p_actor_id IS NULL OR p_actor_role NOT IN ('patient', 'clinician')
     OR p_payload IS NULL OR jsonb_typeof(p_payload) <> 'object' OR octet_length(p_payload::text) > 2000 THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Report unavailable';
  END IF;

  IF p_action = 'list' THEN
    IF p_actor_role <> 'patient' THEN
      RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Report unavailable';
    END IF;
    lim := least(greatest(coalesce((p_payload ->> 'limit')::integer, 50), 1), 100);
    SELECT count(*) INTO total FROM (
      SELECT 1 FROM public.symptom_reports
       WHERE patient_id = p_actor_id AND confirmation_state = 'patient_confirmed' LIMIT lim + 1) x;
    SELECT coalesce(jsonb_agg(private.symptom_report_card(s, false, false)
             ORDER BY s.confirmed_at DESC, s.id DESC), '[]'::jsonb) INTO items
      FROM (SELECT * FROM public.symptom_reports
             WHERE patient_id = p_actor_id AND confirmation_state = 'patient_confirmed'
             ORDER BY confirmed_at DESC, id DESC LIMIT lim) s;
    RETURN jsonb_build_object('items', items, 'has_more', total > lim);
  END IF;

  IF p_action NOT IN ('detail', 'review') THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid report operation';
  END IF;
  SELECT * INTO r FROM public.symptom_reports
   WHERE id = (p_payload ->> 'report_id')::uuid AND confirmation_state = 'patient_confirmed';
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Report unavailable';
  END IF;

  IF p_actor_role = 'patient' THEN
    IF p_action <> 'detail' OR r.patient_id <> p_actor_id THEN
      RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Report unavailable';
    END IF;
    RETURN private.symptom_report_card(r, false, true);
  END IF;

  links := private.symptom_report_links(p_actor_id, r.patient_id);
  IF cardinality(links) = 0
     OR (p_payload ? 'patient_id' AND (p_payload ->> 'patient_id')::uuid <> r.patient_id) THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Report unavailable';
  END IF;
  IF p_action = 'detail' THEN
    RETURN private.symptom_report_card(r, true, true, p_actor_id);
  END IF;

  -- Review: for one of the caller's own links, named when they hold several.
  IF nullif(p_payload ->> 'care_team_id', '') IS NOT NULL THEN
    team := (p_payload ->> 'care_team_id')::uuid;
    IF NOT team = ANY (links) THEN
      RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Report unavailable';
    END IF;
  ELSIF cardinality(links) = 1 THEN
    team := links[1];
  ELSE
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'CARE_TEAM_REQUIRED';
  END IF;
  -- The primary key makes concurrent attempts for one team converge on one row and one audit event.
  INSERT INTO public.symptom_report_reviews (report_id, care_team_id, patient_id, reviewed_by)
    VALUES (r.id, team, r.patient_id, p_actor_id)
    ON CONFLICT (report_id, care_team_id) DO NOTHING;
  inserted := FOUND;
  IF inserted THEN
    SELECT i.revision INTO revision FROM public.symptom_intakes i WHERE i.id = r.intake_id;
    INSERT INTO public.symptom_intake_audit (intake_id, patient_id, actor_id, action, revision, evidence)
      VALUES (r.intake_id, r.patient_id, p_actor_id, 'clinician_reviewed', coalesce(revision, 0),
              jsonb_build_object('report_id', r.id, 'care_team_id', team));
  END IF;
  RETURN private.symptom_report_card(r, true, true, p_actor_id)
    || jsonb_build_object('already_reviewed', NOT inserted, 'acting_care_team_id', team);
END;
$$;

REVOKE ALL ON FUNCTION private.symptom_report_links(uuid, uuid), private.symptom_report_card(public.symptom_reports, boolean, boolean, uuid)
  FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.symptom_report_history(uuid, text, text, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.symptom_report_history(uuid, text, text, jsonb) TO service_role;

DO $$
BEGIN
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.symptom_report_reviews'::regclass) THEN
    RAISE EXCEPTION 'symptom_report_reviews must have RLS enabled';
  END IF;
  IF pg_catalog.has_table_privilege('anon', 'public.symptom_report_reviews', 'SELECT,INSERT,UPDATE,DELETE')
     OR pg_catalog.has_table_privilege('authenticated', 'public.symptom_report_reviews', 'SELECT,INSERT,UPDATE,DELETE') THEN
    RAISE EXCEPTION 'Browser roles must have no access to symptom_report_reviews';
  END IF;
  IF pg_catalog.has_function_privilege('anon', 'public.symptom_report_history(uuid,text,text,jsonb)', 'EXECUTE')
     OR pg_catalog.has_function_privilege('authenticated', 'public.symptom_report_history(uuid,text,text,jsonb)', 'EXECUTE')
     OR NOT pg_catalog.has_function_privilege('service_role', 'public.symptom_report_history(uuid,text,text,jsonb)', 'EXECUTE') THEN
    RAISE EXCEPTION 'symptom_report_history must be callable only by the backend';
  END IF;
  IF pg_catalog.has_function_privilege('authenticated', 'private.symptom_report_card(public.symptom_reports,boolean,boolean,uuid)', 'EXECUTE')
     OR pg_catalog.has_function_privilege('anon', 'private.symptom_report_links(uuid,uuid)', 'EXECUTE') THEN
    RAISE EXCEPTION 'Private report helpers must not be browser-callable';
  END IF;
END $$;
