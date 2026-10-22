-- AI-003: Nora conversation continuity.
-- Re-runnable. Inert until the backend writes to it; the chat path keeps working without it.
--
--   1. chat_conversation_summaries: ONE rolling summary of the older part of a conversation, in
--      the conversation's language, read by the model next to the recent verbatim turns. It is a
--      projection of chat_messages (never an authority) and holds no more than 2000 characters.
--      Written only through record_conversation_summary, a compare-and-set on the watermark (the
--      newest message the summary covers): a redelivered or concurrent writer that read the same
--      watermark loses (reason 'stale'), so the summary only ever moves forward and is never
--      applied twice. The patient and the conversation are checked against the watermark message.
--   2. chat_reply_evidence: append-only record of the structured evidence ONE assistant reply
--      used (tools called, reference and document sources with pages, care plan ids). One row per
--      reply (UNIQUE message_id), written only through record_reply_evidence, never updated.
--      The patient reads their own rows; an ACTIVELY assigned clinician reads their patient's
--      rows (the same rule as chat_messages); nobody else, and no browser role writes.
--      Retention: rows older than 180 days are deleted by the write function, 100 per call.
--
-- Concurrency (OPS-006): the summary writer locks its row (INSERT ... ON CONFLICT, then FOR
-- UPDATE), evidence inserts are idempotent (ON CONFLICT DO NOTHING), counts and sizes are bounded
-- by CHECKs, time comes from the database clock, and nothing here holds a lock across a model call.
-- Rollback: drop the two functions and tables (nothing else depends on them).

-- ── 1. Rolling summaries ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.chat_conversation_summaries (
  patient_id uuid NOT NULL REFERENCES public.patients(id) ON DELETE CASCADE,
  session_id text NOT NULL CHECK (session_id ~ '^[A-Za-z0-9_-]{1,64}$'),
  summary text NOT NULL CHECK (char_length(summary) BETWEEN 1 AND 2000),
  language text NOT NULL CHECK (language IN ('en-US', 'es-MX')),
  covered_through_id uuid NOT NULL,
  covered_through_at timestamptz NOT NULL,
  updates integer NOT NULL DEFAULT 1 CHECK (updates >= 1),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (patient_id, session_id)
);
ALTER TABLE public.chat_conversation_summaries ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.chat_conversation_summaries FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.chat_conversation_summaries TO service_role;

-- The expected watermark is what the caller read before it summarised (NULL for the first
-- summary). p_through_id must be a message of this patient and conversation.
CREATE OR REPLACE FUNCTION public.record_conversation_summary(
  p_patient_id uuid, p_session_id text, p_expected_through timestamptz,
  p_through_id uuid, p_summary text, p_language text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
SET lock_timeout = '2s' SET statement_timeout = '5s' AS $$
DECLARE
  v_through timestamptz;
  v_current timestamptz;
BEGIN
  IF p_patient_id IS NULL OR p_session_id IS NULL OR p_through_id IS NULL
     OR p_summary IS NULL OR char_length(p_summary) NOT BETWEEN 1 AND 2000
     OR p_language IS NULL OR p_language NOT IN ('en-US', 'es-MX')
     OR p_session_id !~ '^[A-Za-z0-9_-]{1,64}$' THEN
    RETURN jsonb_build_object('accepted', false, 'reason', 'invalid');
  END IF;
  SELECT created_at INTO v_through FROM public.chat_messages
   WHERE id = p_through_id AND patient_id = p_patient_id AND session_id = p_session_id;
  IF v_through IS NULL THEN
    RETURN jsonb_build_object('accepted', false, 'reason', 'unknown_message');
  END IF;
  -- Make sure a row exists to lock; the placeholder is replaced (or removed) below.
  INSERT INTO public.chat_conversation_summaries
    (patient_id, session_id, summary, language, covered_through_id, covered_through_at, updates)
  VALUES (p_patient_id, p_session_id, p_summary, p_language, p_through_id, v_through, 1)
  ON CONFLICT (patient_id, session_id) DO NOTHING;
  IF FOUND THEN
    IF p_expected_through IS NOT NULL THEN
      -- The caller expected an earlier summary that no longer exists: do not invent history.
      DELETE FROM public.chat_conversation_summaries
       WHERE patient_id = p_patient_id AND session_id = p_session_id;
      RETURN jsonb_build_object('accepted', false, 'reason', 'stale');
    END IF;
    RETURN jsonb_build_object('accepted', true, 'covered_through_at', v_through);
  END IF;
  SELECT covered_through_at INTO v_current FROM public.chat_conversation_summaries
   WHERE patient_id = p_patient_id AND session_id = p_session_id FOR UPDATE;
  IF v_current IS DISTINCT FROM p_expected_through OR v_through <= v_current THEN
    RETURN jsonb_build_object('accepted', false, 'reason', 'stale');
  END IF;
  UPDATE public.chat_conversation_summaries
     SET summary = p_summary, language = p_language, covered_through_id = p_through_id,
         covered_through_at = v_through, updates = updates + 1, updated_at = clock_timestamp()
   WHERE patient_id = p_patient_id AND session_id = p_session_id;
  RETURN jsonb_build_object('accepted', true, 'covered_through_at', v_through);
END;
$$;
REVOKE ALL ON FUNCTION public.record_conversation_summary(uuid, text, timestamptz, uuid, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_conversation_summary(uuid, text, timestamptz, uuid, text, text)
  TO service_role;

-- ── 2. Per-reply evidence (append-only) ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.chat_reply_evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL REFERENCES public.patients(id) ON DELETE CASCADE,
  session_id text NOT NULL CHECK (session_id ~ '^[A-Za-z0-9_-]{1,64}$'),
  message_id uuid NOT NULL UNIQUE REFERENCES public.chat_messages(id) ON DELETE CASCADE,
  evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'
    AND octet_length(evidence::text) <= 12000),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS chat_reply_evidence_patient_session
  ON public.chat_reply_evidence (patient_id, session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS chat_reply_evidence_created ON public.chat_reply_evidence (created_at);
ALTER TABLE public.chat_reply_evidence ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.chat_reply_evidence FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.chat_reply_evidence TO authenticated, service_role;

DROP POLICY IF EXISTS chat_reply_evidence_patient_select ON public.chat_reply_evidence;
CREATE POLICY chat_reply_evidence_patient_select ON public.chat_reply_evidence
  FOR SELECT TO authenticated USING (patient_id = auth.uid());
DROP POLICY IF EXISTS chat_reply_evidence_clinician_select ON public.chat_reply_evidence;
CREATE POLICY chat_reply_evidence_clinician_select ON public.chat_reply_evidence
  FOR SELECT TO authenticated
  USING (private.is_clinician() AND private.is_assigned_clinician(patient_id));

-- Append-only: a stored row is never changed, by anyone, except by the cascade and retention.
CREATE OR REPLACE FUNCTION private.chat_reply_evidence_append_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
  RAISE EXCEPTION 'chat_reply_evidence rows are append-only' USING ERRCODE = '42501';
END;
$$;
DROP TRIGGER IF EXISTS chat_reply_evidence_no_update ON public.chat_reply_evidence;
CREATE TRIGGER chat_reply_evidence_no_update BEFORE UPDATE ON public.chat_reply_evidence
  FOR EACH ROW EXECUTE FUNCTION private.chat_reply_evidence_append_only();

-- The reply must be an assistant message of this patient and conversation. A repeat (a retried
-- turn) is a no-op. Retention runs here, a bounded batch per call.
CREATE OR REPLACE FUNCTION public.record_reply_evidence(
  p_patient_id uuid, p_session_id text, p_message_id uuid, p_evidence jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
SET lock_timeout = '2s' SET statement_timeout = '5s' AS $$
DECLARE
  v_inserted boolean;
BEGIN
  IF p_patient_id IS NULL OR p_session_id IS NULL OR p_message_id IS NULL
     OR p_evidence IS NULL OR jsonb_typeof(p_evidence) <> 'object'
     OR octet_length(p_evidence::text) > 12000
     OR p_session_id !~ '^[A-Za-z0-9_-]{1,64}$' THEN
    RETURN jsonb_build_object('accepted', false, 'reason', 'invalid');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.chat_messages
                  WHERE id = p_message_id AND patient_id = p_patient_id
                    AND session_id = p_session_id AND role = 'assistant') THEN
    RETURN jsonb_build_object('accepted', false, 'reason', 'unknown_message');
  END IF;
  INSERT INTO public.chat_reply_evidence (patient_id, session_id, message_id, evidence)
  VALUES (p_patient_id, p_session_id, p_message_id, p_evidence)
  ON CONFLICT (message_id) DO NOTHING;
  v_inserted := FOUND;
  DELETE FROM public.chat_reply_evidence WHERE id IN (
    SELECT id FROM public.chat_reply_evidence
     WHERE created_at < clock_timestamp() - interval '180 days' LIMIT 100);
  RETURN jsonb_build_object('accepted', true, 'inserted', v_inserted);
END;
$$;
REVOKE ALL ON FUNCTION public.record_reply_evidence(uuid, text, uuid, jsonb)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_reply_evidence(uuid, text, uuid, jsonb) TO service_role;

-- ── 3. Verification ───────────────────────────────────────────────────────────────────────

DO $verify$
DECLARE
  v_table text;
BEGIN
  FOREACH v_table IN ARRAY ARRAY['chat_conversation_summaries', 'chat_reply_evidence'] LOOP
    IF NOT (SELECT relrowsecurity FROM pg_catalog.pg_class
             WHERE oid = ('public.' || v_table)::regclass) THEN
      RAISE EXCEPTION '094: % must have row level security', v_table;
    END IF;
    IF has_table_privilege('anon', 'public.' || v_table, 'SELECT,INSERT,UPDATE,DELETE')
       OR has_table_privilege('authenticated', 'public.' || v_table, 'INSERT,UPDATE,DELETE')
       OR has_table_privilege('service_role', 'public.' || v_table, 'INSERT,UPDATE,DELETE') THEN
      RAISE EXCEPTION '094: % grants are wider than intended', v_table;
    END IF;
  END LOOP;
  IF has_table_privilege('authenticated', 'public.chat_conversation_summaries', 'SELECT') THEN
    RAISE EXCEPTION '094: chat_conversation_summaries is backend-only';
  END IF;
  IF (SELECT count(*) FROM pg_policies
       WHERE schemaname = 'public' AND tablename = 'chat_reply_evidence') <> 2 THEN
    RAISE EXCEPTION '094: chat_reply_evidence must have exactly the patient and clinician read policies';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger
                  WHERE tgrelid = 'public.chat_reply_evidence'::regclass
                    AND tgname = 'chat_reply_evidence_no_update' AND NOT tgisinternal) THEN
    RAISE EXCEPTION '094: chat_reply_evidence lost its append-only trigger';
  END IF;
  FOREACH v_table IN ARRAY ARRAY[
    'public.record_conversation_summary(uuid,text,timestamptz,uuid,text,text)',
    'public.record_reply_evidence(uuid,text,uuid,jsonb)'] LOOP
    IF has_function_privilege('anon', v_table::regprocedure, 'EXECUTE')
       OR has_function_privilege('authenticated', v_table::regprocedure, 'EXECUTE')
       OR NOT has_function_privilege('service_role', v_table::regprocedure, 'EXECUTE') THEN
      RAISE EXCEPTION '094: wrong execute grants on %', v_table;
    END IF;
  END LOOP;
END
$verify$;
