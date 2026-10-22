-- PAT-002-C: the patient's own confirmed-symptom history and the clinician's structured
-- report detail with an audited, idempotent "mark reviewed".
--
-- Nothing here creates a second event store. Every event shown is read from a row the product
-- already writes: the confirmation (symptom_reports), the care-team hand-off audit row (071),
-- an urgent-answer alert (060/071) and, new in this migration, one review row. The browser
-- roles get no direct access; the backend calls one function that checks the actor itself.
--
--   1. symptom_report_reviews: at most one review per confirmed report. A confirmed symptom is
--      shared safety information (PLAN-002), so the first assigned clinician who reviews it
--      records the review for the whole care team; a later attempt returns that same review.
--   2. private.symptom_report_card: the one shaped read used by the list, the detail and the
--      review result. Unconfirmed drafts are not reports and cannot be reached through it.
--   3. public.symptom_report_history(actor, role, action, payload): list / detail / review.
--      A patient reaches only their own reports; a clinician needs an active care-team link
--      (active clinic membership, active clinic) to the report's patient. Denial and "no such
--      report" are the same error so ids reveal nothing.

CREATE TABLE IF NOT EXISTS public.symptom_report_reviews (
  report_id    uuid PRIMARY KEY REFERENCES public.symptom_reports(id),
  patient_id   uuid NOT NULL REFERENCES public.patients(id),
  reviewed_by  uuid NOT NULL REFERENCES public.clinicians(id),
  care_team_id uuid REFERENCES public.care_teams(id) ON DELETE SET NULL,
  reviewed_at  timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE public.symptom_report_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.symptom_report_reviews FROM PUBLIC, anon, authenticated, service_role;

CREATE INDEX IF NOT EXISTS symptom_reports_confirmed_history
  ON public.symptom_reports (patient_id, confirmed_at DESC, id DESC)
  WHERE confirmation_state = 'patient_confirmed';
CREATE INDEX IF NOT EXISTS symptom_intake_audit_intake_action
  ON public.symptom_intake_audit (intake_id, action);

-- The clinician's active link (care team row) to a patient, or NULL.
CREATE OR REPLACE FUNCTION private.symptom_report_link(p_clinician_id uuid, p_patient_id uuid)
RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
  SELECT t.id FROM public.care_teams t
    JOIN public.clinic_memberships m ON m.clinician_id = t.clinician_id AND m.clinic_id = t.clinic_id
    JOIN public.clinics c ON c.id = t.clinic_id
   WHERE t.patient_id = p_patient_id AND t.clinician_id = p_clinician_id
     AND t.status = 'active' AND m.status = 'active' AND c.status = 'active'
   ORDER BY t.id LIMIT 1;
$$;

-- One report as the caller may see it. Staff get provenance and the safety outcome; the
-- patient gets her own answers and what happened next. Retrieval context is never included.
CREATE OR REPLACE FUNCTION private.symptom_report_card(
  r public.symptom_reports, p_staff boolean, p_detail boolean
) RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  review public.symptom_report_reviews;
  reviewer_name text;
  handoff timestamptz;
  alert public.symptom_intake_safety_alerts;
  card jsonb;
BEGIN
  SELECT * INTO review FROM public.symptom_report_reviews WHERE report_id = r.id;
  IF FOUND THEN
    SELECT btrim(c.first_name || ' ' || c.last_name) INTO reviewer_name
      FROM public.clinicians c WHERE c.id = review.reviewed_by;
  END IF;
  SELECT min(a.created_at) INTO handoff FROM public.symptom_intake_audit a
   WHERE a.intake_id = r.intake_id AND a.action = 'review_handoff';
  SELECT * INTO alert FROM public.symptom_intake_safety_alerts s WHERE s.intake_id = r.intake_id
   ORDER BY (s.urgency = 'emergency') DESC, s.created_at LIMIT 1;

  card := jsonb_build_object(
    'id', r.id, 'symptom', r.symptom, 'severity', r.severity, 'onset', r.onset,
    'duration', r.duration, 'body_area', r.body_area, 'confirmed_at', r.confirmed_at,
    'locale', r.confirmed_content ->> 'locale', 'timezone', r.confirmed_content ->> 'timezone',
    'handed_off_at', handoff,
    'escalation', CASE WHEN alert.intake_id IS NULL THEN NULL ELSE jsonb_build_object(
      'urgency', alert.urgency, 'at', alert.created_at, 'delivery_state', alert.delivery_state) END,
    'review', CASE WHEN review.report_id IS NULL THEN NULL ELSE jsonb_build_object(
      'reviewed_at', review.reviewed_at, 'reviewed_by_name', reviewer_name) END);
  IF p_detail THEN
    card := card || jsonb_build_object(
      'answers', COALESCE(r.confirmed_content -> 'answers', '{}'::jsonb),
      'summary', r.confirmed_content ->> 'summary');
  END IF;
  IF p_staff THEN
    card := card || jsonb_build_object(
      'patient_id', r.patient_id, 'flagged_for_adr', r.flagged_for_adr,
      'related_medication_name', r.related_medication_name,
      'review_detail', CASE WHEN review.report_id IS NULL THEN NULL ELSE jsonb_build_object(
        'reviewed_by', review.reviewed_by, 'care_team_id', review.care_team_id) END);
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
  review public.symptom_report_reviews;
  link uuid;
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

  link := private.symptom_report_link(p_actor_id, r.patient_id);
  IF link IS NULL OR (p_payload ? 'patient_id' AND (p_payload ->> 'patient_id')::uuid <> r.patient_id) THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Report unavailable';
  END IF;
  IF p_action = 'detail' THEN
    RETURN private.symptom_report_card(r, true, true);
  END IF;

  -- Review: the primary key makes concurrent attempts converge on one row and one audit event.
  INSERT INTO public.symptom_report_reviews (report_id, patient_id, reviewed_by, care_team_id)
    VALUES (r.id, r.patient_id, p_actor_id, link)
    ON CONFLICT (report_id) DO NOTHING
    RETURNING * INTO review;
  inserted := FOUND;
  IF inserted THEN
    SELECT i.revision INTO revision FROM public.symptom_intakes i WHERE i.id = r.intake_id;
    INSERT INTO public.symptom_intake_audit (intake_id, patient_id, actor_id, action, revision, evidence)
      VALUES (r.intake_id, r.patient_id, p_actor_id, 'clinician_reviewed', coalesce(revision, 0),
              jsonb_build_object('report_id', r.id, 'care_team_id', link));
  END IF;
  RETURN private.symptom_report_card(r, true, true) || jsonb_build_object('already_reviewed', NOT inserted);
END;
$$;

REVOKE ALL ON FUNCTION private.symptom_report_link(uuid, uuid), private.symptom_report_card(public.symptom_reports, boolean, boolean)
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
  IF pg_catalog.has_function_privilege('authenticated', 'private.symptom_report_card(public.symptom_reports,boolean,boolean)', 'EXECUTE')
     OR pg_catalog.has_function_privilege('anon', 'private.symptom_report_link(uuid,uuid)', 'EXECUTE') THEN
    RAISE EXCEPTION 'Private report helpers must not be browser-callable';
  END IF;
END $$;
