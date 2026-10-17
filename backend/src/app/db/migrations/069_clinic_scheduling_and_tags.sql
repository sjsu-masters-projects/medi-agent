-- CLN-003 slices E and F: cross-clinic scheduling and clinic tags. Requires 067
-- (clinic_lists_and_roles) and the 041/043 appointment objects it builds on.
--
-- This migration:
--   * adds appointments.clinic_id and appointments.clinician_id, backfilled from each
--     appointment's care-team link, NOT NULL, and kept equal to the link by triggers (a new row
--     takes both from its link; a link that moves to another clinic or clinician carries its
--     appointments with it);
--   * fails closed before changing anything if an appointment cannot be matched to exactly one
--     link that has a clinic, or if existing confirmed/scheduled visits already overlap for one
--     clinician (the messages report counts only, never identifiers);
--   * adds the per-clinician no-overlap exclusion constraint across all of a clinician's
--     clinics, with the same [start, end) window as the patient constraint from 043;
--   * replaces public.propose_appointment_slots (same signature, same grants): it locks the
--     clinician, checks every proposed slot against the clinician's whole schedule and returns
--     the conflicting slots with the clinic of the appointment in the way, never a patient;
--   * adds authorization_denial_events.clinic_id (nullable) for denials that concern a link;
--   * makes the notification centre's clinic label follow an appointment's own clinic, so a
--     reminder for a patient with several clinics names the right one.
--
-- Written, not applied: applied to a hosted project only on explicit authorization, and before
-- the backend that calls the new conflict result deploys (apply first, merge after). The
-- existing patient constraint, response function and grants are untouched. Synthetic data.

-- 033 intended the denial trail to be insert/select for the backend only, but hosted
-- projects keep the platform's default table grants (browser roles and service_role UPDATE/
-- DELETE). Restore the intended privileges first, so the snapshot below records them.
REVOKE ALL ON TABLE public.authorization_denial_events FROM PUBLIC, anon, authenticated;
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.authorization_denial_events FROM service_role;
GRANT INSERT, SELECT ON TABLE public.authorization_denial_events TO service_role;

-- Privileges before the change, compared again at the end ("grants unchanged").
CREATE TEMP TABLE _069_grants AS
SELECT 'table' AS kind, c.relname::text AS name, coalesce(c.relacl::text, '') AS acl
  FROM pg_catalog.pg_class c
 WHERE c.oid IN ('public.appointments'::regclass, 'public.authorization_denial_events'::regclass)
UNION ALL
SELECT 'function', p.proname::text || '(' || pg_catalog.pg_get_function_identity_arguments(p.oid) || ')',
       coalesce(p.proacl::text, '')
  FROM pg_catalog.pg_proc p
 WHERE p.oid = 'public.propose_appointment_slots(uuid,uuid,timestamptz[],integer,text,text,text)'::regprocedure
    OR p.oid = 'public.respond_to_appointment_offer(uuid,uuid,text,text)'::regprocedure;

-- ── 1. Backfill, fail-closed checks ──────────────────────────────────────────────────────
ALTER TABLE public.appointments
  ADD COLUMN clinic_id uuid REFERENCES public.clinics(id),
  ADD COLUMN clinician_id uuid REFERENCES public.clinicians(id) ON DELETE CASCADE;

COMMENT ON COLUMN public.appointments.clinic_id IS
  'CLN-003: the clinic of the care-team link this appointment was made under. Always equal to care_teams.clinic_id (trigger).';
COMMENT ON COLUMN public.appointments.clinician_id IS
  'CLN-003: the clinician of the care-team link; the per-clinician no-overlap constraint uses it. Always equal to care_teams.clinician_id (trigger).';

DO $$
DECLARE
  v_unmatched integer;
BEGIN
  -- care_team_id is NOT NULL with a foreign key, so a link always exists by primary key; what
  -- can still be missing is the link's clinic or clinician (a clinician with no clinic).
  SELECT count(*) INTO v_unmatched
    FROM public.appointments a
    LEFT JOIN public.care_teams t ON t.id = a.care_team_id
   WHERE t.id IS NULL OR t.clinic_id IS NULL OR t.clinician_id IS NULL;
  IF v_unmatched > 0 THEN
    RAISE EXCEPTION
      '% appointment(s) cannot be matched to exactly one care-team link that has a clinic and a clinician; resolve them before applying 069 (counts only, nothing was changed)',
      v_unmatched;
  END IF;
END $$;

UPDATE public.appointments a
   SET clinic_id = t.clinic_id,
       clinician_id = t.clinician_id
  FROM public.care_teams t
 WHERE t.id = a.care_team_id;

DO $$
DECLARE
  v_pairs integer;
  v_clinicians integer;
BEGIN
  WITH booked AS (
    SELECT id, clinician_id,
           public.appointment_booking_window(scheduled_at, duration_minutes) AS during
      FROM public.appointments
     WHERE status IN ('confirmed', 'scheduled')
  ), pairs AS (
    SELECT a.clinician_id
      FROM booked a JOIN booked b
        ON a.clinician_id = b.clinician_id AND a.id < b.id AND a.during && b.during
  )
  SELECT count(*), count(DISTINCT clinician_id) INTO v_pairs, v_clinicians FROM pairs;
  IF v_pairs > 0 THEN
    RAISE EXCEPTION
      '% overlapping confirmed/scheduled appointment pair(s) for % clinician(s) block the per-clinician constraint; review them with backend/scripts/appointment-clinician-overlap-preflight.sql (nothing was changed, nothing is cancelled automatically)',
      v_pairs, v_clinicians;
  END IF;
END $$;

ALTER TABLE public.appointments
  ALTER COLUMN clinic_id SET NOT NULL,
  ALTER COLUMN clinician_id SET NOT NULL;

CREATE INDEX idx_appointments_clinic ON public.appointments (clinic_id, scheduled_at);
CREATE INDEX idx_appointments_clinician ON public.appointments (clinician_id, scheduled_at);

-- ── 2. The appointment always carries its link's clinic and clinician ────────────────────
CREATE FUNCTION private.appointment_link_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_clinic uuid;
  v_clinician uuid;
BEGIN
  SELECT t.clinic_id, t.clinician_id INTO v_clinic, v_clinician
    FROM public.care_teams t
   WHERE t.id = NEW.care_team_id;
  IF NOT FOUND OR v_clinic IS NULL OR v_clinician IS NULL THEN
    RAISE EXCEPTION 'An appointment needs a care-team link that has a clinic'
      USING ERRCODE = '23514';
  END IF;
  -- Whatever the writer sent, the link decides.
  NEW.clinic_id := v_clinic;
  NEW.clinician_id := v_clinician;
  RETURN NEW;
END;
$$;

CREATE TRIGGER appointments_link_guard
  BEFORE INSERT OR UPDATE OF care_team_id, clinic_id, clinician_id ON public.appointments
  FOR EACH ROW EXECUTE FUNCTION private.appointment_link_guard();

-- A link handed to another clinician (or moved to another clinic) carries its appointments.
-- If that makes the new clinician's visits overlap, the statement fails and nothing changes.
CREATE FUNCTION private.care_team_appointment_follow()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  UPDATE public.appointments a
     SET clinic_id = NEW.clinic_id,
         clinician_id = NEW.clinician_id
   WHERE a.care_team_id = NEW.id
     AND (a.clinic_id, a.clinician_id) IS DISTINCT FROM (NEW.clinic_id, NEW.clinician_id);
  RETURN NULL;
END;
$$;

CREATE TRIGGER care_teams_appointment_follow
  AFTER UPDATE OF clinic_id, clinician_id ON public.care_teams
  FOR EACH ROW EXECUTE FUNCTION private.care_team_appointment_follow();

REVOKE ALL ON FUNCTION private.appointment_link_guard() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.care_team_appointment_follow() FROM PUBLIC, anon, authenticated;

-- ── 3. One schedule per clinician across every clinic ────────────────────────────────────
-- [start, end) permits back-to-back visits; proposed options do not reserve time. This
-- arbitrates concurrent transactions and direct writes, like the patient constraint in 043.
ALTER TABLE public.appointments ADD CONSTRAINT appointments_clinician_no_overlap
  EXCLUDE USING gist (clinician_id WITH =,
    public.appointment_booking_window(scheduled_at, duration_minutes) WITH &&)
  WHERE (status IN ('confirmed', 'scheduled'));

-- ── 4. Offers check the clinician's whole schedule ───────────────────────────────────────
CREATE OR REPLACE FUNCTION public.propose_appointment_slots(
  p_actor_id uuid, p_care_team_id uuid, p_slots timestamptz[],
  p_duration_minutes integer, p_appointment_type text, p_location text, p_reason text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE
  v_team public.care_teams%ROWTYPE;
  v_group uuid := gen_random_uuid();
  v_name text;
  v_rows jsonb;
  v_conflicts jsonb;
BEGIN
  SELECT * INTO v_team FROM public.care_teams WHERE id = p_care_team_id FOR SHARE;
  IF NOT FOUND OR v_team.status <> 'active' OR v_team.clinician_id <> p_actor_id THEN
    RETURN jsonb_build_object('error', 'forbidden');
  END IF;
  IF cardinality(p_slots) IS NULL OR cardinality(p_slots) NOT BETWEEN 2 AND 4
     OR (SELECT count(DISTINCT value) FROM unnest(p_slots) AS value) <> cardinality(p_slots)
     OR EXISTS (SELECT 1 FROM unnest(p_slots) AS value WHERE value <= now() OR value IS NULL)
     OR p_duration_minutes IS NULL OR p_duration_minutes NOT BETWEEN 5 AND 480
     OR p_appointment_type IS NULL
     OR p_appointment_type NOT IN ('follow_up', 'initial', 'routine', 'urgent', 'pre_op') THEN
    RETURN jsonb_build_object('error', 'invalid');
  END IF;
  IF v_team.clinic_id IS NULL THEN
    RETURN jsonb_build_object('error', 'invalid');
  END IF;
  -- Serialize this clinician's offers and bookings checks; the exclusion constraint stays the
  -- authority for writers that do not take this lock.
  PERFORM pg_advisory_xact_lock(hashtextextended('appointment-clinician:' || p_actor_id::text, 0));
  -- One entry per proposed slot that runs into a booked visit of this clinician at ANY clinic.
  -- The clinic name is the other visit's clinic; no patient is read or returned.
  SELECT jsonb_agg(jsonb_build_object(
      'slot', s.slot, 'clinic_id', hit.clinic_id, 'clinic_name', hit.display_name,
      'starts_at', hit.scheduled_at,
      'ends_at', hit.scheduled_at + hit.duration_minutes * interval '1 minute')
      ORDER BY s.slot)
    INTO v_conflicts
    FROM unnest(p_slots) AS s(slot)
    CROSS JOIN LATERAL (
      SELECT a.clinic_id, c.display_name, a.scheduled_at, a.duration_minutes
        FROM public.appointments a JOIN public.clinics c ON c.id = a.clinic_id
       WHERE a.clinician_id = p_actor_id AND a.status IN ('confirmed', 'scheduled')
         AND public.appointment_booking_window(a.scheduled_at, a.duration_minutes)
             && public.appointment_booking_window(s.slot, p_duration_minutes)
       ORDER BY a.scheduled_at, a.id LIMIT 1) hit;
  IF v_conflicts IS NOT NULL THEN
    RETURN jsonb_build_object('error', 'clinician_conflict', 'conflicts', v_conflicts);
  END IF;
  SELECT concat_ws(' ', first_name, last_name) INTO v_name
    FROM public.clinicians WHERE id = p_actor_id;
  WITH inserted AS (
    INSERT INTO public.appointments(patient_id, care_team_id, clinic_id, clinician_id, clinician_name,
      scheduled_at, duration_minutes, appointment_type, location, reason, status, proposal_group_id)
    SELECT v_team.patient_id, v_team.id, v_team.clinic_id, v_team.clinician_id, v_name, value,
      p_duration_minutes, p_appointment_type::appointment_type_enum, p_location, p_reason,
      'proposed', v_group
    FROM unnest(p_slots) AS value ORDER BY value
    RETURNING *
  ) SELECT jsonb_agg(to_jsonb(inserted) ORDER BY scheduled_at) INTO v_rows FROM inserted;
  INSERT INTO public.appointment_offer_events(appointment_id, patient_id, proposal_group_id,
    actor_id, action, new_status)
  SELECT id, patient_id, proposal_group_id, p_actor_id, 'propose', status
    FROM public.appointments WHERE proposal_group_id = v_group;
  RETURN jsonb_build_object('appointments', v_rows);
END;
$$;

-- ── 5. Denials that concern a link name its clinic ───────────────────────────────────────
-- Nullable: most denials name no link. The table stays append-only and backend-only.
ALTER TABLE public.authorization_denial_events ADD COLUMN clinic_id uuid;
COMMENT ON COLUMN public.authorization_denial_events.clinic_id IS
  'CLN-003: the clinic of the care-team link or clinic the refused action concerned, when there is one.';

-- ── 6. A reminder or appointment item names the appointment's own clinic ──────────────────
-- Same signature as 067. The clinic of an item that comes from an appointment (or from a
-- reminder for one) is the appointment's clinic; every other item keeps the link's clinic. A
-- patient with links at two clinics therefore never sees a reminder labelled with the other.
CREATE OR REPLACE FUNCTION private.notification_row(p_receipt public.notification_receipts,p_actor uuid,p_role text)
RETURNS TABLE(id uuid,event_id uuid,created_at timestamptz,is_read boolean,actionable boolean,
  can_acknowledge boolean,group_key text,item jsonb)
LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 WITH authorized AS (
   SELECT p_receipt.id,p_receipt.event_id,p_receipt.created_at,p_receipt.read_at,p_receipt.acknowledged_at,
     e.event_type,e.category,e.source_type,e.source_id,e.patient_id,e.metadata,
     private.notification_source(e.source_type,e.source_id) s,
     private.notification_actionable(e,p_role) active,
     -- Only the newest receipt this person can see for a source and kind asks for action.
     NOT EXISTS(SELECT 1 FROM public.notification_events n JOIN public.notification_receipts o ON o.event_id=n.id
       WHERE n.source_type=e.source_type AND n.source_id=e.source_id AND n.event_type=e.event_type
         AND (n.created_at,n.id)>(e.created_at,e.id) AND o.recipient_id=p_actor AND o.recipient_role=p_role
         AND private.notification_authorized(n,p_actor,p_role)) latest
   FROM public.notification_events e
   WHERE e.id=p_receipt.event_id AND p_receipt.recipient_id=p_actor AND p_receipt.recipient_role=p_role
     AND private.notification_authorized(e,p_actor,p_role)
 ), states AS (
   SELECT a.*,(a.read_at IS NOT NULL OR (a.source_type='notifications' AND coalesce((s->>'is_read')::boolean,false))
     OR (a.event_type='message_received' AND EXISTS(SELECT 1 FROM public.care_conversation_reads cr
       WHERE cr.conversation_id=private.notification_uuid(a.metadata->>'conversation_id') AND cr.actor_id=p_actor
         AND (private.notification_ts(a.s->>'created_at'),a.source_id)<=(cr.last_message_at,cr.last_message_id)))) seen,
     (a.active AND a.latest AND a.acknowledged_at IS NULL) needs,
     -- The appointment's clinic: from the appointment itself, or from the one a reminder names.
     CASE WHEN a.source_type='appointments' THEN private.notification_uuid(a.s->>'clinic_id')
       WHEN a.event_type='appointment_reminder' THEN (SELECT ap.clinic_id FROM public.appointments ap
         WHERE ap.id=private.notification_uuid(a.metadata->>'appointment_id') AND ap.patient_id=a.patient_id)
     END ref_clinic
   FROM authorized a
 )
 SELECT a.id,a.event_id,a.created_at,a.seen,a.needs,
   (p_role='clinician' AND a.event_type IN ('barrier_reported','safety_flag','appointment_response','critical_result') AND a.needs),
   CASE WHEN a.event_type='message_received' THEN 'message:'||(a.metadata->>'conversation_id')
     WHEN a.category='reminders' THEN 'reminder:'||coalesce(a.metadata->>'target_id',a.source_id::text)||':'||
       coalesce((private.notification_ts(a.metadata->>'scheduled_at')
         AT TIME ZONE private.notification_zone(p.timezone))::date::text,a.created_at::date::text)
     ELSE 'receipt:'||a.id END,
   jsonb_build_object('id',a.id,'event_type',a.event_type,'category',a.category,'source_type',a.source_type,
     'source_id',a.source_id,'patient_id',a.patient_id,'metadata',a.metadata,'created_at',a.created_at,
     'is_read',a.seen,'actionable',a.needs,'can_acknowledge',
       p_role='clinician' AND a.event_type IN ('barrier_reported','safety_flag','appointment_response','critical_result') AND a.needs,
     'patient_name',concat_ws(' ',p.first_name,p.last_name),
     'clinic_id',coalesce(a.ref_clinic,ct.clinic_id),
     'clinic_name',CASE WHEN a.ref_clinic IS NOT NULL THEN rc.display_name ELSE coalesce(cl.display_name,ct.clinic_name) END,
     'actor_name',coalesce(a.metadata->>'actor_name',concat_ws(' ',c.first_name,c.last_name)))
 FROM states a JOIN public.patients p ON p.id=a.patient_id
 LEFT JOIN LATERAL (SELECT t.* FROM public.care_teams t WHERE t.patient_id=a.patient_id AND t.status='active'
   AND (CASE WHEN p_role='clinician' THEN t.clinician_id=p_actor
     WHEN a.metadata->>'clinician_id' IS NOT NULL THEN t.clinician_id=(a.metadata->>'clinician_id')::uuid ELSE true END)
   ORDER BY t.id LIMIT 1) ct ON true
 LEFT JOIN public.clinicians c ON c.id=ct.clinician_id LEFT JOIN public.clinics cl ON cl.id=ct.clinic_id
 LEFT JOIN public.clinics rc ON rc.id=a.ref_clinic;
$$;

-- ── 7. Fail-closed verification ──────────────────────────────────────────────────────────
DO $$
DECLARE
  v_changed text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint
                  WHERE conrelid = 'public.appointments'::regclass
                    AND conname = 'appointments_clinician_no_overlap' AND contype = 'x')
     OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint
                     WHERE conrelid = 'public.appointments'::regclass
                       AND conname = 'appointments_patient_no_overlap' AND contype = 'x') THEN
    RAISE EXCEPTION 'The patient and clinician no-overlap constraints must both exist';
  END IF;
  IF EXISTS (SELECT 1 FROM public.appointments WHERE clinic_id IS NULL OR clinician_id IS NULL) THEN
    RAISE EXCEPTION 'No appointment may be left without a clinic or clinician';
  END IF;
  IF EXISTS (SELECT 1 FROM public.appointments a JOIN public.care_teams t ON t.id = a.care_team_id
              WHERE (a.clinic_id, a.clinician_id) IS DISTINCT FROM (t.clinic_id, t.clinician_id)) THEN
    RAISE EXCEPTION 'Every appointment must carry its care-team link''s clinic and clinician';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_attribute
              WHERE attrelid = 'public.appointments'::regclass
                AND attname IN ('clinic_id', 'clinician_id') AND NOT attnotnull) THEN
    RAISE EXCEPTION 'appointments.clinic_id and clinician_id must be NOT NULL';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(ARRAY['anon', 'authenticated']) r(role)
     CROSS JOIN unnest(ARRAY[
       'public.propose_appointment_slots(uuid,uuid,timestamptz[],integer,text,text,text)',
       'public.respond_to_appointment_offer(uuid,uuid,text,text)']) f(name)
     WHERE pg_catalog.has_function_privilege(r.role, f.name, 'EXECUTE')
  ) OR EXISTS (
    SELECT 1 FROM unnest(ARRAY['anon', 'authenticated']) r(role)
     CROSS JOIN unnest(ARRAY['private.appointment_link_guard()',
       'private.care_team_appointment_follow()']) f(name)
     WHERE pg_catalog.has_function_privilege(r.role, f.name, 'EXECUTE')
  ) THEN
    RAISE EXCEPTION 'Appointment operations and guards are for the service role only';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(ARRAY['anon', 'authenticated']) r(role)
     CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE']) p(privilege)
     WHERE pg_catalog.has_table_privilege(r.role, 'public.authorization_denial_events', p.privilege)
  ) OR EXISTS (
    SELECT 1 FROM unnest(ARRAY['UPDATE', 'DELETE', 'TRUNCATE']) p(privilege)
     WHERE pg_catalog.has_table_privilege('service_role', 'public.authorization_denial_events', p.privilege)
  ) THEN
    RAISE EXCEPTION 'The authorization denial trail must stay append-only and backend-only';
  END IF;
  SELECT string_agg(g.kind || ' ' || g.name, ', ') INTO v_changed
    FROM _069_grants g
    LEFT JOIN (
      SELECT 'table' AS kind, c.relname::text AS name, coalesce(c.relacl::text, '') AS acl
        FROM pg_catalog.pg_class c
       WHERE c.oid IN ('public.appointments'::regclass, 'public.authorization_denial_events'::regclass)
      UNION ALL
      SELECT 'function', p.proname::text || '(' || pg_catalog.pg_get_function_identity_arguments(p.oid) || ')',
             coalesce(p.proacl::text, '')
        FROM pg_catalog.pg_proc p
       WHERE p.oid = 'public.propose_appointment_slots(uuid,uuid,timestamptz[],integer,text,text,text)'::regprocedure
          OR p.oid = 'public.respond_to_appointment_offer(uuid,uuid,text,text)'::regprocedure
    ) cur ON cur.kind = g.kind AND cur.name = g.name
   WHERE cur.acl IS DISTINCT FROM g.acl;
  IF v_changed IS NOT NULL THEN
    RAISE EXCEPTION 'Privileges changed on: %', v_changed;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_proc
              WHERE proname IN ('notification_row', 'notification_centre_operation')
                AND prosrc ~ 'cl\.id\s*=\s*c\.clinic_id') THEN
    RAISE EXCEPTION 'Notification clinic labels must come from the care-team link''s clinic';
  END IF;
END $$;

DROP TABLE _069_grants;
