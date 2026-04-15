-- ============================================================
-- MediAgent — 009 JWT Claims Hook Hardening
--
-- Re-applies and hardens custom_access_token_hook so role claims
-- stay reliable across Supabase event payload variants.
--
-- Why this exists:
--   - Keeps claims parsing resilient when `event.claims` is missing
--     or not a JSON object.
--   - Avoids UUID cast errors for malformed user_id values.
--   - Preserves strict role contract: only `patient` or `clinician`
--     are emitted; otherwise `unknown`.
-- ============================================================

CREATE OR REPLACE FUNCTION public.custom_access_token_hook(event jsonb)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
DECLARE
  claims jsonb := CASE
    WHEN jsonb_typeof(event->'claims') = 'object' THEN event->'claims'
    ELSE '{}'::jsonb
  END;
  user_role text := 'unknown';
  raw_user_id text;
  user_id uuid;
BEGIN
  raw_user_id := coalesce(
    nullif(event->>'user_id', ''),
    nullif(event #>> '{user,id}', '')
  );

  IF raw_user_id IS NOT NULL
     AND raw_user_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
    user_id := raw_user_id::uuid;
  END IF;

  IF user_id IS NOT NULL THEN
    IF EXISTS (SELECT 1 FROM public.patients WHERE id = user_id) THEN
      user_role := 'patient';
    ELSIF EXISTS (SELECT 1 FROM public.clinicians WHERE id = user_id) THEN
      user_role := 'clinician';
    END IF;
  END IF;

  claims := jsonb_set(claims, '{user_role}', to_jsonb(user_role), true);
  event := jsonb_set(event, '{claims}', claims, true);

  RETURN event;
END;
$$;

ALTER FUNCTION public.custom_access_token_hook(jsonb) OWNER TO postgres;

GRANT EXECUTE ON FUNCTION public.custom_access_token_hook(jsonb) TO supabase_auth_admin;
GRANT USAGE ON SCHEMA public TO supabase_auth_admin;

REVOKE EXECUTE ON FUNCTION public.custom_access_token_hook(jsonb)
FROM authenticated, anon, public;
