-- Patient-private drafts and explicit confirmation. No library is approved/activated here.
-- Migration 051 already owns the canonical non-null chat session identity.
ALTER TABLE public.symptom_reports ALTER COLUMN severity DROP NOT NULL;
ALTER TABLE public.symptom_reports
  ADD COLUMN confirmation_state text NOT NULL DEFAULT 'legacy_unconfirmed'
    CHECK (confirmation_state IN ('legacy_unconfirmed','patient_confirmed')),
  ADD COLUMN intake_id uuid UNIQUE,
  ADD COLUMN report_schema_version text,
  ADD COLUMN confirmed_by uuid REFERENCES public.patients(id),
  ADD COLUMN confirmed_at timestamptz,
  ADD COLUMN submitted_status text,
  ADD COLUMN confirmed_content jsonb;

CREATE TABLE public.symptom_question_eligibility (
  version text PRIMARY KEY,
  bundle_hash text NOT NULL CHECK (bundle_hash ~ '^[a-f0-9]{64}$'),
  status text NOT NULL CHECK (status IN ('approved','revoked')),
  approval jsonb NOT NULL CHECK (jsonb_typeof(approval)='object'
    AND approval ?& ARRAY['reference','reviewer_identity','reviewer_role','date']),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE public.symptom_intakes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL REFERENCES public.patients(id),
  session_id text NOT NULL CHECK (char_length(session_id) BETWEEN 1 AND 128),
  source_message_id uuid NOT NULL UNIQUE REFERENCES public.chat_messages(id),
  status text NOT NULL DEFAULT 'collecting' CHECK
    (status IN ('collecting','ready_for_confirmation','confirmed','cancelled','interrupted_safety')),
  revision integer NOT NULL DEFAULT 0 CHECK (revision>=0),
  library_version text NOT NULL REFERENCES public.symptom_question_eligibility(version),
  library_hash text NOT NULL,
  locale text NOT NULL CHECK (locale IN ('en-US','es-MX')),
  timezone text NOT NULL,
  timezone_fallback boolean NOT NULL DEFAULT false,
  answers jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(answers)='object' AND octet_length(answers::text)<=30000),
  preview jsonb,
  preview_hash text,
  safety jsonb,
  confirmed_report_id uuid UNIQUE REFERENCES public.symptom_reports(id),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK ((status='confirmed')=(confirmed_report_id IS NOT NULL)),
  CHECK (preview IS NULL OR (jsonb_typeof(preview)='object' AND octet_length(preview::text)<=45000))
);
CREATE UNIQUE INDEX symptom_intakes_active ON public.symptom_intakes(patient_id,session_id)
  WHERE status IN ('collecting','ready_for_confirmation');
ALTER TABLE public.symptom_reports ADD CONSTRAINT symptom_reports_intake_fk
  FOREIGN KEY(intake_id) REFERENCES public.symptom_intakes(id);
CREATE TABLE public.symptom_intake_audit (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  intake_id uuid NOT NULL REFERENCES public.symptom_intakes(id),
  patient_id uuid NOT NULL REFERENCES public.patients(id),
  actor_id uuid,
  action text NOT NULL,
  revision integer NOT NULL,
  evidence jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE public.symptom_intake_mutations (
  intake_id uuid NOT NULL REFERENCES public.symptom_intakes(id),
  mutation_id uuid NOT NULL,
  action text NOT NULL,
  request jsonb NOT NULL,
  PRIMARY KEY(intake_id,mutation_id)
);
ALTER TABLE public.symptom_intakes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.symptom_intake_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.symptom_intake_mutations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.symptom_question_eligibility ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.symptom_intakes, public.symptom_intake_audit,
  public.symptom_intake_mutations, public.symptom_question_eligibility
  FROM PUBLIC, anon, authenticated, service_role;
-- Stored retrieval content is served only after live authorization/source checks.
GRANT SELECT (id,patient_id,session_id,source_message_id,status,revision,library_version,library_hash,
  locale,timezone,timezone_fallback,answers,preview_hash,safety,confirmed_report_id,created_at,updated_at)
  ON public.symptom_intakes TO authenticated;
REVOKE SELECT ON public.symptom_reports FROM PUBLIC,anon,authenticated;
GRANT SELECT (id,patient_id,symptom,severity,onset,duration,related_medication_id,related_medication_name,
  body_area,ai_assessment,flagged_for_adr,notes,created_at,confirmation_state,intake_id,
  report_schema_version,confirmed_by,confirmed_at,submitted_status) ON public.symptom_reports TO authenticated;
CREATE POLICY symptom_intake_owner ON public.symptom_intakes FOR SELECT TO authenticated
  USING (patient_id=auth.uid());
-- Only backend-saved turns can bind a source session. Existing SELECT visibility remains.
REVOKE INSERT,UPDATE,DELETE ON public.chat_messages FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON public.chat_messages TO service_role;
-- Browser report writes and retired backend direct inserts must fail closed.
REVOKE INSERT,UPDATE,DELETE ON public.symptom_reports FROM PUBLIC,anon,authenticated;
REVOKE INSERT,DELETE ON public.symptom_reports FROM service_role;
DROP POLICY IF EXISTS patients_insert_own_symptoms ON public.symptom_reports;
-- Remove any historical INSERT policies, regardless of their deployed name.
DO $$ DECLARE p record; BEGIN
  FOR p IN SELECT policyname FROM pg_catalog.pg_policies WHERE schemaname='public'
    AND tablename='symptom_reports' AND cmd IN ('INSERT','ALL') LOOP
    EXECUTE format('DROP POLICY %I ON public.symptom_reports',p.policyname);
  END LOOP;
END $$;

CREATE FUNCTION private.symptom_intake_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
  RAISE EXCEPTION 'Intake audit is immutable';
END; $$;
CREATE TRIGGER symptom_intake_audit_immutable BEFORE UPDATE OR DELETE
  ON public.symptom_intake_audit FOR EACH ROW EXECUTE FUNCTION private.symptom_intake_immutable();
CREATE TRIGGER symptom_intake_mutation_immutable BEFORE UPDATE OR DELETE
  ON public.symptom_intake_mutations FOR EACH ROW EXECUTE FUNCTION private.symptom_intake_immutable();

CREATE FUNCTION private.symptom_report_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
  IF TG_OP='INSERT' THEN
    IF NEW.confirmation_state<>'patient_confirmed' OR NEW.intake_id IS NULL
      OR NEW.confirmed_by IS DISTINCT FROM NEW.patient_id OR NEW.confirmed_at IS NULL
      OR NEW.report_schema_version IS DISTINCT FROM 'symptom-report/1'
      OR NEW.submitted_status IS DISTINCT FROM 'submitted'
      OR NOT EXISTS (SELECT 1 FROM public.symptom_intakes i WHERE i.id=NEW.intake_id
        AND i.patient_id=NEW.patient_id AND i.status='ready_for_confirmation'
        AND i.preview=NEW.confirmed_content) THEN
      RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Explicit confirmation required';
    END IF;
  ELSIF OLD.confirmation_state='patient_confirmed' THEN
    IF TG_OP='DELETE' OR (to_jsonb(NEW)-'flagged_for_adr') IS DISTINCT FROM
      (to_jsonb(OLD)-'flagged_for_adr') THEN
      RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Confirmed testimony is immutable';
    END IF;
    IF NEW.flagged_for_adr IS DISTINCT FROM OLD.flagged_for_adr THEN
      INSERT INTO public.symptom_intake_audit(intake_id,patient_id,actor_id,action,revision,evidence)
      SELECT id,patient_id,NULL,'adr_candidate_flag',revision,
        jsonb_build_object('flagged_for_adr',NEW.flagged_for_adr,'authority','backend_service')
        FROM public.symptom_intakes WHERE id=OLD.intake_id;
    END IF;
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER symptom_report_confirmation_guard BEFORE INSERT OR UPDATE OR DELETE
  ON public.symptom_reports FOR EACH ROW EXECUTE FUNCTION private.symptom_report_guard();

-- Deployment-only manifest mirror, never called by intake requests. No default entries.
CREATE FUNCTION public.set_symptom_question_eligibility(p_version text,p_hash text,p_status text,p_approval jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
  IF p_version IS NULL OR char_length(p_version) NOT BETWEEN 1 AND 80
    OR p_hash IS NULL OR p_hash !~ '^[a-f0-9]{64}$' OR p_status NOT IN ('approved','revoked')
    OR p_approval IS NULL OR NOT p_approval ?& ARRAY['reference','reviewer_identity','reviewer_role','date']
    OR EXISTS (SELECT 1 FROM jsonb_each_text(p_approval) WHERE value IS NULL OR value='') THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid approval manifest';
  END IF;
  IF EXISTS (SELECT 1 FROM public.symptom_question_eligibility WHERE version=p_version AND (bundle_hash<>p_hash OR approval IS DISTINCT FROM p_approval)) THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Immutable library version';
  END IF;
  INSERT INTO public.symptom_question_eligibility(version,bundle_hash,status,approval)
    VALUES(p_version,p_hash,p_status,p_approval)
    ON CONFLICT(version) DO UPDATE SET status=EXCLUDED.status,approval=EXCLUDED.approval,updated_at=clock_timestamp();
END; $$;

-- Bounded evidence selection also takes row locks so withdrawal cannot race confirmation.
CREATE FUNCTION private.symptom_context(p_patient_id uuid,p_answers jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE med public.medications; fact public.clinical_facts; citation public.evidence_citations;
  provenance public.source_provenances; doc public.documents;
  medications jsonb:='[]'; facts jsonb:='[]'; excerpts jsonb:='[]'; medication_ids uuid[]:=ARRAY[]::uuid[];
BEGIN
  IF p_answers->'product'->>'state'='answered' AND p_answers->'product'->'value'->>'concern'='true' THEN
    FOR med IN SELECT * FROM public.medications WHERE patient_id=p_patient_id AND is_active
      AND name=p_answers->'product'->'value'->>'name' ORDER BY id LIMIT 4 FOR SHARE LOOP
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
CREATE FUNCTION public.symptom_intake_context(p_patient_id uuid,p_intake_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE v public.symptom_intakes;
BEGIN
  SELECT * INTO v FROM public.symptom_intakes WHERE id=p_intake_id AND patient_id=p_patient_id FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Intake unavailable'; END IF;
  RETURN private.symptom_context(p_patient_id,v.answers);
END; $$;
REVOKE ALL ON FUNCTION private.symptom_context(uuid,jsonb) FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.symptom_intake_context(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.symptom_intake_context(uuid,uuid) TO service_role;

CREATE FUNCTION public.symptom_intake_operation(p_patient_id uuid,p_action text,p_payload jsonb DEFAULT '{}')
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
    RETURN CASE WHEN FOUND THEN to_jsonb(v) || jsonb_build_object('database_library_available', EXISTS(SELECT 1 FROM public.symptom_question_eligibility WHERE version=v.library_version AND bundle_hash=v.library_hash AND status='approved')) ELSE 'null'::jsonb END;
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
    IF FOUND THEN RETURN to_jsonb(v) || jsonb_build_object('database_library_available', EXISTS(SELECT 1 FROM public.symptom_question_eligibility WHERE version=v.library_version AND bundle_hash=v.library_hash AND status='approved')); END IF;
    SELECT * INTO eligible FROM public.symptom_question_eligibility WHERE version=p_payload->>'library_version'
      AND bundle_hash=p_payload->>'library_hash' AND status='approved' FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INTAKE_LIBRARY_UNAVAILABLE'; END IF;
    SELECT * INTO STRICT profile FROM public.patients WHERE id=p_patient_id;
    INSERT INTO public.symptom_intakes(patient_id,session_id,source_message_id,library_version,library_hash,locale,timezone,timezone_fallback)
      VALUES(p_patient_id,source.session_id,source.id,eligible.version,eligible.bundle_hash,
        profile.preferred_language::text,CASE WHEN EXISTS(SELECT 1 FROM pg_catalog.pg_timezone_names WHERE name=profile.timezone) THEN profile.timezone ELSE 'UTC' END,
        NOT EXISTS(SELECT 1 FROM pg_catalog.pg_timezone_names WHERE name=profile.timezone))
      RETURNING * INTO v;
    INSERT INTO public.symptom_intake_audit(intake_id,patient_id,actor_id,action,revision,evidence)
      VALUES(v.id,p_patient_id,p_patient_id,'start',0,jsonb_build_object('source_message_id',source.id,'library_hash',v.library_hash));
    RETURN to_jsonb(v) || jsonb_build_object('database_library_available', EXISTS(SELECT 1 FROM public.symptom_question_eligibility WHERE version=v.library_version AND bundle_hash=v.library_hash AND status='approved'));
  END IF;
  SELECT * INTO v FROM public.symptom_intakes WHERE id=(p_payload->>'intake_id')::uuid
    AND patient_id=p_patient_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Intake unavailable'; END IF;
  IF p_action='read' THEN RETURN to_jsonb(v) || jsonb_build_object('database_library_available', EXISTS(SELECT 1 FROM public.symptom_question_eligibility WHERE version=v.library_version AND bundle_hash=v.library_hash AND status='approved')); END IF;
  identity:=COALESCE(p_payload->>'mutation_id',p_payload->>'confirmation_id')::uuid;
  IF p_action IN ('answer','cancel','interrupt','confirm') THEN
    IF identity IS NULL THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Mutation identity required'; END IF;
    SELECT * INTO m FROM public.symptom_intake_mutations WHERE intake_id=v.id AND mutation_id=identity;
    IF FOUND THEN
      IF m.action<>p_action OR m.request<>p_payload THEN
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INTAKE_MUTATION_CONFLICT';
      END IF;
      RETURN to_jsonb(v) || jsonb_build_object('database_library_available', EXISTS(SELECT 1 FROM public.symptom_question_eligibility WHERE version=v.library_version AND bundle_hash=v.library_hash AND status='approved'));
    END IF;
  END IF;
  IF p_action='confirm' AND v.status='confirmed' AND v.preview_hash=p_payload->>'preview_hash'
    AND p_payload->>'consent'='true' THEN
    INSERT INTO public.symptom_intake_mutations VALUES(v.id,identity,p_action,p_payload);
    RETURN to_jsonb(v) || jsonb_build_object('database_library_available', EXISTS(SELECT 1 FROM public.symptom_question_eligibility WHERE version=v.library_version AND bundle_hash=v.library_hash AND status='approved'));
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
    answer:=answer || jsonb_build_object('captured_at',clock_timestamp(),'source_type','patient_form','question_version',v.library_version);
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
  RETURN to_jsonb(v) || jsonb_build_object('database_library_available', EXISTS(SELECT 1 FROM public.symptom_question_eligibility WHERE version=v.library_version AND bundle_hash=v.library_hash AND status='approved'));
EXCEPTION WHEN no_data_found THEN
  RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Intake unavailable';
END; $$;
REVOKE ALL ON FUNCTION private.symptom_intake_immutable(), private.symptom_report_guard() FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.symptom_intake_operation(uuid,text,jsonb),
  public.set_symptom_question_eligibility(text,text,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.symptom_intake_operation(uuid,text,jsonb),
  public.set_symptom_question_eligibility(text,text,text,jsonb) TO service_role;

CREATE TABLE public.symptom_intake_safety_alerts (
  intake_id uuid PRIMARY KEY REFERENCES public.symptom_intakes(id),
  patient_id uuid NOT NULL REFERENCES public.patients(id),
  delivery_state text NOT NULL DEFAULT 'pending' CHECK (delivery_state IN ('pending','delivered','no_recipients')),
  clinicians_notified integer NOT NULL DEFAULT 0 CHECK (clinicians_notified>=0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE public.symptom_intake_safety_alerts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.symptom_intake_safety_alerts FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION private.capture_symptom_intake_safety() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
  IF NEW.status='interrupted_safety' AND OLD.status<>NEW.status THEN
    INSERT INTO public.symptom_intake_safety_alerts(intake_id,patient_id) VALUES(NEW.id,NEW.patient_id)
      ON CONFLICT DO NOTHING;
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER symptom_intake_safety_capture AFTER UPDATE ON public.symptom_intakes
  FOR EACH ROW EXECUTE FUNCTION private.capture_symptom_intake_safety();
CREATE FUNCTION private.guard_symptom_intake_source() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
  IF EXISTS(SELECT 1 FROM public.symptom_intakes WHERE source_message_id=OLD.id) THEN
    RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Intake source is immutable';
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER symptom_intake_source_immutable BEFORE UPDATE OR DELETE ON public.chat_messages
  FOR EACH ROW EXECUTE FUNCTION private.guard_symptom_intake_source();
CREATE FUNCTION public.deliver_symptom_intake_safety_alerts(p_limit integer DEFAULT 25)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE a public.symptom_intake_safety_alerts; t public.care_teams; recipients uuid[]; result jsonb:='[]';
BEGIN
  IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200 THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid batch';
  END IF;
  FOR a IN SELECT * FROM public.symptom_intake_safety_alerts WHERE delivery_state='pending'
    ORDER BY created_at,intake_id LIMIT p_limit FOR UPDATE SKIP LOCKED LOOP
    recipients:=ARRAY[]::uuid[];
    FOR t IN SELECT * FROM public.care_teams WHERE patient_id=a.patient_id AND status='active'
      ORDER BY id FOR SHARE LOOP
      IF NOT t.clinician_id=ANY(recipients) THEN recipients:=array_append(recipients,t.clinician_id); END IF;
    END LOOP;
    INSERT INTO public.clinician_messages(clinician_id,patient_id,channel,subject,body)
      SELECT recipient,a.patient_id,'in_app','Urgent patient chat escalation',
        'Chat escalation flagged (emergency/symptom). Guided intake interrupted. Private answers are not included.'
        FROM unnest(recipients) recipient;
    UPDATE public.symptom_intake_safety_alerts SET
      delivery_state=CASE WHEN cardinality(recipients)>0 THEN 'delivered' ELSE 'no_recipients' END,
      clinicians_notified=cardinality(recipients) WHERE intake_id=a.intake_id;
    result:=result || jsonb_build_array(jsonb_build_object('intake_id',a.intake_id,'clinicians_notified',cardinality(recipients)));
  END LOOP;
  RETURN result;
END; $$;
REVOKE ALL ON FUNCTION private.capture_symptom_intake_safety(),private.guard_symptom_intake_source() FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.deliver_symptom_intake_safety_alerts(integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.deliver_symptom_intake_safety_alerts(integer) TO service_role;

-- New delegated symptom work cannot consume a private draft or forged report payload.
CREATE FUNCTION private.guard_confirmed_symptom_task() RETURNS trigger
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
    NEW.input_payload:=jsonb_set(NEW.input_payload,'{symptom_report}',to_jsonb(report));
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER symptom_task_confirmation_guard BEFORE INSERT OR UPDATE OF status,input_payload ON public.a2a_tasks
  FOR EACH ROW EXECUTE FUNCTION private.guard_confirmed_symptom_task();
REVOKE ALL ON FUNCTION private.guard_confirmed_symptom_task() FROM PUBLIC,anon,authenticated,service_role;
