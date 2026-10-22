-- PLAN-002 / CLN-003 slice H, part 1: a care plan belongs to one care-team link.
--
-- Before this migration a patient had one lineage of care_plan_versions: one version
-- sequence, one open draft, one approved version. This migration introduces the plan
-- (care_plans) as the lineage owner. Each plan belongs to one care-team link (patient,
-- clinician, clinic), numbers its own versions, holds at most one open draft and one
-- approved version, and has its own approver and audit trail.
--
--   * Existing lineages move to the care team that approved them, or the patient's only
--     care team. Anything ambiguous becomes 'unassigned_legacy' and surfaces a review item;
--     ownership is never guessed. Version rows, item ids, projections, reminders,
--     completions and barriers are not rewritten.
--   * A care team that ends never removes activities. Its plan becomes 'unowned',
--     approved activities stay in Today, and the remaining care teams (and the clinic's
--     admins, with no patient detail) get a review item. A clinician adopts the plan or
--     retires items.
--   * Ownership changes are recorded in an append-only table with no browser access.
--
-- Hosted Supabase gives new tables and functions default grants to anon, authenticated and
-- service_role, so every new object below revokes them explicitly and the final block fails
-- the migration if a grant or RLS setting is wrong.

-- ── 1. Plans ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE public.care_plans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL REFERENCES public.patients(id) ON DELETE CASCADE,
  -- Current owner. NULL exactly while the plan is unowned or unassigned.
  care_team_id uuid REFERENCES public.care_teams(id) ON DELETE SET NULL,
  -- The link the plan was first created for. One native plan per link, ever.
  origin_care_team_id uuid REFERENCES public.care_teams(id) ON DELETE SET NULL,
  origin text NOT NULL DEFAULT 'native' CHECK (origin IN ('native', 'adopted', 'legacy')),
  ownership_state text NOT NULL DEFAULT 'owned'
    CHECK (ownership_state IN ('owned', 'unowned', 'unassigned_legacy')),
  -- Display of the last owner, kept so the patient and clinicians can still read
  -- "Prescribed by Dr. X" after the link or the clinician account is gone.
  owner_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(owner_snapshot) = 'object'),
  unowned_since timestamptz,
  ownership_revision integer NOT NULL DEFAULT 1 CHECK (ownership_revision > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((ownership_state = 'owned') = (care_team_id IS NOT NULL))
);
CREATE TRIGGER care_plans_updated_at
  BEFORE UPDATE ON public.care_plans
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
CREATE UNIQUE INDEX care_plans_one_native_per_link
  ON public.care_plans(origin_care_team_id)
  WHERE origin = 'native' AND origin_care_team_id IS NOT NULL;
CREATE INDEX care_plans_patient ON public.care_plans(patient_id, ownership_state);
CREATE INDEX care_plans_team ON public.care_plans(care_team_id) WHERE care_team_id IS NOT NULL;

-- ── 2. Append-only ownership audit ────────────────────────────────────────────────────────
-- Plain uuid columns, no foreign keys: the trail must survive account deletion, and an
-- append-only table cannot take part in a cascade.

CREATE TABLE public.care_plan_ownership_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL,
  care_plan_id uuid,
  care_team_id uuid,
  actor_id uuid,
  event_type text NOT NULL CHECK (char_length(event_type) BETWEEN 1 AND 100),
  event_data jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(event_data) = 'object'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX care_plan_ownership_events_plan
  ON public.care_plan_ownership_events(care_plan_id, created_at);
CREATE INDEX care_plan_ownership_events_patient
  ON public.care_plan_ownership_events(patient_id, created_at);

CREATE FUNCTION private.care_plan_append_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
  RAISE EXCEPTION 'The care-plan ownership trail is append-only' USING ERRCODE = '42501';
END;
$$;
CREATE TRIGGER care_plan_ownership_events_append_only
  BEFORE UPDATE OR DELETE ON public.care_plan_ownership_events
  FOR EACH ROW EXECUTE FUNCTION private.care_plan_append_only();
CREATE TRIGGER care_plan_ownership_events_no_truncate
  BEFORE TRUNCATE ON public.care_plan_ownership_events
  FOR EACH STATEMENT EXECUTE FUNCTION private.care_plan_append_only();

-- ── 3. Review items for care teams and clinic admins ──────────────────────────────────────
-- Work that needs a clinician: an unassigned or unowned plan, a cross-plan conflict that
-- another team must hear about. An item addressed to a clinic's admins carries no patient
-- detail; the API shows the kind and a count only.

CREATE TABLE public.care_plan_review_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL REFERENCES public.patients(id) ON DELETE CASCADE,
  care_plan_id uuid REFERENCES public.care_plans(id) ON DELETE CASCADE,
  kind text NOT NULL CHECK (kind IN (
    'unassigned_legacy_plan', 'unowned_plan', 'cross_plan_conflict', 'conflict_acknowledged',
    'conflict_published_without', 'conflict_reply'
  )),
  target_care_team_id uuid REFERENCES public.care_teams(id) ON DELETE CASCADE,
  target_clinic_id uuid REFERENCES public.clinics(id) ON DELETE CASCADE,
  -- Cross-plan items: the plan that raised it and the exact conflict.
  source_care_plan_id uuid REFERENCES public.care_plans(id) ON DELETE CASCADE,
  conflict_fingerprint text,
  summary jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(summary) = 'object'),
  request_note text CHECK (request_note IS NULL OR char_length(request_note) BETWEEN 1 AND 2000),
  reply_note text CHECK (reply_note IS NULL OR char_length(reply_note) BETWEEN 1 AND 2000),
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'withdrawn')),
  created_by uuid,
  resolved_by uuid,
  resolved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK ((target_care_team_id IS NOT NULL) <> (target_clinic_id IS NOT NULL)),
  CHECK (status = 'open' OR resolved_at IS NOT NULL)
);
-- One open item per plan, kind, addressee and conflict: retries do not pile up.
CREATE UNIQUE INDEX care_plan_review_items_open_team
  ON public.care_plan_review_items(care_plan_id, kind, target_care_team_id,
    COALESCE(conflict_fingerprint, ''))
  WHERE status = 'open' AND target_care_team_id IS NOT NULL;
CREATE UNIQUE INDEX care_plan_review_items_open_clinic
  ON public.care_plan_review_items(care_plan_id, kind, target_clinic_id)
  WHERE status = 'open' AND target_clinic_id IS NOT NULL;
CREATE INDEX care_plan_review_items_team
  ON public.care_plan_review_items(target_care_team_id, status)
  WHERE target_care_team_id IS NOT NULL;
CREATE INDEX care_plan_review_items_clinic
  ON public.care_plan_review_items(target_clinic_id, status)
  WHERE target_clinic_id IS NOT NULL;

-- ── 4. Item retirements (approved items stay immutable) ───────────────────────────────────

CREATE TABLE public.care_plan_item_retirements (
  item_id uuid PRIMARY KEY REFERENCES public.care_plan_items(id) ON DELETE CASCADE,
  care_plan_id uuid NOT NULL REFERENCES public.care_plans(id) ON DELETE CASCADE,
  retired_by uuid NOT NULL,
  retired_by_care_team_id uuid,
  reason text NOT NULL CHECK (char_length(btrim(reason)) BETWEEN 1 AND 2000),
  retired_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX care_plan_item_retirements_plan ON public.care_plan_item_retirements(care_plan_id);

-- ── 5. Lineage columns on versions and generation requests ────────────────────────────────

ALTER TABLE public.care_plan_versions
  ADD COLUMN care_plan_id uuid REFERENCES public.care_plans(id) ON DELETE CASCADE;
ALTER TABLE public.care_plan_generation_requests
  ADD COLUMN care_plan_id uuid REFERENCES public.care_plans(id) ON DELETE CASCADE;

-- ── 6. Helpers ────────────────────────────────────────────────────────────────────────────

-- Display of a link's clinician, specialty and clinic. Names only; no contact details.
CREATE FUNCTION private.care_team_display(p_care_team_id uuid) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = '' AS $$
  SELECT COALESCE((
    SELECT jsonb_build_object(
      'care_team_id', t.id,
      'clinician_id', t.clinician_id,
      'clinician_name', btrim(concat_ws(' ', c.first_name, c.last_name)),
      'specialty', COALESCE(NULLIF(btrim(t.specialty_context), ''), NULLIF(btrim(c.specialty), ''),
        NULLIF(btrim(t.role), '')),
      'clinic_id', t.clinic_id,
      'clinic_name', cl.display_name)
    FROM public.care_teams t
    LEFT JOIN public.clinicians c ON c.id = t.clinician_id
    LEFT JOIN public.clinics cl ON cl.id = t.clinic_id
    WHERE t.id = p_care_team_id), '{}'::jsonb);
$$;

-- True when the clinician holds this active link and is an active member of its clinic.
CREATE FUNCTION private.clinician_holds_link(p_clinician_id uuid, p_care_team_id uuid)
RETURNS boolean LANGUAGE sql STABLE SET search_path = '' AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.care_teams t
    JOIN public.clinic_memberships m
      ON m.clinician_id = t.clinician_id AND m.clinic_id = t.clinic_id AND m.status = 'active'
    JOIN public.clinics cl ON cl.id = t.clinic_id AND cl.status = 'active'
    WHERE t.id = p_care_team_id AND t.clinician_id = p_clinician_id AND t.status = 'active'
      AND t.patient_id IS NOT NULL);
$$;

CREATE FUNCTION private.log_plan_ownership(
  p_patient_id uuid, p_plan_id uuid, p_care_team_id uuid, p_actor_id uuid,
  p_event text, p_data jsonb DEFAULT '{}'::jsonb
) RETURNS void LANGUAGE sql SET search_path = '' AS $$
  INSERT INTO public.care_plan_ownership_events(
    patient_id, care_plan_id, care_team_id, actor_id, event_type, event_data)
  VALUES (p_patient_id, p_plan_id, p_care_team_id, p_actor_id, p_event, COALESCE(p_data, '{}'));
$$;

-- Open the review items for a plan that has no owner: one per remaining active care team
-- of the patient, and one for the admins of the clinic of the team that ended. Idempotent.
CREATE FUNCTION private.open_unowned_plan_items(
  p_plan_id uuid, p_kind text, p_ended_care_team_id uuid, p_actor_id uuid
) RETURNS integer LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_plan public.care_plans%ROWTYPE;
  v_team uuid;
  v_clinic uuid;
  v_count integer := 0;
  v_rows integer;
BEGIN
  SELECT * INTO v_plan FROM public.care_plans WHERE id = p_plan_id;
  IF NOT FOUND THEN RETURN 0; END IF;
  FOR v_team IN
    SELECT t.id FROM public.care_teams t
    WHERE t.patient_id = v_plan.patient_id AND t.status = 'active'
      AND t.id IS DISTINCT FROM p_ended_care_team_id
    ORDER BY t.id
  LOOP
    INSERT INTO public.care_plan_review_items(
      patient_id, care_plan_id, kind, target_care_team_id, created_by, summary)
    VALUES (v_plan.patient_id, v_plan.id, p_kind, v_team, p_actor_id,
      jsonb_build_object('previous_owner', v_plan.owner_snapshot))
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    v_count := v_count + v_rows;
  END LOOP;
  v_clinic := NULLIF(v_plan.owner_snapshot->>'clinic_id', '')::uuid;
  IF v_clinic IS NOT NULL AND EXISTS (SELECT 1 FROM public.clinics WHERE id = v_clinic) THEN
    -- Admins see that work is open and how much; never the patient or the activities.
    INSERT INTO public.care_plan_review_items(
      patient_id, care_plan_id, kind, target_clinic_id, created_by, summary)
    VALUES (v_plan.patient_id, v_plan.id, p_kind, v_clinic, p_actor_id, '{}'::jsonb)
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    v_count := v_count + v_rows;
  END IF;
  RETURN v_count;
END;
$$;

-- Create (or return) the native plan of a link.
CREATE FUNCTION private.ensure_care_plan(p_care_team_id uuid) RETURNS uuid
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_team public.care_teams%ROWTYPE;
  v_plan uuid;
BEGIN
  SELECT * INTO v_team FROM public.care_teams WHERE id = p_care_team_id;
  IF NOT FOUND OR v_team.patient_id IS NULL THEN
    RAISE EXCEPTION 'care team link not found' USING ERRCODE = '42501';
  END IF;
  SELECT id INTO v_plan FROM public.care_plans
    WHERE origin_care_team_id = p_care_team_id AND origin = 'native';
  IF FOUND THEN RETURN v_plan; END IF;
  INSERT INTO public.care_plans(patient_id, care_team_id, origin_care_team_id, origin,
    ownership_state, owner_snapshot)
  VALUES (v_team.patient_id, v_team.id, v_team.id, 'native', 'owned',
    private.care_team_display(v_team.id))
  ON CONFLICT (origin_care_team_id) WHERE origin = 'native' AND origin_care_team_id IS NOT NULL
  DO NOTHING
  RETURNING id INTO v_plan;
  IF v_plan IS NULL THEN
    SELECT id INTO v_plan FROM public.care_plans
      WHERE origin_care_team_id = p_care_team_id AND origin = 'native';
  ELSE
    PERFORM private.log_plan_ownership(v_team.patient_id, v_plan, v_team.id, NULL, 'plan_created',
      jsonb_build_object('basis', 'care_team_link'));
  END IF;
  RETURN v_plan;
END;
$$;

-- ── 7. Backfill: existing lineages move to the care team that approved them ───────────────
-- Basis, in order: the approving clinician's only link to the patient; the one link the
-- approved activities were projected for; the patient's only care team. Any other case is
-- left unassigned and surfaces a review item. Nothing here rewrites versions or items.

DO $backfill$
DECLARE
  v_patient uuid;
  v_has_versions boolean;
  v_approver uuid;
  v_latest_approved uuid;
  v_owner uuid;
  v_basis text;
  v_count integer;
  v_status public.care_team_status_enum;
  v_plan uuid;
  v_state text;
  v_candidates uuid[];
  v_projected uuid[];
BEGIN
  FOR v_patient IN
    SELECT patient_id FROM public.care_plan_versions
    UNION
    SELECT patient_id FROM public.care_plan_generation_requests
      WHERE status IN ('pending', 'processing', 'retry')
    ORDER BY 1
  LOOP
    v_owner := NULL;
    v_basis := NULL;
    v_plan := NULL;
    SELECT EXISTS (SELECT 1 FROM public.care_plan_versions WHERE patient_id = v_patient)
      INTO v_has_versions;
    SELECT id INTO v_latest_approved FROM public.care_plan_versions
      WHERE patient_id = v_patient AND status = 'approved' LIMIT 1;
    SELECT approved_by INTO v_approver FROM public.care_plan_versions
      WHERE patient_id = v_patient AND approved_by IS NOT NULL
      ORDER BY version_number DESC LIMIT 1;

    IF v_approver IS NOT NULL THEN
      SELECT array_agg(id ORDER BY id) INTO v_candidates FROM public.care_teams
        WHERE patient_id = v_patient AND clinician_id = v_approver;
      v_count := COALESCE(cardinality(v_candidates), 0);
      IF v_count = 1 THEN
        v_owner := v_candidates[1];
        v_basis := 'approver_single_link';
      ELSIF v_count > 1 AND v_latest_approved IS NOT NULL THEN
        SELECT array_agg(DISTINCT team ORDER BY team) INTO v_projected FROM (
          SELECT m.prescribed_by_care_team_id AS team
            FROM public.care_plan_items i
            JOIN public.medications m ON m.id = i.projection_id AND i.projection_type = 'medication'
            WHERE i.plan_version_id = v_latest_approved AND NOT i.is_removed
          UNION ALL
          SELECT o.set_by_care_team_id
            FROM public.care_plan_items i
            JOIN public.obligations o ON o.id = i.projection_id AND i.projection_type = 'obligation'
            WHERE i.plan_version_id = v_latest_approved AND NOT i.is_removed) projected;
        -- A NULL team is a projection nobody recorded: ambiguity, not a vote.
        IF cardinality(v_projected) = 1 AND v_projected[1] = ANY (v_candidates) THEN
          v_owner := v_projected[1];
          v_basis := 'projected_for_one_link';
        END IF;
      END IF;
    END IF;

    IF v_owner IS NULL THEN
      SELECT count(*), (array_agg(id))[1] INTO v_count, v_owner FROM public.care_teams
        WHERE patient_id = v_patient;
      IF v_count = 1 THEN
        v_basis := 'patient_single_care_team';
      ELSE
        v_owner := NULL;
      END IF;
    END IF;

    IF v_owner IS NOT NULL THEN
      SELECT status INTO v_status FROM public.care_teams WHERE id = v_owner;
      v_state := CASE WHEN v_status = 'active' THEN 'owned' ELSE 'unowned' END;
      INSERT INTO public.care_plans(patient_id, care_team_id, origin_care_team_id, origin,
        ownership_state, owner_snapshot, unowned_since)
      VALUES (v_patient, CASE WHEN v_state = 'owned' THEN v_owner END, v_owner, 'native',
        v_state, private.care_team_display(v_owner),
        CASE WHEN v_state = 'unowned' THEN now() END)
      RETURNING id INTO v_plan;
      PERFORM private.log_plan_ownership(v_patient, v_plan, v_owner, NULL, 'backfill_assigned',
        jsonb_build_object('basis', v_basis, 'ownership_state', v_state));
      IF v_state = 'unowned' THEN
        PERFORM private.open_unowned_plan_items(v_plan, 'unowned_plan', v_owner, NULL);
      END IF;
    ELSIF v_has_versions THEN
      INSERT INTO public.care_plans(patient_id, care_team_id, origin_care_team_id, origin,
        ownership_state, owner_snapshot, unowned_since)
      VALUES (v_patient, NULL, NULL, 'legacy', 'unassigned_legacy', '{}'::jsonb, now())
      RETURNING id INTO v_plan;
      PERFORM private.log_plan_ownership(v_patient, v_plan, NULL, NULL, 'backfill_unassigned',
        jsonb_build_object('reason', 'owner_not_determinable'));
      PERFORM private.open_unowned_plan_items(v_plan, 'unassigned_legacy_plan', NULL, NULL);
    END IF;

    IF v_plan IS NOT NULL THEN
      UPDATE public.care_plan_versions SET care_plan_id = v_plan WHERE patient_id = v_patient;
      UPDATE public.care_plan_generation_requests SET care_plan_id = v_plan
        WHERE patient_id = v_patient;
    END IF;
  END LOOP;

  -- A request that has no plan to draft into cannot stay open. The document pipeline
  -- re-requests drafting for the right plan once the document is routed or claimed.
  UPDATE public.care_plan_generation_requests
     SET status = 'failed', failure_code = 'owner_unassigned', completed_at = now()
   WHERE care_plan_id IS NULL AND status IN ('pending', 'processing', 'retry');
END;
$backfill$;

ALTER TABLE public.care_plan_versions ALTER COLUMN care_plan_id SET NOT NULL;
ALTER TABLE public.care_plan_generation_requests ADD CONSTRAINT
  care_plan_generation_requests_plan_required
  CHECK (care_plan_id IS NOT NULL OR status IN ('completed', 'failed'));

-- ── 8. Per-plan versions, drafts and generation ───────────────────────────────────────────
-- Version numbers were unique per patient (040); they are now unique per plan. Existing
-- numbers are kept: each backfilled plan holds its patient's whole history, so the new
-- constraint holds by construction. One open draft and one approved version per plan.

ALTER TABLE public.care_plan_versions
  DROP CONSTRAINT care_plan_versions_patient_id_version_number_key;
ALTER TABLE public.care_plan_versions
  ADD CONSTRAINT care_plan_versions_plan_version_number_key UNIQUE (care_plan_id, version_number);
DROP INDEX public.care_plan_versions_one_open_draft;
CREATE UNIQUE INDEX care_plan_versions_one_open_draft
  ON public.care_plan_versions(care_plan_id) WHERE status = 'draft';
CREATE UNIQUE INDEX care_plan_versions_one_approved
  ON public.care_plan_versions(care_plan_id) WHERE status = 'approved';
CREATE INDEX care_plan_versions_plan_status
  ON public.care_plan_versions(care_plan_id, status, version_number DESC);

DROP INDEX public.care_plan_generation_requests_one_open;
CREATE UNIQUE INDEX care_plan_generation_requests_one_open
  ON public.care_plan_generation_requests(care_plan_id)
  WHERE status IN ('pending', 'processing', 'retry') AND care_plan_id IS NOT NULL;

-- A version's patient must be its plan's patient, and a version never changes plans.
CREATE FUNCTION private.care_plan_version_lineage_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE v_patient uuid;
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.care_plan_id IS DISTINCT FROM OLD.care_plan_id THEN
    RAISE EXCEPTION 'a care-plan version cannot move between plans' USING ERRCODE = '23514';
  END IF;
  SELECT patient_id INTO v_patient FROM public.care_plans WHERE id = NEW.care_plan_id;
  IF v_patient IS DISTINCT FROM NEW.patient_id THEN
    RAISE EXCEPTION 'care-plan version and plan belong to different patients'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER care_plan_version_lineage
  BEFORE INSERT OR UPDATE OF care_plan_id, patient_id ON public.care_plan_versions
  FOR EACH ROW EXECUTE FUNCTION private.care_plan_version_lineage_guard();

-- Request drafting for one plan. The legacy patient signature stays for callers that have
-- not moved yet: it succeeds only when exactly one owned plan can receive the request.
CREATE FUNCTION public.request_care_plan_generation_for_plan(
  p_care_plan_id uuid, p_source_watermark timestamptz
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_plan public.care_plans%ROWTYPE;
  v_request public.care_plan_generation_requests%ROWTYPE;
BEGIN
  SELECT * INTO v_plan FROM public.care_plans WHERE id = p_care_plan_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'care plan not found'; END IF;
  PERFORM private.lock_care_plan_evidence(v_plan.patient_id, true);
  SELECT * INTO v_plan FROM public.care_plans WHERE id = p_care_plan_id FOR UPDATE;
  IF v_plan.ownership_state <> 'owned' THEN
    -- Nobody can review a draft for an unowned plan. Adoption re-requests drafting.
    RETURN jsonb_build_object('request_id', NULL, 'status', 'owner_unassigned');
  END IF;
  SELECT * INTO v_request FROM public.care_plan_generation_requests
    WHERE care_plan_id = p_care_plan_id AND status IN ('pending', 'processing', 'retry')
    FOR UPDATE;
  IF FOUND THEN
    UPDATE public.care_plan_generation_requests
       SET source_watermark = GREATEST(source_watermark, p_source_watermark),
           status = 'pending', requested_at = now(), next_attempt_at = NULL,
           claimed_at = NULL, failure_code = NULL
     WHERE id = v_request.id RETURNING * INTO v_request;
  ELSE
    INSERT INTO public.care_plan_generation_requests(patient_id, care_plan_id, source_watermark)
    VALUES (v_plan.patient_id, p_care_plan_id, p_source_watermark) RETURNING * INTO v_request;
  END IF;
  RETURN jsonb_build_object('request_id', v_request.id, 'status', v_request.status);
END;
$$;

CREATE OR REPLACE FUNCTION public.request_care_plan_generation(
  p_patient_id uuid, p_source_watermark timestamptz
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_plans uuid[];
BEGIN
  SELECT array_agg(id ORDER BY id) INTO v_plans FROM public.care_plans
    WHERE patient_id = p_patient_id AND ownership_state = 'owned';
  IF COALESCE(cardinality(v_plans), 0) <> 1 THEN
    RAISE EXCEPTION 'name the care plan to draft: % owned plans', COALESCE(cardinality(v_plans), 0)
      USING ERRCODE = '22023';
  END IF;
  RETURN public.request_care_plan_generation_for_plan(v_plans[1], p_source_watermark);
END;
$$;

-- Claim: the lease and attempt logic of 040, unchanged, now also returning the plan.
CREATE OR REPLACE FUNCTION public.claim_pending_care_plan_generation(p_limit integer DEFAULT 10)
RETURNS SETOF jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_request public.care_plan_generation_requests%ROWTYPE;
BEGIN
  UPDATE public.care_plan_generation_requests
     SET status = 'retry', next_attempt_at = now(), claimed_at = NULL,
         failure_code = 'worker_lease_expired'
   WHERE status = 'processing' AND claimed_at < now() - interval '15 minutes';
  FOR v_request IN
    SELECT * FROM public.care_plan_generation_requests
    WHERE status IN ('pending', 'retry') AND care_plan_id IS NOT NULL
      AND requested_at <= now() - interval '5 minutes'
      AND (next_attempt_at IS NULL OR next_attempt_at <= now())
    ORDER BY requested_at ASC
    FOR UPDATE SKIP LOCKED LIMIT LEAST(GREATEST(p_limit, 1), 100)
  LOOP
    IF v_request.attempts >= 3 THEN
      UPDATE public.care_plan_generation_requests
         SET status = 'failed', failure_code = 'attempt_limit_reached', completed_at = now()
       WHERE id = v_request.id;
      CONTINUE;
    END IF;
    UPDATE public.care_plan_generation_requests
       SET status = 'processing', attempts = attempts + 1, claimed_at = now(),
           next_attempt_at = NULL, failure_code = NULL
     WHERE id = v_request.id;
    RETURN NEXT jsonb_build_object(
      'request_id', v_request.id, 'patient_id', v_request.patient_id,
      'care_plan_id', v_request.care_plan_id,
      'source_watermark', v_request.source_watermark, 'attempt', v_request.attempts + 1);
  END LOOP;
END;
$$;

-- The publication guard (043) compared the patient's latest request. Compare the plan's.
CREATE OR REPLACE FUNCTION public.guard_care_plan_publication() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_request public.care_plan_generation_requests%ROWTYPE;
BEGIN
  IF NEW.status = 'approved' AND OLD.status IS DISTINCT FROM 'approved' THEN
    SELECT * INTO v_request FROM public.care_plan_generation_requests
      WHERE care_plan_id = NEW.care_plan_id ORDER BY created_at DESC LIMIT 1 FOR UPDATE;
    IF FOUND AND (v_request.status <> 'completed'
      OR v_request.source_watermark > NEW.source_watermark
      OR (v_request.source_watermark >= NEW.source_watermark
        AND v_request.plan_version_id IS DISTINCT FROM NEW.id)) THEN
      RAISE EXCEPTION 'automatic generation must complete before publication';
    END IF;
    IF EXISTS (SELECT 1 FROM public.care_plan_items
      WHERE plan_version_id = NEW.id AND NOT is_removed AND (
        btrim(title) = '' OR btrim(instructions) = '' OR btrim(frequency) = ''
        OR lower(btrim(frequency)) = 'as directed'
        OR (category = 'medication' AND (
          NULLIF(btrim(medication->>'name'), '') IS NULL
          OR NULLIF(btrim(medication->>'dosage'), '') IS NULL
          OR NULLIF(btrim(medication->>'route'), '') IS NULL
          OR NULLIF(btrim(medication->>'frequency'), '') IS NULL)))) THEN
      RAISE EXCEPTION 'active care-plan items require complete reviewed instructions';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

-- Generation completion (049) copied the patient's approved items into the open draft.
-- It now copies only this plan's approved version, and the claim must name this plan.
CREATE OR REPLACE FUNCTION private.complete_care_plan_generation(
  p_plan_version_id uuid, p_request_id uuid, p_source_watermark timestamptz, p_items jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_plan public.care_plan_versions%ROWTYPE;
  v_request public.care_plan_generation_requests%ROWTYPE;
  v_item jsonb;
BEGIN
  SELECT * INTO v_plan FROM public.care_plan_versions WHERE id = p_plan_version_id FOR UPDATE;
  IF NOT FOUND OR v_plan.status <> 'draft' THEN
    RAISE EXCEPTION 'care plan is not an open draft';
  END IF;
  SELECT * INTO v_request FROM public.care_plan_generation_requests
    WHERE id = p_request_id FOR UPDATE;
  IF NOT FOUND OR v_request.care_plan_id IS DISTINCT FROM v_plan.care_plan_id
    OR v_request.patient_id <> v_plan.patient_id
    OR v_request.status <> 'processing'
    OR v_request.source_watermark IS DISTINCT FROM p_source_watermark THEN
    RAISE EXCEPTION 'generation claim is no longer current';
  END IF;
  IF jsonb_typeof(p_items) IS DISTINCT FROM 'array'
    OR jsonb_array_length(p_items) NOT BETWEEN 1 AND 100 THEN
    RAISE EXCEPTION 'invalid care plan item batch';
  END IF;
  INSERT INTO public.care_plan_items(plan_version_id, source_fact_id, category, title,
    instructions, frequency, schedule, medication, confidence_score, uncertainty,
    conflict, blocker_reason, source_locale, wording, wording_origin)
  SELECT v_plan.id, i.source_fact_id, i.category, i.title, i.instructions,
    i.frequency, i.schedule, i.medication, i.confidence_score, i.uncertainty,
    i.conflict, i.blocker_reason, i.source_locale, i.wording, i.wording_origin
  FROM public.care_plan_items i JOIN public.care_plan_versions v ON v.id = i.plan_version_id
  WHERE v.care_plan_id = v_plan.care_plan_id AND v.status = 'approved' AND NOT i.is_removed
    AND NOT EXISTS (SELECT 1 FROM public.care_plan_items d
      WHERE d.plan_version_id = v_plan.id AND d.source_fact_id IS NOT DISTINCT FROM i.source_fact_id);
  FOR v_item IN SELECT value FROM jsonb_array_elements(p_items) LOOP
    IF NOT EXISTS (SELECT 1 FROM public.clinical_facts
      WHERE id = (v_item->>'source_fact_id')::uuid AND patient_id = v_plan.patient_id
        AND review_state IN ('pending_review', 'approved')) THEN
      RAISE EXCEPTION 'source fact is not eligible patient evidence';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.care_plan_items
      WHERE plan_version_id = v_plan.id
        AND source_fact_id = (v_item->>'source_fact_id')::uuid) THEN
      INSERT INTO public.care_plan_items(plan_version_id, source_fact_id, category,
        title, instructions, frequency, medication, confidence_score, uncertainty,
        conflict, blocker_reason)
      VALUES (v_plan.id, (v_item->>'source_fact_id')::uuid, v_item->>'category',
        v_item->>'title', v_item->>'instructions', v_item->>'frequency',
        COALESCE(v_item->'medication', '{}'::jsonb),
        (v_item->>'confidence_score')::numeric,
        COALESCE(v_item->'uncertainty', '[]'::jsonb),
        COALESCE(v_item->'conflict', '{}'::jsonb), v_item->>'blocker_reason');
    END IF;
  END LOOP;
  UPDATE public.care_plan_versions SET source_watermark = p_source_watermark,
    generated_at = now(), generation_error_code = NULL WHERE id = v_plan.id;
  INSERT INTO public.care_plan_audit_events(plan_version_id, event_type, event_data)
    VALUES (v_plan.id, 'generated', jsonb_build_object('fact_count', jsonb_array_length(p_items),
      'request_id', p_request_id));
  UPDATE public.care_plan_generation_requests SET status = 'completed',
    plan_version_id = v_plan.id, completed_at = now(), failure_code = NULL,
    claimed_at = NULL WHERE id = v_request.id;
  RETURN jsonb_build_object('plan_version_id', v_plan.id, 'status', 'completed');
END;
$$;

-- ── 9. A care team ends: the plan becomes unowned, nothing is removed ─────────────────────
-- Fires for a status change away from 'active' and for deleting an active link (a clinician
-- account removal). Approved activities, medications and reminders are not touched. When
-- the patient is being deleted too, there is nothing to hand over.

CREATE FUNCTION private.care_team_left() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_plan public.care_plans%ROWTYPE;
  v_ids uuid[];
  v_id uuid;
  v_display jsonb;
BEGIN
  IF TG_OP = 'UPDATE' AND NOT (OLD.status = 'active' AND NEW.status IS DISTINCT FROM 'active') THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'DELETE' AND (OLD.status IS DISTINCT FROM 'active' OR OLD.patient_id IS NULL
      OR NOT EXISTS (SELECT 1 FROM public.patients WHERE id = OLD.patient_id)) THEN
    RETURN OLD;
  END IF;
  SELECT array_agg(id ORDER BY id) INTO v_ids FROM public.care_plans WHERE care_team_id = OLD.id;
  v_display := private.care_team_display(OLD.id);
  FOREACH v_id IN ARRAY COALESCE(v_ids, ARRAY[]::uuid[]) LOOP
    SELECT * INTO v_plan FROM public.care_plans WHERE id = v_id FOR UPDATE;
    IF v_plan.care_team_id IS DISTINCT FROM OLD.id THEN CONTINUE; END IF;
    UPDATE public.care_plans
       SET care_team_id = NULL, ownership_state = 'unowned', unowned_since = clock_timestamp(),
           -- A deleted clinician leaves no name to read; keep the last known display.
           owner_snapshot = CASE WHEN COALESCE(v_display->>'clinician_name', '') = ''
             THEN owner_snapshot ELSE v_display END,
           ownership_revision = ownership_revision + 1
     WHERE id = v_id;
    PERFORM private.log_plan_ownership(v_plan.patient_id, v_id, OLD.id, NULL, 'team_ended',
      jsonb_build_object('trigger', TG_OP, 'approved_activities_kept', true));
    PERFORM private.open_unowned_plan_items(v_id, 'unowned_plan', OLD.id, NULL);
  END LOOP;
  -- Anything addressed to the ended link can no longer be acted on by it.
  UPDATE public.care_plan_review_items SET status = 'withdrawn', resolved_at = clock_timestamp()
   WHERE target_care_team_id = OLD.id AND status = 'open';
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER care_teams_plan_ownership_on_update
  AFTER UPDATE OF status ON public.care_teams
  FOR EACH ROW EXECUTE FUNCTION private.care_team_left();
CREATE TRIGGER care_teams_plan_ownership_on_delete
  BEFORE DELETE ON public.care_teams
  FOR EACH ROW EXECUTE FUNCTION private.care_team_left();

-- ── 10. Adopt a plan and retire items ─────────────────────────────────────────────────────
-- Both are clinician decisions. Authorization is checked before any lock is taken, then
-- again under the locks. Lock order: patient fence, then the plan row, then projections by id.

CREATE FUNCTION public.adopt_care_plan(
  p_care_plan_id uuid, p_actor_id uuid, p_care_team_id uuid, p_note text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_patient uuid;
  v_plan public.care_plans%ROWTYPE;
BEGIN
  IF p_note IS NULL OR char_length(btrim(p_note)) NOT BETWEEN 1 AND 2000 THEN
    RAISE EXCEPTION 'a note is required to adopt a plan' USING ERRCODE = '22023';
  END IF;
  SELECT patient_id INTO v_patient FROM public.care_plans WHERE id = p_care_plan_id;
  IF NOT FOUND OR NOT private.clinician_holds_link(p_actor_id, p_care_team_id)
     OR NOT EXISTS (SELECT 1 FROM public.care_teams
       WHERE id = p_care_team_id AND patient_id = v_patient) THEN
    RAISE EXCEPTION 'care plan unavailable' USING ERRCODE = '42501';
  END IF;
  PERFORM private.lock_care_plan_evidence(v_patient, true);
  SELECT * INTO v_plan FROM public.care_plans WHERE id = p_care_plan_id FOR UPDATE;
  IF NOT private.clinician_holds_link(p_actor_id, p_care_team_id) THEN
    RAISE EXCEPTION 'care plan unavailable' USING ERRCODE = '42501';
  END IF;
  IF v_plan.ownership_state = 'owned' THEN
    -- A retry by the winner is a success; every other caller lost the race.
    IF v_plan.care_team_id = p_care_team_id AND EXISTS (
      SELECT 1 FROM public.care_plan_ownership_events e
      WHERE e.care_plan_id = v_plan.id AND e.event_type = 'plan_adopted'
        AND e.actor_id = p_actor_id AND e.care_team_id = p_care_team_id
        AND (e.event_data->>'ownership_revision')::int = v_plan.ownership_revision) THEN
      RETURN jsonb_build_object('care_plan_id', v_plan.id, 'care_team_id', p_care_team_id,
        'status', 'adopted', 'replayed', true);
    END IF;
    RAISE EXCEPTION 'care plan was adopted by someone else' USING ERRCODE = '40001';
  END IF;
  UPDATE public.care_plans
     SET care_team_id = p_care_team_id, ownership_state = 'owned', unowned_since = NULL,
         origin = CASE WHEN origin = 'native' AND origin_care_team_id = p_care_team_id
           THEN 'native' ELSE 'adopted' END,
         owner_snapshot = private.care_team_display(p_care_team_id),
         ownership_revision = ownership_revision + 1
   WHERE id = v_plan.id
   RETURNING * INTO v_plan;
  UPDATE public.care_plan_review_items
     SET status = 'resolved', resolved_by = p_actor_id, resolved_at = clock_timestamp()
   WHERE care_plan_id = v_plan.id AND status = 'open'
     AND kind IN ('unowned_plan', 'unassigned_legacy_plan');
  PERFORM private.log_plan_ownership(v_plan.patient_id, v_plan.id, p_care_team_id, p_actor_id,
    'plan_adopted', jsonb_build_object('note_length', char_length(btrim(p_note)),
      'ownership_revision', v_plan.ownership_revision));
  RETURN jsonb_build_object('care_plan_id', v_plan.id, 'care_team_id', p_care_team_id,
    'status', 'adopted', 'replayed', false);
END;
$$;

CREATE FUNCTION public.retire_care_plan_items(
  p_care_plan_id uuid, p_actor_id uuid, p_care_team_id uuid, p_item_ids uuid[], p_reason text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_patient uuid;
  v_plan public.care_plans%ROWTYPE;
  v_item public.care_plan_items%ROWTYPE;
  v_ids uuid[];
  v_done integer := 0;
  v_remaining integer;
BEGIN
  IF p_reason IS NULL OR char_length(btrim(p_reason)) NOT BETWEEN 1 AND 2000 THEN
    RAISE EXCEPTION 'a reason is required to retire an activity' USING ERRCODE = '22023';
  END IF;
  IF COALESCE(cardinality(p_item_ids), 0) NOT BETWEEN 1 AND 100 THEN
    RAISE EXCEPTION 'choose between 1 and 100 activities' USING ERRCODE = '22023';
  END IF;
  SELECT patient_id INTO v_patient FROM public.care_plans WHERE id = p_care_plan_id;
  IF NOT FOUND OR NOT private.clinician_holds_link(p_actor_id, p_care_team_id)
     OR NOT EXISTS (SELECT 1 FROM public.care_teams
       WHERE id = p_care_team_id AND patient_id = v_patient) THEN
    RAISE EXCEPTION 'care plan unavailable' USING ERRCODE = '42501';
  END IF;
  PERFORM private.lock_care_plan_evidence(v_patient, true);
  SELECT * INTO v_plan FROM public.care_plans WHERE id = p_care_plan_id FOR UPDATE;
  IF NOT private.clinician_holds_link(p_actor_id, p_care_team_id) THEN
    RAISE EXCEPTION 'care plan unavailable' USING ERRCODE = '42501';
  END IF;
  -- The owner may retire its own items; any active team of the patient may retire from a
  -- plan nobody owns. Another team's owned plan is theirs to change, not ours.
  IF v_plan.ownership_state = 'owned' AND v_plan.care_team_id IS DISTINCT FROM p_care_team_id THEN
    RAISE EXCEPTION 'care plan unavailable' USING ERRCODE = '42501';
  END IF;
  SELECT array_agg(DISTINCT x ORDER BY x) INTO v_ids FROM unnest(p_item_ids) x;
  FOR v_item IN
    SELECT i.* FROM public.care_plan_items i
    JOIN public.care_plan_versions v ON v.id = i.plan_version_id
    WHERE i.id = ANY (v_ids) AND v.care_plan_id = v_plan.id AND v.status = 'approved'
      AND NOT i.is_removed
    ORDER BY i.id
  LOOP
    IF EXISTS (SELECT 1 FROM public.care_plan_item_retirements WHERE item_id = v_item.id) THEN
      CONTINUE;
    END IF;
    IF v_item.projection_type = 'medication' THEN
      PERFORM 1 FROM public.medications WHERE id = v_item.projection_id
        AND patient_id = v_plan.patient_id FOR UPDATE;
      UPDATE public.medications SET is_active = false
        WHERE id = v_item.projection_id AND patient_id = v_plan.patient_id
          AND care_plan_item_id = v_item.id;
    ELSIF v_item.projection_type = 'obligation' THEN
      PERFORM 1 FROM public.obligations WHERE id = v_item.projection_id
        AND patient_id = v_plan.patient_id FOR UPDATE;
      UPDATE public.obligations SET is_active = false
        WHERE id = v_item.projection_id AND patient_id = v_plan.patient_id
          AND care_plan_item_id = v_item.id;
    END IF;
    INSERT INTO public.care_plan_item_retirements(
      item_id, care_plan_id, retired_by, retired_by_care_team_id, reason)
    VALUES (v_item.id, v_plan.id, p_actor_id, p_care_team_id, btrim(p_reason));
    v_done := v_done + 1;
  END LOOP;
  IF v_done = 0 THEN
    RAISE EXCEPTION 'no current activity of this plan matched' USING ERRCODE = '22023';
  END IF;
  PERFORM private.log_plan_ownership(v_plan.patient_id, v_plan.id, p_care_team_id, p_actor_id,
    'items_retired', jsonb_build_object('count', v_done, 'plan_state', v_plan.ownership_state));
  SELECT count(*) INTO v_remaining
    FROM public.care_plan_items i
    JOIN public.care_plan_versions v ON v.id = i.plan_version_id
    WHERE v.care_plan_id = v_plan.id AND v.status = 'approved' AND NOT i.is_removed
      AND NOT EXISTS (SELECT 1 FROM public.care_plan_item_retirements r WHERE r.item_id = i.id);
  IF v_remaining = 0 THEN
    UPDATE public.care_plan_review_items
       SET status = 'resolved', resolved_by = p_actor_id, resolved_at = clock_timestamp()
     WHERE care_plan_id = v_plan.id AND status = 'open'
       AND kind IN ('unowned_plan', 'unassigned_legacy_plan');
  END IF;
  RETURN jsonb_build_object('care_plan_id', v_plan.id, 'retired', v_done, 'remaining', v_remaining);
END;
$$;

-- ── 11. Row-level security: a clinician reads only their own team's plan ──────────────────
-- Direct browser reads were allowed to any clinician assigned to the patient (047). A plan
-- is owned by one care team, so these policies now require the caller's own active link to
-- the plan's owner. The backend (service role) enforces the same rule in services.

CREATE FUNCTION private.clinician_reads_plan(p_care_plan_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = 'pg_catalog' AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.care_plans p
    JOIN public.care_teams t ON t.id = p.care_team_id
    WHERE p.id = p_care_plan_id AND t.clinician_id = auth.uid() AND t.status = 'active'
      AND t.patient_id = p.patient_id);
$$;

ALTER POLICY care_plan_versions_clinician_select ON public.care_plan_versions
  TO authenticated USING (private.is_clinician() AND private.clinician_reads_plan(care_plan_id));
ALTER POLICY care_plan_items_clinician_select ON public.care_plan_items
  TO authenticated USING (EXISTS (
    SELECT 1 FROM public.care_plan_versions v
    WHERE v.id = care_plan_items.plan_version_id
      AND private.is_clinician() AND private.clinician_reads_plan(v.care_plan_id)));
ALTER POLICY care_plan_generation_requests_clinician_select
  ON public.care_plan_generation_requests
  TO authenticated USING (
    private.is_clinician() AND care_plan_id IS NOT NULL
    AND private.clinician_reads_plan(care_plan_id));
ALTER POLICY care_plan_audit_events_clinician_select ON public.care_plan_audit_events
  TO authenticated USING (EXISTS (
    SELECT 1 FROM public.care_plan_versions v
    WHERE v.id = care_plan_audit_events.plan_version_id
      AND private.is_clinician() AND private.clinician_reads_plan(v.care_plan_id)));

-- ── 12. Grants: the new objects are backend-only ──────────────────────────────────────────

ALTER TABLE public.care_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.care_plan_ownership_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.care_plan_review_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.care_plan_item_retirements ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.care_plans, public.care_plan_ownership_events,
  public.care_plan_review_items, public.care_plan_item_retirements
  FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE ON public.care_plans TO service_role;
GRANT SELECT, INSERT ON public.care_plan_ownership_events TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.care_plan_review_items TO service_role;
GRANT SELECT, INSERT ON public.care_plan_item_retirements TO service_role;

REVOKE ALL ON FUNCTION
  private.care_plan_append_only(), private.care_team_display(uuid),
  private.clinician_holds_link(uuid, uuid),
  private.log_plan_ownership(uuid, uuid, uuid, uuid, text, jsonb),
  private.open_unowned_plan_items(uuid, text, uuid, uuid), private.ensure_care_plan(uuid),
  private.care_plan_version_lineage_guard(), private.care_team_left(),
  private.clinician_reads_plan(uuid),
  private.complete_care_plan_generation(uuid, uuid, timestamptz, jsonb),
  public.request_care_plan_generation_for_plan(uuid, timestamptz),
  public.request_care_plan_generation(uuid, timestamptz),
  public.claim_pending_care_plan_generation(integer),
  public.guard_care_plan_publication(),
  public.adopt_care_plan(uuid, uuid, uuid, text),
  public.retire_care_plan_items(uuid, uuid, uuid, uuid[], text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION
  private.care_plan_append_only(), private.care_team_display(uuid),
  private.clinician_holds_link(uuid, uuid),
  private.log_plan_ownership(uuid, uuid, uuid, uuid, text, jsonb),
  private.open_unowned_plan_items(uuid, text, uuid, uuid), private.ensure_care_plan(uuid),
  private.care_plan_version_lineage_guard(), private.care_team_left(),
  private.clinician_reads_plan(uuid),
  private.complete_care_plan_generation(uuid, uuid, timestamptz, jsonb),
  public.request_care_plan_generation_for_plan(uuid, timestamptz),
  public.request_care_plan_generation(uuid, timestamptz),
  public.claim_pending_care_plan_generation(integer),
  public.guard_care_plan_publication(),
  public.adopt_care_plan(uuid, uuid, uuid, text),
  public.retire_care_plan_items(uuid, uuid, uuid, uuid[], text)
  TO service_role;
-- The row-level policies above call this from the caller's own session.
GRANT EXECUTE ON FUNCTION private.clinician_reads_plan(uuid) TO authenticated;

-- ── 13. Verification: fail the migration if a grant, policy or backfill is wrong ──────────

DO $verify$
DECLARE
  v_table text;
  v_function text;
BEGIN
  FOREACH v_table IN ARRAY ARRAY['care_plans', 'care_plan_ownership_events',
    'care_plan_review_items', 'care_plan_item_retirements'] LOOP
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = ('public.' || v_table)::regclass) THEN
      RAISE EXCEPTION 'PLAN-002 verification: RLS is off on %', v_table;
    END IF;
    IF has_table_privilege('anon', 'public.' || v_table, 'SELECT,INSERT,UPDATE,DELETE')
       OR has_table_privilege('authenticated', 'public.' || v_table,
         'SELECT,INSERT,UPDATE,DELETE') THEN
      RAISE EXCEPTION 'PLAN-002 verification: a browser role can reach %', v_table;
    END IF;
  END LOOP;
  IF has_table_privilege('service_role', 'public.care_plan_ownership_events', 'UPDATE')
     OR has_table_privilege('service_role', 'public.care_plan_ownership_events', 'DELETE') THEN
    RAISE EXCEPTION 'PLAN-002 verification: the ownership trail is not append-only';
  END IF;
  FOREACH v_function IN ARRAY ARRAY[
    'public.adopt_care_plan(uuid,uuid,uuid,text)',
    'public.retire_care_plan_items(uuid,uuid,uuid,uuid[],text)',
    'public.request_care_plan_generation_for_plan(uuid,timestamptz)',
    'public.request_care_plan_generation(uuid,timestamptz)',
    'public.claim_pending_care_plan_generation(integer)',
    'private.ensure_care_plan(uuid)', 'private.care_team_left()'] LOOP
    IF has_function_privilege('anon', v_function, 'EXECUTE')
       OR has_function_privilege('authenticated', v_function, 'EXECUTE')
       OR NOT has_function_privilege('service_role', v_function, 'EXECUTE') THEN
      RAISE EXCEPTION 'PLAN-002 verification: wrong execute grants on %', v_function;
    END IF;
  END LOOP;
  IF EXISTS (SELECT 1 FROM public.care_plan_versions WHERE care_plan_id IS NULL) THEN
    RAISE EXCEPTION 'PLAN-002 verification: a version has no plan';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.care_plan_versions v JOIN public.care_plans p ON p.id = v.care_plan_id
    WHERE v.patient_id <> p.patient_id) THEN
    RAISE EXCEPTION 'PLAN-002 verification: a version belongs to another patient''s plan';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'public'
      AND indexname = 'care_plan_versions_one_open_draft'
      AND indexdef LIKE '%(care_plan_id)%') THEN
    RAISE EXCEPTION 'PLAN-002 verification: open drafts are not per plan';
  END IF;
END;
$verify$;
