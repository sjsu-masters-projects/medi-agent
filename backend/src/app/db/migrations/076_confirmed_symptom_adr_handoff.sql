-- Atomically enqueue eligible patient-confirmed product concerns for ADR screening.
-- The application claims and processes the durable task; this trigger only closes the
-- confirmation-to-outbox gap. It never assigns a clinical causality verdict.

CREATE OR REPLACE FUNCTION private.symptom_context(p_patient_id uuid,p_answers jsonb)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE med public.medications; fact public.clinical_facts; citation public.evidence_citations;
  provenance public.source_provenances; doc public.documents;
  medications jsonb:='[]'; facts jsonb:='[]'; excerpts jsonb:='[]'; medication_ids uuid[]:=ARRAY[]::uuid[];
BEGIN
  IF p_answers->'product'->>'state'='answered' AND p_answers->'product'->'value'->>'concern'='true' THEN
    FOR med IN SELECT * FROM public.medications WHERE patient_id=p_patient_id AND is_active
      AND lower(btrim(name))=lower(btrim(p_answers->'product'->'value'->>'name'))
      ORDER BY id LIMIT 4 FOR SHARE LOOP
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

CREATE FUNCTION private.enqueue_confirmed_symptom_adr_task() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE
  product jsonb:=NEW.confirmed_content->'answers'->'product';
  medications jsonb:=NEW.confirmed_content->'context'->'medications';
BEGIN
  IF NEW.confirmation_state='patient_confirmed'
    AND product->>'state'='answered'
    AND product->'value'->'concern'='true'::jsonb
    AND jsonb_typeof(medications)='array'
    AND jsonb_array_length(medications)>0 THEN
    INSERT INTO public.a2a_tasks(
      patient_id,symptom_event_id,idempotency_key,conversation_session_id,
      source_agent,target_agent,task_type,status,input_payload,worker_payload
    ) VALUES (
      NEW.patient_id,NEW.id,'symptom_event:' || NEW.id::text,
      COALESCE(NULLIF(NEW.confirmed_content->>'session_id',''),'default'),
      'symptom','pharmacovigilance','symptom_adr_screen','submitted',
      jsonb_build_object(
        'session_id',COALESCE(NULLIF(NEW.confirmed_content->>'session_id',''),'default'),
        'symptom_report',jsonb_build_object('id',NEW.id)
      ),
      '{}'::jsonb
    ) ON CONFLICT(patient_id,idempotency_key) DO NOTHING;
  END IF;
  RETURN NEW;
END; $$;

CREATE TRIGGER confirmed_symptom_adr_outbox
  AFTER INSERT ON public.symptom_reports
  FOR EACH ROW EXECUTE FUNCTION private.enqueue_confirmed_symptom_adr_task();

REVOKE ALL ON FUNCTION private.enqueue_confirmed_symptom_adr_task()
  FROM PUBLIC,anon,authenticated,service_role;

COMMENT ON FUNCTION private.enqueue_confirmed_symptom_adr_task() IS
  'Atomically creates a report-keyed ADR screening task for a confirmed, active-medication product concern.';
