-- ============================================================
-- MediAgent — 001 Initial Schema
-- Creates all enum types, tables, indexes, and triggers.
-- Run against a fresh Supabase project.
-- ============================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- ════════════════════════════════════════════════════
-- ENUM TYPES (mirrors backend/src/app/models/enums.py)
-- ════════════════════════════════════════════════════

CREATE TYPE language_enum AS ENUM ('en', 'es');
CREATE TYPE gender_enum AS ENUM ('male', 'female', 'other', 'prefer_not_to_say');
CREATE TYPE clinician_role_enum AS ENUM ('provider', 'admin', 'nurse');
CREATE TYPE care_team_status_enum AS ENUM ('active', 'inactive', 'transferred');
CREATE TYPE document_type_enum AS ENUM ('lab_report', 'discharge_summary', 'prescription', 'diagnostic_report', 'insurance', 'referral', 'other');
CREATE TYPE document_visibility_enum AS ENUM ('all_providers', 'specific_provider');
CREATE TYPE uploader_role_enum AS ENUM ('patient', 'clinician');
CREATE TYPE medication_route_enum AS ENUM ('oral', 'topical', 'iv', 'im', 'subcutaneous', 'inhaled', 'other');
CREATE TYPE obligation_type_enum AS ENUM ('diet', 'exercise', 'custom');
CREATE TYPE adherence_target_type_enum AS ENUM ('medication', 'obligation');
CREATE TYPE adherence_status_enum AS ENUM ('taken', 'completed', 'skipped', 'missed');
CREATE TYPE naranjo_causality_enum AS ENUM ('Definite', 'Probable', 'Possible', 'Doubtful');
CREATE TYPE adr_status_enum AS ENUM ('draft', 'reviewed', 'submitted', 'dismissed');
CREATE TYPE medwatch_status_enum AS ENUM ('draft', 'reviewed', 'submitted');
CREATE TYPE appointment_type_enum AS ENUM ('follow_up', 'initial', 'routine', 'urgent', 'pre_op');
CREATE TYPE appointment_status_enum AS ENUM ('scheduled', 'completed', 'cancelled', 'no_show');
CREATE TYPE chat_role_enum AS ENUM ('user', 'assistant', 'system');
CREATE TYPE notification_type_enum AS ENUM ('med_reminder', 'missed_dose', 'appointment', 'doctor_message', 'adr_alert', 'obligation_reminder');
CREATE TYPE message_channel_enum AS ENUM ('in_app', 'email');
CREATE TYPE allergy_severity_enum AS ENUM ('mild', 'moderate', 'severe');


-- ════════════════════════════════════════════════════
-- HELPER: auto-update updated_at on row changes
-- ════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ════════════════════════════════════════════════════
-- TABLES
-- ════════════════════════════════════════════════════

-- ── patients ──────────────────────────────────────

CREATE TABLE patients (
  id          uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email       text NOT NULL UNIQUE,
  first_name  text NOT NULL CHECK (char_length(first_name) BETWEEN 1 AND 100),
  last_name   text NOT NULL CHECK (char_length(last_name) BETWEEN 1 AND 100),
  date_of_birth date NOT NULL,
  gender      gender_enum,
  preferred_language language_enum NOT NULL DEFAULT 'en',
  phone       text CHECK (char_length(phone) <= 20),
  avatar_url  text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz
);

CREATE TRIGGER patients_updated_at
  BEFORE UPDATE ON patients
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ── clinicians ────────────────────────────────────

CREATE TABLE clinicians (
  id          uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email       text NOT NULL UNIQUE,
  first_name  text NOT NULL CHECK (char_length(first_name) BETWEEN 1 AND 100),
  last_name   text NOT NULL CHECK (char_length(last_name) BETWEEN 1 AND 100),
  specialty   text NOT NULL CHECK (char_length(specialty) BETWEEN 1 AND 100),
  clinic_name text NOT NULL CHECK (char_length(clinic_name) BETWEEN 1 AND 200),
  npi_number  text CHECK (char_length(npi_number) <= 20),
  role        clinician_role_enum NOT NULL DEFAULT 'provider',
  avatar_url  text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz
);

CREATE TRIGGER clinicians_updated_at
  BEFORE UPDATE ON clinicians
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ── care_teams (junction: patient ↔ clinician) ───

CREATE TABLE care_teams (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id        uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  clinician_id      uuid NOT NULL REFERENCES clinicians(id) ON DELETE CASCADE,
  role              text NOT NULL,  -- e.g. "primary_care", "cardiologist"
  specialty_context text,
  clinic_name       text,
  status            care_team_status_enum NOT NULL DEFAULT 'active',
  created_at        timestamptz NOT NULL DEFAULT now(),

  UNIQUE (patient_id, clinician_id)
);

CREATE INDEX idx_care_teams_patient ON care_teams(patient_id);
CREATE INDEX idx_care_teams_clinician ON care_teams(clinician_id);
CREATE INDEX idx_care_teams_active ON care_teams(patient_id, status) WHERE status = 'active';


-- ── documents ─────────────────────────────────────

CREATE TABLE documents (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id      uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  uploaded_by     uuid NOT NULL REFERENCES auth.users(id),
  uploaded_by_role uploader_role_enum NOT NULL,
  document_type   document_type_enum NOT NULL,
  file_name       text NOT NULL,
  file_url        text NOT NULL,  -- Supabase Storage signed URL path
  mime_type       text NOT NULL DEFAULT 'application/pdf',
  file_size_bytes integer NOT NULL,
  parsed          boolean NOT NULL DEFAULT false,
  ai_summary      text,
  source_clinic   text,
  visibility      document_visibility_enum NOT NULL DEFAULT 'all_providers',
  notes           text,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_documents_patient ON documents(patient_id, created_at DESC);


-- ── medications ───────────────────────────────────

CREATE TABLE medications (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id               uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  name                     text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 200),
  generic_name             text,
  rxcui                    text,  -- RxNorm concept ID
  dosage                   text NOT NULL,
  frequency                text NOT NULL,
  route                    medication_route_enum NOT NULL DEFAULT 'oral',
  prescribed_by_care_team_id uuid REFERENCES care_teams(id) ON DELETE SET NULL,
  start_date               date,
  end_date                 date,
  instructions             text,
  source_document_id       uuid REFERENCES documents(id) ON DELETE SET NULL,
  is_active                boolean NOT NULL DEFAULT true,
  created_at               timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_medications_patient ON medications(patient_id, is_active);


-- ── obligations ───────────────────────────────────

CREATE TABLE obligations (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id            uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  obligation_type       obligation_type_enum NOT NULL,
  description           text NOT NULL CHECK (char_length(description) BETWEEN 1 AND 500),
  frequency             text NOT NULL,
  set_by_care_team_id   uuid REFERENCES care_teams(id) ON DELETE SET NULL,
  is_active             boolean NOT NULL DEFAULT true,
  created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_obligations_patient ON obligations(patient_id, is_active);


-- ── adherence_logs ────────────────────────────────

CREATE TABLE adherence_logs (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id     uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  target_type    adherence_target_type_enum NOT NULL,
  target_id      uuid NOT NULL,  -- FK to medications or obligations (validated at app layer)
  status         adherence_status_enum NOT NULL,
  scheduled_time timestamptz,
  notes          text,
  logged_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_adherence_patient ON adherence_logs(patient_id, logged_at DESC);
CREATE INDEX idx_adherence_target ON adherence_logs(target_type, target_id, logged_at DESC);


-- ── conditions ────────────────────────────────────

CREATE TABLE conditions (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  name       text NOT NULL,
  icd10_code text,
  status     text NOT NULL DEFAULT 'active',
  notes      text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_conditions_patient ON conditions(patient_id);


-- ── allergies ─────────────────────────────────────

CREATE TABLE allergies (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  allergen   text NOT NULL,
  reaction   text,
  severity   allergy_severity_enum NOT NULL DEFAULT 'moderate',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_allergies_patient ON allergies(patient_id);


-- ── symptom_reports ───────────────────────────────

CREATE TABLE symptom_reports (
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id              uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  symptom                 text NOT NULL CHECK (char_length(symptom) BETWEEN 1 AND 300),
  severity                smallint NOT NULL CHECK (severity BETWEEN 1 AND 10),
  onset                   text,
  duration                text,
  related_medication_id   uuid REFERENCES medications(id) ON DELETE SET NULL,
  related_medication_name text,  -- denormalized
  body_area               text,
  ai_assessment           text,  -- Symptom Agent output
  flagged_for_adr         boolean NOT NULL DEFAULT false,
  notes                   text,
  created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_symptoms_patient ON symptom_reports(patient_id, created_at DESC);


-- ── adr_assessments ───────────────────────────────

CREATE TABLE adr_assessments (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id               uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  symptom_report_id        uuid NOT NULL REFERENCES symptom_reports(id) ON DELETE CASCADE,
  suspect_medication_id    uuid NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
  suspect_medication_name  text NOT NULL,  -- denormalized
  naranjo_score            smallint NOT NULL CHECK (naranjo_score BETWEEN 0 AND 13),
  causality                naranjo_causality_enum NOT NULL,
  thinking_chain           text,  -- Gemini Pro thinking trace
  status                   adr_status_enum NOT NULL DEFAULT 'draft',
  reviewed_by              uuid REFERENCES clinicians(id) ON DELETE SET NULL,
  reviewed_at              timestamptz,
  dismiss_reason           text,
  created_at               timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_adr_patient ON adr_assessments(patient_id, created_at DESC);
CREATE INDEX idx_adr_status ON adr_assessments(status);


-- ── medwatch_drafts ───────────────────────────────

CREATE TABLE medwatch_drafts (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  adr_assessment_id uuid NOT NULL REFERENCES adr_assessments(id) ON DELETE CASCADE,
  patient_id        uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  form_data         jsonb NOT NULL DEFAULT '{}',  -- FDA 3500A field values
  de_identified     boolean NOT NULL DEFAULT false,
  status            medwatch_status_enum NOT NULL DEFAULT 'draft',
  submitted_at      timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_medwatch_patient ON medwatch_drafts(patient_id);
CREATE INDEX idx_medwatch_status ON medwatch_drafts(status);


-- ── appointments ──────────────────────────────────

CREATE TABLE appointments (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id         uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  care_team_id       uuid NOT NULL REFERENCES care_teams(id) ON DELETE CASCADE,
  clinician_name     text,  -- denormalized
  scheduled_at       timestamptz NOT NULL,
  duration_minutes   smallint NOT NULL DEFAULT 30 CHECK (duration_minutes BETWEEN 5 AND 480),
  appointment_type   appointment_type_enum NOT NULL DEFAULT 'follow_up',
  location           text,
  reason             text,
  notes              text,
  status             appointment_status_enum NOT NULL DEFAULT 'scheduled',
  source_document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_appointments_patient ON appointments(patient_id, scheduled_at DESC);
CREATE INDEX idx_appointments_upcoming ON appointments(scheduled_at) WHERE status = 'scheduled';


-- ── chat_messages ─────────────────────────────────

CREATE TABLE chat_messages (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  content    text NOT NULL,
  role       chat_role_enum NOT NULL,
  intent     text,  -- classified by Triage Agent
  language   language_enum NOT NULL DEFAULT 'en',
  audio_url  text,  -- voice message storage path
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_patient ON chat_messages(patient_id, created_at DESC);


-- ── notifications ─────────────────────────────────

CREATE TABLE notifications (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id        uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  notification_type notification_type_enum NOT NULL,
  title             text NOT NULL CHECK (char_length(title) <= 200),
  body              text NOT NULL CHECK (char_length(body) <= 1000),
  action_url        text,  -- deep link
  is_read           boolean NOT NULL DEFAULT false,
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_notifications_patient ON notifications(patient_id, is_read, created_at DESC);


-- ── clinician_messages ────────────────────────────

CREATE TABLE clinician_messages (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  clinician_id  uuid NOT NULL REFERENCES clinicians(id) ON DELETE CASCADE,
  patient_id    uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  channel       message_channel_enum NOT NULL,
  subject       text CHECK (char_length(subject) <= 200),  -- email only
  body          text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 5000),
  is_read       boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_clinmsg_patient ON clinician_messages(patient_id, created_at DESC);
CREATE INDEX idx_clinmsg_clinician ON clinician_messages(clinician_id, created_at DESC);
