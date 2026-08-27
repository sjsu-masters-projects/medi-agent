-- The server-side patient feed and adherence statistics read these tables using
-- the Supabase service role. Browser roles receive no new table privileges.
GRANT SELECT ON TABLE public.adherence_logs, public.obligations TO service_role;
