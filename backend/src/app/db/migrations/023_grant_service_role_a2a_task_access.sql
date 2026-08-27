-- The backend retry worker persists and redrives A2A task lifecycle state with
-- the server-only service role. Keep this access separate from browser roles:
-- anon and authenticated receive no table grants here, and DELETE is not needed.
GRANT SELECT, INSERT, UPDATE ON TABLE public.a2a_tasks TO service_role;
