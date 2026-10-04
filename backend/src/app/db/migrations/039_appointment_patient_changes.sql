-- Patient-initiated appointment changes (SCH-001, Slice 2)
--
-- Adds the state a patient reaches when they ask for a different time instead of
-- accepting or declining ('alternative_requested'), and a nullable free-text
-- 'patient_note' so a patient can say why they are requesting a change or
-- cancelling. Existing statuses are unchanged; cancelling reuses the existing
-- 'cancelled' status.
--
-- Deploy ordering: application code that writes 'alternative_requested' or
-- patient_note must not reach a database that has not run this migration. Apply
-- this migration before deploying the SCH-001 Slice 2 backend change.
--
-- Note: ALTER TYPE ... ADD VALUE cannot be used in the same transaction that
-- consumes the new value; this migration only extends the enum and adds a
-- nullable column, using neither.

ALTER TYPE appointment_status_enum ADD VALUE IF NOT EXISTS 'alternative_requested';

ALTER TABLE public.appointments
  ADD COLUMN IF NOT EXISTS patient_note text;
