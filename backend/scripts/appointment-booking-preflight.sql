-- Read-only preflight before 043. Zero rows means no existing overlap pairs.
-- Review any returned bookings; never auto-cancel or delete them to pass migration.
WITH booked AS (
  SELECT id, patient_id, tsrange(scheduled_at AT TIME ZONE 'UTC',
    (scheduled_at AT TIME ZONE 'UTC') + duration_minutes * interval '1 minute', '[)') AS during
  FROM public.appointments WHERE status IN ('confirmed', 'scheduled')
)
SELECT a.patient_id, a.id AS appointment_id, b.id AS overlapping_appointment_id
FROM booked a JOIN booked b ON a.patient_id = b.patient_id AND a.id < b.id
  AND a.during && b.during
ORDER BY a.patient_id, a.id, b.id;
