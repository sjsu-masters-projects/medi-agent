-- The server-side patient feed and adherence statistics calculate scheduled
-- events from reminder_schedules. Browser roles receive no new table privilege.
GRANT SELECT ON TABLE public.reminder_schedules TO service_role;
