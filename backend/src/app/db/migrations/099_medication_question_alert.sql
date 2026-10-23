-- MED-002 follow-up: the patient is told, once, that a clinician asked about one of their
-- medicines. The question itself stays on Today (093); this adds one notification-centre item
-- that links there.
--
--   * Event type medication_confirmation_asked (category follow_up, source
--     medication_confirmation_requests, audience patient). An AFTER INSERT trigger on the
--     request table captures it in the request's own transaction: a rolled-back ask leaves
--     nothing, a committed one always has it. The 093 function is untouched. The event key is
--     medication_confirmation:<request id>, the request's primary key, so a replayed ask
--     (which returns the stored request before any insert) and a repeated capture converge on
--     one event, one pending delivery and one receipt. A fresh ask after expiry is a new
--     request and tells the patient again. Requests asked before this migration are not
--     replayed: nobody is told late.
--   * The event stores the clinician's name and specialty and the care-team id. It stores no
--     medication, dose, answer or note: the card on Today already shows what it shows.
--   * Actionable exactly while the request is open and unexpired (database clock). Answering
--     or expiry ends it with no worker; the item then stays as History. Patient only; no email
--     category (private.email_preference is NULL for it).
--   * Visible only to the asked patient while the asking care-team link is still active, the
--     same condition under which 093 shows the question.
--
-- The 096 ledger wrappers (notification_source, notification_authorized,
-- notification_actionable) are extended, not replaced: each current wrapper is kept under a
-- *_handoff name, once, and the new wrapper handles this event type before delegating to it,
-- so handoff-share items (096) and everything below them (symptom review 095, etc.) behave
-- exactly as before.
--
-- Lock order (OPS-006 rule 7): the trigger runs inside the insert that already holds the
-- patient advisory lock and the new request row; it takes no lock beyond
-- notification_capture's own unique-key insert and reads care teams and clinicians unlocked.

-- ── 1. Ledger accepts the new event and source type ──────────────────────────────────────

DO $$
DECLARE v_def text; v_name text; v_token text;
BEGIN
  FOREACH v_name IN ARRAY ARRAY['notification_events_event_type_check',
    'notification_events_source_type_check'] LOOP
    v_token := CASE WHEN v_name LIKE '%event_type%' THEN 'medication_confirmation_asked'
                    ELSE 'medication_confirmation_requests' END;
    SELECT pg_get_constraintdef(oid) INTO v_def FROM pg_constraint
     WHERE conrelid = 'public.notification_events'::regclass AND conname = v_name;
    IF v_def IS NULL THEN
      RAISE EXCEPTION '099: % is missing', v_name;
    END IF;
    IF v_def NOT LIKE '%' || v_token || '%' THEN
      v_def := replace(v_def, '::text])', '::text, ''' || v_token || '''::text])');
      EXECUTE format('ALTER TABLE public.notification_events DROP CONSTRAINT %I', v_name);
      EXECUTE format('ALTER TABLE public.notification_events ADD CONSTRAINT %I %s', v_name, v_def);
    END IF;
  END LOOP;
END;
$$;

-- ── 2. Capture at request time ───────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION private.capture_medication_confirmation_asked() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_name text; v_specialty text;
BEGIN
  SELECT btrim(c.first_name || ' ' || c.last_name),
         coalesce(nullif(btrim(t.specialty_context), ''), nullif(btrim(c.specialty), ''))
    INTO v_name, v_specialty
    FROM public.care_teams t JOIN public.clinicians c ON c.id = t.clinician_id
   WHERE t.id = NEW.care_team_id AND t.patient_id = NEW.patient_id;
  PERFORM private.notification_capture('medication_confirmation_requests', NEW.id, NEW.patient_id,
    'medication_confirmation_asked', 'follow_up', 'patient', NULL,
    jsonb_build_object('care_team_id', NEW.care_team_id, 'clinician_name', left(v_name, 160),
      'specialty', left(v_specialty, 100)),
    'medication_confirmation:' || NEW.id::text, NEW.created_at);
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS medication_confirmation_asked_notification
  ON public.medication_confirmation_requests;
CREATE TRIGGER medication_confirmation_asked_notification
  AFTER INSERT ON public.medication_confirmation_requests
  FOR EACH ROW EXECUTE FUNCTION private.capture_medication_confirmation_asked();

-- ── 3. Ledger wrappers, layered over the 096 wrappers ────────────────────────────────────

DO $$
BEGIN
  IF to_regprocedure('private.notification_source_handoff(text,uuid)') IS NULL THEN
    ALTER FUNCTION private.notification_source(text, uuid) RENAME TO notification_source_handoff;
  END IF;
  IF to_regprocedure('private.notification_authorized_handoff(public.notification_events,uuid,text)') IS NULL THEN
    ALTER FUNCTION private.notification_authorized(public.notification_events, uuid, text)
      RENAME TO notification_authorized_handoff;
  END IF;
  IF to_regprocedure('private.notification_actionable_handoff(public.notification_events,text)') IS NULL THEN
    ALTER FUNCTION private.notification_actionable(public.notification_events, text)
      RENAME TO notification_actionable_handoff;
  END IF;
END;
$$;

-- The request as the ledger sees it: ids and times only, no medication text, no "status" key.
CREATE OR REPLACE FUNCTION private.notification_source(p_type text, p_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  IF p_type = 'medication_confirmation_requests' THEN
    RETURN (SELECT jsonb_build_object('id', r.id, 'patient_id', r.patient_id,
        'care_team_id', r.care_team_id, 'request_state', r.status,
        'expires_at', r.expires_at, 'created_at', r.created_at)
      FROM public.medication_confirmation_requests r WHERE r.id = p_id);
  END IF;
  RETURN private.notification_source_handoff(p_type, p_id);
END;
$$;

-- For the asked patient only, while the asking link is still active.
CREATE OR REPLACE FUNCTION private.notification_authorized(
  e public.notification_events, p_actor uuid, p_role text
) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  IF e.source_type = 'medication_confirmation_requests' OR e.event_type = 'medication_confirmation_asked' THEN
    RETURN p_role = 'patient' AND e.source_type = 'medication_confirmation_requests'
      AND e.event_type = 'medication_confirmation_asked' AND e.audience = 'patient'
      AND p_actor = e.patient_id
      AND EXISTS (SELECT 1 FROM public.medication_confirmation_requests r
        WHERE r.id = e.source_id AND r.patient_id = p_actor AND r.patient_id = e.patient_id
          AND EXISTS (SELECT 1 FROM public.care_teams t
            WHERE t.id = r.care_team_id AND t.patient_id = r.patient_id AND t.status = 'active'));
  END IF;
  RETURN private.notification_authorized_handoff(e, p_actor, p_role);
END;
$$;

-- Open exactly while the question is unanswered and unexpired (database clock).
CREATE OR REPLACE FUNCTION private.notification_actionable(
  e public.notification_events, p_role text
) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  IF e.event_type = 'medication_confirmation_asked' THEN
    RETURN p_role = 'patient' AND EXISTS (SELECT 1 FROM public.medication_confirmation_requests r
      WHERE r.id = e.source_id AND r.patient_id = e.patient_id AND r.status = 'open'
        AND r.expires_at > clock_timestamp());
  END IF;
  RETURN private.notification_actionable_handoff(e, p_role);
END;
$$;

-- ── 4. Grants ─────────────────────────────────────────────────────────────────────────────

REVOKE ALL ON FUNCTION
  private.capture_medication_confirmation_asked(),
  private.notification_source_handoff(text, uuid),
  private.notification_authorized_handoff(public.notification_events, uuid, text),
  private.notification_actionable_handoff(public.notification_events, text),
  private.notification_source(text, uuid),
  private.notification_authorized(public.notification_events, uuid, text),
  private.notification_actionable(public.notification_events, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION
  private.capture_medication_confirmation_asked(),
  private.notification_source_handoff(text, uuid),
  private.notification_authorized_handoff(public.notification_events, uuid, text),
  private.notification_actionable_handoff(public.notification_events, text),
  private.notification_source(text, uuid),
  private.notification_authorized(public.notification_events, uuid, text),
  private.notification_actionable(public.notification_events, text)
  TO service_role;

-- ── 5. Verification ───────────────────────────────────────────────────────────────────────

DO $verify$
DECLARE v_function text;
BEGIN
  FOREACH v_function IN ARRAY ARRAY[
    'private.capture_medication_confirmation_asked()',
    'private.notification_source_handoff(text,uuid)',
    'private.notification_authorized_handoff(public.notification_events,uuid,text)',
    'private.notification_actionable_handoff(public.notification_events,text)',
    'private.notification_source(text,uuid)',
    'private.notification_authorized(public.notification_events,uuid,text)',
    'private.notification_actionable(public.notification_events,text)'] LOOP
    IF has_function_privilege('anon', v_function, 'EXECUTE')
       OR has_function_privilege('authenticated', v_function, 'EXECUTE')
       OR NOT has_function_privilege('service_role', v_function, 'EXECUTE') THEN
      RAISE EXCEPTION '099: wrong execute grants on %', v_function;
    END IF;
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname = 'private'
        AND p.proname IN ('capture_medication_confirmation_asked', 'notification_source',
          'notification_authorized', 'notification_actionable', 'notification_source_handoff',
          'notification_authorized_handoff', 'notification_actionable_handoff')
        AND NOT EXISTS (SELECT 1 FROM unnest(p.proconfig) c WHERE c LIKE 'search_path=%')) THEN
    RAISE EXCEPTION '099: a notification function has no fixed search_path';
  END IF;
  IF NOT (SELECT relrowsecurity FROM pg_class
           WHERE oid = 'public.medication_confirmation_requests'::regclass) THEN
    RAISE EXCEPTION '099: row-level security must stay enabled on the request table';
  END IF;
  IF has_table_privilege('anon', 'public.medication_confirmation_requests', 'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('authenticated', 'public.medication_confirmation_requests', 'SELECT,INSERT,UPDATE,DELETE') THEN
    RAISE EXCEPTION '099: browser roles must have no access to the request table';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'medication_confirmation_asked_notification'
      AND tgrelid = 'public.medication_confirmation_requests'::regclass AND NOT tgisinternal) THEN
    RAISE EXCEPTION '099: the question notification trigger is missing';
  END IF;
  IF (SELECT pg_get_constraintdef(oid) FROM pg_constraint
       WHERE conrelid = 'public.notification_events'::regclass
         AND conname = 'notification_events_event_type_check') NOT LIKE '%medication_confirmation_asked%'
     OR (SELECT pg_get_constraintdef(oid) FROM pg_constraint
       WHERE conrelid = 'public.notification_events'::regclass
         AND conname = 'notification_events_source_type_check') NOT LIKE '%medication_confirmation_requests%' THEN
    RAISE EXCEPTION '099: the notification ledger does not accept a medication question';
  END IF;
  IF (SELECT pg_get_constraintdef(oid) FROM pg_constraint
       WHERE conrelid = 'public.notification_events'::regclass
         AND conname = 'notification_events_event_type_check') NOT LIKE '%handoff_shared%'
     OR (SELECT pg_get_constraintdef(oid) FROM pg_constraint
       WHERE conrelid = 'public.notification_events'::regclass
         AND conname = 'notification_events_event_type_check') NOT LIKE '%symptom_report_reviewed%' THEN
    RAISE EXCEPTION '099: an earlier event type was lost from the allowlist';
  END IF;
  IF private.email_preference('medication_confirmation_asked') IS NOT NULL THEN
    RAISE EXCEPTION '099: a medication question notice must not map to an email category';
  END IF;
END
$verify$;
