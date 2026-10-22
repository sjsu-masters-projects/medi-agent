-- MED-002: patient confirmation requests for a medication discrepancy.
--
-- While reconciling an imported medication against the approved list, a clinician can ask the
-- patient one plain question about it ("Are you still taking Metformin 500 mg twice a day?").
-- The patient answers Yes / No, I stopped / It changed (with a short note) / Not sure.
--
--   * The answer is PATIENT TESTIMONY. Nothing here writes to medications, clinical_facts, the
--     care plan or reminders; the clinician reads the answer next to the candidate and decides
--     through the existing reconciliation decision (apply_clinical_fact_reconciliation).
--   * A request belongs to ONE care-team link (care_team_id) of the asking clinician. Create,
--     list and cancel-less reads re-check in the database that the caller holds that active
--     link and may see the fact (fact_visible_to_links); everything else answers 42501, which
--     the API reports as "not found" so nothing can be probed.
--   * The patient can only see and answer their own requests while the link is still active.
--   * Idempotency (OPS-006 rules 4-5): the request id is client-supplied, repeating it returns
--     the stored request; a second ask for the same fact by the same link while one is open
--     returns the open one. Answering is a guarded transition open -> answered (rule 2);
--     repeating the same answer is a replay, a different answer is a conflict (40001).
--   * Expiry uses the database clock (rule 18); an expired request is neither shown to the
--     patient nor answerable, and the clinician sees it as expired. No worker is needed.
--   * Lock order (rule 7): lock-free authorization read, then the patient advisory lock, then
--     the request row by primary key. Locks are transaction-scoped and short (rule 8).
--   * Events carry ids and types only (no medication text, no answer text) and have no
--     foreign keys, so they survive patient erasure like the other audit trails.
--
-- Every object revokes the browser roles; the Data API reaches nothing. The final block fails
-- the migration if a grant, policy, trigger or function lost its check.

-- ── 1. Tables ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.medication_confirmation_requests (
  id uuid PRIMARY KEY,
  patient_id uuid NOT NULL REFERENCES public.patients(id) ON DELETE CASCADE,
  care_team_id uuid NOT NULL REFERENCES public.care_teams(id) ON DELETE CASCADE,
  requested_by uuid NOT NULL,
  fact_id uuid NOT NULL REFERENCES public.clinical_facts(id) ON DELETE CASCADE,
  subject_kind text NOT NULL CHECK (subject_kind IN ('imported', 'approved')),
  medication_id uuid REFERENCES public.medications(id) ON DELETE SET NULL,
  medication_name text NOT NULL CHECK (char_length(btrim(medication_name)) BETWEEN 1 AND 200),
  dosage text CHECK (dosage IS NULL OR char_length(dosage) <= 100),
  frequency text CHECK (frequency IS NULL OR char_length(frequency) <= 200),
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'answered', 'expired')),
  answer text CHECK (answer IS NULL OR answer IN ('yes', 'stopped', 'changed', 'unsure')),
  answer_note text CHECK (answer_note IS NULL OR char_length(btrim(answer_note)) BETWEEN 1 AND 500),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz NOT NULL,
  answered_at timestamptz,
  CHECK ((status = 'answered') = (answer IS NOT NULL AND answered_at IS NOT NULL)),
  CHECK (answer IS DISTINCT FROM 'changed' OR answer_note IS NOT NULL),
  CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS medication_confirmation_requests_patient
  ON public.medication_confirmation_requests(patient_id, status, expires_at);
CREATE INDEX IF NOT EXISTS medication_confirmation_requests_fact
  ON public.medication_confirmation_requests(fact_id, created_at DESC);
-- One open request per fact and care-team link (a repeat ask returns it).
CREATE UNIQUE INDEX IF NOT EXISTS medication_confirmation_requests_one_open
  ON public.medication_confirmation_requests(fact_id, care_team_id) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS public.medication_confirmation_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id uuid NOT NULL,
  patient_id uuid NOT NULL,
  care_team_id uuid NOT NULL,
  fact_id uuid NOT NULL,
  event_type text NOT NULL CHECK (event_type IN ('requested', 'answered')),
  answer text CHECK (answer IS NULL OR answer IN ('yes', 'stopped', 'changed', 'unsure')),
  actor_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS medication_confirmation_events_request
  ON public.medication_confirmation_events(request_id, created_at);

-- ── 2. Append-only events; an answered request is immutable ──────────────────────────────

CREATE OR REPLACE FUNCTION private.medication_confirmation_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
  IF TG_TABLE_NAME = 'medication_confirmation_requests' THEN
    IF TG_OP = 'DELETE' THEN
      RETURN OLD; -- erasure cascades from the patient or the care-team link
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.status = 'open' AND NEW.status IN ('answered', 'expired')
       AND (OLD.id, OLD.patient_id, OLD.care_team_id, OLD.requested_by, OLD.fact_id,
            OLD.subject_kind, OLD.medication_name, OLD.dosage, OLD.frequency,
            OLD.created_at, OLD.expires_at)
        IS NOT DISTINCT FROM
           (NEW.id, NEW.patient_id, NEW.care_team_id, NEW.requested_by, NEW.fact_id,
            NEW.subject_kind, NEW.medication_name, NEW.dosage, NEW.frequency,
            NEW.created_at, NEW.expires_at) THEN
      RETURN NEW;
    END IF;
    -- The medication link may be nulled when the approved record is erased.
    IF TG_OP = 'UPDATE' AND NEW.medication_id IS NULL AND OLD.medication_id IS NOT NULL
       AND (OLD.status, OLD.answer, OLD.answer_note, OLD.medication_name)
        IS NOT DISTINCT FROM (NEW.status, NEW.answer, NEW.answer_note, NEW.medication_name) THEN
      RETURN NEW;
    END IF;
  END IF;
  RAISE EXCEPTION 'Medication confirmation records are immutable once written'
    USING ERRCODE = '42501';
END;
$$;

DROP TRIGGER IF EXISTS medication_confirmation_requests_immutable
  ON public.medication_confirmation_requests;
CREATE TRIGGER medication_confirmation_requests_immutable
  BEFORE UPDATE OR DELETE ON public.medication_confirmation_requests
  FOR EACH ROW EXECUTE FUNCTION private.medication_confirmation_immutable();
DROP TRIGGER IF EXISTS medication_confirmation_events_append_only
  ON public.medication_confirmation_events;
CREATE TRIGGER medication_confirmation_events_append_only
  BEFORE UPDATE OR DELETE ON public.medication_confirmation_events
  FOR EACH ROW EXECUTE FUNCTION private.medication_confirmation_immutable();
DROP TRIGGER IF EXISTS medication_confirmation_events_no_truncate
  ON public.medication_confirmation_events;
CREATE TRIGGER medication_confirmation_events_no_truncate
  BEFORE TRUNCATE ON public.medication_confirmation_events
  FOR EACH STATEMENT EXECUTE FUNCTION private.medication_confirmation_immutable();

-- ── 3. Row-level security: the Data API reaches nothing ──────────────────────────────────

ALTER TABLE public.medication_confirmation_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.medication_confirmation_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.medication_confirmation_requests, public.medication_confirmation_events
  FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.medication_confirmation_requests, public.medication_confirmation_events
  TO service_role;

-- ── 4. Functions ─────────────────────────────────────────────────────────────────────────

-- The JSON a reader gets. effective_status folds the database clock in, so no worker is needed.
CREATE OR REPLACE FUNCTION private.medication_confirmation_json(
  p_request public.medication_confirmation_requests, p_for_patient boolean
) RETURNS jsonb LANGUAGE sql STABLE SET search_path = '' AS $$
  SELECT jsonb_build_object(
    'id', p_request.id, 'fact_id', p_request.fact_id, 'care_team_id', p_request.care_team_id,
    'subject_kind', p_request.subject_kind, 'medication_name', p_request.medication_name,
    'dosage', p_request.dosage, 'frequency', p_request.frequency,
    'status', CASE WHEN p_request.status = 'open' AND p_request.expires_at <= clock_timestamp()
                   THEN 'expired' ELSE p_request.status END,
    'answer', p_request.answer, 'answer_note', p_request.answer_note,
    'created_at', p_request.created_at, 'expires_at', p_request.expires_at,
    'answered_at', p_request.answered_at)
  || CASE WHEN p_for_patient THEN '{}'::jsonb ELSE
       jsonb_build_object('requested_by', p_request.requested_by,
         'patient_id', p_request.patient_id) END
  || COALESCE((SELECT jsonb_build_object(
        'clinician_name', btrim(c.first_name || ' ' || c.last_name),
        'specialty', c.specialty, 'clinic_name', cl.display_name)
      FROM public.care_teams t
      JOIN public.clinicians c ON c.id = t.clinician_id
      LEFT JOIN public.clinics cl ON cl.id = t.clinic_id
      WHERE t.id = p_request.care_team_id), '{}'::jsonb);
$$;

-- Clinician: ask the patient. Authorization is lock-free and first (rule 9).
CREATE OR REPLACE FUNCTION public.create_medication_confirmation(
  p_actor_id uuid, p_patient_id uuid, p_care_team_id uuid, p_request_id uuid, p_fact_id uuid,
  p_subject_kind text, p_medication_id uuid, p_medication_name text, p_dosage text,
  p_frequency text, p_ttl_days integer DEFAULT 14
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_links uuid[] := private.clinician_patient_links(p_actor_id, p_patient_id);
  v_row public.medication_confirmation_requests%ROWTYPE;
BEGIN
  IF NOT (p_care_team_id = ANY (v_links))
     OR NOT private.fact_visible_to_links(p_fact_id, v_links)
     OR NOT EXISTS (SELECT 1 FROM public.clinical_facts f
        WHERE f.id = p_fact_id AND f.patient_id = p_patient_id AND f.fact_type = 'medication')
  THEN
    RAISE EXCEPTION 'confirmation unavailable' USING ERRCODE = '42501';
  END IF;
  IF p_subject_kind NOT IN ('imported', 'approved')
     OR p_ttl_days NOT BETWEEN 1 AND 30
     OR (p_subject_kind = 'approved' AND NOT EXISTS (SELECT 1 FROM public.medications m
          WHERE m.id = p_medication_id AND m.patient_id = p_patient_id)) THEN
    RAISE EXCEPTION 'invalid confirmation request' USING ERRCODE = '22023';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('medconfirm:' || p_patient_id::text, 0));
  SELECT * INTO v_row FROM public.medication_confirmation_requests WHERE id = p_request_id;
  IF FOUND THEN
    IF v_row.requested_by = p_actor_id AND v_row.patient_id = p_patient_id
       AND v_row.care_team_id = p_care_team_id AND v_row.fact_id = p_fact_id THEN
      RETURN private.medication_confirmation_json(v_row, false)
        || jsonb_build_object('replayed', true);
    END IF;
    RAISE EXCEPTION 'confirmation unavailable' USING ERRCODE = '42501';
  END IF;
  -- An elapsed unanswered request is retired (guarded open -> expired) so it frees the slot.
  UPDATE public.medication_confirmation_requests SET status = 'expired'
   WHERE fact_id = p_fact_id AND care_team_id = p_care_team_id AND status = 'open'
     AND expires_at <= clock_timestamp();
  -- A repeat ask while one is open (even under another request id) returns the open one.
  SELECT * INTO v_row FROM public.medication_confirmation_requests
   WHERE fact_id = p_fact_id AND care_team_id = p_care_team_id AND status = 'open'
     AND expires_at > clock_timestamp();
  IF FOUND THEN
    RETURN private.medication_confirmation_json(v_row, false)
      || jsonb_build_object('replayed', true);
  END IF;
  IF (SELECT count(*) FROM public.medication_confirmation_requests
       WHERE patient_id = p_patient_id AND status = 'open'
         AND expires_at > clock_timestamp()) >= 10 THEN
    RAISE EXCEPTION 'too many open confirmation requests' USING ERRCODE = '54000';
  END IF;
  INSERT INTO public.medication_confirmation_requests(id, patient_id, care_team_id,
    requested_by, fact_id, subject_kind, medication_id, medication_name, dosage, frequency,
    expires_at)
  VALUES (p_request_id, p_patient_id, p_care_team_id, p_actor_id, p_fact_id, p_subject_kind,
    CASE WHEN p_subject_kind = 'approved' THEN p_medication_id END,
    btrim(p_medication_name), NULLIF(btrim(p_dosage), ''), NULLIF(btrim(p_frequency), ''),
    clock_timestamp() + make_interval(days => p_ttl_days))
  RETURNING * INTO v_row;
  INSERT INTO public.medication_confirmation_events(request_id, patient_id, care_team_id,
    fact_id, event_type, actor_id)
  VALUES (p_request_id, p_patient_id, p_care_team_id, p_fact_id, 'requested', p_actor_id);
  RETURN private.medication_confirmation_json(v_row, false)
    || jsonb_build_object('replayed', false);
END;
$$;

-- Clinician: every request for this fact that one of the caller's links asked.
CREATE OR REPLACE FUNCTION public.list_fact_medication_confirmations(
  p_actor_id uuid, p_patient_id uuid, p_fact_id uuid
) RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_links uuid[] := private.clinician_patient_links(p_actor_id, p_patient_id);
BEGIN
  IF cardinality(v_links) = 0 OR NOT private.fact_visible_to_links(p_fact_id, v_links) THEN
    RAISE EXCEPTION 'confirmation unavailable' USING ERRCODE = '42501';
  END IF;
  RETURN COALESCE((SELECT jsonb_agg(private.medication_confirmation_json(r, false)
      ORDER BY r.created_at DESC, r.id)
    FROM (SELECT * FROM public.medication_confirmation_requests
      WHERE patient_id = p_patient_id AND fact_id = p_fact_id AND care_team_id = ANY (v_links)
      ORDER BY created_at DESC LIMIT 20) r), '[]'::jsonb);
END;
$$;

-- Patient: open (not expired) questions plus the few most recent answered ones.
CREATE OR REPLACE FUNCTION public.list_patient_medication_confirmations(p_patient_id uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
  SELECT COALESCE(jsonb_agg(private.medication_confirmation_json(r, true)
      ORDER BY r.created_at DESC, r.id), '[]'::jsonb)
  FROM (SELECT * FROM public.medication_confirmation_requests q
    WHERE q.patient_id = p_patient_id
      AND EXISTS (SELECT 1 FROM public.care_teams t
        WHERE t.id = q.care_team_id AND t.patient_id = q.patient_id AND t.status = 'active')
      AND ((q.status = 'open' AND q.expires_at > clock_timestamp())
        OR (q.status = 'answered' AND q.answered_at > clock_timestamp() - interval '7 days'))
    ORDER BY q.created_at DESC LIMIT 20) r;
$$;

-- Patient: answer once. The same answer again is a replay; a different one is a conflict.
CREATE OR REPLACE FUNCTION public.answer_medication_confirmation(
  p_patient_id uuid, p_request_id uuid, p_answer text, p_note text DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_row public.medication_confirmation_requests%ROWTYPE;
  v_note text := NULLIF(btrim(COALESCE(p_note, '')), '');
BEGIN
  IF p_answer NOT IN ('yes', 'stopped', 'changed', 'unsure')
     OR (p_answer = 'changed' AND v_note IS NULL)
     OR (v_note IS NOT NULL AND char_length(v_note) > 500) THEN
    RAISE EXCEPTION 'invalid confirmation answer' USING ERRCODE = '22023';
  END IF;
  -- Lock-free ownership check before queueing on anything (rule 9).
  SELECT r.* INTO v_row FROM public.medication_confirmation_requests r
   WHERE r.id = p_request_id AND r.patient_id = p_patient_id
     AND EXISTS (SELECT 1 FROM public.care_teams t
        WHERE t.id = r.care_team_id AND t.patient_id = r.patient_id AND t.status = 'active');
  IF NOT FOUND THEN
    RAISE EXCEPTION 'confirmation unavailable' USING ERRCODE = '42501';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('medconfirm:' || p_patient_id::text, 0));
  SELECT * INTO v_row FROM public.medication_confirmation_requests
   WHERE id = p_request_id FOR UPDATE;
  IF v_row.status = 'answered' THEN
    IF v_row.answer = p_answer AND v_row.answer_note IS NOT DISTINCT FROM v_note THEN
      RETURN private.medication_confirmation_json(v_row, true)
        || jsonb_build_object('replayed', true);
    END IF;
    RAISE EXCEPTION 'MEDCONFIRM_ALREADY_ANSWERED: this question was already answered'
      USING ERRCODE = '40001', HINT = 'MEDCONFIRM_ALREADY_ANSWERED';
  END IF;
  IF v_row.status = 'expired' OR v_row.expires_at <= clock_timestamp() THEN
    RAISE EXCEPTION 'MEDCONFIRM_EXPIRED: this question has expired'
      USING ERRCODE = '22023', HINT = 'MEDCONFIRM_EXPIRED';
  END IF;
  UPDATE public.medication_confirmation_requests
     SET status = 'answered', answer = p_answer, answer_note = v_note,
         answered_at = clock_timestamp()
   WHERE id = p_request_id AND status = 'open'
  RETURNING * INTO v_row;
  INSERT INTO public.medication_confirmation_events(request_id, patient_id, care_team_id,
    fact_id, event_type, answer, actor_id)
  VALUES (v_row.id, v_row.patient_id, v_row.care_team_id, v_row.fact_id, 'answered',
    p_answer, p_patient_id);
  RETURN private.medication_confirmation_json(v_row, true)
    || jsonb_build_object('replayed', false);
END;
$$;

-- ── 5. Grants ────────────────────────────────────────────────────────────────────────────

REVOKE ALL ON FUNCTION
  private.medication_confirmation_immutable(),
  private.medication_confirmation_json(public.medication_confirmation_requests, boolean),
  public.create_medication_confirmation(uuid, uuid, uuid, uuid, uuid, text, uuid, text, text, text, integer),
  public.list_fact_medication_confirmations(uuid, uuid, uuid),
  public.list_patient_medication_confirmations(uuid),
  public.answer_medication_confirmation(uuid, uuid, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION
  public.create_medication_confirmation(uuid, uuid, uuid, uuid, uuid, text, uuid, text, text, text, integer),
  public.list_fact_medication_confirmations(uuid, uuid, uuid),
  public.list_patient_medication_confirmations(uuid),
  public.answer_medication_confirmation(uuid, uuid, text, text)
  TO service_role;

-- ── 6. Verification ──────────────────────────────────────────────────────────────────────

DO $verify$
DECLARE v_function text;
BEGIN
  FOREACH v_function IN ARRAY ARRAY[
    'public.create_medication_confirmation(uuid,uuid,uuid,uuid,uuid,text,uuid,text,text,text,integer)',
    'public.list_fact_medication_confirmations(uuid,uuid,uuid)',
    'public.list_patient_medication_confirmations(uuid)',
    'public.answer_medication_confirmation(uuid,uuid,text,text)'] LOOP
    IF has_function_privilege('anon', v_function, 'EXECUTE')
       OR has_function_privilege('authenticated', v_function, 'EXECUTE')
       OR NOT has_function_privilege('service_role', v_function, 'EXECUTE') THEN
      RAISE EXCEPTION '093: wrong execute grants on %', v_function;
    END IF;
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public' AND c.relname IN ('medication_confirmation_requests',
        'medication_confirmation_events') AND NOT c.relrowsecurity) THEN
    RAISE EXCEPTION '093: row-level security is off on a confirmation table';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.role_table_grants
      WHERE table_schema = 'public' AND table_name LIKE 'medication_confirmation_%'
        AND grantee IN ('anon', 'authenticated', 'PUBLIC')) THEN
    RAISE EXCEPTION '093: a browser role can reach a confirmation table';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
      WHERE c.relname LIKE 'medication_confirmation_%') THEN
    RAISE EXCEPTION '093: a confirmation table has a policy';
  END IF;
  IF (SELECT count(*) FROM pg_trigger WHERE tgname IN (
      'medication_confirmation_requests_immutable', 'medication_confirmation_events_append_only',
      'medication_confirmation_events_no_truncate')) <> 3 THEN
    RAISE EXCEPTION '093: the immutability triggers are missing';
  END IF;
END;
$verify$;
