-- ============================================================
-- MediAgent — 004 Custom JWT Claims Hook
--
-- Adds a `user_role` claim ("patient" | "clinician") to every
-- Supabase JWT. This lets the frontend AND RLS policies know
-- which portal the user belongs to without an extra DB lookup
-- on every request.
--
-- After running this, wire it up in the Supabase Dashboard:
--   Auth → Hooks → Customize Access Token (JWT) Claims
--   Hook type: Postgres
--   Schema: public
--   Function: custom_access_token_hook
-- ============================================================

-- The function receives the raw JWT event from Supabase Auth,
-- checks whether the user_id exists in `patients` or `clinicians`,
-- and injects `user_role` into the claims object.
CREATE OR REPLACE FUNCTION custom_access_token_hook(event jsonb)
RETURNS jsonb AS $$
DECLARE
  claims jsonb;
  user_role text;
BEGIN
  claims := event->'claims';

  -- Determine role by checking which profile table has this user
  IF EXISTS (SELECT 1 FROM patients WHERE id = (event->>'user_id')::uuid) THEN
    user_role := 'patient';
  ELSIF EXISTS (SELECT 1 FROM clinicians WHERE id = (event->>'user_id')::uuid) THEN
    user_role := 'clinician';
  ELSE
    user_role := 'unknown';
  END IF;

  -- Inject into JWT claims
  claims := jsonb_set(claims, '{user_role}', to_jsonb(user_role));
  event := jsonb_set(event, '{claims}', claims);

  RETURN event;
END;
$$ LANGUAGE plpgsql;

-- Grant execute to the Supabase auth admin role (required for hooks)
GRANT EXECUTE ON FUNCTION public.custom_access_token_hook TO supabase_auth_admin;
GRANT USAGE ON SCHEMA public TO supabase_auth_admin;

-- Revoke from public-facing roles (security: this runs server-side only)
REVOKE EXECUTE ON FUNCTION public.custom_access_token_hook FROM authenticated, anon, public;
