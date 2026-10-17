-- Read-only preflight before 069. Zero rows means no confirmed/scheduled visits overlap for
-- one clinician across any of their clinics. Review any returned pair; never auto-cancel or
-- delete bookings to pass the migration. Identifiers only appear here, never in the migration.
WITH booked AS (
  SELECT a.id, t.clinician_id, t.clinic_id,
    tsrange(a.scheduled_at AT TIME ZONE 'UTC',
      (a.scheduled_at AT TIME ZONE 'UTC') + a.duration_minutes * interval '1 minute', '[)') AS during
  FROM public.appointments a JOIN public.care_teams t ON t.id = a.care_team_id
  WHERE a.status IN ('confirmed', 'scheduled')
)
SELECT a.clinician_id, a.id AS appointment_id, a.clinic_id,
       b.id AS overlapping_appointment_id, b.clinic_id AS overlapping_clinic_id
FROM booked a JOIN booked b ON a.clinician_id = b.clinician_id AND a.id < b.id
  AND a.during && b.during
ORDER BY a.clinician_id, a.id, b.id;
