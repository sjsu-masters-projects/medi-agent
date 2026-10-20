-- Additive intake review closure. Applied 059/060 files remain immutable.
-- Source locale and input provenance change only for newly captured answers/intakes.
ALTER TABLE public.symptom_intake_safety_alerts ADD COLUMN urgency text NOT NULL DEFAULT 'emergency' CHECK (urgency IN ('urgent','emergency'));
ALTER TABLE public.symptom_intake_safety_alerts DROP CONSTRAINT symptom_intake_safety_alerts_pkey;
ALTER TABLE public.symptom_intake_safety_alerts ADD PRIMARY KEY (intake_id,urgency);
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
    IF p_payload->'safety'->>'safety_rule' IS NULL OR p_payload->'safety'->>'safety_rule' NOT IN ('emergency_symptom_keyword','emergency_mental_health_keyword')
      OR p_payload->'safety'->>'rule_version' IS DISTINCT FROM 'triage-floor/1' THEN
      RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid safety evidence';
    END IF;
    INSERT INTO public.symptom_intake_safety_alerts(intake_id,patient_id) VALUES(v.id,p_patient_id) ON CONFLICT DO NOTHING;
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

-- Only an exact, unique active-list match supplies a medication FK. Unlisted
-- products stay patient-reported and never mutate approved medication truth.
CREATE FUNCTION private.map_confirmed_symptom_product() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE product jsonb; matches uuid[];
BEGIN
  IF NEW.confirmation_state='patient_confirmed' THEN
    product:=NEW.confirmed_content->'answers'->'product';
    IF product->>'state'='answered' AND product->'value'->>'concern'='true' THEN
      NEW.related_medication_name:=product->'value'->>'name';
      SELECT array_agg(m.id ORDER BY m.id) INTO matches FROM public.medications m
        WHERE m.patient_id=NEW.patient_id AND m.is_active
          AND lower(btrim(m.name))=lower(btrim(NEW.related_medication_name));
      NEW.related_medication_id:=CASE WHEN cardinality(matches)=1 THEN matches[1] END;
      NEW.flagged_for_adr:=NEW.related_medication_id IS NOT NULL;
    END IF;
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER symptom_report_candidate_mapping BEFORE INSERT ON public.symptom_reports
  FOR EACH ROW EXECUTE FUNCTION private.map_confirmed_symptom_product();

-- Enqueue in the confirmation transaction. A process crash, lost response or
-- failed worker cannot lose the handoff; existing retry polling drives it.
CREATE FUNCTION private.enqueue_confirmed_symptom_review() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE report public.symptom_reports; recipient record;
BEGIN
  IF NEW.status='confirmed' AND OLD.status IS DISTINCT FROM 'confirmed' THEN
    SELECT * INTO STRICT report FROM public.symptom_reports WHERE id=NEW.confirmed_report_id
      AND patient_id=NEW.patient_id AND confirmation_state='patient_confirmed';
    INSERT INTO public.a2a_tasks(patient_id,symptom_event_id,idempotency_key,conversation_session_id,
      source_agent,target_agent,task_type,status,input_payload,worker_payload,next_retry_at)
      VALUES(NEW.patient_id,report.id,'confirmed_symptom:'||report.id::text,NEW.session_id,
        'symptom','pharmacovigilance','symptom_adr_screen','retrying',
        jsonb_build_object('session_id',NEW.session_id,'symptom_report',jsonb_build_object('id',report.id)),
        '{}',clock_timestamp()) ON CONFLICT(patient_id,idempotency_key) DO NOTHING;
    FOR recipient IN SELECT DISTINCT t.clinician_id FROM public.care_teams t
      JOIN public.clinic_memberships m ON m.clinician_id=t.clinician_id AND m.clinic_id=t.clinic_id
      JOIN public.clinics c ON c.id=t.clinic_id
      WHERE t.patient_id=NEW.patient_id AND t.status='active' AND m.status='active' AND c.status='active'
    LOOP
      INSERT INTO public.clinician_messages(clinician_id,patient_id,channel,subject,body)
        VALUES(recipient.clinician_id,NEW.patient_id,'in_app',
          CASE WHEN report.severity>=8 THEN 'High-severity patient-confirmed symptom' ELSE 'Patient-confirmed symptom for review' END,
          'Patient confirmed: '||report.symptom||'. Severity: '||coalesce(report.severity::text||'/10','unknown')||
          '. Review the confirmed summary and patient-reported products. A cause has not been established.');
    END LOOP;
    INSERT INTO public.symptom_intake_audit(intake_id,patient_id,actor_id,action,revision,evidence)
      VALUES(NEW.id,NEW.patient_id,NEW.patient_id,'review_handoff',NEW.revision,
        jsonb_build_object('report_id',report.id,'task_key','confirmed_symptom:'||report.id::text));
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER symptom_intake_confirmed_handoff AFTER UPDATE OF status ON public.symptom_intakes
  FOR EACH ROW EXECUTE FUNCTION private.enqueue_confirmed_symptom_review();

-- The screen consumes only canonical testimony. Neither a browser-supplied
-- causality answer nor cached retrieval context can enter the worker payload.
CREATE OR REPLACE FUNCTION private.guard_confirmed_symptom_task() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE report public.symptom_reports;
BEGIN
  IF NEW.task_type='symptom_adr_screen' AND (TG_OP='INSERT' OR NEW.status='working' OR NEW.input_payload IS DISTINCT FROM OLD.input_payload) THEN
    SELECT * INTO report FROM public.symptom_reports r
      WHERE r.id=(NEW.input_payload->'symptom_report'->>'id')::uuid AND r.patient_id=NEW.patient_id
        AND r.confirmation_state='patient_confirmed' FOR SHARE;
    IF NOT FOUND OR (NEW.symptom_event_id IS NOT NULL AND NEW.symptom_event_id IS DISTINCT FROM report.id) THEN
      RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Confirmed symptom report required';
    END IF;
    NEW.input_payload:=jsonb_build_object('session_id',report.confirmed_content->>'session_id',
      'symptom_report',to_jsonb(report)||jsonb_build_object('confirmed_content',report.confirmed_content-'context'),
      'naranjo_answers','{}'::jsonb,'adr_evidence','[]'::jsonb);
  END IF;
  RETURN NEW;
END; $$;
REVOKE ALL ON FUNCTION private.map_confirmed_symptom_product(),private.enqueue_confirmed_symptom_review()
  FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.symptom_intake_operation(uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.symptom_intake_operation(uuid,text,jsonb) TO service_role;

-- Apply the same exact case-insensitive name matching to bounded preview context.
CREATE OR REPLACE FUNCTION private.symptom_context(p_patient_id uuid,p_answers jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE med public.medications; fact public.clinical_facts; citation public.evidence_citations;
  provenance public.source_provenances; doc public.documents;
  medications jsonb:='[]'; facts jsonb:='[]'; excerpts jsonb:='[]'; medication_ids uuid[]:=ARRAY[]::uuid[];
BEGIN
  IF p_answers->'product'->>'state'='answered' AND p_answers->'product'->'value'->>'concern'='true' THEN
    FOR med IN SELECT * FROM public.medications WHERE patient_id=p_patient_id AND is_active
      AND lower(btrim(name))=lower(btrim(p_answers->'product'->'value'->>'name')) ORDER BY id LIMIT 4 FOR SHARE LOOP
      medication_ids:=array_append(medication_ids,med.id);
      medications:=medications || jsonb_build_array(jsonb_build_object('source_id',med.id,'name',med.name,
        'dose',med.dosage,'frequency',med.frequency,'source_version',med.created_at,'approval_state','canonical_active'));
    END LOOP;
    FOR fact IN SELECT * FROM public.clinical_facts WHERE patient_id=p_patient_id
      AND subject_type='medication' AND subject_id=ANY(medication_ids) AND review_state='approved'
      AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL AND octet_length(value::text)<=1000
      ORDER BY id LIMIT 5 FOR SHARE LOOP
      SELECT e.* INTO citation FROM public.evidence_citations e JOIN public.source_provenances p ON p.id=e.provenance_id
        WHERE e.fact_id=fact.id AND (p.artifact_type='clinician_entry' OR (p.artifact_type='document'
          AND EXISTS(SELECT 1 FROM public.documents d WHERE d.id=p.document_id AND d.patient_id=p_patient_id
            AND d.visibility='all_providers' AND d.parse_status='completed'
            AND ((d.uploaded_by_role='clinician' AND d.review_status IS DISTINCT FROM 'rejected') OR d.review_status='approved'))))
        ORDER BY e.id LIMIT 1 FOR SHARE OF e,p;
      IF NOT FOUND THEN CONTINUE; END IF;
      SELECT * INTO STRICT provenance FROM public.source_provenances WHERE id=citation.provenance_id FOR SHARE;
      IF provenance.artifact_type='document' THEN
        SELECT * INTO doc FROM public.documents WHERE id=provenance.document_id AND patient_id=p_patient_id
          AND visibility='all_providers' AND parse_status='completed'
          AND ((uploaded_by_role='clinician' AND review_status IS DISTINCT FROM 'rejected') OR review_status='approved') FOR SHARE;
        IF NOT FOUND THEN CONTINUE; END IF;
      END IF;
      facts:=facts || jsonb_build_array(jsonb_build_object('source_id',fact.id,'fact_type',fact.fact_type,
        'value',fact.value,'source_version',fact.updated_at,'approval_state',fact.review_state,
        'reviewed_by',fact.reviewed_by,'reviewed_at',fact.reviewed_at,'citation_id',citation.id,
        'provenance_id',provenance.id,'document_id',provenance.document_id,'source_reference',provenance.source_reference,
        'provenance_version',provenance.captured_at,
        'document_version',CASE WHEN provenance.artifact_type='document' THEN doc.created_at END,
        'document_reviewed_at',CASE WHEN provenance.artifact_type='document' THEN doc.reviewed_at END));
      IF jsonb_array_length(excerpts)<2 THEN
        excerpts:=excerpts || jsonb_build_array(jsonb_build_object('citation_id',citation.id,'fact_id',fact.id,
          'provenance_id',provenance.id,'document_id',provenance.document_id,'source_reference',provenance.source_reference,
          'location',citation.location,'text',left(citation.excerpt,500),'source_version',citation.created_at));
      END IF;
    END LOOP;
  END IF;
  RETURN jsonb_build_object('version','symptom-context/1','purpose','patient_symptom_preview','retrieved_at',clock_timestamp(),
    'medications',medications,'facts',facts,'excerpts',excerpts,
    'limits',jsonb_build_object('medications',4,'facts',5,'excerpts',2,'excerpt_characters',500));
END; $$;

-- Existing >=8 high-severity review threshold is independent of report consent.
-- Urgent and emergency rows have separate identities so one cannot suppress the other.
CREATE FUNCTION private.capture_high_severity_intake() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
  IF NEW.answers->'severity'->>'state'='answered'
    AND (NEW.answers->'severity'->>'value')::integer>=8 THEN
    INSERT INTO public.symptom_intake_safety_alerts(intake_id,patient_id,urgency)
      VALUES(NEW.id,NEW.patient_id,'urgent') ON CONFLICT DO NOTHING;
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER symptom_intake_high_severity AFTER UPDATE OF answers ON public.symptom_intakes
  FOR EACH ROW EXECUTE FUNCTION private.capture_high_severity_intake();
REVOKE ALL ON FUNCTION private.capture_high_severity_intake() FROM PUBLIC,anon,authenticated,service_role;
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
      SELECT recipient,a.patient_id,'in_app',CASE WHEN a.urgency='urgent' THEN 'High-severity symptom answer for review' ELSE 'Urgent patient chat escalation' END,
        CASE WHEN a.urgency='urgent' THEN 'A patient provided a high-severity answer in an unsubmitted symptom draft. Check on the patient. Private answers are not included.' ELSE 'Chat escalation flagged (emergency/symptom). Guided intake interrupted. Private answers are not included.' END
        FROM unnest(recipients) recipient;
    UPDATE public.symptom_intake_safety_alerts SET
      delivery_state=CASE WHEN cardinality(recipients)>0 THEN 'delivered' ELSE 'no_recipients' END,
      clinicians_notified=cardinality(recipients) WHERE intake_id=a.intake_id AND urgency=a.urgency;
    result:=result || jsonb_build_array(jsonb_build_object('intake_id',a.intake_id,'clinicians_notified',cardinality(recipients)));
  END LOOP;
  RETURN result;
END; $$;

REVOKE INSERT,UPDATE,DELETE ON public.a2a_tasks FROM PUBLIC,anon,authenticated;

-- Read-only deployment probe, not a browser-configurable approval mechanism.
CREATE FUNCTION public.symptom_intake_readiness(p_version text,p_hash text,p_approval jsonb)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
  SELECT jsonb_build_object(
    'eligibility_matches',EXISTS(SELECT 1 FROM public.symptom_question_eligibility
      WHERE version=p_version AND bundle_hash=p_hash AND approval=p_approval AND status='approved'),
    'browser_report_writes_denied',NOT pg_catalog.has_any_column_privilege('authenticated','public.symptom_reports','INSERT,UPDATE')
      AND NOT pg_catalog.has_table_privilege('authenticated','public.symptom_reports','DELETE'),
    'browser_task_writes_denied',NOT pg_catalog.has_table_privilege('authenticated','public.a2a_tasks','INSERT,UPDATE,DELETE'),
    'handoff_trigger_present',EXISTS(SELECT 1 FROM pg_catalog.pg_trigger
      WHERE tgrelid='public.symptom_intakes'::regclass AND tgname='symptom_intake_confirmed_handoff' AND tgenabled<>'D')
  );
$$;
REVOKE ALL ON FUNCTION public.symptom_intake_readiness(text,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.symptom_intake_readiness(text,text,jsonb) TO service_role;
