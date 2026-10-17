-- CLN-003 slices C and D: "All clinics" lists with clinic chips and filters, and per-clinic
-- roles and settings. Requires 066 (and the 051/054/060/061 notification objects it builds on).
-- LOC-003's unmerged care-plan wording migration (branch feature/english-first-review) is
-- renumbered to the next free number after this one.
--
-- This migration:
--   * widens the clinic audit trail's action and target checks (the table stays append-only:
--     its triggers and grants are not touched, and are checked again below);
--   * adds three actions to public.clinician_clinic_operation, same signature and grants:
--       set_default   change which clinic is preselected (audited);
--       leave         leave one clinic: refused for the last clinic and for the sole admin;
--                     ends the caller's own care-team links and unused invite codes there,
--                     each audited (decision recorded in the CLN-003 spec);
--       update_clinic an admin edits that clinic's display name (audited);
--   * stops the 065 compatibility mirror from deactivating a membership when the default
--     clinic switches to a clinic the clinician already belongs to;
--   * lets the notification centre list and action items be narrowed to one clinic's links,
--     and makes notification clinic labels the care-team link's clinic (not the clinician's
--     default clinic). Summary counts and every other action are unchanged.
--
-- Written, not applied: applied to a hosted project only on explicit authorization, and
-- before the backend that calls the new actions deploys (apply first, merge after). Every
-- replaced function keeps its signature and its behaviour for the old payloads. Synthetic data.

-- ── 1. Audit trail vocabulary ────────────────────────────────────────────────────────────
ALTER TABLE public.clinic_membership_audit_events
  DROP CONSTRAINT clinic_membership_audit_events_action_check,
  DROP CONSTRAINT clinic_membership_audit_events_target_type_check;
ALTER TABLE public.clinic_membership_audit_events
  ADD CONSTRAINT clinic_membership_audit_events_action_check CHECK (action IN (
    'joined_at_signup', 'joined_by_code', 'joined_by_invitation',
    'member_role_changed', 'member_removed',
    'patient_invite_code_created',
    'email_invitation_created', 'email_invitation_revoked',
    'default_clinic_changed', 'member_left', 'care_link_ended', 'clinic_renamed')),
  ADD CONSTRAINT clinic_membership_audit_events_target_type_check CHECK (
    target_type IN ('clinician', 'care_team', 'invitation', 'clinic'));

-- ── 2. Switching the default clinic is not leaving the old one ────────────────────────────
CREATE OR REPLACE FUNCTION private.mirror_legacy_clinic_membership()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND OLD.clinic_id IS NOT NULL
     AND OLD.clinic_id IS DISTINCT FROM NEW.clinic_id
     AND NOT (NEW.clinic_id IS NOT NULL AND EXISTS (
       SELECT 1 FROM public.clinic_memberships m0
        WHERE m0.clinician_id = NEW.id AND m0.clinic_id = NEW.clinic_id AND m0.status = 'active')) THEN
    -- A legacy move to a clinic with no active membership ends the old one, as in 065. A
    -- switch to a clinic the clinician already belongs to (make default) ends nothing.
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

-- ── 3. Make default, leave, and edit a clinic's name ─────────────────────────────────────
CREATE OR REPLACE FUNCTION public.clinician_clinic_operation(
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
  v_name text;
  v_link record;
  v_ended int := 0;
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

  IF p_action = 'set_default' THEN
    -- Which clinic is preselected, and the legacy mirror columns. Nothing else changes.
    SELECT * INTO cl FROM public.clinics
     WHERE id = nullif(p_payload->>'clinic_id', '')::uuid AND status = 'active' FOR SHARE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Clinic unavailable' USING ERRCODE = '42501', HINT = 'clinic_unavailable';
    END IF;
    SELECT * INTO a FROM public.clinicians WHERE id = p_actor FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Clinician required' USING ERRCODE = '42501', HINT = 'clinician_required';
    END IF;
    SELECT * INTO m FROM public.clinic_memberships
     WHERE clinician_id = p_actor AND clinic_id = cl.id AND status = 'active' FOR SHARE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Clinic unavailable' USING ERRCODE = '42501', HINT = 'clinic_unavailable';
    END IF;
    IF a.clinic_id IS DISTINCT FROM cl.id THEN
      -- The role and name follow the membership (default-clinic trigger); no membership ends.
      UPDATE public.clinicians SET clinic_id = cl.id WHERE id = p_actor;
      PERFORM private.clinic_audit(p_actor, cl.id, 'default_clinic_changed', 'clinician', p_actor, m.role);
    END IF;
    RETURN jsonb_build_object('default_clinic_id', cl.id, 'clinic_id', cl.id, 'role', m.role);
  END IF;

  IF p_action = 'leave' THEN
    SELECT * INTO cl FROM public.clinics WHERE id = nullif(p_payload->>'clinic_id', '')::uuid FOR SHARE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Clinic unavailable' USING ERRCODE = '42501', HINT = 'clinic_unavailable';
    END IF;
    -- Every active member of the clinic, by id, so two admins leaving at once serialize.
    PERFORM 1 FROM public.clinicians
     WHERE id IN (SELECT clinician_id FROM public.clinic_memberships
                   WHERE clinic_id = cl.id AND status = 'active')
        OR id = p_actor
     ORDER BY id FOR UPDATE;
    SELECT * INTO m FROM public.clinic_memberships
     WHERE clinician_id = p_actor AND clinic_id = cl.id AND status = 'active' FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Clinic unavailable' USING ERRCODE = '42501', HINT = 'clinic_unavailable';
    END IF;
    IF (SELECT count(*) FROM public.clinic_memberships m5
          JOIN public.clinics cl5 ON cl5.id = m5.clinic_id
         WHERE m5.clinician_id = p_actor AND m5.status = 'active' AND cl5.status = 'active') <= 1 THEN
      RAISE EXCEPTION 'Last clinic' USING ERRCODE = '22023', HINT = 'last_clinic';
    END IF;
    IF m.role = 'admin' AND NOT EXISTS (
         SELECT 1 FROM public.clinic_memberships m6
          WHERE m6.clinic_id = cl.id AND m6.role = 'admin' AND m6.status = 'active'
            AND m6.clinician_id <> p_actor) THEN
      RAISE EXCEPTION 'Sole admin' USING ERRCODE = '22023', HINT = 'sole_admin';
    END IF;
    UPDATE public.clinic_memberships SET status = 'inactive' WHERE id = m.id;
    -- The caller's own links and unused invite codes at this clinic end with the membership,
    -- each recorded. Other clinicians' links and every record are untouched.
    FOR v_link IN SELECT id, patient_id FROM public.care_teams
                   WHERE clinician_id = p_actor AND clinic_id = cl.id
                     AND status IN ('active', 'pending') ORDER BY id FOR UPDATE LOOP
      UPDATE public.care_teams SET status = 'inactive' WHERE id = v_link.id;
      PERFORM private.clinic_audit(p_actor, cl.id, 'care_link_ended', 'care_team', v_link.id);
      IF v_link.patient_id IS NOT NULL THEN v_ended := v_ended + 1; END IF;
    END LOOP;
    SELECT * INTO a FROM public.clinicians WHERE id = p_actor;
    IF a.clinic_id = cl.id THEN
      SELECT m4.clinic_id INTO v_next FROM public.clinic_memberships m4
        JOIN public.clinics cl4 ON cl4.id = m4.clinic_id
       WHERE m4.clinician_id = p_actor AND m4.status = 'active' AND cl4.status = 'active'
       ORDER BY m4.created_at, m4.clinic_id LIMIT 1;
      UPDATE public.clinicians SET clinic_id = v_next WHERE id = p_actor;
    END IF;
    PERFORM private.clinic_audit(p_actor, cl.id, 'member_left', 'clinician', p_actor, m.role);
    RETURN jsonb_build_object('status', 'left', 'clinic_id', cl.id, 'links_ended', v_ended,
      'default_clinic_id', (SELECT c.clinic_id FROM public.clinicians c WHERE c.id = p_actor));
  END IF;

  IF p_action = 'update_clinic' THEN
    v_name := regexp_replace(btrim(coalesce(p_payload->>'display_name', '')), '\s+', ' ', 'g');
    IF char_length(v_name) NOT BETWEEN 2 AND 120 THEN
      RAISE EXCEPTION 'Invalid clinic name' USING ERRCODE = '22023', HINT = 'invalid_name';
    END IF;
    SELECT * INTO cl FROM public.clinics
     WHERE id = nullif(p_payload->>'clinic_id', '')::uuid AND status = 'active' FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Clinic unavailable' USING ERRCODE = '42501', HINT = 'clinic_unavailable';
    END IF;
    PERFORM 1 FROM public.clinicians WHERE id = p_actor OR clinic_id = cl.id ORDER BY id FOR UPDATE;
    SELECT * INTO m FROM public.clinic_memberships
     WHERE clinician_id = p_actor AND clinic_id = cl.id AND status = 'active' FOR SHARE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Clinic unavailable' USING ERRCODE = '42501', HINT = 'clinic_unavailable';
    END IF;
    IF m.role <> 'admin' THEN
      RAISE EXCEPTION 'Admin required' USING ERRCODE = '42501', HINT = 'admin_required';
    END IF;
    IF EXISTS (SELECT 1 FROM public.clinics WHERE canonical_name = lower(v_name) AND id <> cl.id) THEN
      RAISE EXCEPTION 'Clinic name taken' USING ERRCODE = '22023', HINT = 'clinic_name_taken';
    END IF;
    UPDATE public.clinics SET display_name = v_name, canonical_name = lower(v_name),
           updated_at = clock_timestamp() WHERE id = cl.id;
    -- The legacy label of members whose default clinic this is.
    UPDATE public.clinicians SET clinic_name = v_name WHERE clinic_id = cl.id;
    PERFORM private.clinic_audit(p_actor, cl.id, 'clinic_renamed', 'clinic', cl.id, m.role);
    RETURN jsonb_build_object('clinic_id', cl.id, 'clinic_name', v_name);
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
      -- No default clinic remains, so no clinic-scoped role (admin in particular) may linger.
      UPDATE public.clinicians SET clinic_id = NULL, role = 'provider',
             clinic_name = '_removed_' || cl.display_name
       WHERE id = v_member;
    END IF;
  END IF;
  PERFORM private.clinic_audit(p_actor, cl.id, 'member_removed', 'clinician', v_member, m.role);
  RETURN jsonb_build_object('id', v_member, 'status', 'removed', 'clinic_id', cl.id);
END;
$$;

REVOKE ALL ON FUNCTION public.clinician_clinic_operation(uuid, text, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.clinician_clinic_operation(uuid, text, jsonb) TO service_role;

-- ── 4. Notification centre: clinic filter and the link's clinic ──────────────────────────
-- Same signatures as 061 (grants stay). The only changes: the visible patients narrow to one
-- clinic's links on request, the assignment lock joins the link's clinic, and each item
-- carries the link's clinic id and name.
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
     (a.active AND a.latest AND a.acknowledged_at IS NULL) needs
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
     'clinic_id',ct.clinic_id,
     'clinic_name',coalesce(cl.display_name,ct.clinic_name),
     'actor_name',coalesce(a.metadata->>'actor_name',concat_ws(' ',c.first_name,c.last_name)))
 FROM states a JOIN public.patients p ON p.id=a.patient_id
 LEFT JOIN LATERAL (SELECT t.* FROM public.care_teams t WHERE t.patient_id=a.patient_id AND t.status='active'
   AND (CASE WHEN p_role='clinician' THEN t.clinician_id=p_actor
     WHEN a.metadata->>'clinician_id' IS NOT NULL THEN t.clinician_id=(a.metadata->>'clinician_id')::uuid ELSE true END)
   ORDER BY t.id LIMIT 1) ct ON true
 LEFT JOIN public.clinicians c ON c.id=ct.clinician_id LEFT JOIN public.clinics cl ON cl.id=ct.clinic_id;
$$;

CREATE OR REPLACE FUNCTION public.notification_centre_operation(
 p_actor_id uuid,p_actor_role text,p_action text,p_payload jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v_limit int; v_items jsonb; v_next jsonb; v_ids uuid[]; v_read_ids jsonb; v_count int:=0;
  x record; v_target record; v_note text; v_ack boolean; v_receipt uuid; v_skipped int:=0; v_actions int:=0;
  v_patients uuid[]; v_list boolean; v_unread boolean; v_category text;
  v_before_at timestamptz; v_before_id uuid; v_pos_at timestamptz; v_pos_id uuid;
  v_window int; v_fetched int; v_walked int:=0; v_capped boolean:=false; v_walk text;
  v_r public.notification_receipts; v_row record;
  v_found_ids uuid[]:='{}'; v_found_at timestamptz[]:='{}'; v_found_items jsonb[]:='{}'; v_found_read boolean[]:='{}';
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN
   RAISE EXCEPTION 'Notification operation requires read committed' USING ERRCODE='40001'; END IF;
 IF p_actor_id IS NULL OR p_actor_role IS NULL OR p_actor_role NOT IN ('patient','clinician')
   OR (p_actor_role='patient' AND NOT EXISTS(SELECT 1 FROM public.patients WHERE id=p_actor_id))
   OR (p_actor_role='clinician' AND NOT EXISTS(SELECT 1 FROM public.clinicians WHERE id=p_actor_id)) THEN
   RAISE EXCEPTION 'Notification unavailable' USING ERRCODE='42501'; END IF;
 IF p_action IS NULL OR p_action NOT IN ('list','summary','action_items','read','read_through','acknowledge')
   OR jsonb_typeof(p_payload) IS DISTINCT FROM 'object' THEN
   RAISE EXCEPTION 'Invalid notification request' USING ERRCODE='22023'; END IF;
 IF p_action IN ('action_items','acknowledge') AND p_actor_role<>'clinician' THEN
   RAISE EXCEPTION 'Notification unavailable' USING ERRCODE='42501'; END IF;
 -- Assignment locks precede receipt locks, serializing revocation with access.
 PERFORM t.id FROM public.care_teams t JOIN public.patients p ON p.id=t.patient_id
   JOIN public.clinicians c ON c.id=t.clinician_id JOIN public.clinics cl ON cl.id=t.clinic_id
   WHERE t.status='active' AND ((p_actor_role='patient' AND t.patient_id=p_actor_id)
     OR (p_actor_role='clinician' AND t.clinician_id=p_actor_id)) ORDER BY t.id FOR SHARE OF t,p,c,cl;
 PERFORM private.notification_prepare(p_actor_id,p_actor_role);
 v_patients:=private.notification_scope(p_actor_id,p_actor_role);
 -- A clinician's clinic filter: only patients linked at that clinic, and only where the caller
 -- holds an active membership. Any other clinic is an empty list, never an error.
 IF p_actor_role='clinician' AND p_action IN ('list','action_items') AND p_payload ? 'clinic_id' THEN
   v_patients:=coalesce((SELECT array_agg(DISTINCT t.patient_id) FROM public.care_teams t
     JOIN public.clinic_memberships cm ON cm.clinician_id=t.clinician_id AND cm.clinic_id=t.clinic_id
     JOIN public.clinics cc ON cc.id=t.clinic_id
     WHERE t.clinician_id=p_actor_id AND t.status='active' AND t.patient_id=ANY(v_patients)
       AND cm.status='active' AND cc.status='active'
       AND t.clinic_id=(p_payload->>'clinic_id')::uuid),'{}');
 END IF;

 IF p_action='summary' THEN
   -- Unread: only receipts in the unread index are evaluated.
   SELECT count(DISTINCT nr.group_key) INTO v_count FROM public.notification_receipts r
     JOIN public.notification_events e ON e.id=r.event_id
     CROSS JOIN LATERAL private.notification_row(r,p_actor_id,p_actor_role) nr
     WHERE r.recipient_id=p_actor_id AND r.recipient_role=p_actor_role AND r.read_at IS NULL
       AND e.patient_id=ANY(v_patients) AND NOT nr.is_read;
   -- Action items: only work whose source is still open is evaluated.
   IF p_actor_role='clinician' THEN
     SELECT count(*) INTO v_actions FROM private.notification_open_work(p_actor_id,p_actor_role,v_patients) r
       CROSS JOIN LATERAL private.notification_row(r,p_actor_id,p_actor_role) nr
       WHERE nr.actionable AND nr.item->>'category'<>'messages';
   END IF;
   RETURN jsonb_build_object('unread_count',v_count,'action_item_count',v_actions);
 ELSIF p_action IN ('list','action_items') THEN
   v_limit:=coalesce((p_payload->>'limit')::int,50);
   IF v_limit NOT BETWEEN 1 AND 100 OR (p_payload ? 'category' AND p_payload->>'category' NOT IN
     ('documents','care_plans','appointments','follow_up','safety'))
     OR (p_payload ? 'before' AND (jsonb_typeof(p_payload->'before')<>'object'
       OR p_payload->'before'->>'id' IS NULL OR p_payload->'before'->>'created_at' IS NULL)) THEN
     RAISE EXCEPTION 'Invalid notification request' USING ERRCODE='22023'; END IF;
   v_list:=p_action='list'; v_unread:=coalesce((p_payload->>'unread')::boolean,false);
   v_category:=p_payload->>'category';
   IF p_payload ? 'before' THEN
     v_before_at:=(p_payload->'before'->>'created_at')::timestamptz; v_before_id:=(p_payload->'before'->>'id')::uuid;
   END IF;
   -- Walk this person's receipts newest first from the cursor in bounded windows and
   -- evaluate only what is walked, until the page plus one is found. Unread grouped rows
   -- (messages, same-day reminders) are excluded here and taken from the unread index below.
   v_walk:='SELECT r.* FROM '
     ||CASE WHEN v_list THEN 'public.notification_receipts' ELSE 'private.notification_open_work($1,$2,$3)' END
     ||' r JOIN public.notification_events e ON e.id=r.event_id
     WHERE r.recipient_id=$1 AND r.recipient_role=$2 AND e.patient_id=ANY($3)
       AND ($4::timestamptz IS NULL OR (r.created_at,r.id)<($4,$5)) AND ($7::text IS NULL OR e.category=$7)'
     ||CASE WHEN NOT v_list THEN ' AND e.category<>''messages'''
       WHEN v_unread THEN ' AND r.read_at IS NULL AND e.event_type<>''message_received'' AND e.category<>''reminders'''
       ELSE ' AND NOT (r.read_at IS NULL AND (e.event_type=''message_received'' OR e.category=''reminders''))' END
     ||' ORDER BY r.created_at DESC,r.id DESC LIMIT $6';
   v_window:=greatest(2*(v_limit+1),50); v_pos_at:=v_before_at; v_pos_id:=v_before_id;
   <<walk>> LOOP
     v_fetched:=0;
     FOR v_r IN EXECUTE v_walk USING p_actor_id,p_actor_role,v_patients,v_pos_at,v_pos_id,v_window,v_category LOOP
       v_fetched:=v_fetched+1; v_walked:=v_walked+1; v_pos_at:=v_r.created_at; v_pos_id:=v_r.id;
       SELECT * INTO v_row FROM private.notification_row(v_r,p_actor_id,p_actor_role);
       CONTINUE WHEN NOT FOUND;
       CONTINUE WHEN CASE WHEN v_list THEN v_unread AND v_row.is_read
         ELSE NOT v_row.actionable OR v_row.item->>'category'='messages' END;
       v_found_ids:=array_append(v_found_ids,v_row.id); v_found_at:=array_append(v_found_at,v_row.created_at);
       v_found_items:=array_append(v_found_items,v_row.item); v_found_read:=array_append(v_found_read,v_row.is_read);
       EXIT walk WHEN cardinality(v_found_ids)>v_limit;
     END LOOP;
     EXIT walk WHEN v_fetched<v_window;
     -- Bounded: a long run of rows that are not shown ends this page early with a cursor
     -- at the walk position, and the next page continues from there.
     IF v_walked>=1000 THEN v_capped:=true; EXIT walk; END IF;
   END LOOP;
   WITH grouped AS MATERIALIZED (
     SELECT nr.id,nr.created_at,nr.is_read,nr.group_key,nr.item FROM public.notification_receipts r
       JOIN public.notification_events e ON e.id=r.event_id
       CROSS JOIN LATERAL private.notification_row(r,p_actor_id,p_actor_role) nr
     WHERE v_list AND r.recipient_id=p_actor_id AND r.recipient_role=p_actor_role AND r.read_at IS NULL
       AND (e.event_type='message_received' OR e.category='reminders') AND e.patient_id=ANY(v_patients)
       AND (v_category IS NULL OR e.category=v_category) AND (NOT v_unread OR NOT nr.is_read)
   ), eligible AS (
     SELECT f.id,f.created_at,f.is_read,'receipt:'||f.id bucket,f.item
       FROM unnest(v_found_ids,v_found_at,v_found_read,v_found_items) f(id,created_at,is_read,item)
     UNION ALL SELECT g.id,g.created_at,g.is_read,CASE WHEN g.is_read THEN 'receipt:'||g.id ELSE g.group_key END,g.item
       FROM grouped g
   ), ranked AS (SELECT *,row_number() OVER(PARTITION BY bucket ORDER BY created_at DESC,id DESC) n FROM eligible),
   page AS (SELECT * FROM ranked WHERE n=1
     AND (v_before_at IS NULL OR (created_at,id)<(v_before_at,v_before_id))
     AND (NOT v_capped OR (created_at,id)>=(v_pos_at,v_pos_id))
     ORDER BY created_at DESC,id DESC LIMIT v_limit+1),
   shown AS (SELECT * FROM page ORDER BY created_at DESC,id DESC LIMIT v_limit)
   SELECT coalesce(jsonb_agg(s.item||jsonb_build_object('receipt_ids',
     (SELECT jsonb_agg(q.id ORDER BY q.created_at DESC,q.id DESC) FROM
       (SELECT r.id,r.created_at FROM eligible r WHERE r.bucket=s.bucket ORDER BY r.created_at DESC,r.id DESC LIMIT 1000) q))
     ORDER BY s.created_at DESC,s.id DESC),'[]'),
     CASE WHEN (SELECT count(*) FROM page)>v_limit THEN
       (SELECT jsonb_build_object('created_at',created_at,'id',id) FROM shown ORDER BY created_at,id LIMIT 1)
     WHEN v_capped THEN jsonb_build_object('created_at',v_pos_at,'id',v_pos_id) END,
     (SELECT coalesce(jsonb_agg(q.id),'[]') FROM (SELECT DISTINCT r.id FROM eligible r JOIN shown s ON s.bucket=r.bucket
       WHERE NOT r.is_read ORDER BY r.id LIMIT 1000) q)
   INTO v_items,v_next,v_read_ids FROM shown s;
   RETURN jsonb_build_object('items',v_items,'next_cursor',v_next,'read_ids',v_read_ids);
 END IF;
 v_ack:=p_action='acknowledge'; v_note:=nullif(btrim(p_payload->>'note'),'');
 IF char_length(v_note)>1000 THEN RAISE EXCEPTION 'Invalid notification request' USING ERRCODE='22023'; END IF;
 IF p_action='read_through' THEN
   IF jsonb_typeof(p_payload->'ids') IS DISTINCT FROM 'array' OR jsonb_array_length(p_payload->'ids')>1000 THEN
     RAISE EXCEPTION 'Invalid notification request' USING ERRCODE='22023'; END IF;
   SELECT coalesce(array_agg(DISTINCT value::uuid),'{}') INTO v_ids FROM jsonb_array_elements_text(p_payload->'ids');
   v_skipped:=cardinality(v_ids);
   -- Only this person's receipts are locked or touched. A receipt in the snapshot that is
   -- no longer authorized (or was never theirs) is skipped, not an error for the batch.
   PERFORM r.id FROM public.notification_receipts r WHERE r.id=ANY(v_ids) AND r.recipient_id=p_actor_id
     ORDER BY r.id FOR UPDATE;
   SELECT coalesce(array_agg(r.id ORDER BY r.id),'{}') INTO v_ids FROM public.notification_receipts r
     JOIN public.notification_events e ON e.id=r.event_id
     WHERE r.id=ANY(v_ids) AND r.recipient_id=p_actor_id AND r.recipient_role=p_actor_role
       AND private.notification_authorized(e,p_actor_id,p_actor_role);
   v_skipped:=v_skipped-cardinality(v_ids);
 ELSE
   v_receipt:=(p_payload->>'id')::uuid;
   SELECT nr.* INTO v_target FROM public.notification_receipts r
     CROSS JOIN LATERAL private.notification_row(r,p_actor_id,p_actor_role) nr
     WHERE r.id=v_receipt AND r.recipient_id=p_actor_id;
   IF NOT FOUND THEN RAISE EXCEPTION 'Notification unavailable' USING ERRCODE='42501'; END IF;
   IF v_ack THEN
     IF NOT v_target.can_acknowledge AND NOT EXISTS(SELECT 1 FROM public.notification_receipts r
       JOIN public.notification_events e ON e.id=r.event_id WHERE r.id=v_receipt AND r.acknowledged_at IS NOT NULL
         AND e.event_type IN ('barrier_reported','safety_flag','appointment_response','critical_result')) THEN
       RAISE EXCEPTION 'Notification cannot be acknowledged' USING ERRCODE='22023'; END IF;
     v_ids:=ARRAY[v_receipt];
   ELSIF v_target.group_key LIKE 'receipt:%' THEN
     v_ids:=ARRAY[v_receipt];
   ELSE
     -- Bound a grouped read by the captured representative, never newer arrivals. Members
     -- already read need nothing, so only the unread index is searched.
     SELECT array_agg(DISTINCT u.id ORDER BY u.id) INTO v_ids FROM (
       SELECT v_receipt id
       UNION ALL SELECT nr.id FROM public.notification_receipts r JOIN public.notification_events e ON e.id=r.event_id
         CROSS JOIN LATERAL private.notification_row(r,p_actor_id,p_actor_role) nr
         WHERE r.recipient_id=p_actor_id AND r.recipient_role=p_actor_role AND r.read_at IS NULL
           AND (e.event_type='message_received' OR e.category='reminders') AND e.patient_id=ANY(v_patients)
           AND nr.group_key=v_target.group_key AND (nr.created_at,nr.id)<=(v_target.created_at,v_target.id)) u;
   END IF;
   PERFORM r.id FROM public.notification_receipts r WHERE r.id=ANY(v_ids) ORDER BY r.id FOR UPDATE;
 END IF;
 FOR x IN SELECT r.*,e.source_type,e.source_id FROM public.notification_receipts r
   JOIN public.notification_events e ON e.id=r.event_id WHERE r.id=ANY(v_ids) ORDER BY r.id LOOP
   IF v_ack AND x.acknowledged_at IS NULL THEN
     UPDATE public.notification_receipts SET acknowledged_at=clock_timestamp() WHERE id=x.id;
     INSERT INTO public.notification_read_audit(receipt_id,actor_id,action,note)
       VALUES(x.id,p_actor_id,'acknowledge',v_note) ON CONFLICT DO NOTHING;
   END IF;
   IF x.read_at IS NULL THEN
     UPDATE public.notification_receipts SET read_at=clock_timestamp() WHERE id=x.id;
     INSERT INTO public.notification_read_audit(receipt_id,actor_id,action) VALUES(x.id,p_actor_id,'read') ON CONFLICT DO NOTHING;
     v_count:=v_count+1;
   END IF;
   IF x.source_type='notifications' THEN UPDATE public.notifications SET is_read=true WHERE id=x.source_id; END IF;
 END LOOP;
 IF p_action='read_through' THEN
   RETURN jsonb_build_object('updated_count',v_count,'skipped_count',v_skipped);
 END IF;
 RETURN jsonb_build_object('updated_count',v_count);
END;
$$;

-- ── 5. Fail-closed verification ──────────────────────────────────────────────────────────
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM unnest(ARRAY['anon', 'authenticated']) r(role)
     CROSS JOIN unnest(ARRAY[
       'public.clinician_clinic_operation(uuid,text,jsonb)',
       'public.notification_centre_operation(uuid,text,text,jsonb)']) f(name)
     WHERE pg_catalog.has_function_privilege(r.role, f.name, 'EXECUTE')
  ) THEN
    RAISE EXCEPTION 'Clinic and notification operations are for the service role only';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(ARRAY['anon', 'authenticated']) r(role)
     CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) p(privilege)
     WHERE pg_catalog.has_table_privilege(r.role, 'public.clinic_membership_audit_events', p.privilege)
  ) OR EXISTS (
    SELECT 1 FROM unnest(ARRAY['UPDATE', 'DELETE', 'TRUNCATE']) p(privilege)
     WHERE pg_catalog.has_table_privilege('service_role', 'public.clinic_membership_audit_events', p.privilege)
  ) OR (SELECT count(*) FROM pg_catalog.pg_trigger
         WHERE tgrelid = 'public.clinic_membership_audit_events'::regclass
           AND tgname IN ('clinic_membership_audit_no_update_or_delete',
                          'clinic_membership_audit_no_truncate')) <> 2 THEN
    RAISE EXCEPTION 'The clinic audit trail must stay append-only and backend-only';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(ARRAY['anon', 'authenticated']) r(role)
     CROSS JOIN unnest(ARRAY['public.clinicians', 'public.clinic_memberships']) t(name)
     CROSS JOIN unnest(ARRAY['INSERT', 'UPDATE', 'DELETE']) p(privilege)
     WHERE pg_catalog.has_table_privilege(r.role, t.name, p.privilege)
  ) THEN
    RAISE EXCEPTION 'Browser roles may not write clinicians or clinic_memberships';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_proc
              WHERE proname = 'clinician_email_invitation_operation'
                AND prosrc ~ 'clinicians\.role|c\.role\s*=') THEN
    RAISE EXCEPTION 'Invitation admin checks must read the membership, not clinicians.role';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_proc
              WHERE proname IN ('notification_row', 'notification_centre_operation')
                AND prosrc ~ 'cl\.id\s*=\s*c\.clinic_id') THEN
    RAISE EXCEPTION 'Notification clinic labels must come from the care-team link''s clinic';
  END IF;
END $$;
