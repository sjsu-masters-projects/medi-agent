-- ============================================================
-- MediAgent — 020 Database Security Hardening
-- Keeps RLS helper access internal, removes anonymous RPC access,
-- and pins deterministic function search paths.
-- ============================================================

-- Private helpers are invoked only from RLS policies. Keeping them outside
-- the Data API schemas avoids exposing SECURITY DEFINER functions as RPCs.
CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC;
GRANT USAGE ON SCHEMA private TO authenticated;

CREATE OR REPLACE FUNCTION private.is_assigned_clinician(p_patient_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.care_teams
    WHERE clinician_id = auth.uid()
      AND patient_id = p_patient_id
      AND status = 'active'
  );
$$;

CREATE OR REPLACE FUNCTION private.is_patient()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.patients
    WHERE id = auth.uid()
  );
$$;

CREATE OR REPLACE FUNCTION private.is_clinician()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.clinicians
    WHERE id = auth.uid()
  );
$$;

REVOKE ALL ON FUNCTION private.is_assigned_clinician(uuid) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.is_patient() FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.is_clinician() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.is_assigned_clinician(uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION private.is_patient() TO authenticated;
GRANT EXECUTE ON FUNCTION private.is_clinician() TO authenticated;

-- Public helper functions remain for backend ownership only. RLS policies are
-- rewritten below to call the private helpers instead.
ALTER FUNCTION public.is_assigned_clinician(uuid)
  SET search_path = pg_catalog, public;
ALTER FUNCTION public.is_patient()
  SET search_path = pg_catalog, public;
ALTER FUNCTION public.is_clinician()
  SET search_path = pg_catalog, public;
ALTER FUNCTION public.rls_auto_enable()
  SET search_path = pg_catalog;

REVOKE EXECUTE ON FUNCTION public.is_assigned_clinician(uuid)
  FROM PUBLIC, anon, authenticated, supabase_auth_admin;
REVOKE EXECUTE ON FUNCTION public.is_patient()
  FROM PUBLIC, anon, authenticated, supabase_auth_admin;
REVOKE EXECUTE ON FUNCTION public.is_clinician()
  FROM PUBLIC, anon, authenticated, supabase_auth_admin;
REVOKE EXECUTE ON FUNCTION public.rls_auto_enable()
  FROM PUBLIC, anon, authenticated, supabase_auth_admin;
GRANT EXECUTE ON FUNCTION public.is_assigned_clinician(uuid) TO postgres;
GRANT EXECUTE ON FUNCTION public.is_patient() TO postgres;
GRANT EXECUTE ON FUNCTION public.is_clinician() TO postgres;
GRANT EXECUTE ON FUNCTION public.rls_auto_enable() TO postgres;

-- Pin every advisor-flagged public function. The vector extension deliberately
-- remains in public until its compatibility move has been separately verified.
ALTER FUNCTION public.update_updated_at()
  SET search_path = pg_catalog, public;
ALTER FUNCTION public.normalize_clinic_name(text)
  SET search_path = pg_catalog, public;
ALTER FUNCTION public.generate_clinic_code()
  SET search_path = pg_catalog, public;
ALTER FUNCTION public.match_drug_knowledge_chunks(public.vector, integer, text[], text[], double precision)
  SET search_path = pg_catalog, public;

-- Preserve the Auth hook's least-privilege execution contract and use the
-- same deterministic path convention as the hardened functions.
ALTER FUNCTION public.custom_access_token_hook(jsonb)
  SET search_path = pg_catalog, public;
REVOKE EXECUTE ON FUNCTION public.custom_access_token_hook(jsonb)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.custom_access_token_hook(jsonb)
  TO postgres, supabase_auth_admin;

-- All browser-facing RLS policies explicitly require an authenticated role.
-- Their existing predicates are preserved, with helper calls redirected to
-- the non-exposed private schema.
DO $$
DECLARE
  policy_record record;
  policy_using text;
  policy_with_check text;
BEGIN
  FOR policy_record IN
    SELECT
      policy.oid,
      policy.polname,
      table_schema.nspname AS schema_name,
      table_class.relname AS table_name,
      pg_get_expr(policy.polqual, policy.polrelid) AS using_expression,
      pg_get_expr(policy.polwithcheck, policy.polrelid) AS with_check_expression
    FROM pg_policy AS policy
    JOIN pg_class AS table_class ON table_class.oid = policy.polrelid
    JOIN pg_namespace AS table_schema ON table_schema.oid = table_class.relnamespace
    WHERE table_schema.nspname = 'public'
      AND 0::oid = ANY(policy.polroles)
      AND NOT (
        table_class.relname = 'soap_notes'
        AND policy.polname = 'service_role_manage_soap_notes'
      )
  LOOP
    policy_using := regexp_replace(
      regexp_replace(
        regexp_replace(policy_record.using_expression, '\mis_assigned_clinician\s*\(', 'private.is_assigned_clinician(', 'g'),
        '\mis_patient\s*\(', 'private.is_patient(', 'g'
      ),
      '\mis_clinician\s*\(', 'private.is_clinician(', 'g'
    );
    policy_with_check := regexp_replace(
      regexp_replace(
        regexp_replace(policy_record.with_check_expression, '\mis_assigned_clinician\s*\(', 'private.is_assigned_clinician(', 'g'),
        '\mis_patient\s*\(', 'private.is_patient(', 'g'
      ),
      '\mis_clinician\s*\(', 'private.is_clinician(', 'g'
    );

    EXECUTE format(
      'ALTER POLICY %I ON %I.%I TO authenticated',
      policy_record.polname,
      policy_record.schema_name,
      policy_record.table_name
    );

    IF policy_using IS NOT NULL THEN
      EXECUTE format(
        'ALTER POLICY %I ON %I.%I USING (%s)',
        policy_record.polname,
        policy_record.schema_name,
        policy_record.table_name,
        policy_using
      );
    END IF;

    IF policy_with_check IS NOT NULL THEN
      EXECUTE format(
        'ALTER POLICY %I ON %I.%I WITH CHECK (%s)',
        policy_record.polname,
        policy_record.schema_name,
        policy_record.table_name,
        policy_with_check
      );
    END IF;
  END LOOP;
END;
$$;

-- service_role bypasses RLS, but this policy is retained as an explicit
-- backend-only policy and no longer relies on deprecated auth.role().
ALTER POLICY service_role_manage_soap_notes ON public.soap_notes
  TO service_role
  USING (true)
  WITH CHECK (true);

-- Storage object reads and writes require a signed-in principal. Public avatar
-- delivery remains governed by the bucket's public setting, not these policies.
DO $$
DECLARE
  policy_record record;
  policy_using text;
  policy_with_check text;
BEGIN
  FOR policy_record IN
    SELECT
      policy.polname,
      pg_get_expr(policy.polqual, policy.polrelid) AS using_expression,
      pg_get_expr(policy.polwithcheck, policy.polrelid) AS with_check_expression
    FROM pg_policy AS policy
    JOIN pg_class AS table_class ON table_class.oid = policy.polrelid
    JOIN pg_namespace AS table_schema ON table_schema.oid = table_class.relnamespace
    WHERE table_schema.nspname = 'storage'
      AND table_class.relname = 'objects'
      AND 0::oid = ANY(policy.polroles)
  LOOP
    policy_using := regexp_replace(
      policy_record.using_expression,
      '\mis_assigned_clinician\s*\(',
      'private.is_assigned_clinician(',
      'g'
    );
    policy_with_check := regexp_replace(
      policy_record.with_check_expression,
      '\mis_assigned_clinician\s*\(',
      'private.is_assigned_clinician(',
      'g'
    );

    EXECUTE format('ALTER POLICY %I ON storage.objects TO authenticated', policy_record.polname);

    IF policy_using IS NOT NULL THEN
      EXECUTE format('ALTER POLICY %I ON storage.objects USING (%s)', policy_record.polname, policy_using);
    END IF;

    IF policy_with_check IS NOT NULL THEN
      EXECUTE format('ALTER POLICY %I ON storage.objects WITH CHECK (%s)', policy_record.polname, policy_with_check);
    END IF;
  END LOOP;
END;
$$;
