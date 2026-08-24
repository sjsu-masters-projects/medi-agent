-- Canonical clinical facts are evidence-backed candidates.  They are never
-- approved by insertion: an explicit review transition is required.

CREATE TABLE clinical_facts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  fact_type text NOT NULL CHECK (char_length(fact_type) BETWEEN 1 AND 100),
  subject_type text NOT NULL CHECK (char_length(subject_type) BETWEEN 1 AND 100),
  subject_id uuid,
  value jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence_score numeric(4, 3) CHECK (confidence_score >= 0 AND confidence_score <= 1),
  confidence_band text NOT NULL DEFAULT 'unknown'
    CHECK (confidence_band IN ('unknown', 'low', 'medium', 'high')),
  uncertainty jsonb NOT NULL DEFAULT '[]'::jsonb,
  review_state text NOT NULL DEFAULT 'pending_review'
    CHECK (review_state IN ('pending_review', 'approved', 'rejected', 'deleted')),
  reviewed_by uuid REFERENCES clinicians(id) ON DELETE SET NULL,
  reviewed_at timestamptz,
  review_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (
    (review_state = 'approved' AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)
    OR review_state <> 'approved'
  )
);

CREATE TRIGGER clinical_facts_updated_at
  BEFORE UPDATE ON clinical_facts
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE INDEX idx_clinical_facts_patient_review
  ON clinical_facts(patient_id, review_state, created_at DESC);

CREATE TABLE source_provenances (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  artifact_type text NOT NULL
    CHECK (artifact_type IN ('document', 'fhir_resource', 'patient_report', 'clinician_entry', 'external_record')),
  source_system text NOT NULL CHECK (char_length(source_system) BETWEEN 1 AND 100),
  source_reference text NOT NULL CHECK (char_length(source_reference) BETWEEN 1 AND 500),
  document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
  document_location jsonb NOT NULL DEFAULT '{}'::jsonb,
  extractor_version text,
  model_version text,
  captured_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((artifact_type = 'document' AND document_id IS NOT NULL) OR artifact_type <> 'document')
);

CREATE INDEX idx_source_provenances_document
  ON source_provenances(document_id) WHERE document_id IS NOT NULL;

CREATE TABLE evidence_citations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fact_id uuid NOT NULL REFERENCES clinical_facts(id) ON DELETE CASCADE,
  provenance_id uuid NOT NULL REFERENCES source_provenances(id) ON DELETE RESTRICT,
  excerpt text NOT NULL CHECK (char_length(excerpt) BETWEEN 1 AND 5000),
  location jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_evidence_citations_fact ON evidence_citations(fact_id);
CREATE INDEX idx_evidence_citations_provenance ON evidence_citations(provenance_id);

CREATE TABLE clinical_fact_audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fact_id uuid NOT NULL REFERENCES clinical_facts(id) ON DELETE RESTRICT,
  actor_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
  event_type text NOT NULL
    CHECK (event_type IN ('created', 'corrected', 'approved', 'rejected', 'deleted')),
  event_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_clinical_fact_audit_events_fact
  ON clinical_fact_audit_events(fact_id, created_at ASC);

-- Direct client access is read-only and constrained to the same patient/care-team
-- relationship as the rest of the clinical record.  Mutations go through the
-- backend review service, which records an audit event for every lifecycle change.
ALTER TABLE clinical_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_provenances ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_citations ENABLE ROW LEVEL SECURITY;
ALTER TABLE clinical_fact_audit_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY clinical_facts_patient_approved_select ON clinical_facts
  FOR SELECT USING (patient_id = auth.uid() AND review_state = 'approved');

CREATE POLICY clinical_facts_clinician_select ON clinical_facts
  FOR SELECT USING (is_clinician() AND is_assigned_clinician(patient_id));

CREATE POLICY evidence_citations_patient_approved_select ON evidence_citations
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM clinical_facts
      WHERE clinical_facts.id = evidence_citations.fact_id
        AND clinical_facts.patient_id = auth.uid()
        AND clinical_facts.review_state = 'approved'
    )
  );

CREATE POLICY evidence_citations_clinician_select ON evidence_citations
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM clinical_facts
      WHERE clinical_facts.id = evidence_citations.fact_id
        AND is_clinician()
        AND is_assigned_clinician(clinical_facts.patient_id)
    )
  );

CREATE POLICY source_provenances_patient_approved_select ON source_provenances
  FOR SELECT USING (
    EXISTS (
      SELECT 1
      FROM evidence_citations
      JOIN clinical_facts ON clinical_facts.id = evidence_citations.fact_id
      WHERE evidence_citations.provenance_id = source_provenances.id
        AND clinical_facts.patient_id = auth.uid()
        AND clinical_facts.review_state = 'approved'
    )
  );

CREATE POLICY source_provenances_clinician_select ON source_provenances
  FOR SELECT USING (
    EXISTS (
      SELECT 1
      FROM evidence_citations
      JOIN clinical_facts ON clinical_facts.id = evidence_citations.fact_id
      WHERE evidence_citations.provenance_id = source_provenances.id
        AND is_clinician()
        AND is_assigned_clinician(clinical_facts.patient_id)
    )
  );

CREATE POLICY clinical_fact_audit_events_clinician_select ON clinical_fact_audit_events
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM clinical_facts
      WHERE clinical_facts.id = clinical_fact_audit_events.fact_id
        AND is_clinician()
        AND is_assigned_clinician(clinical_facts.patient_id)
    )
  );
