-- EMAIL-001 review fixes on top of 057_email_delivery.sql, which is already in the
-- ledger and must not change. Everything here is additive (ALTER / CREATE OR REPLACE)
-- and keeps every function signature, so the 057 grants still apply.
--
-- * No auth-schema reads. A hosted migration cannot grant service_role access to
--   auth.users, so the backend reads the account address through the Auth Admin API
--   and passes it as p_payload->>'account_email'. It is compared with the verified
--   contact immediately before a send and on invitation acceptance.
-- * Invitation operations take locks in one order: clinic, clinician rows by id,
--   invitation. Invitation history takes no row locks.
-- * New invitations and verification codes return their outbox id so the backend can
--   send that one row at once; the shared worker only retries.
-- * A grouped summary that was stopped is reopened when a new unread item arrives.
-- * Provider status is polled for at most 72 hours; complaints are recorded and
--   withdraw optional-notice consent rather than being reported as bounces.
-- * Verification challenges are capped per contact per day; consent is stamped only
--   when optional notices go from off to on; one-time codes and invitation links leave
--   the outbox once they can no longer be used.

ALTER TABLE public.email_contacts
  ADD COLUMN challenge_window_start timestamptz,
  ADD COLUMN challenge_count integer NOT NULL DEFAULT 0;
ALTER TABLE public.email_outbox
  ADD COLUMN generation integer NOT NULL DEFAULT 0,
  ADD COLUMN accepted_at timestamptz,
  ADD COLUMN status_checked_at timestamptz,
  ADD COLUMN complained_at timestamptz;
DROP INDEX IF EXISTS public.email_outbox_accepted;
CREATE INDEX email_outbox_status_poll ON public.email_outbox(accepted_at,id)
  WHERE state IN ('accepted','delivered') AND complained_at IS NULL;

CREATE OR REPLACE FUNCTION private.email_capture() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE e public.notification_events; c public.email_contacts; k text; group_key text;
BEGIN
 SELECT * INTO e FROM public.notification_events WHERE id=NEW.event_id;
 k:=private.email_preference(e.event_type);
 SELECT * INTO c FROM public.email_contacts WHERE user_id=NEW.recipient_id;
 IF k IS NULL OR c.verified_at IS NULL OR c.consent_at IS NULL OR e.created_at<c.consent_at
   OR c.preferences->k IS DISTINCT FROM 'true'::jsonb THEN RETURN NEW; END IF;
 -- Compact unread-message summaries per addressed thread/15 minute window;
 -- shared review reminders per category/hour. Other saved transitions remain distinct.
 group_key:=CASE WHEN k='messages' THEN coalesce(e.metadata->>'conversation_id',e.source_id::text)||'/'||floor(extract(epoch FROM e.created_at)/900)::text
   WHEN k='reviews' THEN e.category||'/'||floor(extract(epoch FROM e.created_at)/3600)::text
   ELSE e.id::text END;
 -- An unsent summary follows the newest item. A summary that was stopped (its item was
 -- read or became unavailable, or retries ran out) is reopened as a new generation with
 -- a fresh provider idempotency key. Accepted or delivered summaries stay sent.
 INSERT INTO public.email_outbox(user_id,receipt_id,kind,dedupe_key,available_at)
 VALUES(NEW.recipient_id,NEW.id,'notice',NEW.recipient_id::text||'/'||k||'/'||group_key,
   clock_timestamp()+CASE WHEN k IN ('messages','reviews') THEN interval '5 minutes' ELSE interval '0' END)
 ON CONFLICT(dedupe_key) DO UPDATE SET receipt_id=EXCLUDED.receipt_id,
   state='queued',
   payload=NULL,
   generation=email_outbox.generation+CASE WHEN email_outbox.state IN ('suppressed','failed') THEN 1 ELSE 0 END,
   attempts=CASE WHEN email_outbox.state IN ('suppressed','failed') THEN 0 ELSE email_outbox.attempts END,
   created_at=CASE WHEN email_outbox.state IN ('suppressed','failed') THEN clock_timestamp() ELSE email_outbox.created_at END,
   available_at=CASE WHEN email_outbox.state IN ('suppressed','failed') THEN EXCLUDED.available_at ELSE email_outbox.available_at END,
   lease=NULL,leased_until=NULL,provider_id=NULL,updated_at=clock_timestamp()
   WHERE (email_outbox.state='queued' AND email_outbox.payload IS NULL)
     OR email_outbox.state IN ('suppressed','failed');
 RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.email_account_operation(p_actor_id uuid,p_role text,p_action text,p_payload jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c public.email_contacts; address text:=lower(nullif(btrim(p_payload->>'account_email'),''));
  v_valid boolean; v_outbox uuid; v_preferences jsonb; v_any boolean; v_fresh_window boolean;
BEGIN
 IF NOT ((p_role='patient' AND EXISTS(SELECT 1 FROM public.patients WHERE id=p_actor_id))
   OR (p_role='clinician' AND EXISTS(SELECT 1 FROM public.clinicians WHERE id=p_actor_id))) THEN
   RAISE EXCEPTION 'Email preferences unavailable' USING ERRCODE='42501',HINT='email_unavailable'; END IF;
 -- The backend supplies the current Auth address; nothing here reads the auth schema.
 IF address IS NULL OR position('@' IN address)<2 THEN
   RAISE EXCEPTION 'Email unavailable' USING ERRCODE='42501',HINT='email_unavailable'; END IF;
 INSERT INTO public.email_contacts(user_id,role,email) VALUES(p_actor_id,p_role,address) ON CONFLICT DO NOTHING;
 SELECT * INTO c FROM public.email_contacts WHERE user_id=p_actor_id FOR UPDATE;
 IF c.email<>address THEN
   UPDATE public.email_contacts SET email=address,verified_at=NULL,preferences='{}',consent_at=NULL,
     challenge_hash=NULL,challenge_expires_at=NULL WHERE user_id=p_actor_id;
   UPDATE public.email_outbox SET state='suppressed',payload=NULL,updated_at=clock_timestamp()
    WHERE user_id=p_actor_id AND state='queued';
   SELECT * INTO c FROM public.email_contacts WHERE user_id=p_actor_id;
 END IF;
 IF p_action='challenge' THEN
   IF address LIKE '%@accounts.mediagent.live' THEN RETURN jsonb_build_object('status','synthetic'); END IF;
   IF c.challenge_sent_at>clock_timestamp()-interval '60 seconds' THEN RETURN jsonb_build_object('status','wait'); END IF;
   v_fresh_window:=c.challenge_window_start IS NULL OR c.challenge_window_start<=clock_timestamp()-interval '24 hours';
   IF NOT v_fresh_window AND c.challenge_count>=5 THEN RETURN jsonb_build_object('status','limit'); END IF;
   UPDATE public.email_contacts SET challenge_hash=p_payload->>'hash',challenge_expires_at=clock_timestamp()+interval '10 minutes',
     challenge_attempts=0,challenge_sent_at=clock_timestamp(),
     challenge_window_start=CASE WHEN v_fresh_window THEN clock_timestamp() ELSE challenge_window_start END,
     challenge_count=CASE WHEN v_fresh_window THEN 1 ELSE challenge_count+1 END
    WHERE user_id=p_actor_id;
   -- Only the newest code may be delivered.
   UPDATE public.email_outbox SET state='suppressed',payload=NULL,updated_at=clock_timestamp()
    WHERE user_id=p_actor_id AND kind='verification' AND state='queued';
   INSERT INTO public.email_outbox(user_id,kind,dedupe_key,payload)
    VALUES(p_actor_id,'verification',p_payload->>'key',p_payload->'payload') RETURNING id INTO v_outbox;
   RETURN jsonb_build_object('status','queued','outbox_id',v_outbox);
 ELSIF p_action='verify' THEN
   v_valid:=c.challenge_hash IS NOT NULL AND c.challenge_expires_at>clock_timestamp() AND c.challenge_attempts<5
     AND c.challenge_hash=p_payload->>'hash';
   UPDATE public.email_contacts SET challenge_attempts=challenge_attempts+1,
     verified_at=CASE WHEN v_valid THEN clock_timestamp() ELSE verified_at END,
     challenge_hash=CASE WHEN v_valid THEN NULL ELSE challenge_hash END WHERE user_id=p_actor_id;
   IF v_valid THEN
     UPDATE public.email_outbox SET state='suppressed',payload=NULL,updated_at=clock_timestamp()
      WHERE user_id=p_actor_id AND kind='verification' AND state='queued';
   END IF;
   RETURN jsonb_build_object('verified',v_valid);
 ELSIF p_action='preferences' THEN
   IF c.verified_at IS NULL THEN RAISE EXCEPTION 'Verify your email first' USING ERRCODE='22023',HINT='verify_first'; END IF;
   v_preferences:=p_payload-'account_email';
   IF EXISTS(SELECT 1 FROM jsonb_each(v_preferences) x WHERE x.key NOT IN ('messages','appointments','care_plans','records','reviews')
     OR jsonb_typeof(x.value)<>'boolean') THEN
     RAISE EXCEPTION 'Invalid preferences' USING ERRCODE='22023',HINT='invalid_preferences'; END IF;
   IF p_role='patient' AND v_preferences->'reviews'='true'::jsonb THEN
     RAISE EXCEPTION 'Clinician only preference' USING ERRCODE='22023',HINT='clinician_only'; END IF;
   v_any:=EXISTS(SELECT 1 FROM jsonb_each(v_preferences) x WHERE x.value='true'::jsonb);
   -- Consent starts when optional notices go from off to on, not on every save.
   UPDATE public.email_contacts SET preferences=v_preferences,
     consent_at=CASE WHEN v_any THEN coalesce(consent_at,clock_timestamp()) END WHERE user_id=p_actor_id;
 ELSIF p_action<>'get' THEN RAISE EXCEPTION 'Invalid operation' USING ERRCODE='22023',HINT='invalid_operation'; END IF;
 SELECT * INTO c FROM public.email_contacts WHERE user_id=p_actor_id;
 RETURN jsonb_build_object('email',c.email,'verified',c.verified_at IS NOT NULL,'synthetic',c.email LIKE '%@accounts.mediagent.live','preferences',c.preferences);
END;
$$;

CREATE OR REPLACE FUNCTION private.email_eligible(o public.email_outbox) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c public.email_contacts; r public.notification_receipts; e public.notification_events;
BEGIN
 IF o.kind='invitation' THEN
  RETURN EXISTS(SELECT 1 FROM public.clinician_email_invitations i
   JOIN public.clinics cl ON cl.id=i.clinic_id JOIN public.clinicians a ON a.id=i.invited_by
   WHERE i.id=o.invitation_id AND i.accepted_at IS NULL AND i.revoked_at IS NULL
    AND i.expires_at>clock_timestamp() AND cl.status='active' AND a.role='admin' AND a.clinic_id=i.clinic_id);
 END IF;
 -- The current Auth address is compared at freeze time, immediately before sending.
 SELECT * INTO c FROM public.email_contacts WHERE user_id=o.user_id;
 IF NOT FOUND OR c.email LIKE '%@accounts.mediagent.live' THEN RETURN false; END IF;
 IF o.kind='verification' THEN
   RETURN c.challenge_hash IS NOT NULL AND c.challenge_sent_at<=o.created_at AND c.challenge_expires_at>clock_timestamp(); END IF;
 SELECT * INTO r FROM public.notification_receipts WHERE id=o.receipt_id;
 SELECT * INTO e FROM public.notification_events WHERE id=r.event_id;
 IF private.email_preference(e.event_type)='reviews' THEN
  -- The representative item may have been reviewed while another item in the
  -- same summary remains pending. Check every authorized item in that bucket.
  RETURN c.verified_at IS NOT NULL AND c.preferences->'reviews'='true'::jsonb AND EXISTS(
   SELECT 1 FROM public.notification_receipts r2 JOIN public.notification_events e2 ON e2.id=r2.event_id
   WHERE r2.recipient_id=o.user_id AND r2.read_at IS NULL AND r2.acknowledged_at IS NULL
    AND private.email_preference(e2.event_type)='reviews' AND e2.category=e.category
    AND floor(extract(epoch FROM e2.created_at)/3600)=floor(extract(epoch FROM e.created_at)/3600)
    AND e2.created_at>=c.consent_at AND private.notification_authorized(e2,o.user_id,c.role)
    AND private.notification_actionable(e2,c.role));
 END IF;
 RETURN c.verified_at IS NOT NULL AND c.preferences->private.email_preference(e.event_type)='true'::jsonb
   AND r.read_at IS NULL AND r.acknowledged_at IS NULL
   AND private.notification_authorized(e,o.user_id,c.role)
   AND (e.event_type IN ('appointment_changed','appointment_response') OR private.notification_actionable(e,c.role));
END;
$$;

CREATE OR REPLACE FUNCTION public.email_delivery_operation(p_action text,p_payload jsonb DEFAULT '{}') RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE o public.email_outbox; rows jsonb:='[]'; c public.email_contacts; e public.notification_events;
  v_one uuid:=nullif(p_payload->>'id','')::uuid; v_kinds text[]; v_state text;
BEGIN
 IF p_action='claim' THEN
  -- Optional kinds let the worker skip mail whose sender is not configured.
  v_kinds:=CASE WHEN jsonb_typeof(p_payload->'kinds')='array'
    THEN ARRAY(SELECT jsonb_array_elements_text(p_payload->'kinds'))
    ELSE ARRAY['verification','notice','invitation'] END;
  -- A single-row claim sends a just-created code or invitation at once. Only the
  -- shared worker materializes receipts for opted-in accounts whose portals are closed.
  IF v_one IS NULL THEN
   FOR c IN SELECT * FROM public.email_contacts WHERE verified_at IS NOT NULL
     AND consent_at IS NOT NULL AND EXISTS(SELECT 1 FROM jsonb_each(preferences) x WHERE x.value='true'::jsonb)
     ORDER BY user_id LOOP
    PERFORM private.notification_prepare(c.user_id,c.role);
   END LOOP;
  END IF;
  FOR o IN SELECT * FROM public.email_outbox WHERE kind=ANY(v_kinds)
    AND ((v_one IS NULL AND state IN ('queued','sending') AND available_at<=clock_timestamp())
      OR (id=v_one AND state='queued'))
    AND (leased_until IS NULL OR leased_until<clock_timestamp()) ORDER BY available_at,id LIMIT 25 FOR UPDATE SKIP LOCKED LOOP
   -- Stop before Resend's 24-hour idempotency retention expires. Ambiguous sends
   -- are left for operator reconciliation, never retried after that boundary.
   IF o.created_at<clock_timestamp()-interval '23 hours' OR o.attempts>=5 THEN
     UPDATE public.email_outbox SET state='failed',payload=NULL,updated_at=clock_timestamp() WHERE id=o.id; CONTINUE; END IF;
   IF NOT coalesce(private.email_eligible(o),false) THEN
     UPDATE public.email_outbox SET state='suppressed',payload=NULL,updated_at=clock_timestamp() WHERE id=o.id; CONTINUE; END IF;
   UPDATE public.email_outbox SET state='sending',lease=gen_random_uuid(),leased_until=clock_timestamp()+interval '2 minutes',
     attempts=attempts+1,updated_at=clock_timestamp() WHERE id=o.id RETURNING * INTO o;
   SELECT * INTO c FROM public.email_contacts WHERE user_id=o.user_id;
   SELECT ev.* INTO e FROM public.notification_events ev JOIN public.notification_receipts r ON r.event_id=ev.id WHERE r.id=o.receipt_id;
   rows:=rows||jsonb_build_array(to_jsonb(o)||jsonb_build_object('email',c.email,'role',c.role,
     'locale',CASE WHEN c.role='patient' THEN (SELECT preferred_language::text FROM public.patients WHERE id=c.user_id) ELSE 'en-US' END,'event',to_jsonb(e)));
  END LOOP;
  RETURN jsonb_build_object('items',rows);
 ELSIF p_action='freeze' THEN
  SELECT * INTO o FROM public.email_outbox WHERE id=v_one AND lease=(p_payload->>'lease')::uuid AND state='sending' FOR UPDATE;
  IF NOT FOUND THEN RETURN '{}'::jsonb; END IF;
  IF o.user_id IS NOT NULL THEN
   SELECT * INTO c FROM public.email_contacts WHERE user_id=o.user_id;
   -- A changed or missing Auth address stops this send; the next account read resets
   -- verification and consent for the new address.
   IF lower(coalesce(p_payload->>'account_email','')) IS DISTINCT FROM c.email THEN
    UPDATE public.email_outbox SET state='suppressed',payload=NULL,leased_until=NULL,updated_at=clock_timestamp() WHERE id=o.id;
    RETURN '{}'::jsonb;
   END IF;
  END IF;
  IF NOT coalesce(private.email_eligible(o),false) THEN
   UPDATE public.email_outbox SET state='suppressed',payload=NULL,leased_until=NULL,updated_at=clock_timestamp() WHERE id=o.id;
   RETURN '{}'::jsonb;
  END IF;
  IF o.payload IS NULL AND (p_payload->'payload' IS NULL OR p_payload->'payload'='null'::jsonb) THEN
   UPDATE public.email_outbox SET state='failed',leased_until=NULL,updated_at=clock_timestamp() WHERE id=o.id;
   RETURN '{}'::jsonb;
  END IF;
  UPDATE public.email_outbox SET payload=coalesce(payload,nullif(p_payload->'payload','null'::jsonb)) WHERE id=o.id RETURNING payload INTO rows;
  RETURN jsonb_build_object('payload',rows);
 ELSIF p_action='finish' THEN
  -- Provider acceptance clears the frozen body, including any one-time code or link.
  UPDATE public.email_outbox SET state=CASE WHEN nullif(p_payload->>'provider_id','') IS NULL THEN 'queued' ELSE 'accepted' END,
   provider_id=nullif(p_payload->>'provider_id',''),
   accepted_at=CASE WHEN nullif(p_payload->>'provider_id','') IS NULL THEN NULL ELSE clock_timestamp() END,
   available_at=clock_timestamp()+interval '5 minutes',leased_until=NULL,
   updated_at=clock_timestamp(),payload=CASE WHEN nullif(p_payload->>'provider_id','') IS NULL THEN payload ELSE NULL END
   WHERE id=v_one AND lease=(p_payload->>'lease')::uuid AND state='sending' RETURNING state INTO v_state;
  RETURN jsonb_build_object('state',v_state);
 ELSIF p_action='accepted' THEN
  -- Poll provider status for 72 hours: unconfirmed sends every five minutes, delivered
  -- optional notices every six hours for complaints. Older rows keep their last state.
  SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'provider_id',provider_id)),'[]') INTO rows
   FROM (SELECT id,provider_id FROM public.email_outbox
     WHERE state IN ('accepted','delivered') AND complained_at IS NULL AND provider_id IS NOT NULL
      AND accepted_at>clock_timestamp()-interval '72 hours'
      AND ((state='accepted' AND coalesce(status_checked_at,accepted_at)<clock_timestamp()-interval '5 minutes')
        OR (state='delivered' AND kind='notice' AND coalesce(status_checked_at,accepted_at)<clock_timestamp()-interval '6 hours'))
     ORDER BY coalesce(status_checked_at,accepted_at),id LIMIT 25) s;
  RETURN jsonb_build_object('items',rows);
 ELSIF p_action='status' THEN
  v_state:=p_payload->>'state';
  IF v_state IS NULL OR v_state NOT IN ('accepted','delivered','bounced','failed','complained') THEN
   RAISE EXCEPTION 'Invalid delivery status' USING ERRCODE='22023',HINT='invalid_operation'; END IF;
  -- A complaint is recorded on a delivered message; it is not a bounce. Delivery is
  -- never downgraded by a later poll.
  UPDATE public.email_outbox SET
    state=CASE WHEN v_state='complained' OR email_outbox.state='delivered' THEN 'delivered' ELSE v_state END,
    complained_at=CASE WHEN v_state='complained' THEN coalesce(complained_at,clock_timestamp()) ELSE complained_at END,
    status_checked_at=clock_timestamp(),updated_at=clock_timestamp()
   WHERE id=v_one AND provider_id=p_payload->>'provider_id' AND state IN ('accepted','delivered')
   RETURNING * INTO o;
  -- A spam complaint withdraws optional-notice consent. Account access is unaffected.
  IF FOUND AND v_state='complained' AND o.user_id IS NOT NULL AND o.kind='notice' THEN
   UPDATE public.email_contacts SET preferences='{}',consent_at=NULL WHERE user_id=o.user_id;
  END IF;
  RETURN '{}';
 ELSIF p_action='pending' THEN
  -- Read-only counts for a dry run.
  RETURN jsonb_build_object(
   'due',(SELECT count(*) FROM public.email_outbox WHERE state IN ('queued','sending') AND available_at<=clock_timestamp()
     AND (leased_until IS NULL OR leased_until<clock_timestamp())),
   'awaiting_status',(SELECT count(*) FROM public.email_outbox WHERE state='accepted'
     AND accepted_at>clock_timestamp()-interval '72 hours'));
 END IF;
 RAISE EXCEPTION 'Invalid operation' USING ERRCODE='22023',HINT='invalid_operation';
END;
$$;

CREATE OR REPLACE FUNCTION public.clinician_email_invitation_operation(p_actor uuid,p_action text,p_payload jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE a public.clinicians; i public.clinician_email_invitations; cl public.clinics; v_id uuid; v_outbox uuid;
  v_clinic uuid; v_email text; v_account text:=lower(nullif(btrim(p_payload->>'account_email'),''));
BEGIN
 -- Lock order for every operation: clinic, then clinician rows by id, then invitation.
 IF p_action IN ('create','list','revoke') THEN
  SELECT clinic_id INTO v_clinic FROM public.clinicians WHERE id=p_actor AND role='admin';
  IF v_clinic IS NULL THEN RAISE EXCEPTION 'Admin required' USING ERRCODE='42501',HINT='admin_required'; END IF;
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
  IF NOT FOUND OR a.role<>'admin' OR a.clinic_id IS DISTINCT FROM cl.id THEN
   RAISE EXCEPTION 'Admin required' USING ERRCODE='42501',HINT='admin_required'; END IF;
  IF p_action='revoke' THEN
   UPDATE public.clinician_email_invitations SET revoked_at=coalesce(revoked_at,clock_timestamp())
    WHERE id=(p_payload->>'id')::uuid AND clinic_id=cl.id AND accepted_at IS NULL RETURNING id INTO v_id;
   IF v_id IS NULL THEN RAISE EXCEPTION 'Invitation unavailable' USING ERRCODE='42501',HINT='invitation_unavailable'; END IF;
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
  IF EXISTS(SELECT 1 FROM public.clinicians WHERE lower(email)=v_email AND clinic_id IS NOT NULL) THEN
   RAISE EXCEPTION 'Existing membership must not be changed by invitation' USING ERRCODE='22023',HINT='existing_membership'; END IF;
  SELECT * INTO i FROM public.clinician_email_invitations WHERE clinic_id=cl.id AND email=v_email
    AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at>clock_timestamp()
    ORDER BY created_at DESC LIMIT 1 FOR UPDATE;
  IF FOUND THEN
   IF EXISTS(SELECT 1 FROM public.email_outbox WHERE invitation_id=i.id AND state IN ('queued','sending','accepted','delivered')) THEN
    RETURN jsonb_build_object('status','already_pending','email_sent',false);
   END IF;
   -- The earlier link's delivery stopped (failed, bounced or suppressed). Replace it.
   UPDATE public.clinician_email_invitations SET revoked_at=clock_timestamp() WHERE id=i.id;
  END IF;
  INSERT INTO public.clinician_email_invitations(clinic_id,invited_by,email,role,token_hash)
   VALUES(cl.id,p_actor,v_email,(p_payload->>'role')::public.clinician_role_enum,p_payload->>'hash') RETURNING * INTO i;
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
  IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM public.clinicians WHERE id=i.invited_by AND role='admin' AND clinic_id=i.clinic_id) THEN
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
 IF i.accepted_by=p_actor AND i.accepted_at IS NOT NULL AND a.clinic_id=i.clinic_id AND v_account=i.email THEN
  RETURN jsonb_build_object('status','accepted','clinic_id',cl.id,'clinic_code',cl.code,'clinic_name',cl.display_name,'clinic_status',cl.status);
 END IF;
 IF i.accepted_at IS NOT NULL OR i.revoked_at IS NOT NULL OR i.expires_at<=clock_timestamp() THEN
  RAISE EXCEPTION 'Invitation invalid or expired' USING ERRCODE='22023',HINT='invitation_invalid'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.clinicians WHERE id=i.invited_by AND role='admin' AND clinic_id=i.clinic_id) THEN
  RAISE EXCEPTION 'Invitation unavailable' USING ERRCODE='42501',HINT='invitation_unavailable'; END IF;
 IF a.id IS NULL OR v_account IS DISTINCT FROM i.email THEN
  RAISE EXCEPTION 'Invitation not for this account' USING ERRCODE='42501',HINT='invitation_wrong_account'; END IF;
 IF a.clinic_id IS NOT NULL AND a.clinic_id<>i.clinic_id THEN
  RAISE EXCEPTION 'Existing membership must not be changed by invitation' USING ERRCODE='42501',HINT='existing_membership'; END IF;
 UPDATE public.clinicians SET clinic_id=i.clinic_id,clinic_name=cl.display_name,role=i.role WHERE id=p_actor;
 UPDATE public.clinician_email_invitations SET accepted_by=p_actor,accepted_at=clock_timestamp() WHERE id=i.id;
 UPDATE public.email_outbox SET state='suppressed',payload=NULL,updated_at=clock_timestamp()
  WHERE invitation_id=i.id AND state='queued';
 -- Possession of the addressed invitation proves ownership; optional notices stay off.
 INSERT INTO public.email_contacts(user_id,role,email,verified_at) VALUES(p_actor,'clinician',i.email,clock_timestamp())
  ON CONFLICT(user_id) DO UPDATE SET email=EXCLUDED.email,verified_at=EXCLUDED.verified_at,preferences='{}',consent_at=NULL;
 RETURN jsonb_build_object('status','accepted','clinic_id',cl.id,'clinic_code',cl.code,'clinic_name',cl.display_name,'clinic_status',cl.status);
END;
$$;

REVOKE ALL ON FUNCTION private.email_capture(),private.email_eligible(public.email_outbox),
 public.email_account_operation(uuid,text,text,jsonb),public.email_delivery_operation(text,jsonb),
 public.clinician_email_invitation_operation(uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION private.email_capture(),private.email_eligible(public.email_outbox),
 public.email_account_operation(uuid,text,text,jsonb),public.email_delivery_operation(text,jsonb),
 public.clinician_email_invitation_operation(uuid,text,jsonb) TO service_role;

-- 057 attempted to grant service_role read access to auth.users. Nothing reads the auth
-- schema any more. Remove that grant where this role made it; elsewhere this is a no-op.
DO $$
BEGIN
 REVOKE SELECT ON auth.users FROM service_role;
EXCEPTION WHEN insufficient_privilege THEN
 RAISE NOTICE 'auth.users grant cleanup skipped';
END;
$$;
