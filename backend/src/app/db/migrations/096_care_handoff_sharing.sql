-- CON-001 follow-up: share an APPROVED care-handoff summary version with a named colleague.
--
-- The author of an approved summary shares that exact version with one clinician who is
-- allowed to receive it: a clinician who holds an active care-team link to the same patient
-- (at any clinic), or an active member of the AUTHOR'S clinic (so a colleague who is taking
-- over can receive it before they are linked). The recipient sees only the shared version's
-- content (which by construction holds only what the author was allowed to see); sharing
-- grants no access to the patient's record.
--
--   * A share belongs to ONE version (summary_id, version). Editing the summary makes a new
--     version; the share stays on the version it was made for. Shares are per recipient,
--     unique per (summary, version, recipient), and revocable only by the author. A revoked
--     share can be granted again; that is a new generation with its own notification.
--   * Authorization comes first: every author function reads the summary WITHOUT a lock and
--     answers 42501 (the same answer for missing, foreign and not-yours) before it takes the
--     summary row lock. Lock order (OPS-006 rule 7): the single summary row, then rows it
--     writes by primary key. No other lock is taken by the share functions.
--   * Idempotency (rule 4/5): sharing again with an active share is a replay (no second event,
--     no second notification). The notification event key is `handoff_share:<share>:<generation>`
--     so a concurrent or retried share can only ever capture it once.
--   * Revoking removes access immediately: every recipient read re-checks, in the database,
--     that the share is not revoked and that the recipient is still an allowed recipient.
--   * The recipient's notification-centre item is a normal ledger event (write-time capture in
--     the same transaction as the share). The ledger's helper functions are WRAPPED, not
--     rewritten: the existing bodies are renamed unchanged and the new function handles the
--     share source first and delegates everything else, so this file cannot silently drop a
--     change another migration made to them.
--   * Audit events carry ids and types only; the append-only table is extended, not replaced.
--
-- All new objects revoke the browser roles explicitly; the final block fails the migration if a
-- grant, policy, trigger or function lost its check.

-- ── 1. Audit events: share, revoke, recipient view and export ─────────────────────────────

ALTER TABLE public.care_handoff_summary_events
  ADD COLUMN IF NOT EXISTS share_id uuid,
  ADD COLUMN IF NOT EXISTS recipient_id uuid;

ALTER TABLE public.care_handoff_summary_events
  DROP CONSTRAINT IF EXISTS care_handoff_summary_events_event_type_check;
ALTER TABLE public.care_handoff_summary_events
  ADD CONSTRAINT care_handoff_summary_events_event_type_check CHECK (event_type IN (
    'created', 'edited', 'refreshed', 'approved', 'exported',
    'shared', 'share_revoked', 'shared_viewed', 'shared_exported'));

-- ── 2. Shares ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.care_handoff_shares (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  summary_id uuid NOT NULL REFERENCES public.care_handoff_summaries(id) ON DELETE CASCADE,
  version integer NOT NULL,
  patient_id uuid NOT NULL REFERENCES public.patients(id) ON DELETE CASCADE,
  author_id uuid NOT NULL,
  recipient_id uuid NOT NULL REFERENCES public.clinicians(id) ON DELETE CASCADE,
  -- What the recipient is shown is fixed when the share is made: the version's approval and
  -- the title and purpose the author had then (the summary's title may change later).
  title text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
  purpose text NOT NULL CHECK (purpose IN ('colleague', 'care_team', 'transition')),
  approved_by uuid NOT NULL,
  approved_at timestamptz NOT NULL,
  generation integer NOT NULL DEFAULT 1 CHECK (generation BETWEEN 1 AND 100),
  shared_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  revoked_at timestamptz,
  revoked_by uuid,
  CONSTRAINT care_handoff_shares_version_fk FOREIGN KEY (summary_id, version)
    REFERENCES public.care_handoff_summary_versions(summary_id, version) ON DELETE CASCADE,
  CONSTRAINT care_handoff_shares_once UNIQUE (summary_id, version, recipient_id),
  CONSTRAINT care_handoff_shares_revoke_pair CHECK ((revoked_at IS NULL) = (revoked_by IS NULL))
);
CREATE INDEX IF NOT EXISTS care_handoff_shares_recipient_active
  ON public.care_handoff_shares(recipient_id, shared_at DESC) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS care_handoff_shares_summary
  ON public.care_handoff_shares(summary_id, shared_at DESC);

-- Identity never changes. Only a revoke, or a re-share of a revoked share, may update a row.
CREATE OR REPLACE FUNCTION private.care_handoff_share_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
  IF TG_OP = 'DELETE' AND (
      NOT EXISTS (SELECT 1 FROM public.care_handoff_summaries WHERE id = OLD.summary_id)
      OR NOT EXISTS (SELECT 1 FROM public.patients WHERE id = OLD.patient_id)
      OR NOT EXISTS (SELECT 1 FROM public.clinicians WHERE id = OLD.recipient_id)) THEN
    RETURN OLD; -- the summary, its patient or the recipient is being erased
  END IF;
  IF TG_OP = 'UPDATE'
     AND (NEW.id, NEW.summary_id, NEW.version, NEW.patient_id, NEW.author_id, NEW.recipient_id,
          NEW.title, NEW.purpose, NEW.approved_by, NEW.approved_at)
       IS NOT DISTINCT FROM
         (OLD.id, OLD.summary_id, OLD.version, OLD.patient_id, OLD.author_id, OLD.recipient_id,
          OLD.title, OLD.purpose, OLD.approved_by, OLD.approved_at)
     AND ((OLD.revoked_at IS NULL AND NEW.revoked_at IS NOT NULL AND NEW.generation = OLD.generation)
       OR (OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS NULL
           AND NEW.generation = OLD.generation + 1)) THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'Handoff shares change only by revoke or re-share' USING ERRCODE = '42501';
END;
$$;
DROP TRIGGER IF EXISTS care_handoff_shares_guard ON public.care_handoff_shares;
CREATE TRIGGER care_handoff_shares_guard
  BEFORE UPDATE OR DELETE ON public.care_handoff_shares
  FOR EACH ROW EXECUTE FUNCTION private.care_handoff_share_guard();
DROP TRIGGER IF EXISTS care_handoff_shares_no_truncate ON public.care_handoff_shares;
CREATE TRIGGER care_handoff_shares_no_truncate
  BEFORE TRUNCATE ON public.care_handoff_shares
  FOR EACH STATEMENT EXECUTE FUNCTION private.care_handoff_share_guard();

ALTER TABLE public.care_handoff_shares ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.care_handoff_shares FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.care_handoff_shares TO service_role;

-- ── 3. Who may receive a summary ──────────────────────────────────────────────────────────

-- One row per allowed clinician (never the author): an active care-team link to the summary's
-- patient at an active clinic where they are an active member, or an active member of the
-- author's own clinic. `p_recipient` asks the single-person question the share and the read
-- ask; `p_query` is a case-insensitive name/specialty/clinic substring (no wildcards).
CREATE OR REPLACE FUNCTION private.handoff_share_candidates(
  p_summary_id uuid, p_recipient uuid DEFAULT NULL, p_query text DEFAULT NULL
) RETURNS TABLE(clinician_id uuid, first_name text, last_name text, specialty text,
  clinics jsonb, bases text[])
LANGUAGE sql STABLE SET search_path = '' AS $$
  WITH s AS (
    SELECT sm.patient_id, sm.author_id, t.clinic_id AS author_clinic
      FROM public.care_handoff_summaries sm
      JOIN public.care_teams t ON t.id = sm.care_team_id
     WHERE sm.id = p_summary_id
  ), via AS (
    SELECT ct.clinician_id, ct.clinic_id, 'care_team'::text AS basis
      FROM s JOIN public.care_teams ct ON ct.patient_id = s.patient_id AND ct.status = 'active'
      JOIN public.clinic_memberships m ON m.clinician_id = ct.clinician_id
        AND m.clinic_id = ct.clinic_id AND m.status = 'active'
      JOIN public.clinics cl ON cl.id = ct.clinic_id AND cl.status = 'active'
    UNION ALL
    SELECT m.clinician_id, m.clinic_id, 'clinic_member'::text
      FROM s JOIN public.clinic_memberships m ON m.clinic_id = s.author_clinic AND m.status = 'active'
      JOIN public.clinics cl ON cl.id = m.clinic_id AND cl.status = 'active'
  )
  SELECT c.id, c.first_name, c.last_name, c.specialty,
         jsonb_agg(DISTINCT jsonb_build_object('id', cl.id, 'name', cl.display_name)),
         array_agg(DISTINCT v.basis ORDER BY v.basis)
    FROM via v
    JOIN public.clinicians c ON c.id = v.clinician_id
    JOIN public.clinics cl ON cl.id = v.clinic_id
    CROSS JOIN s
   WHERE v.clinician_id <> s.author_id
     AND (p_recipient IS NULL OR v.clinician_id = p_recipient)
     AND (p_query IS NULL OR btrim(p_query) = '' OR position(lower(btrim(p_query)) IN lower(
          c.first_name || ' ' || c.last_name || ' ' || c.specialty || ' ' || cl.display_name)) > 0)
   GROUP BY c.id, c.first_name, c.last_name, c.specialty
   ORDER BY c.last_name, c.first_name, c.id
   LIMIT 200;
$$;

-- An active share whose recipient is still an allowed recipient. Both halves are checked at
-- every read, so revoking, leaving the clinic or ending the link all remove access at once.
CREATE OR REPLACE FUNCTION private.handoff_share_usable(p_share public.care_handoff_shares)
RETURNS boolean LANGUAGE sql STABLE SET search_path = '' AS $$
  SELECT p_share.revoked_at IS NULL AND EXISTS (
    SELECT 1 FROM private.handoff_share_candidates(p_share.summary_id, p_share.recipient_id));
$$;

-- The recipient's view of one share: the shared version only. No team, events, other
-- versions or source links.
CREATE OR REPLACE FUNCTION private.handoff_shared_payload(p_share public.care_handoff_shares)
RETURNS jsonb LANGUAGE sql STABLE SET search_path = '' AS $$
  SELECT jsonb_build_object(
    'share_id', h.id, 'summary_id', h.summary_id, 'version', h.version,
    'title', h.title, 'purpose', h.purpose, 'patient_id', h.patient_id,
    'patient_name', concat_ws(' ', p.first_name, p.last_name),
    'author_id', h.author_id, 'author_name', concat_ws(' ', a.first_name, a.last_name),
    'author_specialty', a.specialty,
    'author_clinic', (SELECT cl.display_name FROM public.care_handoff_summaries sm
        JOIN public.care_teams t ON t.id = sm.care_team_id
        JOIN public.clinics cl ON cl.id = t.clinic_id WHERE sm.id = h.summary_id),
    'shared_at', h.shared_at, 'approved_by', h.approved_by,
    'approved_by_name', (SELECT concat_ws(' ', ap.first_name, ap.last_name)
        FROM public.clinicians ap WHERE ap.id = h.approved_by),
    'approved_at', h.approved_at, 'built_at', v.built_at, 'sections', v.sections,
    'narrative', v.narrative, 'notes', v.notes,
    'newer', (SELECT jsonb_build_object('share_id', n.id, 'version', n.version)
        FROM public.care_handoff_shares n
       WHERE n.summary_id = h.summary_id AND n.recipient_id = h.recipient_id
         AND n.version > h.version AND n.revoked_at IS NULL
       ORDER BY n.version DESC LIMIT 1))
  FROM (SELECT p_share.*) h
  JOIN public.care_handoff_summary_versions v ON v.summary_id = h.summary_id AND v.version = h.version
  JOIN public.patients p ON p.id = h.patient_id
  JOIN public.clinicians a ON a.id = h.author_id;
$$;

-- ── 4. Author functions ───────────────────────────────────────────────────────────────────

-- The author, still holding the summary's active link. Read without a lock: an unauthorized
-- caller never queues behind a writer (OPS-006 rule 9). Missing, foreign and not-yours are the
-- same 42501.
CREATE OR REPLACE FUNCTION private.handoff_author_summary(p_actor_id uuid, p_summary_id uuid)
RETURNS public.care_handoff_summaries LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE v_summary public.care_handoff_summaries%ROWTYPE;
BEGIN
  SELECT * INTO v_summary FROM public.care_handoff_summaries WHERE id = p_summary_id;
  IF NOT FOUND OR v_summary.author_id <> p_actor_id OR NOT (v_summary.care_team_id =
      ANY (private.clinician_patient_links(p_actor_id, v_summary.patient_id))) THEN
    RAISE EXCEPTION 'handoff summary unavailable' USING ERRCODE = '42501';
  END IF;
  RETURN v_summary;
END;
$$;

CREATE OR REPLACE FUNCTION public.list_care_handoff_share_candidates(
  p_actor_id uuid, p_summary_id uuid, p_query text DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  PERFORM private.handoff_author_summary(p_actor_id, p_summary_id);
  RETURN COALESCE((SELECT jsonb_agg(jsonb_build_object('clinician_id', c.clinician_id,
      'first_name', c.first_name, 'last_name', c.last_name, 'specialty', c.specialty,
      'clinics', c.clinics, 'bases', to_jsonb(c.bases)))
    FROM private.handoff_share_candidates(p_summary_id, NULL, p_query) c), '[]');
END;
$$;

CREATE OR REPLACE FUNCTION private.handoff_share_json(p_share public.care_handoff_shares)
RETURNS jsonb LANGUAGE sql STABLE SET search_path = '' AS $$
  SELECT jsonb_build_object('id', p_share.id, 'summary_id', p_share.summary_id,
    'version', p_share.version, 'recipient_id', p_share.recipient_id,
    'recipient_name', (SELECT concat_ws(' ', r.first_name, r.last_name)
        FROM public.clinicians r WHERE r.id = p_share.recipient_id),
    'recipient_specialty', (SELECT r.specialty FROM public.clinicians r WHERE r.id = p_share.recipient_id),
    'shared_at', p_share.shared_at, 'revoked_at', p_share.revoked_at);
$$;

CREATE OR REPLACE FUNCTION public.share_care_handoff_summary(
  p_actor_id uuid, p_summary_id uuid, p_version integer, p_recipient_id uuid
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_summary public.care_handoff_summaries%ROWTYPE;
  v_share public.care_handoff_shares%ROWTYPE;
  v_author text;
  v_existing boolean;
BEGIN
  PERFORM private.handoff_author_summary(p_actor_id, p_summary_id);   -- authorize, no lock
  -- Serialise with save, approve and every other share of this summary.
  SELECT * INTO v_summary FROM public.care_handoff_summaries WHERE id = p_summary_id FOR UPDATE;
  IF NOT FOUND OR v_summary.author_id <> p_actor_id OR NOT (v_summary.care_team_id =
      ANY (private.clinician_patient_links(p_actor_id, v_summary.patient_id))) THEN
    RAISE EXCEPTION 'handoff summary unavailable' USING ERRCODE = '42501';
  END IF;
  -- Only the approved current version can be shared; an edit returned the summary to draft.
  IF v_summary.status <> 'approved' OR v_summary.approved_version IS DISTINCT FROM p_version
     OR v_summary.current_version <> p_version THEN
    RAISE EXCEPTION 'HANDOFF_NOT_APPROVED: only the approved version can be shared'
      USING ERRCODE = '22023', HINT = 'HANDOFF_NOT_APPROVED';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM private.handoff_share_candidates(p_summary_id, p_recipient_id)) THEN
    RAISE EXCEPTION 'HANDOFF_RECIPIENT_NOT_ALLOWED: this clinician cannot receive the summary'
      USING ERRCODE = '22023', HINT = 'HANDOFF_RECIPIENT_NOT_ALLOWED';
  END IF;
  SELECT * INTO v_share FROM public.care_handoff_shares
    WHERE summary_id = p_summary_id AND version = p_version AND recipient_id = p_recipient_id;
  v_existing := FOUND;
  IF v_existing AND v_share.revoked_at IS NULL THEN
    RETURN private.handoff_share_json(v_share) || jsonb_build_object('replayed', true);
  END IF;
  IF (SELECT count(*) FROM public.care_handoff_shares
      WHERE summary_id = p_summary_id AND revoked_at IS NULL) >= 50 THEN
    RAISE EXCEPTION 'too many shares of this handoff summary' USING ERRCODE = '54000';
  END IF;
  IF v_existing THEN
    UPDATE public.care_handoff_shares
       SET revoked_at = NULL, revoked_by = NULL, generation = generation + 1,
           shared_at = clock_timestamp()
     WHERE id = v_share.id RETURNING * INTO v_share;
  ELSE
    INSERT INTO public.care_handoff_shares(summary_id, version, patient_id, author_id,
      recipient_id, title, purpose, approved_by, approved_at)
    VALUES (p_summary_id, p_version, v_summary.patient_id, p_actor_id, p_recipient_id,
      v_summary.title, v_summary.purpose, v_summary.approved_by, v_summary.approved_at)
    RETURNING * INTO v_share;
  END IF;
  INSERT INTO public.care_handoff_summary_events(summary_id, patient_id, care_team_id, version,
    event_type, actor_id, share_id, recipient_id)
  VALUES (p_summary_id, v_summary.patient_id, v_summary.care_team_id, p_version, 'shared',
    p_actor_id, v_share.id, p_recipient_id);
  -- Same transaction as the share: the recipient is told once per generation.
  SELECT concat_ws(' ', first_name, last_name) INTO v_author
    FROM public.clinicians WHERE id = p_actor_id;
  PERFORM private.notification_capture('care_handoff_shares', v_share.id, v_share.patient_id,
    'handoff_shared', 'follow_up', 'clinician', p_recipient_id,
    jsonb_build_object('share_id', v_share.id, 'summary_id', p_summary_id,
      'version', p_version, 'generation', v_share.generation, 'actor_name', v_author),
    'handoff_share:' || v_share.id::text || ':' || v_share.generation::text, v_share.shared_at);
  RETURN private.handoff_share_json(v_share) || jsonb_build_object('replayed', false);
END;
$$;

CREATE OR REPLACE FUNCTION public.revoke_care_handoff_share(p_actor_id uuid, p_share_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_share public.care_handoff_shares%ROWTYPE;
  v_summary public.care_handoff_summaries%ROWTYPE;
BEGIN
  SELECT * INTO v_share FROM public.care_handoff_shares WHERE id = p_share_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'handoff summary unavailable' USING ERRCODE = '42501';
  END IF;
  PERFORM private.handoff_author_summary(p_actor_id, v_share.summary_id);   -- authorize, no lock
  SELECT * INTO v_summary FROM public.care_handoff_summaries
    WHERE id = v_share.summary_id FOR UPDATE;
  SELECT * INTO v_share FROM public.care_handoff_shares WHERE id = p_share_id;
  IF v_share.revoked_at IS NOT NULL THEN
    RETURN private.handoff_share_json(v_share) || jsonb_build_object('replayed', true);
  END IF;
  UPDATE public.care_handoff_shares SET revoked_at = clock_timestamp(), revoked_by = p_actor_id
    WHERE id = p_share_id AND revoked_at IS NULL RETURNING * INTO v_share;
  INSERT INTO public.care_handoff_summary_events(summary_id, patient_id, care_team_id, version,
    event_type, actor_id, share_id, recipient_id)
  VALUES (v_share.summary_id, v_share.patient_id, v_summary.care_team_id, v_share.version,
    'share_revoked', p_actor_id, v_share.id, v_share.recipient_id);
  RETURN private.handoff_share_json(v_share) || jsonb_build_object('replayed', false);
END;
$$;

CREATE OR REPLACE FUNCTION public.list_care_handoff_shares(p_actor_id uuid, p_summary_id uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  PERFORM private.handoff_author_summary(p_actor_id, p_summary_id);
  RETURN COALESCE((SELECT jsonb_agg(private.handoff_share_json(s)
      ORDER BY s.shared_at DESC, s.id)
    FROM (SELECT * FROM public.care_handoff_shares WHERE summary_id = p_summary_id
      ORDER BY shared_at DESC LIMIT 100) s), '[]');
END;
$$;

-- The audit list now names the recipient of a share event. Same signature and result as 089.
CREATE OR REPLACE FUNCTION public.read_care_handoff_summary(
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
        'recipient_id', e.recipient_id,
        'recipient_name', (SELECT concat_ws(' ', r.first_name, r.last_name)
            FROM public.clinicians r WHERE r.id = e.recipient_id),
        'created_at', e.created_at) ORDER BY e.created_at DESC, e.id)
      FROM (SELECT * FROM public.care_handoff_summary_events
        WHERE summary_id = p_summary_id ORDER BY created_at DESC LIMIT 100) e), '[]'));
END;
$$;

-- ── 5. Recipient functions ────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.list_care_handoff_shared_with_me(p_actor_id uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
  SELECT COALESCE(jsonb_agg(item ORDER BY shared_ts DESC, sid), '[]') FROM (
    SELECT h.shared_at AS shared_ts, h.id AS sid,
      jsonb_build_object('share_id', h.id, 'summary_id', h.summary_id, 'version', h.version,
        'title', h.title, 'purpose', h.purpose, 'patient_id', h.patient_id,
        'patient_name', concat_ws(' ', p.first_name, p.last_name),
        'author_name', concat_ws(' ', a.first_name, a.last_name), 'author_specialty', a.specialty,
        'shared_at', h.shared_at, 'approved_at', h.approved_at,
        'newer', (SELECT jsonb_build_object('share_id', n.id, 'version', n.version)
            FROM public.care_handoff_shares n
           WHERE n.summary_id = h.summary_id AND n.recipient_id = h.recipient_id
             AND n.version > h.version AND n.revoked_at IS NULL
           ORDER BY n.version DESC LIMIT 1)) AS item
      FROM public.care_handoff_shares h
      JOIN public.patients p ON p.id = h.patient_id
      JOIN public.clinicians a ON a.id = h.author_id
     WHERE h.recipient_id = p_actor_id AND private.handoff_share_usable(h)
     ORDER BY h.shared_at DESC, h.id LIMIT 100) q;
$$;

CREATE OR REPLACE FUNCTION public.read_shared_care_handoff(p_actor_id uuid, p_share_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_share public.care_handoff_shares%ROWTYPE;
BEGIN
  SELECT * INTO v_share FROM public.care_handoff_shares WHERE id = p_share_id;
  IF NOT FOUND OR v_share.recipient_id <> p_actor_id OR NOT private.handoff_share_usable(v_share) THEN
    RAISE EXCEPTION 'handoff summary unavailable' USING ERRCODE = '42501';
  END IF;
  -- Opening PHI is audited, once per ten minutes per reader so a refresh does not flood it.
  IF NOT EXISTS (SELECT 1 FROM public.care_handoff_summary_events e
      WHERE e.share_id = v_share.id AND e.actor_id = p_actor_id AND e.event_type = 'shared_viewed'
        AND e.created_at > clock_timestamp() - interval '10 minutes') THEN
    INSERT INTO public.care_handoff_summary_events(summary_id, patient_id, care_team_id, version,
      event_type, actor_id, share_id, recipient_id)
    SELECT v_share.summary_id, v_share.patient_id, sm.care_team_id, v_share.version,
           'shared_viewed', p_actor_id, v_share.id, p_actor_id
      FROM public.care_handoff_summaries sm WHERE sm.id = v_share.summary_id;
  END IF;
  RETURN private.handoff_shared_payload(v_share);
END;
$$;

CREATE OR REPLACE FUNCTION public.record_shared_care_handoff_export(
  p_actor_id uuid, p_share_id uuid, p_format text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_share public.care_handoff_shares%ROWTYPE;
BEGIN
  IF p_format NOT IN ('print', 'fhir') THEN
    RAISE EXCEPTION 'unsupported export format' USING ERRCODE = '22023';
  END IF;
  SELECT * INTO v_share FROM public.care_handoff_shares WHERE id = p_share_id;
  IF NOT FOUND OR v_share.recipient_id <> p_actor_id OR NOT private.handoff_share_usable(v_share) THEN
    RAISE EXCEPTION 'handoff summary unavailable' USING ERRCODE = '42501';
  END IF;
  INSERT INTO public.care_handoff_summary_events(summary_id, patient_id, care_team_id, version,
    event_type, export_format, actor_id, share_id, recipient_id)
  SELECT v_share.summary_id, v_share.patient_id, sm.care_team_id, v_share.version,
         'shared_exported', p_format, p_actor_id, v_share.id, p_actor_id
    FROM public.care_handoff_summaries sm WHERE sm.id = v_share.summary_id;
  RETURN private.handoff_shared_payload(v_share);
END;
$$;

-- ── 6. Notification-centre integration (wrappers over the unchanged ledger helpers) ───────

DO $$
DECLARE v_def text; v_name text;
BEGIN
  FOREACH v_name IN ARRAY ARRAY['notification_events_event_type_check',
    'notification_events_source_type_check'] LOOP
    SELECT pg_get_constraintdef(oid) INTO v_def FROM pg_constraint
     WHERE conrelid = 'public.notification_events'::regclass AND conname = v_name;
    IF v_def IS NULL THEN
      RAISE EXCEPTION '096: % is missing', v_name;
    END IF;
    IF v_def NOT LIKE '%handoff_shared%' AND v_def NOT LIKE '%care_handoff_shares%' THEN
      v_def := replace(v_def, '::text])', '::text, '''
        || CASE WHEN v_name LIKE '%event_type%' THEN 'handoff_shared' ELSE 'care_handoff_shares' END
        || '''::text])');
      EXECUTE format('ALTER TABLE public.notification_events DROP CONSTRAINT %I', v_name);
      EXECUTE format('ALTER TABLE public.notification_events ADD CONSTRAINT %I %s', v_name, v_def);
    END IF;
  END LOOP;
END;
$$;

-- Keep each existing body exactly as it is, under a new name, once.
DO $$
BEGIN
  IF to_regprocedure('private.notification_source_core(text,uuid)') IS NULL THEN
    ALTER FUNCTION private.notification_source(text, uuid) RENAME TO notification_source_core;
  END IF;
  IF to_regprocedure('private.notification_authorized_core(public.notification_events,uuid,text)') IS NULL THEN
    ALTER FUNCTION private.notification_authorized(public.notification_events, uuid, text)
      RENAME TO notification_authorized_core;
  END IF;
  IF to_regprocedure('private.notification_actionable_core(public.notification_events,text)') IS NULL THEN
    ALTER FUNCTION private.notification_actionable(public.notification_events, text)
      RENAME TO notification_actionable_core;
  END IF;
  IF to_regprocedure('private.notification_scope_core(uuid,text)') IS NULL THEN
    ALTER FUNCTION private.notification_scope(uuid, text) RENAME TO notification_scope_core;
  END IF;
  IF to_regprocedure('private.notification_owner_sees_core(text,uuid,text,uuid,uuid)') IS NULL THEN
    ALTER FUNCTION private.notification_owner_sees(text, uuid, text, uuid, uuid)
      RENAME TO notification_owner_sees_core;
  END IF;
END;
$$;

-- The share as the ledger sees it: ids and the revocation flag, no clinical text and no
-- "status" key (the ledger reads one for appointments).
CREATE OR REPLACE FUNCTION private.notification_source(p_type text, p_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  IF p_type = 'care_handoff_shares' THEN
    RETURN (SELECT jsonb_build_object('id', h.id, 'patient_id', h.patient_id,
        'recipient_id', h.recipient_id, 'summary_id', h.summary_id, 'version', h.version,
        'generation', h.generation, 'revoked', h.revoked_at IS NOT NULL,
        'created_at', h.shared_at)
      FROM public.care_handoff_shares h WHERE h.id = p_id);
  END IF;
  RETURN private.notification_source_core(p_type, p_id);
END;
$$;

-- A handoff item is for its named recipient only, while the share is usable. Nothing about
-- the patient's other records is implied: the recipient needs no care-team link.
CREATE OR REPLACE FUNCTION private.notification_authorized(
  e public.notification_events, p_actor uuid, p_role text
) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  IF e.source_type = 'care_handoff_shares' OR e.event_type = 'handoff_shared' THEN
    RETURN p_role = 'clinician' AND e.source_type = 'care_handoff_shares'
      AND e.event_type = 'handoff_shared' AND e.audience = 'clinician'
      AND e.recipient_id = p_actor
      AND EXISTS (SELECT 1 FROM public.care_handoff_shares h
        WHERE h.id = e.source_id AND h.recipient_id = p_actor AND h.patient_id = e.patient_id
          -- Only the current grant: an older, revoked-then-reshared event is gone.
          AND h.generation::text = e.metadata->>'generation'
          AND private.handoff_share_usable(h));
  END IF;
  RETURN private.notification_authorized_core(e, p_actor, p_role);
END;
$$;

CREATE OR REPLACE FUNCTION private.notification_actionable(
  e public.notification_events, p_role text
) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  IF e.event_type = 'handoff_shared' THEN RETURN false; END IF; -- news, never work
  RETURN private.notification_actionable_core(e, p_role);
END;
$$;

-- The list is limited to patients in scope; a patient with a usable share to me is in scope
-- for that item only (authorization above still decides, per item).
CREATE OR REPLACE FUNCTION private.notification_scope(p_actor uuid, p_role text) RETURNS uuid[]
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
  SELECT private.notification_scope_core(p_actor, p_role) || CASE WHEN p_role = 'clinician' THEN
    COALESCE((SELECT array_agg(DISTINCT h.patient_id) FROM public.care_handoff_shares h
      WHERE h.recipient_id = p_actor AND h.revoked_at IS NULL), ARRAY[]::uuid[])
    ELSE ARRAY[]::uuid[] END;
$$;

-- Widening the scope must not make other work addressable to someone with no link: the
-- ownership question is only ever asked about a clinician who holds an active link.
CREATE OR REPLACE FUNCTION private.notification_owner_sees(
  p_type text, p_id uuid, p_kind text, p_actor uuid, p_patient uuid
) RETURNS boolean LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  IF cardinality(private.clinician_patient_links(p_actor, p_patient)) = 0 THEN
    RETURN false;
  END IF;
  RETURN private.notification_owner_sees_core(p_type, p_id, p_kind, p_actor, p_patient);
END;
$$;

-- ── 7. Grants ─────────────────────────────────────────────────────────────────────────────

REVOKE ALL ON FUNCTION
  private.care_handoff_share_guard(),
  private.handoff_share_candidates(uuid, uuid, text),
  private.handoff_share_usable(public.care_handoff_shares),
  private.handoff_shared_payload(public.care_handoff_shares),
  private.handoff_author_summary(uuid, uuid),
  private.handoff_share_json(public.care_handoff_shares),
  private.notification_source_core(text, uuid),
  private.notification_authorized_core(public.notification_events, uuid, text),
  private.notification_actionable_core(public.notification_events, text),
  private.notification_scope_core(uuid, text),
  private.notification_owner_sees_core(text, uuid, text, uuid, uuid),
  private.notification_source(text, uuid),
  private.notification_authorized(public.notification_events, uuid, text),
  private.notification_actionable(public.notification_events, text),
  private.notification_scope(uuid, text),
  private.notification_owner_sees(text, uuid, text, uuid, uuid),
  public.list_care_handoff_share_candidates(uuid, uuid, text),
  public.share_care_handoff_summary(uuid, uuid, integer, uuid),
  public.revoke_care_handoff_share(uuid, uuid),
  public.list_care_handoff_shares(uuid, uuid),
  public.read_care_handoff_summary(uuid, uuid, integer),
  public.list_care_handoff_shared_with_me(uuid),
  public.read_shared_care_handoff(uuid, uuid),
  public.record_shared_care_handoff_export(uuid, uuid, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION
  private.care_handoff_share_guard(),
  private.handoff_share_candidates(uuid, uuid, text),
  private.handoff_share_usable(public.care_handoff_shares),
  private.handoff_shared_payload(public.care_handoff_shares),
  private.handoff_author_summary(uuid, uuid),
  private.handoff_share_json(public.care_handoff_shares),
  private.notification_source_core(text, uuid),
  private.notification_authorized_core(public.notification_events, uuid, text),
  private.notification_actionable_core(public.notification_events, text),
  private.notification_scope_core(uuid, text),
  private.notification_owner_sees_core(text, uuid, text, uuid, uuid),
  private.notification_source(text, uuid),
  private.notification_authorized(public.notification_events, uuid, text),
  private.notification_actionable(public.notification_events, text),
  private.notification_scope(uuid, text),
  private.notification_owner_sees(text, uuid, text, uuid, uuid),
  public.list_care_handoff_share_candidates(uuid, uuid, text),
  public.share_care_handoff_summary(uuid, uuid, integer, uuid),
  public.revoke_care_handoff_share(uuid, uuid),
  public.list_care_handoff_shares(uuid, uuid),
  public.read_care_handoff_summary(uuid, uuid, integer),
  public.list_care_handoff_shared_with_me(uuid),
  public.read_shared_care_handoff(uuid, uuid),
  public.record_shared_care_handoff_export(uuid, uuid, text)
  TO service_role;

-- ── 8. Verification ───────────────────────────────────────────────────────────────────────

DO $verify$
DECLARE v_function text;
BEGIN
  FOREACH v_function IN ARRAY ARRAY[
    'public.list_care_handoff_share_candidates(uuid,uuid,text)',
    'public.share_care_handoff_summary(uuid,uuid,integer,uuid)',
    'public.revoke_care_handoff_share(uuid,uuid)',
    'public.list_care_handoff_shares(uuid,uuid)',
    'public.read_care_handoff_summary(uuid,uuid,integer)',
    'public.list_care_handoff_shared_with_me(uuid)',
    'public.read_shared_care_handoff(uuid,uuid)',
    'public.record_shared_care_handoff_export(uuid,uuid,text)',
    'private.handoff_share_candidates(uuid,uuid,text)',
    'private.handoff_author_summary(uuid,uuid)',
    'private.notification_source(text,uuid)',
    'private.notification_authorized(public.notification_events,uuid,text)',
    'private.notification_actionable(public.notification_events,text)',
    'private.notification_scope(uuid,text)',
    'private.notification_owner_sees(text,uuid,text,uuid,uuid)'] LOOP
    IF has_function_privilege('anon', v_function, 'EXECUTE')
       OR has_function_privilege('authenticated', v_function, 'EXECUTE')
       OR NOT has_function_privilege('service_role', v_function, 'EXECUTE') THEN
      RAISE EXCEPTION '096: wrong execute grants on %', v_function;
    END IF;
  END LOOP;
  IF NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public' AND c.relname = 'care_handoff_shares' AND c.relrowsecurity) THEN
    RAISE EXCEPTION '096: row-level security is off on care_handoff_shares';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.role_table_grants
      WHERE table_schema = 'public' AND table_name = 'care_handoff_shares'
        AND grantee IN ('anon', 'authenticated', 'PUBLIC')) THEN
    RAISE EXCEPTION '096: a browser role can reach care_handoff_shares';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
      WHERE c.relname = 'care_handoff_shares') THEN
    RAISE EXCEPTION '096: care_handoff_shares has a policy';
  END IF;
  IF (SELECT count(*) FROM pg_trigger WHERE tgname IN ('care_handoff_shares_guard',
      'care_handoff_shares_no_truncate')) <> 2 THEN
    RAISE EXCEPTION '096: the share guard triggers are missing';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname IN ('public', 'private')
        AND (p.proname LIKE '%handoff%' OR p.proname IN ('notification_source',
          'notification_authorized', 'notification_actionable', 'notification_scope',
          'notification_owner_sees'))
        AND p.prosecdef AND NOT EXISTS (SELECT 1 FROM unnest(p.proconfig) c
          WHERE c LIKE 'search_path=%')) THEN
    RAISE EXCEPTION '096: a handoff or ledger function has no fixed search_path';
  END IF;
  IF (SELECT pg_get_constraintdef(oid) FROM pg_constraint
      WHERE conrelid = 'public.notification_events'::regclass
        AND conname = 'notification_events_event_type_check') NOT LIKE '%handoff_shared%'
     OR (SELECT pg_get_constraintdef(oid) FROM pg_constraint
      WHERE conrelid = 'public.notification_events'::regclass
        AND conname = 'notification_events_source_type_check') NOT LIKE '%care_handoff_shares%' THEN
    RAISE EXCEPTION '096: the notification ledger does not accept a handoff share';
  END IF;
END;
$verify$;
