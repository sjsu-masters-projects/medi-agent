-- SAFE-003: persist all floor rules during intake; keep private answers out of alerts.
-- Additive replacement of 071 routines. Service-only grants and RLS remain unchanged.

ALTER TABLE public.symptom_intake_safety_alerts
  ADD COLUMN alert_kind text NOT NULL DEFAULT 'safety_interrupt'
    CHECK (alert_kind IN ('safety_interrupt','severity_review','medication_error'));
UPDATE public.symptom_intake_safety_alerts SET alert_kind='severity_review' WHERE urgency='urgent';
ALTER TABLE public.symptom_intake_safety_alerts DROP CONSTRAINT symptom_intake_safety_alerts_pkey;
ALTER TABLE public.symptom_intake_safety_alerts ADD PRIMARY KEY(intake_id,urgency,alert_kind);

CREATE OR REPLACE FUNCTION public.symptom_intake_operation(p_patient_id uuid,p_action text,p_payload jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE
  v public.symptom_intakes;
  m public.symptom_intake_mutations;
  source public.chat_messages;
  profile public.patients;
  eligible public.symptom_question_eligibility;
  answer jsonb;
  key text;
  identity uuid;
  report public.symptom_reports;
  current_context jsonb;
  saved_context jsonb;
BEGIN
  IF NOT EXISTS(SELECT 1 FROM public.patients WHERE id=p_patient_id)
    OR p_payload IS NULL OR jsonb_typeof(p_payload)<>'object' OR octet_length(p_payload::text)>60000 THEN
    RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Intake unavailable';
  END IF;
  IF p_action='report' THEN
    SELECT * INTO report FROM public.symptom_reports WHERE id=(p_payload->>'report_id')::uuid
      AND patient_id=p_patient_id AND confirmation_state='patient_confirmed';
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Intake unavailable'; END IF;
    RETURN to_jsonb(report);
  END IF;
  IF p_action='active' THEN
    SELECT * INTO v FROM public.symptom_intakes WHERE patient_id=p_patient_id
      AND session_id=p_payload->>'session_id'
      ORDER BY created_at DESC LIMIT 1;
    RETURN CASE WHEN FOUND THEN to_jsonb(v) || jsonb_build_object('review_requested',EXISTS(SELECT 1 FROM public.symptom_intake_safety_alerts sa WHERE sa.intake_id=v.id AND sa.urgency='urgent'),'database_library_available', EXISTS(SELECT 1 FROM public.symptom_question_eligibility WHERE version=v.library_version AND bundle_hash=v.library_hash AND status='approved')) ELSE 'null'::jsonb END;
  END IF;
  IF p_action='start' THEN
    PERFORM 1 FROM public.patients WHERE id=p_patient_id FOR UPDATE;
    SELECT * INTO STRICT source FROM public.chat_messages WHERE id=(p_payload->>'source_message_id')::uuid FOR SHARE;
    IF source.patient_id<>p_patient_id OR source.role::text<>'user'
      OR source.session_id IS NULL OR source.session_id IS DISTINCT FROM p_payload->>'session_id' THEN
      RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Intake unavailable';
    END IF;
    SELECT * INTO v FROM public.symptom_intakes WHERE patient_id=p_patient_id
      AND (source_message_id=source.id OR (session_id=source.session_id AND status IN ('collecting','ready_for_confirmation')))
      ORDER BY (source_message_id=source.id) DESC LIMIT 1;
    IF FOUND THEN RETURN to_jsonb(v) || jsonb_build_object('review_requested',EXISTS(SELECT 1 FROM public.symptom_intake_safety_alerts sa WHERE sa.intake_id=v.id AND sa.urgency='urgent'),'database_library_available', EXISTS(SELECT 1 FROM public.symptom_question_eligibility WHERE version=v.library_version AND bundle_hash=v.library_hash AND status='approved')); END IF;
    SELECT * INTO eligible FROM public.symptom_question_eligibility WHERE version=p_payload->>'library_version'
      AND bundle_hash=p_payload->>'library_hash' AND status='approved' FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INTAKE_LIBRARY_UNAVAILABLE'; END IF;
    SELECT * INTO STRICT profile FROM public.patients WHERE id=p_patient_id;
    INSERT INTO public.symptom_intakes(patient_id,session_id,source_message_id,library_version,library_hash,locale,timezone,timezone_fallback)
      VALUES(p_patient_id,source.session_id,source.id,eligible.version,eligible.bundle_hash,
        source.language::text,CASE WHEN EXISTS(SELECT 1 FROM pg_catalog.pg_timezone_names WHERE name=profile.timezone) THEN profile.timezone ELSE 'UTC' END,
        NOT EXISTS(SELECT 1 FROM pg_catalog.pg_timezone_names WHERE name=profile.timezone))
      RETURNING * INTO v;
    INSERT INTO public.symptom_intake_audit(intake_id,patient_id,actor_id,action,revision,evidence)
      VALUES(v.id,p_patient_id,p_patient_id,'start',0,jsonb_build_object('source_message_id',source.id,'library_hash',v.library_hash));
    RETURN to_jsonb(v) || jsonb_build_object('review_requested',EXISTS(SELECT 1 FROM public.symptom_intake_safety_alerts sa WHERE sa.intake_id=v.id AND sa.urgency='urgent'),'database_library_available', EXISTS(SELECT 1 FROM public.symptom_question_eligibility WHERE version=v.library_version AND bundle_hash=v.library_hash AND status='approved'));
  END IF;
  SELECT * INTO v FROM public.symptom_intakes WHERE id=(p_payload->>'intake_id')::uuid
    AND patient_id=p_patient_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Intake unavailable'; END IF;
  IF p_action='read' THEN RETURN to_jsonb(v) || jsonb_build_object('review_requested',EXISTS(SELECT 1 FROM public.symptom_intake_safety_alerts sa WHERE sa.intake_id=v.id AND sa.urgency='urgent'),'database_library_available', EXISTS(SELECT 1 FROM public.symptom_question_eligibility WHERE version=v.library_version AND bundle_hash=v.library_hash AND status='approved')); END IF;
  identity:=COALESCE(p_payload->>'mutation_id',p_payload->>'confirmation_id')::uuid;
  IF p_action IN ('answer','cancel','interrupt','confirm') THEN
    IF identity IS NULL THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Mutation identity required'; END IF;
    SELECT * INTO m FROM public.symptom_intake_mutations WHERE intake_id=v.id AND mutation_id=identity;
    IF FOUND THEN
      IF m.action<>p_action OR m.request<>p_payload THEN
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INTAKE_MUTATION_CONFLICT';
      END IF;
      RETURN to_jsonb(v) || jsonb_build_object('review_requested',EXISTS(SELECT 1 FROM public.symptom_intake_safety_alerts sa WHERE sa.intake_id=v.id AND sa.urgency='urgent'),'database_library_available', EXISTS(SELECT 1 FROM public.symptom_question_eligibility WHERE version=v.library_version AND bundle_hash=v.library_hash AND status='approved'));
    END IF;
  END IF;
  IF p_action='confirm' AND v.status='confirmed' AND v.preview_hash=p_payload->>'preview_hash'
    AND p_payload->>'consent'='true' THEN
    INSERT INTO public.symptom_intake_mutations VALUES(v.id,identity,p_action,p_payload);
    RETURN to_jsonb(v) || jsonb_build_object('review_requested',EXISTS(SELECT 1 FROM public.symptom_intake_safety_alerts sa WHERE sa.intake_id=v.id AND sa.urgency='urgent'),'database_library_available', EXISTS(SELECT 1 FROM public.symptom_question_eligibility WHERE version=v.library_version AND bundle_hash=v.library_hash AND status='approved'));
  END IF;
  IF p_action<>'interrupt' AND v.status NOT IN ('collecting','ready_for_confirmation') THEN
    RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INTAKE_TERMINAL';
  END IF;
  IF p_action<>'interrupt' AND (p_payload->>'expected_revision')::integer IS DISTINCT FROM v.revision THEN
    RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INTAKE_REVISION_CONFLICT';
  END IF;
  IF p_action NOT IN ('cancel','interrupt') THEN
    SELECT * INTO eligible FROM public.symptom_question_eligibility WHERE version=v.library_version
      AND bundle_hash=v.library_hash AND status='approved' FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INTAKE_LIBRARY_UNAVAILABLE'; END IF;
  END IF;
  IF p_action IN ('preview','confirm') THEN
    current_context:=private.symptom_context(p_patient_id,v.answers);
    saved_context:=CASE WHEN p_action='preview' THEN p_payload->'preview'->'context' ELSE v.preview->'context' END;
    IF saved_context->>'version' IS DISTINCT FROM 'symptom-context/1'
      OR saved_context->>'purpose' IS DISTINCT FROM 'patient_symptom_preview'
      OR saved_context->'medications' IS DISTINCT FROM current_context->'medications'
      OR saved_context->'facts' IS DISTINCT FROM current_context->'facts'
      OR saved_context->'excerpts' IS DISTINCT FROM current_context->'excerpts' THEN
      RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INTAKE_PREVIEW_STALE';
    END IF;
  END IF;
  IF p_action='answer' THEN
    answer:=p_payload->'answer'; key:=answer->>'question_id';
    IF key NOT IN ('description','location','onset','duration','course','severity','associated','red_flags','product','concomitant','history','outcome')
      OR key IS NULL OR answer->>'state' NOT IN ('answered','unknown','declined')
      OR answer->>'state' IS NULL OR answer->>'locale' IS NULL OR answer->>'locale' NOT IN ('en-US','es-MX')
      OR NOT answer ? 'value' OR char_length(COALESCE(answer->>'wording',''))>1000 THEN
      RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid answer';
    END IF;
    IF answer->>'state' IN ('unknown','declined') AND answer->'value'<>'null'::jsonb THEN
      RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Unresolved value';
    END IF;
    IF key='severity' AND answer->>'state'='answered' AND (jsonb_typeof(answer->'value') IS DISTINCT FROM 'number' OR (answer->>'value') !~ '^(10|[1-9])$') THEN
      RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid patient severity';
    END IF;
    answer:=answer || jsonb_build_object('captured_at',clock_timestamp(),'source_type',CASE answer->>'input_mode' WHEN 'voice' THEN 'patient_voice' WHEN 'typed' THEN 'patient_chat' ELSE 'patient_form' END,'question_version',v.library_version);
    UPDATE public.symptom_intakes SET answers=answers || jsonb_build_object(key,answer),status='collecting',preview=NULL,preview_hash=NULL
      WHERE id=v.id;
  ELSIF p_action='cancel' THEN
    UPDATE public.symptom_intakes SET status='cancelled',preview=NULL,preview_hash=NULL WHERE id=v.id;
  ELSIF p_action='interrupt' THEN
    IF p_payload->'safety'->>'safety_rule' IS NULL OR p_payload->'safety'->>'safety_rule' NOT IN ('emergency_symptom_keyword','emergency_mental_health_keyword','urgent_medication_error')
      OR p_payload->'safety'->>'rule_version' IS DISTINCT FROM 'triage-floor/1' THEN
      RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid safety evidence';
    END IF;
    INSERT INTO public.symptom_intake_safety_alerts(intake_id,patient_id,alert_kind,urgency)
      VALUES(v.id,p_patient_id,CASE WHEN p_payload->'safety'->>'safety_rule'='urgent_medication_error' THEN 'medication_error' ELSE 'safety_interrupt' END,CASE WHEN p_payload->'safety'->>'safety_rule'='urgent_medication_error'
        THEN 'urgent' ELSE 'emergency' END) ON CONFLICT DO NOTHING;
    IF v.status IN ('collecting','ready_for_confirmation') THEN
      UPDATE public.symptom_intakes SET status='interrupted_safety',safety=(p_payload->'safety') || jsonb_build_object('evaluated_at',clock_timestamp()),preview=NULL,preview_hash=NULL WHERE id=v.id;
    ELSE
      UPDATE public.symptom_intakes SET safety=(p_payload->'safety') || jsonb_build_object('evaluated_at',clock_timestamp()) WHERE id=v.id;
    END IF;
  ELSIF p_action='preview' THEN
    IF p_payload->'preview'->>'schema_version' IS DISTINCT FROM 'symptom-report/1'
      OR p_payload->'preview'->'answers' IS DISTINCT FROM v.answers
      OR NOT v.answers ?& ARRAY['description','location','onset','duration','course','severity','associated','red_flags','product','history','outcome']
      OR (v.answers->'product'->'value'->>'concern'='true' AND NOT v.answers ? 'concomitant')
      OR p_payload->'preview'->>'source_message_id' IS DISTINCT FROM v.source_message_id::text
      OR p_payload->'preview'->>'session_id' IS DISTINCT FROM v.session_id
      OR p_payload->'preview'->>'locale' IS DISTINCT FROM v.locale
      OR p_payload->'preview'->>'timezone' IS DISTINCT FROM v.timezone
      OR p_payload->'preview'->>'library_version' IS DISTINCT FROM v.library_version
      OR p_payload->'preview'->>'library_hash' IS DISTINCT FROM v.library_hash
      OR jsonb_array_length(p_payload->'preview'->'context'->'medications')>4
      OR jsonb_array_length(p_payload->'preview'->'context'->'facts')>5
      OR jsonb_array_length(p_payload->'preview'->'context'->'excerpts')>2 THEN
      RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid preview';
    END IF;
    UPDATE public.symptom_intakes SET status='ready_for_confirmation',preview=p_payload->'preview',
      preview_hash=encode(sha256(convert_to((p_payload->'preview')::text,'UTF8')),'hex') WHERE id=v.id;
  ELSIF p_action='confirm' THEN
    IF v.status<>'ready_for_confirmation' OR v.preview_hash IS DISTINCT FROM p_payload->>'preview_hash'
      OR p_payload->>'consent' IS DISTINCT FROM 'true' THEN
      RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INTAKE_PREVIEW_STALE';
    END IF;
    PERFORM 1 FROM public.chat_messages WHERE id=v.source_message_id AND patient_id=p_patient_id
      AND role::text='user' AND session_id=v.session_id FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Intake unavailable'; END IF;
    INSERT INTO public.symptom_reports(patient_id,symptom,severity,onset,duration,body_area,notes,
      confirmation_state,intake_id,report_schema_version,confirmed_by,confirmed_at,submitted_status,confirmed_content)
      VALUES(p_patient_id,CASE WHEN v.answers->'description'->>'state'='answered' THEN left(v.answers->'description'->>'value',300)
        ELSE 'Patient-reported event; description not provided' END,
        CASE WHEN v.answers->'severity'->>'state'='answered' THEN (v.answers->'severity'->>'value')::integer ELSE NULL END,
        CASE WHEN v.answers->'onset'->>'state'='answered' THEN v.answers->'onset'->>'value' END,
        CASE WHEN v.answers->'duration'->>'state'='answered' THEN v.answers->'duration'->>'value' END,
        CASE WHEN v.answers->'location'->>'state'='answered' THEN v.answers->'location'->>'value' END,
        NULL,'patient_confirmed',v.id,'symptom-report/1',p_patient_id,clock_timestamp(),'submitted',v.preview)
      RETURNING * INTO report;
    UPDATE public.symptom_intakes SET status='confirmed',confirmed_report_id=report.id WHERE id=v.id;
  ELSE
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid intake operation';
  END IF;
  UPDATE public.symptom_intakes SET revision=revision+1,updated_at=clock_timestamp() WHERE id=v.id RETURNING * INTO v;
  INSERT INTO public.symptom_intake_audit(intake_id,patient_id,actor_id,action,revision,evidence)
    VALUES(v.id,p_patient_id,p_patient_id,p_action,v.revision,
      CASE WHEN p_action='answer' THEN jsonb_build_object('answer',answer)
      WHEN p_action='preview' THEN jsonb_build_object('preview_hash',v.preview_hash,'preview',v.preview)
      ELSE jsonb_build_object('report_id',v.confirmed_report_id,'safety',v.safety) END);
  IF identity IS NOT NULL THEN
    INSERT INTO public.symptom_intake_mutations VALUES(v.id,identity,p_action,p_payload);
  END IF;
  RETURN to_jsonb(v) || jsonb_build_object('review_requested',EXISTS(SELECT 1 FROM public.symptom_intake_safety_alerts sa WHERE sa.intake_id=v.id AND sa.urgency='urgent'),'database_library_available', EXISTS(SELECT 1 FROM public.symptom_question_eligibility WHERE version=v.library_version AND bundle_hash=v.library_hash AND status='approved'));
EXCEPTION WHEN no_data_found THEN
  RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Intake unavailable';
END; $$;

CREATE OR REPLACE FUNCTION public.deliver_symptom_intake_safety_alerts(p_limit integer DEFAULT 25)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE a public.symptom_intake_safety_alerts; t public.care_teams; recipients uuid[]; result jsonb:='[]';
BEGIN
  IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200 THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid batch';
  END IF;
  FOR a IN SELECT * FROM public.symptom_intake_safety_alerts WHERE delivery_state='pending'
    ORDER BY created_at,intake_id LIMIT p_limit FOR UPDATE SKIP LOCKED LOOP
    recipients:=ARRAY[]::uuid[];
    FOR t IN SELECT team.* FROM public.care_teams team
      JOIN public.clinic_memberships m ON m.clinician_id=team.clinician_id AND m.clinic_id=team.clinic_id
      JOIN public.clinics c ON c.id=team.clinic_id
      WHERE team.patient_id=a.patient_id AND team.status='active' AND m.status='active' AND c.status='active'
      ORDER BY team.id FOR SHARE OF team LOOP
      IF NOT t.clinician_id=ANY(recipients) THEN recipients:=array_append(recipients,t.clinician_id); END IF;
    END LOOP;
    INSERT INTO public.clinician_messages(clinician_id,patient_id,channel,subject,body)
      SELECT recipient,a.patient_id,'in_app',CASE WHEN a.alert_kind='medication_error' THEN 'Same-day review: possible patient medication error' WHEN a.urgency='urgent' THEN 'High-severity symptom answer for review' ELSE 'Urgent patient chat escalation' END,
        CASE WHEN a.alert_kind='medication_error' THEN 'Possible medication error in an unsubmitted symptom draft (urgent). Same-day review is recommended; this is not an emergency alert. Private answers are not included.' WHEN a.urgency='urgent' THEN 'A patient provided a high-severity answer in an unsubmitted symptom draft. Check on the patient. Private answers are not included.' ELSE 'Chat escalation flagged (emergency/symptom). Guided intake interrupted. Private answers are not included.' END
        FROM unnest(recipients) recipient;
    UPDATE public.symptom_intake_safety_alerts SET
      delivery_state=CASE WHEN cardinality(recipients)>0 THEN 'delivered' ELSE 'no_recipients' END,
      clinicians_notified=cardinality(recipients) WHERE intake_id=a.intake_id AND urgency=a.urgency AND alert_kind=a.alert_kind;
    result:=result || jsonb_build_array(jsonb_build_object('intake_id',a.intake_id,'clinicians_notified',cardinality(recipients)));
  END LOOP;
  RETURN result;
END; $$;


CREATE OR REPLACE FUNCTION private.capture_high_severity_intake() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
  IF NEW.answers->'severity'->>'state'='answered'
    AND (NEW.answers->'severity'->>'value')::integer>=8 THEN
    INSERT INTO public.symptom_intake_safety_alerts(intake_id,patient_id,urgency,alert_kind)
      VALUES(NEW.id,NEW.patient_id,'urgent','severity_review') ON CONFLICT DO NOTHING;
  END IF;
  RETURN NEW;
END; $$;

-- The existing status-capture trigger must derive the same key as the RPC. Otherwise
-- entering interrupted_safety would also insert its legacy default emergency alert.
CREATE OR REPLACE FUNCTION private.capture_symptom_intake_safety() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
  IF NEW.status='interrupted_safety' AND OLD.status<>NEW.status THEN
    INSERT INTO public.symptom_intake_safety_alerts(intake_id,patient_id,urgency,alert_kind)
      VALUES(NEW.id,NEW.patient_id,
        CASE WHEN NEW.safety->>'safety_rule'='urgent_medication_error' THEN 'urgent' ELSE 'emergency' END,
        CASE WHEN NEW.safety->>'safety_rule'='urgent_medication_error' THEN 'medication_error' ELSE 'safety_interrupt' END)
      ON CONFLICT DO NOTHING;
  END IF;
  RETURN NEW;
END; $$;
