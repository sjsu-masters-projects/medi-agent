-- CON-001: reviewed care-handoff summaries.
--
-- A clinician drafts a handoff summary for one of their patients, built by the backend from
-- records that clinician may see (shared core, their own care team's plan and work, the
-- bounded timeline), then reviews, edits and approves it. Each save is a new immutable
-- version; an approval, edit or export is an append-only audit event.
--
--   * A summary belongs to ONE care-team link (care_team_id) of its author. Every function
--     below re-checks, in the database, that the caller holds that active link to the
--     patient; a summary that is missing, belongs to another link or another patient's
--     link answers the same way (42501), so nothing can be probed.
--   * Versions are append-only. They hold the deterministic section snapshot the backend
--     assembled plus the clinician's narrative and notes. A version is deleted only when its
--     summary row is gone (patient erasure cascade), never by itself.
--   * Events carry ids and types only (no clinical text) and survive erasure like the other
--     audit trails; they have no foreign keys for that reason.
--   * Concurrency (OPS-006): every writer locks the summary row, saves are optimistic on the
--     version the caller saw (40001), approval and export check the CURRENT version, a repeat
--     create/approve is a no-op replay, counts are bounded and time comes from the database.
--   * Export is allowed only for the approved version; editing after approval returns the
--     summary to draft.
--
-- All objects revoke the browser roles explicitly; the final block fails the migration if a
-- grant, policy, trigger or function lost its check.

-- ── 1. Tables ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE public.care_handoff_summaries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL REFERENCES public.patients(id) ON DELETE CASCADE,
  care_team_id uuid NOT NULL REFERENCES public.care_teams(id) ON DELETE CASCADE,
  author_id uuid NOT NULL,
  title text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
  purpose text NOT NULL CHECK (purpose IN ('colleague', 'care_team', 'transition')),
  recipient_label text CHECK (recipient_label IS NULL OR char_length(recipient_label) <= 200),
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved')),
  current_version integer NOT NULL DEFAULT 1 CHECK (current_version BETWEEN 1 AND 200),
  approved_version integer,
  approved_by uuid,
  approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK ((status = 'approved') = (approved_version IS NOT NULL
    AND approved_by IS NOT NULL AND approved_at IS NOT NULL)),
  CHECK (approved_version IS NULL OR approved_version = current_version)
);
CREATE INDEX care_handoff_summaries_patient_team
  ON public.care_handoff_summaries(patient_id, care_team_id, created_at DESC);

CREATE TABLE public.care_handoff_summary_versions (
  summary_id uuid NOT NULL REFERENCES public.care_handoff_summaries(id) ON DELETE CASCADE,
  version integer NOT NULL CHECK (version BETWEEN 1 AND 200),
  sections jsonb NOT NULL CHECK (jsonb_typeof(sections) = 'array'
    AND octet_length(sections::text) <= 400000),
  narrative text CHECK (narrative IS NULL OR char_length(narrative) <= 4000),
  notes text CHECK (notes IS NULL OR char_length(notes) <= 4000),
  built_at timestamptz NOT NULL,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (summary_id, version)
);

CREATE TABLE public.care_handoff_summary_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  summary_id uuid NOT NULL,
  patient_id uuid NOT NULL,
  care_team_id uuid NOT NULL,
  version integer NOT NULL,
  event_type text NOT NULL CHECK (event_type IN ('created', 'edited', 'refreshed', 'approved', 'exported')),
  export_format text CHECK (export_format IS NULL OR export_format IN ('print', 'fhir')),
  actor_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX care_handoff_summary_events_summary
  ON public.care_handoff_summary_events(summary_id, created_at);

-- ── 2. Append-only ────────────────────────────────────────────────────────────────────────

CREATE FUNCTION private.care_handoff_append_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
  IF TG_OP = 'DELETE' AND TG_TABLE_NAME = 'care_handoff_summary_versions'
     AND NOT EXISTS (SELECT 1 FROM public.care_handoff_summaries WHERE id = OLD.summary_id) THEN
    RETURN OLD; -- the summary itself is being erased with its patient
  END IF;
  RAISE EXCEPTION 'Handoff summary versions and events are append-only' USING ERRCODE = '42501';
END;
$$;
CREATE TRIGGER care_handoff_versions_append_only
  BEFORE UPDATE OR DELETE ON public.care_handoff_summary_versions
  FOR EACH ROW EXECUTE FUNCTION private.care_handoff_append_only();
CREATE TRIGGER care_handoff_versions_no_truncate
  BEFORE TRUNCATE ON public.care_handoff_summary_versions
  FOR EACH STATEMENT EXECUTE FUNCTION private.care_handoff_append_only();
CREATE TRIGGER care_handoff_events_append_only
  BEFORE UPDATE OR DELETE ON public.care_handoff_summary_events
  FOR EACH ROW EXECUTE FUNCTION private.care_handoff_append_only();
CREATE TRIGGER care_handoff_events_no_truncate
  BEFORE TRUNCATE ON public.care_handoff_summary_events
  FOR EACH STATEMENT EXECUTE FUNCTION private.care_handoff_append_only();

-- ── 3. Row-level security: the Data API reaches nothing ───────────────────────────────────

ALTER TABLE public.care_handoff_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.care_handoff_summary_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.care_handoff_summary_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.care_handoff_summaries, public.care_handoff_summary_versions,
  public.care_handoff_summary_events FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.care_handoff_summaries, public.care_handoff_summary_versions,
  public.care_handoff_summary_events TO service_role;

-- ── 4. Functions ──────────────────────────────────────────────────────────────────────────

-- The caller must hold this exact active link to this patient; every other case is the same
-- answer. Returns the locked summary when it exists for that link.
CREATE FUNCTION private.handoff_locked_summary(p_actor_id uuid, p_summary_id uuid)
RETURNS public.care_handoff_summaries LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE v_summary public.care_handoff_summaries%ROWTYPE;
BEGIN
  SELECT * INTO v_summary FROM public.care_handoff_summaries WHERE id = p_summary_id FOR UPDATE;
  IF NOT FOUND OR NOT (v_summary.care_team_id =
      ANY (private.clinician_patient_links(p_actor_id, v_summary.patient_id))) THEN
    RAISE EXCEPTION 'handoff summary unavailable' USING ERRCODE = '42501';
  END IF;
  RETURN v_summary;
END;
$$;

CREATE FUNCTION private.handoff_header(p_summary public.care_handoff_summaries) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = '' AS $$
  SELECT jsonb_build_object(
    'id', p_summary.id, 'patient_id', p_summary.patient_id,
    'care_team_id', p_summary.care_team_id, 'author_id', p_summary.author_id,
    'title', p_summary.title, 'purpose', p_summary.purpose,
    'recipient_label', p_summary.recipient_label, 'status', p_summary.status,
    'current_version', p_summary.current_version,
    'approved_version', p_summary.approved_version, 'approved_by', p_summary.approved_by,
    'approved_at', p_summary.approved_at, 'created_at', p_summary.created_at,
    'updated_at', p_summary.updated_at);
$$;

CREATE FUNCTION public.create_care_handoff_summary(
  p_actor_id uuid, p_patient_id uuid, p_care_team_id uuid, p_summary_id uuid,
  p_title text, p_purpose text, p_recipient_label text, p_sections jsonb,
  p_built_at timestamptz, p_narrative text DEFAULT NULL, p_notes text DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_summary public.care_handoff_summaries%ROWTYPE;
BEGIN
  IF NOT (p_care_team_id = ANY (private.clinician_patient_links(p_actor_id, p_patient_id))) THEN
    RAISE EXCEPTION 'handoff summary unavailable' USING ERRCODE = '42501';
  END IF;
  -- Serialise creates for one patient and team so the bound below cannot be raced past.
  PERFORM pg_advisory_xact_lock(hashtextextended('handoff:' || p_patient_id || p_care_team_id, 0));
  SELECT * INTO v_summary FROM public.care_handoff_summaries WHERE id = p_summary_id;
  IF FOUND THEN
    IF v_summary.care_team_id = p_care_team_id AND v_summary.patient_id = p_patient_id
       AND v_summary.author_id = p_actor_id THEN
      RETURN private.handoff_header(v_summary) || jsonb_build_object('replayed', true);
    END IF;
    RAISE EXCEPTION 'handoff summary unavailable' USING ERRCODE = '42501';
  END IF;
  IF (SELECT count(*) FROM public.care_handoff_summaries
      WHERE patient_id = p_patient_id AND care_team_id = p_care_team_id) >= 50 THEN
    RAISE EXCEPTION 'too many handoff summaries for this patient' USING ERRCODE = '54000';
  END IF;
  INSERT INTO public.care_handoff_summaries(id, patient_id, care_team_id, author_id, title,
    purpose, recipient_label)
  VALUES (p_summary_id, p_patient_id, p_care_team_id, p_actor_id, p_title, p_purpose,
    p_recipient_label)
  RETURNING * INTO v_summary;
  INSERT INTO public.care_handoff_summary_versions(summary_id, version, sections, narrative,
    notes, built_at, created_by)
  VALUES (p_summary_id, 1, p_sections, p_narrative, p_notes, p_built_at, p_actor_id);
  INSERT INTO public.care_handoff_summary_events(summary_id, patient_id, care_team_id, version,
    event_type, actor_id)
  VALUES (p_summary_id, p_patient_id, p_care_team_id, 1, 'created', p_actor_id);
  RETURN private.handoff_header(v_summary) || jsonb_build_object('replayed', false);
END;
$$;

-- Saves the narrative, notes and (when refreshed) a rebuilt section snapshot as the next
-- version. The caller names the version it was looking at; any other is a conflict.
CREATE FUNCTION public.save_care_handoff_version(
  p_actor_id uuid, p_summary_id uuid, p_expected_version integer,
  p_narrative text, p_notes text, p_title text DEFAULT NULL,
  p_sections jsonb DEFAULT NULL, p_built_at timestamptz DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_summary public.care_handoff_summaries%ROWTYPE;
  v_prior public.care_handoff_summary_versions%ROWTYPE;
  v_title text;
BEGIN
  v_summary := private.handoff_locked_summary(p_actor_id, p_summary_id);
  IF v_summary.current_version <> p_expected_version THEN
    RAISE EXCEPTION 'HANDOFF_VERSION_CONFLICT: the summary changed since you opened it'
      USING ERRCODE = '40001', HINT = 'HANDOFF_VERSION_CONFLICT';
  END IF;
  SELECT * INTO v_prior FROM public.care_handoff_summary_versions
    WHERE summary_id = p_summary_id AND version = v_summary.current_version;
  v_title := COALESCE(p_title, v_summary.title);
  IF p_sections IS NULL AND p_narrative IS NOT DISTINCT FROM v_prior.narrative
     AND p_notes IS NOT DISTINCT FROM v_prior.notes AND v_title = v_summary.title THEN
    RETURN private.handoff_header(v_summary) || jsonb_build_object('changed', false);
  END IF;
  IF v_summary.current_version >= 200 THEN
    RAISE EXCEPTION 'too many versions of this handoff summary' USING ERRCODE = '54000';
  END IF;
  INSERT INTO public.care_handoff_summary_versions(summary_id, version, sections, narrative,
    notes, built_at, created_by)
  VALUES (p_summary_id, v_summary.current_version + 1,
    COALESCE(p_sections, v_prior.sections), p_narrative, p_notes,
    CASE WHEN p_sections IS NULL THEN v_prior.built_at ELSE COALESCE(p_built_at, clock_timestamp()) END,
    p_actor_id);
  UPDATE public.care_handoff_summaries
     SET current_version = current_version + 1, title = v_title, status = 'draft',
         approved_version = NULL, approved_by = NULL, approved_at = NULL,
         updated_at = clock_timestamp()
   WHERE id = p_summary_id RETURNING * INTO v_summary;
  INSERT INTO public.care_handoff_summary_events(summary_id, patient_id, care_team_id, version,
    event_type, actor_id)
  VALUES (p_summary_id, v_summary.patient_id, v_summary.care_team_id, v_summary.current_version,
    CASE WHEN p_sections IS NULL THEN 'edited' ELSE 'refreshed' END, p_actor_id);
  RETURN private.handoff_header(v_summary) || jsonb_build_object('changed', true);
END;
$$;

CREATE FUNCTION public.approve_care_handoff_summary(
  p_actor_id uuid, p_summary_id uuid, p_version integer
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_summary public.care_handoff_summaries%ROWTYPE;
BEGIN
  v_summary := private.handoff_locked_summary(p_actor_id, p_summary_id);
  IF v_summary.current_version <> p_version THEN
    RAISE EXCEPTION 'HANDOFF_VERSION_CONFLICT: the summary changed since you opened it'
      USING ERRCODE = '40001', HINT = 'HANDOFF_VERSION_CONFLICT';
  END IF;
  IF v_summary.status = 'approved' THEN
    RETURN private.handoff_header(v_summary) || jsonb_build_object('changed', false);
  END IF;
  UPDATE public.care_handoff_summaries
     SET status = 'approved', approved_version = current_version, approved_by = p_actor_id,
         approved_at = clock_timestamp(), updated_at = clock_timestamp()
   WHERE id = p_summary_id RETURNING * INTO v_summary;
  INSERT INTO public.care_handoff_summary_events(summary_id, patient_id, care_team_id, version,
    event_type, actor_id)
  VALUES (p_summary_id, v_summary.patient_id, v_summary.care_team_id, v_summary.current_version,
    'approved', p_actor_id);
  RETURN private.handoff_header(v_summary) || jsonb_build_object('changed', true);
END;
$$;

-- Reads one summary with a version (default: the current one), the version list and the
-- recent events. Never mutates.
CREATE FUNCTION public.read_care_handoff_summary(
  p_actor_id uuid, p_summary_id uuid, p_version integer DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_summary public.care_handoff_summaries%ROWTYPE;
  v_version public.care_handoff_summary_versions%ROWTYPE;
BEGIN
  SELECT * INTO v_summary FROM public.care_handoff_summaries WHERE id = p_summary_id;
  IF NOT FOUND OR NOT (v_summary.care_team_id =
      ANY (private.clinician_patient_links(p_actor_id, v_summary.patient_id))) THEN
    RAISE EXCEPTION 'handoff summary unavailable' USING ERRCODE = '42501';
  END IF;
  SELECT * INTO v_version FROM public.care_handoff_summary_versions
    WHERE summary_id = p_summary_id AND version = COALESCE(p_version, v_summary.current_version);
  IF NOT FOUND THEN
    RAISE EXCEPTION 'handoff summary unavailable' USING ERRCODE = '42501';
  END IF;
  RETURN private.handoff_header(v_summary) || jsonb_build_object(
    'version', jsonb_build_object('version', v_version.version, 'sections', v_version.sections,
      'narrative', v_version.narrative, 'notes', v_version.notes,
      'built_at', v_version.built_at, 'created_by', v_version.created_by,
      'created_at', v_version.created_at),
    'versions', COALESCE((SELECT jsonb_agg(jsonb_build_object('version', v.version,
        'created_by', v.created_by, 'created_at', v.created_at) ORDER BY v.version DESC)
      FROM public.care_handoff_summary_versions v WHERE v.summary_id = p_summary_id), '[]'),
    'events', COALESCE((SELECT jsonb_agg(jsonb_build_object('event_type', e.event_type,
        'version', e.version, 'export_format', e.export_format, 'actor_id', e.actor_id,
        'created_at', e.created_at) ORDER BY e.created_at DESC, e.id)
      FROM (SELECT * FROM public.care_handoff_summary_events
        WHERE summary_id = p_summary_id ORDER BY created_at DESC LIMIT 100) e), '[]'));
END;
$$;

CREATE FUNCTION public.list_care_handoff_summaries(p_actor_id uuid, p_patient_id uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_links uuid[] := private.clinician_patient_links(p_actor_id, p_patient_id);
BEGIN
  IF cardinality(v_links) = 0 THEN
    RAISE EXCEPTION 'patient unavailable' USING ERRCODE = '42501';
  END IF;
  RETURN COALESCE((SELECT jsonb_agg(private.handoff_header(s) ORDER BY s.created_at DESC, s.id)
    FROM (SELECT * FROM public.care_handoff_summaries
      WHERE patient_id = p_patient_id AND care_team_id = ANY (v_links)
      ORDER BY created_at DESC LIMIT 50) s), '[]');
END;
$$;

-- Records an export of the approved, current version and returns that version. Anything else
-- (a draft, an older version, an edited-since-approval summary) is refused.
CREATE FUNCTION public.record_care_handoff_export(
  p_actor_id uuid, p_summary_id uuid, p_version integer, p_format text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_summary public.care_handoff_summaries%ROWTYPE;
BEGIN
  IF p_format NOT IN ('print', 'fhir') THEN
    RAISE EXCEPTION 'unsupported export format' USING ERRCODE = '22023';
  END IF;
  v_summary := private.handoff_locked_summary(p_actor_id, p_summary_id);
  IF v_summary.status <> 'approved' OR v_summary.approved_version IS DISTINCT FROM p_version
     OR v_summary.current_version <> p_version THEN
    RAISE EXCEPTION 'HANDOFF_NOT_APPROVED: only the approved version can be exported'
      USING ERRCODE = '22023', HINT = 'HANDOFF_NOT_APPROVED';
  END IF;
  INSERT INTO public.care_handoff_summary_events(summary_id, patient_id, care_team_id, version,
    event_type, export_format, actor_id)
  VALUES (p_summary_id, v_summary.patient_id, v_summary.care_team_id, p_version, 'exported',
    p_format, p_actor_id);
  RETURN public.read_care_handoff_summary(p_actor_id, p_summary_id, p_version);
END;
$$;

-- ── 5. Grants ─────────────────────────────────────────────────────────────────────────────

REVOKE ALL ON FUNCTION
  private.care_handoff_append_only(), private.handoff_locked_summary(uuid, uuid),
  private.handoff_header(public.care_handoff_summaries),
  public.create_care_handoff_summary(uuid, uuid, uuid, uuid, text, text, text, jsonb, timestamptz, text, text),
  public.save_care_handoff_version(uuid, uuid, integer, text, text, text, jsonb, timestamptz),
  public.approve_care_handoff_summary(uuid, uuid, integer),
  public.read_care_handoff_summary(uuid, uuid, integer),
  public.list_care_handoff_summaries(uuid, uuid),
  public.record_care_handoff_export(uuid, uuid, integer, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION
  private.care_handoff_append_only(), private.handoff_locked_summary(uuid, uuid),
  private.handoff_header(public.care_handoff_summaries),
  public.create_care_handoff_summary(uuid, uuid, uuid, uuid, text, text, text, jsonb, timestamptz, text, text),
  public.save_care_handoff_version(uuid, uuid, integer, text, text, text, jsonb, timestamptz),
  public.approve_care_handoff_summary(uuid, uuid, integer),
  public.read_care_handoff_summary(uuid, uuid, integer),
  public.list_care_handoff_summaries(uuid, uuid),
  public.record_care_handoff_export(uuid, uuid, integer, text)
  TO service_role;

-- ── 6. Verification ───────────────────────────────────────────────────────────────────────

DO $verify$
DECLARE v_function text;
BEGIN
  FOREACH v_function IN ARRAY ARRAY[
    'public.create_care_handoff_summary(uuid,uuid,uuid,uuid,text,text,text,jsonb,timestamptz,text,text)',
    'public.save_care_handoff_version(uuid,uuid,integer,text,text,text,jsonb,timestamptz)',
    'public.approve_care_handoff_summary(uuid,uuid,integer)',
    'public.read_care_handoff_summary(uuid,uuid,integer)',
    'public.list_care_handoff_summaries(uuid,uuid)',
    'public.record_care_handoff_export(uuid,uuid,integer,text)',
    'private.handoff_locked_summary(uuid,uuid)'] LOOP
    IF has_function_privilege('anon', v_function, 'EXECUTE')
       OR has_function_privilege('authenticated', v_function, 'EXECUTE')
       OR NOT has_function_privilege('service_role', v_function, 'EXECUTE') THEN
      RAISE EXCEPTION '089: wrong execute grants on %', v_function;
    END IF;
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public' AND c.relname IN ('care_handoff_summaries',
        'care_handoff_summary_versions', 'care_handoff_summary_events')
        AND NOT c.relrowsecurity) THEN
    RAISE EXCEPTION '089: row-level security is off on a handoff table';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.role_table_grants
      WHERE table_schema = 'public' AND table_name LIKE 'care_handoff_summar%'
        AND grantee IN ('anon', 'authenticated', 'PUBLIC')) THEN
    RAISE EXCEPTION '089: a browser role can reach a handoff table';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
      WHERE c.relname LIKE 'care_handoff_summar%') THEN
    RAISE EXCEPTION '089: a handoff table has a policy';
  END IF;
  IF (SELECT count(*) FROM pg_trigger WHERE tgname IN ('care_handoff_versions_append_only',
      'care_handoff_events_append_only', 'care_handoff_versions_no_truncate',
      'care_handoff_events_no_truncate')) <> 4 THEN
    RAISE EXCEPTION '089: the append-only triggers are missing';
  END IF;
END;
$verify$;
