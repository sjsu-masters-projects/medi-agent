-- Commit this enum addition before 043 consumes it. Preserve applied 038–041 files.
ALTER TYPE appointment_status_enum ADD VALUE IF NOT EXISTS 'expired';
