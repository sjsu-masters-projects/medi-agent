-- Appointment proposal lifecycle (SCH-001, Slice 1)
--
-- Adds the states a proposed appointment moves through: a clinician offers a
-- slot ('proposed'), and the patient either accepts it ('confirmed') or turns
-- it down ('declined'). The existing states ('scheduled', 'completed',
-- 'cancelled', 'no_show') are unchanged.
--
-- Deploy ordering: application code that writes these values must not reach a
-- database that has not run this migration, or the write is rejected. Apply
-- this migration before deploying the SCH-001 backend change.
--
-- Note: ALTER TYPE ... ADD VALUE cannot be used in the same transaction that
-- consumes the new value, so this migration only extends the enum and touches
-- nothing that references the new labels.

ALTER TYPE appointment_status_enum ADD VALUE IF NOT EXISTS 'proposed';
ALTER TYPE appointment_status_enum ADD VALUE IF NOT EXISTS 'confirmed';
ALTER TYPE appointment_status_enum ADD VALUE IF NOT EXISTS 'declined';
