-- SMART launch state and raw FHIR import envelopes.  All imported content is
-- synthetic-demo data and must pass through the clinical-fact review gate.

CREATE TABLE smart_launch_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  state_hash text NOT NULL UNIQUE,
  pkce_verifier_ciphertext text NOT NULL,
  issuer text NOT NULL,
  authorization_endpoint text NOT NULL,
  token_endpoint text NOT NULL,
  launch_context text,
  clinician_id uuid NOT NULL REFERENCES clinicians(id) ON DELETE CASCADE,
  patient_id uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  requested_scopes text NOT NULL,
  nonce text NOT NULL,
  expires_at timestamptz NOT NULL,
  consumed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_smart_launch_sessions_state_expiry
  ON smart_launch_sessions(state_hash, expires_at) WHERE consumed_at IS NULL;

CREATE TABLE fhir_imports (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  launch_session_id uuid REFERENCES smart_launch_sessions(id) ON DELETE SET NULL,
  clinician_id uuid NOT NULL REFERENCES clinicians(id) ON DELETE RESTRICT,
  patient_id uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  issuer text NOT NULL,
  external_patient_id text,
  external_encounter_id text,
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'importing', 'completed', 'completed_with_warnings', 'failed')),
  resource_count integer NOT NULL DEFAULT 0 CHECK (resource_count >= 0),
  candidate_fact_count integer NOT NULL DEFAULT 0 CHECK (candidate_fact_count >= 0),
  warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  failure_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE INDEX idx_fhir_imports_patient_created
  ON fhir_imports(patient_id, created_at DESC);
CREATE INDEX idx_fhir_imports_clinician_created
  ON fhir_imports(clinician_id, created_at DESC);

CREATE TABLE fhir_import_resources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  import_id uuid NOT NULL REFERENCES fhir_imports(id) ON DELETE CASCADE,
  issuer text NOT NULL,
  resource_type text NOT NULL,
  external_resource_id text,
  version_id text,
  dedupe_key text NOT NULL UNIQUE,
  content_hash text NOT NULL,
  raw_resource jsonb NOT NULL,
  validation_errors jsonb NOT NULL DEFAULT '[]'::jsonb,
  mapping_warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_fhir_import_resources_import ON fhir_import_resources(import_id);
CREATE INDEX idx_fhir_import_resources_source
  ON fhir_import_resources(issuer, resource_type, external_resource_id);

CREATE TABLE smart_portal_handoffs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_hash text NOT NULL UNIQUE,
  import_id uuid NOT NULL REFERENCES fhir_imports(id) ON DELETE CASCADE,
  clinician_id uuid NOT NULL REFERENCES clinicians(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL,
  consumed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_smart_portal_handoffs_ticket_expiry
  ON smart_portal_handoffs(ticket_hash, expires_at) WHERE consumed_at IS NULL;

ALTER TABLE smart_launch_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE fhir_imports ENABLE ROW LEVEL SECURITY;
ALTER TABLE fhir_import_resources ENABLE ROW LEVEL SECURITY;
ALTER TABLE smart_portal_handoffs ENABLE ROW LEVEL SECURITY;

CREATE POLICY fhir_imports_clinician_select ON fhir_imports
  FOR SELECT USING (is_clinician() AND clinician_id = auth.uid() AND is_assigned_clinician(patient_id));

CREATE POLICY fhir_import_resources_clinician_select ON fhir_import_resources
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM fhir_imports
      WHERE fhir_imports.id = fhir_import_resources.import_id
        AND is_clinician()
        AND fhir_imports.clinician_id = auth.uid()
        AND is_assigned_clinician(fhir_imports.patient_id)
    )
  );

-- No direct insert/update/delete policy is granted.  The backend creates all
-- launch, import, and handoff records after local clinician authorization.
