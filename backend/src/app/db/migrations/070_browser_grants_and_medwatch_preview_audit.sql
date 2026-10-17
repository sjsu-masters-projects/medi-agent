-- 070: close two browser-role gaps found by the hosted-default-grants harness, and audit the
-- MedWatch PDF preview as a view (never an export).
--
--   1. public.clinics and public.cron_job_runs were created without row level security. Hosted
--      Supabase grants anon and authenticated every privilege on a new public table by default,
--      so with the public API key either table could be read or written directly. Both are
--      backend-only (service role): enable RLS with no browser policy and revoke the browser
--      roles' privileges. The service role is not changed.
--   2. record_medwatch_draft_preview_viewed writes one 'preview_viewed' audit row with the
--      actor. It changes no draft state and creates no export record.
--
-- Idempotent and additive: no data is rewritten.

-- 1. Backend-only tables --------------------------------------------------------------------
ALTER TABLE public.clinics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cron_job_runs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.clinics FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.cron_job_runs FROM PUBLIC, anon, authenticated;

-- 2. MedWatch preview audit -----------------------------------------------------------------
ALTER TABLE public.medwatch_draft_audit_events
  DROP CONSTRAINT medwatch_draft_audit_events_event_type_check,
  ADD CONSTRAINT medwatch_draft_audit_events_event_type_check CHECK (event_type IN (
    'created', 'edited', 'approved', 'exported',
    'discarded', 'submission_recorded', 'submission_amended', 'preview_viewed'));

CREATE OR REPLACE FUNCTION public.record_medwatch_draft_preview_viewed(
  p_draft_id uuid,
  p_actor_id uuid
) RETURNS SETOF public.medwatch_drafts
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_draft public.medwatch_drafts%ROWTYPE;
BEGIN
  SELECT * INTO v_draft FROM public.medwatch_drafts WHERE id = p_draft_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'MedWatch draft not found' USING ERRCODE = 'P0002';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.care_teams
    WHERE clinician_id = p_actor_id
      AND patient_id = v_draft.patient_id
      AND status = 'active'
  ) THEN
    RAISE EXCEPTION 'Clinician is not assigned to this patient' USING ERRCODE = '42501';
  END IF;

  INSERT INTO public.medwatch_draft_audit_events(
    medwatch_draft_id, adr_assessment_id, actor_id, event_type, event_data
  ) VALUES (
    v_draft.id,
    v_draft.adr_assessment_id,
    p_actor_id,
    'preview_viewed',
    jsonb_build_object('revision', v_draft.revision, 'status', v_draft.status)
  );

  RETURN NEXT v_draft;
END;
$$;

REVOKE ALL ON FUNCTION public.record_medwatch_draft_preview_viewed(uuid, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_medwatch_draft_preview_viewed(uuid, uuid) TO service_role;

-- 3. Verification: fail the migration rather than leave the gaps ---------------------------
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
      FROM unnest(ARRAY['anon', 'authenticated']) r(role)
     CROSS JOIN unnest(ARRAY['public.clinics', 'public.cron_job_runs']) t(name)
     CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) p(privilege)
     WHERE pg_catalog.has_table_privilege(r.role, t.name, p.privilege)
  ) THEN
    RAISE EXCEPTION 'clinics and cron_job_runs must not be open to a browser role';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_class
     WHERE oid IN ('public.clinics'::regclass, 'public.cron_job_runs'::regclass)
       AND relrowsecurity
     HAVING count(*) = 2
  ) THEN
    RAISE EXCEPTION 'clinics and cron_job_runs must have row level security enabled';
  END IF;
  IF pg_catalog.has_function_privilege(
       'anon', 'public.record_medwatch_draft_preview_viewed(uuid, uuid)', 'EXECUTE')
     OR pg_catalog.has_function_privilege(
       'authenticated', 'public.record_medwatch_draft_preview_viewed(uuid, uuid)', 'EXECUTE')
     OR NOT pg_catalog.has_function_privilege(
       'service_role', 'public.record_medwatch_draft_preview_viewed(uuid, uuid)', 'EXECUTE') THEN
    RAISE EXCEPTION 'The preview audit function is for the service role only';
  END IF;
END $$;
