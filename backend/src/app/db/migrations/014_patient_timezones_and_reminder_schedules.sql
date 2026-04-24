-- ============================================================
-- MediAgent — 014 Patient Timezones and Reminder Schedules
-- Adds patient timezone preferences, obligation notes, and
-- first-class reminder schedules for medications and obligations.
-- ============================================================

ALTER TABLE patients
  ADD COLUMN IF NOT EXISTS timezone text NOT NULL DEFAULT 'UTC'
  CHECK (char_length(timezone) BETWEEN 1 AND 64);

ALTER TABLE obligations
  ADD COLUMN IF NOT EXISTS notes text;

CREATE TABLE IF NOT EXISTS reminder_schedules (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id   uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  target_type  adherence_target_type_enum NOT NULL,
  target_id    uuid NOT NULL,
  timezone     text NOT NULL CHECK (char_length(timezone) BETWEEN 1 AND 64),
  times_of_day jsonb NOT NULL DEFAULT '[]'::jsonb,
  days_of_week jsonb NOT NULL DEFAULT '["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]'::jsonb,
  is_enabled   boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_reminder_schedules_target
  ON reminder_schedules(patient_id, target_type, target_id);

CREATE INDEX IF NOT EXISTS idx_reminder_schedules_patient
  ON reminder_schedules(patient_id, is_enabled);

CREATE TRIGGER reminder_schedules_updated_at
  BEFORE UPDATE ON reminder_schedules
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

ALTER TABLE reminder_schedules ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'reminder_schedules'
      AND policyname = 'reminder_schedules_patient_select'
  ) THEN
    CREATE POLICY reminder_schedules_patient_select ON reminder_schedules
      FOR SELECT USING (patient_id = auth.uid());
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'reminder_schedules'
      AND policyname = 'reminder_schedules_patient_insert'
  ) THEN
    CREATE POLICY reminder_schedules_patient_insert ON reminder_schedules
      FOR INSERT WITH CHECK (patient_id = auth.uid());
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'reminder_schedules'
      AND policyname = 'reminder_schedules_patient_update'
  ) THEN
    CREATE POLICY reminder_schedules_patient_update ON reminder_schedules
      FOR UPDATE USING (patient_id = auth.uid());
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'reminder_schedules'
      AND policyname = 'reminder_schedules_clinician_select'
  ) THEN
    CREATE POLICY reminder_schedules_clinician_select ON reminder_schedules
      FOR SELECT USING (is_clinician() AND is_assigned_clinician(patient_id));
  END IF;
END $$;
