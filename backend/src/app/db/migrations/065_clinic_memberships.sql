-- CLN-003 slice A: clinic memberships and clinic-tagged care-team links. Requires 001, 006,
-- 007 and the private schema from 020.
--
-- A clinician gets one membership row per clinic (role and status per clinic), and every
-- care-team link records the clinic it belongs to, so one provider can later hold one link
-- per clinic for the same patient. Nothing visible changes:
--   * access is still the active care-team link; is_assigned_clinician is not touched and
--     no policy reads memberships yet (private.is_clinic_member is added for later slices);
--   * clinicians.clinic_id and clinicians.role stay for the compatibility period, and a
--     trigger mirrors them into memberships, so every existing write path keeps the two in
--     step: at most one active membership per clinician, equal to the legacy columns;
--   * a care-team insert without a clinic takes the clinician's clinic, so the deployed
--     backend and the demo seed keep working once this is applied.
--
-- Written, not applied: applied to a hosted project only on explicit authorization, and
-- before the backend that reads clinic_memberships deploys (apply first, merge after).
-- Synthetic data only.

-- ── 1. Memberships ───────────────────────────────────────────────────────────────────────
CREATE TABLE public.clinic_memberships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  clinician_id uuid NOT NULL REFERENCES public.clinicians(id) ON DELETE CASCADE,
  clinic_id uuid NOT NULL REFERENCES public.clinics(id) ON DELETE RESTRICT,
  role public.clinician_role_enum NOT NULL,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT clinic_memberships_clinician_clinic_key UNIQUE (clinician_id, clinic_id)
);

CREATE INDEX idx_clinic_memberships_active_clinic
  ON public.clinic_memberships (clinic_id)
  WHERE status = 'active';

CREATE TRIGGER clinic_memberships_updated_at
  BEFORE UPDATE ON public.clinic_memberships
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

COMMENT ON TABLE public.clinic_memberships IS
  'CLN-003: a clinician''s role and status at one clinic. Mirrors clinicians.clinic_id/role until slice B writes memberships directly.';

ALTER TABLE public.clinic_memberships ENABLE ROW LEVEL SECURITY;

-- A clinician reads only their own memberships. Writes go through the service role.
CREATE POLICY clinic_memberships_own_select ON public.clinic_memberships
  FOR SELECT TO authenticated
  USING (clinician_id = auth.uid());

REVOKE ALL ON TABLE public.clinic_memberships FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.clinic_memberships TO authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.clinic_memberships TO service_role;

-- Backfill: one active membership per clinician that has a clinic. A clinician without a
-- clinic gets none; the verification block reports how many.
INSERT INTO public.clinic_memberships (clinician_id, clinic_id, role, status)
SELECT c.id, c.clinic_id, c.role, 'active'
FROM public.clinicians c
WHERE c.clinic_id IS NOT NULL
ON CONFLICT (clinician_id, clinic_id) DO NOTHING;

-- Compatibility mirror: the legacy columns stay the write path until slice B. The clinic a
-- clinician now belongs to gets an active membership with the current role; a clinic they
-- leave (profile clinic change, staff removal, invitation acceptance) becomes inactive.
CREATE FUNCTION private.mirror_legacy_clinic_membership()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND OLD.clinic_id IS NOT NULL
     AND OLD.clinic_id IS DISTINCT FROM NEW.clinic_id THEN
    UPDATE public.clinic_memberships
       SET status = 'inactive'
     WHERE clinician_id = NEW.id AND clinic_id = OLD.clinic_id AND status = 'active';
  END IF;
  IF NEW.clinic_id IS NOT NULL THEN
    INSERT INTO public.clinic_memberships AS m (clinician_id, clinic_id, role, status)
    VALUES (NEW.id, NEW.clinic_id, NEW.role, 'active')
    ON CONFLICT (clinician_id, clinic_id) DO UPDATE
      SET role = EXCLUDED.role, status = 'active'
      WHERE m.role IS DISTINCT FROM EXCLUDED.role OR m.status <> 'active';
  END IF;
  RETURN NULL;
END;
$$;

CREATE TRIGGER clinicians_mirror_clinic_membership
  AFTER INSERT OR UPDATE OF clinic_id, role ON public.clinicians
  FOR EACH ROW EXECUTE FUNCTION private.mirror_legacy_clinic_membership();

-- ── 2. Clinic-tagged care-team links ─────────────────────────────────────────────────────
ALTER TABLE public.care_teams
  ADD COLUMN clinic_id uuid REFERENCES public.clinics(id);

COMMENT ON COLUMN public.care_teams.clinic_id IS
  'CLN-003: the clinic this link belongs to, taken from the patient invite code that created it. NULL only when the clinician has no clinic.';

-- Before 065 a patient invite code had no recorded clinic: the code is the pending row and
-- the clinician had exactly one clinic, so that clinic issued every existing link.
UPDATE public.care_teams t
   SET clinic_id = c.clinic_id
  FROM public.clinicians c
 WHERE c.id = t.clinician_id
   AND t.clinic_id IS NULL
   AND c.clinic_id IS NOT NULL;

-- One link per (patient, clinician, clinic) instead of per (patient, clinician). The old
-- constraint is found by definition so an environment-specific name cannot be missed.
DO $$
DECLARE
  v_name text;
BEGIN
  SELECT c.conname INTO v_name
    FROM pg_catalog.pg_constraint c
   WHERE c.conrelid = 'public.care_teams'::regclass
     AND c.contype = 'u'
     AND pg_catalog.pg_get_constraintdef(c.oid) = 'UNIQUE (patient_id, clinician_id)';
  IF v_name IS NULL THEN
    RAISE EXCEPTION 'care_teams has no UNIQUE (patient_id, clinician_id) constraint to replace';
  END IF;
  EXECUTE pg_catalog.format('ALTER TABLE public.care_teams DROP CONSTRAINT %I', v_name);
END $$;

ALTER TABLE public.care_teams
  ADD CONSTRAINT care_teams_patient_clinician_clinic_key
  UNIQUE (patient_id, clinician_id, clinic_id);

-- NULLs are distinct in the constraint above, so keep the old guarantee for links of a
-- clinician without a clinic. Pending invites (patient_id NULL) stay unconstrained, as before.
CREATE UNIQUE INDEX uq_care_teams_patient_clinician_without_clinic
  ON public.care_teams (patient_id, clinician_id)
  WHERE clinic_id IS NULL;

CREATE INDEX idx_care_teams_clinic
  ON public.care_teams (clinic_id, status);

-- A new link (or invite code) takes its clinic explicitly or, during the compatibility
-- period, from the clinician's clinic. It may only name a clinic where the clinician is an
-- active member, and a link's clinic is never cleared (a link reassigned to another
-- clinician without a clinic takes that clinician's clinic).
CREATE FUNCTION private.care_team_clinic_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.clinic_id IS NOT DISTINCT FROM OLD.clinic_id
     AND NEW.clinician_id IS NOT DISTINCT FROM OLD.clinician_id THEN
    RETURN NEW;
  END IF;
  -- A link handed to another clinician without naming a clinic follows that clinician's
  -- clinic, as a new link would; otherwise a link's clinic is never cleared.
  IF TG_OP = 'UPDATE' AND NEW.clinician_id IS DISTINCT FROM OLD.clinician_id
     AND NEW.clinic_id IS NOT DISTINCT FROM OLD.clinic_id THEN
    NEW.clinic_id := NULL;
  ELSIF TG_OP = 'UPDATE' AND OLD.clinic_id IS NOT NULL AND NEW.clinic_id IS NULL THEN
    RAISE EXCEPTION 'A care-team link keeps its clinic' USING ERRCODE = '23514';
  END IF;
  IF NEW.clinic_id IS NULL THEN
    SELECT c.clinic_id INTO NEW.clinic_id
      FROM public.clinicians c
     WHERE c.id = NEW.clinician_id;
  END IF;
  IF NEW.clinic_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM public.clinic_memberships m
     WHERE m.clinician_id = NEW.clinician_id
       AND m.clinic_id = NEW.clinic_id
       AND m.status = 'active'
  ) THEN
    RAISE EXCEPTION 'A care-team link must belong to a clinic where the clinician is an active member'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER care_teams_clinic_guard
  BEFORE INSERT OR UPDATE OF clinic_id, clinician_id ON public.care_teams
  FOR EACH ROW EXECUTE FUNCTION private.care_team_clinic_guard();

REVOKE ALL ON FUNCTION private.mirror_legacy_clinic_membership() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.care_team_clinic_guard() FROM PUBLIC, anon, authenticated;

-- ── 3. Access helper for later slices ────────────────────────────────────────────────────
-- Not used by any policy in slice A. Later slices combine it with the care-team check:
-- membership alone never grants access to a patient.
CREATE FUNCTION private.is_clinic_member(p_clinic_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.clinic_memberships m
    JOIN public.clinics cl ON cl.id = m.clinic_id
    WHERE m.clinician_id = auth.uid()
      AND m.clinic_id = p_clinic_id
      AND m.status = 'active'
      AND cl.status = 'active'
  );
$$;

REVOKE ALL ON FUNCTION private.is_clinic_member(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.is_clinic_member(uuid) TO authenticated;

-- ── 4. Fail-closed verification ──────────────────────────────────────────────────────────
DO $$
DECLARE
  v_without_clinic integer;
BEGIN
  IF EXISTS (
    SELECT 1 FROM public.clinicians c
     WHERE c.clinic_id IS NOT NULL
       AND (SELECT count(*) FROM public.clinic_memberships m WHERE m.clinician_id = c.id) <> 1
  ) THEN
    RAISE EXCEPTION 'Every clinician with a clinic needs exactly one membership';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.clinicians c
      JOIN public.clinic_memberships m ON m.clinician_id = c.id
     WHERE m.clinic_id IS DISTINCT FROM c.clinic_id OR m.role <> c.role OR m.status <> 'active'
  ) THEN
    RAISE EXCEPTION 'A backfilled membership does not match the clinician''s clinic and role';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.care_teams t
      JOIN public.clinicians c ON c.id = t.clinician_id
     WHERE t.clinic_id IS NULL AND c.clinic_id IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'Every care-team link needs a clinic unless its clinician has none';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint c
     WHERE c.conrelid = 'public.care_teams'::regclass
       AND c.conname = 'care_teams_patient_clinician_clinic_key'
       AND pg_catalog.pg_get_constraintdef(c.oid) = 'UNIQUE (patient_id, clinician_id, clinic_id)'
  ) OR EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint c
     WHERE c.conrelid = 'public.care_teams'::regclass
       AND pg_catalog.pg_get_constraintdef(c.oid) = 'UNIQUE (patient_id, clinician_id)'
  ) THEN
    RAISE EXCEPTION 'care_teams must be unique on (patient_id, clinician_id, clinic_id) only';
  END IF;
  IF NOT (SELECT relrowsecurity FROM pg_catalog.pg_class
           WHERE oid = 'public.clinic_memberships'::regclass) THEN
    RAISE EXCEPTION 'clinic_memberships must have row-level security enabled';
  END IF;
  IF pg_catalog.has_table_privilege('anon', 'public.clinic_memberships', 'SELECT')
     OR EXISTS (
       SELECT 1 FROM unnest(ARRAY['anon', 'authenticated', 'service_role']) r(role)
        CROSS JOIN unnest(ARRAY['DELETE', 'TRUNCATE']) p(privilege)
        WHERE pg_catalog.has_table_privilege(r.role, 'public.clinic_memberships', p.privilege)
     )
     OR EXISTS (
       SELECT 1 FROM unnest(ARRAY['INSERT', 'UPDATE']) p(privilege)
        WHERE pg_catalog.has_table_privilege('authenticated', 'public.clinic_memberships', p.privilege)
     ) THEN
    RAISE EXCEPTION 'clinic_memberships grants are wider than service-role writes and own reads';
  END IF;
  IF pg_catalog.has_function_privilege('anon', 'private.is_clinic_member(uuid)', 'EXECUTE') THEN
    RAISE EXCEPTION 'anon may not call private.is_clinic_member';
  END IF;
  SELECT count(*) INTO v_without_clinic FROM public.clinicians WHERE clinic_id IS NULL;
  RAISE NOTICE 'clinic_memberships: % clinician(s) have no clinic and received no membership',
    v_without_clinic;
END $$;
