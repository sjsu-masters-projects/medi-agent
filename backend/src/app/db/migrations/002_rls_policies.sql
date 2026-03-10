-- ============================================================
-- MediAgent — 002 Row-Level Security Policies
-- Enforces data isolation: patients see own data,
-- clinicians see assigned patients via care_teams.
-- ============================================================

-- ════════════════════════════════════════════════════
-- HELPER FUNCTION
-- ════════════════════════════════════════════════════

-- Returns true if the current JWT user is an active clinician
-- assigned to the given patient via care_teams.
CREATE OR REPLACE FUNCTION is_assigned_clinician(p_patient_id uuid)
RETURNS boolean AS $$
  SELECT EXISTS (
    SELECT 1 FROM care_teams
    WHERE clinician_id = auth.uid()
      AND patient_id = p_patient_id
      AND status = 'active'
  );
$$ LANGUAGE sql SECURITY DEFINER STABLE;

-- Returns true if the current JWT user exists in the patients table.
CREATE OR REPLACE FUNCTION is_patient()
RETURNS boolean AS $$
  SELECT EXISTS (SELECT 1 FROM patients WHERE id = auth.uid());
$$ LANGUAGE sql SECURITY DEFINER STABLE;

-- Returns true if the current JWT user exists in the clinicians table.
CREATE OR REPLACE FUNCTION is_clinician()
RETURNS boolean AS $$
  SELECT EXISTS (SELECT 1 FROM clinicians WHERE id = auth.uid());
$$ LANGUAGE sql SECURITY DEFINER STABLE;


-- ════════════════════════════════════════════════════
-- ENABLE RLS ON ALL TABLES
-- ════════════════════════════════════════════════════

ALTER TABLE patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE clinicians ENABLE ROW LEVEL SECURITY;
ALTER TABLE care_teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE medications ENABLE ROW LEVEL SECURITY;
ALTER TABLE obligations ENABLE ROW LEVEL SECURITY;
ALTER TABLE adherence_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE conditions ENABLE ROW LEVEL SECURITY;
ALTER TABLE allergies ENABLE ROW LEVEL SECURITY;
ALTER TABLE symptom_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE adr_assessments ENABLE ROW LEVEL SECURITY;
ALTER TABLE medwatch_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE clinician_messages ENABLE ROW LEVEL SECURITY;


-- ════════════════════════════════════════════════════
-- PATIENTS
-- ════════════════════════════════════════════════════

-- Patient sees own row
CREATE POLICY patients_own_select ON patients
  FOR SELECT USING (id = auth.uid());

-- Patient updates own row
CREATE POLICY patients_own_update ON patients
  FOR UPDATE USING (id = auth.uid());

-- Patient inserts own row (during signup)
CREATE POLICY patients_own_insert ON patients
  FOR INSERT WITH CHECK (id = auth.uid());

-- Clinician sees assigned patients
CREATE POLICY patients_clinician_select ON patients
  FOR SELECT USING (is_clinician() AND is_assigned_clinician(id));


-- ════════════════════════════════════════════════════
-- CLINICIANS
-- ════════════════════════════════════════════════════

-- Clinician sees own row
CREATE POLICY clinicians_own_select ON clinicians
  FOR SELECT USING (id = auth.uid());

-- Clinician updates own row
CREATE POLICY clinicians_own_update ON clinicians
  FOR UPDATE USING (id = auth.uid());

-- Clinician inserts own row (during signup)
CREATE POLICY clinicians_own_insert ON clinicians
  FOR INSERT WITH CHECK (id = auth.uid());

-- Patient sees their care team clinicians
CREATE POLICY clinicians_patient_select ON clinicians
  FOR SELECT USING (
    is_patient() AND EXISTS (
      SELECT 1 FROM care_teams
      WHERE care_teams.clinician_id = clinicians.id
        AND care_teams.patient_id = auth.uid()
        AND care_teams.status = 'active'
    )
  );


-- ════════════════════════════════════════════════════
-- CARE TEAMS
-- ════════════════════════════════════════════════════

-- Patient sees own memberships
CREATE POLICY care_teams_patient_select ON care_teams
  FOR SELECT USING (patient_id = auth.uid());

-- Patient can join a clinic (insert)
CREATE POLICY care_teams_patient_insert ON care_teams
  FOR INSERT WITH CHECK (patient_id = auth.uid());

-- Clinician sees own memberships
CREATE POLICY care_teams_clinician_select ON care_teams
  FOR SELECT USING (clinician_id = auth.uid());

-- Clinician can add patients
CREATE POLICY care_teams_clinician_insert ON care_teams
  FOR INSERT WITH CHECK (clinician_id = auth.uid());

-- Clinician can update status (e.g. transferred)
CREATE POLICY care_teams_clinician_update ON care_teams
  FOR UPDATE USING (clinician_id = auth.uid());


-- ════════════════════════════════════════════════════
-- DOCUMENTS
-- ════════════════════════════════════════════════════

-- Patient sees own documents
CREATE POLICY documents_patient_select ON documents
  FOR SELECT USING (patient_id = auth.uid());

-- Patient uploads documents
CREATE POLICY documents_patient_insert ON documents
  FOR INSERT WITH CHECK (patient_id = auth.uid());

-- Clinician sees assigned patients' docs (respecting visibility)
CREATE POLICY documents_clinician_select ON documents
  FOR SELECT USING (
    is_clinician() AND is_assigned_clinician(patient_id)
    AND (
      visibility = 'all_providers'
      OR uploaded_by = auth.uid()
    )
  );

-- Clinician uploads to assigned patient
CREATE POLICY documents_clinician_insert ON documents
  FOR INSERT WITH CHECK (
    is_clinician() AND is_assigned_clinician(patient_id)
  );


-- ════════════════════════════════════════════════════
-- MEDICATIONS
-- ════════════════════════════════════════════════════

-- Patient sees own medications
CREATE POLICY medications_patient_select ON medications
  FOR SELECT USING (patient_id = auth.uid());

-- Clinician sees assigned patients' medications
CREATE POLICY medications_clinician_select ON medications
  FOR SELECT USING (is_clinician() AND is_assigned_clinician(patient_id));

-- Clinician creates medications for assigned patients
CREATE POLICY medications_clinician_insert ON medications
  FOR INSERT WITH CHECK (is_clinician() AND is_assigned_clinician(patient_id));

-- Clinician updates medications for assigned patients
CREATE POLICY medications_clinician_update ON medications
  FOR UPDATE USING (is_clinician() AND is_assigned_clinician(patient_id));


-- ════════════════════════════════════════════════════
-- OBLIGATIONS
-- ════════════════════════════════════════════════════

CREATE POLICY obligations_patient_select ON obligations
  FOR SELECT USING (patient_id = auth.uid());

CREATE POLICY obligations_clinician_select ON obligations
  FOR SELECT USING (is_clinician() AND is_assigned_clinician(patient_id));

CREATE POLICY obligations_clinician_insert ON obligations
  FOR INSERT WITH CHECK (is_clinician() AND is_assigned_clinician(patient_id));

CREATE POLICY obligations_clinician_update ON obligations
  FOR UPDATE USING (is_clinician() AND is_assigned_clinician(patient_id));


-- ════════════════════════════════════════════════════
-- ADHERENCE LOGS
-- ════════════════════════════════════════════════════

-- Patient logs own adherence
CREATE POLICY adherence_patient_select ON adherence_logs
  FOR SELECT USING (patient_id = auth.uid());

CREATE POLICY adherence_patient_insert ON adherence_logs
  FOR INSERT WITH CHECK (patient_id = auth.uid());

-- Clinician reads assigned patients' adherence
CREATE POLICY adherence_clinician_select ON adherence_logs
  FOR SELECT USING (is_clinician() AND is_assigned_clinician(patient_id));


-- ════════════════════════════════════════════════════
-- CONDITIONS
-- ════════════════════════════════════════════════════

CREATE POLICY conditions_patient_select ON conditions
  FOR SELECT USING (patient_id = auth.uid());

CREATE POLICY conditions_clinician_select ON conditions
  FOR SELECT USING (is_clinician() AND is_assigned_clinician(patient_id));

CREATE POLICY conditions_clinician_insert ON conditions
  FOR INSERT WITH CHECK (is_clinician() AND is_assigned_clinician(patient_id));


-- ════════════════════════════════════════════════════
-- ALLERGIES
-- ════════════════════════════════════════════════════

CREATE POLICY allergies_patient_select ON allergies
  FOR SELECT USING (patient_id = auth.uid());

CREATE POLICY allergies_clinician_select ON allergies
  FOR SELECT USING (is_clinician() AND is_assigned_clinician(patient_id));

CREATE POLICY allergies_clinician_insert ON allergies
  FOR INSERT WITH CHECK (is_clinician() AND is_assigned_clinician(patient_id));


-- ════════════════════════════════════════════════════
-- SYMPTOM REPORTS
-- ════════════════════════════════════════════════════

CREATE POLICY symptoms_patient_select ON symptom_reports
  FOR SELECT USING (patient_id = auth.uid());

CREATE POLICY symptoms_patient_insert ON symptom_reports
  FOR INSERT WITH CHECK (patient_id = auth.uid());

CREATE POLICY symptoms_clinician_select ON symptom_reports
  FOR SELECT USING (is_clinician() AND is_assigned_clinician(patient_id));


-- ════════════════════════════════════════════════════
-- ADR ASSESSMENTS
-- ════════════════════════════════════════════════════

-- Patient sees own ADR assessments (read-only)
CREATE POLICY adr_patient_select ON adr_assessments
  FOR SELECT USING (patient_id = auth.uid());

-- Clinician reads + reviews ADR assessments for assigned patients
CREATE POLICY adr_clinician_select ON adr_assessments
  FOR SELECT USING (is_clinician() AND is_assigned_clinician(patient_id));

CREATE POLICY adr_clinician_update ON adr_assessments
  FOR UPDATE USING (is_clinician() AND is_assigned_clinician(patient_id));


-- ════════════════════════════════════════════════════
-- MEDWATCH DRAFTS (clinician-only)
-- ════════════════════════════════════════════════════

CREATE POLICY medwatch_clinician_select ON medwatch_drafts
  FOR SELECT USING (is_clinician() AND is_assigned_clinician(patient_id));

CREATE POLICY medwatch_clinician_update ON medwatch_drafts
  FOR UPDATE USING (is_clinician() AND is_assigned_clinician(patient_id));


-- ════════════════════════════════════════════════════
-- APPOINTMENTS
-- ════════════════════════════════════════════════════

CREATE POLICY appointments_patient_select ON appointments
  FOR SELECT USING (patient_id = auth.uid());

CREATE POLICY appointments_clinician_select ON appointments
  FOR SELECT USING (is_clinician() AND is_assigned_clinician(patient_id));

CREATE POLICY appointments_clinician_insert ON appointments
  FOR INSERT WITH CHECK (is_clinician() AND is_assigned_clinician(patient_id));

CREATE POLICY appointments_clinician_update ON appointments
  FOR UPDATE USING (is_clinician() AND is_assigned_clinician(patient_id));


-- ════════════════════════════════════════════════════
-- CHAT MESSAGES
-- ════════════════════════════════════════════════════

-- Patient sees and writes own chat
CREATE POLICY chat_patient_select ON chat_messages
  FOR SELECT USING (patient_id = auth.uid());

CREATE POLICY chat_patient_insert ON chat_messages
  FOR INSERT WITH CHECK (patient_id = auth.uid());

-- Clinician reads assigned patients' chat (transcript review)
CREATE POLICY chat_clinician_select ON chat_messages
  FOR SELECT USING (is_clinician() AND is_assigned_clinician(patient_id));


-- ════════════════════════════════════════════════════
-- NOTIFICATIONS
-- ════════════════════════════════════════════════════

-- Patient sees and marks own notifications
CREATE POLICY notifications_patient_select ON notifications
  FOR SELECT USING (patient_id = auth.uid());

CREATE POLICY notifications_patient_update ON notifications
  FOR UPDATE USING (patient_id = auth.uid());  -- mark as read

-- Clinician can create notifications for assigned patients
CREATE POLICY notifications_clinician_insert ON notifications
  FOR INSERT WITH CHECK (is_clinician() AND is_assigned_clinician(patient_id));


-- ════════════════════════════════════════════════════
-- CLINICIAN MESSAGES
-- ════════════════════════════════════════════════════

-- Patient sees messages sent to them
CREATE POLICY clinmsg_patient_select ON clinician_messages
  FOR SELECT USING (patient_id = auth.uid());

-- Patient marks messages as read
CREATE POLICY clinmsg_patient_update ON clinician_messages
  FOR UPDATE USING (patient_id = auth.uid());

-- Clinician sees messages they sent
CREATE POLICY clinmsg_clinician_select ON clinician_messages
  FOR SELECT USING (clinician_id = auth.uid());

-- Clinician sends messages to assigned patients
CREATE POLICY clinmsg_clinician_insert ON clinician_messages
  FOR INSERT WITH CHECK (
    clinician_id = auth.uid()
    AND is_assigned_clinician(patient_id)
  );
