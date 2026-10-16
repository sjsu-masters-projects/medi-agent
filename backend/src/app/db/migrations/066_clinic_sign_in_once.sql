-- CLN-003 slice B: sign in once and add a clinic to an existing account. Requires 065 (and
-- the 048, 051/054 and 057/058 objects it replaces). Numbered 066: LOC-003's unmerged
-- 066_care_plan_wording_back_translation.sql is renumbered when it lands.
--
-- A clinician signs in without a clinic code and sees every patient they are linked to, as
-- before: access stays the care-team link and no policy reads memberships. A clinic is chosen
-- only inside an action that belongs to one clinic. This migration:
--   * keeps clinicians.clinic_id/clinic_name/role as the clinician's default clinic (the first
--     clinic joined). Joining another clinic adds a membership and leaves the default alone;
--     when the default does change, its role and name come from that clinic's membership;
--   * adds public.clinician_clinic_operation (list memberships, join by open clinic code);
--   * lets an addressed invitation add a clinic to an account that already has one, and checks
--     admin rights against the membership at the invitation's clinic;
--   * tags care conversations, and checks them and the notification centre, by the care-team
--     link's clinic instead of the clinician's default clinic;
--   * moves an admin's role change and removal of a member into one audited, locked function
--     that checks the admin's membership at the clinic named in the request;
--   * records every membership change and clinic-scoped action in an append-only audit trail.
--
-- Written, not applied: applied to a hosted project only on explicit authorization, and
-- before the backend that calls clinician_clinic_operation deploys (apply first, merge after).
-- Every replaced function keeps its signature, so the deployed backend keeps working.
-- Synthetic data only.

-- ── 1. Clinic audit trail ────────────────────────────────────────────────────────────────
-- Append-only: every membership change and every clinic-scoped action, with the acting
-- clinician, the clinic, the action, its target and the time. No names or addresses. No
-- foreign keys, so the history outlives the rows it describes (an admin-signup rollback still
-- deletes its clinic; account deletion keeps the record, which names no one).
CREATE TABLE public.clinic_membership_audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id uuid NOT NULL,
  clinic_id uuid NOT NULL,
  action text NOT NULL CHECK (action IN (
    'joined_at_signup', 'joined_by_code', 'joined_by_invitation',
    'member_role_changed', 'member_removed',
    'patient_invite_code_created',
    'email_invitation_created', 'email_invitation_revoked')),
  target_type text NOT NULL CHECK (target_type IN ('clinician', 'care_team', 'invitation')),
  target_id uuid NOT NULL,
  role public.clinician_role_enum,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_clinic_membership_audit_clinic
  ON public.clinic_membership_audit_events (clinic_id, created_at);
CREATE INDEX idx_clinic_membership_audit_target
  ON public.clinic_membership_audit_events (target_id, created_at);
CREATE INDEX idx_clinic_membership_audit_actor
  ON public.clinic_membership_audit_events (actor_id, created_at);

COMMENT ON TABLE public.clinic_membership_audit_events IS
  'CLN-003: append-only record of clinic membership changes and clinic-scoped actions. Identifiers only; no names or addresses.';

ALTER TABLE public.clinic_membership_audit_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.clinic_membership_audit_events FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON TABLE public.clinic_membership_audit_events TO service_role;

-- Even the table owner cannot rewrite history.
CREATE FUNCTION private.clinic_audit_append_only()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  RAISE EXCEPTION 'The clinic audit trail is append-only' USING ERRCODE = '42501';
END;
$$;

CREATE TRIGGER clinic_membership_audit_no_update_or_delete
  BEFORE UPDATE OR DELETE ON public.clinic_membership_audit_events
  FOR EACH ROW EXECUTE FUNCTION private.clinic_audit_append_only();
CREATE TRIGGER clinic_membership_audit_no_truncate
  BEFORE TRUNCATE ON public.clinic_membership_audit_events
  FOR EACH STATEMENT EXECUTE FUNCTION private.clinic_audit_append_only();

CREATE FUNCTION private.clinic_audit(
  p_actor uuid, p_clinic uuid, p_action text, p_target_type text, p_target uuid,
  p_role public.clinician_role_enum DEFAULT NULL
) RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
AS $$
  INSERT INTO public.clinic_membership_audit_events
    (actor_id, clinic_id, action, target_type, target_id, role)
  VALUES (p_actor, p_clinic, p_action, p_target_type, p_target, p_role);
$$;

-- A clinician row created with a clinic is a signup with a clinic code (or the first admin
-- of a new clinic): the account itself is the actor.
CREATE FUNCTION private.audit_clinician_signup()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  IF NEW.clinic_id IS NOT NULL THEN
    PERFORM private.clinic_audit(NEW.id, NEW.clinic_id, 'joined_at_signup', 'clinician', NEW.id, NEW.role);
  END IF;
  RETURN NULL;
END;
$$;

CREATE TRIGGER clinicians_audit_signup
  AFTER INSERT ON public.clinicians
  FOR EACH ROW EXECUTE FUNCTION private.audit_clinician_signup();

-- A patient invite code is a pending care-team row; the clinician who issued it is the actor
-- and its clinic (set by the 065 guard) is the clinic.
CREATE FUNCTION private.audit_patient_invite_code()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  IF NEW.invite_code IS NOT NULL AND NEW.status = 'pending' AND NEW.clinic_id IS NOT NULL THEN
    PERFORM private.clinic_audit(NEW.clinician_id, NEW.clinic_id, 'patient_invite_code_created',
      'care_team', NEW.id);
  END IF;
  RETURN NULL;
END;
$$;

CREATE TRIGGER care_teams_audit_patient_invite_code
  AFTER INSERT ON public.care_teams
  FOR EACH ROW EXECUTE FUNCTION private.audit_patient_invite_code();

REVOKE ALL ON FUNCTION private.clinic_audit_append_only(),
  private.clinic_audit(uuid, uuid, text, text, uuid, public.clinician_role_enum),
  private.audit_clinician_signup(), private.audit_patient_invite_code()
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION
  private.clinic_audit(uuid, uuid, text, text, uuid, public.clinician_role_enum) TO service_role;

-- ── 2. The default clinic takes its role from that clinic's membership ───────────────────
-- The default changes only when a clinician gets a first clinic or an admin removes them from
-- their default while they belong elsewhere. Copying the role from the membership means no
-- write path can carry a role (an admin role in particular) from one clinic to another.
CREATE FUNCTION private.default_clinic_from_membership()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_role public.clinician_role_enum;
  v_name text;
BEGIN
  IF NEW.clinic_id IS NOT NULL AND NEW.clinic_id IS DISTINCT FROM OLD.clinic_id THEN
    SELECT m.role, cl.display_name INTO v_role, v_name
      FROM public.clinic_memberships m
      JOIN public.clinics cl ON cl.id = m.clinic_id
     WHERE m.clinician_id = NEW.id AND m.clinic_id = NEW.clinic_id AND m.status = 'active';
    IF FOUND THEN
      NEW.role := v_role;
      NEW.clinic_name := v_name;
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER clinicians_default_clinic_from_membership
  BEFORE UPDATE OF clinic_id ON public.clinicians
  FOR EACH ROW EXECUTE FUNCTION private.default_clinic_from_membership();

REVOKE ALL ON FUNCTION private.default_clinic_from_membership() FROM PUBLIC, anon, authenticated;

-- ── 3. Memberships: list, join by open code, and an admin's role change or removal ────────
-- Backend only (service role). The actor is the signed-in clinician. Every clinic-scoped
-- check reads the membership at the clinic named in the request, never clinicians.role.
-- Lock order: clinic, then clinician rows by id, then memberships (as invitation acceptance).
CREATE FUNCTION public.clinician_clinic_operation(
  p_actor uuid, p_action text, p_payload jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  a public.clinicians;
  t public.clinicians;
  cl public.clinics;
  m public.clinic_memberships;
  v_role text := p_payload->>'role';
  v_member uuid;
  v_next uuid;
  v_status text;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'Clinician required' USING ERRCODE = '42501', HINT = 'clinician_required';
  END IF;
  IF p_action = 'list' THEN
    -- Active memberships at active clinics: what a clinic picker may offer.
    RETURN jsonb_build_object(
      'default_clinic_id', (SELECT c.clinic_id FROM public.clinicians c WHERE c.id = p_actor),
      'clinics', (SELECT coalesce(jsonb_agg(jsonb_build_object(
            'clinic_id', s.id, 'clinic_code', s.code, 'clinic_name', s.display_name,
            'status', s.status, 'role', s.role) ORDER BY lower(s.display_name), s.id), '[]'::jsonb)
          FROM (SELECT cl2.id, cl2.code, cl2.display_name, cl2.status, m2.role
                  FROM public.clinic_memberships m2
                  JOIN public.clinics cl2 ON cl2.id = m2.clinic_id
                 WHERE m2.clinician_id = p_actor AND m2.status = 'active'
                   AND cl2.status = 'active') s));
  END IF;

  IF p_action = 'join_code' THEN
    -- An open clinic code grants provider or nurse access, as signup with a code does.
    -- Admin access comes only from an addressed invitation.
    IF v_role IS NULL OR v_role NOT IN ('provider', 'nurse') THEN
      RAISE EXCEPTION 'Invalid role' USING ERRCODE = '22023', HINT = 'invalid_role';
    END IF;
    SELECT * INTO cl FROM public.clinics
     WHERE upper(btrim(code)) = upper(btrim(coalesce(p_payload->>'clinic_code', '')))
     ORDER BY id LIMIT 1 FOR SHARE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Clinic code is invalid' USING ERRCODE = '22023', HINT = 'clinic_code_invalid';
    END IF;
    IF cl.status <> 'active' THEN
      RAISE EXCEPTION 'Clinic code is inactive' USING ERRCODE = '22023', HINT = 'clinic_code_inactive';
    END IF;
    SELECT * INTO a FROM public.clinicians WHERE id = p_actor FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Clinician required' USING ERRCODE = '42501', HINT = 'clinician_required';
    END IF;
    SELECT * INTO m FROM public.clinic_memberships
     WHERE clinician_id = p_actor AND clinic_id = cl.id FOR UPDATE;
    IF FOUND AND m.status = 'active' THEN
      v_status := 'already_member';
    ELSIF FOUND THEN
      -- Removed by this clinic's admin: only that admin can bring the clinician back.
      RAISE EXCEPTION 'Membership inactive' USING ERRCODE = '42501', HINT = 'membership_inactive';
    ELSE
      IF a.clinic_id IS NULL THEN
        -- A first clinic becomes the default; the 065 mirror writes the membership.
        UPDATE public.clinicians
           SET clinic_id = cl.id, clinic_name = cl.display_name,
               role = v_role::public.clinician_role_enum
         WHERE id = p_actor;
      ELSE
        INSERT INTO public.clinic_memberships (clinician_id, clinic_id, role, status)
        VALUES (p_actor, cl.id, v_role::public.clinician_role_enum, 'active');
      END IF;
      PERFORM private.clinic_audit(p_actor, cl.id, 'joined_by_code', 'clinician', p_actor,
        v_role::public.clinician_role_enum);
      v_status := 'joined';
    END IF;
    RETURN jsonb_build_object('status', v_status, 'clinic_id', cl.id, 'clinic_code', cl.code,
      'clinic_name', cl.display_name, 'clinic_status', cl.status,
      'role', (SELECT m3.role FROM public.clinic_memberships m3
                WHERE m3.clinician_id = p_actor AND m3.clinic_id = cl.id));
  END IF;

  IF p_action NOT IN ('set_member_role', 'remove_member') THEN
    RAISE EXCEPTION 'Invalid clinic operation' USING ERRCODE = '22023', HINT = 'invalid_operation';
  END IF;
  v_member := nullif(p_payload->>'member_id', '')::uuid;
  IF v_member IS NULL OR v_member = p_actor THEN
    RAISE EXCEPTION 'An admin cannot change their own membership' USING ERRCODE = '22023',
      HINT = 'self_change';
  END IF;
  IF p_action = 'set_member_role' AND (v_role IS NULL OR v_role NOT IN ('provider', 'nurse', 'admin')) THEN
    RAISE EXCEPTION 'Invalid role' USING ERRCODE = '22023', HINT = 'invalid_role';
  END IF;
  SELECT * INTO cl FROM public.clinics
   WHERE id = nullif(p_payload->>'clinic_id', '')::uuid AND status = 'active' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Clinic unavailable' USING ERRCODE = '42501', HINT = 'clinic_unavailable';
  END IF;
  PERFORM 1 FROM public.clinicians WHERE id IN (p_actor, v_member) ORDER BY id FOR UPDATE;
  -- Admin rights are the role held at this clinic.
  PERFORM 1 FROM public.clinic_memberships
   WHERE clinician_id = p_actor AND clinic_id = cl.id AND role = 'admin' AND status = 'active'
   FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Admin required' USING ERRCODE = '42501', HINT = 'admin_required';
  END IF;
  SELECT * INTO m FROM public.clinic_memberships
   WHERE clinician_id = v_member AND clinic_id = cl.id AND status = 'active' FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Member unavailable' USING ERRCODE = '42501', HINT = 'member_unavailable';
  END IF;
  SELECT * INTO t FROM public.clinicians WHERE id = v_member;
  IF p_action = 'set_member_role' THEN
    UPDATE public.clinic_memberships SET role = v_role::public.clinician_role_enum WHERE id = m.id;
    -- The legacy role is the role at the default clinic, so it changes only with it.
    IF t.clinic_id = cl.id THEN
      UPDATE public.clinicians SET role = v_role::public.clinician_role_enum WHERE id = v_member;
    END IF;
    PERFORM private.clinic_audit(p_actor, cl.id, 'member_role_changed', 'clinician', v_member,
      v_role::public.clinician_role_enum);
    RETURN jsonb_build_object('id', v_member, 'role', v_role, 'clinic_id', cl.id);
  END IF;
  UPDATE public.clinic_memberships SET status = 'inactive' WHERE id = m.id;
  IF t.clinic_id = cl.id THEN
    -- The earliest remaining clinic becomes the default (role and name from its membership,
    -- by the trigger above), or there is none.
    SELECT m4.clinic_id INTO v_next FROM public.clinic_memberships m4
      JOIN public.clinics cl4 ON cl4.id = m4.clinic_id
     WHERE m4.clinician_id = v_member AND m4.status = 'active' AND cl4.status = 'active'
     ORDER BY m4.created_at, m4.clinic_id LIMIT 1;
    IF v_next IS NOT NULL THEN
      UPDATE public.clinicians SET clinic_id = v_next WHERE id = v_member;
    ELSE
      UPDATE public.clinicians SET clinic_id = NULL, clinic_name = '_removed_' || cl.display_name
       WHERE id = v_member;
    END IF;
  END IF;
  PERFORM private.clinic_audit(p_actor, cl.id, 'member_removed', 'clinician', v_member, m.role);
  RETURN jsonb_build_object('id', v_member, 'status', 'removed', 'clinic_id', cl.id);
END;
$$;

REVOKE ALL ON FUNCTION public.clinician_clinic_operation(uuid, text, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.clinician_clinic_operation(uuid, text, jsonb) TO service_role;

-- ── 4. Care conversations belong to the care-team link's clinic ──────────────────────────
-- 048 tagged and checked a thread by the clinician's clinic. A clinician can now hold links at
-- several clinics, so the thread takes the link's clinic, and access needs an active
-- membership there. For a clinician with one clinic the two are the same clinic.
CREATE OR REPLACE FUNCTION private.lock_care_conversation_pair(p_team uuid, p_actor uuid, p_role text)
RETURNS public.care_teams LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_team public.care_teams;
BEGIN
  SELECT t.* INTO v_team FROM public.care_teams t
    JOIN public.patients p ON p.id=t.patient_id
    JOIN public.clinicians c ON c.id=t.clinician_id
    JOIN public.clinics cl ON cl.id=t.clinic_id
    JOIN public.clinic_memberships m ON m.clinician_id=t.clinician_id AND m.clinic_id=t.clinic_id
    WHERE t.id=p_team AND t.status='active' AND cl.status='active' AND m.status='active'
      AND ((p_role='patient' AND t.patient_id=p_actor) OR
           (p_role='clinician' AND t.clinician_id=p_actor))
    FOR SHARE OF t, p, c, cl, m;
  IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Conversation unavailable'; END IF;
  RETURN v_team;
END;
$$;

CREATE OR REPLACE FUNCTION public.care_conversation_operation(
  p_actor_id uuid, p_actor_role text, p_action text, p_payload jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_team public.care_teams;
  v_thread public.care_conversations;
  v_message public.care_conversation_messages;
  v_marker public.care_conversation_reads;
  v_id uuid; v_team_id uuid; v_cursor public.care_conversation_messages;
  v_key uuid; v_body text; v_name text; v_clinic uuid; v_clinic_name text;
  v_limit int; v_items jsonb; v_next uuid; v_result jsonb := '[]'::jsonb;
  v_created boolean := false;
BEGIN
  IF current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION USING ERRCODE='40001', MESSAGE='Conversation operation requires read committed';
  END IF;
  IF p_actor_id IS NULL OR p_actor_role NOT IN ('patient','clinician') OR p_actor_role IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Conversation unavailable';
  END IF;
  IF p_action IN ('recipients','list') THEN
    -- Consistent assignment order for multi-team reads; each pair is checked anew.
    FOR v_team_id IN SELECT t.id FROM public.care_teams t WHERE t.status='active'
      AND ((p_actor_role='patient' AND t.patient_id=p_actor_id) OR
           (p_actor_role='clinician' AND t.clinician_id=p_actor_id)) ORDER BY t.id LOOP
      BEGIN
        v_team := private.lock_care_conversation_pair(v_team_id,p_actor_id,p_actor_role);
      EXCEPTION WHEN insufficient_privilege THEN CONTINUE;
      END;
      IF p_action='recipients' THEN
        -- The clinic and the role are the link's clinic and the role held there.
        SELECT jsonb_build_object('id', CASE WHEN p_actor_role='patient' THEN c.id ELSE p.id END,
          'name', CASE WHEN p_actor_role='patient' THEN concat_ws(' ',c.first_name,c.last_name)
                      ELSE concat_ws(' ',p.first_name,p.last_name) END,
          'role', CASE WHEN p_actor_role='patient' THEN m.role::text ELSE 'patient' END,
          'clinic_name', cl.display_name) INTO v_items
          FROM public.patients p JOIN public.clinicians c ON c.id=v_team.clinician_id
            JOIN public.clinics cl ON cl.id=v_team.clinic_id
            JOIN public.clinic_memberships m ON m.clinician_id=c.id AND m.clinic_id=v_team.clinic_id
          WHERE p.id=v_team.patient_id;
        v_result := v_result || jsonb_build_array(v_items);
      ELSE
        SELECT t.* INTO v_thread FROM public.care_conversations t WHERE t.care_team_id=v_team.id
          AND t.patient_id=v_team.patient_id AND t.clinician_id=v_team.clinician_id
          AND t.clinic_id=v_team.clinic_id;
        IF FOUND THEN
          v_result := v_result || jsonb_build_array(private.care_conversation_summary(v_thread.id,p_actor_id));
        END IF;
      END IF;
    END LOOP;
    IF p_action='list' THEN
      -- Presentation order is independent of the consistent assignment lock order.
      SELECT coalesce(jsonb_agg(value ORDER BY (value->>'last_message_at')::timestamptz DESC NULLS LAST,
        (value->>'id')::uuid), '[]'::jsonb) INTO v_result FROM jsonb_array_elements(v_result);
    END IF;
    RETURN v_result;
  END IF;
  -- Sender-scoped key locks precede assignment/thread locks, including cross-thread retries.
  IF p_action='send' THEN
    v_key := (p_payload->>'client_message_id')::uuid;
    v_body := regexp_replace(p_payload->>'body', '^[[:space:]]+|[[:space:]]+$', '', 'g');
    IF v_key IS NULL OR v_body IS NULL OR char_length(v_body) NOT BETWEEN 1 AND 4000 THEN
      RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid conversation request';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(p_actor_id::text || ':' || v_key::text,0));
  END IF;
  IF p_action='open' THEN
    SELECT t.id INTO v_team_id FROM public.care_teams t WHERE t.status='active' AND
      ((p_actor_role='patient' AND t.patient_id=p_actor_id AND t.clinician_id=(p_payload->>'recipient_id')::uuid)
       OR (p_actor_role='clinician' AND t.clinician_id=p_actor_id AND t.patient_id=(p_payload->>'recipient_id')::uuid));
  ELSE
    SELECT t.care_team_id INTO v_team_id FROM public.care_conversations t
      WHERE t.id=(p_payload->>'conversation_id')::uuid;
  END IF;
  v_team := private.lock_care_conversation_pair(v_team_id,p_actor_id,p_actor_role);
  SELECT cl.id, cl.display_name INTO v_clinic,v_clinic_name FROM public.clinics cl
    WHERE cl.id=v_team.clinic_id;
  IF p_action='open' THEN
    INSERT INTO public.care_conversations(care_team_id,patient_id,clinician_id,clinic_id,clinic_name)
      VALUES(v_team.id,v_team.patient_id,v_team.clinician_id,v_clinic,v_clinic_name)
      ON CONFLICT(care_team_id,patient_id,clinician_id,clinic_id) DO NOTHING RETURNING id INTO v_id;
    v_created := FOUND;
    SELECT * INTO v_thread FROM public.care_conversations WHERE care_team_id=v_team.id
      AND patient_id=v_team.patient_id AND clinician_id=v_team.clinician_id
      AND clinic_id=v_clinic FOR UPDATE;
  ELSE
    SELECT * INTO v_thread FROM public.care_conversations
      WHERE id=(p_payload->>'conversation_id')::uuid FOR UPDATE;
  END IF;
  IF NOT FOUND OR v_thread.patient_id<>v_team.patient_id OR v_thread.clinician_id<>v_team.clinician_id
    OR v_thread.clinic_id<>v_clinic THEN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Conversation unavailable';
  END IF;
  IF p_action='open' THEN
    IF v_created THEN
      INSERT INTO public.care_conversation_audit_events(conversation_id,actor_id,action)
        VALUES(v_thread.id,p_actor_id,'opened');
    END IF;
    RETURN private.care_conversation_summary(v_thread.id,p_actor_id);
  ELSIF p_action='messages' THEN
    v_limit := coalesce((p_payload->>'limit')::int,50);
    IF v_limit NOT BETWEEN 1 AND 100 THEN
      RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid conversation request';
    END IF;
    IF p_payload->>'before' IS NOT NULL THEN
      SELECT * INTO v_cursor FROM public.care_conversation_messages
        WHERE id=(p_payload->>'before')::uuid AND conversation_id=v_thread.id;
      IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid conversation request'; END IF;
    END IF;
    SELECT coalesce(jsonb_agg(private.care_conversation_message(m.id) ORDER BY m.created_at,m.id),'[]'::jsonb)
      INTO v_items FROM (SELECT * FROM public.care_conversation_messages
        WHERE conversation_id=v_thread.id AND (v_cursor.id IS NULL OR (created_at,id)<(v_cursor.created_at,v_cursor.id))
        ORDER BY created_at DESC,id DESC LIMIT v_limit) m;
    IF jsonb_array_length(v_items)>0 THEN
      SELECT * INTO v_cursor FROM public.care_conversation_messages WHERE id=(v_items->0->>'id')::uuid;
      IF EXISTS(SELECT 1 FROM public.care_conversation_messages WHERE conversation_id=v_thread.id
        AND (created_at,id)<(v_cursor.created_at,v_cursor.id)) THEN v_next := v_cursor.id; END IF;
    END IF;
    RETURN jsonb_build_object('items',v_items,'next_cursor',v_next);
  ELSIF p_action='send' THEN
    SELECT * INTO v_message FROM public.care_conversation_messages
      WHERE sender_id=p_actor_id AND client_message_id=v_key;
    IF FOUND THEN
      IF v_message.conversation_id<>v_thread.id OR v_message.body<>v_body THEN
        RAISE EXCEPTION USING ERRCODE='23505', MESSAGE='Message idempotency mismatch';
      END IF;
      RETURN private.care_conversation_message(v_message.id);
    END IF;
    IF p_actor_role='patient' THEN
      SELECT concat_ws(' ',first_name,last_name) INTO v_name FROM public.patients WHERE id=p_actor_id;
    ELSE
      SELECT concat_ws(' ',first_name,last_name) INTO v_name FROM public.clinicians WHERE id=p_actor_id;
    END IF;
    -- Transaction start timestamps can backdate waiting sends below a read marker.
    INSERT INTO public.care_conversation_messages(conversation_id,sender_id,sender_role,sender_name,body,client_message_id,created_at)
      VALUES(v_thread.id,p_actor_id,p_actor_role,v_name,v_body,v_key,
        greatest(clock_timestamp(),v_thread.last_message_at + interval '1 microsecond')) RETURNING * INTO v_message;
    UPDATE public.care_conversations SET last_message_at=v_message.created_at WHERE id=v_thread.id;
    INSERT INTO public.care_conversation_audit_events(conversation_id,actor_id,action,message_id)
      VALUES(v_thread.id,p_actor_id,'sent',v_message.id);
    RETURN private.care_conversation_message(v_message.id);
  ELSIF p_action='read' THEN
    SELECT * INTO v_message FROM public.care_conversation_messages
      WHERE id=(p_payload->>'last_message_id')::uuid AND conversation_id=v_thread.id;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid conversation request'; END IF;
    SELECT * INTO v_marker FROM public.care_conversation_reads WHERE conversation_id=v_thread.id AND actor_id=p_actor_id;
    IF NOT FOUND OR (v_message.created_at,v_message.id)>(v_marker.last_message_at,v_marker.last_message_id) THEN
      INSERT INTO public.care_conversation_reads(conversation_id,actor_id,last_message_id,last_message_at,read_at)
        VALUES(v_thread.id,p_actor_id,v_message.id,v_message.created_at,clock_timestamp())
        ON CONFLICT(conversation_id,actor_id) DO UPDATE SET last_message_id=EXCLUDED.last_message_id,
          last_message_at=EXCLUDED.last_message_at,read_at=EXCLUDED.read_at RETURNING * INTO v_marker;
      INSERT INTO public.care_conversation_audit_events(conversation_id,actor_id,action,message_id)
        VALUES(v_thread.id,p_actor_id,'read',v_message.id);
    END IF;
    RETURN jsonb_build_object('read_at',v_marker.read_at);
  END IF;
  RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid conversation request';
END;
$$;

REVOKE ALL ON FUNCTION public.care_conversation_operation(uuid,text,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.care_conversation_operation(uuid,text,text,jsonb) TO service_role;
REVOKE ALL ON FUNCTION private.lock_care_conversation_pair(uuid,uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION private.lock_care_conversation_pair(uuid,uuid,text) TO service_role;

-- ── 5. Fail-closed verification ──────────────────────────────────────────────────────────
DO $$
BEGIN
  IF NOT (SELECT relrowsecurity FROM pg_catalog.pg_class
           WHERE oid = 'public.clinic_membership_audit_events'::regclass) THEN
    RAISE EXCEPTION 'clinic_membership_audit_events must have row-level security enabled';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(ARRAY['anon', 'authenticated']) r(role)
     CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) p(privilege)
     WHERE pg_catalog.has_table_privilege(r.role, 'public.clinic_membership_audit_events', p.privilege)
  ) OR EXISTS (
    SELECT 1 FROM unnest(ARRAY['UPDATE', 'DELETE', 'TRUNCATE']) p(privilege)
     WHERE pg_catalog.has_table_privilege('service_role', 'public.clinic_membership_audit_events', p.privilege)
  ) THEN
    RAISE EXCEPTION 'clinic_membership_audit_events must be append-only and backend-only';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(ARRAY['anon', 'authenticated']) r(role)
     CROSS JOIN unnest(ARRAY[
       'public.clinician_clinic_operation(uuid,text,jsonb)',
       'public.care_conversation_operation(uuid,text,text,jsonb)']) f(name)
     WHERE pg_catalog.has_function_privilege(r.role, f.name, 'EXECUTE')
  ) THEN
    RAISE EXCEPTION 'Clinic and conversation operations are for the service role only';
  END IF;
  IF (SELECT count(*) FROM pg_catalog.pg_trigger
       WHERE tgrelid = 'public.clinic_membership_audit_events'::regclass
         AND tgname IN ('clinic_membership_audit_no_update_or_delete',
                        'clinic_membership_audit_no_truncate')) <> 2 THEN
    RAISE EXCEPTION 'The clinic audit trail needs its append-only triggers';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(ARRAY['anon', 'authenticated']) r(role)
     CROSS JOIN unnest(ARRAY['public.clinicians', 'public.clinic_memberships']) t(name)
     CROSS JOIN unnest(ARRAY['INSERT', 'UPDATE', 'DELETE']) p(privilege)
     WHERE pg_catalog.has_table_privilege(r.role, t.name, p.privilege)
  ) THEN
    RAISE EXCEPTION 'Browser roles may not write clinicians or clinic_memberships';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_trigger
                  WHERE tgname = 'clinicians_default_clinic_from_membership'
                    AND tgrelid = 'public.clinicians'::regclass)
     OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_trigger
                     WHERE tgname = 'clinicians_mirror_clinic_membership'
                       AND tgrelid = 'public.clinicians'::regclass) THEN
    RAISE EXCEPTION 'The default-clinic and mirror triggers on clinicians are required';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_catalog.pg_proc
     WHERE proname IN ('lock_care_conversation_pair', 'care_conversation_operation')
       AND prosrc ~ 'cl\.id\s*=\s*c\.clinic_id'
  ) THEN
    RAISE EXCEPTION 'Care conversations must use the care-team link''s clinic';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.clinicians c
     WHERE c.clinic_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM public.clinic_memberships m
        WHERE m.clinician_id = c.id AND m.clinic_id = c.clinic_id AND m.status = 'active'
          AND m.role = c.role)
  ) THEN
    RAISE EXCEPTION 'Every default clinic needs an active membership with the same role';
  END IF;
END $$;

-- ── 6. Invitations add a clinic; admin rights come from that clinic's membership ─────────
-- Same signature and results as 058. Changes: create and list act in the clinic named by
-- p_payload.clinic_id (the default clinic when absent, for the deployed backend); revoke acts
-- in the invitation's clinic; every admin check reads the membership at that clinic; an
-- address that belongs to another clinic can be invited; accepting adds a membership and
-- keeps the account's other memberships and default clinic.
CREATE OR REPLACE FUNCTION public.clinician_email_invitation_operation(p_actor uuid,p_action text,p_payload jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE a public.clinicians; i public.clinician_email_invitations; cl public.clinics; v_id uuid; v_outbox uuid;
  v_clinic uuid; v_email text; v_account text:=lower(nullif(btrim(p_payload->>'account_email'),''));
BEGIN
 -- Lock order for every operation: clinic, then clinician rows by id, then invitation.
 IF p_action IN ('create','list','revoke') THEN
  IF p_action='revoke' THEN
   -- Unlocked lookup only to learn the clinic; state is rechecked under lock below.
   SELECT clinic_id INTO v_clinic FROM public.clinician_email_invitations WHERE id=(p_payload->>'id')::uuid;
  ELSE
   v_clinic:=nullif(p_payload->>'clinic_id','')::uuid;
   IF v_clinic IS NULL THEN SELECT clinic_id INTO v_clinic FROM public.clinicians WHERE id=p_actor; END IF;
  END IF;
  IF NOT EXISTS(SELECT 1 FROM public.clinic_memberships WHERE clinician_id=p_actor AND clinic_id=v_clinic
    AND role='admin' AND status='active') THEN
   IF p_action='revoke' AND EXISTS(SELECT 1 FROM public.clinic_memberships WHERE clinician_id=p_actor
     AND role='admin' AND status='active') THEN
    -- An admin elsewhere learns nothing about another clinic's invitation.
    RAISE EXCEPTION 'Invitation unavailable' USING ERRCODE='42501',HINT='invitation_unavailable';
   END IF;
   RAISE EXCEPTION 'Admin required' USING ERRCODE='42501',HINT='admin_required';
  END IF;
  IF p_action='list' THEN
   -- History is read-only and takes no row locks.
   IF NOT EXISTS(SELECT 1 FROM public.clinics WHERE id=v_clinic AND status='active') THEN
    RAISE EXCEPTION 'Clinic unavailable' USING ERRCODE='42501',HINT='clinic_unavailable'; END IF;
   RETURN jsonb_build_object('items',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',s.id,'email',s.email,'role',s.role,
      'expires_at',s.expires_at,'accepted_at',s.accepted_at,'revoked_at',s.revoked_at,
      'delivery_state',(SELECT state FROM public.email_outbox WHERE invitation_id=s.id ORDER BY created_at DESC LIMIT 1))
      ORDER BY s.created_at DESC),'[]')
     FROM (SELECT * FROM public.clinician_email_invitations WHERE clinic_id=v_clinic ORDER BY created_at DESC LIMIT 50) s));
  END IF;
  -- Serializes invitation changes across different admins of the same clinic.
  SELECT * INTO cl FROM public.clinics WHERE id=v_clinic AND status='active' FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Clinic unavailable' USING ERRCODE='42501',HINT='clinic_unavailable'; END IF;
  SELECT * INTO a FROM public.clinicians WHERE id=p_actor FOR SHARE;
  PERFORM 1 FROM public.clinic_memberships WHERE clinician_id=p_actor AND clinic_id=cl.id
    AND role='admin' AND status='active' FOR SHARE;
  IF a.id IS NULL OR NOT FOUND THEN
   RAISE EXCEPTION 'Admin required' USING ERRCODE='42501',HINT='admin_required'; END IF;
  IF p_action='revoke' THEN
   UPDATE public.clinician_email_invitations SET revoked_at=coalesce(revoked_at,clock_timestamp())
    WHERE id=(p_payload->>'id')::uuid AND clinic_id=cl.id AND accepted_at IS NULL RETURNING id INTO v_id;
   IF v_id IS NULL THEN RAISE EXCEPTION 'Invitation unavailable' USING ERRCODE='42501',HINT='invitation_unavailable'; END IF;
   PERFORM private.clinic_audit(p_actor,cl.id,'email_invitation_revoked','invitation',v_id);
   -- A revoked link never leaves the outbox.
   UPDATE public.email_outbox SET state='suppressed',payload=NULL,updated_at=clock_timestamp()
    WHERE invitation_id=v_id AND state='queued';
   RETURN jsonb_build_object('status','revoked');
  END IF;
  v_email:=lower(btrim(p_payload->>'email'));
  IF v_email IS NULL OR position('@' IN v_email)<2 THEN
   RAISE EXCEPTION 'Invalid invitation address' USING ERRCODE='22023',HINT='invalid_address'; END IF;
  IF v_email LIKE '%@accounts.mediagent.live' THEN
   RAISE EXCEPTION 'Undeliverable demo address' USING ERRCODE='22023',HINT='synthetic_address'; END IF;
  -- An address that belongs to another clinic can be invited; acceptance adds this clinic.
  IF EXISTS(SELECT 1 FROM public.clinicians c JOIN public.clinic_memberships m ON m.clinician_id=c.id
    WHERE lower(c.email)=v_email AND m.clinic_id=cl.id AND m.status='active') THEN
   RAISE EXCEPTION 'Already a member of this clinic' USING ERRCODE='22023',HINT='already_member'; END IF;
  SELECT * INTO i FROM public.clinician_email_invitations WHERE clinic_id=cl.id AND email=v_email
    AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at>clock_timestamp()
    ORDER BY created_at DESC LIMIT 1 FOR UPDATE;
  IF FOUND THEN
   IF EXISTS(SELECT 1 FROM public.email_outbox WHERE invitation_id=i.id AND state IN ('queued','sending','accepted','delivered')) THEN
    RETURN jsonb_build_object('status','already_pending','email_sent',false);
   END IF;
   -- The earlier link's delivery stopped (failed, bounced or suppressed). Replace it.
   UPDATE public.clinician_email_invitations SET revoked_at=clock_timestamp() WHERE id=i.id;
   PERFORM private.clinic_audit(p_actor,cl.id,'email_invitation_revoked','invitation',i.id,i.role);
  END IF;
  INSERT INTO public.clinician_email_invitations(clinic_id,invited_by,email,role,token_hash)
   VALUES(cl.id,p_actor,v_email,(p_payload->>'role')::public.clinician_role_enum,p_payload->>'hash') RETURNING * INTO i;
  PERFORM private.clinic_audit(p_actor,cl.id,'email_invitation_created','invitation',i.id,i.role);
  INSERT INTO public.email_outbox(invitation_id,kind,dedupe_key,payload)
   VALUES(i.id,'invitation','invitation/'||i.id::text,p_payload->'payload') RETURNING id INTO v_outbox;
  RETURN jsonb_build_object('status','queued','email_sent',false,'invitation_id',i.id,'outbox_id',v_outbox);
 END IF;

 IF p_action NOT IN ('preview','accept') THEN
  RAISE EXCEPTION 'Invalid invitation operation' USING ERRCODE='22023',HINT='invalid_operation'; END IF;
 -- Unlocked lookup only to learn the clinic; state is rechecked under lock below.
 SELECT * INTO i FROM public.clinician_email_invitations WHERE token_hash=p_payload->>'hash';
 IF NOT FOUND THEN RAISE EXCEPTION 'Invitation invalid or expired' USING ERRCODE='22023',HINT='invitation_invalid'; END IF;
 IF p_action='preview' THEN
  IF i.accepted_at IS NOT NULL OR i.revoked_at IS NOT NULL OR i.expires_at<=clock_timestamp() THEN
   RAISE EXCEPTION 'Invitation invalid or expired' USING ERRCODE='22023',HINT='invitation_invalid'; END IF;
  SELECT * INTO cl FROM public.clinics WHERE id=i.clinic_id AND status='active';
  IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM public.clinic_memberships WHERE clinician_id=i.invited_by
    AND clinic_id=i.clinic_id AND role='admin' AND status='active') THEN
   RAISE EXCEPTION 'Invitation unavailable' USING ERRCODE='42501',HINT='invitation_unavailable'; END IF;
  -- The clinic code is shared only after membership is accepted.
  RETURN jsonb_build_object('email',i.email,'role',i.role,'clinic_name',cl.display_name,'status','active');
 END IF;
 SELECT * INTO cl FROM public.clinics WHERE id=i.clinic_id FOR SHARE;
 IF NOT FOUND OR cl.status<>'active' THEN
  RAISE EXCEPTION 'Invitation unavailable' USING ERRCODE='42501',HINT='invitation_unavailable'; END IF;
 PERFORM 1 FROM public.clinicians WHERE id IN (p_actor,i.invited_by) ORDER BY id FOR UPDATE;
 SELECT * INTO i FROM public.clinician_email_invitations WHERE id=i.id FOR UPDATE;
 SELECT * INTO a FROM public.clinicians WHERE id=p_actor;
 IF i.accepted_by=p_actor AND i.accepted_at IS NOT NULL AND v_account=i.email AND EXISTS(
   SELECT 1 FROM public.clinic_memberships WHERE clinician_id=p_actor AND clinic_id=i.clinic_id AND status='active') THEN
  RETURN jsonb_build_object('status','accepted','clinic_id',cl.id,'clinic_code',cl.code,'clinic_name',cl.display_name,'clinic_status',cl.status);
 END IF;
 IF i.accepted_at IS NOT NULL OR i.revoked_at IS NOT NULL OR i.expires_at<=clock_timestamp() THEN
  RAISE EXCEPTION 'Invitation invalid or expired' USING ERRCODE='22023',HINT='invitation_invalid'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.clinic_memberships WHERE clinician_id=i.invited_by
   AND clinic_id=i.clinic_id AND role='admin' AND status='active') THEN
  RAISE EXCEPTION 'Invitation unavailable' USING ERRCODE='42501',HINT='invitation_unavailable'; END IF;
 IF a.id IS NULL OR v_account IS DISTINCT FROM i.email THEN
  RAISE EXCEPTION 'Invitation not for this account' USING ERRCODE='42501',HINT='invitation_wrong_account'; END IF;
 IF EXISTS(SELECT 1 FROM public.clinic_memberships WHERE clinician_id=p_actor AND clinic_id=i.clinic_id AND status='active') THEN
  RAISE EXCEPTION 'Already a member of this clinic' USING ERRCODE='22023',HINT='already_member'; END IF;
 IF a.clinic_id IS NULL THEN
  -- A first clinic becomes the default; the 065 mirror writes (or reactivates) the membership.
  UPDATE public.clinicians SET clinic_id=i.clinic_id,clinic_name=cl.display_name,role=i.role WHERE id=p_actor;
 ELSE
  -- Another clinic: add it. The default clinic and the other memberships are unchanged.
  INSERT INTO public.clinic_memberships AS m(clinician_id,clinic_id,role,status) VALUES(p_actor,i.clinic_id,i.role,'active')
   ON CONFLICT(clinician_id,clinic_id) DO UPDATE SET role=EXCLUDED.role,status='active';
 END IF;
 PERFORM private.clinic_audit(p_actor,i.clinic_id,'joined_by_invitation','clinician',p_actor,i.role);
 UPDATE public.clinician_email_invitations SET accepted_by=p_actor,accepted_at=clock_timestamp() WHERE id=i.id;
 UPDATE public.email_outbox SET state='suppressed',payload=NULL,updated_at=clock_timestamp()
  WHERE invitation_id=i.id AND state='queued';
 -- Possession of the addressed invitation proves ownership; optional notices stay off.
 INSERT INTO public.email_contacts(user_id,role,email,verified_at) VALUES(p_actor,'clinician',i.email,clock_timestamp())
  ON CONFLICT(user_id) DO UPDATE SET email=EXCLUDED.email,verified_at=EXCLUDED.verified_at,preferences='{}',consent_at=NULL;
 RETURN jsonb_build_object('status','accepted','clinic_id',cl.id,'clinic_code',cl.code,'clinic_name',cl.display_name,'clinic_status',cl.status);
END;
$$;

REVOKE ALL ON FUNCTION public.clinician_email_invitation_operation(uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.clinician_email_invitation_operation(uuid,text,jsonb) TO service_role;

DO $$
BEGIN
  IF pg_catalog.has_function_privilege('anon', 'public.clinician_email_invitation_operation(uuid,text,jsonb)', 'EXECUTE')
     OR pg_catalog.has_function_privilege('authenticated', 'public.clinician_email_invitation_operation(uuid,text,jsonb)', 'EXECUTE') THEN
    RAISE EXCEPTION 'The invitation operation is for the service role only';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_proc WHERE proname = 'clinician_email_invitation_operation'
              AND prosrc ~ 'role=''admin'' AND clinic_id=i\.clinic_id\)') THEN
    RAISE EXCEPTION 'Invitation admin checks must read the membership at the invitation''s clinic';
  END IF;
END $$;

-- ── 7. Notification centre checks use the care-team link's clinic ────────────────────────
-- Same signatures and rules as 051/054; the clinic is the link's clinic, with an active
-- membership there, instead of the clinician's default clinic. notification_scope still
-- covers every patient notification_authorized can admit.
CREATE OR REPLACE FUNCTION private.notification_authorized(e public.notification_events,p_actor uuid,p_role text)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE s jsonb; t public.care_conversations;
BEGIN
 s:=private.notification_source(e.source_type,e.source_id);
 IF s IS NULL THEN RETURN false; END IF;
 IF e.source_type='care_conversation_messages' THEN
   SELECT * INTO t FROM public.care_conversations WHERE id=(s->>'conversation_id')::uuid;
   RETURN e.recipient_id=p_actor AND EXISTS(SELECT 1 FROM public.care_teams ct
     JOIN public.clinics cl ON cl.id=ct.clinic_id
     JOIN public.clinic_memberships m ON m.clinician_id=ct.clinician_id AND m.clinic_id=ct.clinic_id
     WHERE ct.id=t.care_team_id AND ct.patient_id=t.patient_id AND ct.clinician_id=t.clinician_id
       AND ct.clinic_id=t.clinic_id AND cl.status='active' AND ct.status='active' AND m.status='active'
       AND ((p_role='patient' AND t.patient_id=p_actor) OR (p_role='clinician' AND t.clinician_id=p_actor)));
 END IF;
 IF (s->>'patient_id')::uuid IS DISTINCT FROM e.patient_id THEN RETURN false; END IF;
 IF p_role='patient' THEN
   IF p_actor<>e.patient_id OR e.audience<>'patient' THEN RETURN false; END IF;
   IF e.source_type='care_plan_versions' AND s->>'status' NOT IN ('approved','superseded') THEN RETURN false; END IF;
   IF e.source_type='adr_assessments' AND e.event_type<>'adr_information_requested' THEN RETURN false; END IF;
   RETURN true;
 END IF;
 RETURN p_role='clinician' AND e.audience IN ('clinician','shared')
   AND (e.audience<>'clinician' OR e.recipient_id=p_actor)
   AND EXISTS(SELECT 1 FROM public.care_teams ct JOIN public.clinics cl ON cl.id=ct.clinic_id
     JOIN public.clinic_memberships m ON m.clinician_id=ct.clinician_id AND m.clinic_id=ct.clinic_id
     WHERE ct.patient_id=e.patient_id AND ct.clinician_id=p_actor AND ct.status='active'
       AND cl.status='active' AND m.status='active');
END;
$$;

CREATE OR REPLACE FUNCTION private.notification_scope(p_actor uuid,p_role text) RETURNS uuid[]
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT CASE WHEN p_role='patient' THEN ARRAY[p_actor] ELSE
   (SELECT coalesce(array_agg(DISTINCT t.patient_id),'{}') FROM public.care_teams t
     JOIN public.clinics cl ON cl.id=t.clinic_id
     JOIN public.clinic_memberships m ON m.clinician_id=t.clinician_id AND m.clinic_id=t.clinic_id
     WHERE t.clinician_id=p_actor AND t.status='active' AND cl.status='active' AND m.status='active') END
$$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_catalog.pg_proc
     WHERE proname IN ('notification_authorized', 'notification_scope')
       AND prosrc ~ 'cl\.id\s*=\s*c\.clinic_id'
  ) THEN
    RAISE EXCEPTION 'Notification checks must use the care-team link''s clinic';
  END IF;
END $$;
