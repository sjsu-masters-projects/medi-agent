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
CREATE OR REPLACE FUNCTION public.custom_access_token_hook(event jsonb)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  claims jsonb := coalesce(event->'claims', '{}'::jsonb);
  user_role text := 'unknown';
  user_id uuid;
BEGIN
  user_id := nullif(event->>'user_id', '')::uuid;

  -- Determine role by checking which profile table has this user.
  IF user_id IS NOT NULL THEN
    IF EXISTS (SELECT 1 FROM public.patients WHERE id = user_id) THEN
      user_role := 'patient';
    ELSIF EXISTS (SELECT 1 FROM public.clinicians WHERE id = user_id) THEN
      user_role := 'clinician';
    END IF;
  END IF;

  -- Inject into JWT claims
  claims := jsonb_set(claims, '{user_role}', to_jsonb(user_role), true);
  event := jsonb_set(event, '{claims}', claims, true);

  RETURN event;
END;
$$;

-- Grant execute to the Supabase auth admin role (required for hooks)
GRANT EXECUTE ON FUNCTION public.custom_access_token_hook TO supabase_auth_admin;
GRANT USAGE ON SCHEMA public TO supabase_auth_admin;

-- Revoke from public-facing roles (security: this runs server-side only)
REVOKE EXECUTE ON FUNCTION public.custom_access_token_hook FROM authenticated, anon, public;
