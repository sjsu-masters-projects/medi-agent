-- EMAIL-001. Scaffold generated with Supabase CLI, named for the repository ledger.
-- New sends only; no backfill or historical notice replay. Browser writes are forbidden.
-- An addressed invite may create an account before membership is explicitly
-- accepted. NULL is unassigned; never put an invented clinic into authorization.
ALTER TABLE public.clinicians ALTER COLUMN clinic_name DROP NOT NULL;
CREATE TABLE public.email_contacts (
  user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN ('patient','clinician')),
  email text NOT NULL,
  verified_at timestamptz,
  preferences jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(preferences)='object'),
  consent_at timestamptz,
  challenge_hash text,
  challenge_expires_at timestamptz,
  challenge_attempts integer NOT NULL DEFAULT 0,
  challenge_sent_at timestamptz
);
CREATE TABLE public.clinician_email_invitations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  clinic_id uuid NOT NULL REFERENCES public.clinics(id) ON DELETE CASCADE,
  invited_by uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  email text NOT NULL,
  role public.clinician_role_enum NOT NULL,
  token_hash text NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL DEFAULT clock_timestamp()+interval '7 days',
  accepted_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  accepted_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX clinician_email_invites_clinic ON public.clinician_email_invitations(clinic_id,created_at);
CREATE INDEX clinician_email_invites_inviter ON public.clinician_email_invitations(invited_by);
CREATE INDEX clinician_email_invites_accepted ON public.clinician_email_invitations(accepted_by);
CREATE TABLE public.email_outbox (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
  invitation_id uuid REFERENCES public.clinician_email_invitations(id) ON DELETE CASCADE,
  receipt_id uuid REFERENCES public.notification_receipts(id) ON DELETE CASCADE,
  kind text NOT NULL CHECK(kind IN ('verification','notice','invitation')),
  dedupe_key text NOT NULL UNIQUE,
  state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','sending','accepted','delivered','bounced','failed','suppressed')),
  payload jsonb CHECK(payload IS NULL OR jsonb_typeof(payload)='object'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  attempts integer NOT NULL DEFAULT 0,
  lease uuid,
  leased_until timestamptz,
  provider_id text,
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX email_outbox_user ON public.email_outbox(user_id,created_at);
CREATE INDEX email_outbox_receipt ON public.email_outbox(receipt_id);
CREATE INDEX email_outbox_invitation ON public.email_outbox(invitation_id);
CREATE INDEX email_outbox_due ON public.email_outbox(available_at,id) WHERE state IN ('queued','sending');
CREATE INDEX email_outbox_accepted ON public.email_outbox(updated_at,id) WHERE state='accepted';
ALTER TABLE public.email_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.email_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.clinician_email_invitations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.clinician_email_invitations FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT,UPDATE ON public.clinician_email_invitations TO service_role;
REVOKE ALL ON public.email_contacts,public.email_outbox FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT,UPDATE ON public.email_contacts,public.email_outbox TO service_role;
GRANT SELECT ON auth.users TO service_role;
GRANT USAGE ON SCHEMA auth TO service_role;

CREATE FUNCTION private.email_preference(p_type text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path='' AS $$
SELECT CASE WHEN p_type='message_received' THEN 'messages'
 WHEN p_type IN ('appointment_offered','appointment_changed','appointment_response') THEN 'appointments'
 WHEN p_type='care_plan_published' THEN 'care_plans'
 WHEN p_type IN ('document_failed','adr_information_requested') THEN 'records'
 WHEN p_type IN ('document_review','care_plan_draft') THEN 'reviews' END;
$$;

CREATE FUNCTION private.email_capture() RETURNS trigger
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
 INSERT INTO public.email_outbox(user_id,receipt_id,kind,dedupe_key,available_at)
 VALUES(NEW.recipient_id,NEW.id,'notice',NEW.recipient_id::text||'/'||k||'/'||group_key,
   clock_timestamp()+CASE WHEN k IN ('messages','reviews') THEN interval '5 minutes' ELSE interval '0' END)
 ON CONFLICT(dedupe_key) DO UPDATE SET receipt_id=EXCLUDED.receipt_id
   WHERE email_outbox.state='queued' AND email_outbox.payload IS NULL;
 RETURN NEW;
END;
$$;
CREATE TRIGGER email_notice_capture AFTER INSERT ON public.notification_receipts
 FOR EACH ROW EXECUTE FUNCTION private.email_capture();

CREATE FUNCTION public.email_account_operation(p_actor_id uuid,p_role text,p_action text,p_payload jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c public.email_contacts; address text; v_valid boolean;
BEGIN
 IF NOT ((p_role='patient' AND EXISTS(SELECT 1 FROM public.patients WHERE id=p_actor_id))
   OR (p_role='clinician' AND EXISTS(SELECT 1 FROM public.clinicians WHERE id=p_actor_id))) THEN
   RAISE EXCEPTION 'Email preferences unavailable' USING ERRCODE='42501'; END IF;
 SELECT lower(email) INTO address FROM auth.users WHERE id=p_actor_id;
 IF address IS NULL THEN RAISE EXCEPTION 'Email unavailable' USING ERRCODE='42501'; END IF;
 INSERT INTO public.email_contacts(user_id,role,email) VALUES(p_actor_id,p_role,address) ON CONFLICT DO NOTHING;
 SELECT * INTO c FROM public.email_contacts WHERE user_id=p_actor_id FOR UPDATE;
 IF c.email<>address THEN
   UPDATE public.email_contacts SET email=address,verified_at=NULL,preferences='{}',consent_at=NULL,
     challenge_hash=NULL,challenge_expires_at=NULL WHERE user_id=p_actor_id;
   SELECT * INTO c FROM public.email_contacts WHERE user_id=p_actor_id;
 END IF;
 IF p_action='challenge' THEN
   IF address LIKE '%@accounts.mediagent.live' THEN RETURN jsonb_build_object('status','synthetic'); END IF;
   IF c.challenge_sent_at>clock_timestamp()-interval '60 seconds' THEN RETURN jsonb_build_object('status','wait'); END IF;
   UPDATE public.email_contacts SET challenge_hash=p_payload->>'hash',challenge_expires_at=clock_timestamp()+interval '10 minutes',
     challenge_attempts=0,challenge_sent_at=clock_timestamp() WHERE user_id=p_actor_id;
   INSERT INTO public.email_outbox(user_id,kind,dedupe_key,payload)
    VALUES(p_actor_id,'verification',p_payload->>'key',p_payload->'payload');
   RETURN jsonb_build_object('status','queued');
 ELSIF p_action='verify' THEN
   v_valid:=c.challenge_hash IS NOT NULL AND c.challenge_expires_at>clock_timestamp() AND c.challenge_attempts<5
     AND c.challenge_hash=p_payload->>'hash';
   UPDATE public.email_contacts SET challenge_attempts=challenge_attempts+1,
     verified_at=CASE WHEN v_valid THEN clock_timestamp() ELSE verified_at END,
     challenge_hash=CASE WHEN v_valid THEN NULL ELSE challenge_hash END WHERE user_id=p_actor_id;
   RETURN jsonb_build_object('verified',v_valid);
 ELSIF p_action='preferences' THEN
   IF c.verified_at IS NULL THEN RAISE EXCEPTION 'Verify your email first' USING ERRCODE='22023'; END IF;
   IF EXISTS(SELECT 1 FROM jsonb_each(p_payload) x WHERE x.key NOT IN ('messages','appointments','care_plans','records','reviews')
     OR jsonb_typeof(x.value)<>'boolean') THEN RAISE EXCEPTION 'Invalid preferences' USING ERRCODE='22023'; END IF;
   IF p_role='patient' AND p_payload->'reviews'='true'::jsonb THEN RAISE EXCEPTION 'Clinician only preference' USING ERRCODE='22023'; END IF;
   UPDATE public.email_contacts SET preferences=p_payload,consent_at=clock_timestamp() WHERE user_id=p_actor_id;
 ELSIF p_action<>'get' THEN RAISE EXCEPTION 'Invalid operation' USING ERRCODE='22023'; END IF;
 SELECT * INTO c FROM public.email_contacts WHERE user_id=p_actor_id;
 RETURN jsonb_build_object('email',c.email,'verified',c.verified_at IS NOT NULL,'synthetic',c.email LIKE '%@accounts.mediagent.live','preferences',c.preferences);
END;
$$;

CREATE FUNCTION private.email_eligible(o public.email_outbox) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c public.email_contacts; r public.notification_receipts; e public.notification_events;
BEGIN
 IF o.kind='invitation' THEN
  RETURN EXISTS(SELECT 1 FROM public.clinician_email_invitations i
   JOIN public.clinics cl ON cl.id=i.clinic_id JOIN public.clinicians a ON a.id=i.invited_by
   WHERE i.id=o.invitation_id AND i.accepted_at IS NULL AND i.revoked_at IS NULL
    AND i.expires_at>clock_timestamp() AND cl.status='active' AND a.role='admin' AND a.clinic_id=i.clinic_id);
 END IF;
 SELECT * INTO c FROM public.email_contacts WHERE user_id=o.user_id;
 IF NOT EXISTS(SELECT 1 FROM auth.users WHERE id=o.user_id AND lower(email)=c.email)
   OR c.email LIKE '%@accounts.mediagent.live' THEN RETURN false; END IF;
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

CREATE FUNCTION public.email_delivery_operation(p_action text,p_payload jsonb DEFAULT '{}') RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE o public.email_outbox; rows jsonb:='[]'; c public.email_contacts; e public.notification_events;
BEGIN
 IF p_action='claim' THEN
  -- Materialize recipient receipts for opted-in accounts even while their
  -- portals are closed. Email must not depend on opening the in-app inbox.
  FOR c IN SELECT * FROM public.email_contacts WHERE verified_at IS NOT NULL
    AND consent_at IS NOT NULL AND EXISTS(SELECT 1 FROM jsonb_each(preferences) x WHERE x.value='true'::jsonb)
    ORDER BY user_id LOOP
   PERFORM private.notification_prepare(c.user_id,c.role);
  END LOOP;
  FOR o IN SELECT * FROM public.email_outbox WHERE state IN ('queued','sending') AND available_at<=clock_timestamp()
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
  SELECT * INTO o FROM public.email_outbox WHERE id=(p_payload->>'id')::uuid AND lease=(p_payload->>'lease')::uuid AND state='sending' FOR UPDATE;
  IF NOT FOUND OR NOT coalesce(private.email_eligible(o),false) THEN RETURN '{}'::jsonb; END IF;
  IF o.payload IS NULL AND (p_payload->'payload' IS NULL OR p_payload->'payload'='null'::jsonb) THEN
   UPDATE public.email_outbox SET state='failed',updated_at=clock_timestamp() WHERE id=o.id;
   RETURN '{}'::jsonb;
  END IF;
  UPDATE public.email_outbox SET payload=coalesce(payload,nullif(p_payload->'payload','null'::jsonb)) WHERE id=o.id RETURNING payload INTO rows;
  RETURN jsonb_build_object('payload',rows);
 ELSIF p_action='finish' THEN
  UPDATE public.email_outbox SET state=CASE WHEN nullif(p_payload->>'provider_id','') IS NULL THEN 'queued' ELSE 'accepted' END,
   provider_id=nullif(p_payload->>'provider_id',''),available_at=clock_timestamp()+interval '5 minutes',leased_until=NULL,
   updated_at=clock_timestamp(),payload=CASE WHEN nullif(p_payload->>'provider_id','') IS NULL THEN payload ELSE NULL END
   WHERE id=(p_payload->>'id')::uuid AND lease=(p_payload->>'lease')::uuid AND state='sending';
  RETURN '{}';
 ELSIF p_action='accepted' THEN
  SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'provider_id',provider_id)),'[]') INTO rows
   FROM (SELECT id,provider_id FROM public.email_outbox WHERE state='accepted' AND updated_at<clock_timestamp()-interval '5 minutes' ORDER BY updated_at LIMIT 25) s;
  RETURN jsonb_build_object('items',rows);
 ELSIF p_action='status' THEN
  IF p_payload->>'state' NOT IN ('accepted','delivered','bounced','failed') THEN RAISE EXCEPTION 'Invalid delivery status'; END IF;
  UPDATE public.email_outbox SET state=p_payload->>'state',updated_at=clock_timestamp()
   WHERE id=(p_payload->>'id')::uuid AND provider_id=p_payload->>'provider_id' AND state='accepted';
  RETURN '{}';
 END IF;
 RAISE EXCEPTION 'Invalid operation' USING ERRCODE='22023';
END;
$$;
REVOKE ALL ON FUNCTION private.email_preference(text),private.email_capture(),private.email_eligible(public.email_outbox),
 public.email_account_operation(uuid,text,text,jsonb),public.email_delivery_operation(text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION private.email_preference(text),private.email_capture(),private.email_eligible(public.email_outbox),
 public.email_account_operation(uuid,text,text,jsonb),public.email_delivery_operation(text,jsonb) TO service_role;

CREATE FUNCTION public.clinician_email_invitation_operation(p_actor uuid,p_action text,p_payload jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE a public.clinicians; i public.clinician_email_invitations; cl public.clinics; v_id uuid;
BEGIN
 IF p_action IN ('create','list','revoke') THEN
  SELECT * INTO a FROM public.clinicians WHERE id=p_actor FOR UPDATE;
  IF NOT FOUND OR a.role<>'admin' OR a.clinic_id IS NULL THEN RAISE EXCEPTION 'Admin required' USING ERRCODE='42501'; END IF;
  -- Serialize invitation creation across different admins of the same clinic.
  SELECT * INTO cl FROM public.clinics WHERE id=a.clinic_id AND status='active' FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Clinic unavailable' USING ERRCODE='42501'; END IF;
  IF p_action='list' THEN
   RETURN jsonb_build_object('items',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',s.id,'email',s.email,'role',s.role,
      'expires_at',s.expires_at,'accepted_at',s.accepted_at,'revoked_at',s.revoked_at,
      'delivery_state',(SELECT state FROM public.email_outbox WHERE invitation_id=s.id LIMIT 1)) ORDER BY s.created_at DESC),'[]')
     FROM (SELECT * FROM public.clinician_email_invitations WHERE clinic_id=cl.id ORDER BY created_at DESC LIMIT 50) s));
  ELSIF p_action='revoke' THEN
   UPDATE public.clinician_email_invitations SET revoked_at=clock_timestamp() WHERE id=(p_payload->>'id')::uuid
    AND clinic_id=cl.id AND accepted_at IS NULL RETURNING id INTO v_id;
   IF v_id IS NULL THEN RAISE EXCEPTION 'Invitation unavailable' USING ERRCODE='42501'; END IF;
   RETURN jsonb_build_object('status','revoked');
  END IF;
  IF p_payload->>'email' LIKE '%@accounts.mediagent.live' THEN RAISE EXCEPTION 'Undeliverable demo address' USING ERRCODE='22023'; END IF;
  IF EXISTS(SELECT 1 FROM public.clinicians WHERE lower(email)=lower(p_payload->>'email') AND clinic_id IS NOT NULL) THEN
   RAISE EXCEPTION 'Existing membership must not be changed by invitation' USING ERRCODE='22023'; END IF;
  IF EXISTS(SELECT 1 FROM public.clinician_email_invitations WHERE clinic_id=cl.id AND email=lower(p_payload->>'email')
      AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at>clock_timestamp()) THEN
   RETURN jsonb_build_object('status','already_pending','email_sent',false); END IF;
  INSERT INTO public.clinician_email_invitations(clinic_id,invited_by,email,role,token_hash)
   VALUES(cl.id,p_actor,lower(p_payload->>'email'),(p_payload->>'role')::public.clinician_role_enum,p_payload->>'hash') RETURNING * INTO i;
  INSERT INTO public.email_outbox(invitation_id,kind,dedupe_key,payload)
   VALUES(i.id,'invitation','invitation/'||i.id::text,p_payload->'payload');
  RETURN jsonb_build_object('status','queued','email_sent',false,'invitation_id',i.id);
 END IF;
 SELECT * INTO i FROM public.clinician_email_invitations WHERE token_hash=p_payload->>'hash' FOR UPDATE;
 IF FOUND AND p_action='accept' AND i.accepted_by=p_actor AND i.accepted_at IS NOT NULL
   AND EXISTS(SELECT 1 FROM public.clinicians WHERE id=p_actor AND clinic_id=i.clinic_id)
   AND EXISTS(SELECT 1 FROM auth.users WHERE id=p_actor AND lower(email)=i.email) THEN
   RETURN jsonb_build_object('status','accepted');
 END IF;
 IF NOT FOUND OR i.accepted_at IS NOT NULL OR i.revoked_at IS NOT NULL OR i.expires_at<=clock_timestamp() THEN
   RAISE EXCEPTION 'Invitation invalid or expired' USING ERRCODE='22023'; END IF;
 SELECT * INTO cl FROM public.clinics WHERE id=i.clinic_id AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Invitation unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.clinicians WHERE id=i.invited_by AND role='admin' AND clinic_id=i.clinic_id FOR SHARE;
 IF NOT FOUND THEN
   RAISE EXCEPTION 'Invitation unavailable' USING ERRCODE='42501'; END IF;
 IF p_action='preview' THEN
  RETURN jsonb_build_object('email',i.email,'role',i.role,'clinic_id',cl.id,'clinic_name',cl.display_name,'clinic_code',cl.code,'status','active');
 ELSIF p_action='accept' THEN
  SELECT * INTO a FROM public.clinicians WHERE id=p_actor FOR UPDATE;
  IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM auth.users WHERE id=p_actor AND lower(email)=i.email)
    OR (a.clinic_id IS NOT NULL AND a.clinic_id<>i.clinic_id) THEN RAISE EXCEPTION 'Invitation not for this account' USING ERRCODE='42501'; END IF;
  UPDATE public.clinicians SET clinic_id=i.clinic_id,clinic_name=cl.display_name,role=i.role WHERE id=p_actor;
  UPDATE public.clinician_email_invitations SET accepted_by=p_actor,accepted_at=clock_timestamp() WHERE id=i.id;
  -- Possession of the addressed invitation proves ownership; optional notices stay off.
  INSERT INTO public.email_contacts(user_id,role,email,verified_at) VALUES(p_actor,'clinician',i.email,clock_timestamp())
   ON CONFLICT(user_id) DO UPDATE SET email=EXCLUDED.email,verified_at=EXCLUDED.verified_at,preferences='{}',consent_at=NULL;
  RETURN jsonb_build_object('status','accepted');
 END IF;
 RAISE EXCEPTION 'Invalid invitation operation' USING ERRCODE='22023';
END;
$$;
REVOKE ALL ON FUNCTION public.clinician_email_invitation_operation(uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.clinician_email_invitation_operation(uuid,text,jsonb) TO service_role;
