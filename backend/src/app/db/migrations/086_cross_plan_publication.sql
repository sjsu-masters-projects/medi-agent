-- PLAN-002 / CLN-003 slice H, part 3: cross-plan checks and atomic publication.
--
-- Publishing one plan never touches another plan's activities. Before a draft is published,
-- the database compares it with the patient's other approved plans and the shared medication
-- list, in the same transaction that publishes, under the patient-wide publication lock:
--
--   Blockers  duplicate ingredient or name, conflicting dose/schedule for the same identity,
--             and stop-versus-continue. Each needs a current resolution.
--   Warnings  a non-medication activity that overlaps another plan's. Never blocks, and
--             reveals only that an overlap exists, not the other plan's wording.
--   Not checked: interaction severity. MED-001 excludes that engine; nothing here invents a
--             verdict, and the API reports "interactions: not_checked" explicitly.
--
-- Resolutions (all by the clinician who owns the draft; the other plan is never edited):
--   change or remove the item (the check simply runs again), keep both with a written
--   reason (bound to the exact content of both instructions: if either changes, the
--   acknowledgement is stale), ask the other care team (a review item; stays blocked),
--   or publish without the item (the item is carried into the next draft, still pending).
-- The other care team is always told. The patient's Today is unchanged until publication.
--
-- Retries are idempotent: one key, one actor, one draft, one set of exclusions; the same
-- key with anything different is refused.

CREATE FUNCTION private.norm_text(p_value text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
  SELECT lower(btrim(regexp_replace(COALESCE(p_value, ''), '\s+', ' ', 'g')));
$$;

-- ── 1. Resolutions, review replies and publication records ───────────────────────────────

CREATE TABLE public.care_plan_conflict_resolutions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL REFERENCES public.patients(id) ON DELETE CASCADE,
  care_plan_id uuid NOT NULL REFERENCES public.care_plans(id) ON DELETE CASCADE,
  plan_version_id uuid NOT NULL REFERENCES public.care_plan_versions(id) ON DELETE CASCADE,
  draft_item_id uuid NOT NULL,
  other_care_plan_id uuid,
  -- Binds the decision to both exact instructions; any change makes it stale.
  fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
  resolution text NOT NULL CHECK (resolution IN ('keep_both', 'ask_other_team')),
  reason text NOT NULL CHECK (char_length(btrim(reason)) BETWEEN 1 AND 2000),
  actor_id uuid NOT NULL,
  review_item_count integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE UNIQUE INDEX care_plan_conflict_resolutions_once
  ON public.care_plan_conflict_resolutions(plan_version_id, fingerprint, resolution, actor_id);
CREATE INDEX care_plan_conflict_resolutions_version
  ON public.care_plan_conflict_resolutions(plan_version_id, fingerprint);
CREATE TRIGGER care_plan_conflict_resolutions_append_only
  BEFORE UPDATE OR DELETE ON public.care_plan_conflict_resolutions
  FOR EACH ROW WHEN (pg_trigger_depth() = 0) EXECUTE FUNCTION private.care_plan_append_only();

CREATE TABLE public.care_plan_publications (
  idempotency_key uuid PRIMARY KEY,
  care_plan_id uuid NOT NULL REFERENCES public.care_plans(id) ON DELETE CASCADE,
  plan_version_id uuid NOT NULL REFERENCES public.care_plan_versions(id) ON DELETE CASCADE,
  actor_id uuid NOT NULL,
  -- version, actor and exclusions; the digest of the published items is taken afterwards.
  request_hash text NOT NULL,
  content_digest text NOT NULL,
  result jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE UNIQUE INDEX care_plan_publications_version ON public.care_plan_publications(plan_version_id);

-- ── 2. The cross-plan comparison (the only implementation; preview and publish share it) ──

CREATE FUNCTION private.care_plan_cross_conflicts(
  p_plan_version_id uuid, p_excluded uuid[] DEFAULT ARRAY[]::uuid[]
) RETURNS TABLE (
  kind text, severity text, identity_basis text, draft_item_id uuid, other_item_id uuid,
  other_medication_id uuid, other_care_plan_id uuid, other_care_team_id uuid, fingerprint text
) LANGUAGE sql STABLE SET search_path = '' AS $$
  WITH v AS (
    SELECT id, patient_id, care_plan_id FROM public.care_plan_versions WHERE id = p_plan_version_id
  ), d AS (
    -- The draft's live items, and its medication lines whose source says to stop.
    SELECT i.id AS d_item, i.category AS d_cat, i.instructions AS d_instr,
           i.frequency AS d_freq, i.schedule AS d_sched, i.wording AS d_word,
           i.medication AS d_med, i.is_removed AS d_removed,
           COALESCE(i.conflict->>'kind' = 'medication_stop_source', false) AS d_stop,
           CASE WHEN i.medication->>'target_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
             THEN (i.medication->>'target_id')::uuid END AS d_mid,
           CASE WHEN i.medication->>'ingredient_rxcui' ~ '^[0-9]+$'
             THEN i.medication->>'ingredient_rxcui' END AS d_ing,
           private.norm_text(i.medication->>'name') AS d_name,
           v.id AS d_version, v.care_plan_id AS d_plan
    FROM public.care_plan_items i JOIN v ON v.id = i.plan_version_id
    WHERE NOT (i.id = ANY (COALESCE(p_excluded, ARRAY[]::uuid[])))
      AND (NOT i.is_removed
        OR (i.category = 'medication' AND i.conflict->>'kind' = 'medication_stop_source'))
  ), o AS (
    -- Other plans: live approved activities, a recorded stop, and shared-list entries that
    -- no plan owns. A retired or deactivated activity is not "live".
    SELECT i.id AS o_item, NULL::uuid AS o_shared, i.category AS o_cat, i.instructions AS o_instr,
           i.frequency AS o_freq, i.schedule AS o_sched, i.medication AS o_med,
           false AS o_stop, p.id AS o_plan, p.care_team_id AS o_team,
           CASE WHEN i.projection_type = 'medication' THEN i.projection_id END AS o_mid,
           CASE WHEN i.medication->>'ingredient_rxcui' ~ '^[0-9]+$'
             THEN i.medication->>'ingredient_rxcui' END AS o_ing,
           private.norm_text(i.medication->>'name') AS o_name, ov.id AS o_version, i.wording AS o_word
    FROM public.care_plan_items i
    JOIN public.care_plan_versions ov ON ov.id = i.plan_version_id AND ov.status = 'approved'
    JOIN public.care_plans p ON p.id = ov.care_plan_id
    JOIN v ON v.patient_id = ov.patient_id AND ov.care_plan_id <> v.care_plan_id
    WHERE NOT i.is_removed
      AND NOT EXISTS (SELECT 1 FROM public.care_plan_item_retirements r WHERE r.item_id = i.id)
      AND ((i.projection_type = 'medication' AND EXISTS (
            SELECT 1 FROM public.medications m
            WHERE m.id = i.projection_id AND m.is_active AND m.care_plan_item_id = i.id))
        OR (i.projection_type = 'obligation' AND EXISTS (
            SELECT 1 FROM public.obligations ob
            WHERE ob.id = i.projection_id AND ob.is_active AND ob.care_plan_item_id = i.id)))
    UNION ALL
    SELECT i.id, NULL::uuid, i.category, i.instructions, i.frequency, i.schedule, i.medication,
           true, p.id, p.care_team_id, NULL::uuid,
           CASE WHEN i.medication->>'ingredient_rxcui' ~ '^[0-9]+$'
             THEN i.medication->>'ingredient_rxcui' END,
           private.norm_text(i.medication->>'name'), ov.id, i.wording
    FROM public.care_plan_items i
    JOIN public.care_plan_versions ov ON ov.id = i.plan_version_id AND ov.status = 'approved'
    JOIN public.care_plans p ON p.id = ov.care_plan_id
    JOIN v ON v.patient_id = ov.patient_id AND ov.care_plan_id <> v.care_plan_id
    WHERE i.is_removed AND i.category = 'medication'
      AND i.conflict->>'kind' = 'medication_stop_source'
    UNION ALL
    SELECT NULL::uuid, m.id, 'medication', COALESCE(m.instructions, ''), m.frequency, '{}'::jsonb,
           jsonb_build_object('name', m.name, 'dosage', m.dosage, 'frequency', m.frequency,
             'route', m.route::text),
           false, NULL::uuid, m.prescribed_by_care_team_id, m.id, NULL,
           private.norm_text(m.name), NULL::uuid, '{}'::jsonb
    FROM public.medications m JOIN v ON v.patient_id = m.patient_id
    WHERE m.is_active AND m.care_plan_item_id IS NULL
  ), pairs AS (
    SELECT d.*, o.*,
      CASE WHEN d.d_mid IS NOT NULL AND d.d_mid = o.o_mid THEN 'canonical_target'
           WHEN d.d_ing IS NOT NULL AND d.d_ing = o.o_ing THEN 'recorded_ingredient'
           WHEN d.d_name <> '' AND d.d_name = o.o_name THEN 'recorded_name' END AS basis
    FROM d JOIN o ON d.d_cat = 'medication' AND o.o_cat = 'medication'
    -- Updating a shared-list entry is the plan adopting it, not a conflict with it.
    WHERE NOT (o.o_item IS NULL AND d.d_mid IS NOT NULL AND d.d_mid = o.o_mid)
  ), conflicts AS (
    SELECT basis,
      CASE WHEN d_stop <> o_stop THEN 'stop_continue'
           WHEN private.norm_text(d_med->>'dosage') <> private.norm_text(o_med->>'dosage')
             OR private.norm_text(d_med->>'frequency') <> private.norm_text(o_med->>'frequency')
             OR private.norm_text(d_med->>'route') <> private.norm_text(o_med->>'route')
             OR private.norm_text(d_instr) <> private.norm_text(o_instr)
             OR d_sched <> o_sched THEN 'regimen_difference'
           ELSE 'duplicate_medication' END AS kind,
      'blocker'::text AS severity, pairs.d_item, pairs.o_item, pairs.o_shared, pairs.o_plan, pairs.o_team,
      jsonb_build_object('draft', jsonb_build_object('version', d_version, 'item', d_item,
          'target', d_mid, 'ingredient', d_ing, 'name', d_med->>'name', 'dosage', d_med->>'dosage',
          'frequency', d_freq, 'route', d_med->>'route', 'instructions', d_instr, 'stop', d_stop,
          'schedule', d_sched, 'wording', d_word),
        'other', jsonb_build_object('version', o_version, 'item', o_item, 'shared', o_shared,
          'plan', o_plan, 'target', o_mid, 'ingredient', o_ing, 'name', o_med->>'name',
          'dosage', o_med->>'dosage', 'frequency', o_freq, 'route', o_med->>'route',
          'instructions', o_instr, 'stop', o_stop, 'schedule', o_sched, 'wording', o_word)) AS snapshot
    FROM pairs
    WHERE basis IS NOT NULL AND NOT (d_stop AND o_stop)
    UNION ALL
    SELECT 'activity_instruction', 'schedule_overlap', 'warning', d.d_item, o.o_item, o.o_shared,
      o.o_plan, o.o_team,
      jsonb_build_object('draft', jsonb_build_object('version', d.d_version, 'item', d.d_item,
          'category', d.d_cat, 'instructions', d.d_instr, 'schedule', d.d_sched),
        'other', jsonb_build_object('version', o.o_version, 'item', o.o_item, 'plan', o.o_plan,
          'category', o.o_cat, 'instructions', o.o_instr, 'schedule', o.o_sched))
    FROM d JOIN o ON d.d_cat <> 'medication' AND NOT d.d_removed AND o.o_cat = d.d_cat
      AND o.o_item IS NOT NULL AND private.norm_text(d.d_instr) = private.norm_text(o.o_instr)
  )
  SELECT c.kind, c.severity, c.basis, c.d_item, c.o_item, c.o_shared, c.o_plan, c.o_team,
         encode(sha256(convert_to(jsonb_build_object('schema', 'cross-plan-review/v1',
           'kind', c.kind, 'basis', c.basis, 'snapshot', c.snapshot)::text, 'UTF8')), 'hex')
  FROM conflicts c
  ORDER BY c.d_item, c.o_item NULLS LAST, c.o_shared NULLS FIRST;
$$;

-- ── 3. Review items for the other care team ──────────────────────────────────────────────

-- Tell the owner of the other instruction. An unowned or unassigned plan, or a shared-list
-- entry whose recording team has ended, is told to every other active team of the patient.
CREATE FUNCTION private.open_conflict_items(
  p_source_plan uuid, p_other_plan uuid, p_other_team uuid, p_kind text, p_fingerprint text,
  p_summary jsonb, p_note text, p_actor uuid
) RETURNS integer LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_source public.care_plans%ROWTYPE;
  v_target uuid;
  v_count integer := 0;
  v_rows integer;
  v_targets uuid[];
BEGIN
  SELECT * INTO v_source FROM public.care_plans WHERE id = p_source_plan;
  IF p_other_team IS NOT NULL AND EXISTS (
    SELECT 1 FROM public.care_teams WHERE id = p_other_team AND status = 'active'
      AND patient_id = v_source.patient_id) THEN
    v_targets := ARRAY[p_other_team];
  ELSE
    SELECT COALESCE(array_agg(t.id ORDER BY t.id), ARRAY[]::uuid[]) INTO v_targets
      FROM public.care_teams t
     WHERE t.patient_id = v_source.patient_id AND t.status = 'active'
       AND t.id IS DISTINCT FROM v_source.care_team_id;
  END IF;
  FOREACH v_target IN ARRAY v_targets LOOP
    INSERT INTO public.care_plan_review_items(patient_id, care_plan_id, kind, target_care_team_id,
      source_care_plan_id, conflict_fingerprint, summary, request_note, created_by)
    VALUES (v_source.patient_id, p_source_plan, p_kind, v_target, p_source_plan, p_fingerprint,
      p_summary, p_note, p_actor)
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    v_count := v_count + v_rows;
  END LOOP;
  RETURN v_count;
END;
$$;

-- What the other team may be told about a conflict: the two medication instructions and
-- plan metadata. Never a source document, a title, a note or non-medication wording.
CREATE FUNCTION private.conflict_summary(
  p_plan_version_id uuid, p_kind text, p_severity text, p_basis text, p_draft_item uuid,
  p_other_item uuid, p_other_medication uuid
) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = '' AS $$
  SELECT jsonb_build_object(
    'kind', p_kind, 'severity', p_severity, 'identity_basis', p_basis,
    'from', (SELECT p.owner_snapshot FROM public.care_plan_versions v
      JOIN public.care_plans p ON p.id = v.care_plan_id WHERE v.id = p_plan_version_id),
    'ours', (SELECT CASE WHEN i.category = 'medication' THEN jsonb_build_object(
        'name', i.medication->>'name', 'dosage', i.medication->>'dosage',
        'frequency', i.medication->>'frequency', 'route', i.medication->>'route',
        'instructions', i.instructions) ELSE jsonb_build_object('category', i.category) END
      FROM public.care_plan_items i WHERE i.id = p_draft_item),
    'theirs', CASE WHEN p_other_item IS NOT NULL THEN
      (SELECT CASE WHEN i.category = 'medication' THEN jsonb_build_object(
        'name', i.medication->>'name', 'dosage', i.medication->>'dosage',
        'frequency', i.medication->>'frequency', 'route', i.medication->>'route',
        'instructions', i.instructions) ELSE jsonb_build_object('category', i.category) END
       FROM public.care_plan_items i WHERE i.id = p_other_item)
      ELSE (SELECT jsonb_build_object('name', m.name, 'dosage', m.dosage,
        'frequency', m.frequency, 'route', m.route::text, 'instructions', m.instructions,
        'shared_list', true) FROM public.medications m WHERE m.id = p_other_medication) END);
$$;

-- ── 4. Preview: conflicts with both instructions and the other plan's metadata only ──────

CREATE FUNCTION public.care_plan_cross_plan_review(p_plan_version_id uuid, p_reviewer_id uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_version public.care_plan_versions%ROWTYPE;
  v_plan public.care_plans%ROWTYPE;
BEGIN
  SELECT * INTO v_version FROM public.care_plan_versions WHERE id = p_plan_version_id;
  SELECT * INTO v_plan FROM public.care_plans WHERE id = v_version.care_plan_id;
  IF NOT FOUND OR v_plan.ownership_state <> 'owned'
     OR NOT private.clinician_holds_link(p_reviewer_id, v_plan.care_team_id) THEN
    RAISE EXCEPTION 'care plan unavailable' USING ERRCODE = '42501';
  END IF;
  RETURN jsonb_build_object(
    'interaction_coverage', 'not_checked',
    'conflicts', COALESCE((
      SELECT jsonb_agg(jsonb_build_object(
        'fingerprint', c.fingerprint, 'kind', c.kind, 'severity', c.severity,
        'identity_basis', c.identity_basis, 'draft_item_id', c.draft_item_id,
        'ours', private.conflict_summary(p_plan_version_id, c.kind, c.severity, c.identity_basis,
          c.draft_item_id, c.other_item_id, c.other_medication_id)->'ours',
        'theirs', private.conflict_summary(p_plan_version_id, c.kind, c.severity, c.identity_basis,
          c.draft_item_id, c.other_item_id, c.other_medication_id)->'theirs',
        'other_plan', CASE WHEN c.other_care_plan_id IS NULL THEN NULL ELSE (
          SELECT jsonb_build_object('care_plan_id', op.id, 'ownership_state', op.ownership_state,
            'specialty', op.owner_snapshot->'specialty',
            'clinician_name', op.owner_snapshot->'clinician_name',
            'clinic_name', op.owner_snapshot->'clinic_name',
            'approved_at', (SELECT max(ov.approved_at) FROM public.care_plan_versions ov
              WHERE ov.care_plan_id = op.id AND ov.status = 'approved'))
          FROM public.care_plans op WHERE op.id = c.other_care_plan_id) END,
        'shared_list_entry_id', c.other_medication_id,
        'acknowledged', EXISTS (SELECT 1 FROM public.care_plan_conflict_resolutions r
          WHERE r.plan_version_id = p_plan_version_id AND r.fingerprint = c.fingerprint
            AND r.resolution = 'keep_both'),
        'acknowledged_reason', (SELECT r.reason FROM public.care_plan_conflict_resolutions r
          WHERE r.plan_version_id = p_plan_version_id AND r.fingerprint = c.fingerprint
            AND r.resolution = 'keep_both' ORDER BY r.created_at DESC LIMIT 1),
        'asked_other_team', EXISTS (SELECT 1 FROM public.care_plan_conflict_resolutions r
          WHERE r.plan_version_id = p_plan_version_id AND r.fingerprint = c.fingerprint
            AND r.resolution = 'ask_other_team'))
        ORDER BY c.draft_item_id, c.fingerprint)
      FROM private.care_plan_cross_conflicts(p_plan_version_id) c), '[]'::jsonb));
END;
$$;

-- ── 5. Record a resolution: keep both with a reason, or ask the other care team ──────────

CREATE FUNCTION public.record_cross_plan_resolution(
  p_plan_version_id uuid, p_actor_id uuid, p_fingerprint text, p_resolution text, p_reason text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_version public.care_plan_versions%ROWTYPE;
  v_plan public.care_plans%ROWTYPE;
  v_conflict record;
  v_existing public.care_plan_conflict_resolutions%ROWTYPE;
  v_items integer;
BEGIN
  IF p_resolution NOT IN ('keep_both', 'ask_other_team') THEN
    RAISE EXCEPTION 'unsupported resolution' USING ERRCODE = '22023';
  END IF;
  IF p_reason IS NULL OR char_length(btrim(p_reason)) NOT BETWEEN 1 AND 2000 THEN
    RAISE EXCEPTION 'a written reason is required' USING ERRCODE = '22023';
  END IF;
  SELECT * INTO v_version FROM public.care_plan_versions WHERE id = p_plan_version_id;
  SELECT * INTO v_plan FROM public.care_plans WHERE id = v_version.care_plan_id;
  IF NOT FOUND OR v_plan.ownership_state <> 'owned'
     OR NOT private.clinician_holds_link(p_actor_id, v_plan.care_team_id) THEN
    RAISE EXCEPTION 'care plan unavailable' USING ERRCODE = '42501';
  END IF;
  PERFORM private.lock_care_plan_evidence(v_version.patient_id, true);
  SELECT * INTO v_plan FROM public.care_plans WHERE id = v_version.care_plan_id FOR UPDATE;
  SELECT * INTO v_version FROM public.care_plan_versions WHERE id = p_plan_version_id FOR UPDATE;
  IF v_version.status <> 'draft' OR v_plan.ownership_state <> 'owned'
     OR NOT private.clinician_holds_link(p_actor_id, v_plan.care_team_id) THEN
    RAISE EXCEPTION 'care plan unavailable' USING ERRCODE = '42501';
  END IF;
  SELECT * INTO v_conflict FROM private.care_plan_cross_conflicts(p_plan_version_id) c
    WHERE c.fingerprint = p_fingerprint AND c.severity = 'blocker';
  IF NOT FOUND THEN
    -- Either an edit or a publication changed one of the two instructions: stale.
    RAISE EXCEPTION 'this conflict has changed; review it again' USING ERRCODE = '40001';
  END IF;
  SELECT * INTO v_existing FROM public.care_plan_conflict_resolutions
    WHERE plan_version_id = p_plan_version_id AND fingerprint = p_fingerprint
      AND resolution = p_resolution AND actor_id = p_actor_id;
  IF FOUND THEN
    RETURN jsonb_build_object('fingerprint', p_fingerprint, 'resolution', p_resolution,
      'replayed', true);
  END IF;
  v_items := private.open_conflict_items(v_plan.id, v_conflict.other_care_plan_id,
    v_conflict.other_care_team_id,
    CASE p_resolution WHEN 'ask_other_team' THEN 'cross_plan_conflict' ELSE 'conflict_acknowledged' END,
    p_fingerprint,
    private.conflict_summary(p_plan_version_id, v_conflict.kind, v_conflict.severity,
      v_conflict.identity_basis, v_conflict.draft_item_id, v_conflict.other_item_id,
      v_conflict.other_medication_id),
    btrim(p_reason), p_actor_id);
  INSERT INTO public.care_plan_conflict_resolutions(patient_id, care_plan_id, plan_version_id,
    draft_item_id, other_care_plan_id, fingerprint, resolution, reason, actor_id, review_item_count)
  VALUES (v_version.patient_id, v_plan.id, p_plan_version_id, v_conflict.draft_item_id,
    v_conflict.other_care_plan_id, p_fingerprint, p_resolution, btrim(p_reason), p_actor_id, v_items);
  INSERT INTO public.care_plan_audit_events(plan_version_id, actor_id, event_type, event_data)
  VALUES (p_plan_version_id, p_actor_id, 'cross_plan_resolution',
    jsonb_build_object('fingerprint', p_fingerprint, 'resolution', p_resolution,
      'kind', v_conflict.kind, 'review_items', v_items));
  RETURN jsonb_build_object('fingerprint', p_fingerprint, 'resolution', p_resolution,
    'review_items', v_items, 'replayed', false);
END;
$$;

-- The other team answers. The answer informs the asker; it does not clear the blocker.
CREATE FUNCTION public.reply_care_plan_review_item(
  p_item_id uuid, p_actor_id uuid, p_note text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_item public.care_plan_review_items%ROWTYPE;
  v_source public.care_plans%ROWTYPE;
BEGIN
  SELECT * INTO v_item FROM public.care_plan_review_items WHERE id = p_item_id;
  IF NOT FOUND OR v_item.target_care_team_id IS NULL
     OR NOT private.clinician_holds_link(p_actor_id, v_item.target_care_team_id)
     OR v_item.kind NOT IN ('cross_plan_conflict', 'conflict_acknowledged',
       'conflict_published_without') THEN
    RAISE EXCEPTION 'review item unavailable' USING ERRCODE = '42501';
  END IF;
  IF v_item.kind = 'cross_plan_conflict'
     AND (p_note IS NULL OR char_length(btrim(p_note)) NOT BETWEEN 1 AND 2000) THEN
    RAISE EXCEPTION 'a reply is required' USING ERRCODE = '22023';
  END IF;
  IF p_note IS NOT NULL AND char_length(btrim(p_note)) > 2000 THEN
    RAISE EXCEPTION 'a reply is required' USING ERRCODE = '22023';
  END IF;
  SELECT * INTO v_item FROM public.care_plan_review_items WHERE id = p_item_id FOR UPDATE;
  IF v_item.status <> 'open' THEN
    RETURN jsonb_build_object('id', p_item_id, 'status', v_item.status, 'replayed', true);
  END IF;
  UPDATE public.care_plan_review_items
     SET status = 'resolved', reply_note = NULLIF(btrim(p_note), ''), resolved_by = p_actor_id,
         resolved_at = clock_timestamp()
   WHERE id = p_item_id;
  SELECT * INTO v_source FROM public.care_plans WHERE id = v_item.source_care_plan_id;
  IF FOUND AND v_source.care_team_id IS NOT NULL AND v_item.kind = 'cross_plan_conflict' THEN
    INSERT INTO public.care_plan_review_items(patient_id, care_plan_id, kind, target_care_team_id,
      source_care_plan_id, conflict_fingerprint, summary, request_note, created_by)
    VALUES (v_item.patient_id, v_source.id, 'conflict_reply', v_source.care_team_id, v_source.id,
      v_item.conflict_fingerprint, v_item.summary, NULLIF(btrim(p_note), ''), p_actor_id)
    ON CONFLICT DO NOTHING;
  END IF;
  RETURN jsonb_build_object('id', p_item_id, 'status', 'resolved', 'replayed', false);
END;
$$;

-- ── 6. Publication core: the 049 body, scoped to one plan ─────────────────────────────────
-- Changes from 049, and nothing else: the reviewer must own this plan (not merely be
-- assigned to the patient); the recorded team is the plan's team; only this plan's previous
-- approved version is superseded and only its projections are switched off; a medication
-- that another plan's activity owns cannot be updated from here; a duplicate active name
-- is allowed only for an item whose conflict was acknowledged with a written reason.

CREATE FUNCTION private.publish_care_plan_core(
  p_plan_version_id uuid,
  p_reviewer_id uuid,
  p_note text,
  p_acknowledged jsonb
) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE
  v_plan public.care_plan_versions%ROWTYPE;
  v_cplan public.care_plans%ROWTYPE;
  v_old_plan public.care_plan_versions%ROWTYPE;
  v_item public.care_plan_items%ROWTYPE;
  v_recommendation_id uuid;
  v_care_team_id uuid;
  v_projection_id uuid;
  v_evidence jsonb;
  v_route public.medication_route_enum;
  v_locale text;
  v_target_id uuid;
  v_continuity jsonb := '{}'::jsonb;
BEGIN
  SELECT * INTO v_plan FROM public.care_plan_versions WHERE id = p_plan_version_id FOR UPDATE;
  IF NOT FOUND OR v_plan.status <> 'draft' THEN
    RAISE EXCEPTION 'care plan draft is not eligible for approval';
  END IF;
  SELECT * INTO v_cplan FROM public.care_plans WHERE id = v_plan.care_plan_id;
  IF NOT FOUND OR v_cplan.ownership_state <> 'owned'
     OR NOT private.clinician_holds_link(p_reviewer_id, v_cplan.care_team_id) THEN
    RAISE EXCEPTION 'clinician does not own this care plan' USING ERRCODE = '42501';
  END IF;
  -- Records written below are attributed to this plan's team, never to a guess.
  PERFORM set_config('mediagent.recording_care_team', v_cplan.care_team_id::text, true);
  SELECT COALESCE(NULLIF(preferred_language::text, ''), 'en-US') INTO v_locale
  FROM public.patients WHERE id = v_plan.patient_id FOR UPDATE;
  -- Both languages are reviewed together, so a later language switch needs no new review.
  IF EXISTS (
    SELECT 1 FROM public.care_plan_items
    WHERE plan_version_id = p_plan_version_id AND NOT is_removed
      AND NOT (wording_verified AND private.care_plan_wording_is_complete(
        wording, source_locale, title, instructions, frequency))
  ) THEN
    RAISE EXCEPTION 'every patient-facing item needs verified English and Spanish wording';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.care_plan_items
    WHERE plan_version_id = p_plan_version_id AND NOT is_removed
      AND blocker_reason IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'all care-plan blockers must be resolved before approval';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.care_plan_items
    WHERE plan_version_id = p_plan_version_id AND category = 'medication' AND NOT is_removed
      AND medication->>'decision' = 'update'
    GROUP BY medication->>'target_id' HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'two plan items cannot update one medication';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.care_plan_items
    WHERE plan_version_id = p_plan_version_id AND category = 'medication' AND NOT is_removed
      AND medication->>'decision' = 'create'
    GROUP BY lower(trim(medication->>'name')) HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'two plan items cannot create the same medication';
  END IF;
  -- Validate against current canonical state while the plan is still a draft.
  -- Any failure occurs before recommendation, supersession, or projection writes.
  FOR v_item IN SELECT * FROM public.care_plan_items
    WHERE plan_version_id = p_plan_version_id AND category = 'medication' AND NOT is_removed
  LOOP
    IF trim(v_item.frequency) IS DISTINCT FROM trim(v_item.medication->>'frequency') THEN
      RAISE EXCEPTION 'medication frequency must match the patient-facing item';
    END IF;
    IF v_item.medication->>'decision' = 'create'
       AND NULLIF(v_item.medication->>'target_id', '') IS NULL THEN
      IF EXISTS (
        SELECT 1 FROM public.medications
        WHERE patient_id = v_plan.patient_id AND is_active
          AND lower(trim(name)) = lower(trim(v_item.medication->>'name'))
      ) AND NOT (p_acknowledged ? v_item.id::text) THEN
        RAISE EXCEPTION 'active medication already exists; choose an update decision';
      END IF;
    ELSIF v_item.medication->>'decision' = 'update'
      AND NULLIF(v_item.medication->>'target_id', '') IS NOT NULL THEN
      v_target_id := (v_item.medication->>'target_id')::uuid;
      -- Another plan's activity is changed by that plan, never from here.
      IF EXISTS (
        SELECT 1 FROM public.medications m
        JOIN public.care_plan_items ci ON ci.id = m.care_plan_item_id
        JOIN public.care_plan_versions cv ON cv.id = ci.plan_version_id
        WHERE m.id = v_target_id AND cv.care_plan_id <> v_plan.care_plan_id
      ) THEN
        RAISE EXCEPTION 'medication belongs to another care plan';
      END IF;
      PERFORM 1 FROM public.medications
      WHERE id = v_target_id AND patient_id = v_plan.patient_id AND is_active
        AND lower(trim(name)) = lower(trim(v_item.medication->>'name')) FOR UPDATE;
      IF NOT FOUND THEN
        RAISE EXCEPTION 'medication update target is not an active matching patient record';
      END IF;
    ELSE
      RAISE EXCEPTION 'medication projection needs an explicit create or update decision';
    END IF;
  END LOOP;
  SELECT jsonb_agg(jsonb_build_object('fact_id', source_fact_id)) INTO v_evidence
  FROM public.care_plan_items
  WHERE plan_version_id = p_plan_version_id AND NOT is_removed AND source_fact_id IS NOT NULL;
  IF v_evidence IS NULL OR jsonb_array_length(v_evidence) = 0 THEN
    RAISE EXCEPTION 'care plan needs evidence-backed items before approval';
  END IF;
  v_care_team_id := v_cplan.care_team_id;

  INSERT INTO public.clinical_recommendations(
    patient_id, action_type, proposed_payload, evidence, rationale, proposer_type, proposer_reference, state
  ) VALUES (
    v_plan.patient_id, 'publish_care_plan', jsonb_build_object('plan_version_id', v_plan.id),
    v_evidence, 'Evidence-backed care plan draft awaiting assigned clinician approval.',
    'document_evidence_agent', v_plan.id::text, 'executed'
  ) RETURNING id INTO v_recommendation_id;
  INSERT INTO public.approval_decisions(recommendation_id, reviewer_id, decision, note, edited_payload)
  VALUES (v_recommendation_id, p_reviewer_id, 'approve', p_note,
    jsonb_build_object('plan_version_id', v_plan.id, 'version_number', v_plan.version_number));
  INSERT INTO public.clinical_action_audit_records(recommendation_id, actor_id, event_type, event_data)
  VALUES
    (v_recommendation_id, NULL, 'proposed', jsonb_build_object('proposer_type', 'document_evidence_agent')),
    (v_recommendation_id, p_reviewer_id, 'approved', jsonb_build_object('plan_version_id', v_plan.id)),
    (v_recommendation_id, p_reviewer_id, 'executed', jsonb_build_object('plan_version_id', v_plan.id));

  SELECT * INTO v_old_plan FROM public.care_plan_versions
  WHERE care_plan_id = v_plan.care_plan_id AND status = 'approved' FOR UPDATE;
  IF FOUND THEN
    -- Lock prior canonical activities before comparing them. Retain identity only
    -- for one exact source-backed, unchanged item; never merge distinct evidence.
    PERFORM 1 FROM public.obligations
    WHERE care_plan_item_id IN (
      SELECT id FROM public.care_plan_items WHERE plan_version_id = v_old_plan.id
    ) ORDER BY id FOR UPDATE;
    SELECT COALESCE(jsonb_object_agg(new_item.id::text, matching.id::text), '{}'::jsonb)
    INTO v_continuity
    FROM public.care_plan_items new_item
    CROSS JOIN LATERAL (
      SELECT (array_agg(o.id ORDER BY o.id))[1] AS id
      FROM public.care_plan_items old_item
      JOIN public.obligations o ON o.id = old_item.projection_id
      WHERE old_item.plan_version_id = v_old_plan.id AND NOT old_item.is_removed
        AND old_item.projection_type = 'obligation'
        AND old_item.source_fact_id = new_item.source_fact_id
        AND old_item.category = new_item.category
        AND old_item.title = new_item.title
        AND old_item.instructions = new_item.instructions
        AND old_item.frequency = new_item.frequency
        AND old_item.schedule = new_item.schedule
        AND o.patient_id = v_plan.patient_id AND o.is_active
        AND o.care_plan_item_id = old_item.id
        AND o.description = old_item.title AND o.notes = old_item.instructions
        AND o.frequency = old_item.frequency
        AND o.obligation_type = CASE old_item.category
          WHEN 'nutrition' THEN 'diet'::public.obligation_type_enum
          WHEN 'movement' THEN 'exercise'::public.obligation_type_enum
          ELSE 'custom'::public.obligation_type_enum END
      HAVING count(*) = 1
    ) matching
    WHERE new_item.plan_version_id = v_plan.id AND NOT new_item.is_removed
      AND new_item.category <> 'medication' AND new_item.source_fact_id IS NOT NULL;
    UPDATE public.medications SET is_active = false
    WHERE care_plan_item_id IN (SELECT id FROM public.care_plan_items WHERE plan_version_id = v_old_plan.id);
    UPDATE public.obligations SET is_active = false
    WHERE care_plan_item_id IN (SELECT id FROM public.care_plan_items WHERE plan_version_id = v_old_plan.id);
    UPDATE public.care_plan_versions SET status = 'superseded', superseded_at = now()
    WHERE id = v_old_plan.id;
  END IF;

  FOR v_item IN SELECT * FROM public.care_plan_items
    WHERE plan_version_id = v_plan.id AND NOT is_removed ORDER BY created_at
  LOOP
    IF v_item.category = 'medication' THEN
      IF lower(COALESCE(v_item.medication->>'route', '')) NOT IN (
        'oral', 'topical', 'inhaled', 'iv', 'im', 'subcutaneous'
      ) THEN
        RAISE EXCEPTION 'medication route is required and must be supported before approval';
      END IF;
      v_route := CASE lower(v_item.medication->>'route')
        WHEN 'oral' THEN 'oral'::public.medication_route_enum
        WHEN 'topical' THEN 'topical'::public.medication_route_enum
        WHEN 'inhaled' THEN 'inhaled'::public.medication_route_enum
        WHEN 'iv' THEN 'iv'::public.medication_route_enum
        WHEN 'im' THEN 'im'::public.medication_route_enum
        WHEN 'subcutaneous' THEN 'subcutaneous'::public.medication_route_enum
        ELSE NULL
      END;
      IF v_item.medication->>'decision' = 'update' THEN
        UPDATE public.medications SET
          name = v_item.medication->>'name', dosage = v_item.medication->>'dosage',
          frequency = v_item.medication->>'frequency', route = v_route,
          instructions = v_item.instructions, is_active = true, care_plan_item_id = v_item.id,
          patient_wording = v_item.wording
        WHERE id = (v_item.medication->>'target_id')::uuid AND patient_id = v_plan.patient_id
        RETURNING id INTO v_projection_id;
      ELSE
        INSERT INTO public.medications(
          patient_id, name, dosage, frequency, route, instructions,
          prescribed_by_care_team_id, start_date, end_date, is_active, care_plan_item_id,
          patient_wording
        ) VALUES (
          v_plan.patient_id, v_item.medication->>'name', v_item.medication->>'dosage',
          v_item.medication->>'frequency', v_route, v_item.instructions, v_care_team_id,
          NULLIF(v_item.schedule->>'start_date', '')::date,
          NULLIF(v_item.schedule->>'end_date', '')::date, true, v_item.id, v_item.wording
        ) RETURNING id INTO v_projection_id;
      END IF;
      UPDATE public.care_plan_items SET projection_type = 'medication', projection_id = v_projection_id
      WHERE id = v_item.id;
    ELSE
      v_projection_id := NULLIF(v_continuity->>v_item.id::text, '')::uuid;
      IF v_projection_id IS NOT NULL THEN
        -- Reminder settings and adherence logs reference this stable identity.
        -- Historical item projection references remain immutable.
        UPDATE public.obligations SET is_active = true, care_plan_item_id = v_item.id,
          patient_wording = v_item.wording
        WHERE id = v_projection_id AND patient_id = v_plan.patient_id;
      ELSE
      INSERT INTO public.obligations(
        patient_id, obligation_type, description, frequency, notes, set_by_care_team_id,
        is_active, care_plan_item_id, patient_wording
      ) VALUES (
        v_plan.patient_id,
        CASE v_item.category WHEN 'nutrition' THEN 'diet'::public.obligation_type_enum
          WHEN 'movement' THEN 'exercise'::public.obligation_type_enum
          ELSE 'custom'::public.obligation_type_enum END,
        v_item.title, v_item.frequency, v_item.instructions, v_care_team_id, true, v_item.id,
        v_item.wording
      ) RETURNING id INTO v_projection_id;
      END IF;
      UPDATE public.care_plan_items SET projection_type = 'obligation', projection_id = v_projection_id
      WHERE id = v_item.id;
    END IF;
  END LOOP;

  UPDATE public.care_plan_versions SET status = 'approved', approved_by = p_reviewer_id,
    approved_at = now(), recommendation_id = v_recommendation_id WHERE id = v_plan.id;
  INSERT INTO public.care_plan_audit_events(plan_version_id, actor_id, event_type, event_data)
  VALUES (v_plan.id, p_reviewer_id, 'approved_and_published',
    jsonb_build_object('recommendation_id', v_recommendation_id, 'patient_locale', v_locale,
      'care_plan_id', v_plan.care_plan_id, 'acknowledged_items', p_acknowledged,
      'wording', (SELECT COALESCE(jsonb_object_agg(id::text, jsonb_build_object(
        'source_locale', source_locale, 'origin', wording_origin)), '{}'::jsonb)
        FROM public.care_plan_items WHERE plan_version_id = v_plan.id AND NOT is_removed)));
  RETURN jsonb_build_object('plan_version_id', v_plan.id, 'recommendation_id', v_recommendation_id,
    'status', 'approved', 'care_plan_id', v_plan.care_plan_id);
END;
$$;

-- ── 6b. Conversations: another team's plan detail never travels through a thread ────────
CREATE OR REPLACE FUNCTION private.care_conversation_message(p_id uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path = '' AS $$
  -- A message may carry an activity the patient chose to discuss. Its detail is shown only
  -- when the plan belongs to this conversation's care team (or to nobody); another team's
  -- plan detail is never disclosed through a thread.
  SELECT jsonb_build_object('id', m.id, 'conversation_id', m.conversation_id,
    'sender_id', m.sender_id, 'sender_role', m.sender_role, 'sender_name', m.sender_name,
    'body', m.body, 'created_at', m.created_at,
    'activity_context', CASE WHEN i.id IS NULL THEN NULL
      WHEN p.ownership_state = 'owned' AND p.care_team_id IS DISTINCT FROM c.care_team_id
        THEN jsonb_build_object('unavailable', true)
      ELSE jsonb_build_object(
      'item_id', i.id, 'plan_id', v.id, 'care_plan_id', p.id, 'title', i.title,
      'frequency', i.frequency, 'wording', i.wording,
      'current', v.status='approved' AND NOT i.is_removed) END)
  FROM public.care_conversation_messages m
  JOIN public.care_conversations c ON c.id=m.conversation_id
  LEFT JOIN public.care_plan_items i ON i.id=m.care_plan_item_id
  LEFT JOIN public.care_plan_versions v ON v.id=i.plan_version_id
  LEFT JOIN public.care_plans p ON p.id=v.care_plan_id
  WHERE m.id=p_id;
$$;

CREATE OR REPLACE FUNCTION public.care_conversation_activity_operation(
  p_actor_id uuid, p_actor_role text, p_action text, p_payload jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_result jsonb;
  v_message public.care_conversation_messages;
  v_item public.care_plan_items;
  v_plan public.care_plan_versions;
  v_draft public.care_plan_versions;
  v_thread public.care_conversations;
  v_key uuid;
  v_item_id uuid;
  v_target uuid;
  v_existing boolean;
  v_count integer;
  v_patient uuid;
  v_cplan public.care_plans;
  v_conv_team uuid;
BEGIN
  IF p_action='send' THEN
    v_key := (p_payload->>'client_message_id')::uuid;
    v_item_id := (p_payload->>'care_plan_item_id')::uuid;
    -- Match the original sender-key -> assignment -> thread lock order.
    PERFORM pg_advisory_xact_lock(hashtextextended(p_actor_id::text || ':' || v_key::text,0));
    SELECT * INTO v_message FROM public.care_conversation_messages
      WHERE sender_id=p_actor_id AND client_message_id=v_key;
    v_existing := FOUND;
    v_result := public.care_conversation_operation(p_actor_id,p_actor_role,'send',p_payload);
    IF v_existing THEN
      IF v_message.care_plan_item_id IS DISTINCT FROM v_item_id THEN
        RAISE EXCEPTION USING ERRCODE='23505', MESSAGE='Message idempotency mismatch';
      END IF;
      RETURN v_result;
    END IF;
    IF v_item_id IS NOT NULL THEN
      IF p_actor_role<>'patient' THEN
        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Activity unavailable';
      END IF;
      SELECT i.* INTO v_item FROM public.care_plan_items i
        JOIN public.care_plan_versions v ON v.id=i.plan_version_id
        WHERE i.id=v_item_id AND v.patient_id=p_actor_id AND v.status='approved'
          AND NOT i.is_removed FOR SHARE OF i,v;
      IF NOT FOUND THEN
        -- One neutral result covers missing, foreign and no-longer-approved identifiers.
        -- A patient must not be able to probe whether another record exists.
        RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Activity context unavailable',
          HINT='activity_context_unavailable';
      END IF;
      -- Attach only an activity of this conversation's own care team (or of no team).
      SELECT p.* INTO v_cplan FROM public.care_plan_versions pv
        JOIN public.care_plans p ON p.id=pv.care_plan_id WHERE pv.id=v_item.plan_version_id;
      SELECT c.care_team_id INTO v_conv_team FROM public.care_conversations c
        WHERE c.id=(v_result->>'conversation_id')::uuid;
      IF v_cplan.ownership_state='owned' AND v_cplan.care_team_id IS DISTINCT FROM v_conv_team THEN
        RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Activity context unavailable',
          HINT='activity_context_unavailable';
      END IF;
      UPDATE public.care_conversation_messages SET care_plan_item_id=v_item_id
        WHERE id=(v_result->>'id')::uuid;
    END IF;
    RETURN private.care_conversation_message((v_result->>'id')::uuid);
  ELSIF p_action='review' THEN
    IF p_actor_role IS DISTINCT FROM 'clinician' THEN
      RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Conversation unavailable';
    END IF;
    -- Reject an outsider before waiting on a patient-scoped evidence lock. This is the
    -- lock-free equivalent of 066's lock_care_conversation_pair: the exact thread must
    -- still belong to an active care-team link at an active clinic, and the clinician
    -- must still hold an active membership at that link's clinic. Every denial is neutral.
    SELECT c.* INTO v_thread FROM public.care_conversations c
      JOIN public.care_teams t ON t.id=c.care_team_id
        AND t.patient_id=c.patient_id AND t.clinician_id=c.clinician_id
        AND t.clinic_id=c.clinic_id
      JOIN public.patients p ON p.id=t.patient_id
      JOIN public.clinicians clinician ON clinician.id=t.clinician_id
      JOIN public.clinics cl ON cl.id=t.clinic_id
      JOIN public.clinic_memberships membership
        ON membership.clinician_id=t.clinician_id AND membership.clinic_id=t.clinic_id
      WHERE c.id=(p_payload->>'conversation_id')::uuid
        AND c.clinician_id=p_actor_id AND t.status='active'
        AND cl.status='active' AND membership.status='active';
    IF NOT FOUND THEN
      RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Conversation unavailable';
    END IF;
    v_patient := v_thread.patient_id;
    -- Match publication/generation: evidence fence BEFORE assignment/thread, plan and
    -- patient row locks. The existing operation then rechecks authorization under locks.
    PERFORM private.lock_care_plan_evidence(v_patient,true);
    -- Existing RPC rechecks and locks the current assignment and exact private thread.
    PERFORM public.care_conversation_operation(p_actor_id,p_actor_role,'messages',
      jsonb_build_object('conversation_id',p_payload->>'conversation_id','limit',1));
    SELECT * INTO v_thread FROM public.care_conversations
      WHERE id=(p_payload->>'conversation_id')::uuid;
    IF v_thread.patient_id IS DISTINCT FROM v_patient THEN
      RAISE EXCEPTION USING ERRCODE='40001', MESSAGE='Conversation changed; retry review';
    END IF;
    SELECT * INTO v_message FROM public.care_conversation_messages
      WHERE id=(p_payload->>'message_id')::uuid AND conversation_id=v_thread.id
        AND sender_role='patient';
    IF NOT FOUND OR v_message.care_plan_item_id IS NULL THEN
      RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Activity context unavailable',
        HINT='activity_context_unavailable';
    END IF;
    SELECT i.* INTO v_item FROM public.care_plan_items i
      JOIN public.care_plan_versions v ON v.id=i.plan_version_id
      WHERE i.id=v_message.care_plan_item_id AND v.patient_id=v_thread.patient_id
      FOR SHARE OF i,v;
    IF NOT FOUND THEN
      RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Activity context unavailable',
        HINT='activity_context_unavailable';
    END IF;
    SELECT * INTO v_plan FROM public.care_plan_versions WHERE id=v_item.plan_version_id;
    -- Only the plan's own care team reviews it; another team's plan is not reachable here.
    SELECT * INTO v_cplan FROM public.care_plans WHERE id=v_plan.care_plan_id;
    IF v_cplan.ownership_state IS DISTINCT FROM 'owned'
       OR v_cplan.care_team_id IS DISTINCT FROM v_thread.care_team_id THEN
      RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Activity context unavailable',
        HINT='activity_context_unavailable';
    END IF;
    IF v_plan.status IS DISTINCT FROM 'approved' OR v_item.is_removed THEN
      RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Activity is no longer current',
        HINT='activity_context_stale';
    END IF;
    SELECT * INTO v_draft FROM public.care_plan_versions
      WHERE care_plan_id=v_plan.care_plan_id AND status='draft' FOR UPDATE;
    IF NOT FOUND THEN
      INSERT INTO public.care_plan_versions(patient_id,care_plan_id,version_number,status,source_watermark,generated_at)
        SELECT v_thread.patient_id,v_plan.care_plan_id,coalesce(max(version_number),0)+1,'draft',v_plan.source_watermark,clock_timestamp()
        FROM public.care_plan_versions WHERE care_plan_id=v_plan.care_plan_id RETURNING * INTO v_draft;
      INSERT INTO public.care_plan_items(plan_version_id,review_source_item_id,source_fact_id,
        category,title,instructions,frequency,schedule,medication,confidence_score,
        uncertainty,conflict,blocker_reason,is_removed,source_locale,wording,wording_origin)
        SELECT v_draft.id,i.id,i.source_fact_id,i.category,i.title,i.instructions,i.frequency,
          i.schedule,CASE WHEN i.projection_type='medication' AND i.projection_id IS NOT NULL
            AND NOT i.is_removed THEN i.medication || jsonb_build_object('decision','update','target_id',i.projection_id)
            ELSE i.medication END,i.confidence_score,i.uncertainty,i.conflict,i.blocker_reason,
          i.is_removed,i.source_locale,i.wording,i.wording_origin
        FROM public.care_plan_items i WHERE i.plan_version_id=v_plan.id;
    END IF;
    SELECT count(*),(array_agg(id))[1] INTO v_count,v_target FROM public.care_plan_items
      WHERE plan_version_id=v_draft.id AND NOT is_removed AND
        (review_source_item_id=v_item.id OR
          (v_item.source_fact_id IS NOT NULL AND source_fact_id=v_item.source_fact_id));
    IF v_count<>1 THEN
      RAISE EXCEPTION USING ERRCODE='22023',
        MESSAGE='Review the existing draft before opening this activity',
        HINT='care_plan_draft_exists';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.care_plan_audit_events
      WHERE plan_version_id=v_draft.id AND event_type='message_review_opened'
        AND event_data->>'message_id'=v_message.id::text AND actor_id=p_actor_id) THEN
      INSERT INTO public.care_plan_audit_events(plan_version_id,actor_id,event_type,event_data)
        VALUES(v_draft.id,p_actor_id,'message_review_opened',jsonb_build_object(
          'message_id',v_message.id,'conversation_id',v_thread.id,
          'source_item_id',v_item.id,'draft_item_id',v_target));
    END IF;
    RETURN jsonb_build_object('patient_id',v_thread.patient_id,'plan_id',v_draft.id,'item_id',v_target);
  END IF;
  RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid activity operation';
END;
$$;



-- ── 7. Publication: one transaction, one patient-wide lock ───────────────────────────────
-- Order: authorization (no locks) -> patient fence -> idempotency record -> plan row ->
-- version row -> items (by the item trigger) -> projections. The cross-plan comparison reads
-- current state under the fence, so two plans cannot both pass a check against a state the
-- other is about to change.

CREATE FUNCTION public.publish_care_plan_version(
  p_plan_version_id uuid, p_reviewer_id uuid, p_note text, p_idempotency_key uuid,
  p_excluded_item_ids uuid[] DEFAULT ARRAY[]::uuid[]
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_version public.care_plan_versions%ROWTYPE;
  v_plan public.care_plans%ROWTYPE;
  v_patient uuid;
  v_excluded uuid[];
  v_request_hash text;
  v_pub public.care_plan_publications%ROWTYPE;
  v_row record;
  v_unresolved jsonb := '[]'::jsonb;
  v_ack jsonb := '[]'::jsonb;
  v_warnings jsonb := '[]'::jsonb;
  v_acked_fps text[] := ARRAY[]::text[];
  v_copies jsonb;
  v_result jsonb;
  v_new_draft public.care_plan_versions%ROWTYPE;
  v_live integer;
  v_digest text;
BEGIN
  IF p_idempotency_key IS NULL THEN
    RAISE EXCEPTION 'an idempotency key is required' USING ERRCODE = '22023';
  END IF;
  IF p_note IS NULL OR char_length(btrim(p_note)) NOT BETWEEN 1 AND 5000 THEN
    RAISE EXCEPTION 'an approval note is required' USING ERRCODE = '22023';
  END IF;
  SELECT array_agg(DISTINCT x ORDER BY x) INTO v_excluded
    FROM unnest(COALESCE(p_excluded_item_ids, ARRAY[]::uuid[])) x;
  v_excluded := COALESCE(v_excluded, ARRAY[]::uuid[]);
  SELECT patient_id INTO v_patient FROM public.care_plan_versions WHERE id = p_plan_version_id;
  SELECT p.* INTO v_plan FROM public.care_plan_versions v
    JOIN public.care_plans p ON p.id = v.care_plan_id WHERE v.id = p_plan_version_id;
  IF NOT FOUND OR v_plan.ownership_state <> 'owned'
     OR NOT private.clinician_holds_link(p_reviewer_id, v_plan.care_team_id) THEN
    RAISE EXCEPTION 'care plan unavailable' USING ERRCODE = '42501';
  END IF;
  v_request_hash := encode(sha256(convert_to(jsonb_build_object('version', p_plan_version_id,
    'actor', p_reviewer_id, 'excluded', to_jsonb(v_excluded))::text, 'UTF8')), 'hex');

  PERFORM private.lock_care_plan_evidence(v_patient, true);

  SELECT * INTO v_pub FROM public.care_plan_publications WHERE idempotency_key = p_idempotency_key;
  IF FOUND THEN
    -- A retry is the same key, actor, draft and exclusions, and the published items are
    -- exactly what was published. Anything else is a different request wearing an old key.
    SELECT encode(sha256(convert_to((SELECT COALESCE(jsonb_agg(jsonb_build_object('id', i.id,
      'title', i.title, 'instructions', i.instructions, 'frequency', i.frequency,
      'schedule', i.schedule, 'medication', i.medication, 'wording', i.wording,
      'removed', i.is_removed) ORDER BY i.id), '[]'::jsonb)::text
      FROM public.care_plan_items i WHERE i.plan_version_id = v_pub.plan_version_id), 'UTF8')),
      'hex') INTO v_digest;
    IF v_pub.request_hash <> v_request_hash OR v_pub.content_digest IS DISTINCT FROM v_digest THEN
      RAISE EXCEPTION 'this idempotency key was used for a different request'
        USING ERRCODE = '22023';
    END IF;
    RETURN v_pub.result || jsonb_build_object('replayed', true);
  END IF;

  SELECT * INTO v_plan FROM public.care_plans WHERE id = v_plan.id FOR UPDATE;
  SELECT * INTO v_version FROM public.care_plan_versions WHERE id = p_plan_version_id FOR UPDATE;
  IF v_version.status <> 'draft' THEN
    RAISE EXCEPTION 'care plan draft is not eligible for approval';
  END IF;
  IF v_plan.ownership_state <> 'owned'
     OR NOT private.clinician_holds_link(p_reviewer_id, v_plan.care_team_id) THEN
    RAISE EXCEPTION 'care plan unavailable' USING ERRCODE = '42501';
  END IF;
  IF EXISTS (SELECT 1 FROM unnest(v_excluded) x WHERE NOT EXISTS (
      SELECT 1 FROM public.care_plan_items i
      WHERE i.id = x AND i.plan_version_id = p_plan_version_id AND NOT i.is_removed)) THEN
    RAISE EXCEPTION 'choose items of this draft to publish without' USING ERRCODE = '22023';
  END IF;
  SELECT count(*) INTO v_live FROM public.care_plan_items
    WHERE plan_version_id = p_plan_version_id AND NOT is_removed AND NOT (id = ANY (v_excluded));
  IF v_live = 0 THEN
    RAISE EXCEPTION 'care plan needs evidence-backed items before approval';
  END IF;

  -- Cross-plan checks against current state. Blockers need a current keep-both reason.
  FOR v_row IN SELECT * FROM private.care_plan_cross_conflicts(p_plan_version_id, v_excluded) LOOP
    IF v_row.severity = 'warning' THEN
      v_warnings := v_warnings || jsonb_build_array(jsonb_build_object(
        'kind', v_row.kind, 'draft_item_id', v_row.draft_item_id,
        'other_care_plan_id', v_row.other_care_plan_id));
    ELSIF EXISTS (SELECT 1 FROM public.care_plan_conflict_resolutions r
        WHERE r.plan_version_id = p_plan_version_id AND r.fingerprint = v_row.fingerprint
          AND r.resolution = 'keep_both' AND btrim(r.reason) <> '') THEN
      v_ack := v_ack || jsonb_build_array(v_row.draft_item_id::text);
      v_acked_fps := v_acked_fps || v_row.fingerprint;
    ELSE
      v_unresolved := v_unresolved || jsonb_build_array(jsonb_build_object(
        'fingerprint', v_row.fingerprint, 'kind', v_row.kind,
        'draft_item_id', v_row.draft_item_id));
    END IF;
  END LOOP;
  IF jsonb_array_length(v_unresolved) > 0 THEN
    RAISE EXCEPTION 'resolve each cross-plan conflict before publication'
      USING ERRCODE = 'CP001', DETAIL = v_unresolved::text;
  END IF;

  -- Items published without: carried into the next draft, still pending. The other team is
  -- told for every blocker the excluded items would have raised. The originals are then
  -- marked removed (and say why) so every existing publication gate sees only what is
  -- published.
  IF cardinality(v_excluded) > 0 THEN
    FOR v_row IN SELECT * FROM private.care_plan_cross_conflicts(p_plan_version_id) LOOP
      IF v_row.severity = 'blocker' AND v_row.draft_item_id = ANY (v_excluded) THEN
        PERFORM private.open_conflict_items(v_plan.id, v_row.other_care_plan_id,
          v_row.other_care_team_id, 'conflict_published_without', v_row.fingerprint,
          private.conflict_summary(p_plan_version_id, v_row.kind, v_row.severity,
            v_row.identity_basis, v_row.draft_item_id, v_row.other_item_id,
            v_row.other_medication_id), NULL, p_reviewer_id);
      END IF;
    END LOOP;
    SELECT jsonb_agg(to_jsonb(i) ORDER BY i.id) INTO v_copies FROM public.care_plan_items i
      WHERE i.id = ANY (v_excluded);
    UPDATE public.care_plan_items
       SET is_removed = true, blocker_reason = NULL,
           conflict = conflict || jsonb_build_object('deferred_by_publication', true)
     WHERE id = ANY (v_excluded);
  END IF;

  v_result := private.publish_care_plan_core(p_plan_version_id, p_reviewer_id, btrim(p_note), v_ack);

  v_result := v_result || jsonb_build_object('published_item_count', v_live,
    'excluded_item_ids', to_jsonb(v_excluded), 'acknowledged_fingerprints', to_jsonb(v_acked_fps),
    'warnings', v_warnings, 'interaction_coverage', 'not_checked', 'replayed', false);

  IF cardinality(v_excluded) > 0 THEN
    INSERT INTO public.care_plan_versions(patient_id, care_plan_id, version_number, status,
      source_watermark, generated_at)
    SELECT v_patient, v_plan.id, COALESCE(max(version_number), 0) + 1, 'draft',
      v_version.source_watermark, clock_timestamp()
      FROM public.care_plan_versions WHERE care_plan_id = v_plan.id
    RETURNING * INTO v_new_draft;
    INSERT INTO public.care_plan_items
    SELECT (jsonb_populate_record(NULL::public.care_plan_items,
      (c.value - 'id' - 'created_at' - 'updated_at' - 'projection_type' - 'projection_id'
        - 'review_source_item_id') || jsonb_build_object('id', gen_random_uuid(),
        'plan_version_id', v_new_draft.id, 'is_removed', false,
        'created_at', clock_timestamp(), 'updated_at', clock_timestamp(),
        'review_source_item_id', c.value->>'id',
        'conflict', (c.value->'conflict') - 'deferred_by_publication'))).*
    FROM jsonb_array_elements(v_copies) c;
    INSERT INTO public.care_plan_audit_events(plan_version_id, actor_id, event_type, event_data)
    VALUES (p_plan_version_id, p_reviewer_id, 'published_without_items',
      jsonb_build_object('item_ids', to_jsonb(v_excluded), 'next_draft_id', v_new_draft.id));
    v_result := v_result || jsonb_build_object('next_draft_version_id', v_new_draft.id);
  END IF;

  SELECT encode(sha256(convert_to((SELECT COALESCE(jsonb_agg(jsonb_build_object('id', i.id,
    'title', i.title, 'instructions', i.instructions, 'frequency', i.frequency,
    'schedule', i.schedule, 'medication', i.medication, 'wording', i.wording,
    'removed', i.is_removed) ORDER BY i.id), '[]'::jsonb)::text
    FROM public.care_plan_items i WHERE i.plan_version_id = p_plan_version_id), 'UTF8')),
    'hex') INTO v_digest;
  INSERT INTO public.care_plan_publications(idempotency_key, care_plan_id, plan_version_id,
    actor_id, request_hash, content_digest, result)
  VALUES (p_idempotency_key, v_plan.id, p_plan_version_id, p_reviewer_id, v_request_hash,
    v_digest, v_result);
  RETURN v_result;
END;
$$;

-- The pre-existing three-argument approval (048 wrapper) now publishes through the same
-- checks, with a fresh key and no exclusions.
CREATE OR REPLACE FUNCTION private.approve_care_plan_version(
  p_plan_version_id uuid, p_reviewer_id uuid, p_note text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  RETURN public.publish_care_plan_version(p_plan_version_id, p_reviewer_id, p_note,
    gen_random_uuid(), ARRAY[]::uuid[]);
END;
$$;

-- ── 9. Grants ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE public.care_plan_conflict_resolutions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.care_plan_publications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.care_plan_conflict_resolutions, public.care_plan_publications
  FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.care_plan_conflict_resolutions, public.care_plan_publications
  TO service_role;

REVOKE ALL ON FUNCTION
  private.norm_text(text), private.care_plan_cross_conflicts(uuid, uuid[]),
  private.open_conflict_items(uuid, uuid, uuid, text, text, jsonb, text, uuid),
  private.conflict_summary(uuid, text, text, text, uuid, uuid, uuid),
  private.publish_care_plan_core(uuid, uuid, text, jsonb),
  private.approve_care_plan_version(uuid, uuid, text),
  private.care_conversation_message(uuid),
  public.care_plan_cross_plan_review(uuid, uuid),
  public.record_cross_plan_resolution(uuid, uuid, text, text, text),
  public.reply_care_plan_review_item(uuid, uuid, text),
  public.publish_care_plan_version(uuid, uuid, text, uuid, uuid[]),
  public.care_conversation_activity_operation(uuid, text, text, jsonb)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION
  private.norm_text(text), private.care_plan_cross_conflicts(uuid, uuid[]),
  private.open_conflict_items(uuid, uuid, uuid, text, text, jsonb, text, uuid),
  private.conflict_summary(uuid, text, text, text, uuid, uuid, uuid),
  private.publish_care_plan_core(uuid, uuid, text, jsonb),
  private.approve_care_plan_version(uuid, uuid, text),
  private.care_conversation_message(uuid),
  public.care_plan_cross_plan_review(uuid, uuid),
  public.record_cross_plan_resolution(uuid, uuid, text, text, text),
  public.reply_care_plan_review_item(uuid, uuid, text),
  public.publish_care_plan_version(uuid, uuid, text, uuid, uuid[]),
  public.care_conversation_activity_operation(uuid, text, text, jsonb)
  TO service_role;

-- ── 10. Verification ──────────────────────────────────────────────────────────────────────

DO $verify$
DECLARE v_function text;
BEGIN
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.care_plan_conflict_resolutions'::regclass)
     OR NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.care_plan_publications'::regclass) THEN
    RAISE EXCEPTION 'PLAN-002 verification: RLS is off on a publication table';
  END IF;
  IF has_table_privilege('anon', 'public.care_plan_conflict_resolutions', 'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('authenticated', 'public.care_plan_conflict_resolutions',
       'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('anon', 'public.care_plan_publications', 'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('authenticated', 'public.care_plan_publications',
       'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('service_role', 'public.care_plan_conflict_resolutions', 'UPDATE')
     OR has_table_privilege('service_role', 'public.care_plan_publications', 'DELETE') THEN
    RAISE EXCEPTION 'PLAN-002 verification: wrong grants on a publication table';
  END IF;
  FOREACH v_function IN ARRAY ARRAY[
    'public.publish_care_plan_version(uuid,uuid,text,uuid,uuid[])',
    'public.record_cross_plan_resolution(uuid,uuid,text,text,text)',
    'public.reply_care_plan_review_item(uuid,uuid,text)',
    'public.care_plan_cross_plan_review(uuid,uuid)',
    'public.approve_care_plan_version(uuid,uuid,text)',
    'private.care_plan_cross_conflicts(uuid,uuid[])'] LOOP
    IF has_function_privilege('anon', v_function, 'EXECUTE')
       OR has_function_privilege('authenticated', v_function, 'EXECUTE')
       OR NOT has_function_privilege('service_role', v_function, 'EXECUTE') THEN
      RAISE EXCEPTION 'PLAN-002 verification: wrong execute grants on %', v_function;
    END IF;
  END LOOP;
  -- Exactly one approved version and at most one open draft per plan, and no patient has two
  -- plans claiming the same native link.
  IF EXISTS (SELECT 1 FROM public.care_plan_versions WHERE status = 'approved'
      GROUP BY care_plan_id HAVING count(*) > 1) THEN
    RAISE EXCEPTION 'PLAN-002 verification: a plan has two approved versions';
  END IF;
END;
$verify$;
