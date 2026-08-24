-- A generic approval gate for externally visible clinical actions.

CREATE TABLE clinical_recommendations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  action_type text NOT NULL CHECK (char_length(action_type) BETWEEN 1 AND 100),
  proposed_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence jsonb NOT NULL CHECK (jsonb_array_length(evidence) > 0),
  rationale text NOT NULL CHECK (char_length(rationale) BETWEEN 1 AND 5000),
  proposer_type text NOT NULL CHECK (char_length(proposer_type) BETWEEN 1 AND 100),
  proposer_reference text,
  proposed_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  state text NOT NULL DEFAULT 'pending_approval'
    CHECK (state IN ('pending_approval', 'approved', 'rejected', 'executed', 'failed', 'cancelled')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER clinical_recommendations_updated_at
  BEFORE UPDATE ON clinical_recommendations
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TABLE approval_decisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  recommendation_id uuid NOT NULL REFERENCES clinical_recommendations(id) ON DELETE RESTRICT,
  reviewer_id uuid NOT NULL REFERENCES clinicians(id) ON DELETE RESTRICT,
  decision text NOT NULL CHECK (decision IN ('approve', 'reject')),
  note text NOT NULL CHECK (char_length(note) BETWEEN 1 AND 5000),
  edited_payload jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_approval_decisions_one_final_decision
  ON approval_decisions(recommendation_id);

CREATE TABLE action_envelopes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  recommendation_id uuid NOT NULL REFERENCES clinical_recommendations(id) ON DELETE RESTRICT,
  idempotency_key text NOT NULL CHECK (char_length(idempotency_key) BETWEEN 16 AND 255),
  state text NOT NULL DEFAULT 'approved'
    CHECK (state IN ('approved', 'executed', 'failed')),
  outcome jsonb NOT NULL DEFAULT '{}'::jsonb,
  executed_by uuid REFERENCES clinicians(id) ON DELETE SET NULL,
  executed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (recommendation_id, idempotency_key)
);

CREATE TABLE clinical_action_audit_records (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  recommendation_id uuid NOT NULL REFERENCES clinical_recommendations(id) ON DELETE RESTRICT,
  actor_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  event_type text NOT NULL CHECK (char_length(event_type) BETWEEN 1 AND 100),
  event_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_clinical_recommendations_patient_state
  ON clinical_recommendations(patient_id, state, created_at DESC);
CREATE INDEX idx_clinical_action_audits_recommendation
  ON clinical_action_audit_records(recommendation_id, created_at ASC);

ALTER TABLE clinical_recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE action_envelopes ENABLE ROW LEVEL SECURITY;
ALTER TABLE clinical_action_audit_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY clinical_recommendations_assigned_clinician_select ON clinical_recommendations
  FOR SELECT USING (is_clinician() AND is_assigned_clinician(patient_id));
CREATE POLICY approval_decisions_assigned_clinician_select ON approval_decisions
  FOR SELECT USING (
    EXISTS (SELECT 1 FROM clinical_recommendations
      WHERE clinical_recommendations.id = approval_decisions.recommendation_id
        AND is_clinician() AND is_assigned_clinician(clinical_recommendations.patient_id)));
CREATE POLICY action_envelopes_assigned_clinician_select ON action_envelopes
  FOR SELECT USING (
    EXISTS (SELECT 1 FROM clinical_recommendations
      WHERE clinical_recommendations.id = action_envelopes.recommendation_id
        AND is_clinician() AND is_assigned_clinician(clinical_recommendations.patient_id)));
CREATE POLICY clinical_action_audits_assigned_clinician_select ON clinical_action_audit_records
  FOR SELECT USING (
    EXISTS (SELECT 1 FROM clinical_recommendations
      WHERE clinical_recommendations.id = clinical_action_audit_records.recommendation_id
        AND is_clinician() AND is_assigned_clinician(clinical_recommendations.patient_id)));

-- Backend services are the only mutation path; each transition writes an audit record.
